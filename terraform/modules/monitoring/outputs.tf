# Monitoring Module - Outputs

output "dashboard_url" {
  description = "URL of the Cloud Monitoring dashboard"
  value       = "https://console.cloud.google.com/monitoring/dashboards?project=${var.project_id}"
}

output "alert_policies" {
  description = "List of created alert policy names"
  value = var.alert_email != "" ? [
    google_monitoring_alert_policy.function_errors[0].display_name,
    google_monitoring_alert_policy.high_latency[0].display_name,
  ] : []
}

output "log_based_metrics" {
  description = "List of created log-based metrics"
  value = [
    google_logging_metric.pro_usage.name,
    google_logging_metric.processing_errors.name,
  ]
}
