# Staging Environment Variables

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
  default     = ""
}

variable "ui_image" {
  description = "Docker image for UI service"
  type        = string
  default     = ""
}

variable "api_domain" {
  description = "Custom domain for API"
  type        = string
  default     = ""
}

variable "ui_domain" {
  description = "Custom domain for UI"
  type        = string
  default     = ""
}

variable "iap_oauth_client_id" {
  description = "OAuth Client ID for IAP"
  type        = string
  default     = ""
  sensitive   = true
}

variable "iap_oauth_client_secret" {
  description = "OAuth Client Secret for IAP"
  type        = string
  default     = ""
  sensitive   = true
}

variable "alert_email" {
  description = "Email for alerts"
  type        = string
  default     = ""
}
