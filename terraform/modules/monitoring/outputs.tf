# Monitoring Module - Outputs

output "dashboard_url" {
  description = "URL of the Cloud Monitoring dashboard"
  value       = "https://console.cloud.google.com/monitoring/dashboards?project=${var.project_id}"
}

output "alert_policies" {
  description = "List of created alert policy names"
  value = [
    google_monitoring_alert_policy.high_failure_rate.display_name,
    google_monitoring_alert_policy.queue_backlog.display_name,
    google_monitoring_alert_policy.pro_budget.display_name,
    google_monitoring_alert_policy.low_confidence.display_name,
  ]
}

output "log_based_metrics" {
  description = "List of created log-based metrics"
  value = [
    google_logging_metric.pro_usage.name,
    google_logging_metric.confidence_score.name,
    google_logging_metric.processing_duration.name,
  ]
}
