# Functions Module - Outputs

output "processor_function_name" {
  description = "Name of the processor function"
  value       = google_cloudfunctions2_function.processor.name
}

output "processor_function_url" {
  description = "URL of the processor function"
  value       = google_cloudfunctions2_function.processor.service_config[0].uri
}

output "health_check_function_name" {
  description = "Name of the health check function"
  value       = google_cloudfunctions2_function.health_check.name
}

output "health_check_function_url" {
  description = "URL of the health check function"
  value       = google_cloudfunctions2_function.health_check.service_config[0].uri
}

output "alert_handler_function_name" {
  description = "Name of the alert handler function"
  value       = google_cloudfunctions2_function.alert_handler.name
}

output "source_bucket" {
  description = "Bucket for function source code"
  value       = var.function_source_bucket
}
