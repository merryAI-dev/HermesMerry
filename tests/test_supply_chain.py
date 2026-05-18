import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_uses_digest_pinned_base_and_hash_locked_install() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    first_line = dockerfile.splitlines()[0]

    assert re.fullmatch(r"FROM python:3\.12-slim@sha256:[0-9a-f]{64}", first_line)
    assert "RUN pip install --no-cache-dir --require-hashes -r requirements.lock" in dockerfile
    assert "RUN pip install --no-cache-dir --no-deps ." in dockerfile


def test_ci_runs_pip_audit_against_locked_requirements() -> None:
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert re.search(
        r"(?m)^\s*run:\s*(?:python3\s+-m\s+pip_audit|pip-audit)\s+-r\s+requirements\.lock\s*$",
        ci,
    )
    assert "continue-on-error: true" not in ci
    assert "|| true" not in ci
    assert "--ignore-vuln" not in ci
    assert "--skip-vuln" not in ci
