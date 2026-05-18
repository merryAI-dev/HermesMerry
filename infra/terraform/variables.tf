variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run jobs and Scheduler."
  type        = string
  default     = "asia-northeast3"
}

variable "dataset_id" {
  description = "BigQuery dataset for Hermes x Merry."
  type        = string
  default     = "merry_ac_discovery"
}

variable "raw_bucket_name" {
  description = "Globally unique GCS bucket name for raw documents."
  type        = string
}

variable "image_uri" {
  description = "Container image URI for Cloud Run jobs."
  type        = string
}

variable "service_account_id" {
  description = "Service account ID used by agent jobs."
  type        = string
  default     = "hermes-merry-agent"
}

variable "llm_api_key_secret_id" {
  description = "Secret Manager secret ID for the selected LLM provider API key."
  type        = string
  default     = "merry-llm-api-key"
}

variable "review_sheet_id" {
  description = "Google Sheet ID used as the review queue."
  type        = string
  default     = ""
}

variable "slack_channel" {
  description = "Slack channel ID for summaries."
  type        = string
  default     = ""
}
