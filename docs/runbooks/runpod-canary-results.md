# Hermes Runpod Canary Results

## Run

- Date: 2026-05-18 17:53:15 KST (+0900)
- Operator: local Codex session with gcloud account `mwbyun1220@mysc.co.kr`
- Docker Hub image digest:
  `sha256:3136562e304acd9f9b22714991ad4156ad1ab6393242fbff5773a24467f838d1`
- Docker Hub image: `docker.io/boram1220/hermes-merry:staging`
- Docker Hub immutable image: `docker.io/boram1220/hermes-merry:staging-096cbea`
- Runpod registry auth ID: `cmpayp7w3004nlb076xogtx3r`
- Runpod Pod ID: `yoe3dvzrjhi72r`
- Runpod image: existing Pod image
  `runpod/pytorch:1.0.3-cu1281-torch280-ubuntu2404`; Docker Hub image pull was
  verified through a short-lived CPU smoke Pod
- GCP project: `yapnotes-app-2`
- BigQuery dataset: `merry_ac_discovery_staging`
- SQLite Mother DB: planned primary runtime path `/workspace/hermes/mother.db`
- GCS raw bucket: not created; project billing is disabled for GCS bucket creation
- Object store backend: `local`
- Raw root: `/workspace/hermes/raw`
- Sheet tab: not verified
- Slack channel: not verified
- Wiki path: `/workspace/hermes/wiki`
- backup-export: planned primary backup job for SQLite, CSV, JSONL, and wiki
  archive artifacts under `/workspace/hermes/backups`
- Code path: `/workspace/hermes/releases/1652d76`
- Active symlink: `/workspace/hermes/current`
- Canary venv: `/tmp/hermes-venv-1652d76`

## Evidence

- Docker guardrail: `BIGQUERY_WRITE_MODE=append` with unbounded `loop` exits
  with code `2` before runtime construction
- Docker one-shot ingest: `run_bb3dcd25f56d`
- Docker one-cycle loop: `calibrate-scores`, `run_calibrate_ac_climate_c9e58d56e2b8`
- Docker Hub push: `staging` and `staging-096cbea` both pushed with digest
  `sha256:3136562e304acd9f9b22714991ad4156ad1ab6393242fbff5773a24467f838d1`
- Runpod private pull smoke: CPU Pod `6btmmuzcep26cc` started from
  `docker.io/boram1220/hermes-merry:staging-096cbea`, reached `RUNNING`, and
  was deleted immediately after verification
- Runpod bootstrap: uploaded committed files only with `git archive HEAD`;
  no `.git`, `tfvars`, Terraform state, local credentials, caches, raw data, or
  wiki data were transferred
- Runpod smoke checks: `validate-hermes-profile` passed, schema rendered, and
  `35 passed` for focused runtime/adapter/docs tests under `env -i`
- Runpod credential path: long-lived service account key creation failed with
  `iam.serviceAccountKeys.create` denied; one-shot canary used a short-lived
  ADC access token delivered over SSH stdin and did not write a credential file
- Runpod one-shot ingest: `run_864ff3778a62`
- BigQuery agent_runs row: latest rows include `ingest-sources`,
  `calibrate-scores`, `ingest-sources`, `ingest-ac-profiles`, and
  `ingest-sources` with `success`
- BigQuery row counts: `raw_sources=3`, `mother_entities=3`, `signals=3`,
  `ac_profiles=1`
- GCS raw object: not applicable for Runpod local raw storage; local raw files
  written under `/workspace/hermes/raw/raw/external_referral/`
- Sheet row count before: not checked
- Sheet row count after: not checked
- Slack message timestamp: not checked
- Wiki page path:
  `/workspace/hermes/wiki/wiki/entities/runpod-token-hermes-carefarm.md`
- Terraform output: `agent_service_account_email = hermes-merry-agent-staging@yapnotes-app-2.iam.gserviceaccount.com`
- Terraform output: `cloud_run_jobs = []`
- Terraform output: `artifact_registry_repository = ""`
- GCP ADC identity: `ai@mysc.co.kr`; active `gcloud` user
  `mwbyun1220@mysc.co.kr` has narrower project permissions, so runtime checks
  must use ADC rather than the active gcloud account
- GCP API enablement: `gmail.googleapis.com`, `sheets.googleapis.com`,
  `drive.googleapis.com`, and `iamcredentials.googleapis.com` were enabled
  through Service Usage on 2026-05-18
- GCP billing status: `billingEnabled=false`; BigQuery read/query jobs work,
  but DML/MERGE fails with the free-tier billing restriction
- BigQuery ADC row counts after the Runpod canary:
  `raw_sources=3`, `mother_entities=3`, `signals=3`, `agent_runs=5`
- Runpod REST API auth: valid for Pods, Templates, and Container Registry Auths
- Runpod GraphQL API auth: returned HTTP 403 for `myself` and `secretCreate`,
  so Runpod secrets still require console setup or a GraphQL-enabled API key
- Runpod template: `hermes-merry-staging-one-cycle`, id `7s0amucf96`, image
  `docker.io/boram1220/hermes-merry:staging-096cbea`, registry auth
  `cmpayp7w3004nlb076xogtx3r`, `BIGQUERY_WRITE_MODE=append`, and
  `AGENT_LOOP_MAX_CYCLES=1`
- Runpod secret: `hermes_gcp_sa_staging_json` was created in the Runpod console
  on 2026-05-18
- Runpod one-cycle template launch: Pod `fwwbdffmacf59k`, cost `$0.06/hr`,
  image `docker.io/boram1220/hermes-merry:staging-096cbea`
- Runpod canary BigQuery evidence after launch: new success rows included
  `resolve-entities` and `calibrate-scores`
- Runpod restart behavior: the finite one-cycle command was restarted by Runpod
  while desired status stayed `RUNNING`, so the canary Pod produced duplicate
  success rows before deletion
- Runpod canary cleanup: Pod `fwwbdffmacf59k` was deleted successfully; follow-up
  Pod list showed `CANARY_PRESENT 0`
- Runpod template hardening: `hermes-merry-staging-one-cycle` now runs the loop
  once, prints `HERMES_CANARY_DONE`, then sleeps to avoid repeated restarts
- SQLite-first image push: `docker.io/boram1220/hermes-merry:staging-cb0ddd0`
  pushed with digest
  `sha256:5b8c7757f960895c87d2822ddf7f5efcfde7a2c23eb373f602d266ad277ee9dd`
- SQLite-first Docker smoke: `validate-hermes-profile` passed and
  `run backup-export` produced SQLite, CSV, JSONL, wiki archive, and manifest
  paths without requiring Google ADC
- Runpod template update: template `7s0amucf96` renamed to
  `hermes-merry-staging-sqlite-canary`, image
  `docker.io/boram1220/hermes-merry:staging-cb0ddd0`, env
  `STRUCTURED_STORE_BACKEND=sqlite`, `MOTHER_DB_PATH=/workspace/hermes/mother.db`,
  `BACKUP_ROOT=/workspace/hermes/backups`
- Runpod SQLite image pull smoke: Pod `l7tqb76utbrt8g` reached `RUNNING` from
  the SQLite-first template at `$0.06/hr` and was deleted successfully with HTTP
  204

## Result

- Canary status: local Docker canary passed and existing remote Runpod Pod
  canary passed
- Failed job count: 0 for the focused Runpod canary path
- Human review required: enable GCP billing before switching the runtime to
  `BIGQUERY_WRITE_MODE=merge` and an unbounded loop.

## Rollback command

```bash
stop the Runpod Pod from the Runpod console
```
