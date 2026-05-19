# Hermes TheVC To SMINFO Queue Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for implementation, then `superpowers:verification-before-completion` before claiming completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the existing The VC crawler to the SMINFO enrichment flow through a durable SQLite-backed work queue so the 24-hour Runpod Hermes agent can autonomously receive, lease, retry, and complete enrichment work.

**Architecture:** `crawl-sources` extracts The VC investment/company cards, writes the human-facing `Candidate Detail` Sheet projection, and enqueues SMINFO lookup tasks into SQLite. `enrich-sminfo` drains only due queue tasks, uses the Playwright SMINFO client, writes `sminfo_company_profiles`, updates queue state, updates `Candidate Detail`, appends `SMINFO Enrichment`, and lets `backup-export` snapshot the DB/wiki/sheets on the existing loop.

**Tech Stack:** Python 3.12, SQLiteStructuredStore, Google Sheets adapter, Playwright SMINFO client, Runpod Docker agent loop.

---

## Current State

- `agent_loop` can already run `AGENT_LOOP_JOBS=crawl-sources,enrich-sminfo,backup-export` every hour on Runpod.
- `crawl-sources` already extracts The VC rows and writes `Candidate Detail`.
- `enrich-sminfo` already fetches real SMINFO details and writes `sminfo_company_profiles`, `SMINFO Enrichment`, and `Candidate Detail`.
- The missing link is a first-class queue. Today `enrich-sminfo` scans `Candidate Detail`, which makes Sheets both the UI and the scheduler. The desired design is SQLite as Hermes memory and queue source of truth, with Sheets as a projection/backup console.

## Target Flow

1. Hermes Runpod loop starts a cycle.
2. `crawl-sources` crawls The VC investment/M&A targets.
3. New or stale candidates are upserted into `Candidate Detail`.
4. The same candidates are enqueued into SQLite table `sminfo_enrichment_queue`.
5. `enrich-sminfo` leases due queue rows, capped by `SMINFO_BATCH_LIMIT`.
6. For each task, Hermes calls SMINFO through Playwright with the existing 35 second minimum interval.
7. Results are written to:
   - `sminfo_company_profiles`: structured source of truth
   - `sminfo_enrichment_queue`: task state and retry metadata
   - `Candidate Detail`: human front
   - `SMINFO Enrichment`: append/upsert detail projection
8. `backup-export` snapshots SQLite, wiki, and sheet projections.

## Queue Contract

Add table `sminfo_enrichment_queue` to `src/merry_runtime/schema.py`.

Required fields:

- `task_id`: stable id, e.g. `sminfo_task_<sha1>`
- `company`: display company name from The VC
- `normalized_name`: normalized matching key
- `representative`: optional hint from The VC/detail fallback
- `homepage`: optional hint from The VC/detail fallback
- `source_url`: The VC source URL
- `source_channel`: usually `thevc_investment_ma`
- `status`: `pending`, `running`, `matched`, `matched_no_financials`, `not_found`, `ambiguous`, `retry`, `failed`
- `priority`: integer, default 100
- `attempt_count`: integer
- `max_attempts`: integer, default 5
- `next_run_at`: timestamp
- `locked_at`: timestamp
- `locked_by`: Runpod/Hermes agent id
- `last_error`: text
- `last_profile_id`: latest `sminfo_company_profiles.profile_id`
- `created_at`, `updated_at`, `completed_at`: timestamps

Idempotency key:

```text
normalized_company + "|" + normalized_homepage + "|" + normalized_representative
```

Fallback when homepage/representative are absent:

```text
normalized_company + "|" + source_channel
```

Terminal rows should not be re-enqueued until `SMINFO_STALE_DAYS` has elapsed, unless a new source gives materially better hints such as homepage or representative.

## Task 1: Queue Schema And Pure Helpers

**Files:**
- Modify: `src/merry_runtime/schema.py`
- Create: `src/merry_runtime/ingestion/sminfo_queue.py`
- Test: `tests/test_bigquery_schema.py`
- Test: `tests/test_sminfo_queue.py`

- [ ] **Step 1: Write failing tests**

Assert the schema includes `sminfo_enrichment_queue` and that helper functions produce stable task ids, normalize legal Korean prefixes/suffixes safely, classify terminal vs retryable statuses, and compute retry backoff.

Run:

```bash
python3 -m pytest tests/test_bigquery_schema.py tests/test_sminfo_queue.py -q
```

Expected: fail because the queue table/helper module does not exist.

- [ ] **Step 2: Implement schema and helpers**

Add pure helpers:

- `build_sminfo_task(candidate, source_channel, now) -> dict`
- `sminfo_task_id(...) -> str`
- `is_terminal_queue_status(status) -> bool`
- `next_retry_at(attempt_count, now) -> str`
- `queue_status_for_profile(profile) -> str`

Use only deterministic normalization and no browser/network calls here.

- [ ] **Step 3: Verify**

Run:

```bash
python3 -m pytest tests/test_bigquery_schema.py tests/test_sminfo_queue.py -q
```

Expected: pass.

## Task 2: Enqueue From The VC Crawl

**Files:**
- Modify: `src/merry_runtime/pipelines/crawl_sources.py`
- Test: `tests/integration/test_crawl_sources.py`

- [ ] **Step 1: Write failing crawl enqueue test**

Seed a The VC crawl source, run `crawl_sources`, and assert:

- `Candidate Detail` still receives the human-facing row.
- `sminfo_enrichment_queue` receives exactly one `pending` task.
- Running the same crawl twice does not duplicate the task.
- A previously terminal fresh task is not reset to `pending`.

Run:

```bash
python3 -m pytest tests/integration/test_crawl_sources.py -q
```

Expected: fail because crawl does not enqueue SMINFO tasks.

- [ ] **Step 2: Implement enqueue inside `crawl_sources`**

After parsing The VC candidate detail sources, call a queue helper that upserts tasks into `structured_store`.

Rules:

- The Sheet projection stays unchanged except for already approved column labels.
- Queue writes happen even when Google Sheets is disabled, because SQLite is the source of truth.
- Existing `matched`, `matched_no_financials`, `not_found`, and `ambiguous` rows are not reset if fresh.
- Existing `retry`/`failed` rows may be re-opened only when a new crawl gives stronger hints.

- [ ] **Step 3: Add run accounting**

Extend `CrawlResult` with `enqueued_sminfo_task_count` and record it in `agent_runs.output_count` or a structured payload field if available.

- [ ] **Step 4: Verify**

Run:

```bash
python3 -m pytest tests/integration/test_crawl_sources.py -q
```

Expected: pass.

## Task 3: Drain Queue In `enrich-sminfo`

**Files:**
- Modify: `src/merry_runtime/pipelines/enrich_sminfo.py`
- Modify: `src/merry_runtime/job_runner.py`
- Test: `tests/integration/test_enrich_sminfo.py`

- [ ] **Step 1: Write failing queue drain tests**

Add tests for:

- Due `pending` tasks are selected before Sheet fallback.
- Each selected task is marked `running` with `locked_by` and `locked_at`.
- Successful SMINFO results update profile table, Sheet projections, and queue terminal status.
- Browser/network exceptions move task to `retry` with incremented `attempt_count` and future `next_run_at`.
- Exceeding `max_attempts` moves task to `failed`.
- Existing Sheet-scan behavior remains as migration fallback when the queue is empty.

Run:

```bash
python3 -m pytest tests/integration/test_enrich_sminfo.py -q
```

Expected: fail because `enrich_sminfo_candidates` only scans `Candidate Detail`.

- [ ] **Step 2: Implement queue selection and leasing**

Add `agent_id` and `use_queue` parameters to `enrich_sminfo_candidates`.

Selection query:

```sql
SELECT * FROM sminfo_enrichment_queue
WHERE status IN ('pending', 'retry')
  AND next_run_at <= @now
ORDER BY priority ASC, created_at ASC
LIMIT @max_items
```

Lease by upserting selected rows to `status='running'`, `locked_by=<agent_id>`, `locked_at=<now>`, `updated_at=<now>` before calling Playwright.

- [ ] **Step 3: Implement task completion**

For each profile:

- Upsert profile to `sminfo_company_profiles`.
- Upsert `SMINFO Enrichment`.
- Upsert `Candidate Detail` by `company, homepage`.
- Upsert queue row with `status`, `completed_at`, `last_profile_id`, `last_error`.

Use `matched_no_financials` in queue when SMINFO matched the company but financial fields are empty. Keep the visible `Candidate Detail.sminfo_status` as the underlying SMINFO `match_status` unless a separate Korean label is needed later.

- [ ] **Step 4: Implement retry path**

For exceptions:

- Write an error profile as today.
- Queue status becomes `retry` until `attempt_count >= max_attempts`.
- Then queue status becomes `failed`.
- Preserve `last_error` with a truncated exception message.

- [ ] **Step 5: Verify**

Run:

```bash
python3 -m pytest tests/integration/test_enrich_sminfo.py -q
```

Expected: pass.

## Task 4: Sheet Queue Projection For Monitoring

**Files:**
- Modify: `src/merry_runtime/adapters/google_sheets.py`
- Modify: `src/merry_runtime/pipelines/enrich_sminfo.py`
- Modify: `src/merry_runtime/pipelines/backup_export.py`
- Test: `tests/test_adapter_contracts.py`
- Test: `tests/integration/test_enrich_sminfo.py`

- [ ] **Step 1: Add `SMINFO Queue` tab headers**

Headers:

- `task_id`
- `company`
- `status`
- `priority`
- `attempt_count`
- `next_run_at`
- `locked_by`
- `last_error`
- `last_profile_id`
- `source_url`
- `updated_at`

Korean label row should mirror the existing row 1 key / row 2 Korean label convention.

- [ ] **Step 2: Publish queue updates**

When tasks are created or updated, optionally project them to `SMINFO Queue` using `review_queue.upsert_cards`. The SQLite row remains authoritative.

- [ ] **Step 3: Verify**

Run:

```bash
python3 -m pytest tests/test_adapter_contracts.py tests/integration/test_enrich_sminfo.py -q
```

Expected: pass.

## Task 5: Runtime Config And Runpod Loop

**Files:**
- Modify: `src/merry_runtime/runtime_config.py`
- Modify: `configs/runpod.env.example`
- Modify: `docs/runbooks/runpod-staging.md`
- Test: `tests/test_runtime_config.py`
- Test: `tests/test_runpod_docs.py`

- [ ] **Step 1: Add queue env config**

Keep current env names where possible:

- `SMINFO_BATCH_LIMIT`: max queue tasks per loop, capped to 20
- `SMINFO_MIN_INTERVAL_SECONDS`: minimum seconds between SMINFO lookups, lower bound 35
- `SMINFO_STALE_DAYS`: terminal task freshness window

Add only if needed:

- `HERMES_AGENT_ID`: defaults to hostname/pod id
- `SMINFO_RETRY_MAX_ATTEMPTS`: default 5
- `SMINFO_RETRY_BASE_SECONDS`: default 3600

- [ ] **Step 2: Document the canonical Runpod job order**

Use:

```bash
AGENT_LOOP_JOBS=crawl-sources,enrich-sminfo,backup-export
AGENT_LOOP_INTERVAL_SECONDS=3600
AGENT_LOOP_MAX_CYCLES=0
```

This means every cycle starts one hour after the previous cycle completes. It is not a local Codex job and not a one-off manual script.

- [ ] **Step 3: Verify config/docs tests**

Run:

```bash
python3 -m pytest tests/test_runtime_config.py tests/test_runpod_docs.py -q
```

Expected: pass.

## Task 6: End-To-End Canary

**Files:**
- Modify only if tests reveal bugs.

- [ ] **Step 1: Local unit/integration verification**

Run:

```bash
make verify
```

Expected: all tests pass.

- [ ] **Step 2: Docker smoke**

Build and run a one-cycle smoke with mounted local test env:

```bash
docker build -t hermes-merry:sminfo-queue .
docker run --rm --env-file <local-env> hermes-merry:sminfo-queue \
  python -m merry_runtime.jobs agent-loop --max-cycles 1
```

Expected:

- The VC crawl creates or preserves candidates.
- `sminfo_enrichment_queue` contains due tasks.
- `enrich-sminfo` processes up to `SMINFO_BATCH_LIMIT`.
- Sheet `Candidate Detail` receives real SMINFO fields.

- [ ] **Step 3: Push staging image**

Tag with the commit sha:

```bash
docker tag hermes-merry:sminfo-queue docker.io/boram1220/hermes-merry:staging-<sha>
docker push docker.io/boram1220/hermes-merry:staging-<sha>
```

- [ ] **Step 4: Replace Runpod pod**

Create a new Runpod pod using the new image and the existing secrets. Keep:

```bash
AGENT_LOOP_JOBS=crawl-sources,enrich-sminfo,backup-export
AGENT_LOOP_INTERVAL_SECONDS=3600
AGENT_LOOP_MAX_CYCLES=0
```

Expected: Hermes, not Codex, keeps doing the crawl/enrich loop.

- [ ] **Step 5: Canary checks**

After one cycle:

- Query SQLite backup or pod logs for queue counts by status.
- Confirm `Candidate Detail` has newly enriched rows.
- Confirm `SMINFO Queue` reflects task status.
- Confirm `agent_runs` has successful `crawl-sources`, `enrich-sminfo`, and `backup-export` rows.

## Risk Register

- **SMINFO blocks or resets connections:** keep Playwright session reuse, 35 second minimum interval, batch cap, and retry backoff.
- **Sheet becomes scheduler again:** queue selection must prefer SQLite and use Sheet only as migration fallback.
- **Duplicate company names:** task id should include homepage/representative when available; SMINFO matching still uses candidate hints.
- **False terminal state:** stale window allows rechecking after `SMINFO_STALE_DAYS`.
- **Runpod interruption:** queue lease is represented in SQLite; stale `running` leases need a future recovery rule if interruption becomes common.
- **Sensitive data:** do not write SMINFO credentials, API keys, or raw browser session data into Sheet/logs/backup exports.

## Success Criteria

- A The VC candidate can be discovered in `crawl-sources`, appear in `sminfo_enrichment_queue`, be processed by `enrich-sminfo`, and land real SMINFO data in `Candidate Detail` without Codex manually triggering the lookup.
- The Runpod Hermes pod can run the loop continuously with `AGENT_LOOP_MAX_CYCLES=0`.
- Re-running the same crawl is idempotent.
- Failures retry with backoff instead of blocking the whole loop.
- `make verify` passes before image push.

## Deferred Backlog

- Lease timeout recovery for long-dead `running` tasks.
- Per-company manual pause/force-refresh controls in `SMINFO Queue`.
- Portfolio-news-to-SMINFO enrichment for portfolio companies.
- Confidence scoring that combines The VC evidence quality with SMINFO completeness.
