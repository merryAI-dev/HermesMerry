output "dataset_id" {
  value = google_bigquery_dataset.merry.dataset_id
}

output "raw_bucket" {
  value = google_storage_bucket.raw_docs.name
}

output "agent_service_account" {
  value = google_service_account.agent.email
}

output "scheduler_service_account" {
  value = google_service_account.scheduler.email
}

output "cloud_run_jobs" {
  value = sort(keys(google_cloud_run_v2_job.agent_jobs))
}

output "artifact_registry_repository" {
  value = google_artifact_registry_repository.runtime.name
}
