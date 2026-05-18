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
- GCS raw bucket: not created; project billing is disabled for GCS bucket creation
- Object store backend: `local`
- Raw root: `/workspace/hermes/raw`
- Sheet tab: not verified
- Slack channel: not verified
- Wiki path: `/workspace/hermes/wiki`
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

## Result

- Canary status: local Docker canary passed and existing remote Runpod Pod
  canary passed
- Failed job count: 0 for the focused Runpod canary path
- Human review required: configure durable GCP credentials for the Runpod Pod,
  then replace the SSH bootstrap with the private Docker Hub image and configure
  isolated Sheet/Slack targets

## Rollback command

```bash
stop the Runpod Pod from the Runpod console
```
