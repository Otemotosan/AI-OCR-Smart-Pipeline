# Firestore Module - Document Database
# Creates Firestore database with indexes.

# ============================================================
# Firestore Database
# ============================================================

resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  # Enable point-in-time recovery for production
  point_in_time_recovery_enablement = var.environment == "production" ? "POINT_IN_TIME_RECOVERY_ENABLED" : "POINT_IN_TIME_RECOVERY_DISABLED"
}

# ============================================================
# Composite Indexes
# ============================================================

# Index for listing documents by status and date
resource "google_firestore_index" "documents_status_created" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "processed_documents"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }

  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }
}

# Index for audit log queries
resource "google_firestore_index" "audit_log_document_timestamp" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "audit_log"

  fields {
    field_path = "document_id"
    order      = "ASCENDING"
  }

  fields {
    field_path = "timestamp"
    order      = "DESCENDING"
  }
}

# Index for drafts by user
resource "google_firestore_index" "drafts_user_updated" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "drafts"

  fields {
    field_path = "user_id"
    order      = "ASCENDING"
  }

  fields {
    field_path = "updated_at"
    order      = "DESCENDING"
  }
}

# Index for lock management
resource "google_firestore_index" "locks_status_expires" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "processed_documents"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }

  fields {
    field_path = "lock_expires_at"
    order      = "ASCENDING"
  }
}
