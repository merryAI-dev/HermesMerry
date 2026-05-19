# KVIC Investor Fund DB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily KVIC fund snapshot job that turns public fund-status data into a SQLite-backed investor/fund Mother DB and exports an investor cockpit to Sheets.

**Architecture:** Hermes fetches KVIC fund categories and full fund rows with a browser User-Agent, normalizes the raw API payload into fund type, fund, and investor-manager profile rows, then upserts those rows into SQLite. The hourly Runpod agent loop may include `sync-kvic-funds`, but the job itself enforces a 24-hour freshness gate so the effective update cadence is every day.

**Tech Stack:** Python stdlib `urllib`, existing `StructuredStore`/`ReviewQueue` interfaces, SQLite schema source in `schema.py`, pytest, existing job runner and Runpod env config.

---

### Task 1: KVIC API Normalization

**Files:**
- Create: `src/merry_runtime/ingestion/kvic.py`
- Test: `tests/test_kvic_ingestion.py`

- [ ] **Step 1: Write failing tests**

```python
def test_normalizes_fund_types_and_funds_from_kvic_payloads() -> None:
    fund_types = parse_kvic_fund_types({"result": [{"fundCode": "11", "fundName": "한국모태펀드"}]})
    funds = parse_kvic_funds(
        {
            "result_11": [
                {
                    "year": "2023년",
                    "fd": "소셜임팩트",
                    "mng": "디쓰리쥬빌리파트너스",
                    "asn": "디쓰리 임팩트 벤처투자조합 제2호",
                    "exp": "2027-08-08",
                    "amt": "30850",
                    "ca": "21000",
                }
            ],
            "code": "",
        },
        collected_at="2026-05-19T16:00:00+09:00",
    )

    assert fund_types[0]["fund_code"] == "11"
    assert funds[0]["manager_name"] == "디쓰리쥬빌리파트너스"
    assert funds[0]["amount_eok"] == 308.5
    assert funds[0]["commitment_eok"] == 210.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_kvic_ingestion.py -q`

- [ ] **Step 3: Implement normalization**

Create pure parsing functions for fund types, fund rows, active status, KRW amount normalization, and manager profile aggregation.

- [ ] **Step 4: Run tests to verify green**

Run: `uv run pytest tests/test_kvic_ingestion.py -q`

### Task 2: Structured Schema And Sync Pipeline

**Files:**
- Modify: `src/merry_runtime/schema.py`
- Create: `src/merry_runtime/adapters/kvic.py`
- Create: `src/merry_runtime/pipelines/sync_kvic_funds.py`
- Test: `tests/integration/test_sync_kvic_funds.py`

- [ ] **Step 1: Write failing tests**

```python
def test_sync_kvic_funds_upserts_funds_and_investor_profiles(tmp_path) -> None:
    store = SQLiteStructuredStore(db_path=tmp_path / "mother.db")
    client = FakeKVICClient(...)
    result = sync_kvic_funds(structured_store=store, client=client, reference_date="2026-05-19")

    assert result.fund_type_count == 1
    assert result.fund_count == 2
    assert result.manager_count == 1
    assert store.query_rows(sql="select * from kvic_investor_managers", parameters={})[0]["active_fund_count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_sync_kvic_funds.py -q`

- [ ] **Step 3: Implement schema and pipeline**

Add `kvic_fund_types`, `kvic_funds`, `kvic_investor_managers`, and `kvic_sync_state`. The pipeline always stores raw evidence fields and derived profile fields separately.

- [ ] **Step 4: Run tests to verify green**

Run: `uv run pytest tests/integration/test_sync_kvic_funds.py -q`

### Task 3: Job Routing And Daily Cadence

**Files:**
- Modify: `src/merry_runtime/runtime_config.py`
- Modify: `src/merry_runtime/job_runner.py`
- Modify: `src/merry_runtime/jobs.py`
- Modify: `src/merry_runtime/runtime_factory.py`
- Test: `tests/test_runtime_config.py`
- Test: `tests/test_job_runner.py`
- Test: `tests/test_jobs_cli.py`

- [ ] **Step 1: Write failing tests**

Tests must prove `sync-kvic-funds` is a valid job, accepts `KVIC_API_KEY`, and skips work when the latest KVIC success is fresher than `KVIC_SYNC_INTERVAL_SECONDS=86400`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_runtime_config.py tests/test_job_runner.py tests/test_jobs_cli.py -q`

- [ ] **Step 3: Implement job routing**

Expose the job in CLI choices, runtime validation, runtime adapters, and job runner dispatch.

- [ ] **Step 4: Run tests to verify green**

Run: `uv run pytest tests/test_runtime_config.py tests/test_job_runner.py tests/test_jobs_cli.py -q`

### Task 4: Sheets Export And Docs

**Files:**
- Modify: `src/merry_runtime/pipelines/sync_kvic_funds.py`
- Modify: `configs/runpod.env.example`
- Modify: `README.md`
- Modify: `docs/runbooks/runpod-staging.md`
- Test: `tests/integration/test_sync_kvic_funds.py`
- Test: `tests/test_runpod_docs.py`

- [ ] **Step 1: Write failing tests**

Tests must prove investor rows are published to `Investor DB` with manager name, active fund count, fund fields, representative funds, and collected timestamp.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_sync_kvic_funds.py tests/test_runpod_docs.py -q`

- [ ] **Step 3: Implement export and documentation**

Publish profile rows when a review queue is configured, document the daily cadence, and add the job to Runpod loop examples.

- [ ] **Step 4: Run full targeted verification**

Run: `uv run pytest tests/test_kvic_ingestion.py tests/integration/test_sync_kvic_funds.py tests/test_runtime_config.py tests/test_job_runner.py tests/test_jobs_cli.py tests/test_runpod_docs.py -q`
