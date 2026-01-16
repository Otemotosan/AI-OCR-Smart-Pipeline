#!/bin/bash
# Deployment script for OCR Pipeline
# Usage: ./deploy.sh [staging|production]

set -euo pipefail

# Default to staging
ENVIRONMENT="${1:-staging}"

# Load environment variables
if [ -f "deploy/.env.${ENVIRONMENT}" ]; then
    source "deploy/.env.${ENVIRONMENT}"
elif [ -f "deploy/.env" ]; then
    source "deploy/.env"
else
    echo "Error: No environment file found. Copy deploy/env.example to deploy/.env"
    exit 1
fi

echo "=== Deploying OCR Pipeline to ${ENVIRONMENT} ==="
echo "Project: ${GCP_PROJECT_ID}"
echo "Region: ${GCP_REGION}"

# Verify gcloud is configured
gcloud config set project "${GCP_PROJECT_ID}"

# Step 1: Create GCS buckets (if not exist)
echo ""
echo "=== Creating GCS Buckets ==="

for BUCKET in "${INPUT_BUCKET}" "${OUTPUT_BUCKET}" "${QUARANTINE_BUCKET}"; do
    if ! gsutil ls "gs://${BUCKET}" &>/dev/null; then
        echo "Creating bucket: ${BUCKET}"
        gsutil mb -l "${GCP_REGION}" "gs://${BUCKET}"
        gsutil uniformbucketlevelaccess set on "gs://${BUCKET}"
    else
        echo "Bucket exists: ${BUCKET}"
    fi
done

# Step 2: Create BigQuery dataset (if not exist)
echo ""
echo "=== Creating BigQuery Dataset ==="

if ! bq show "${GCP_PROJECT_ID}:${BIGQUERY_DATASET}" &>/dev/null; then
    echo "Creating dataset: ${BIGQUERY_DATASET}"
    bq mk --location="${GCP_REGION}" "${GCP_PROJECT_ID}:${BIGQUERY_DATASET}"
else
    echo "Dataset exists: ${BIGQUERY_DATASET}"
fi

# Step 3: Create service account (if not exist)
echo ""
echo "=== Creating Service Account ==="

SERVICE_ACCOUNT="ocr-processor@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "${SERVICE_ACCOUNT}" &>/dev/null; then
    echo "Creating service account: ocr-processor"
    gcloud iam service-accounts create ocr-processor \
        --display-name="OCR Pipeline Processor"
fi

# Grant necessary roles
echo "Granting roles to service account..."
ROLES=(
    "roles/storage.objectAdmin"
    "roles/datastore.user"
    "roles/bigquery.dataEditor"
    "roles/documentai.apiUser"
    "roles/aiplatform.user"
    "roles/logging.logWriter"
    "roles/monitoring.metricWriter"
)

for ROLE in "${ROLES[@]}"; do
    gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="${ROLE}" \
        --condition=None \
        --quiet || true
done

# Step 4: Create/Update secrets in Secret Manager
echo ""
echo "=== Configuring Secrets ==="

# Function to create or update a secret
create_or_update_secret() {
    local SECRET_NAME=$1
    local SECRET_VALUE=$2

    if [ -z "${SECRET_VALUE}" ]; then
        echo "Warning: ${SECRET_NAME} is not set, skipping..."
        return
    fi

    if gcloud secrets describe "${SECRET_NAME}" &>/dev/null; then
        echo "Updating secret: ${SECRET_NAME}"
        echo -n "${SECRET_VALUE}" | gcloud secrets versions add "${SECRET_NAME}" --data-file=-
    else
        echo "Creating secret: ${SECRET_NAME}"
        echo -n "${SECRET_VALUE}" | gcloud secrets create "${SECRET_NAME}" --data-file=-
    fi

    # Grant access to service account
    gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="roles/secretmanager.secretAccessor" \
        --quiet || true
}

# Create secrets (only if environment variables are set)
create_or_update_secret "gemini-api-key" "${GEMINI_API_KEY:-}"
create_or_update_secret "slack-webhook" "${SLACK_WEBHOOK_URL:-}"
create_or_update_secret "sendgrid-key" "${SENDGRID_API_KEY:-}"

# Step 5: Create Pub/Sub topic for dead letter queue
echo ""
echo "=== Creating Pub/Sub Topics ==="

if ! gcloud pubsub topics describe "ocr-dead-letter" &>/dev/null; then
    echo "Creating dead letter topic"
    gcloud pubsub topics create "ocr-dead-letter"
else
    echo "Dead letter topic exists"
fi

# Step 6: Deploy Cloud Functions
echo ""
echo "=== Deploying Cloud Functions ==="

# Deploy main processor function
echo "Deploying ocr-processor..."
gcloud functions deploy ocr-processor \
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
    --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},OUTPUT_BUCKET=${OUTPUT_BUCKET},QUARANTINE_BUCKET=${QUARANTINE_BUCKET},BIGQUERY_DATASET=${BIGQUERY_DATASET},DOCUMENT_AI_PROCESSOR=${DOCUMENT_AI_PROCESSOR}" \
    --set-secrets="GEMINI_API_KEY=gemini-api-key:latest"

# Step 7: Create Cloud Scheduler job for health check
echo ""
echo "=== Creating Cloud Scheduler Jobs ==="

# Get the URL of the health check function
HEALTH_CHECK_URL=$(gcloud functions describe ocr-health-check \
    --region="${GCP_REGION}" \
    --format="value(serviceConfig.uri)" 2>/dev/null || echo "")

if [ -n "${HEALTH_CHECK_URL}" ]; then
    if ! gcloud scheduler jobs describe ocr-health-check --location="${GCP_REGION}" &>/dev/null; then
        echo "Creating health check scheduler job"
        gcloud scheduler jobs create http ocr-health-check \
            --location="${GCP_REGION}" \
            --schedule="*/15 * * * *" \
            --time-zone="Asia/Tokyo" \
            --uri="${HEALTH_CHECK_URL}" \
            --http-method=POST \
            --oidc-service-account-email="${SERVICE_ACCOUNT}"
    else
        echo "Health check scheduler job exists"
    fi
fi

# Step 8: Run smoke test
echo ""
echo "=== Running Smoke Test ==="

# Upload a test file to trigger the pipeline
TEST_FILE="deploy/test-document.pdf"
if [ -f "${TEST_FILE}" ]; then
    echo "Uploading test document..."
    gsutil cp "${TEST_FILE}" "gs://${INPUT_BUCKET}/test/"
    echo "Test document uploaded. Check Cloud Logging for processing status."
else
    echo "No test document found at ${TEST_FILE}"
    echo "Create a test PDF and upload to gs://${INPUT_BUCKET}/test/ to verify deployment"
fi

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Next steps:"
echo "1. Verify functions are running: gcloud functions list --region=${GCP_REGION}"
echo "2. Check logs: gcloud functions logs read ocr-processor --region=${GCP_REGION}"
echo "3. Monitor dashboard: https://console.cloud.google.com/monitoring"
echo ""
