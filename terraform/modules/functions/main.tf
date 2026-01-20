# Functions Module - Cloud Functions (2nd Gen)
# Creates Cloud Functions for document processing.
#
# Note: The source bucket is created in main.tf and passed as a variable.
# This allows the bucket to be created before the source code is uploaded.

# ============================================================
# Document Processor Function
# ============================================================

resource "google_cloudfunctions2_function" "processor" {
  name        = "ocr-processor-${var.environment}"
  project     = var.project_id
  location    = var.region
  description = "Processes documents uploaded to input bucket"

  build_config {
    runtime     = "python311"
    entry_point = "process_document"

    source {
      storage_source {
        bucket = var.function_source_bucket
        object = "processor-source.zip"
      }
    }
  }

  service_config {
    max_instance_count    = 10
    min_instance_count    = 0
    available_memory      = "1Gi"
    timeout_seconds       = 540
    service_account_email = var.service_account

    environment_variables = {
      GCP_PROJECT_ID        = var.project_id
      OUTPUT_BUCKET         = var.output_bucket
      QUARANTINE_BUCKET     = var.quarantine_bucket
      BIGQUERY_DATASET      = var.bigquery_dataset
      DOCUMENT_AI_PROCESSOR = var.document_ai_processor
      ENVIRONMENT           = var.environment
      LOG_LEVEL             = "INFO"
    }

    secret_environment_variables {
      key        = "GEMINI_API_KEY"
      project_id = var.project_id
      secret     = var.gemini_api_key_secret
      version    = "latest"
    }
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.storage.object.v1.finalized"
    retry_policy   = "RETRY_POLICY_RETRY"

    event_filters {
      attribute = "bucket"
      value     = var.input_bucket
    }
  }

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
    function    = "processor"
  }
}

# ============================================================
# Health Check Function
# ============================================================

resource "google_cloudfunctions2_function" "health_check" {
  name        = "ocr-health-check-${var.environment}"
  project     = var.project_id
  location    = var.region
  description = "Health check endpoint for monitoring"

  build_config {
    runtime     = "python311"
    entry_point = "health_check"

    source {
      storage_source {
        bucket = var.function_source_bucket
        object = "processor-source.zip"
      }
    }
  }

  service_config {
    max_instance_count    = 2
    min_instance_count    = 0
    available_memory      = "256Mi"
    timeout_seconds       = 60
    service_account_email = var.service_account

    environment_variables = {
      GCP_PROJECT_ID = var.project_id
      ENVIRONMENT    = var.environment
    }

    secret_environment_variables {
      key        = "SLACK_WEBHOOK_URL"
      project_id = var.project_id
      secret     = var.slack_webhook_secret
      version    = "latest"
    }
  }

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
    function    = "health-check"
  }
}

# ============================================================
# Alert Handler Function (Dead Letter)
# ============================================================

resource "google_cloudfunctions2_function" "alert_handler" {
  name        = "ocr-alert-handler-${var.environment}"
  project     = var.project_id
  location    = var.region
  description = "Handles dead letter queue and sends alerts"

  build_config {
    runtime     = "python311"
    entry_point = "handle_dead_letter"

    source {
      storage_source {
        bucket = var.function_source_bucket
        object = "processor-source.zip"
      }
    }
  }

  service_config {
    max_instance_count    = 2
    min_instance_count    = 0
    available_memory      = "256Mi"
    timeout_seconds       = 60
    service_account_email = var.service_account

    environment_variables = {
      GCP_PROJECT_ID = var.project_id
      ENVIRONMENT    = var.environment
    }

    secret_environment_variables {
      key        = "SLACK_WEBHOOK_URL"
      project_id = var.project_id
      secret     = var.slack_webhook_secret
      version    = "latest"
    }
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = "projects/${var.project_id}/topics/ocr-dead-letter-${var.environment}"
    retry_policy   = "RETRY_POLICY_DO_NOT_RETRY"
  }

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
    function    = "alert-handler"
  }
}

# ============================================================
# Cloud Scheduler - Health Check Job
# ============================================================

resource "google_cloud_scheduler_job" "health_check" {
  name        = "ocr-health-check-${var.environment}"
  project     = var.project_id
  region      = var.region
  description = "Periodic health check"
  schedule    = "*/15 * * * *"  # Every 15 minutes
  time_zone   = "Asia/Tokyo"

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.health_check.service_config[0].uri

    oidc_token {
      service_account_email = var.service_account
    }
  }

  retry_config {
    retry_count = 3
  }
}
