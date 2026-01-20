# IAM Module - Service accounts and permissions
# Creates service accounts with least privilege access.

# ============================================================
# Service Accounts
# ============================================================

# Processor Service Account - For Cloud Functions
resource "google_service_account" "processor" {
  account_id   = "ocr-processor-${var.environment}"
  display_name = "OCR Pipeline Processor (${var.environment})"
  description  = "Service account for document processing Cloud Functions"
  project      = var.project_id
}

# API Service Account - For Cloud Run API
resource "google_service_account" "api" {
  account_id   = "ocr-api-${var.environment}"
  display_name = "OCR Pipeline API (${var.environment})"
  description  = "Service account for Review UI API service"
  project      = var.project_id
}

# ============================================================
# Processor Service Account Roles
# ============================================================

# Storage access for input/output/quarantine buckets
resource "google_project_iam_member" "processor_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.processor.email}"
}

# Firestore access for document records
resource "google_project_iam_member" "processor_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.processor.email}"
}

# BigQuery access for analytics
resource "google_project_iam_member" "processor_bigquery" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.processor.email}"
}

# Document AI access
resource "google_project_iam_member" "processor_documentai" {
  project = var.project_id
  role    = "roles/documentai.apiUser"
  member  = "serviceAccount:${google_service_account.processor.email}"
}

# Vertex AI access for Gemini
resource "google_project_iam_member" "processor_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.processor.email}"
}

# Logging access
resource "google_project_iam_member" "processor_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.processor.email}"
}

# Monitoring access
resource "google_project_iam_member" "processor_monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.processor.email}"
}

# Pub/Sub access for dead letter queue
resource "google_project_iam_member" "processor_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.processor.email}"
}

# ============================================================
# API Service Account Roles
# ============================================================

# Storage read access for signed URLs
resource "google_project_iam_member" "api_storage" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Storage signing access for signed URLs
resource "google_service_account_iam_member" "api_storage_signing" {
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.api.email}"
}

# Firestore access for document records
resource "google_project_iam_member" "api_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# BigQuery access for analytics queries
resource "google_project_iam_member" "api_bigquery" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# BigQuery job access for running queries
resource "google_project_iam_member" "api_bigquery_job" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Logging access
resource "google_project_iam_member" "api_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# ============================================================
# Secret Manager - API Keys
# ============================================================

# Gemini API Key Secret
resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "gemini-api-key-${var.environment}"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
  }
}

# Grant processor access to Gemini API key
resource "google_secret_manager_secret_iam_member" "processor_gemini_access" {
  secret_id = google_secret_manager_secret.gemini_api_key.secret_id
  project   = var.project_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.processor.email}"
}

# Slack Webhook Secret
resource "google_secret_manager_secret" "slack_webhook" {
  secret_id = "slack-webhook-${var.environment}"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
  }
}

# Grant processor access to Slack webhook
resource "google_secret_manager_secret_iam_member" "processor_slack_access" {
  secret_id = google_secret_manager_secret.slack_webhook.secret_id
  project   = var.project_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.processor.email}"
}
