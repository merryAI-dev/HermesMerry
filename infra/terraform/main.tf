terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  table_schemas = {
    raw_sources = [
      { name = "source_id", type = "STRING", mode = "REQUIRED" },
      { name = "source_type", type = "STRING", mode = "REQUIRED" },
      { name = "channel", type = "STRING", mode = "REQUIRED" },
      { name = "url", type = "STRING", mode = "NULLABLE" },
      { name = "title", type = "STRING", mode = "NULLABLE" },
      { name = "raw_text_path", type = "STRING", mode = "REQUIRED" },
      { name = "published_at", type = "TIMESTAMP", mode = "NULLABLE" },
      { name = "collected_at", type = "TIMESTAMP", mode = "REQUIRED" },
      { name = "checksum", type = "STRING", mode = "REQUIRED" },
      { name = "contains_pii", type = "BOOL", mode = "REQUIRED" }
    ]
    mother_entities = [
      { name = "entity_id", type = "STRING", mode = "REQUIRED" },
      { name = "entity_type", type = "STRING", mode = "REQUIRED" },
      { name = "name", type = "STRING", mode = "REQUIRED" },
      { name = "normalized_name", type = "STRING", mode = "REQUIRED" },
      { name = "region", type = "STRING", mode = "NULLABLE" },
      { name = "industry", type = "STRING", mode = "NULLABLE" },
      { name = "homepage", type = "STRING", mode = "NULLABLE" },
      { name = "representative", type = "STRING", mode = "NULLABLE" },
      { name = "first_seen_at", type = "TIMESTAMP", mode = "REQUIRED" },
      { name = "last_seen_at", type = "TIMESTAMP", mode = "REQUIRED" }
    ]
    entity_aliases = [
      { name = "alias_id", type = "STRING", mode = "REQUIRED" },
      { name = "entity_id", type = "STRING", mode = "REQUIRED" },
      { name = "alias", type = "STRING", mode = "REQUIRED" },
      { name = "normalized_alias", type = "STRING", mode = "REQUIRED" },
      { name = "source_id", type = "STRING", mode = "NULLABLE" },
      { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" }
    ]
    entity_resolution_events = [
      { name = "event_id", type = "STRING", mode = "REQUIRED" },
      { name = "candidate_entity_id", type = "STRING", mode = "REQUIRED" },
      { name = "matched_entity_id", type = "STRING", mode = "NULLABLE" },
      { name = "action", type = "STRING", mode = "REQUIRED" },
      { name = "probability", type = "FLOAT", mode = "REQUIRED" },
      { name = "features_json", type = "STRING", mode = "REQUIRED" },
      { name = "rationale", type = "STRING", mode = "REQUIRED" },
      { name = "status", type = "STRING", mode = "REQUIRED" },
      { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" }
    ]
    signals = [
      { name = "signal_id", type = "STRING", mode = "REQUIRED" },
      { name = "entity_id", type = "STRING", mode = "REQUIRED" },
      { name = "signal_type", type = "STRING", mode = "REQUIRED" },
      { name = "evidence_text", type = "STRING", mode = "REQUIRED" },
      { name = "source_id", type = "STRING", mode = "REQUIRED" },
      { name = "confidence", type = "FLOAT", mode = "REQUIRED" },
      { name = "tags", type = "STRING", mode = "REPEATED" },
      { name = "detected_at", type = "TIMESTAMP", mode = "REQUIRED" }
    ]
    ac_profiles = [
      { name = "ac_id", type = "STRING", mode = "REQUIRED" },
      { name = "ac_name", type = "STRING", mode = "REQUIRED" },
      { name = "fund_purpose", type = "STRING", mode = "REQUIRED" },
      { name = "recruiting_area", type = "STRING", mode = "NULLABLE" },
      { name = "hypothesis_tags", type = "STRING", mode = "REPEATED" },
      { name = "impact_priority", type = "STRING", mode = "REPEATED" },
      { name = "region_preferences", type = "STRING", mode = "REPEATED" },
      { name = "industry_preferences", type = "STRING", mode = "REPEATED" },
      { name = "tech_preferences", type = "STRING", mode = "REPEATED" }
    ]
    ac_scores = [
      { name = "score_id", type = "STRING", mode = "REQUIRED" },
      { name = "ac_id", type = "STRING", mode = "REQUIRED" },
      { name = "entity_id", type = "STRING", mode = "REQUIRED" },
      { name = "base_score", type = "FLOAT", mode = "REQUIRED" },
      { name = "fund_fit_score", type = "FLOAT", mode = "REQUIRED" },
      { name = "recruiting_fit_score", type = "FLOAT", mode = "REQUIRED" },
      { name = "hypothesis_fit_score", type = "FLOAT", mode = "REQUIRED" },
      { name = "impact_fit_score", type = "FLOAT", mode = "REQUIRED" },
      { name = "total_score", type = "FLOAT", mode = "REQUIRED" },
      { name = "priority_probability", type = "FLOAT", mode = "REQUIRED" },
      { name = "priority_utility", type = "FLOAT", mode = "REQUIRED" },
      { name = "queue_type", type = "STRING", mode = "REQUIRED" },
      { name = "uncertainty", type = "FLOAT", mode = "REQUIRED" },
      { name = "model_version", type = "STRING", mode = "REQUIRED" },
      { name = "rationale", type = "STRING", mode = "REQUIRED" },
      { name = "recommended_action", type = "STRING", mode = "REQUIRED" },
      { name = "scored_at", type = "TIMESTAMP", mode = "REQUIRED" }
    ]
    candidate_cards = [
      { name = "card_id", type = "STRING", mode = "REQUIRED" },
      { name = "ac_id", type = "STRING", mode = "REQUIRED" },
      { name = "entity_id", type = "STRING", mode = "REQUIRED" },
      { name = "summary", type = "STRING", mode = "REQUIRED" },
      { name = "recommended_action", type = "STRING", mode = "REQUIRED" },
      { name = "queue_type", type = "STRING", mode = "REQUIRED" },
      { name = "status", type = "STRING", mode = "REQUIRED" },
      { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" }
    ]
    reviews = [
      { name = "review_id", type = "STRING", mode = "REQUIRED" },
      { name = "card_id", type = "STRING", mode = "REQUIRED" },
      { name = "reviewer", type = "STRING", mode = "REQUIRED" },
      { name = "decision", type = "STRING", mode = "REQUIRED" },
      { name = "memo", type = "STRING", mode = "NULLABLE" },
      { name = "reviewed_at", type = "TIMESTAMP", mode = "REQUIRED" }
    ]
    agent_runs = [
      { name = "run_id", type = "STRING", mode = "REQUIRED" },
      { name = "job_name", type = "STRING", mode = "REQUIRED" },
      { name = "status", type = "STRING", mode = "REQUIRED" },
      { name = "started_at", type = "TIMESTAMP", mode = "REQUIRED" },
      { name = "finished_at", type = "TIMESTAMP", mode = "NULLABLE" },
      { name = "input_count", type = "INTEGER", mode = "NULLABLE" },
      { name = "output_count", type = "INTEGER", mode = "NULLABLE" },
      { name = "error_message", type = "STRING", mode = "NULLABLE" }
    ]
  }

  jobs = {
    ingest-sources = {
      args     = ["-m", "merry_runtime.jobs", "run", "ingest-sources"]
      schedule = "0 * * * *"
    }
    resolve-entities = {
      args     = ["-m", "merry_runtime.jobs", "run", "resolve-entities"]
      schedule = "15 * * * *"
    }
    score-candidates = {
      args     = ["-m", "merry_runtime.jobs", "run", "score-candidates"]
      schedule = "30 * * * *"
    }
    sync-review-sheet = {
      args     = ["-m", "merry_runtime.jobs", "run", "sync-review-sheet"]
      schedule = "45 * * * *"
    }
    weekly-summary = {
      args     = ["-m", "merry_runtime.jobs", "run", "weekly-summary"]
      schedule = "0 9 * * MON"
    }
  }
}

resource "google_bigquery_dataset" "merry" {
  dataset_id                 = var.dataset_id
  location                   = "asia-northeast3"
  delete_contents_on_destroy = false
}

resource "google_bigquery_table" "tables" {
  for_each = local.table_schemas

  dataset_id          = google_bigquery_dataset.merry.dataset_id
  table_id            = each.key
  deletion_protection = true
  schema              = jsonencode(each.value)
}

resource "google_storage_bucket" "raw_docs" {
  name                        = var.raw_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 365
    }
  }
}

resource "google_artifact_registry_repository" "runtime" {
  location      = var.region
  repository_id = "hermes-merry"
  description   = "Hermes Merry AC discovery runtime images"
  format        = "DOCKER"
}

resource "google_service_account" "agent" {
  account_id   = var.service_account_id
  display_name = "Hermes Merry AC discovery agent"
}

resource "google_service_account" "scheduler" {
  account_id   = var.scheduler_service_account_id
  display_name = "Hermes Merry scheduler invoker"
}

resource "google_project_iam_member" "bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_bigquery_dataset_iam_member" "bigquery_data_editor" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.merry.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_storage_bucket_iam_member" "raw_docs_object_creator" {
  bucket = google_storage_bucket.raw_docs.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_secret_manager_secret" "llm_api_key" {
  secret_id = var.llm_api_key_secret_id

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "llm_secret_accessor" {
  secret_id = google_secret_manager_secret.llm_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_secret_manager_secret" "slack_bot_token" {
  secret_id = var.slack_bot_token_secret_id

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "slack_secret_accessor" {
  secret_id = google_secret_manager_secret.slack_bot_token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_cloud_run_v2_job" "agent_jobs" {
  for_each = local.jobs

  name     = each.key
  location = var.region

  template {
    template {
      service_account = google_service_account.agent.email

      containers {
        image   = var.image_uri
        command = ["python3"]
        args    = each.value.args

        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "BIGQUERY_DATASET"
          value = google_bigquery_dataset.merry.dataset_id
        }

        env {
          name  = "RAW_BUCKET"
          value = google_storage_bucket.raw_docs.name
        }

        env {
          name  = "REVIEW_SHEET_ID"
          value = var.review_sheet_id
        }

        env {
          name  = "AC_ID"
          value = var.ac_id
        }

        env {
          name  = "GMAIL_LABEL_ID"
          value = var.gmail_label_id
        }

        env {
          name  = "WIKI_ROOT"
          value = var.wiki_root
        }

        env {
          name  = "SLACK_CHANNEL"
          value = var.slack_channel
        }

        env {
          name = "LLM_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.llm_api_key.secret_id
              version = "latest"
            }
          }
        }

        env {
          name = "SLACK_BOT_TOKEN"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.slack_bot_token.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  for_each = google_cloud_run_v2_job.agent_jobs

  project  = var.project_id
  location = var.region
  name     = each.value.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_scheduler_job" "agent_schedules" {
  for_each = local.jobs

  name      = "${each.key}-schedule"
  region    = var.region
  schedule  = each.value.schedule
  time_zone = "Asia/Seoul"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.agent_jobs[each.key].name}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
}
