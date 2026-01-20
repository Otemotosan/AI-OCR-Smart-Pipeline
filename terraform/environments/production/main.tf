# Production Environment Configuration
# Usage:
#   cd terraform/environments/production
#   terraform init
#   terraform plan -var-file=terraform.tfvars
#   terraform apply -var-file=terraform.tfvars

terraform {
  required_version = ">= 1.5.0"

  # REQUIRED for production - use remote state
  # backend "gcs" {
  #   bucket = "your-project-terraform-state"
  #   prefix = "production"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

module "ocr_pipeline" {
  source = "../../"

  project_id               = var.project_id
  region                   = var.region
  environment              = "production"
  document_ai_processor_id = var.document_ai_processor_id

  # Container images
  api_image = var.api_image
  ui_image  = var.ui_image

  # Domain configuration
  api_domain = var.api_domain
  ui_domain  = var.ui_domain

  # IAP configuration (required for production)
  iap_oauth_client_id     = var.iap_oauth_client_id
  iap_oauth_client_secret = var.iap_oauth_client_secret
  iap_allowed_members     = var.iap_allowed_members

  # Alerting
  alert_email                = var.alert_email
  slack_notification_channel = var.slack_notification_channel

  # Scaling (higher limits for production)
  function_max_instances = 10
  cloudrun_max_instances = 10
  cloudrun_min_instances = 1  # Always-on for production
}

output "deployment_summary" {
  value = module.ocr_pipeline.deployment_summary
}
