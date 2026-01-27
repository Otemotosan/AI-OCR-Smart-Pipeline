#!/bin/bash
# =============================================================================
# AI-OCR Smart Pipeline - Deployment Verification Script
# =============================================================================
# Usage:
#   ./verify.sh [staging|production]
#
# Verifies that all components are deployed and working correctly.
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[FAIL]${NC} $1"; }

ENVIRONMENT="${1:-staging}"
PASSED=0
FAILED=0
WARNINGS=0

# Load environment
ENV_FILE="deploy/.env.${ENVIRONMENT}"
if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
elif [ -f "deploy/.env" ]; then
    source "deploy/.env"
else
    log_error "No environment file found"
    exit 1
fi

echo ""
echo "=============================================="
echo "  Deployment Verification: ${ENVIRONMENT}"
echo "=============================================="
echo ""

# =============================================================================
# Check Functions
# =============================================================================

check_function() {
    local FUNC_NAME=$1
    local EXPECTED_STATE=${2:-ACTIVE}

    log_info "Checking function: ${FUNC_NAME}"

    STATE=$(gcloud functions describe "${FUNC_NAME}" \
        --region="${GCP_REGION}" \
        --format="value(state)" 2>/dev/null || echo "NOT_FOUND")

    if [ "$STATE" = "$EXPECTED_STATE" ]; then
        log_success "Function ${FUNC_NAME}: ${STATE}"
        ((PASSED++))
    else
        log_error "Function ${FUNC_NAME}: ${STATE} (expected ${EXPECTED_STATE})"
        ((FAILED++))
    fi
}

log_info "Verifying Cloud Functions..."
check_function "ocr-processor-${ENVIRONMENT}"
check_function "ocr-health-check-${ENVIRONMENT}"
check_function "ocr-alert-handler-${ENVIRONMENT}"

# =============================================================================
# Check Buckets
# =============================================================================

check_bucket() {
    local BUCKET=$1

    log_info "Checking bucket: ${BUCKET}"

    if gsutil ls "gs://${BUCKET}" &>/dev/null; then
        log_success "Bucket ${BUCKET}: EXISTS"
        ((PASSED++))
    else
        log_error "Bucket ${BUCKET}: NOT FOUND"
        ((FAILED++))
    fi
}

log_info "Verifying GCS Buckets..."
check_bucket "${INPUT_BUCKET}"
check_bucket "${OUTPUT_BUCKET}"
check_bucket "${QUARANTINE_BUCKET}"

# =============================================================================
# Check BigQuery
# =============================================================================

log_info "Verifying BigQuery..."

if bq show "${GCP_PROJECT_ID}:${BIGQUERY_DATASET}" &>/dev/null 2>&1; then
    log_success "BigQuery dataset ${BIGQUERY_DATASET}: EXISTS"
    ((PASSED++))
else
    log_error "BigQuery dataset ${BIGQUERY_DATASET}: NOT FOUND"
    ((FAILED++))
fi

# Check tables
for TABLE in "extraction_results" "corrections"; do
    if bq show "${GCP_PROJECT_ID}:${BIGQUERY_DATASET}.${TABLE}" &>/dev/null 2>&1; then
        log_success "BigQuery table ${TABLE}: EXISTS"
        ((PASSED++))
    else
        log_warn "BigQuery table ${TABLE}: NOT FOUND (will be created on first use)"
        ((WARNINGS++))
    fi
done

# =============================================================================
# Check Service Account
# =============================================================================

log_info "Verifying Service Account..."

SERVICE_ACCOUNT="ocr-processor@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

if gcloud iam service-accounts describe "${SERVICE_ACCOUNT}" &>/dev/null 2>&1; then
    log_success "Service account ${SERVICE_ACCOUNT}: EXISTS"
    ((PASSED++))
else
    log_error "Service account ${SERVICE_ACCOUNT}: NOT FOUND"
    ((FAILED++))
fi

# =============================================================================
# Check Secrets
# =============================================================================

log_info "Verifying Secrets..."

check_secret() {
    local SECRET_NAME=$1
    local REQUIRED=${2:-true}

    if gcloud secrets describe "${SECRET_NAME}" &>/dev/null 2>&1; then
        log_success "Secret ${SECRET_NAME}: EXISTS"
        ((PASSED++))
    else
        if [ "$REQUIRED" = true ]; then
            log_error "Secret ${SECRET_NAME}: NOT FOUND"
            ((FAILED++))
        else
            log_warn "Secret ${SECRET_NAME}: NOT FOUND (optional)"
            ((WARNINGS++))
        fi
    fi
}

check_secret "gemini-api-key-${ENVIRONMENT}" true
check_secret "slack-webhook-${ENVIRONMENT}" false

# =============================================================================
# Check Pub/Sub
# =============================================================================

log_info "Verifying Pub/Sub Topics..."

if gcloud pubsub topics describe "ocr-dead-letter-${ENVIRONMENT}" &>/dev/null 2>&1; then
    log_success "Pub/Sub topic ocr-dead-letter-${ENVIRONMENT}: EXISTS"
    ((PASSED++))
else
    log_error "Pub/Sub topic ocr-dead-letter-${ENVIRONMENT}: NOT FOUND"
    ((FAILED++))
fi

# =============================================================================
# Check Cloud Scheduler
# =============================================================================

log_info "Verifying Cloud Scheduler..."

if gcloud scheduler jobs describe "ocr-health-check-${ENVIRONMENT}" --location="${GCP_REGION}" &>/dev/null 2>&1; then
    log_success "Scheduler job ocr-health-check-${ENVIRONMENT}: EXISTS"
    ((PASSED++))
else
    log_warn "Scheduler job ocr-health-check-${ENVIRONMENT}: NOT FOUND (optional)"
    ((WARNINGS++))
fi

# =============================================================================
# Check IAM Roles
# =============================================================================

log_info "Verifying IAM Roles..."

REQUIRED_ROLES=(
    "roles/storage.objectAdmin"
    "roles/datastore.user"
    "roles/bigquery.dataEditor"
    "roles/documentai.apiUser"
    "roles/aiplatform.user"
)

IAM_POLICY=$(gcloud projects get-iam-policy "${GCP_PROJECT_ID}" --format=json 2>/dev/null)

for ROLE in "${REQUIRED_ROLES[@]}"; do
    if echo "$IAM_POLICY" | grep -q "serviceAccount:${SERVICE_ACCOUNT}" && \
       echo "$IAM_POLICY" | grep -q "${ROLE}"; then
        log_success "IAM role ${ROLE}: GRANTED"
        ((PASSED++))
    else
        log_error "IAM role ${ROLE}: NOT GRANTED"
        ((FAILED++))
    fi
done

# =============================================================================
# Health Check (if function is deployed)
# =============================================================================

log_info "Running health check..."

HEALTH_URL=$(gcloud functions describe "ocr-health-check-${ENVIRONMENT}" \
    --region="${GCP_REGION}" \
    --format="value(serviceConfig.uri)" 2>/dev/null || echo "")

if [ -n "$HEALTH_URL" ]; then
    # Get identity token for authenticated request
    TOKEN=$(gcloud auth print-identity-token 2>/dev/null || echo "")

    if [ -n "$TOKEN" ]; then
        RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "Authorization: Bearer ${TOKEN}" \
            "${HEALTH_URL}" 2>/dev/null || echo "000")

        if [ "$RESPONSE" = "200" ]; then
            log_success "Health check endpoint: HEALTHY"
            ((PASSED++))
        else
            log_warn "Health check endpoint: HTTP ${RESPONSE}"
            ((WARNINGS++))
        fi
    else
        log_warn "Could not get identity token for health check"
        ((WARNINGS++))
    fi
else
    log_warn "Health check URL not available"
    ((WARNINGS++))
fi

# =============================================================================
# Summary
# =============================================================================

TOTAL=$((PASSED + FAILED))

echo ""
echo "=============================================="
echo "  Verification Summary"
echo "=============================================="
echo ""
echo -e "  ${GREEN}Passed:${NC}   ${PASSED}"
echo -e "  ${RED}Failed:${NC}   ${FAILED}"
echo -e "  ${YELLOW}Warnings:${NC} ${WARNINGS}"
echo ""
echo "=============================================="
echo ""

if [ "$FAILED" -gt 0 ]; then
    log_error "Verification FAILED - ${FAILED} checks failed"
    exit 1
elif [ "$WARNINGS" -gt 0 ]; then
    log_warn "Verification PASSED with warnings"
    exit 0
else
    log_success "Verification PASSED - All checks successful"
    exit 0
fi
