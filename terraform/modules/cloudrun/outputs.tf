# Cloud Run Module - Outputs

output "api_service_url" {
  description = "URL of the API Cloud Run service"
  value       = length(google_cloud_run_v2_service.api) > 0 ? google_cloud_run_v2_service.api[0].uri : ""
}

output "api_service_name" {
  description = "Name of the API Cloud Run service"
  value       = length(google_cloud_run_v2_service.api) > 0 ? google_cloud_run_v2_service.api[0].name : ""
}

output "ui_service_url" {
  description = "URL of the UI Cloud Run service"
  value       = length(google_cloud_run_v2_service.ui) > 0 ? google_cloud_run_v2_service.ui[0].uri : ""
}

output "ui_service_name" {
  description = "Name of the UI Cloud Run service"
  value       = length(google_cloud_run_v2_service.ui) > 0 ? google_cloud_run_v2_service.ui[0].name : ""
}
