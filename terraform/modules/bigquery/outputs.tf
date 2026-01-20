# BigQuery Module - Outputs

output "dataset_id" {
  description = "BigQuery dataset ID"
  value       = google_bigquery_dataset.ocr_pipeline.dataset_id
}

output "dataset_full_id" {
  description = "BigQuery dataset full ID (project:dataset)"
  value       = "${var.project_id}:${google_bigquery_dataset.ocr_pipeline.dataset_id}"
}

output "extractions_table_id" {
  description = "Extraction results table ID"
  value       = google_bigquery_table.extraction_results.table_id
}

output "corrections_table_id" {
  description = "Corrections table ID"
  value       = google_bigquery_table.corrections.table_id
}
