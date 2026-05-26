# HermesMerry

HermesMerry is a Python runtime for evidence-first accelerator candidate discovery.

The project helps Merry/Hermes collect company signals from allowed public sources, keep the work in a durable local database, enrich candidates through SMINFO when credentials are configured, and present the review state in Google Sheets plus a local AIOps dashboard.

It is not a finished production service yet. The current codebase is a working runtime foundation with tests, queueing, crawler adapters, Sheet projections, and runbooks. Real operating quality still depends on configured credentials, source-site availability, and operator review.

## What It Does Today

- Separates accelerator-company monitoring from investment-portfolio news monitoring.
- Preserves user-provided company names while removing only narrow legal prefixes/suffixes for search matching.
- Crawls configured sources such as THE VC and Platum through bounded adapters.
- Uses a SQLite-backed Mother DB as the source of truth for raw sources, candidates, signals, runs, queues, and SMINFO profiles.
- Chains discovery work through `agent_work_queue`: crawl, SMINFO enrichment, entity resolution, scoring, review-sheet sync, and backup export.
- Drains SMINFO work through a separate `sminfo_enrichment_queue` with retries, stale checks, and a batch cap.
- Projects review data into Google Sheets so non-developers can inspect, edit, and operate the candidate list.
- Renders a local AIOps dashboard that shows recent run times, queue status, table counts, and the discovery topology.
- Creates Gmail drafts only. It does not send outreach email automatically.

## What Is Conditional

- THE VC login automation can be blocked by human verification or site changes. The crawler records warnings instead of hiding that state.
- SMINFO enrichment requires `SMINFO_USER_ID`, `SMINFO_PASSWORD`, `REVIEW_SHEET_ID`, and browser/runtime dependencies.
- Google Sheets, Gmail, Slack, Claude, KVIC, and Runpod integrations require local `.env.local` or deployment secrets.
- GPU is not required for the current crawl, queue, Sheet, and SMINFO loop. If Gemma/Qwen or another local model is added later, it should run as a separate scale-to-zero endpoint unless active workers are explicitly justified.
- BigQuery and Cloud Run remain optional infrastructure paths. The default staging path is SQLite-first and Runpod/CPU-friendly.

## Runpod-first staging

The primary staging path is a Runpod Pod that can pull:

```bash
docker.io/boram1220/hermes-merry:staging
```

In that mode, Hermes uses a SQLite-backed Mother DB on the persistent runtime volume and Google Sheets as the human operating console. BigQuery is optional for later warehouse/export use. Cloud Run is optional and remains available through the separate Cloud Run runbook path.

## Discovery Flow

1. `crawl-sources` reads configured crawl targets and stores source evidence.
2. Candidate companies are written to the Mother DB and, when relevant, into the SMINFO queue.
3. `enrich-sminfo` leases due SMINFO tasks, respects the batch/rate limits, and writes structured company profiles.
4. `resolve-entities` and `score-candidates` prepare review-ready candidate records.
5. `sync-review-sheet` publishes the review queue to Google Sheets.
6. `backup-export` snapshots the database/wiki/sheet-facing state.
7. `render-loop-dashboard` creates a local HTML view for run history and queue health.

The chain definition lives in `configs/agent_work_queue.discovery.json`.

## Quick Start

```bash
cd /Users/boram/hermes-merry-ac-discovery
python3 -m pip install -e ".[dev]"
make verify
```

If you use `uv`, the equivalent test command is:

```bash
uv run pytest
```

## Local Configuration

Runtime secrets belong in `.env.local`, which is ignored by Git.

Start from the example file:

```bash
cp configs/runpod.env.example .env.local
```

Minimum variables for the full chain are:

```bash
STRUCTURED_STORE_BACKEND=sqlite
MOTHER_DB_PATH=/Users/boram/hermes-merry-ac-discovery/tmp/hermes/mother.db
REVIEW_SHEET_ID=your-google-sheet-id
AGENT_WORK_QUEUE_SPEC_PATH=configs/agent_work_queue.discovery.json
AGENT_LOOP_JOBS=agent-work-queue
SMINFO_USER_ID=your-sminfo-id
SMINFO_PASSWORD=your-sminfo-password
THEVC_USER_EMAIL=optional-thevc-email
THEVC_PASSWORD=optional-thevc-password
ANTHROPIC_API_KEY=optional-claude-key
```

Do not commit `.env.local`, browser session files, SQLite databases, or generated dashboard files.

## Useful Commands

Run one agent-work-queue pass:

```bash
python3 -m merry_runtime.jobs run agent-work-queue
```

Run the long-lived loop only when the environment is intentionally configured:

```bash
HERMES_ALLOW_UNBOUNDED_LOOP=1 python3 -m merry_runtime.jobs loop
```

Render the local AIOps dashboard:

```bash
python3 -m merry_runtime.jobs render-loop-dashboard --output tmp/hermes/loop-dashboard.html
```

Read a Runpod billing snapshot without changing infrastructure:

```bash
scripts/runpod_cost_audit.sh --days 3
```

Save THE VC credentials to `.env.local` without committing them:

```bash
scripts/save_thevc_credentials.sh
```

## Main Runtime Modules

```text
src/merry_runtime/
  jobs.py                         CLI entrypoint
  runtime_config.py               Environment-backed configuration
  runtime_factory.py              Runtime adapter construction
  agent_loop.py                   Repeating job loop
  job_runner.py                   Job dispatch
  loop_dashboard.py               Local AIOps dashboard renderer
  schema.py                       SQLite/warehouse table schema
  pipelines/
    agent_work_queue.py           Chained queue runner
    crawl_sources.py              Source crawling and candidate extraction
    enrich_sminfo.py              SMINFO queue drain and sheet projection
  ingestion/
    agent_work_queue.py           Durable task helpers
    sminfo_queue.py               SMINFO task normalization/retry helpers
    thevc.py                      THE VC parsing
  adapters/
    sqlite_store.py               SQLite Mother DB adapter
    google_sheets.py              Google Sheets projection adapter
    thevc_playwright.py           Browser-backed THE VC adapter
    sminfo_playwright.py          Browser-backed SMINFO adapter
```

## Documentation

- `docs/ONBOARDING.md`: codebase tour for new contributors and operators.
- `docs/SAFETY.md`: guardrails and safety checklist.
- `docs/runbooks/runpod-staging.md`: staging/runtime operations.
- `configs/runpod.env.example`: environment variable template.
- `.understand-anything/knowledge-graph.json`: generated codebase graph used for onboarding.

## Operator Notes

- Treat Google Sheets as the human review console, not the only source of truth.
- Check `agent_runs`, `agent_work_queue`, `sminfo_enrichment_queue`, and the dashboard before assuming a night run completed.
- Keep crawl/sheet/SMINFO loops on CPU unless a model-serving requirement is added.
- Prefer finite test batches before enabling an unbounded loop.
- When a source site changes or blocks automation, keep the failure visible in queue status and run logs.

## Current Status

The current branch contains the chained queue implementation, accelerator watchlist separation, THE VC Playwright improvements, SMINFO queue integration, local dashboard, and related tests. Before using it as a production workflow, run a real credentialed staging pass and verify the resulting Sheet rows, queue state, and dashboard timestamps.
