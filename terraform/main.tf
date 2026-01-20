# AI-OCR Smart Pipeline - Terraform Main Configuration
# This is the root module that orchestrates all infrastructure components.
#
# Usage:
#   cd terraform/environments/staging
#   terraform init
#   terraform plan
#   terraform apply

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }
}

# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "cloudfunctions.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudscheduler.googleapis.com",
    "documentai.googleapis.com",
    "aiplatform.googleapis.com",
    "firestore.googleapis.com",
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "secretmanager.googleapis.com",
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "cloudkms.googleapis.com",
    "iap.googleapis.com",
    "artifactregistry.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# IAM Module - Service accounts and permissions
module "iam" {
  source = "./modules/iam"

  project_id  = var.project_id
  environment = var.environment

  depends_on = [google_project_service.apis]
}

# Storage Module - GCS buckets
module "storage" {
  source = "./modules/storage"

  project_id      = var.project_id
  region          = var.region
  environment     = var.environment
  service_account = module.iam.processor_service_account_email

  depends_on = [google_project_service.apis, module.iam]
}

# Firestore Module - Document database
module "firestore" {
  source = "./modules/firestore"

  project_id  = var.project_id
  region      = var.region
  environment = var.environment

  depends_on = [google_project_service.apis]
}

# BigQuery Module - Analytics warehouse
module "bigquery" {
  source = "./modules/bigquery"

  project_id      = var.project_id
  region          = var.region
  environment     = var.environment
  service_account = module.iam.processor_service_account_email

  depends_on = [google_project_service.apis, module.iam]
}

# Cloud Functions Module - Serverless processing
# Set deploy_functions = true after uploading source code to GCS
module "functions" {
  count  = var.deploy_functions ? 1 : 0
  source = "./modules/functions"

  project_id              = var.project_id
  region                  = var.region
  environment             = var.environment
  service_account         = module.iam.processor_service_account_email
  input_bucket            = module.storage.input_bucket_name
  output_bucket           = module.storage.output_bucket_name
  quarantine_bucket       = module.storage.quarantine_bucket_name
  bigquery_dataset        = module.bigquery.dataset_id
  document_ai_processor   = var.document_ai_processor_id
  gemini_api_key_secret   = module.iam.gemini_api_key_secret_id
  slack_webhook_secret    = module.iam.slack_webhook_secret_id

  depends_on = [
    google_project_service.apis,
    module.iam,
    module.storage,
    module.bigquery,
  ]
}

# Cloud Run Module - API and UI services
# Set deploy_cloudrun = true after building container images
module "cloudrun" {
  count  = var.deploy_cloudrun ? 1 : 0
  source = "./modules/cloudrun"

  project_id              = var.project_id
  region                  = var.region
  environment             = var.environment
  service_account         = module.iam.api_service_account_email
  api_image               = var.api_image
  ui_image                = var.ui_image
  api_domain              = var.api_domain
  ui_domain               = var.ui_domain
  iap_oauth_client_id     = var.iap_oauth_client_id
  iap_oauth_client_secret = var.iap_oauth_client_secret

  depends_on = [google_project_service.apis, module.iam]
}

# Monitoring Module - Dashboards and alerts
module "monitoring" {
  source = "./modules/monitoring"

  project_id           = var.project_id
  environment          = var.environment
  notification_channel = var.slack_notification_channel
  alert_email          = var.alert_email
  api_domain           = var.api_domain

  depends_on = [google_project_service.apis]
}
