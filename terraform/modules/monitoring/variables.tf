# Monitoring Module - Variables

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "environment" {
  description = "Environment name (staging, production)"
  type        = string
}

variable "notification_channel" {
  description = "Notification channel ID (e.g., Slack)"
  type        = string
  default     = ""
}

variable "alert_email" {
  description = "Email address for alert notifications"
  type        = string
  default     = ""
}
