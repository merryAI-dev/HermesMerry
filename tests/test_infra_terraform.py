from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_terraform_wires_required_runtime_job_environment_and_slack_secret() -> None:
    main_tf = (REPO_ROOT / "infra" / "terraform" / "main.tf").read_text()
    variables_tf = (REPO_ROOT / "infra" / "terraform" / "variables.tf").read_text()

    for variable_name in ("ac_id", "gmail_label_id", "wiki_root", "slack_bot_token_secret_id"):
        assert f'variable "{variable_name}"' in variables_tf

    for env_name in ("AC_ID", "GMAIL_LABEL_ID", "WIKI_ROOT", "SLACK_BOT_TOKEN"):
        assert f'name  = "{env_name}"' in main_tf or f'name = "{env_name}"' in main_tf

    assert "google_secret_manager_secret\" \"slack_bot_token" in main_tf
    assert "google_secret_manager_secret_iam_member\" \"slack_secret_accessor" in main_tf


def test_terraform_separates_scheduler_identity_and_scopes_bigquery_iam_to_dataset() -> None:
    main_tf = (REPO_ROOT / "infra" / "terraform" / "main.tf").read_text()
    variables_tf = (REPO_ROOT / "infra" / "terraform" / "variables.tf").read_text()

    assert 'variable "scheduler_service_account_id"' in variables_tf
    assert 'google_service_account" "scheduler"' in main_tf
    assert 'google_bigquery_dataset_iam_member" "bigquery_data_editor"' in main_tf
    assert 'role    = "roles/run.developer"' not in main_tf
    assert 'google_cloud_run_v2_job_iam_member" "scheduler_invoker"' in main_tf
    assert "service_account_email = google_service_account.scheduler.email" in main_tf


def test_terraform_grants_create_only_raw_docs_bucket_access() -> None:
    main_tf = (REPO_ROOT / "infra" / "terraform" / "main.tf").read_text()

    assert "roles/storage.objectAdmin" not in main_tf
    assert 'role   = "roles/storage.objectCreator"' in main_tf


def test_terraform_defines_frontless_job_ops_alerting_shell() -> None:
    main_tf = (REPO_ROOT / "infra" / "terraform" / "main.tf").read_text()
    variables_tf = (REPO_ROOT / "infra" / "terraform" / "variables.tf").read_text()

    assert 'variable "ops_alert_email"' in variables_tf
    assert 'variable "enable_ops_alerts"' in variables_tf
    assert 'google_monitoring_notification_channel" "ops_email"' in main_tf
    assert 'google_logging_metric" "cloud_run_job_errors"' in main_tf
    assert 'google_monitoring_alert_policy" "frontless_job_failures"' in main_tf
    assert "count = var.enable_ops_alerts ? 1 : 0" in main_tf
    assert 'resource.type="cloud_run_job"' in main_tf
    assert 'severity>=ERROR' in main_tf


def test_dockerfile_runs_runtime_as_non_root_user() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()

    assert "useradd" in dockerfile
    assert "USER hermes" in dockerfile
