from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_marks_runpod_as_primary_staging_backend() -> None:
    readme = (REPO_ROOT / "README.md").read_text()

    assert "Runpod-first staging" in readme
    assert "docker.io/boram1220/hermes-merry:staging" in readme
    assert "SQLite-backed Mother DB" in readme
    assert "Cloud Run is optional" in readme


def test_runpod_runbook_contains_required_stop_conditions() -> None:
    runbook = (REPO_ROOT / "docs" / "runbooks" / "runpod-staging.md").read_text()

    for required in (
        "GOOGLE_APPLICATION_CREDENTIALS_JSON",
        "APPS_SCRIPT_DRAFT_SECRET",
        "/home/hermes/hermes/wiki",
        "/home/hermes/hermes/mother.db",
        "backup-export",
        "infra/terraform/runpod-staging.tfvars",
        "docker buildx build --platform linux/amd64",
        "docker.io/boram1220/hermes-merry:staging",
        "Runpod Container Registry Auth",
        "python3 -m merry_runtime.jobs loop",
    ):
        assert required in runbook


def test_cloud_run_canary_is_marked_optional_backend() -> None:
    runbook = (REPO_ROOT / "docs" / "runbooks" / "staging-canary.md").read_text()

    assert "Optional Cloud Run backend" in runbook


def test_runpod_canary_results_template_captures_required_evidence() -> None:
    template = (REPO_ROOT / "docs" / "runbooks" / "runpod-canary-results.md").read_text()

    for required in (
        "Docker Hub image digest",
        "Runpod Pod ID",
        "SQLite Mother DB",
        "backup-export",
        "Sheet tab",
        "Slack message timestamp",
        "Wiki path",
        "Rollback command",
    ):
        assert required in template


def test_runpod_sqlite_mode_is_documented_as_primary_runtime() -> None:
    env_example = (REPO_ROOT / "configs" / "runpod.env.example").read_text()
    runbook = (REPO_ROOT / "docs" / "runbooks" / "runpod-staging.md").read_text()

    assert "STRUCTURED_STORE_BACKEND=sqlite" in env_example
    assert "MOTHER_DB_PATH=/home/hermes/hermes/mother.db" in env_example
    assert "BACKUP_ROOT=/home/hermes/hermes/backups" in env_example
    assert "HERMES_AGENT_ID=runpod-hermes-staging" in env_example
    assert "APPS_SCRIPT_DRAFT_WEBHOOK_URL=" in env_example
    assert "APPS_SCRIPT_DRAFT_SECRET=" in env_example
    assert "AGENT_LOOP_JOBS=crawl-sources,draft-outreach-emails,enrich-sminfo,backup-export" in env_example
    assert "AGENT_LOOP_MAX_CYCLES=0" in env_example
    assert "BigQuery is optional" in runbook
    assert "STRUCTURED_STORE_BACKEND=bigquery" in runbook
