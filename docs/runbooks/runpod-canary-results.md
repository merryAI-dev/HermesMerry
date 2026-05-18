# Hermes Runpod Canary Results

## Run

- Date: 2026-05-18 17:07:51 KST (+0900)
- Operator: local Codex session with gcloud account `mwbyun1220@mysc.co.kr`
- GHCR image digest: not pushed; local image `sha256:77b534c7b3d624ccc79f9693e0713f65686c8d7bf68dedb6887d914a80a8a5b5`
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

- BigQuery agent_runs row: not created; Pod canary not run
- GCS raw object: not applicable for Runpod local raw storage
- Sheet row count before: not checked
- Sheet row count after: not checked
- Slack message timestamp: not checked
- Wiki page path: not created; Pod canary not run
- Terraform output: `agent_service_account_email = hermes-merry-agent-staging@yapnotes-app-2.iam.gserviceaccount.com`
- Terraform output: `cloud_run_jobs = []`
- Terraform output: `artifact_registry_repository = ""`

## Result

- Canary status: blocked before Runpod Pod creation
- Failed job count: not available
- Human review required: yes, approve GitHub `write:packages` scope or provide a registry token

## Rollback command

```bash
stop the Runpod Pod from the Runpod console
```
