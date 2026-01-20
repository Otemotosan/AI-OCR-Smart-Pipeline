# Production Environment Variables

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "asia-northeast1"
}

variable "document_ai_processor_id" {
  description = "Document AI processor ID"
  type        = string
}

variable "api_image" {
  description = "Docker image for API service"
  type        = string
}

variable "ui_image" {
  description = "Docker image for UI service"
  type        = string
}

variable "api_domain" {
  description = "Custom domain for API"
  type        = string
}

variable "ui_domain" {
  description = "Custom domain for UI"
  type        = string
}

variable "iap_oauth_client_id" {
  description = "OAuth Client ID for IAP"
  type        = string
  sensitive   = true
}

variable "iap_oauth_client_secret" {
  description = "OAuth Client Secret for IAP"
  type        = string
  sensitive   = true
}

variable "iap_allowed_members" {
  description = "Members allowed to access via IAP"
  type        = list(string)
  default     = []
}

variable "alert_email" {
  description = "Email for alerts"
  type        = string
}

variable "slack_notification_channel" {
  description = "Slack notification channel ID"
  type        = string
  default     = ""
}
