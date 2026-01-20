# Monitoring Module - Dashboards and Alerts
# Creates Cloud Monitoring alerts and dashboards.

# ============================================================
# Notification Channels
# ============================================================

resource "google_monitoring_notification_channel" "email" {
  count        = var.alert_email != "" ? 1 : 0
  display_name = "OCR Pipeline Email (${var.environment})"
  type         = "email"
  project      = var.project_id

  labels = {
    email_address = var.alert_email
  }
}

# ============================================================
# Log-Based Metrics (Simple counters - no value extractor)
# ============================================================

resource "google_logging_metric" "pro_usage" {
  name        = "ocr_pro_usage_${var.environment}"
  project     = var.project_id
  description = "Count of Gemini Pro API calls"
  filter      = "resource.type=\"cloud_function\" AND jsonPayload.model=\"pro\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_logging_metric" "processing_errors" {
  name        = "ocr_processing_errors_${var.environment}"
  project     = var.project_id
  description = "Count of processing errors"
  filter      = "resource.type=\"cloud_function\" AND severity>=ERROR"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

# ============================================================
# Uptime Checks (Only if API domain is provided)
# ============================================================

resource "google_monitoring_uptime_check_config" "api_health" {
  count        = var.api_domain != "" ? 1 : 0
  display_name = "OCR API Health Check (${var.environment})"
  project      = var.project_id
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.api_domain
    }
  }

  content_matchers {
    content = "healthy"
    matcher = "CONTAINS_STRING"
  }
}

# ============================================================
# Alert Policies (Basic - using built-in metrics only)
# ============================================================

# Alert on Cloud Function errors
resource "google_monitoring_alert_policy" "function_errors" {
  count        = var.alert_email != "" ? 1 : 0
  display_name = "OCR Pipeline - Function Errors (${var.environment})"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Cloud Function Errors"

    condition_threshold {
      filter          = "resource.type=\"cloud_function\" AND metric.type=\"cloudfunctions.googleapis.com/function/execution_count\" AND metric.labels.status!=\"ok\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = <<-EOT
      ## Cloud Function Errors Alert

      The OCR pipeline Cloud Functions are experiencing errors.

      ### Investigation Steps
      1. Check Cloud Logging for error messages
      2. Review recent deployments
      3. Check Gemini API status
      4. Verify Document AI processor status
    EOT
    mime_type = "text/markdown"
  }

  user_labels = {
    environment = var.environment
    severity    = "p1"
  }
}

# Alert on high latency
resource "google_monitoring_alert_policy" "high_latency" {
  count        = var.alert_email != "" ? 1 : 0
  display_name = "OCR Pipeline - High Latency (${var.environment})"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Function execution time > 5 minutes"

    condition_threshold {
      filter          = "resource.type=\"cloud_function\" AND metric.type=\"cloudfunctions.googleapis.com/function/execution_times\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 300000000000  # 5 minutes in nanoseconds

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_PERCENTILE_99"
        cross_series_reducer = "REDUCE_MAX"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = <<-EOT
      ## High Latency Alert

      Cloud Function execution time is exceeding 5 minutes.

      ### Investigation Steps
      1. Check for large documents
      2. Review Gemini API response times
      3. Check Document AI processing times
    EOT
    mime_type = "text/markdown"
  }

  user_labels = {
    environment = var.environment
    severity    = "p2"
  }
}
