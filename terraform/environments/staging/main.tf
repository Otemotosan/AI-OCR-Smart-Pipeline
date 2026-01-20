# Staging Environment Configuration
# Usage:
#   cd terraform/environments/staging
#   terraform init
#   terraform plan -var-file=terraform.tfvars
#   terraform apply -var-file=terraform.tfvars

terraform {
  required_version = ">= 1.5.0"

  # Uncomment to use remote state
  # backend "gcs" {
  #   bucket = "your-project-terraform-state"
  #   prefix = "staging"
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
  environment              = "staging"
  document_ai_processor_id = var.document_ai_processor_id

  # Container images (optional - leave empty if not deploying API/UI)
  api_image = var.api_image
  ui_image  = var.ui_image

  # Domain configuration (optional - leave empty if using Cloud Run URLs)
  api_domain = var.api_domain
  ui_domain  = var.ui_domain

  # IAP configuration (optional - leave empty if not using custom domains)
  iap_oauth_client_id     = var.iap_oauth_client_id
  iap_oauth_client_secret = var.iap_oauth_client_secret

  # Alerting
  alert_email = var.alert_email

  # Scaling (lower limits for staging)
  function_max_instances = 5
  cloudrun_max_instances = 3
}

output "deployment_summary" {
  value = module.ocr_pipeline.deployment_summary
}
