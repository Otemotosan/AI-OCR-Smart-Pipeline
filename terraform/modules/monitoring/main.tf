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
# Alert Policies
# ============================================================

# P0: High Failure Rate (>5% in 1 hour)
resource "google_monitoring_alert_policy" "high_failure_rate" {
  display_name = "OCR Pipeline - High Failure Rate (${var.environment})"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Failure rate > 5%"

    condition_threshold {
      filter          = "resource.type=\"cloud_function\" AND resource.labels.function_name=~\"ocr-processor-${var.environment}\" AND metric.type=\"cloudfunctions.googleapis.com/function/execution_count\""
      duration        = "3600s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05

      aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_NONE"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email[0].id] : []

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = <<-EOT
      ## High Failure Rate Alert

      The OCR pipeline is experiencing a failure rate above 5% in the last hour.

      ### Investigation Steps
      1. Check Cloud Logging for error messages
      2. Review recent deployments
      3. Check Gemini API status
      4. Verify Document AI processor status

      ### Runbook
      See: docs/runbooks/high-failure-rate.md
    EOT
    mime_type = "text/markdown"
  }

  user_labels = {
    environment = var.environment
    severity    = "p0"
  }
}

# P0: Queue Backlog (>100 pending documents)
resource "google_monitoring_alert_policy" "queue_backlog" {
  display_name = "OCR Pipeline - Queue Backlog (${var.environment})"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Queue backlog > 100"

    condition_threshold {
      filter          = "resource.type=\"cloud_function\" AND resource.labels.function_name=~\"ocr-processor-${var.environment}\" AND metric.type=\"cloudfunctions.googleapis.com/function/active_instances\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 10

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_MAX"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email[0].id] : []

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = <<-EOT
      ## Queue Backlog Alert

      The OCR pipeline has a large backlog of documents waiting to be processed.

      ### Investigation Steps
      1. Check if Cloud Functions are scaling properly
      2. Review rate limits and quotas
      3. Check for stuck processing jobs

      ### Runbook
      See: docs/runbooks/queue-backlog.md
    EOT
    mime_type = "text/markdown"
  }

  user_labels = {
    environment = var.environment
    severity    = "p0"
  }
}

# P1: Pro Budget Warning (>80% daily)
resource "google_monitoring_alert_policy" "pro_budget" {
  display_name = "OCR Pipeline - Pro Budget Warning (${var.environment})"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Pro API usage > 80%"

    condition_threshold {
      filter          = "resource.type=\"global\" AND metric.type=\"logging.googleapis.com/user/ocr_pro_usage\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 40  # 80% of 50 daily limit

      aggregations {
        alignment_period     = "86400s"  # 24 hours
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email[0].id] : []

  alert_strategy {
    auto_close = "86400s"  # Auto-close after 24 hours
  }

  documentation {
    content   = <<-EOT
      ## Pro Budget Warning

      The Gemini Pro API usage is above 80% of the daily limit.

      ### Investigation Steps
      1. Review documents causing Pro escalation
      2. Check quality of input documents
      3. Consider adjusting confidence thresholds

      ### Runbook
      See: docs/runbooks/pro-budget.md
    EOT
    mime_type = "text/markdown"
  }

  user_labels = {
    environment = var.environment
    severity    = "p1"
  }
}

# P2: Low Confidence (average < 0.7)
resource "google_monitoring_alert_policy" "low_confidence" {
  display_name = "OCR Pipeline - Low Confidence (${var.environment})"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Average confidence < 0.7"

    condition_threshold {
      filter          = "resource.type=\"global\" AND metric.type=\"logging.googleapis.com/user/ocr_confidence_score\""
      duration        = "3600s"
      comparison      = "COMPARISON_LT"
      threshold_value = 0.7

      aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email[0].id] : []

  alert_strategy {
    auto_close = "7200s"
  }

  documentation {
    content   = <<-EOT
      ## Low Confidence Alert

      The average extraction confidence is below 0.7.

      ### Investigation Steps
      1. Review recent document quality
      2. Check for new document types
      3. Analyze extraction errors

      ### Runbook
      See: docs/runbooks/low-confidence.md
    EOT
    mime_type = "text/markdown"
  }

  user_labels = {
    environment = var.environment
    severity    = "p2"
  }
}

# ============================================================
# Uptime Checks
# ============================================================

resource "google_monitoring_uptime_check_config" "api_health" {
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
      host       = "ocr-api-${var.environment}-run.app"
    }
  }

  content_matchers {
    content = "healthy"
    matcher = "CONTAINS_STRING"
  }
}

# ============================================================
# Log-Based Metrics
# ============================================================

resource "google_logging_metric" "pro_usage" {
  name        = "ocr_pro_usage"
  project     = var.project_id
  description = "Count of Gemini Pro API calls"
  filter      = "resource.type=\"cloud_function\" AND jsonPayload.model=\"pro\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_logging_metric" "confidence_score" {
  name        = "ocr_confidence_score"
  project     = var.project_id
  description = "Extraction confidence scores"
  filter      = "resource.type=\"cloud_function\" AND jsonPayload.confidence_score!=\"\""

  metric_descriptor {
    metric_kind = "GAUGE"
    value_type  = "DOUBLE"
    unit        = "1"
  }

  value_extractor = "EXTRACT(jsonPayload.confidence_score)"
}

resource "google_logging_metric" "processing_duration" {
  name        = "ocr_processing_duration"
  project     = var.project_id
  description = "Document processing duration in milliseconds"
  filter      = "resource.type=\"cloud_function\" AND jsonPayload.processing_duration_ms!=\"\""

  metric_descriptor {
    metric_kind = "GAUGE"
    value_type  = "INT64"
    unit        = "ms"
  }

  value_extractor = "EXTRACT(jsonPayload.processing_duration_ms)"

  bucket_options {
    exponential_buckets {
      num_finite_buckets = 20
      growth_factor      = 2
      scale              = 100
    }
  }
}
