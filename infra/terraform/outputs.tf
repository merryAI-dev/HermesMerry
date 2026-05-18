output "dataset_id" {
  value = google_bigquery_dataset.merry.dataset_id
}

output "raw_bucket" {
  value = google_storage_bucket.raw_docs.name
}

output "agent_service_account" {
  value = google_service_account.agent.email
}

output "agent_service_account_email" {
  value = google_service_account.agent.email
}

output "scheduler_service_account" {
  value = try(google_service_account.scheduler[0].email, "")
}

output "cloud_run_jobs" {
  value = sort(keys(google_cloud_run_v2_job.agent_jobs))
}

output "artifact_registry_repository" {
  value = try(google_artifact_registry_repository.runtime[0].name, "")
}
