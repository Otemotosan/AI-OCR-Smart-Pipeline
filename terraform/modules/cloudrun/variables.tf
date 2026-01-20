# Cloud Run Module - Variables

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
}

variable "environment" {
  description = "Environment name (staging, production)"
  type        = string
}

variable "service_account" {
  description = "Service account email for Cloud Run services"
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
  description = "Custom domain for API service"
  type        = string
  default     = ""
}

variable "ui_domain" {
  description = "Custom domain for UI service"
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
