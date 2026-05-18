# Hermes Remaining Risk Burn-Down Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the current Hermes Merry MVP from a passing skeleton into a staging-safe, data-safe discovery runtime.

**Architecture:** Keep the current frontless GCP architecture: Cloud Run Jobs, BigQuery, GCS, Google Sheets, Gmail, Slack, and the SQLite-backed Obsidian wiki. Burn down the remaining production risks in dependency order: atomic data writes, non-destructive entity resolution, supply-chain reproducibility, least-privilege raw storage, observability, staging execution, and product-loop expansion.

**Tech Stack:** Python 3.12+, pytest, OpenTofu, Google BigQuery, GCS, Cloud Run Jobs, Cloud Scheduler, Secret Manager, Google Sheets API, Gmail API, Slack Web API.

---

## Current Baseline

Fresh verification before this plan:

- `make verify` passes.
- `pytest`: 82 tests passed.
- Hermes production profile lockdown passes.
- MCP tool list is restricted to domain tools.
- `tofu fmt -check`, `tofu init -backend=false`, and `tofu validate` pass.

Recently closed risks:

- Sheets column/header mismatch.
- Sheets formula injection.
- BigQuery default dataset for reads.
- Re-score overwriting human card status.
- Wiki path traversal.
- MCP schema-shaped but not schema-enforced payloads.
- Missing Cloud Run env/secrets.
- Runtime/Scheduler service-account separation.
- Project-level BigQuery data editor IAM.
- Container root execution.

Remaining risks that still block production trust:

| Risk | Severity | Why It Matters | Primary Burn-Down Task |
|---|---:|---|---|
| BigQuery upsert is delete-then-insert | Critical | Insert failure or concurrency can erase structured data | Task 1 |
| `resolve-entities` is a stub | Critical | Duplicate/ambiguous candidates remain unhandled | Task 2 |
| Dependency/image builds are not pinned | High | Cloud Run rebuilds can pull new unreviewed code | Task 3 |
| Raw GCS bucket still uses object admin | High | Runtime can overwrite/delete raw evidence | Task 4 |
| Job failures are not operationally visible enough | High | Frontless system can silently stop working | Task 5 |
| No real staging cycle has run | High | IaC and adapters are validated syntactically, not operationally | Task 6 |
| AC hypothesis ingestion is missing | Medium | Scoring cannot adapt to fund/program context beyond seeded profiles | Task 7 |
| Review-feedback calibration is not implemented | Medium | Human decisions are stored but do not update model coefficients | Task 8 |
| 1,000-candidate acquisition is not implemented | Medium | The system cannot prove sourcing throughput | Task 9 |

## Execution Strategy

Do not merge large subsystems together. Each task below must land in its own commit after `make verify`.

Recommended execution order:

1. Task 1, BigQuery atomic writes.
2. Task 2, non-destructive probabilistic resolution events.
3. Task 3 and Task 4, security hardening.
4. Task 5, observability.
5. Task 6, staging canary cycle.
6. Task 7, Task 8, and Task 9, product-loop expansion.

Stop gate:

- If any task requires destructive merge/delete of real startup data, pause and add a human review state instead.
- If any Terraform change grants project-wide editor/admin roles, pause and redesign the IAM boundary.
- If any staging run touches production Sheet, Gmail label, Slack channel, bucket, or BigQuery dataset, pause and create isolated staging resources first.

## File Ownership Map

- `src/merry_runtime/adapters/bigquery.py`: BigQuery adapter behavior.
- `src/merry_runtime/adapters/bigquery_merge.py`: BigQuery MERGE SQL and schema conversion helpers.
- `src/merry_runtime/schema.py`: BigQuery schema source of truth.
- `src/merry_runtime/pipelines/resolve_entities.py`: Entity-resolution job pipeline.
- `src/merry_runtime/job_runner.py`: Cloud Run job dispatch.
- `src/merry_runtime/jobs.py`: CLI error handling and structured job result output.
- `src/merry_runtime/adapters/gcs.py`: Immutable raw evidence writes.
- `infra/terraform/main.tf`: GCP resources, IAM, scheduler, monitoring.
- `infra/terraform/variables.tf`: Deployment variables.
- `infra/terraform/outputs.tf`: Deployment outputs.
- `Dockerfile`: Runtime image pinning and installation behavior.
- `pyproject.toml`, `requirements.lock`, `.github/workflows/ci.yml`: Dependency lock and audit checks.
- `docs/runbooks/staging-canary.md`: Manual staging execution runbook.
- `docs/superpowers/plans/2026-05-18-hermes-merry-ac-discovery-cto-roadmap.md`: CTO roadmap status.

---

## Task 1: Replace BigQuery Delete-Then-Insert With Target-Atomic MERGE

**Risk Burned Down:** Structured rows can be lost if `insert_rows_json` fails after delete, or if concurrent jobs overlap.

**Design Decision:** Use a staging table plus one target-table `MERGE`. Loading staging rows is separate, but the target mutation is atomic. If staging load fails, the target is untouched.

**Files:**
- Create: `src/merry_runtime/adapters/bigquery_merge.py`
- Modify: `src/merry_runtime/adapters/bigquery.py`
- Modify: `src/merry_runtime/schema.py`
- Test: `tests/test_bigquery_merge.py`
- Test: `tests/test_adapter_contracts.py`

- [ ] **Step 1: Write failing test for MERGE SQL generation**

Create `tests/test_bigquery_merge.py`:

```python
from merry_runtime.adapters.bigquery_merge import build_merge_sql


def test_build_merge_sql_updates_existing_rows_and_inserts_new_rows() -> None:
    sql = build_merge_sql(
        target_table_id="project.dataset.mother_entities",
        staging_table_id="project.dataset._staging_mother_entities_run1",
        field_names=("entity_id", "name", "normalized_name", "last_seen_at"),
        key_fields=("entity_id",),
    )

    assert "MERGE `project.dataset.mother_entities` T" in sql
    assert "USING `project.dataset._staging_mother_entities_run1` S" in sql
    assert "ON T.entity_id = S.entity_id" in sql
    assert "WHEN MATCHED THEN UPDATE SET" in sql
    assert "name = S.name" in sql
    assert "normalized_name = S.normalized_name" in sql
    assert "last_seen_at = S.last_seen_at" in sql
    assert "WHEN NOT MATCHED THEN INSERT" in sql
    assert "`entity_id`, `name`, `normalized_name`, `last_seen_at`" in sql
```

Run:

```bash
python3 -m pytest tests/test_bigquery_merge.py::test_build_merge_sql_updates_existing_rows_and_inserts_new_rows
```

Expected: fails because `merry_runtime.adapters.bigquery_merge` does not exist.

- [ ] **Step 2: Implement MERGE SQL helper**

Create `src/merry_runtime/adapters/bigquery_merge.py` with:

```python
from __future__ import annotations


def build_merge_sql(
    *,
    target_table_id: str,
    staging_table_id: str,
    field_names: tuple[str, ...],
    key_fields: tuple[str, ...],
) -> str:
    if not key_fields:
        raise ValueError("key_fields must not be empty")
    if not field_names:
        raise ValueError("field_names must not be empty")
    missing_keys = set(key_fields) - set(field_names)
    if missing_keys:
        raise ValueError(f"key_fields must exist in field_names: {sorted(missing_keys)}")

    on_clause = " AND ".join(f"T.{field} = S.{field}" for field in key_fields)
    update_fields = tuple(field for field in field_names if field not in key_fields)
    update_clause = ", ".join(f"{field} = S.{field}" for field in update_fields) or ", ".join(
        f"{field} = S.{field}" for field in key_fields
    )
    insert_columns = ", ".join(f"`{field}`" for field in field_names)
    insert_values = ", ".join(f"S.{field}" for field in field_names)

    return f"""
MERGE `{target_table_id}` T
USING `{staging_table_id}` S
ON {on_clause}
WHEN MATCHED THEN UPDATE SET {update_clause}
WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})
""".strip()
```

Run:

```bash
python3 -m pytest tests/test_bigquery_merge.py
```

Expected: pass.

- [ ] **Step 3: Write failing adapter test for staging-load then MERGE**

Extend `tests/test_adapter_contracts.py` with a fake BigQuery client that records:

- `load_table_from_json` calls.
- `query` SQL.
- `delete_table` calls.

Add:

```python
def test_bigquery_upsert_loads_staging_table_and_merges_without_target_delete() -> None:
    client = FakeBigQueryClient()
    store = BigQueryStructuredStore(client=client, project_id="p", dataset_id="d")

    count = store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": "ent_1",
                "entity_type": "startup",
                "name": "Merry AI",
                "normalized_name": "merryai",
                "first_seen_at": "2026-05-18T00:00:00+00:00",
                "last_seen_at": "2026-05-18T00:00:00+00:00",
            }
        ],
        key_fields=("entity_id",),
    )

    assert count == 1
    assert client.loaded_rows[0][0].startswith("p.d._staging_mother_entities_")
    assert "MERGE `p.d.mother_entities`" in client.queries[-1][0]
    assert "DELETE FROM `p.d.mother_entities`" not in " ".join(sql for sql, _metadata in client.queries)
    assert client.deleted_tables[0].startswith("p.d._staging_mother_entities_")
```

Run:

```bash
python3 -m pytest tests/test_adapter_contracts.py::test_bigquery_upsert_loads_staging_table_and_merges_without_target_delete
```

Expected: fails because current adapter uses target `DELETE`.

- [ ] **Step 4: Implement staging-load MERGE in adapter**

Modify `src/merry_runtime/adapters/bigquery.py`:

- Use `BIGQUERY_TABLES[table]` to derive schema and field order.
- Build a staging table id under the same dataset.
- Call `client.load_table_from_json(rows, staging_table_id, job_config=...)`.
- Call one `MERGE` query.
- Call `client.delete_table(staging_table_id, not_found_ok=True)` in `finally`.
- Preserve fallback behavior for fake clients by keeping job config objects simple when Google modules are unavailable.

Run:

```bash
python3 -m pytest tests/test_bigquery_merge.py tests/test_adapter_contracts.py
```

Expected: pass.

- [ ] **Step 5: Run full verification and commit**

Run:

```bash
make verify
git diff --check
```

Expected:

- All tests pass.
- No whitespace errors.
- `tofu validate` remains valid.

Commit:

```bash
git add src/merry_runtime/adapters/bigquery.py src/merry_runtime/adapters/bigquery_merge.py src/merry_runtime/schema.py tests/test_bigquery_merge.py tests/test_adapter_contracts.py
git commit -m "fix: make bigquery upserts target-atomic"
```

---

## Task 2: Wire Non-Destructive Probabilistic Entity Resolution Job

**Risk Burned Down:** `resolve-entities` currently records a run but does not persist duplicate/ambiguous resolution outcomes.

**Design Decision:** Do not destructively merge entities in this task. Persist resolution events and queue ambiguous/high-probability matches for human review. A separate reviewed-merge task can apply confirmed merges after evidence exists.

**Files:**
- Modify: `src/merry_runtime/schema.py`
- Modify: `infra/terraform/main.tf`
- Create: `src/merry_runtime/pipelines/resolve_entities.py`
- Modify: `src/merry_runtime/job_runner.py`
- Test: `tests/integration/test_resolve_entities.py`
- Test: `tests/test_bigquery_schema.py`
- Test: `tests/test_job_runner.py`

- [ ] **Step 1: Add failing schema test for `entity_resolution_events`**

Add to `tests/test_bigquery_schema.py`:

```python
def test_entity_resolution_events_schema_captures_probabilistic_decisions() -> None:
    fields = {field["name"] for field in BIGQUERY_TABLES["entity_resolution_events"]}

    assert {
        "event_id",
        "candidate_entity_id",
        "matched_entity_id",
        "action",
        "probability",
        "features_json",
        "rationale",
        "status",
        "created_at",
    }.issubset(fields)
```

Run:

```bash
python3 -m pytest tests/test_bigquery_schema.py::test_entity_resolution_events_schema_captures_probabilistic_decisions
```

Expected: fails because table does not exist.

- [ ] **Step 2: Add schema and Terraform table**

Add `entity_resolution_events` to `BIGQUERY_TABLES` in `src/merry_runtime/schema.py`:

```python
"entity_resolution_events": [
    _field("event_id", "STRING", "REQUIRED"),
    _field("candidate_entity_id", "STRING", "REQUIRED"),
    _field("matched_entity_id", "STRING"),
    _field("action", "STRING", "REQUIRED"),
    _field("probability", "FLOAT", "REQUIRED"),
    _field("features_json", "STRING", "REQUIRED"),
    _field("rationale", "STRING", "REQUIRED"),
    _field("status", "STRING", "REQUIRED"),
    _field("created_at", "TIMESTAMP", "REQUIRED"),
],
```

Terraform reads from local schemas only if manually mirrored, so add the same table block to `infra/terraform/main.tf` local `table_schemas`.

Run:

```bash
python3 -m pytest tests/test_bigquery_schema.py
```

Expected: pass.

- [ ] **Step 3: Write failing pipeline tests**

Create `tests/integration/test_resolve_entities.py`:

```python
from merry_runtime.adapters.fakes import FakeReviewQueue, FakeStructuredStore
from merry_runtime.pipelines.resolve_entities import resolve_entities


def test_resolve_entities_persists_high_probability_merge_candidate_without_deleting_rows() -> None:
    store = FakeStructuredStore()
    store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": "ent_existing",
                "entity_type": "startup",
                "name": "CareFarm Carbon",
                "normalized_name": "carefarmcarbon",
                "region": "Jeonbuk",
                "industry": "AgriTech",
                "homepage": "https://carefarm.example",
            },
            {
                "entity_id": "ent_candidate",
                "entity_type": "startup",
                "name": "CareFarm",
                "normalized_name": "carefarm",
                "region": "Jeonbuk",
                "industry": "AgriTech",
                "homepage": "https://carefarm.example",
            },
        ],
        key_fields=("entity_id",),
    )
    queue = FakeReviewQueue()

    result = resolve_entities(structured_store=store, review_queue=queue, run_id="run_resolve_test")

    assert result.event_count == 1
    event = store.tables["entity_resolution_events"][0]
    assert event["candidate_entity_id"] == "ent_candidate"
    assert event["matched_entity_id"] == "ent_existing"
    assert event["action"] == "merge_candidate"
    assert event["status"] == "pending_review"
    assert store.tables["mother_entities"][0]["entity_id"] == "ent_existing"
    assert store.tables["mother_entities"][1]["entity_id"] == "ent_candidate"
    assert queue.published["entity_resolution"][0]["candidate_entity_id"] == "ent_candidate"
```

Run:

```bash
python3 -m pytest tests/integration/test_resolve_entities.py
```

Expected: fails because pipeline does not exist.

- [ ] **Step 4: Implement pipeline**

Create `src/merry_runtime/pipelines/resolve_entities.py`:

- Query `mother_entities`.
- Convert rows into `EntityObservation`.
- Compare each entity only with entities seen before it in deterministic sorted order.
- Persist `merge_candidate` for resolver action `merge`.
- Persist `needs_review` for resolver action `needs_review`.
- Publish pending events to `review_queue` tab `entity_resolution`.
- Write `agent_runs`.

Use these action mappings:

- Resolver `merge` -> event action `merge_candidate`, status `pending_review`.
- Resolver `needs_review` -> event action `needs_review`, status `pending_review`.
- Resolver `create` -> no event row.

Run:

```bash
python3 -m pytest tests/integration/test_resolve_entities.py
```

Expected: pass.

- [ ] **Step 5: Wire job runner**

Modify `src/merry_runtime/job_runner.py`:

- Import `resolve_entities`.
- Replace `_run_resolve_entities` stub with pipeline call.
- Return `event_count`, `merge_candidate_count`, and `needs_review_count`.

Add/update `tests/test_job_runner.py`:

```python
def test_run_resolve_entities_persists_resolution_events(tmp_path) -> None:
    store = FakeStructuredStore()
    store.upsert_rows(
        table="mother_entities",
        rows=[
            {"entity_id": "ent_a", "entity_type": "startup", "name": "Merry AI", "normalized_name": "merryai", "region": "Seoul", "homepage": "https://merry.example"},
            {"entity_id": "ent_b", "entity_type": "startup", "name": "Merry", "normalized_name": "merry", "region": "Seoul", "homepage": "https://merry.example"},
        ],
        key_fields=("entity_id",),
    )
    runtime = _runtime(tmp_path, store=store)

    result = run_job("resolve-entities", runtime=runtime, config=_config(tmp_path))

    assert result["job_name"] == "resolve-entities"
    assert result["event_count"] == 1
    assert store.tables["entity_resolution_events"][0]["status"] == "pending_review"
```

Run:

```bash
python3 -m pytest tests/integration/test_resolve_entities.py tests/test_job_runner.py
```

Expected: pass.

- [ ] **Step 6: Run verification and commit**

Run:

```bash
make verify
git diff --check
```

Commit:

```bash
git add src/merry_runtime/schema.py src/merry_runtime/pipelines/resolve_entities.py src/merry_runtime/job_runner.py infra/terraform/main.tf tests/integration/test_resolve_entities.py tests/test_bigquery_schema.py tests/test_job_runner.py
git commit -m "feat: persist probabilistic entity resolution events"
```

---

## Task 3: Pin Runtime Dependencies And Add Supply-Chain Audit

**Risk Burned Down:** Each Cloud Run image build can pull different dependency versions.

**Design Decision:** Use a generated hash-locked `requirements.lock`, install the package with `--no-deps`, pin Docker base image by digest, and run `pip-audit` in CI.

**Files:**
- Create: `requirements.in`
- Create: `requirements.lock`
- Modify: `Dockerfile`
- Modify: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`
- Test: `tests/test_supply_chain.py`

- [ ] **Step 1: Write failing supply-chain static test**

Create `tests/test_supply_chain.py`:

```python
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
```

Run:

```bash
python3 -m pytest tests/test_supply_chain.py
```

Expected: fails because lockfile and digest pinning are absent.

- [ ] **Step 2: Create lock input file**

Create `requirements.in`:

```text
google-api-python-client==2.140.0
google-cloud-bigquery==3.25.0
google-cloud-storage==2.18.0
slack-sdk==3.33.0
```

Run:

```bash
python3 -m pip install pip-tools pip-audit
python3 -m piptools compile --generate-hashes --output-file requirements.lock requirements.in
```

Expected:

- `requirements.lock` exists.
- Each package entry includes `--hash=sha256:`.

- [ ] **Step 3: Pin Docker base image digest**

Run:

```bash
docker buildx imagetools inspect python:3.12-slim
```

Copy the linux/amd64 digest printed by Docker into `Dockerfile`. The final committed line must match this regular expression:

```text
^FROM python:3\.12-slim@sha256:[0-9a-f]{64}$
```

Verify after editing:

```bash
python3 - <<'PY'
from pathlib import Path
import re
line = Path("Dockerfile").read_text().splitlines()[0]
assert re.match(r"^FROM python:3\\.12-slim@sha256:[0-9a-f]{64}$", line), line
PY
```

- [ ] **Step 4: Change Docker install path**

Modify `Dockerfile`:

```dockerfile
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs

RUN pip install --no-cache-dir --no-deps .
```

Run:

```bash
python3 -m pytest tests/test_supply_chain.py
```

Expected: pass.

- [ ] **Step 5: Add CI audit**

Modify `.github/workflows/ci.yml`:

```yaml
- name: Install audit tooling
  run: python3 -m pip install pip-audit

- name: Audit locked Python dependencies
  run: python3 -m pip_audit -r requirements.lock
```

Run:

```bash
python3 -m pip_audit -r requirements.lock
make verify
```

Expected: `pip-audit` exits 0 or reports only explicitly accepted advisories documented in the commit message. Do not commit with unresolved critical/high advisories.

- [ ] **Step 6: Commit**

```bash
git add requirements.in requirements.lock Dockerfile .github/workflows/ci.yml tests/test_supply_chain.py pyproject.toml
git commit -m "chore: pin runtime supply chain"
```

---

## Task 4: Make Raw Evidence Writes Immutable And Remove GCS Object Admin

**Risk Burned Down:** Runtime service account can overwrite/delete raw evidence.

**Design Decision:** Raw evidence is immutable. `write_raw_text` uses create-only upload with `if_generation_match=0`. Duplicate ingestion returns the same URI without requiring overwrite/delete.

**Files:**
- Modify: `src/merry_runtime/adapters/gcs.py`
- Modify: `infra/terraform/main.tf`
- Test: `tests/test_adapter_contracts.py`
- Test: `tests/test_infra_terraform.py`

- [ ] **Step 1: Write failing GCS adapter test**

Extend `tests/test_adapter_contracts.py`:

```python
def test_gcs_object_store_uses_create_only_upload_precondition() -> None:
    client = FakeGCSClient()
    store = GCSObjectStore(client=client, bucket="raw-bucket")

    uri = store.write_raw_text(path="/raw/a.txt", text="hello", content_type="text/plain")

    blob = client.bucket_obj.blobs["raw/a.txt"]
    assert uri == "gs://raw-bucket/raw/a.txt"
    assert blob.uploaded["if_generation_match"] == 0
```

Run:

```bash
python3 -m pytest tests/test_adapter_contracts.py::test_gcs_object_store_uses_create_only_upload_precondition
```

Expected: fails because `upload_from_string` does not pass `if_generation_match`.

- [ ] **Step 2: Implement create-only upload**

Modify `src/merry_runtime/adapters/gcs.py`:

```python
blob.upload_from_string(text, content_type=content_type, if_generation_match=0)
```

If Google raises a precondition failure for an already-existing object, return the same `gs://` URI and do not modify the object. Keep the fake test simple by recording the precondition argument.

Run:

```bash
python3 -m pytest tests/test_adapter_contracts.py
```

Expected: pass.

- [ ] **Step 3: Write failing Terraform IAM test**

Extend `tests/test_infra_terraform.py`:

```python
def test_terraform_raw_bucket_grants_creator_not_object_admin() -> None:
    main_tf = (REPO_ROOT / "infra" / "terraform" / "main.tf").read_text()

    assert 'roles/storage.objectAdmin' not in main_tf
    assert 'roles/storage.objectCreator' in main_tf
```

Run:

```bash
python3 -m pytest tests/test_infra_terraform.py::test_terraform_raw_bucket_grants_creator_not_object_admin
```

Expected: fails because Terraform still grants object admin.

- [ ] **Step 4: Replace object admin IAM**

Modify `infra/terraform/main.tf`:

- Replace `google_storage_bucket_iam_member.raw_docs_object_admin`.
- Add `google_storage_bucket_iam_member.raw_docs_object_creator`.
- Use role `roles/storage.objectCreator`.

Run:

```bash
tofu -chdir=infra/terraform fmt
make verify
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/merry_runtime/adapters/gcs.py infra/terraform/main.tf tests/test_adapter_contracts.py tests/test_infra_terraform.py
git commit -m "fix: make raw evidence writes immutable"
```

---

## Task 5: Add Operational Visibility For Frontless Jobs

**Risk Burned Down:** Scheduled frontless jobs can fail silently or produce low-quality summaries.

**Design Decision:** Add application-level visibility first: every job writes a structured `agent_runs` success/failure record when the structured store is available, and weekly Slack summaries include failures, review throughput, candidate queues, and resolution events. Terraform alerting can then watch logs/metrics in staging.

**Files:**
- Modify: `src/merry_runtime/job_runner.py`
- Modify: `src/merry_runtime/jobs.py`
- Create: `src/merry_runtime/pipelines/weekly_summary.py`
- Modify: `infra/terraform/main.tf`
- Modify: `infra/terraform/variables.tf`
- Test: `tests/test_job_runner.py`
- Test: `tests/test_jobs_cli.py`
- Test: `tests/test_infra_terraform.py`

- [ ] **Step 1: Write failing weekly summary test**

Extend `tests/test_job_runner.py`:

```python
def test_run_weekly_summary_includes_failures_reviews_and_resolution_events(tmp_path) -> None:
    store = FakeStructuredStore.seed_candidate_card()
    store.upsert_rows(
        table="agent_runs",
        rows=[
            {"run_id": "run_fail", "job_name": "ingest-sources", "status": "failed", "started_at": "2026-05-18T00:00:00+00:00", "finished_at": "2026-05-18T00:00:01+00:00", "input_count": 1, "output_count": 0, "error_message": "boom"},
        ],
        key_fields=("run_id",),
    )
    store.upsert_rows(
        table="reviews",
        rows=[
            {"review_id": "rev_1", "card_id": "card_1", "reviewer": "boram", "decision": "advance", "memo": "", "reviewed_at": "2026-05-18T00:00:00+00:00"},
        ],
        key_fields=("review_id",),
    )
    store.upsert_rows(
        table="entity_resolution_events",
        rows=[
            {"event_id": "evt_1", "candidate_entity_id": "ent_b", "matched_entity_id": "ent_a", "action": "merge_candidate", "probability": 0.91, "features_json": "{}", "rationale": "domain_match=1.00", "status": "pending_review", "created_at": "2026-05-18T00:00:00+00:00"},
        ],
        key_fields=("event_id",),
    )
    runtime = _runtime(tmp_path, store=store)

    run_job("weekly-summary", runtime=runtime, config=_config(tmp_path))

    text = runtime.notifier.messages[0]["text"]
    assert "failed_jobs=1" in text
    assert "reviews=1" in text
    assert "resolution_pending=1" in text
    assert "priority=1" in text
```

Run:

```bash
python3 -m pytest tests/test_job_runner.py::test_run_weekly_summary_includes_failures_reviews_and_resolution_events
```

Expected: fails because weekly summary only counts candidate card queues.

- [ ] **Step 2: Implement weekly summary pipeline**

Create `src/merry_runtime/pipelines/weekly_summary.py`:

- Query `candidate_cards`.
- Query `reviews`.
- Query `agent_runs`.
- Query `entity_resolution_events`.
- Count candidate queues, review decisions, failed jobs, and pending resolution events.
- Return a single bounded summary string with no raw PII.

Modify `job_runner.py` so `_run_weekly_summary` calls this pipeline and sends the text.

Run:

```bash
python3 -m pytest tests/test_job_runner.py
```

Expected: pass.

- [ ] **Step 3: Add job failure record path**

Modify `src/merry_runtime/jobs.py` so unexpected exceptions after runtime creation attempt to write an `agent_runs` row with:

- `status`: `failed`.
- `job_name`: selected job.
- `error_message`: exception class and message, bounded to 1000 characters.

Add `tests/test_jobs_cli.py` coverage for a failing runtime path using fake adapters.

Run:

```bash
python3 -m pytest tests/test_jobs_cli.py
```

Expected: pass.

- [ ] **Step 4: Add Terraform alert shell**

Add variables:

- `ops_alert_email`
- `enable_ops_alerts`

Add resources when `enable_ops_alerts = true`:

- `google_monitoring_notification_channel`
- `google_logging_metric` for Cloud Run job error logs.
- `google_monitoring_alert_policy` for failure count.

Add static Terraform test ensuring resources and variables exist.

Run:

```bash
tofu -chdir=infra/terraform fmt
make verify
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/merry_runtime/job_runner.py src/merry_runtime/jobs.py src/merry_runtime/pipelines/weekly_summary.py infra/terraform/main.tf infra/terraform/variables.tf tests/test_job_runner.py tests/test_jobs_cli.py tests/test_infra_terraform.py
git commit -m "feat: add frontless job observability"
```

---

## Task 6: Run A Staging Canary Cycle

**Risk Burned Down:** The system has only local/fake validation, not real GCP adapter validation.

**Design Decision:** Use isolated staging resources and synthetic data only. A full pass means one synthetic candidate travels through ingest, resolve, score, review sync, wiki projection, BigQuery, GCS, Sheet, and Slack summary.

**Files:**
- Create: `docs/runbooks/staging-canary.md`
- Modify: `infra/terraform/staging.tfvars.example`
- Optional local-only file: `infra/terraform/staging.tfvars`

- [ ] **Step 1: Write staging runbook**

Create `docs/runbooks/staging-canary.md` with exact commands:

```markdown
# Hermes Staging Canary Runbook

## Preconditions

- Staging GCP project exists.
- Required APIs are enabled: Cloud Run, Cloud Scheduler, BigQuery, GCS, Artifact Registry, Secret Manager, Gmail API, Sheets API, Slack.
- `infra/terraform/staging.tfvars` exists and points only to staging resources.
- Secret versions exist for LLM API key and Slack bot token.
- Review Sheet is a staging Sheet.
- Gmail label is a staging label.
- Slack channel is a staging channel.

## Commands

```bash
tofu -chdir=infra/terraform plan -var-file=staging.tfvars
tofu -chdir=infra/terraform apply -var-file=staging.tfvars
docker build -t hermes-merry:staging .
docker tag hermes-merry:staging "$(tofu -chdir=infra/terraform output -raw artifact_registry_repository)/hermes-merry:staging"
docker push "$(tofu -chdir=infra/terraform output -raw artifact_registry_repository)/hermes-merry:staging"
python3 -m merry_runtime.jobs run ingest-sources --sources-json '[{"channel":"external_referral","payload":{"company":"Canary CareFarm","region":"Jeonbuk","industry":"AgriTech","reason":"Canary synthetic referral","tags":"social_problem:rural_income, beneficiary:older_farmers","confidence":"0.91"}}]'
```

## Acceptance

- GCS has one raw synthetic source object.
- BigQuery has one raw source, one mother entity, at least one signal, one score, one candidate card, and one agent run.
- Review Sheet has one candidate row.
- Slack receives weekly summary in staging channel.
- No production resource IDs appear in logs or Terraform outputs.
```

Run:

```bash
markdownlint docs/runbooks/staging-canary.md
```

If `markdownlint` is unavailable, run:

```bash
python3 - <<'PY'
from pathlib import Path
text = Path("docs/runbooks/staging-canary.md").read_text()
assert "production" in text.casefold()
assert "staging" in text.casefold()
assert "Acceptance" in text
PY
```

- [ ] **Step 2: Execute Terraform plan**

Run:

```bash
tofu -chdir=infra/terraform plan -var-file=staging.tfvars
```

Expected:

- Creates staging dataset, bucket, service accounts, secrets, jobs, scheduler, and artifact registry.
- No destroy actions.
- No production project/resource names in plan.

- [ ] **Step 3: Apply and run manual jobs**

Run manual Cloud Run jobs in this order:

```bash
gcloud run jobs execute ingest-sources --region asia-northeast3 --wait
gcloud run jobs execute resolve-entities --region asia-northeast3 --wait
gcloud run jobs execute score-candidates --region asia-northeast3 --wait
gcloud run jobs execute sync-review-sheet --region asia-northeast3 --wait
gcloud run jobs execute weekly-summary --region asia-northeast3 --wait
```

Expected:

- Each job exits successfully.
- `agent_runs` contains one success row per job.

- [ ] **Step 4: Capture staging evidence**

Create `docs/runbooks/staging-canary-results.md` with:

- Absolute date and time.
- `tofu output` summary.
- BigQuery row counts.
- Cloud Run job execution names.
- Manual note that staging Sheet and Slack were checked.

- [ ] **Step 5: Commit runbook/results**

```bash
git add docs/runbooks/staging-canary.md docs/runbooks/staging-canary-results.md infra/terraform/staging.tfvars.example
git commit -m "docs: add staging canary runbook"
```

---

## Task 7: Implement AC Hypothesis Report Ingestion

**Risk Burned Down:** AC-specific thesis/fund/program context is mostly seeded manually, so scoring cannot adapt to real AC documents.

**Design Decision:** Treat hypothesis reports as sources that produce `ac_profiles` and ontology/wiki pages. Do not let LLM prose directly set scores; extracted tags and fields feed the transparent scoring model.

**Files:**
- Create: `src/merry_runtime/ingestion/ac_profile_parser.py`
- Create: `src/merry_runtime/pipelines/ingest_ac_profiles.py`
- Modify: `src/merry_runtime/jobs.py`
- Modify: `src/merry_runtime/runtime_config.py`
- Modify: `infra/terraform/main.tf`
- Test: `tests/test_ac_profile_parser.py`
- Test: `tests/integration/test_ingest_ac_profiles.py`

Execution tasks:

- [ ] Write parser tests for a plain-text AC report with fund purpose, recruiting area, hypothesis tags, impact priorities, region preferences, industry preferences, and tech preferences.
- [ ] Implement deterministic parser that rejects empty `ac_id`, empty `fund_purpose`, and reports with no hypothesis/impact tags.
- [ ] Implement pipeline that upserts `ac_profiles` and writes wiki concept pages.
- [ ] Add Cloud Run job `ingest-ac-profiles`.
- [ ] Verify `make verify`.
- [ ] Commit with `feat: ingest ac hypothesis profiles`.

Acceptance:

- A synthetic AC report creates one `ac_profiles` row.
- Scoring the same candidate against two different AC profiles produces different feature/rationale values.
- The wiki index links the AC profile and impact thesis pages.

---

## Task 8: Add Review-Feedback Calibration Loop

**Risk Burned Down:** Human decisions are stored but do not update scoring priors.

**Design Decision:** Start with transparent coefficient calibration stored per AC. Do not train an opaque model. Use human decisions to adjust priors with bounded updates.

**Files:**
- Modify: `src/merry_runtime/schema.py`
- Create: `src/merry_runtime/calibration.py`
- Create: `src/merry_runtime/pipelines/calibrate_scores.py`
- Modify: `src/merry_runtime/probabilistic_scoring.py`
- Modify: `src/merry_runtime/scoring.py`
- Test: `tests/test_calibration.py`
- Test: `tests/integration/test_calibrate_scores.py`

Execution tasks:

- [ ] Add `ac_scoring_coefficients` schema with `ac_id`, coefficient fields, `sample_count`, `model_version`, and `updated_at`.
- [ ] Write tests proving positive decisions lift relevant coefficients within a cap and rejects lower them within a floor.
- [ ] Implement calibration with bounded coefficient deltas.
- [ ] Load AC-specific coefficients in scoring.
- [ ] Persist calibration run output to `agent_runs`.
- [ ] Verify `make verify`.
- [ ] Commit with `feat: calibrate scoring from human reviews`.

Acceptance:

- At least 10 synthetic review rows produce deterministic coefficient changes.
- A single outlier review cannot move a coefficient beyond the configured cap.
- Existing score tests remain deterministic when no coefficient row exists.

---

## Task 9: Build 1,000-Candidate Acquisition And Data Quality Gate

**Risk Burned Down:** The runtime can process candidates, but there is no repeatable acquisition path for the target Mother DB size.

**Design Decision:** Start with importable curated files before autonomous web crawling. The first 1,000 candidates should come from controlled CSV/Sheet/Gmail/Drive exports with source-channel semantics preserved.

**Files:**
- Create: `src/merry_runtime/ingestion/batch_import.py`
- Create: `src/merry_runtime/pipelines/import_candidate_batch.py`
- Create: `tests/fixtures/candidate_batch_100.csv`
- Test: `tests/test_batch_import.py`
- Test: `tests/integration/test_import_candidate_batch.py`
- Modify: `docs/runbooks/staging-canary.md`

Execution tasks:

- [ ] Add CSV parser tests for columns: company, brand, representative, homepage, region, industry, channel, evidence, confidence, tags, source_uri.
- [ ] Implement CSV import parser with strict required columns and PII redaction on evidence.
- [ ] Implement batch pipeline using existing ingest path so raw source, entity, signal, wiki, and scores stay consistent.
- [ ] Add a 100-row fixture and a generated 1,000-row synthetic scale test.
- [ ] Add quality gate: reject batch if duplicate normalized name + homepage conflict rate is above 5%.
- [ ] Verify `make verify`.
- [ ] Commit with `feat: import curated candidate batches`.

Acceptance:

- 1,000 synthetic candidates ingest under local test without network.
- Duplicate/conflict report is generated.
- Every imported candidate has a preserved discovery channel and evidence source.

---

## Release Gates

### Gate A: Data Safety

Must pass before any real startup data:

- Task 1 complete.
- Task 2 complete.
- Task 4 complete.
- `make verify` passes.
- No target-table delete SQL remains in `BigQueryStructuredStore.upsert_rows`.
- Raw GCS writes are create-only.
- Entity resolution is non-destructive unless a human-reviewed merge task is added.

### Gate B: Runtime Security

Must pass before scheduled jobs run:

- Task 3 complete.
- Docker image uses digest-pinned base.
- Python dependencies install from hash-locked requirements.
- `pip-audit` passes or documented accepted advisories are approved.
- Cloud Run runtime SA does not have `roles/run.developer`, project editor/admin, or bucket object admin.

### Gate C: Staging Confidence

Must pass before production planning:

- Task 5 complete.
- Task 6 complete.
- One synthetic candidate completes ingest -> resolve -> score -> review sync -> weekly summary.
- Staging Sheet, Slack, GCS, BigQuery, and Cloud Run logs are checked.
- Staging run results are documented.

### Gate D: Product Loop Readiness

Must pass before scaling acquisition:

- Task 7 complete.
- Task 8 complete.
- Task 9 complete.
- 1,000-candidate synthetic import passes local quality gates.
- A 50-candidate real-data pilot is reviewed by a human before broader acquisition.

## CTO Recommendation

Execute Task 1 and Task 2 first. They decide whether the Mother DB can be trusted. Security hardening without atomic writes and resolution events would still leave the core memory layer unsafe.

Then execute Task 3 and Task 4 before any staging data with real names, because they reduce supply-chain and raw-evidence blast radius.

Only after Gate A and Gate B should the team spend time on staging canary, calibration, AC report ingestion, or 1,000-candidate growth. That sequencing prevents a common failure mode: scaling a source pipeline before the memory layer is trustworthy.
