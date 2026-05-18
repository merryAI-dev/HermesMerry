from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_marks_runpod_as_primary_staging_backend() -> None:
    readme = (REPO_ROOT / "README.md").read_text()

    assert "Runpod-first staging" in readme
    assert "ghcr.io/$GHCR_OWNER/hermes-merry:staging" in readme
    assert "Cloud Run is optional" in readme


def test_runpod_runbook_contains_required_stop_conditions() -> None:
    runbook = (REPO_ROOT / "docs" / "runbooks" / "runpod-staging.md").read_text()

    for required in (
        "GOOGLE_APPLICATION_CREDENTIALS_JSON",
        "/workspace/hermes/wiki",
        "infra/terraform/runpod-staging.tfvars",
        "docker buildx build --platform linux/amd64",
        "ghcr.io/$GHCR_OWNER/hermes-merry:staging",
        "python3 -m merry_runtime.jobs loop",
    ):
        assert required in runbook


def test_cloud_run_canary_is_marked_optional_backend() -> None:
    runbook = (REPO_ROOT / "docs" / "runbooks" / "staging-canary.md").read_text()

    assert "Optional Cloud Run backend" in runbook
