#!/bin/bash
# =============================================================================
# Cloud Functions Deployment Script
# AI-OCR Smart Pipeline
#
# Usage:
#   ./scripts/deploy-functions.sh [environment]
#
# Prerequisites:
#   - gcloud CLI authenticated
#   - Terraform infrastructure deployed (storage bucket exists)
# =============================================================================

set -e

# Configuration
ENVIRONMENT="${1:-staging}"
PROJECT_ID="${PROJECT_ID:-ai-ocr-smart-pipeline}"
REGION="${REGION:-asia-northeast1}"

# Derived names
SOURCE_BUCKET="${PROJECT_ID}-function-source-${ENVIRONMENT}"
SOURCE_OBJECT="processor-source.zip"
TEMP_DIR=$(mktemp -d)
ZIP_FILE="${TEMP_DIR}/${SOURCE_OBJECT}"

echo "=============================================="
echo "Cloud Functions Deployment"
echo "=============================================="
echo "Environment: ${ENVIRONMENT}"
echo "Project ID:  ${PROJECT_ID}"
echo "Region:      ${REGION}"
echo "Source Bucket: ${SOURCE_BUCKET}"
echo ""

# Step 1: Check if source bucket exists
echo "Checking source bucket..."
if ! gsutil ls "gs://${SOURCE_BUCKET}" > /dev/null 2>&1; then
    echo "ERROR: Source bucket ${SOURCE_BUCKET} does not exist."
    echo "Please run 'terraform apply' with deploy_functions=true first."
    echo "This will create the bucket."
    echo ""
    echo "Or create it manually:"
    echo "  gsutil mb -l ${REGION} gs://${SOURCE_BUCKET}"
    exit 1
fi
echo "Source bucket exists."

# Step 2: Package source code
echo ""
echo "Packaging source code..."

# Create a clean directory for packaging
PACKAGE_DIR="${TEMP_DIR}/package"
mkdir -p "${PACKAGE_DIR}"

# Copy source files
echo "  Copying src/core/..."
cp -r src/core "${PACKAGE_DIR}/"

echo "  Copying src/functions/processor/..."
mkdir -p "${PACKAGE_DIR}/src/functions/processor"
cp src/functions/__init__.py "${PACKAGE_DIR}/src/functions/" 2>/dev/null || echo "" > "${PACKAGE_DIR}/src/functions/__init__.py"
cp src/functions/processor/*.py "${PACKAGE_DIR}/src/functions/processor/"

# Copy main.py to root (Cloud Functions entry point)
cp src/functions/processor/main.py "${PACKAGE_DIR}/main.py"

# Copy requirements.txt
cp src/functions/processor/requirements.txt "${PACKAGE_DIR}/requirements.txt"

# Create __init__.py files for proper imports
echo "" > "${PACKAGE_DIR}/src/__init__.py"
echo "" > "${PACKAGE_DIR}/src/core/__init__.py"

# Create the ZIP file
echo "  Creating ZIP archive..."
cd "${PACKAGE_DIR}"
zip -r "${ZIP_FILE}" . -x "*.pyc" -x "__pycache__/*" -x "*.pytest_cache/*" > /dev/null
cd - > /dev/null

echo "  Package size: $(du -h ${ZIP_FILE} | cut -f1)"

# Step 3: Upload to GCS
echo ""
echo "Uploading to GCS..."
gsutil cp "${ZIP_FILE}" "gs://${SOURCE_BUCKET}/${SOURCE_OBJECT}"
echo "Uploaded: gs://${SOURCE_BUCKET}/${SOURCE_OBJECT}"

# Step 4: Cleanup
echo ""
echo "Cleaning up..."
rm -rf "${TEMP_DIR}"

# Step 5: Instructions for next steps
echo ""
echo "=============================================="
echo "Source code uploaded successfully!"
echo "=============================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Set up Secret Manager secrets (if not already done):"
echo ""
echo "   # Gemini API Key"
echo "   echo -n 'YOUR_GEMINI_API_KEY' | gcloud secrets versions add \\"
echo "     gemini-api-key-${ENVIRONMENT} --data-file=-"
echo ""
echo "   # Slack Webhook URL (optional)"
echo "   echo -n 'YOUR_SLACK_WEBHOOK_URL' | gcloud secrets versions add \\"
echo "     slack-webhook-${ENVIRONMENT} --data-file=-"
echo ""
echo "2. Deploy Cloud Functions with Terraform:"
echo ""
echo "   cd terraform/environments/${ENVIRONMENT}"
echo "   # Edit terraform.tfvars to set: deploy_functions = true"
echo "   terraform apply"
echo ""
echo "=============================================="
