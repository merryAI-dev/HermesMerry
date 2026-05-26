# HermesMerry Onboarding

This guide is generated from the current repository structure and the local Understand graph. It is written for engineers and operators who need to understand where work enters the system, how it moves, and where to check failures.

## One-Sentence Model

HermesMerry is a queue-driven discovery runtime: public/company signals enter through crawlers, become candidate records in SQLite, move through SMINFO and scoring jobs, and appear in Google Sheets for human review.

## System Map

```text
Configured crawl targets
        |
        v
crawl-sources
        |
        +--> raw_sources / signals / candidate records
        |
        +--> sminfo_enrichment_queue
                  |
                  v
             enrich-sminfo
                  |
                  +--> sminfo_company_profiles
                  +--> Candidate Detail / SMINFO Queue Sheet projection

agent_work_queue chains the larger loop:
crawl -> sminfo -> resolve -> score -> sync -> backup
```

## Most Important Files

- `configs/agent_work_queue.discovery.json`: the ordered chain and risk notes.
- `src/merry_runtime/jobs.py`: command-line entrypoint.
- `src/merry_runtime/runtime_config.py`: environment variable parsing and job validation.
- `src/merry_runtime/job_runner.py`: maps job names to concrete pipeline functions.
- `src/merry_runtime/pipelines/agent_work_queue.py`: leases one chain task at a time and enqueues the next stage.
- `src/merry_runtime/pipelines/crawl_sources.py`: fetches configured sources and creates candidate/SMINFO work.
- `src/merry_runtime/pipelines/enrich_sminfo.py`: drains SMINFO tasks and updates SQLite/Sheets.
- `src/merry_runtime/loop_dashboard.py`: renders the local AIOps dashboard from SQLite.
- `src/merry_runtime/adapters/sqlite_store.py`: persistent local Mother DB implementation.
- `src/merry_runtime/adapters/google_sheets.py`: human-facing Sheet projection.

## Data Stores

- SQLite Mother DB: source of truth for runtime state.
- Google Sheets: review and operations console.
- Local raw/wiki/backup folders: artifacts and snapshots.
- Optional external services: Gmail drafts, Slack alerts, Claude summaries, KVIC public data, Runpod runtime.

## Queues

`agent_work_queue` is the high-level chain queue. It decides which stage should run next and keeps dependencies visible.

`sminfo_enrichment_queue` is the company-level SMINFO queue. It controls lookup retries, stale checks, rate limits, and task status per company.

## How To Check A Run

1. Open the SQLite DB configured by `MOTHER_DB_PATH`.
2. Check `agent_runs` for the latest job timestamps and failures.
3. Check `agent_work_queue` for blocked, failed, retry, or pending stages.
4. Check `sminfo_enrichment_queue` for company-level lookup state.
5. Render `tmp/hermes/loop-dashboard.html` and inspect the topology plus recent events.
6. Compare the Sheet tabs with SQLite before making a business decision.

## Common Failure Points

- Missing `SMINFO_USER_ID` or `SMINFO_PASSWORD`: SMINFO stage is blocked until credentials are added.
- Missing `REVIEW_SHEET_ID`: Sheet projection cannot run, but SQLite state may still exist.
- THE VC human verification: browser crawl may stop or fall back depending on target settings.
- Long-running loop cost: unbounded loops require `HERMES_ALLOW_UNBOUNDED_LOOP=1` and should be CPU-first.
- Duplicate company names: normalization is intentionally conservative, so ambiguous names should remain visible for review.

## Development Workflow

```bash
python3 -m pip install -e ".[dev]"
make verify
```

Focused tests for the current queue work:

```bash
uv run pytest tests/test_agent_work_queue.py tests/test_loop_dashboard.py tests/integration/test_crawl_sources.py tests/integration/test_enrich_sminfo.py
```

## Operator Rule

Do not infer that “the loop finished” from a commit or a process start. Confirm it from run logs, queue status, Sheet output, and dashboard timestamps.
