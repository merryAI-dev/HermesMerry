# Hermes x Merry AC Discovery

This repo is the first implementation scaffold for the Hermes x Merry autonomous AC discovery plan.

It builds a frontless MVP around:

- Mother DB entity and signal model
- AC-specific scoring and candidate cards
- Google Sheet review feedback semantics
- Source parsers for article, info mail, external referral, and internal memo inputs
- Local integration pipelines for ingest, score, and review feedback
- Fake adapters for deterministic no-network integration testing
- Thin production adapter contracts for GCS, BigQuery, Google Sheets, Gmail, and Slack
- SQLite-backed LLM Wiki memory with Obsidian-compatible markdown projections
- Probabilistic entity resolution and logit/probit priority scoring
- Hermes production safety profile
- Whitelisted MCP tool contracts
- BigQuery, GCS, Cloud Run Jobs, Cloud Scheduler Terraform skeleton

## Local Checks

```bash
cd /Users/boram/hermes-merry-ac-discovery
python3 -m pip install -e ".[dev]"
make verify
```

OpenTofu is the primary IaC runner for this repo. Terraform is installed for compatibility checks, but do not alternate Terraform and OpenTofu against the same `.terraform.lock.hcl` in one working tree; each tool records provider sources differently.

Use `infra/terraform/staging.tfvars.example` as the staging variable template. Slack and LLM tokens are referenced through Secret Manager; create secret versions before running the scheduled jobs.

## Cloud Run Jobs

The container entrypoint is `python3 -m merry_runtime.jobs`. Runtime adapters are built from env/ADC:

```bash
GCP_PROJECT_ID=my-project
BIGQUERY_DATASET=merry_ac_discovery
RAW_BUCKET=my-raw-bucket
REVIEW_SHEET_ID=google-sheet-id
AC_ID=ac_climate
GMAIL_LABEL_ID=Label_123
SLACK_CHANNEL=C123
SLACK_BOT_TOKEN=xoxb-...
WIKI_ROOT=/tmp/hermes-merry-wiki
```

Supported job commands:

```bash
python3 -m merry_runtime.jobs run ingest-sources --sources-file sources.json
python3 -m merry_runtime.jobs run ingest-sources
python3 -m merry_runtime.jobs run score-candidates --ac-id ac_climate
python3 -m merry_runtime.jobs run sync-review-sheet --ac-id ac_climate
python3 -m merry_runtime.jobs run weekly-summary
```

Without `--sources-file` or `--sources-json`, `ingest-sources` reads Gmail messages from `GMAIL_LABEL_ID`.

## Runtime Layout

```text
src/merry_runtime/
  models.py              Core Mother DB, AC, score, card, review models
  entity_resolution.py   Deterministic first-pass merge/review decisions
  scoring.py             Evidence-first AC scoring
  review_sync.py         Sheet decision validation and card status updates
  pii.py                 PII detection/redaction before LLM payloads
  hermes_profile.py      Production Hermes safety validation
  schema.py              BigQuery table schema source of truth
  jobs.py                Cloud Run job CLI entrypoint
  runtime_config.py      Env-backed runtime configuration
  runtime_factory.py     ADC/client-backed production adapter factory
  job_runner.py          Job routing for ingest, score, review sync, summary
  ontology.py            Source-channel semantics and in-process relation model
  wiki_store.py          SQLite wiki memory and Obsidian markdown projection
  probabilistic_resolution.py  Entity matching probability model
  probabilistic_scoring.py     Priority utility/probability and exploration routing
  adapters/              Fake and production adapter contracts
  ingestion/             Deterministic source parsers
  pipelines/             Ingest, scoring, and review feedback jobs

src/merry_mcp/
  registry.py            Whitelisted tool contracts Hermes can call
  server.py              Tool dispatcher with payload validation and PII redaction

configs/
  hermes-production-profile.json
  ac_profiles.example.json
  source_channels.example.json
  scoring_weights.json

infra/terraform/
  BigQuery, GCS, Secret Manager, Cloud Run Jobs, Scheduler, IAM
```

## Safety Boundary

Hermes should run with `configs/hermes-production-profile.json`. Generic local tools are disabled, and the agent only receives the domain-specific MCP contracts in `merry_mcp.registry`.

See `docs/SAFETY.md` for the explicit guardrail checklist.

## Next Implementation Steps

1. Bind real GCP and Google Workspace clients from environment/ADC in `merry_runtime.jobs`.
2. Wire pipeline outputs into `SQLiteWikiStore` so each ingest updates the Obsidian wiki projection.
3. Build and push the Cloud Run image, then apply `infra/terraform` in a staging GCP project.
4. Load the first AC profile and run a 50-candidate dry run before scaling toward the 1,000-candidate Mother DB target.
5. Add score calibration from human review decisions.
