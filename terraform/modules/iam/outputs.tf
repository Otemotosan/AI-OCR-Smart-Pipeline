# IAM Module - Outputs

output "processor_service_account_email" {
  description = "Email of the processor service account"
  value       = google_service_account.processor.email
}

output "processor_service_account_name" {
  description = "Full name of the processor service account"
  value       = google_service_account.processor.name
}

output "api_service_account_email" {
  description = "Email of the API service account"
  value       = google_service_account.api.email
}

output "api_service_account_name" {
  description = "Full name of the API service account"
  value       = google_service_account.api.name
}

output "gemini_api_key_secret_id" {
  description = "Secret ID for Gemini API key"
  value       = google_secret_manager_secret.gemini_api_key.secret_id
}

output "slack_webhook_secret_id" {
  description = "Secret ID for Slack webhook"
  value       = google_secret_manager_secret.slack_webhook.secret_id
}
