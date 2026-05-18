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
SLACK_CHANNEL=C123
SLACK_BOT_TOKEN=xoxb-...
WIKI_ROOT=/home/hermes/hermes/wiki
CRAWL_SHEET_TAB=Crawl Sources
CRAWL_TARGETS_JSON=[{"url":"https://thevc.kr/","source_kind":"thevc_investment_ma","max_cards":20}]
AGENT_LOOP_JOBS=crawl-sources,resolve-entities,backup-export
AGENT_LOOP_INTERVAL_SECONDS=3600
AGENT_LOOP_MAX_CYCLES=0
```

`AGENT_LOOP_INTERVAL_SECONDS=3600` with `AGENT_LOOP_MAX_CYCLES=0` means the
Hermes agent stays alive and repeats the configured jobs every 1 hour.

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
```

Without `--sources-file` or `--sources-json`, `crawl-sources` reads URL targets
from the `Crawl Sources` Sheet tab. The first crawler target is THE VC public
investment/M&A cards on `https://thevc.kr/`; it does not call `/api` paths.
If `crawl4ai` is installed in the runtime image, the crawler uses it first;
otherwise it falls back to a bounded stdlib HTML fetch for server-rendered pages.
Without source flags, `ingest-sources` reads Gmail messages from
`GMAIL_LABEL_ID`.

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
2. Run the SQLite-first Runpod loop with `crawl-sources` enabled and verify Mother DB/Wiki accumulation.
3. Rewire `score-candidates` from AC-specific tabs to `Review Queue`.
4. Wire Sheet decisions back into SQLite feedback/calibration.
5. Add optional BigQuery export only after billing and IAM are intentionally enabled.
