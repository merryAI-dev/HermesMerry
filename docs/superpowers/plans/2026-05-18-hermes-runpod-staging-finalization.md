# Hermes Runpod Staging Finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Hermes staging by running the always-on agent loop on Runpod, pushing the runtime image to GHCR, and keeping GCP as the minimum data and Google Workspace integration layer.

**Architecture:** Runpod becomes the primary execution backend. GHCR stores the private runtime image. GCP keeps only BigQuery, GCS, a least-privilege runtime service account, and the Google Workspace API access needed by Gmail and Sheets. Cloud Run, Cloud Scheduler, Artifact Registry, and Secret Manager remain optional for the old GCP-native path but are disabled for the Runpod staging path.

**Tech Stack:** Python 3.12+, pytest, Docker buildx, GHCR, Runpod Pod, Runpod secrets/env, OpenTofu, GCP BigQuery, GCS, Gmail API, Google Sheets API, Slack Web API, SQLite-backed Obsidian wiki.

---

## Revised Runtime Flow

```text
Developer machine
  -> docker buildx build --platform linux/amd64
  -> ghcr.io/$GHCR_OWNER/hermes-merry:staging

Runpod Pod
  -> pulls GHCR image
  -> injects Runpod secrets and env
  -> writes GOOGLE_APPLICATION_CREDENTIALS_JSON to an ephemeral /tmp file
  -> runs python3 -m merry_runtime.jobs loop
  -> keeps SQLite wiki under /workspace/hermes/wiki

GCP minimal layer
  -> BigQuery structured tables
  -> GCS raw source bucket
  -> one least-privilege Hermes runtime service account
  -> Gmail API and Sheets API access through the same service account or delegated credential setup

Human interface
  -> Google Sheet review queue
  -> Slack summary channel
  -> Obsidian-compatible wiki files in the Runpod persistent volume
```

## Decisions Locked By This Plan

- Use GHCR as the image registry: `ghcr.io/$GHCR_OWNER/hermes-merry:staging`.
- Use a Runpod Pod, not Runpod Serverless, for the first staging runtime because Hermes needs a persistent loop.
- Keep `Cloud Run` as an optional execution backend, not the staging default.
- Do not create service account keys with Terraform. Terraform state must not contain private keys.
- Store the GCP service account JSON in Runpod secret `GOOGLE_APPLICATION_CREDENTIALS_JSON`, materialized only to `/tmp` inside the container at startup.
- Store the SQLite wiki under `/workspace/hermes/wiki` so Pod restarts do not erase it.
- Keep raw sources in GCS and structured state in BigQuery, not in the Runpod filesystem.
- Treat Runpod filesystem writes outside `/workspace/hermes` as disposable.

## Stop Conditions

Stop before push, apply, or canary if any of these are true:

- `GHCR_OWNER` is empty.
- `docker buildx` is unavailable.
- The active gcloud project does not match `project_id` in `infra/terraform/runpod-staging.tfvars`.
- Any staging value contains `prod` or `production`.
- `infra/terraform/runpod-staging.tfvars` is absent.
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` is being written to git, Terraform state, or a persistent repo file.
- Runpod `WIKI_ROOT` is not under `/workspace/hermes`.
- `SLACK_CHANNEL`, `REVIEW_SHEET_ID`, or `GMAIL_LABEL_ID` points to a production resource.

## File Structure

- Modify: `README.md` - switch staging instructions from Cloud Run-first to Runpod-first.
- Modify: `Dockerfile` - add Runpod credential bootstrap entrypoint while preserving the existing job CLI.
- Create: `scripts/build_ghcr_staging.sh` - build and push the linux/amd64 image to GHCR.
- Create: `scripts/runpod_entrypoint.sh` - convert Runpod secret JSON into ephemeral ADC file.
- Create: `configs/runpod.env.example` - documented Runpod env surface.
- Create: `docs/runbooks/runpod-staging.md` - end-to-end setup and canary runbook.
- Modify: `docs/runbooks/staging-canary.md` - mark Cloud Run canary as optional legacy backend.
- Modify: `docs/runbooks/staging-canary-results.md` - record the backend switch and current blocker status.
- Modify: `infra/terraform/variables.tf` - add `execution_backend` and optional resource toggles.
- Modify: `infra/terraform/main.tf` - conditionally disable Cloud Run, Scheduler, Artifact Registry, and Secret Manager in Runpod mode.
- Modify: `infra/terraform/outputs.tf` - make Cloud Run outputs safe when disabled and add service account output.
- Create: `infra/terraform/runpod-staging.tfvars.example` - minimum GCP data-layer example.
- Create: `src/merry_runtime/agent_loop.py` - reusable loop runner around existing jobs.
- Modify: `src/merry_runtime/jobs.py` - add `loop` command.
- Modify: `src/merry_runtime/runtime_config.py` - parse loop config and Runpod-safe paths.
- Modify: `tests/test_infra_terraform.py` - lock backend conditionals.
- Create: `tests/test_agent_loop.py` - test loop order, error handling, and max-cycle behavior.
- Modify: `tests/test_supply_chain.py` - lock GHCR build script and Runpod entrypoint safety.
- Create: `tests/test_runpod_docs.py` - ensure docs contain the Runpod stop conditions and canary commands.

---

## Task 1: Document The Revised Runpod-First Staging Flow

**Files:**
- Modify: `README.md`
- Create: `docs/runbooks/runpod-staging.md`
- Modify: `docs/runbooks/staging-canary.md`
- Modify: `docs/runbooks/staging-canary-results.md`
- Create: `tests/test_runpod_docs.py`

- [ ] **Step 1: Write the failing documentation lock test**

```python
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
```

- [ ] **Step 2: Run the failing test**

Run: `python3 -m pytest tests/test_runpod_docs.py -v`

Expected: fail because the Runpod runbook does not exist and README still says Cloud Run-first.

- [ ] **Step 3: Update `README.md` staging section**

Replace the Cloud Run-first staging text with this section:

```markdown
## Runpod-first staging

The default staging runtime is a Runpod Pod that pulls a private GHCR image:

```bash
ghcr.io/$GHCR_OWNER/hermes-merry:staging
```

Runpod runs the long-lived agent loop:

```bash
python3 -m merry_runtime.jobs loop
```

GCP is still used for the minimum data and integration layer: BigQuery, GCS,
Gmail API, Sheets API, and one least-privilege runtime service account. Cloud
Run is optional and remains available only through the `cloud_run` Terraform
backend mode.
```

- [ ] **Step 4: Create `docs/runbooks/runpod-staging.md`**

Use this structure:

```markdown
# Hermes Runpod Staging Runbook

## Backend

Runpod is the primary staging execution backend. GCP is the minimum data layer.

## Required Values

- `GHCR_OWNER`
- `GCP_PROJECT_ID`
- `BIGQUERY_DATASET`
- `RAW_BUCKET`
- `REVIEW_SHEET_ID`
- `AC_ID`
- `GMAIL_LABEL_ID`
- `SLACK_CHANNEL`
- `SLACK_BOT_TOKEN`
- `GOOGLE_APPLICATION_CREDENTIALS_JSON`
- `WIKI_ROOT=/workspace/hermes/wiki`
- `AGENT_LOOP_JOBS=ingest-sources,resolve-entities,score-candidates,sync-review-sheet,calibrate-scores`
- `AGENT_LOOP_INTERVAL_SECONDS=1800`

## Build And Push

```bash
GHCR_OWNER="$GHCR_OWNER" PUSH_IMAGE=1 scripts/build_ghcr_staging.sh
```

## Runpod Pod Command

```bash
python3 -m merry_runtime.jobs loop
```

## Canary

1. Confirm `infra/terraform/runpod-staging.tfvars` points only to staging.
2. Run `tofu -chdir=infra/terraform plan -var-file=runpod-staging.tfvars`.
3. Apply only after the plan has no destroy actions.
4. Start the Runpod Pod with the GHCR image.
5. Verify one loop cycle writes `agent_runs`, uses the staging Sheet, and keeps wiki files under `/workspace/hermes/wiki`.
```

- [ ] **Step 5: Mark `docs/runbooks/staging-canary.md` as optional Cloud Run backend**

Add this paragraph near the top:

```markdown
## Optional Cloud Run backend

This runbook is retained for the optional `cloud_run` execution backend. The
default staging path is now `docs/runbooks/runpod-staging.md`.
```

- [ ] **Step 6: Update canary results**

Add this current status:

```markdown
## Backend decision update

Staging execution moved from Cloud Run-first to Runpod-first. No Cloud Run apply
or job execution is required for the primary staging canary. The remaining
staging blocker is a real `infra/terraform/runpod-staging.tfvars`, GHCR auth,
Runpod Pod secret setup, and one isolated staging Sheet/Gmail label/Slack
channel.
```

- [ ] **Step 7: Verify and commit**

Run: `python3 -m pytest tests/test_runpod_docs.py -v`

Expected: pass.

Commit:

```bash
git add README.md docs/runbooks/runpod-staging.md docs/runbooks/staging-canary.md docs/runbooks/staging-canary-results.md tests/test_runpod_docs.py
git commit -m "docs: define runpod staging flow"
```

---

## Task 2: Add Runpod Minimal GCP Mode To Terraform

**Files:**
- Modify: `infra/terraform/variables.tf`
- Modify: `infra/terraform/main.tf`
- Modify: `infra/terraform/outputs.tf`
- Create: `infra/terraform/runpod-staging.tfvars.example`
- Modify: `tests/test_infra_terraform.py`

- [ ] **Step 1: Write failing Terraform backend tests**

Append to `tests/test_infra_terraform.py`:

```python
def test_terraform_supports_runpod_execution_backend_without_cloud_run_resources() -> None:
    main_tf = (REPO_ROOT / "infra" / "terraform" / "main.tf").read_text()
    variables_tf = (REPO_ROOT / "infra" / "terraform" / "variables.tf").read_text()

    assert 'variable "execution_backend"' in variables_tf
    assert '"runpod"' in variables_tf
    assert '"cloud_run"' in variables_tf
    assert 'var.execution_backend == "cloud_run" ? local.jobs : {}' in main_tf
    assert 'var.execution_backend == "cloud_run" ? local.scheduled_jobs : {}' in main_tf
    assert 'count = var.execution_backend == "cloud_run" && var.create_artifact_registry ? 1 : 0' in main_tf


def test_runpod_staging_tfvars_example_uses_minimal_gcp_layer() -> None:
    tfvars = (REPO_ROOT / "infra" / "terraform" / "runpod-staging.tfvars.example").read_text()

    assert 'execution_backend = "runpod"' in tfvars
    assert 'create_artifact_registry = false' in tfvars
    assert 'wiki_root = "/workspace/hermes/wiki"' in tfvars
    assert "image_uri" not in tfvars
```

- [ ] **Step 2: Run the failing tests**

Run: `python3 -m pytest tests/test_infra_terraform.py -v`

Expected: fail because `execution_backend` and the Runpod tfvars example are absent.

- [ ] **Step 3: Add backend variables**

Add to `infra/terraform/variables.tf`:

```hcl
variable "execution_backend" {
  description = "Execution backend. Use runpod for the primary staging Pod runtime or cloud_run for GCP-native jobs."
  type        = string
  default     = "cloud_run"

  validation {
    condition     = contains(["cloud_run", "runpod"], var.execution_backend)
    error_message = "execution_backend must be cloud_run or runpod."
  }
}

variable "create_artifact_registry" {
  description = "Whether to create the Artifact Registry repository used by the optional Cloud Run backend."
  type        = bool
  default     = true
}
```

- [ ] **Step 4: Make Cloud Run resources conditional**

Change the Cloud Run resource loops in `infra/terraform/main.tf`:

```hcl
resource "google_cloud_run_v2_job" "agent_jobs" {
  for_each = var.execution_backend == "cloud_run" ? local.jobs : {}
```

```hcl
resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  for_each = var.execution_backend == "cloud_run" ? local.scheduled_jobs : {}
```

```hcl
resource "google_cloud_scheduler_job" "agent_schedules" {
  for_each = var.execution_backend == "cloud_run" ? local.scheduled_jobs : {}
```

- [ ] **Step 5: Make Artifact Registry conditional**

Change:

```hcl
resource "google_artifact_registry_repository" "runtime" {
```

to:

```hcl
resource "google_artifact_registry_repository" "runtime" {
  count = var.execution_backend == "cloud_run" && var.create_artifact_registry ? 1 : 0
```

- [ ] **Step 6: Make Secret Manager resources conditional**

For `google_secret_manager_secret.llm_api_key`, `google_secret_manager_secret.slack_bot_token`, and their IAM members, add:

```hcl
count = var.execution_backend == "cloud_run" ? 1 : 0
```

Change references inside secret IAM blocks to index zero:

```hcl
secret_id = google_secret_manager_secret.llm_api_key[0].secret_id
```

```hcl
secret_id = google_secret_manager_secret.slack_bot_token[0].secret_id
```

- [ ] **Step 7: Make outputs safe when Cloud Run is disabled**

Change `infra/terraform/outputs.tf` so Cloud Run outputs evaluate to empty values in Runpod mode:

```hcl
output "cloud_run_jobs" {
  value = sort(keys(google_cloud_run_v2_job.agent_jobs))
}

output "agent_service_account_email" {
  value = google_service_account.agent.email
}
```

- [ ] **Step 8: Add `infra/terraform/runpod-staging.tfvars.example`**

```hcl
execution_backend            = "runpod"
create_artifact_registry     = false
project_id                   = "hermes-staging-example"
region                       = "asia-northeast3"
dataset_id                   = "merry_ac_discovery_staging"
raw_bucket_name              = "hermes-merry-raw-staging-example"
service_account_id           = "hermes-merry-agent-staging"
scheduler_service_account_id = "hermes-merry-scheduler-unused"
review_sheet_id              = "staging-google-sheet-id"
ac_id                        = "ac_climate"
gmail_label_id               = "Label_staging"
slack_channel                = "CSTAGING"
wiki_root                    = "/workspace/hermes/wiki"
enable_ops_alerts            = false
ops_alert_email              = "ops-staging@example.com"
```

- [ ] **Step 9: Verify and commit**

Run:

```bash
python3 -m pytest tests/test_infra_terraform.py -v
tofu -chdir=infra/terraform fmt -check
tofu -chdir=infra/terraform init -backend=false
tofu -chdir=infra/terraform validate
```

Expected: all pass.

Commit:

```bash
git add infra/terraform tests/test_infra_terraform.py
git commit -m "feat: add runpod gcp staging mode"
```

---

## Task 3: Add A Reusable Agent Loop

**Files:**
- Create: `src/merry_runtime/agent_loop.py`
- Modify: `src/merry_runtime/runtime_config.py`
- Create: `tests/test_agent_loop.py`

- [ ] **Step 1: Write failing loop tests**

```python
from __future__ import annotations

from merry_runtime.agent_loop import run_agent_loop


class FakeRuntime:
    pass


def test_agent_loop_runs_configured_jobs_in_order() -> None:
    calls: list[str] = []

    def run_job_fn(job_name, *, runtime, config, sources_json="", ac_id=""):
        calls.append(job_name)
        return {"job_name": job_name, "status": "success"}

    result = run_agent_loop(
        runtime=FakeRuntime(),
        config=object(),
        jobs=("resolve-entities", "score-candidates", "calibrate-scores"),
        interval_seconds=0,
        max_cycles=1,
        run_job_fn=run_job_fn,
        sleep_fn=lambda seconds: None,
    )

    assert calls == ["resolve-entities", "score-candidates", "calibrate-scores"]
    assert result.cycle_count == 1
    assert result.failure_count == 0


def test_agent_loop_records_failures_and_continues_to_next_job() -> None:
    calls: list[str] = []

    def run_job_fn(job_name, *, runtime, config, sources_json="", ac_id=""):
        calls.append(job_name)
        if job_name == "score-candidates":
            raise RuntimeError("score failed")
        return {"job_name": job_name, "status": "success"}

    result = run_agent_loop(
        runtime=FakeRuntime(),
        config=object(),
        jobs=("resolve-entities", "score-candidates", "calibrate-scores"),
        interval_seconds=0,
        max_cycles=1,
        run_job_fn=run_job_fn,
        sleep_fn=lambda seconds: None,
    )

    assert calls == ["resolve-entities", "score-candidates", "calibrate-scores"]
    assert result.failure_count == 1
    assert result.results[1].status == "failed"
    assert "RuntimeError: score failed" in result.results[1].error_message
```

- [ ] **Step 2: Run the failing tests**

Run: `python3 -m pytest tests/test_agent_loop.py -v`

Expected: fail with `ModuleNotFoundError: No module named 'merry_runtime.agent_loop'`.

- [ ] **Step 3: Implement `src/merry_runtime/agent_loop.py`**

```python
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from merry_runtime.job_runner import run_job


@dataclass(frozen=True, slots=True)
class LoopJobResult:
    job_name: str
    status: str
    payload: dict[str, object] = field(default_factory=dict)
    error_message: str = ""


@dataclass(frozen=True, slots=True)
class LoopResult:
    cycle_count: int
    success_count: int
    failure_count: int
    results: tuple[LoopJobResult, ...]


def run_agent_loop(
    *,
    runtime: Any,
    config: Any,
    jobs: Iterable[str],
    interval_seconds: int,
    max_cycles: int,
    run_job_fn: Callable[..., dict[str, object]] = run_job,
    sleep_fn: Callable[[int], None],
) -> LoopResult:
    cycle_count = 0
    results: list[LoopJobResult] = []
    job_names = tuple(jobs)
    while max_cycles <= 0 or cycle_count < max_cycles:
        cycle_count += 1
        for job_name in job_names:
            try:
                payload = run_job_fn(job_name, runtime=runtime, config=config)
            except Exception as exc:
                results.append(
                    LoopJobResult(
                        job_name=job_name,
                        status="failed",
                        error_message=f"{type(exc).__name__}: {exc}"[:1000],
                    )
                )
                continue
            results.append(LoopJobResult(job_name=job_name, status="success", payload=payload))
        if max_cycles > 0 and cycle_count >= max_cycles:
            break
        sleep_fn(interval_seconds)
    success_count = sum(1 for result in results if result.status == "success")
    failure_count = sum(1 for result in results if result.status == "failed")
    return LoopResult(
        cycle_count=cycle_count,
        success_count=success_count,
        failure_count=failure_count,
        results=tuple(results),
    )
```

- [ ] **Step 4: Verify and commit**

Run: `python3 -m pytest tests/test_agent_loop.py -v`

Expected: pass.

Commit:

```bash
git add src/merry_runtime/agent_loop.py tests/test_agent_loop.py
git commit -m "feat: add runpod agent loop runner"
```

---

## Task 4: Wire The Loop Into The Job CLI

**Files:**
- Modify: `src/merry_runtime/jobs.py`
- Modify: `src/merry_runtime/runtime_config.py`
- Modify: `tests/test_agent_loop.py`

- [ ] **Step 1: Add failing CLI config tests**

Append to `tests/test_agent_loop.py`:

```python
from merry_runtime.runtime_config import RuntimeConfig


def test_runtime_config_reads_agent_loop_environment(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LOOP_JOBS", "resolve-entities,score-candidates")
    monkeypatch.setenv("AGENT_LOOP_INTERVAL_SECONDS", "90")
    monkeypatch.setenv("AGENT_LOOP_MAX_CYCLES", "2")

    config = RuntimeConfig.from_env()

    assert config.agent_loop_jobs == ("resolve-entities", "score-candidates")
    assert config.agent_loop_interval_seconds == 90
    assert config.agent_loop_max_cycles == 2


def test_runtime_config_defaults_runpod_wiki_root(monkeypatch) -> None:
    monkeypatch.setenv("WIKI_ROOT", "/workspace/hermes/wiki")

    config = RuntimeConfig.from_env()

    assert str(config.wiki_root) == "/workspace/hermes/wiki"
```

- [ ] **Step 2: Run the failing tests**

Run: `python3 -m pytest tests/test_agent_loop.py -v`

Expected: fail because `RuntimeConfig` lacks loop fields.

- [ ] **Step 3: Add loop fields to `RuntimeConfig`**

Add fields:

```python
agent_loop_jobs: tuple[str, ...] = (
    "ingest-sources",
    "resolve-entities",
    "score-candidates",
    "sync-review-sheet",
    "calibrate-scores",
)
agent_loop_interval_seconds: int = 1800
agent_loop_max_cycles: int = 0
```

Add parsing helpers:

```python
def _parse_jobs(value: str) -> tuple[str, ...]:
    if not value.strip():
        return (
            "ingest-sources",
            "resolve-entities",
            "score-candidates",
            "sync-review-sheet",
            "calibrate-scores",
        )
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parse_int(value: str, *, default: int) -> int:
    if not value.strip():
        return default
    return int(value)
```

Use them in `from_env`:

```python
agent_loop_jobs=_parse_jobs(os.getenv("AGENT_LOOP_JOBS", "")),
agent_loop_interval_seconds=_parse_int(os.getenv("AGENT_LOOP_INTERVAL_SECONDS", ""), default=1800),
agent_loop_max_cycles=_parse_int(os.getenv("AGENT_LOOP_MAX_CYCLES", ""), default=0),
```

- [ ] **Step 4: Add `loop` subcommand to `src/merry_runtime/jobs.py`**

Add parser:

```python
loop_parser = subparsers.add_parser("loop")
loop_parser.add_argument("--max-cycles", type=int, default=None)
loop_parser.add_argument("--interval-seconds", type=int, default=None)
```

Add command handling:

```python
if args.command == "loop":
    import time
    from dataclasses import asdict

    from merry_runtime.agent_loop import run_agent_loop

    config = RuntimeConfig.from_env()
    runtime = build_runtime(config)
    result = run_agent_loop(
        runtime=runtime,
        config=config,
        jobs=config.agent_loop_jobs,
        interval_seconds=args.interval_seconds
        if args.interval_seconds is not None
        else config.agent_loop_interval_seconds,
        max_cycles=args.max_cycles
        if args.max_cycles is not None
        else config.agent_loop_max_cycles,
        sleep_fn=time.sleep,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
    return 0 if result.failure_count == 0 else 1
```

- [ ] **Step 5: Verify with local no-network tests**

Run: `python3 -m pytest tests/test_agent_loop.py -v`

Expected: pass.

Commit:

```bash
git add src/merry_runtime/jobs.py src/merry_runtime/runtime_config.py tests/test_agent_loop.py
git commit -m "feat: expose runpod agent loop cli"
```

---

## Task 5: Add GHCR Build And Runpod Credential Bootstrap

**Files:**
- Modify: `Dockerfile`
- Create: `scripts/build_ghcr_staging.sh`
- Create: `scripts/runpod_entrypoint.sh`
- Create: `configs/runpod.env.example`
- Modify: `tests/test_supply_chain.py`

- [ ] **Step 1: Write failing supply-chain tests**

Append to `tests/test_supply_chain.py`:

```python
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
```

- [ ] **Step 2: Run the failing tests**

Run: `python3 -m pytest tests/test_supply_chain.py -v`

Expected: fail because the scripts and Dockerfile entrypoint are absent.

- [ ] **Step 3: Create `scripts/runpod_entrypoint.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

credential_file=""

cleanup() {
  if [ -n "$credential_file" ] && [ -f "$credential_file" ]; then
    rm -f "$credential_file"
  fi
}
trap cleanup EXIT

if [ -n "${GOOGLE_APPLICATION_CREDENTIALS_JSON:-}" ]; then
  credential_file="$(mktemp /tmp/hermes-gcp-XXXXXX.json)"
  chmod 600 "$credential_file"
  printf '%s' "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > "$credential_file"
  export GOOGLE_APPLICATION_CREDENTIALS="$credential_file"
fi

exec "$@"
```

- [ ] **Step 4: Create `scripts/build_ghcr_staging.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

: "${GHCR_OWNER:?Set GHCR_OWNER to the GitHub user or org that owns the package.}"

IMAGE_TAG="${IMAGE_TAG:-staging}"
IMAGE_URI="ghcr.io/${GHCR_OWNER}/hermes-merry:${IMAGE_TAG}"

docker buildx inspect >/dev/null

if [ "${PUSH_IMAGE:-0}" = "1" ]; then
  docker buildx build --platform linux/amd64 -t "$IMAGE_URI" --push .
else
  docker buildx build --platform linux/amd64 -t "$IMAGE_URI" --load .
fi

printf '%s\n' "$IMAGE_URI"
```

- [ ] **Step 5: Update `Dockerfile`**

Add before `USER hermes`:

```dockerfile
COPY scripts/runpod_entrypoint.sh /usr/local/bin/runpod-entrypoint
RUN chmod 755 /usr/local/bin/runpod-entrypoint
```

Replace the entrypoint with:

```dockerfile
ENTRYPOINT ["runpod-entrypoint", "python3", "-m", "merry_runtime.jobs"]
```

- [ ] **Step 6: Create `configs/runpod.env.example`**

```bash
GCP_PROJECT_ID=hermes-staging-example
BIGQUERY_DATASET=merry_ac_discovery_staging
RAW_BUCKET=hermes-merry-raw-staging-example
REVIEW_SHEET_ID=staging-google-sheet-id
AC_ID=ac_climate
GMAIL_LABEL_ID=Label_staging
SLACK_CHANNEL=CSTAGING
SLACK_BOT_TOKEN=xoxb-staging-token-from-runpod-secret
GOOGLE_APPLICATION_CREDENTIALS_JSON={"type":"service_account","project_id":"hermes-staging-example"}
WIKI_ROOT=/workspace/hermes/wiki
AGENT_LOOP_JOBS=ingest-sources,resolve-entities,score-candidates,sync-review-sheet,calibrate-scores
AGENT_LOOP_INTERVAL_SECONDS=1800
AGENT_LOOP_MAX_CYCLES=0
```

- [ ] **Step 7: Verify and commit**

Run:

```bash
chmod 755 scripts/build_ghcr_staging.sh scripts/runpod_entrypoint.sh
python3 -m pytest tests/test_supply_chain.py -v
docker build --platform linux/amd64 -t hermes-merry:runpod-staging .
docker run --rm --platform linux/amd64 hermes-merry:runpod-staging validate-hermes-profile
```

Expected: tests pass and Docker smoke test prints `Hermes profile lockdown: OK`.

Commit:

```bash
git add Dockerfile scripts/build_ghcr_staging.sh scripts/runpod_entrypoint.sh configs/runpod.env.example tests/test_supply_chain.py
git commit -m "feat: add ghcr runpod image packaging"
```

---

## Task 6: Add Runpod Canary Execution Evidence

**Files:**
- Modify: `docs/runbooks/runpod-staging.md`
- Create: `docs/runbooks/runpod-canary-results.md`
- Create: `tests/test_runpod_docs.py`

- [ ] **Step 1: Extend docs test for evidence fields**

Append to `tests/test_runpod_docs.py`:

```python
def test_runpod_canary_results_template_captures_required_evidence() -> None:
    template = (REPO_ROOT / "docs" / "runbooks" / "runpod-canary-results.md").read_text()

    for required in (
        "GHCR image digest",
        "Runpod Pod ID",
        "BigQuery agent_runs row",
        "GCS raw object",
        "Sheet tab",
        "Slack message timestamp",
        "Wiki path",
        "Rollback command",
    ):
        assert required in template
```

- [ ] **Step 2: Run the failing docs test**

Run: `python3 -m pytest tests/test_runpod_docs.py -v`

Expected: fail because canary results template is absent.

- [ ] **Step 3: Create `docs/runbooks/runpod-canary-results.md`**

```markdown
# Hermes Runpod Canary Results

## Run

- Date:
- Operator:
- GHCR image digest:
- Runpod Pod ID:
- Runpod image:
- GCP project:
- BigQuery dataset:
- GCS raw bucket:
- Sheet tab:
- Slack channel:
- Wiki path:

## Evidence

- BigQuery agent_runs row:
- GCS raw object:
- Sheet row count before:
- Sheet row count after:
- Slack message timestamp:
- Wiki page path:

## Result

- Canary status:
- Failed job count:
- Human review required:

## Rollback command

```bash
stop the Runpod Pod from the Runpod console
```
```

- [ ] **Step 4: Add canary command sequence to runbook**

Add:

```markdown
## One-cycle Canary Command

Set `AGENT_LOOP_MAX_CYCLES=1` for the first Runpod run. The Pod command remains:

```bash
python3 -m merry_runtime.jobs loop
```

After the first cycle, confirm:

```bash
bq query --use_legacy_sql=false \
  'select job_name, status, started_at, finished_at from `PROJECT.DATASET.agent_runs` order by started_at desc limit 10'
```
```

- [ ] **Step 5: Verify and commit**

Run: `python3 -m pytest tests/test_runpod_docs.py -v`

Expected: pass.

Commit:

```bash
git add docs/runbooks/runpod-staging.md docs/runbooks/runpod-canary-results.md tests/test_runpod_docs.py
git commit -m "docs: add runpod canary evidence template"
```

---

## Task 7: Push The GHCR Image

**Files:**
- No repo file edits expected after Task 5.

- [ ] **Step 1: Confirm GHCR owner and Docker auth**

Run:

```bash
test -n "$GHCR_OWNER"
docker info
```

Expected: both commands exit zero.

- [ ] **Step 2: Login to GHCR**

Run:

```bash
printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "$GITHUB_USER" --password-stdin
```

Expected: Docker prints `Login Succeeded`.

- [ ] **Step 3: Build and push**

Run:

```bash
GHCR_OWNER="$GHCR_OWNER" PUSH_IMAGE=1 scripts/build_ghcr_staging.sh
```

Expected: command prints `ghcr.io/$GHCR_OWNER/hermes-merry:staging`.

- [ ] **Step 4: Capture immutable digest**

Run:

```bash
docker buildx imagetools inspect "ghcr.io/$GHCR_OWNER/hermes-merry:staging"
```

Expected: output includes an image digest beginning with `sha256:`.

- [ ] **Step 5: Record evidence**

Update `docs/runbooks/runpod-canary-results.md` with:

```markdown
- GHCR image digest: sha256 value from `docker buildx imagetools inspect`
- Runpod image: `ghcr.io/$GHCR_OWNER/hermes-merry:staging`
```

Commit:

```bash
git add docs/runbooks/runpod-canary-results.md
git commit -m "docs: record runpod image digest"
```

---

## Task 8: Apply Minimal GCP Staging Layer

**Files:**
- Optional local-only file: `infra/terraform/runpod-staging.tfvars`
- Modify after execution: `docs/runbooks/runpod-canary-results.md`

- [ ] **Step 1: Create local tfvars from example**

Run:

```bash
cp infra/terraform/runpod-staging.tfvars.example infra/terraform/runpod-staging.tfvars
```

Edit the local file with real staging IDs. This file must stay uncommitted.

- [ ] **Step 2: Confirm the active project**

Run:

```bash
ACTIVE_PROJECT="$(gcloud config get-value project)"
CONFIG_PROJECT="$(sed -n 's/^project_id *= *"\\(.*\\)"/\\1/p' infra/terraform/runpod-staging.tfvars)"
test "$ACTIVE_PROJECT" = "$CONFIG_PROJECT"
```

Expected: exit zero.

- [ ] **Step 3: Plan**

Run:

```bash
tofu -chdir=infra/terraform plan -var-file=runpod-staging.tfvars
```

Expected:

- Creates or updates BigQuery dataset/tables.
- Creates or updates GCS raw bucket.
- Creates or updates Hermes runtime service account.
- Does not create Cloud Run jobs.
- Does not create Cloud Scheduler jobs.
- Does not create Artifact Registry.
- Does not create Secret Manager secrets.
- Has no destroy actions.

- [ ] **Step 4: Apply**

Run:

```bash
tofu -chdir=infra/terraform apply -var-file=runpod-staging.tfvars
```

Expected: apply completes with no destroy actions.

- [ ] **Step 5: Create service account key outside Terraform**

Run:

```bash
AGENT_SA="$(tofu -chdir=infra/terraform output -raw agent_service_account_email)"
gcloud iam service-accounts keys create /tmp/hermes-runpod-sa.json --iam-account "$AGENT_SA"
python3 -m json.tool /tmp/hermes-runpod-sa.json >/tmp/hermes-runpod-sa.min.json
```

Expected: `/tmp/hermes-runpod-sa.min.json` exists and is not under the repo.

- [ ] **Step 6: Store JSON in Runpod secret and delete local key file**

Store the compact JSON content from `/tmp/hermes-runpod-sa.min.json` in Runpod secret `GOOGLE_APPLICATION_CREDENTIALS_JSON`.

Then run:

```bash
rm -f /tmp/hermes-runpod-sa.json /tmp/hermes-runpod-sa.min.json
```

Expected: local key files are deleted.

- [ ] **Step 7: Record GCP evidence**

Update `docs/runbooks/runpod-canary-results.md` with:

```markdown
- GCP project: project ID from runpod-staging.tfvars
- BigQuery dataset: dataset ID from runpod-staging.tfvars
- GCS raw bucket: bucket name from runpod-staging.tfvars
```

Commit:

```bash
git add docs/runbooks/runpod-canary-results.md
git commit -m "docs: record runpod gcp staging layer"
```

---

## Task 9: Start Runpod Pod And Run One Canary Cycle

**Files:**
- Modify after execution: `docs/runbooks/runpod-canary-results.md`

- [ ] **Step 1: Configure Runpod Pod**

Use these values:

```text
Image: ghcr.io/$GHCR_OWNER/hermes-merry:staging
Command: python3 -m merry_runtime.jobs loop
Volume path: /workspace
WIKI_ROOT: /workspace/hermes/wiki
AGENT_LOOP_MAX_CYCLES: 1
AGENT_LOOP_INTERVAL_SECONDS: 1800
```

Configure private registry auth in Runpod for GHCR before starting the Pod.

- [ ] **Step 2: Add Runpod secrets**

Set these as Runpod secrets or environment variables:

```text
GCP_PROJECT_ID
BIGQUERY_DATASET
RAW_BUCKET
REVIEW_SHEET_ID
AC_ID
GMAIL_LABEL_ID
SLACK_CHANNEL
SLACK_BOT_TOKEN
GOOGLE_APPLICATION_CREDENTIALS_JSON
WIKI_ROOT=/workspace/hermes/wiki
AGENT_LOOP_JOBS=ingest-sources,resolve-entities,score-candidates,sync-review-sheet,calibrate-scores
AGENT_LOOP_MAX_CYCLES=1
```

- [ ] **Step 3: Start Pod**

Expected container log:

```text
"cycle_count": 1
```

If failure count is nonzero, inspect job payload errors before increasing loop duration.

- [ ] **Step 4: Verify BigQuery**

Run from local machine:

```bash
bq query --use_legacy_sql=false \
  'select job_name, status, started_at, finished_at, error_message from `PROJECT.DATASET.agent_runs` order by started_at desc limit 20'
```

Expected: one or more staging `agent_runs` rows. For configured jobs with no Gmail messages, failures must be explainable and bounded.

- [ ] **Step 5: Verify Sheet and Slack**

Check:

```text
Sheet tab: AC_ID tab has queue rows or remains unchanged with no source input.
Slack: no production channel received messages.
```

- [ ] **Step 6: Verify wiki persistence**

Inside Runpod shell:

```bash
test -d /workspace/hermes/wiki
find /workspace/hermes/wiki -maxdepth 2 -type f | sort | head
```

Expected: wiki directory exists under `/workspace/hermes/wiki`.

- [ ] **Step 7: Record canary evidence**

Update `docs/runbooks/runpod-canary-results.md` with:

```markdown
- Runpod Pod ID:
- BigQuery agent_runs row:
- Sheet tab:
- Slack message timestamp:
- Wiki path: `/workspace/hermes/wiki`
- Canary status:
```

Commit:

```bash
git add docs/runbooks/runpod-canary-results.md
git commit -m "docs: record runpod canary evidence"
```

---

## Task 10: Switch From One-Cycle Canary To Always-On Staging

**Files:**
- Modify after execution: `docs/runbooks/runpod-canary-results.md`

- [ ] **Step 1: Remove one-cycle limit in Runpod**

Set:

```text
AGENT_LOOP_MAX_CYCLES=0
AGENT_LOOP_INTERVAL_SECONDS=1800
```

Expected: the loop runs until the Pod is stopped.

- [ ] **Step 2: Restart Pod**

Expected: Pod restarts and logs periodic loop output.

- [ ] **Step 3: Observe two cycles**

Wait for two intervals or temporarily set:

```text
AGENT_LOOP_INTERVAL_SECONDS=300
```

Expected: at least two loop cycles run without unbounded failures.

- [ ] **Step 4: Restore normal interval**

Set:

```text
AGENT_LOOP_INTERVAL_SECONDS=1800
```

- [ ] **Step 5: Final verification**

Run:

```bash
make verify
git diff --check HEAD
git status --short --branch
```

Expected:

- `make verify` passes.
- `git diff --check HEAD` exits zero.
- `git status --short --branch` shows only expected local `runpod-staging.tfvars` ignored or absent.

Commit any documentation evidence changes:

```bash
git add docs/runbooks/runpod-canary-results.md
git commit -m "docs: finalize runpod staging status"
```

---

## Risks And Controls

| Risk | Control |
| --- | --- |
| Runpod Pod deletes non-volume data | Keep wiki under `/workspace/hermes/wiki`; treat everything else as disposable. |
| Service account key leaks | Never create key through Terraform; store only in Runpod secret; materialize to `/tmp` at runtime; delete local temp files. |
| Agent touches production resources | Stop conditions require staging Sheet, label, Slack channel, dataset, and bucket. |
| GHCR private image pull fails | Configure Runpod registry auth before starting Pod; verify image digest with `docker buildx imagetools inspect`. |
| Loop repeats a failing job forever | First canary uses `AGENT_LOOP_MAX_CYCLES=1`; always-on starts only after one-cycle evidence is reviewed. |
| Cloud Run Terraform references break when disabled | Tests require conditional `for_each` and safe outputs; `tofu validate` must pass in Runpod mode. |
| Gmail/Sheets auth fails on Runpod | Runpod secret injects ADC JSON; first canary verifies BigQuery, Gmail, Sheets, and Slack separately. |

## Self-Review

- Spec coverage: The plan covers GHCR, Runpod Pod runtime, minimum GCP Terraform mode, credential handling, persistent wiki path, one-cycle canary, and always-on staging.
- Placeholder scan: The plan uses environment variables for operator-provided secrets and avoids committed placeholder files for real credentials.
- Type consistency: The loop API uses `LoopResult`, `LoopJobResult`, and existing `run_job` signatures.
- Safety consistency: No task writes GCP private keys into Terraform state or the repo. Cloud Run is optional and disabled by `execution_backend = "runpod"`.
