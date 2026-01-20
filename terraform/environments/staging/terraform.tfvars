# Staging Environment Configuration
# AI-OCR Smart Pipeline

# =============================================================================
# Required Configuration
# =============================================================================

project_id = "ai-ocr-smart-pipeline"

# Document AI Processor - UPDATE THIS after creating your processor
# To find your processor path, run:
#   gcloud ai document-processors list --project=ai-ocr-smart-pipeline --location=asia-northeast1
#
# To create a new processor:
#   gcloud ai document-processors create \
#     --project=ai-ocr-smart-pipeline \
#     --location=asia-northeast1 \
#     --display-name="OCR Pipeline Processor" \
#     --type=FORM_PARSER_PROCESSOR
#
document_ai_processor_id = "projects/ai-ocr-smart-pipeline/locations/us/processors/d7296be3cc8d37c4"

# =============================================================================
# Optional Configuration
# =============================================================================

# Container images (uncomment after building images)
# api_image = "gcr.io/ai-ocr-smart-pipeline/ocr-api:latest"
# ui_image  = "gcr.io/ai-ocr-smart-pipeline/ocr-ui:latest"

# Custom domains (requires DNS setup)
# api_domain = "api-staging.yourdomain.com"
# ui_domain  = "ocr-staging.yourdomain.com"

# IAP OAuth (required if using custom domains)
# iap_oauth_client_id     = ""
# iap_oauth_client_secret = ""

# Alerting (uncomment to enable)
# alert_email = "your-email@example.com"
