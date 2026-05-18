from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_marks_runpod_as_primary_staging_backend() -> None:
    readme = (REPO_ROOT / "README.md").read_text()

    assert "Runpod-first staging" in readme
    assert "docker.io/boram1220/hermes-merry:staging" in readme
    assert "Cloud Run is optional" in readme


def test_runpod_runbook_contains_required_stop_conditions() -> None:
    runbook = (REPO_ROOT / "docs" / "runbooks" / "runpod-staging.md").read_text()

    for required in (
        "GOOGLE_APPLICATION_CREDENTIALS_JSON",
        "/workspace/hermes/wiki",
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
        "BigQuery agent_runs row",
        "GCS raw object",
        "Sheet tab",
        "Slack message timestamp",
        "Wiki path",
        "Rollback command",
    ):
        assert required in template


def test_runpod_append_mode_is_documented_as_one_cycle_canary_only() -> None:
    env_example = (REPO_ROOT / "configs" / "runpod.env.example").read_text()
    runbook = (REPO_ROOT / "docs" / "runbooks" / "runpod-staging.md").read_text()

    assert "BIGQUERY_WRITE_MODE=merge" in env_example
    assert "AGENT_LOOP_MAX_CYCLES=0" in env_example
    assert "`BIGQUERY_WRITE_MODE=append` only with `AGENT_LOOP_MAX_CYCLES=1`" in runbook
    assert "`BIGQUERY_WRITE_MODE=merge`" in runbook
