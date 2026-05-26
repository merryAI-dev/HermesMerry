# Hermes x Merry AC Discovery

This repo is the first implementation scaffold for the Hermes x Merry autonomous AC discovery plan.

It builds a frontless MVP around:

- Mother DB entity and signal model
- AC-specific scoring and candidate cards
- Google Sheet review feedback semantics
- Source parsers for article, THE VC investment/M&A cards, info mail, external referral, and internal memo inputs
- Local integration pipelines for ingest, score, and review feedback
- Fake adapters for deterministic no-network integration testing
- Thin production adapter contracts for SQLite, optional BigQuery, Google Sheets, Gmail, and Slack
- SQLite-backed LLM Wiki memory with Obsidian-compatible markdown projections
- Probabilistic entity resolution and logit/probit priority scoring
- Hermes production safety profile
- Whitelisted MCP tool contracts
- SQLite-backed Mother DB and Sheet console as the primary Runpod staging data layer

## Local Checks

```bash
cd /Users/boram/hermes-merry-ac-discovery
python3 -m pip install -e ".[dev]"
make verify
```

OpenTofu is the primary IaC runner for this repo. Terraform is installed for compatibility checks, but do not alternate Terraform and OpenTofu against the same `.terraform.lock.hcl` in one working tree; each tool records provider sources differently.

Use `infra/terraform/runpod-staging.tfvars.example` as the primary staging variable template. `infra/terraform/staging.tfvars.example` remains available for the optional Cloud Run backend.

## Runpod-first staging

The default staging runtime is a Runpod Pod that pulls a private Docker Hub image:

```bash
docker.io/boram1220/hermes-merry:staging
```

Runpod runs the long-lived agent loop:

```bash
python3 -m merry_runtime.jobs loop
```

The primary staging runtime uses a SQLite-backed Mother DB on the Runpod
persistent volume, local raw storage, an Obsidian wiki projection, and Google
Sheets as the human operating console. GCP is reduced to Google Workspace API
access for Gmail and Sheets. BigQuery is optional warehouse/export
infrastructure. Cloud Run is optional and remains available only through the `cloud_run`
Terraform backend mode.

When `REVIEW_SHEET_ID` is configured, `backup-export` also treats the same
Google Sheet as the first backup surface. It rewrites `SQLite Backup`,
`Wiki Backup`, and `Backup Manifest` with the latest Mother DB rows, markdown
wiki chunks, and artifact manifest on every loop.

## Runtime Jobs

The container entrypoint is `python3 -m merry_runtime.jobs`. Runtime adapters are built from env/ADC:

```bash
GCP_PROJECT_ID=my-project
STRUCTURED_STORE_BACKEND=sqlite
MOTHER_DB_PATH=/home/hermes/hermes/mother.db
BIGQUERY_DATASET=merry_ac_discovery
RAW_BUCKET=my-raw-bucket
OBJECT_STORE_BACKEND=local
RAW_ROOT=/home/hermes/hermes/raw
BACKUP_ROOT=/home/hermes/hermes/backups
REVIEW_SHEET_ID=google-sheet-id
AC_ID=ac_climate
GMAIL_LABEL_ID=Label_123
GMAIL_USER_ID=operator@mysc.co.kr
GMAIL_FROM_NAME=Merry
APPS_SCRIPT_DRAFT_WEBHOOK_URL=https://script.google.com/macros/s/deployment-id/exec
APPS_SCRIPT_DRAFT_SECRET=runpod-secret-hermes-draft-gateway
APPS_SCRIPT_DRAFT_TIMEOUT_SECONDS=10
SLACK_CHANNEL=C123
SLACK_BOT_TOKEN=xoxb-...
KVIC_API_KEY=public-kvic-api-key
KVIC_SYNC_INTERVAL_SECONDS=86400
KVIC_REQUEST_TIMEOUT_SECONDS=15
KVIC_FUND_DESCRIPTION_BATCH_LIMIT=50
KVIC_FUND_DESCRIPTION_STALE_DAYS=30
KVIC_FUND_SEARCH_MAX_RESULTS=5
ANTHROPIC_API_KEY=runpod-secret-anthropic-key
HERMES_LLM_MODEL=claude-sonnet-4-6
HERMES_LLM_TIMEOUT_SECONDS=30
INVESTOR_RESEARCH_BATCH_LIMIT=20
INVESTOR_RESEARCH_STALE_DAYS=7
INVESTOR_RESEARCH_SEARCH_MAX_RESULTS=5
THEVC_USER_EMAIL=
THEVC_PASSWORD=
THEVC_BROWSER_STATE_PATH=/home/hermes/hermes/thevc-state.json
THEVC_BROWSER_HEADLESS=1
THEVC_BROWSER_CHANNEL=
THEVC_TIMEOUT_SECONDS=30
WIKI_ROOT=/home/hermes/hermes/wiki
HERMES_AGENT_ID=runpod-hermes-staging
CRAWL_SHEET_TAB=Crawl Sources
CRAWL_TARGETS_JSON=[{"url":"https://thevc.kr/","source_kind":"thevc_investment_ma","max_cards":20,"max_pages":3,"thevc_backend":"playwright"},{"url":"https://platum.kr/archives/category/investment","source_kind":"platum_investment_news","max_articles":24,"max_pages":2,"portfolio_watchlist_path":"configs/portfolio_watchlist.txt"},{"url":"https://platum.kr/archives/category/investment","source_kind":"platum_investment_news","max_articles":24,"max_pages":2,"portfolio_watchlist_sheet_tab":"Accelerator Watchlist","portfolio_news_sheet_tab":"Accelerator News","portfolio_news_slack_heading":"Hermes 육성기업 뉴스 감지","portfolio_notify_recent_days":2}]
AGENT_WORK_QUEUE_SPEC_PATH=configs/agent_work_queue.discovery.json
AGENT_WORK_QUEUE_BATCH_LIMIT=10
AGENT_LOOP_JOBS=agent-work-queue
AGENT_LOOP_INTERVAL_SECONDS=3600
AGENT_LOOP_MAX_CYCLES=0
HERMES_ALLOW_UNBOUNDED_LOOP=1
```

`AGENT_LOOP_INTERVAL_SECONDS=3600` with `AGENT_LOOP_MAX_CYCLES=0` means the
Hermes agent stays alive and repeats the configured jobs every 1 hour. Hermes
requires `HERMES_ALLOW_UNBOUNDED_LOOP=1` for that mode so a canary or GPU Pod
does not accidentally become a long-running compute bill. Keep the crawl/sheet
control plane on a CPU or finite batch runtime. Run Gemma, Qwen, or other local
LLM serving as a separate scale-to-zero Serverless endpoint unless low latency
explicitly justifies active workers.
`sync-kvic-funds` is safe to keep in that hourly loop because it enforces
`KVIC_SYNC_INTERVAL_SECONDS=86400`; it refreshes the KVIC investor/fund snapshot
every day and otherwise records a skipped run without calling KVIC again.

For a read-only Runpod cost snapshot, run:

```bash
scripts/runpod_cost_audit.sh --days 3
```

Supported job commands:

```bash
python3 -m merry_runtime.jobs loop
python3 -m merry_runtime.jobs run crawl-sources --sources-file crawl-targets.json
python3 -m merry_runtime.jobs run ingest-sources --sources-file sources.json
python3 -m merry_runtime.jobs run ingest-sources
python3 -m merry_runtime.jobs run score-candidates --ac-id ac_climate
python3 -m merry_runtime.jobs run sync-review-sheet --ac-id ac_climate
python3 -m merry_runtime.jobs run backup-export
python3 -m merry_runtime.jobs run weekly-summary
python3 -m merry_runtime.jobs run draft-outreach-emails
python3 -m merry_runtime.jobs run sync-kvic-funds
python3 -m merry_runtime.jobs run research-investors
python3 -m merry_runtime.jobs render-loop-dashboard --output tmp/hermes/loop-dashboard.html
```

Without `--sources-file` or `--sources-json`, `crawl-sources` reads URL targets
from the `Crawl Sources` Sheet tab. The first crawler target is THE VC public
investment/M&A cards on `https://thevc.kr/`; it does not call `/api` paths.
Set `thevc_backend=playwright` on that row to use a real browser session for
the visible "더 보기" / "다음 페이지 보기" flow. `THEVC_USER_EMAIL` and
`THEVC_PASSWORD` are optional for public crawling but enable the logged-in
session, and `THEVC_BROWSER_STATE_PATH` stores reusable cookies outside Git.
By default, failed automated login falls back to public crawling; set
`thevc_login_required=true` only when the run should fail without login. Login
fallback and THE VC human-verification blocks are recorded as crawl warnings in
`agent_runs.error_message` and, for Sheet-driven runs, the `Crawl Sources`
`error_message` column.
Platum portfolio monitoring and accelerator-company monitoring should use
separate rows: keep the investment list in `Portfolio News`, and put accelerator
companies in the `Accelerator Watchlist` tab so row add/edit/delete becomes the
runtime CRUD surface. Accelerator matches are written to `Accelerator News`;
`portfolio_notify_recent_days=2` limits Slack to today and yesterday while still
recording all matched rows in the sheet.
If `crawl4ai` is installed in the runtime image, the crawler uses it first;
otherwise it falls back to a bounded stdlib HTML fetch for server-rendered pages.
Without source flags, `ingest-sources` reads Gmail messages from
`GMAIL_LABEL_ID`.

`draft-outreach-emails` reads `Candidate Detail.contact_email`, creates Gmail
drafts only, and records the draft state in SQLite plus the `Outreach Drafts`
Sheet tab. It does not send email. If `APPS_SCRIPT_DRAFT_WEBHOOK_URL` and
`APPS_SCRIPT_DRAFT_SECRET` are set, Hermes creates drafts through the Apps
Script gateway in `apps_script/gmail_draft_gateway/`. Otherwise it falls back
to the direct Gmail API client. `GMAIL_USER_ID` only applies to that direct
fallback path.

`sync-kvic-funds` reads the KVIC public fund-status API, stores
`kvic_fund_types`, `kvic_funds`, `kvic_investor_managers`, and
`kvic_fund_descriptions` in SQLite, then rewrites the `Investor DB` and
`Fund DB` Sheet tabs as the human-facing investor/fund cockpit. Fund
descriptions are evidence-backed web-search projections: Hermes searches the
public web for each fund, stores the selected title/URL/snippet in SQLite, and
keeps the search batch bounded through `KVIC_FUND_DESCRIPTION_BATCH_LIMIT`.
When `ANTHROPIC_API_KEY` is configured, the same job sends only that selected
evidence to Claude as a bounded encoder and stores a source-grounded fund
description. Hermes never accepts a Claude-provided source URL unless it matches
the search evidence URL already selected for that fund.
When public search has no matching evidence, Hermes still writes a conservative
KVIC-field summary and marks the description status as `no_result`.

`research-investors` reads `kvic_investor_managers`, searches public web
evidence for investor AUM/profile facts, and sends that evidence to Claude as a
bounded encoder. Claude returns a source-grounded JSON object; Hermes decodes it
into `investor_external_profiles` and rewrites `Investor DB` with separate
`KVIC 공개 ...` and `외부 공개 AUM ...` columns.

To set up the Apps Script gateway, create a Google Apps Script project, copy
`apps_script/gmail_draft_gateway/Code.gs` and `appsscript.json`, set script
properties `HERMES_DRAFT_SECRET`, `HERMES_DRAFT_FROM_NAME`, and optionally
`HERMES_DRAFT_MAX_PER_DAY`, then deploy as a web app that executes as the owner.
Store the deployment URL and shared secret in Runpod secrets.

## Runtime Layout

```text
src/merry_runtime/
  models.py              Core Mother DB, AC, score, card, review models
  entity_resolution.py   Deterministic first-pass merge/review decisions
  scoring.py             Evidence-first AC scoring
  review_sync.py         Sheet decision validation and card status updates
  pii.py                 PII detection/redaction before LLM payloads
  hermes_profile.py      Production Hermes safety validation
  schema.py              Structured table schema source of truth
  jobs.py                Runtime job CLI entrypoint
  runtime_config.py      Env-backed runtime configuration
  runtime_factory.py     ADC/client-backed production adapter factory
  job_runner.py          Job routing for ingest, score, review sync, summary
  ontology.py            Source-channel semantics and in-process relation model
  wiki_store.py          SQLite wiki memory and Obsidian markdown projection
  probabilistic_resolution.py  Entity matching probability model
  probabilistic_scoring.py     Priority utility/probability and exploration routing
  adapters/              Fake and production adapter contracts
  ingestion/             Deterministic source parsers and web crawlers
  pipelines/             Crawl, ingest, scoring, and review feedback jobs

src/merry_mcp/
  registry.py            Whitelisted tool contracts Hermes can call
  server.py              Tool dispatcher with payload validation and PII redaction

configs/
  hermes-production-profile.json
  ac_profiles.example.json
  source_channels.example.json
  scoring_weights.json

infra/terraform/
  Optional BigQuery, GCS, Secret Manager, Cloud Run Jobs, Scheduler, IAM
```

## Safety Boundary

Hermes should run with `configs/hermes-production-profile.json`. Generic local tools are disabled, and the agent only receives the domain-specific MCP contracts in `merry_mcp.registry`.

See `docs/SAFETY.md` for the explicit guardrail checklist.

## Next Implementation Steps

1. Put THE VC and other allowed public crawl targets in the `Crawl Sources` Sheet tab.
2. Run the SQLite-first Runpod loop with `crawl-sources` and `sync-kvic-funds` enabled and verify Mother DB/Wiki accumulation.
3. Use `Investor DB` to connect The VC investor mentions to KVIC fund mandates.
4. Rewire `score-candidates` from AC-specific tabs to `Review Queue`.
5. Wire Sheet decisions back into SQLite feedback/calibration.
6. Add optional BigQuery export only after billing and IAM are intentionally enabled.
