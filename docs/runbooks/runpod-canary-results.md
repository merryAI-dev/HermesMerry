# Hermes Runpod Canary Results

## Run

- Date: 2026-05-18 17:23:03 KST (+0900)
- Operator: local Codex session with gcloud account `mwbyun1220@mysc.co.kr`
- GHCR image digest: not pushed; local image
  `sha256:3136562e304acd9f9b22714991ad4156ad1ab6393242fbff5773a24467f838d1`
- Runpod Pod ID: not created
- Runpod image: `ghcr.io/merryai-dev/hermes-merry:staging` planned, push blocked by missing GitHub `write:packages` scope
- GCP project: `yapnotes-app-2`
- BigQuery dataset: `merry_ac_discovery_staging`
- GCS raw bucket: not created; project billing is disabled for GCS bucket creation
- Object store backend: `local`
- Raw root: `/workspace/hermes/raw`
- Sheet tab: not verified
- Slack channel: not verified
- Wiki path: `/workspace/hermes/wiki`

## Evidence

- Docker guardrail: `BIGQUERY_WRITE_MODE=append` with unbounded `loop` exits
  with code `2` before runtime construction
- Docker one-shot ingest: `run_bb3dcd25f56d`
- Docker one-cycle loop: `calibrate-scores`, `run_calibrate_ac_climate_c9e58d56e2b8`
- BigQuery agent_runs row: latest rows include `calibrate-scores`, `ingest-sources`,
  `ingest-ac-profiles`, and `ingest-sources` with `success`
- BigQuery row counts: `raw_sources=2`, `mother_entities=2`, `signals=2`,
  `ac_profiles=1`
- GCS raw object: not applicable for Runpod local raw storage; local raw files
  written under `/tmp/hermes-runpod-raw/raw/external_referral/`
- Sheet row count before: not checked
- Sheet row count after: not checked
- Slack message timestamp: not checked
- Wiki page path: `/tmp/hermes-runpod-wiki/wiki/entities/runpod-guardrail-carefarm.md`
- Terraform output: `agent_service_account_email = hermes-merry-agent-staging@yapnotes-app-2.iam.gserviceaccount.com`
- Terraform output: `cloud_run_jobs = []`
- Terraform output: `artifact_registry_repository = ""`

## Result

- Canary status: local Docker canary passed; remote Runpod Pod canary blocked
  before Pod creation
- Failed job count: not available
- Human review required: yes, approve GitHub `write:packages` scope or provide a
  registry token, then configure Runpod Pod secrets and isolated Sheet/Slack
  targets

## Rollback command

```bash
stop the Runpod Pod from the Runpod console
```
