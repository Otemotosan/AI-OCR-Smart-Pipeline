# Functions Module - Variables

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
  description = "Service account email for function execution"
  type        = string
}

variable "input_bucket" {
  description = "Input bucket name for trigger"
  type        = string
}

variable "output_bucket" {
  description = "Output bucket name"
  type        = string
}

variable "quarantine_bucket" {
  description = "Quarantine bucket name"
  type        = string
}

variable "bigquery_dataset" {
  description = "BigQuery dataset ID"
  type        = string
}

variable "document_ai_processor" {
  description = "Document AI processor ID"
  type        = string
}

variable "gemini_api_key_secret" {
  description = "Secret Manager secret ID for Gemini API key"
  type        = string
}

variable "slack_webhook_secret" {
  description = "Secret Manager secret ID for Slack webhook"
  type        = string
}

variable "function_source_bucket" {
  description = "GCS bucket name for function source code"
  type        = string
}
