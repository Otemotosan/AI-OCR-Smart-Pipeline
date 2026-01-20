# AI-OCR Smart Pipeline - Terraform Outputs
# Useful outputs for deployment verification and integration.

# ============================================================
# Storage Outputs
# ============================================================

output "input_bucket" {
  description = "GCS bucket for incoming documents"
  value       = module.storage.input_bucket_name
}

output "output_bucket" {
  description = "GCS bucket for processed documents"
  value       = module.storage.output_bucket_name
}

output "quarantine_bucket" {
  description = "GCS bucket for failed documents"
  value       = module.storage.quarantine_bucket_name
}

# ============================================================
# Database Outputs
# ============================================================

output "firestore_database" {
  description = "Firestore database name"
  value       = module.firestore.database_name
}

output "bigquery_dataset" {
  description = "BigQuery dataset ID"
  value       = module.bigquery.dataset_id
}

output "bigquery_extractions_table" {
  description = "BigQuery extractions table ID"
  value       = module.bigquery.extractions_table_id
}

output "bigquery_corrections_table" {
  description = "BigQuery corrections table ID"
  value       = module.bigquery.corrections_table_id
}

# ============================================================
# Service Outputs
# ============================================================

output "processor_function_url" {
  description = "URL of the document processor Cloud Function"
  value       = module.functions.processor_function_url
}

output "health_check_function_url" {
  description = "URL of the health check Cloud Function"
  value       = module.functions.health_check_function_url
}

output "api_service_url" {
  description = "URL of the API Cloud Run service"
  value       = module.cloudrun.api_service_url
}

output "ui_service_url" {
  description = "URL of the UI Cloud Run service"
  value       = module.cloudrun.ui_service_url
}

# ============================================================
# IAM Outputs
# ============================================================

output "processor_service_account" {
  description = "Service account for document processing"
  value       = module.iam.processor_service_account_email
}

output "api_service_account" {
  description = "Service account for API service"
  value       = module.iam.api_service_account_email
}

# ============================================================
# Monitoring Outputs
# ============================================================

output "monitoring_dashboard_url" {
  description = "URL of the Cloud Monitoring dashboard"
  value       = module.monitoring.dashboard_url
}

# ============================================================
# Summary
# ============================================================

output "deployment_summary" {
  description = "Summary of deployed resources"
  value = {
    project_id       = var.project_id
    region           = var.region
    environment      = var.environment
    input_bucket     = module.storage.input_bucket_name
    api_url          = module.cloudrun.api_service_url
    ui_url           = module.cloudrun.ui_service_url
    bigquery_dataset = module.bigquery.dataset_id
  }
}
