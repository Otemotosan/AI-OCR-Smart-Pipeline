# Storage Module - Outputs

output "input_bucket_name" {
  description = "Name of the input bucket"
  value       = google_storage_bucket.input.name
}

output "input_bucket_url" {
  description = "URL of the input bucket"
  value       = google_storage_bucket.input.url
}

output "output_bucket_name" {
  description = "Name of the output bucket"
  value       = google_storage_bucket.output.name
}

output "output_bucket_url" {
  description = "URL of the output bucket"
  value       = google_storage_bucket.output.url
}

output "quarantine_bucket_name" {
  description = "Name of the quarantine bucket"
  value       = google_storage_bucket.quarantine.name
}

output "quarantine_bucket_url" {
  description = "URL of the quarantine bucket"
  value       = google_storage_bucket.quarantine.url
}

output "document_uploaded_topic" {
  description = "Pub/Sub topic for document upload events"
  value       = google_pubsub_topic.document_uploaded.name
}

output "dead_letter_topic" {
  description = "Pub/Sub topic for dead letter queue"
  value       = google_pubsub_topic.dead_letter.name
}
