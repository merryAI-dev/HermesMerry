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

variable "scheduler_service_account_id" {
  description = "Service account ID used by Cloud Scheduler to invoke Cloud Run jobs."
  type        = string
  default     = "hermes-merry-scheduler"
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

variable "ac_id" {
  description = "Default AC profile ID used by score and review sync jobs."
  type        = string
  default     = ""
}

variable "gmail_label_id" {
  description = "Gmail label ID used by the scheduled ingest job."
  type        = string
  default     = ""
}

variable "wiki_root" {
  description = "Writable path for the SQLite-backed Obsidian wiki projection."
  type        = string
  default     = "/tmp/hermes-merry-wiki"
}

variable "slack_channel" {
  description = "Slack channel ID for summaries."
  type        = string
  default     = ""
}

variable "slack_bot_token_secret_id" {
  description = "Secret Manager secret ID for the Slack bot token."
  type        = string
  default     = "merry-slack-bot-token"
}

variable "ops_alert_email" {
  description = "Email address for frontless job operational alerts."
  type        = string
  default     = ""
}

variable "enable_ops_alerts" {
  description = "Whether to create operational alerting resources for scheduled frontless jobs."
  type        = bool
  default     = false
}
