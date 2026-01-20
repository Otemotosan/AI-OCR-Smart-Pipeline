# Storage Module - GCS Buckets
# Creates storage buckets for input, output, and quarantine documents.

# ============================================================
# Input Bucket - Incoming documents
# ============================================================

resource "google_storage_bucket" "input" {
  name          = "${var.project_id}-ocr-input-${var.environment}"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = false
  }

  lifecycle_rule {
    condition {
      age = 7  # Delete processed files after 7 days
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
    type        = "input"
  }
}

# ============================================================
# Output Bucket - Processed documents (organized)
# ============================================================

resource "google_storage_bucket" "output" {
  name          = "${var.project_id}-ocr-output-${var.environment}"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = true  # Keep versions for audit trail
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 3  # Keep last 3 versions
    }
    action {
      type = "Delete"
    }
  }

  # Move to Nearline after 90 days
  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  # Move to Coldline after 365 days
  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
    type        = "output"
  }
}

# ============================================================
# Quarantine Bucket - Failed documents
# ============================================================

resource "google_storage_bucket" "quarantine" {
  name          = "${var.project_id}-ocr-quarantine-${var.environment}"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  # Keep quarantined documents for 30 days
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
    type        = "quarantine"
  }
}

# ============================================================
# Bucket IAM - Grant service account access
# ============================================================

resource "google_storage_bucket_iam_member" "input_processor" {
  bucket = google_storage_bucket.input.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.service_account}"
}

resource "google_storage_bucket_iam_member" "output_processor" {
  bucket = google_storage_bucket.output.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.service_account}"
}

resource "google_storage_bucket_iam_member" "quarantine_processor" {
  bucket = google_storage_bucket.quarantine.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.service_account}"
}

# ============================================================
# Pub/Sub Notification for Input Bucket
# ============================================================

resource "google_storage_notification" "input_notification" {
  bucket         = google_storage_bucket.input.name
  payload_format = "JSON_API_V1"
  topic          = google_pubsub_topic.document_uploaded.id
  event_types    = ["OBJECT_FINALIZE"]

  depends_on = [google_pubsub_topic_iam_member.storage_publisher]
}

resource "google_pubsub_topic" "document_uploaded" {
  name    = "ocr-document-uploaded-${var.environment}"
  project = var.project_id

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
  }
}

# Grant GCS permission to publish to topic
data "google_storage_project_service_account" "gcs_account" {
  project = var.project_id
}

resource "google_pubsub_topic_iam_member" "storage_publisher" {
  topic  = google_pubsub_topic.document_uploaded.id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${data.google_storage_project_service_account.gcs_account.email_address}"
}

# ============================================================
# Dead Letter Topic
# ============================================================

resource "google_pubsub_topic" "dead_letter" {
  name    = "ocr-dead-letter-${var.environment}"
  project = var.project_id

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
  }
}
