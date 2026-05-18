import re
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SETUPTOOLS_VERSION = "80.9.0"
PIP_AUDIT_VERSION = "2.10.0"
PYTEST_VERSION = "9.0.2"


def _lock_has_hash_locked_requirement(lock_path: Path, package: str, version: str) -> bool:
    lines = lock_path.read_text().splitlines()
    requirement_prefix = f"{package}=={version}"
    for index, line in enumerate(lines):
        if not line.startswith(requirement_prefix):
            continue
        for following_line in lines[index + 1 :]:
            if following_line and not following_line.startswith((" ", "#")):
                return False
            if "--hash=sha256:" in following_line:
                return True
    return False


def test_dockerfile_uses_digest_pinned_base_and_hash_locked_install() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    first_line = dockerfile.splitlines()[0]

    assert re.fullmatch(r"FROM python:3\.12-slim@sha256:[0-9a-f]{64}", first_line)
    assert "RUN pip install --no-cache-dir --require-hashes -r requirements.lock" in dockerfile
    assert "RUN pip install --no-cache-dir --no-deps --no-build-isolation ." in dockerfile


def test_build_backend_is_exact_pinned_and_hash_locked_for_non_isolated_build() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())

    assert pyproject["build-system"]["requires"] == [f"setuptools=={SETUPTOOLS_VERSION}"]
    assert _lock_has_hash_locked_requirement(
        REPO_ROOT / "requirements.lock",
        "setuptools",
        SETUPTOOLS_VERSION,
    )


def test_ci_runs_pip_audit_against_locked_requirements() -> None:
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert 'pip install -e ".[dev]"' not in ci
    assert "pip install -e '.[dev]'" not in ci
    assert re.search(
        r"(?m)^\s*run:\s*python\s+-m\s+pip\s+install\s+--require-hashes\s+-r\s+requirements\.lock\s*$",
        ci,
    )
    assert re.search(
        r"(?m)^\s*run:\s*python\s+-m\s+pip\s+install\s+--require-hashes\s+-r\s+requirements-dev\.lock\s*$",
        ci,
    )
    assert re.search(
        r"(?m)^\s*run:\s*python\s+-m\s+pip\s+install\s+--no-deps\s+--no-build-isolation\s+-e\s+\.\s*$",
        ci,
    )
    assert re.search(
        r"(?m)^\s*run:\s*python3\s+-m\s+pip\s+install\s+--require-hashes\s+-r\s+requirements-audit\.lock\s*$",
        ci,
    )
    assert re.search(
        r"(?m)^\s*run:\s*(?:python3\s+-m\s+pip_audit|pip-audit)\s+-r\s+requirements\.lock\s*$",
        ci,
    )
    assert not re.search(r"(?m)^\s*run:\s*python3\s+-m\s+pip\s+install\s+pip-audit\s*$", ci)
    assert "continue-on-error: true" not in ci
    assert "|| true" not in ci
    assert "--ignore-vuln" not in ci
    assert "--skip-vuln" not in ci


def test_audit_tooling_is_hash_locked() -> None:
    assert (REPO_ROOT / "requirements-audit.in").read_text().splitlines() == [
        f"pip-audit=={PIP_AUDIT_VERSION}"
    ]
    assert _lock_has_hash_locked_requirement(
        REPO_ROOT / "requirements-audit.lock",
        "pip-audit",
        PIP_AUDIT_VERSION,
    )


def test_dev_test_tooling_is_hash_locked() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())

    assert pyproject["project"]["optional-dependencies"]["dev"] == [f"pytest=={PYTEST_VERSION}"]
    assert (REPO_ROOT / "requirements-dev.in").read_text().splitlines() == [
        f"pytest=={PYTEST_VERSION}"
    ]
    assert _lock_has_hash_locked_requirement(
        REPO_ROOT / "requirements-dev.lock",
        "pytest",
        PYTEST_VERSION,
    )


def test_runpod_entrypoint_materializes_gcp_credentials_to_tmp_only() -> None:
    entrypoint = (REPO_ROOT / "scripts" / "runpod_entrypoint.sh").read_text()

    assert "GOOGLE_APPLICATION_CREDENTIALS_JSON" in entrypoint
    assert "mktemp /tmp/hermes-gcp-" in entrypoint
    assert "chmod 600" in entrypoint
    assert "/workspace" not in entrypoint


def test_dockerfile_uses_runpod_entrypoint_before_jobs_cli() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()

    assert "COPY scripts/runpod_entrypoint.sh /usr/local/bin/runpod-entrypoint" in dockerfile
    assert 'ENTRYPOINT ["runpod-entrypoint", "python3", "-m", "merry_runtime.jobs"]' in dockerfile


def test_ghcr_build_script_pushes_linux_amd64_staging_image() -> None:
    script = (REPO_ROOT / "scripts" / "build_ghcr_staging.sh").read_text()

    assert "docker buildx build" in script
    assert "--platform linux/amd64" in script
    assert "ghcr.io/${GHCR_OWNER}/hermes-merry:${IMAGE_TAG}" in script
    assert "--push" in script
