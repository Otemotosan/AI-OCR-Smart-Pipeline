# BigQuery Module - Analytics Data Warehouse
# Creates BigQuery dataset and tables for analytics.

# ============================================================
# Dataset
# ============================================================

resource "google_bigquery_dataset" "ocr_pipeline" {
  dataset_id  = "ocr_pipeline_${var.environment}"
  project     = var.project_id
  location    = var.region
  description = "OCR Pipeline analytics data (${var.environment})"

  default_table_expiration_ms = null  # No expiration

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
  }

  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }

  access {
    role          = "WRITER"
    user_by_email = var.service_account
  }
}

# ============================================================
# Extraction Results Table
# ============================================================

resource "google_bigquery_table" "extraction_results" {
  dataset_id          = google_bigquery_dataset.ocr_pipeline.dataset_id
  table_id            = "extraction_results"
  project             = var.project_id
  deletion_protection = var.environment == "production"

  description = "Extraction results from document processing"

  time_partitioning {
    type  = "DAY"
    field = "document_date"
  }

  clustering = ["document_type"]

  schema = jsonencode([
    { name = "document_id", type = "STRING", mode = "REQUIRED", description = "SHA-256 hash of document" },
    { name = "document_type", type = "STRING", mode = "REQUIRED", description = "Type of document (delivery_note, invoice)" },
    { name = "schema_version", type = "STRING", mode = "REQUIRED", description = "Schema version used" },
    { name = "management_id", type = "STRING", mode = "NULLABLE", description = "Extracted management ID" },
    { name = "company_name", type = "STRING", mode = "NULLABLE", description = "Extracted company name" },
    { name = "document_date", type = "DATE", mode = "NULLABLE", description = "Document date for partitioning" },
    { name = "issue_date", type = "DATE", mode = "NULLABLE", description = "Issue date from document" },
    { name = "extracted_data", type = "JSON", mode = "NULLABLE", description = "Full extracted data as JSON" },
    { name = "confidence_score", type = "FLOAT64", mode = "NULLABLE", description = "Extraction confidence score" },
    { name = "model_used", type = "STRING", mode = "NULLABLE", description = "Model used (flash, pro)" },
    { name = "attempts_count", type = "INT64", mode = "NULLABLE", description = "Number of extraction attempts" },
    { name = "processing_duration_ms", type = "INT64", mode = "NULLABLE", description = "Processing time in milliseconds" },
    { name = "source_uri", type = "STRING", mode = "NULLABLE", description = "Original document URI" },
    { name = "destination_uri", type = "STRING", mode = "NULLABLE", description = "Organized document URI" },
    { name = "quality_warnings", type = "STRING", mode = "REPEATED", description = "Quality linter warnings" },
    { name = "processed_at", type = "TIMESTAMP", mode = "NULLABLE", description = "Processing timestamp" },
    { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED", description = "Record creation timestamp" },
  ])

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
  }
}

# ============================================================
# Corrections Table
# ============================================================

resource "google_bigquery_table" "corrections" {
  dataset_id          = google_bigquery_dataset.ocr_pipeline.dataset_id
  table_id            = "corrections"
  project             = var.project_id
  deletion_protection = var.environment == "production"

  description = "Human corrections and audit trail"

  time_partitioning {
    type  = "DAY"
    field = "corrected_at"
  }

  schema = jsonencode([
    { name = "correction_id", type = "STRING", mode = "REQUIRED", description = "Unique correction ID" },
    { name = "document_id", type = "STRING", mode = "REQUIRED", description = "Document being corrected" },
    { name = "user_id", type = "STRING", mode = "REQUIRED", description = "User who made correction" },
    { name = "field_name", type = "STRING", mode = "NULLABLE", description = "Field that was corrected" },
    { name = "before_value", type = "STRING", mode = "NULLABLE", description = "Value before correction" },
    { name = "after_value", type = "STRING", mode = "NULLABLE", description = "Value after correction" },
    { name = "before_data", type = "JSON", mode = "NULLABLE", description = "Full data before correction" },
    { name = "after_data", type = "JSON", mode = "NULLABLE", description = "Full data after correction" },
    { name = "correction_type", type = "STRING", mode = "NULLABLE", description = "Type of correction" },
    { name = "corrected_at", type = "TIMESTAMP", mode = "REQUIRED", description = "Correction timestamp" },
  ])

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
  }
}

# ============================================================
# Views for Analytics
# ============================================================

resource "google_bigquery_table" "daily_stats_view" {
  dataset_id          = google_bigquery_dataset.ocr_pipeline.dataset_id
  table_id            = "daily_processing_stats"
  project             = var.project_id
  deletion_protection = false

  view {
    query = <<-SQL
      SELECT
        DATE(processed_at) as processing_date,
        document_type,
        COUNT(*) as total_documents,
        AVG(confidence_score) as avg_confidence,
        AVG(processing_duration_ms) as avg_duration_ms,
        COUNTIF(model_used = 'flash') as flash_count,
        COUNTIF(model_used = 'pro') as pro_count,
        AVG(attempts_count) as avg_attempts
      FROM `${var.project_id}.${google_bigquery_dataset.ocr_pipeline.dataset_id}.extraction_results`
      WHERE processed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
      GROUP BY processing_date, document_type
      ORDER BY processing_date DESC
    SQL
    use_legacy_sql = false
  }
}

resource "google_bigquery_table" "correction_rate_view" {
  dataset_id          = google_bigquery_dataset.ocr_pipeline.dataset_id
  table_id            = "correction_rate"
  project             = var.project_id
  deletion_protection = false

  view {
    query = <<-SQL
      SELECT
        DATE(c.corrected_at) as correction_date,
        COUNT(DISTINCT c.document_id) as documents_corrected,
        COUNT(*) as total_corrections,
        COUNT(*) / COUNT(DISTINCT c.document_id) as corrections_per_document
      FROM `${var.project_id}.${google_bigquery_dataset.ocr_pipeline.dataset_id}.corrections` c
      WHERE c.corrected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
      GROUP BY correction_date
      ORDER BY correction_date DESC
    SQL
    use_legacy_sql = false
  }
}
