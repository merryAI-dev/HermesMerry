from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_uses_digest_pinned_base_and_hash_locked_install() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()

    assert "FROM python:3.12-slim@sha256:" in dockerfile
    assert "pip install --require-hashes -r requirements.lock" in dockerfile
    assert "pip install --no-deps ." in dockerfile


def test_ci_runs_pip_audit_against_locked_requirements() -> None:
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "pip-audit" in ci
    assert "requirements.lock" in ci
