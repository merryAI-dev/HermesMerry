# SQLite Sheet Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SQLite-backed Mother DB plus Google Sheet console the primary Runpod staging runtime, with BigQuery reduced to an optional backend/export target.

**Architecture:** Add a `SQLiteStructuredStore` behind the existing `StructuredStore` protocol, select it via `STRUCTURED_STORE_BACKEND=sqlite`, and keep BigQuery available through `STRUCTURED_STORE_BACKEND=bigquery`. Strengthen Google Sheets tabs for human operation and add a local `backup-export` job that snapshots SQLite, exports tables, and archives the wiki.

**Tech Stack:** Python 3.12+, sqlite3, csv/json/tarfile stdlib, pytest, Google Sheets adapter, Runpod Docker runtime.

---

## File Map

- Create `src/merry_runtime/adapters/sqlite_store.py`: SQLite implementation of `StructuredStore`.
- Create `src/merry_runtime/pipelines/backup_export.py`: local backup/export pipeline.
- Create `tests/test_sqlite_structured_store.py`: SQLite store behavior.
- Create `tests/integration/test_backup_export.py`: backup/export behavior.
- Modify `src/merry_runtime/runtime_config.py`: parse `STRUCTURED_STORE_BACKEND`, `MOTHER_DB_PATH`, `BACKUP_ROOT`.
- Modify `src/merry_runtime/runtime_factory.py`: select SQLite or BigQuery.
- Modify `src/merry_runtime/jobs.py`: add `backup-export`.
- Modify `src/merry_runtime/adapters/google_sheets.py`: add console tab headers.
- Modify `configs/runpod.env.example`, `README.md`, `docs/runbooks/runpod-staging.md`, `docs/SAFETY.md`: document SQLite-first runtime.
- Modify tests that assert runtime docs/config behavior.

## Task 1: SQLite Structured Store

**Files:**
- Create: `src/merry_runtime/adapters/sqlite_store.py`
- Test: `tests/test_sqlite_structured_store.py`

- [ ] **Step 1: Write failing SQLite store tests**

Add tests that assert table creation from `BIGQUERY_TABLES`, key-field upsert replacement, repeated/list value round-tripping, and parameterized `SELECT ... FROM table` reads.

Run: `python3 -m pytest tests/test_sqlite_structured_store.py -q`
Expected: fail because `merry_runtime.adapters.sqlite_store` does not exist.

- [ ] **Step 2: Implement `SQLiteStructuredStore`**

Implement `upsert_rows()` and `query_rows()` using `sqlite3`. Store repeated/list and dict values as compact JSON text. Use SQLite `INSERT ... ON CONFLICT (...) DO UPDATE` for atomic upserts. Keep SQL support intentionally small: the pipelines currently issue simple `SELECT ... FROM table` queries with equality parameters, so reject unsupported writes in `query_rows()`.

- [ ] **Step 3: Verify SQLite tests**

Run: `python3 -m pytest tests/test_sqlite_structured_store.py -q`
Expected: pass.

- [ ] **Step 4: Commit**

Commit message: `feat: add sqlite structured store`

## Task 2: Runtime Backend Switch

**Files:**
- Modify: `src/merry_runtime/runtime_config.py`
- Modify: `src/merry_runtime/runtime_factory.py`
- Test: `tests/test_runtime_config.py`
- Test: `tests/test_runtime_factory.py`

- [ ] **Step 1: Write failing backend config tests**

Add tests for `STRUCTURED_STORE_BACKEND=sqlite`, default `MOTHER_DB_PATH`, custom `MOTHER_DB_PATH`, invalid backend validation, and factory construction without importing BigQuery when SQLite is selected.

Run: `python3 -m pytest tests/test_runtime_config.py tests/test_runtime_factory.py -q`
Expected: fail because backend config does not exist.

- [ ] **Step 2: Implement backend config and factory selection**

Add `structured_store_backend`, `mother_db_path`, and `backup_root` to `RuntimeConfig`. In `build_runtime()`, import BigQuery only for `bigquery`; use `SQLiteStructuredStore(db_path=config.mother_db_path)` for `sqlite`.

- [ ] **Step 3: Verify runtime tests**

Run: `python3 -m pytest tests/test_runtime_config.py tests/test_runtime_factory.py -q`
Expected: pass.

- [ ] **Step 4: Commit**

Commit message: `feat: select sqlite structured runtime`

## Task 3: Sheet Console Headers

**Files:**
- Modify: `src/merry_runtime/adapters/google_sheets.py`
- Test: `tests/test_adapter_contracts.py`

- [ ] **Step 1: Write failing Sheet console tests**

Add assertions that `Review Queue`, `Candidate Detail`, `Evidence`, `Decision Log`, `AC Settings`, `Exploration Queue`, and `Run Log` ranges use stable headers, and that formula-injection escaping still applies.

Run: `python3 -m pytest tests/test_adapter_contracts.py -q`
Expected: fail on missing console tabs.

- [ ] **Step 2: Implement tab headers**

Add constants for the console tabs and update `_headers_for_tab()` to support the new tab names while preserving existing `entity_resolution` behavior.

- [ ] **Step 3: Verify Sheet tests**

Run: `python3 -m pytest tests/test_adapter_contracts.py -q`
Expected: pass.

- [ ] **Step 4: Commit**

Commit message: `feat: expand sheet console tabs`

## Task 4: Backup Export Job

**Files:**
- Create: `src/merry_runtime/pipelines/backup_export.py`
- Modify: `src/merry_runtime/jobs.py`
- Modify: `src/merry_runtime/job_runner.py`
- Test: `tests/integration/test_backup_export.py`
- Test: `tests/test_jobs_cli.py`

- [ ] **Step 1: Write failing backup/export tests**

Add tests that seed a SQLite DB, run `backup-export`, and assert manifest, SQLite copy, CSV, JSONL, and wiki tarball outputs exist with row counts.

Run: `python3 -m pytest tests/integration/test_backup_export.py tests/test_jobs_cli.py -q`
Expected: fail because the job is not registered.

- [ ] **Step 2: Implement backup/export pipeline**

Use `sqlite3.Connection.backup()` for the database copy. Export each known table to CSV and JSONL. Compress `WIKI_ROOT` as `wiki.tar.gz` when present. Write `manifest.json` with timestamp, db path, wiki path, artifact paths, and row counts.

- [ ] **Step 3: Wire job runner and CLI choices**

Add `backup-export` to CLI choices and `run_job()` routing. Require SQLite backend for this job.

- [ ] **Step 4: Verify backup/export tests**

Run: `python3 -m pytest tests/integration/test_backup_export.py tests/test_jobs_cli.py -q`
Expected: pass.

- [ ] **Step 5: Commit**

Commit message: `feat: add sqlite backup export job`

## Task 5: Docs And Runpod Defaults

**Files:**
- Modify: `README.md`
- Modify: `configs/runpod.env.example`
- Modify: `docs/runbooks/runpod-staging.md`
- Modify: `docs/SAFETY.md`
- Modify: `tests/test_runpod_docs.py`
- Modify: `tests/test_supply_chain.py`

- [ ] **Step 1: Write failing docs tests**

Update docs tests to expect SQLite-first Runpod defaults, `STRUCTURED_STORE_BACKEND=sqlite`, `MOTHER_DB_PATH`, `BACKUP_ROOT`, and BigQuery as optional export infrastructure.

Run: `python3 -m pytest tests/test_runpod_docs.py tests/test_supply_chain.py -q`
Expected: fail until docs and env example are updated.

- [ ] **Step 2: Update docs and env example**

Rewrite Runpod staging docs so the primary path is SQLite + Sheet + Wiki + backup/export. Keep BigQuery references only for optional warehouse/export mode.

- [ ] **Step 3: Verify docs tests**

Run: `python3 -m pytest tests/test_runpod_docs.py tests/test_supply_chain.py -q`
Expected: pass.

- [ ] **Step 4: Full verification and commit**

Run: `make verify`
Expected: pass.

Commit message: `docs: make sqlite sheet runtime primary`

## Self-Review

- Spec coverage: tasks cover SQLite store, runtime switch, Sheet console, backup/export, and docs.
- Placeholder scan: no TBD/TODO/fill-in sections.
- Type consistency: `STRUCTURED_STORE_BACKEND`, `MOTHER_DB_PATH`, and `BACKUP_ROOT` are used consistently across config, factory, docs, and tests.

## Deferred Backlog

These are intentionally deferred while the crawl loop is opened first:

- Rewire `score-candidates` writes from AC-specific tabs to the canonical `Review Queue` tab.
- Wire Sheet decisions back into SQLite as the durable feedback source for calibration.
