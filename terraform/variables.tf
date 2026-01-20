# AI-OCR Smart Pipeline - Terraform Variables
# These variables are used across all modules.

# ============================================================
# Project Configuration
# ============================================================

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region for resources"
  type        = string
  default     = "asia-northeast1"
}

variable "environment" {
  description = "Environment name (staging, production)"
  type        = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Environment must be 'staging' or 'production'."
  }
}

# ============================================================
# Document AI Configuration
# ============================================================

variable "document_ai_processor_id" {
  description = "Document AI processor ID (full resource path)"
  type        = string
}

# ============================================================
# Container Images
# ============================================================

variable "api_image" {
  description = "Docker image for API service"
  type        = string
  default     = ""
}

variable "ui_image" {
  description = "Docker image for UI service"
  type        = string
  default     = ""
}

# ============================================================
# Domain Configuration
# ============================================================

variable "api_domain" {
  description = "Custom domain for API service (optional)"
  type        = string
  default     = ""
}

variable "ui_domain" {
  description = "Custom domain for UI service (optional)"
  type        = string
  default     = ""
}

# ============================================================
# IAP Configuration
# ============================================================

variable "iap_oauth_client_id" {
  description = "OAuth Client ID for Identity-Aware Proxy"
  type        = string
  default     = ""
  sensitive   = true
}

variable "iap_oauth_client_secret" {
  description = "OAuth Client Secret for Identity-Aware Proxy"
  type        = string
  default     = ""
  sensitive   = true
}

variable "iap_allowed_members" {
  description = "List of members allowed to access via IAP"
  type        = list(string)
  default     = []
}

# ============================================================
# Alerting Configuration
# ============================================================

variable "slack_notification_channel" {
  description = "Slack notification channel ID for Cloud Monitoring"
  type        = string
  default     = ""
}

variable "alert_email" {
  description = "Email address for alert notifications"
  type        = string
  default     = ""
}

# ============================================================
# Budget Configuration
# ============================================================

variable "pro_daily_limit" {
  description = "Daily limit for Gemini Pro API calls"
  type        = number
  default     = 50
}

variable "pro_monthly_limit" {
  description = "Monthly limit for Gemini Pro API calls"
  type        = number
  default     = 1000
}

# ============================================================
# Scaling Configuration
# ============================================================

variable "function_max_instances" {
  description = "Maximum instances for Cloud Functions"
  type        = number
  default     = 10
}

variable "function_min_instances" {
  description = "Minimum instances for Cloud Functions"
  type        = number
  default     = 0
}

variable "cloudrun_max_instances" {
  description = "Maximum instances for Cloud Run services"
  type        = number
  default     = 10
}

variable "cloudrun_min_instances" {
  description = "Minimum instances for Cloud Run services"
  type        = number
  default     = 0
}
