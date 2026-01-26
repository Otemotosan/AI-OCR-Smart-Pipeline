#!/bin/bash
# =============================================================================
# AI-OCR Smart Pipeline - Deployment Script
# =============================================================================
# Usage:
#   ./deploy.sh [staging|production] [--skip-tests] [--skip-build] [--dry-run]
#
# Options:
#   --skip-tests   Skip running tests before deployment
#   --skip-build   Skip building Docker images
#   --dry-run      Show what would be deployed without making changes
#
# Requirements:
#   - gcloud CLI configured with appropriate permissions
#   - Docker installed (for image builds)
#   - Environment file (deploy/.env.{environment})
# =============================================================================


# Validating environment...
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
ENVIRONMENT="${1:-staging}"
SKIP_TESTS=false
SKIP_BUILD=false
DRY_RUN=false

shift || true
for arg in "$@"; do
    case $arg in
        --skip-tests) SKIP_TESTS=true ;;
        --skip-build) SKIP_BUILD=true ;;
        --dry-run) DRY_RUN=true ;;
        *) log_error "Unknown argument: $arg"; exit 1 ;;
    esac
done

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
    log_error "Invalid environment: $ENVIRONMENT. Must be 'staging' or 'production'"
    exit 1
fi

# Load environment variables
ENV_FILE="deploy/.env.${ENVIRONMENT}"
if [ -f "$ENV_FILE" ]; then
    log_info "Loading environment from $ENV_FILE"
    # shellcheck disable=SC1090
    source "$ENV_FILE"
elif [ -f "deploy/.env" ]; then
    log_warn "Using default .env file"
    source "deploy/.env"
else
    log_error "No environment file found. Copy deploy/env.example to $ENV_FILE"
    exit 1
fi

# Validate required environment variables
REQUIRED_VARS=(
    "GCP_PROJECT_ID"
    "GCP_REGION"
    "INPUT_BUCKET"
    "OUTPUT_BUCKET"
    "QUARANTINE_BUCKET"
    "BIGQUERY_DATASET"
    "DOCUMENT_AI_PROCESSOR"
)

log_info "Validating environment variables..."
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var:-}" ]; then
        log_error "Required variable $var is not set"
        exit 1
    fi
done
log_success "All required variables are set"

# Display deployment configuration
echo ""
echo "=============================================="
echo "  AI-OCR Smart Pipeline Deployment"
echo "=============================================="
echo ""
echo "  Environment:     $ENVIRONMENT"
echo "  Project:         $GCP_PROJECT_ID"
echo "  Region:          $GCP_REGION"
echo "  Input Bucket:    $INPUT_BUCKET"
echo "  Output Bucket:   $OUTPUT_BUCKET"
echo "  Quarantine:      $QUARANTINE_BUCKET"
echo "  BigQuery:        $BIGQUERY_DATASET"
echo "  Skip Tests:      $SKIP_TESTS"
echo "  Skip Build:      $SKIP_BUILD"
echo "  Dry Run:         $DRY_RUN"
echo ""
echo "=============================================="
echo ""

if [ "$DRY_RUN" = true ]; then
    log_warn "DRY RUN MODE - No changes will be made"
fi

# Confirm production deployment
if [ "$ENVIRONMENT" = "production" ] && [ "$DRY_RUN" = false ]; then
    read -p "You are deploying to PRODUCTION. Are you sure? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        log_info "Deployment cancelled"
        exit 0
    fi
fi

# Set gcloud project
log_info "Configuring gcloud project..."
if [ "$DRY_RUN" = false ]; then
    gcloud config set project "${GCP_PROJECT_ID}"
fi

# =============================================================================
# Step 1: Run Tests
# =============================================================================
if [ "$SKIP_TESTS" = false ]; then
    log_info "Running tests..."
    if [ "$DRY_RUN" = false ]; then
        pytest tests/unit -v --cov=src/core --cov-fail-under=80 || {
            log_error "Tests failed. Aborting deployment."
            exit 1
        }
        log_success "Tests passed"
    else
        log_info "[DRY RUN] Would run: pytest tests/unit -v --cov=src/core --cov-fail-under=80"
    fi
else
    log_warn "Skipping tests (--skip-tests flag)"
fi

# =============================================================================
# Step 2: Enable Required APIs
# =============================================================================
log_info "Enabling required APIs..."
APIS=(
    "cloudfunctions.googleapis.com"
    "cloudbuild.googleapis.com"
    "cloudscheduler.googleapis.com"
    "documentai.googleapis.com"
    "aiplatform.googleapis.com"
    "firestore.googleapis.com"
    "bigquery.googleapis.com"
    "storage.googleapis.com"
    "secretmanager.googleapis.com"
    "run.googleapis.com"
    "pubsub.googleapis.com"
    "logging.googleapis.com"
    "monitoring.googleapis.com"
)

for api in "${APIS[@]}"; do
    if [ "$DRY_RUN" = false ]; then
        gcloud services enable "$api" --quiet 2>/dev/null || true
    else
        log_info "[DRY RUN] Would enable: $api"
    fi
done
log_success "APIs enabled"

# =============================================================================
# Step 3: Create GCS Buckets
# =============================================================================
log_info "Creating GCS buckets..."

create_bucket() {
    local BUCKET=$1
    local LIFECYCLE_DAYS=${2:-0}

    if [ "$DRY_RUN" = false ]; then
        if ! gsutil ls "gs://${BUCKET}" &>/dev/null; then
            log_info "Creating bucket: $BUCKET"
            gsutil mb -l "${GCP_REGION}" "gs://${BUCKET}"
            gsutil uniformbucketlevelaccess set on "gs://${BUCKET}"

            if [ "$LIFECYCLE_DAYS" -gt 0 ]; then
                cat > /tmp/lifecycle.json << EOF
{
  "rule": [{
    "action": {"type": "Delete"},
    "condition": {"age": $LIFECYCLE_DAYS}
  }]
}
EOF
                gsutil lifecycle set /tmp/lifecycle.json "gs://${BUCKET}"
                rm /tmp/lifecycle.json
            fi
        else
            log_info "Bucket exists: $BUCKET"
        fi
    else
        log_info "[DRY RUN] Would create bucket: $BUCKET"
    fi
}

create_bucket "${INPUT_BUCKET}" 7
create_bucket "${OUTPUT_BUCKET}" 0
create_bucket "${QUARANTINE_BUCKET}" 30
log_success "Buckets configured"

# =============================================================================
# Step 4: Create BigQuery Dataset
# =============================================================================
log_info "Creating BigQuery dataset..."

if [ "$DRY_RUN" = false ]; then
    if ! bq show "${GCP_PROJECT_ID}:${BIGQUERY_DATASET}" &>/dev/null 2>&1; then
        log_info "Creating dataset: ${BIGQUERY_DATASET}"
        bq mk --location="${GCP_REGION}" "${GCP_PROJECT_ID}:${BIGQUERY_DATASET}"
    else
        log_info "Dataset exists: ${BIGQUERY_DATASET}"
    fi
else
    log_info "[DRY RUN] Would create dataset: ${BIGQUERY_DATASET}"
fi
log_success "BigQuery configured"

# =============================================================================
# Step 5: Create Service Account
# =============================================================================
log_info "Creating service account..."

SERVICE_ACCOUNT="ocr-processor@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
SA_NAME="ocr-processor"

if [ "$DRY_RUN" = false ]; then
    if ! gcloud iam service-accounts describe "${SERVICE_ACCOUNT}" &>/dev/null 2>&1; then
        log_info "Creating service account: ${SA_NAME}"
        gcloud iam service-accounts create "${SA_NAME}" \
            --display-name="OCR Pipeline Processor (${ENVIRONMENT})"
    else
        log_info "Service account exists: ${SA_NAME}"
    fi

    # Grant roles
    ROLES=(
        "roles/storage.objectAdmin"
        "roles/datastore.user"
        "roles/bigquery.dataEditor"
        "roles/documentai.apiUser"
        "roles/aiplatform.user"
        "roles/logging.logWriter"
        "roles/monitoring.metricWriter"
        "roles/pubsub.publisher"
        "roles/eventarc.eventReceiver"
    )

    log_info "Granting roles to service account..."
    for ROLE in "${ROLES[@]}"; do
        gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
            --member="serviceAccount:${SERVICE_ACCOUNT}" \
            --role="${ROLE}" \
            --condition=None \
            --quiet 2>/dev/null || true
    done
else
    log_info "[DRY RUN] Would create service account and grant roles"
fi
log_success "Service account configured"

# =============================================================================
# Step 6: Configure Secrets
# =============================================================================
log_info "Configuring secrets..."

create_or_update_secret() {
    local SECRET_NAME=$1
    local SECRET_VALUE=$2

    if [ -z "${SECRET_VALUE}" ]; then
        log_warn "Secret ${SECRET_NAME} value not set, skipping..."
        return
    fi

    if [ "$DRY_RUN" = false ]; then
        if gcloud secrets describe "${SECRET_NAME}" &>/dev/null 2>&1; then
            log_info "Updating secret: ${SECRET_NAME}"
            echo -n "${SECRET_VALUE}" | gcloud secrets versions add "${SECRET_NAME}" --data-file=-
        else
            log_info "Creating secret: ${SECRET_NAME}"
            echo -n "${SECRET_VALUE}" | gcloud secrets create "${SECRET_NAME}" --data-file=-
        fi

        # Grant access to service account
        gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
            --member="serviceAccount:${SERVICE_ACCOUNT}" \
            --role="roles/secretmanager.secretAccessor" \
            --quiet 2>/dev/null || true
    else
        log_info "[DRY RUN] Would configure secret: ${SECRET_NAME}"
    fi
}

create_or_update_secret "gemini-api-key-${ENVIRONMENT}" "${GEMINI_API_KEY:-}"
create_or_update_secret "slack-webhook-${ENVIRONMENT}" "${SLACK_WEBHOOK_URL:-}"
log_success "Secrets configured"

# =============================================================================
# Step 7: Create Pub/Sub Topics
# =============================================================================
log_info "Creating Pub/Sub topics..."

if [ "$DRY_RUN" = false ]; then
    if ! gcloud pubsub topics describe "ocr-dead-letter-${ENVIRONMENT}" &>/dev/null 2>&1; then
        gcloud pubsub topics create "ocr-dead-letter-${ENVIRONMENT}"
        log_info "Created dead letter topic"
    else
        log_info "Dead letter topic exists"
    fi
else
    log_info "[DRY RUN] Would create Pub/Sub topics"
fi
log_success "Pub/Sub configured"

# =============================================================================
# Step 8: Build Docker Images (if not skipping)
# =============================================================================
if [ "$SKIP_BUILD" = false ]; then
    log_info "Building Docker images..."

    IMAGE_TAG="${GIT_SHA:-$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')}"

    if [ "$DRY_RUN" = false ]; then
        # Build processor image using Cloud Build
        log_info "Submitting build for processor image..."
        # gcloud builds submit requires Dockerfile at root or a cloudbuild.yaml
        cp deploy/Dockerfile Dockerfile
        gcloud builds submit --tag "asia.gcr.io/${GCP_PROJECT_ID}/ocr-processor:${IMAGE_TAG}" . --quiet
        rm Dockerfile
        gcloud container images add-tag "asia.gcr.io/${GCP_PROJECT_ID}/ocr-processor:${IMAGE_TAG}" "asia.gcr.io/${GCP_PROJECT_ID}/ocr-processor:latest" --quiet

        # Build API image if Dockerfile exists
        if [ -f "deploy/Dockerfile.api" ]; then
            log_info "Submitting build for API image..."
            cp deploy/Dockerfile.api Dockerfile
            gcloud builds submit --tag "asia.gcr.io/${GCP_PROJECT_ID}/ocr-api:${IMAGE_TAG}" . --quiet
            rm Dockerfile
            gcloud container images add-tag "asia.gcr.io/${GCP_PROJECT_ID}/ocr-api:${IMAGE_TAG}" "asia.gcr.io/${GCP_PROJECT_ID}/ocr-api:latest" --quiet
        fi

        # Build UI image if Dockerfile exists
        if [ -f "deploy/Dockerfile.ui" ]; then
            log_info "Submitting build for UI image..."
            cp deploy/Dockerfile.ui Dockerfile
            gcloud builds submit --tag "asia.gcr.io/${GCP_PROJECT_ID}/ocr-ui:${IMAGE_TAG}" . --quiet
            rm Dockerfile
            gcloud container images add-tag "asia.gcr.io/${GCP_PROJECT_ID}/ocr-ui:${IMAGE_TAG}" "asia.gcr.io/${GCP_PROJECT_ID}/ocr-ui:latest" --quiet
        fi

        log_success "Images built and pushed via Cloud Build"
    else
        log_info "[DRY RUN] Would build and push Docker images using Cloud Build"
    fi
else
    log_warn "Skipping image build (--skip-build flag)"
fi

# =============================================================================
# Step 9: Deploy Cloud Functions
# =============================================================================
log_info "Deploying Cloud Functions..."

if [ "$DRY_RUN" = false ]; then
    # Deploy processor function
    log_info "Deploying ocr-processor-${ENVIRONMENT}..."
    gcloud functions deploy "ocr-processor-${ENVIRONMENT}" \
        --gen2 \
        --runtime=python311 \
        --region="${GCP_REGION}" \
        --source=. \
        --entry-point=process_document \
        --trigger-bucket="${INPUT_BUCKET}" \
        --service-account="${SERVICE_ACCOUNT}" \
        --memory=1Gi \
        --timeout=540s \
        --max-instances=10 \
        --min-instances=0 \
        --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},OUTPUT_BUCKET=${OUTPUT_BUCKET},QUARANTINE_BUCKET=${QUARANTINE_BUCKET},BIGQUERY_DATASET=${BIGQUERY_DATASET},DOCUMENT_AI_PROCESSOR=${DOCUMENT_AI_PROCESSOR},ENVIRONMENT=${ENVIRONMENT}" \
        --set-secrets="GEMINI_API_KEY=gemini-api-key-${ENVIRONMENT}:latest"

    # Deploy health check function
    log_info "Deploying ocr-health-check-${ENVIRONMENT}..."
    gcloud functions deploy "ocr-health-check-${ENVIRONMENT}" \
        --gen2 \
        --runtime=python311 \
        --region="${GCP_REGION}" \
        --source=. \
        --entry-point=health_check \
        --trigger-http \
        --allow-unauthenticated=false \
        --service-account="${SERVICE_ACCOUNT}" \
        --memory=256Mi \
        --timeout=60s \
        --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},ENVIRONMENT=${ENVIRONMENT}" \
        --set-secrets="SLACK_WEBHOOK_URL=slack-webhook-${ENVIRONMENT}:latest" || true

    # Deploy alert handler function
    log_info "Deploying ocr-alert-handler-${ENVIRONMENT}..."
    gcloud functions deploy "ocr-alert-handler-${ENVIRONMENT}" \
        --gen2 \
        --runtime=python311 \
        --region="${GCP_REGION}" \
        --source=. \
        --entry-point=handle_dead_letter \
        --trigger-topic="ocr-dead-letter-${ENVIRONMENT}" \
        --service-account="${SERVICE_ACCOUNT}" \
        --memory=256Mi \
        --timeout=60s \
        --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},ENVIRONMENT=${ENVIRONMENT}" \
        --set-secrets="SLACK_WEBHOOK_URL=slack-webhook-${ENVIRONMENT}:latest" || true

    log_success "Cloud Functions deployed"
else
    log_info "[DRY RUN] Would deploy Cloud Functions"
fi

# =============================================================================
# Step 10: Create Cloud Scheduler Jobs
# =============================================================================
log_info "Creating Cloud Scheduler jobs..."

if [ "$DRY_RUN" = false ]; then
    HEALTH_CHECK_URL=$(gcloud functions describe "ocr-health-check-${ENVIRONMENT}" \
        --region="${GCP_REGION}" \
        --format="value(serviceConfig.uri)" 2>/dev/null || echo "")

    if [ -n "${HEALTH_CHECK_URL}" ]; then
        if ! gcloud scheduler jobs describe "ocr-health-check-${ENVIRONMENT}" --location="${GCP_REGION}" &>/dev/null 2>&1; then
            log_info "Creating health check scheduler job"
            gcloud scheduler jobs create http "ocr-health-check-${ENVIRONMENT}" \
                --location="${GCP_REGION}" \
                --schedule="*/15 * * * *" \
                --time-zone="Asia/Tokyo" \
                --uri="${HEALTH_CHECK_URL}" \
                --http-method=POST \
                --oidc-service-account-email="${SERVICE_ACCOUNT}"
        else
            log_info "Health check scheduler job exists"
        fi
    else
        log_warn "Health check function URL not available, skipping scheduler"
    fi
else
    log_info "[DRY RUN] Would create Cloud Scheduler jobs"
fi
log_success "Scheduler configured"

# =============================================================================
# Step 11: Run Verification
# =============================================================================
log_info "Running deployment verification..."

if [ "$DRY_RUN" = false ]; then
    if [ -f "deploy/verify.sh" ]; then
        bash deploy/verify.sh "${ENVIRONMENT}"
    else
        log_warn "Verification script not found, skipping"
    fi
else
    log_info "[DRY RUN] Would run deployment verification"
fi

# =============================================================================
# Deployment Complete
# =============================================================================
echo ""
echo "=============================================="
echo "  Deployment Complete!"
echo "=============================================="
echo ""
log_success "Deployed to: ${ENVIRONMENT}"
echo ""
echo "Next steps:"
echo "  1. Verify functions: gcloud functions list --region=${GCP_REGION}"
echo "  2. Check logs: gcloud functions logs read ocr-processor-${ENVIRONMENT} --region=${GCP_REGION}"
echo "  3. Upload test doc: gsutil cp test.pdf gs://${INPUT_BUCKET}/test/"
echo "  4. Monitor: https://console.cloud.google.com/monitoring?project=${GCP_PROJECT_ID}"
echo ""

if [ "$ENVIRONMENT" = "production" ]; then
    log_warn "PRODUCTION DEPLOYMENT - Monitor closely for the next 24 hours"
fi
