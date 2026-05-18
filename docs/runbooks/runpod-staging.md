# Hermes Runpod Staging Runbook

Use this runbook for the primary staging path. Runpod is the execution backend.
GCP is the minimum data layer for BigQuery, GCS, Gmail API, Sheets API, and one
least-privilege runtime service account.

## Backend

Runpod runs the long-lived Hermes agent loop from a private GHCR image:

```bash
ghcr.io/$GHCR_OWNER/hermes-merry:staging
```

The Pod command is:

```bash
python3 -m merry_runtime.jobs loop
```

Cloud Run is optional and belongs to `docs/runbooks/staging-canary.md`.

## Required Values

- `GHCR_OWNER`
- `GCP_PROJECT_ID`
- `BIGQUERY_DATASET`
- `RAW_BUCKET`
- `REVIEW_SHEET_ID`
- `AC_ID`
- `GMAIL_LABEL_ID`
- `SLACK_CHANNEL`
- `SLACK_BOT_TOKEN`
- `GOOGLE_APPLICATION_CREDENTIALS_JSON`
- `WIKI_ROOT=/workspace/hermes/wiki`
- `AGENT_LOOP_JOBS=ingest-sources,resolve-entities,score-candidates,sync-review-sheet,calibrate-scores`
- `AGENT_LOOP_INTERVAL_SECONDS=1800`
- `AGENT_LOOP_MAX_CYCLES=1` for the first canary only

## Stop Conditions

Stop before push, apply, or canary if any condition is true:

- `GHCR_OWNER` is empty.
- `docker buildx` is unavailable.
- `infra/terraform/runpod-staging.tfvars` is absent.
- The active gcloud project differs from `project_id` in
  `infra/terraform/runpod-staging.tfvars`.
- Any staging value contains `prod` or `production`.
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` is written to git, Terraform state, or
  a persistent repo file.
- `WIKI_ROOT` is not under `/workspace/hermes`.
- `REVIEW_SHEET_ID`, `GMAIL_LABEL_ID`, or `SLACK_CHANNEL` points to a
  production resource.

## Build And Push

Build and push the linux/amd64 staging image:

```bash
docker buildx build --platform linux/amd64 \
  -t "ghcr.io/$GHCR_OWNER/hermes-merry:staging" \
  --push .
```

After the helper script is added, prefer:

```bash
GHCR_OWNER="$GHCR_OWNER" PUSH_IMAGE=1 scripts/build_ghcr_staging.sh
```

## Minimum GCP Layer

Create a local uncommitted tfvars file:

```bash
cp infra/terraform/runpod-staging.tfvars.example infra/terraform/runpod-staging.tfvars
```

Edit it with isolated staging IDs only, then verify the active project:

```bash
ACTIVE_PROJECT="$(gcloud config get-value project)"
CONFIG_PROJECT="$(sed -n 's/^project_id *= *"\(.*\)"/\1/p' infra/terraform/runpod-staging.tfvars)"
test "$ACTIVE_PROJECT" = "$CONFIG_PROJECT"
```

Plan and inspect before apply:

```bash
tofu -chdir=infra/terraform plan -var-file=runpod-staging.tfvars
```

Expected plan scope:

- Staging BigQuery dataset and tables.
- Staging GCS raw bucket.
- Hermes runtime service account and least-privilege IAM.
- No Cloud Run jobs.
- No Cloud Scheduler jobs.
- No Artifact Registry repository.
- No Secret Manager secrets.
- No destroy actions.

## Runpod Pod

Configure the Pod with:

```text
Image: ghcr.io/$GHCR_OWNER/hermes-merry:staging
Command: python3 -m merry_runtime.jobs loop
Volume path: /workspace
WIKI_ROOT: /workspace/hermes/wiki
AGENT_LOOP_MAX_CYCLES: 1
```

Store sensitive values as Runpod secrets. `GOOGLE_APPLICATION_CREDENTIALS_JSON`
must be a Runpod secret, not a committed file.

## One-cycle Canary

Set `AGENT_LOOP_MAX_CYCLES=1` for the first Runpod run. Start the Pod and wait
for one loop result.

The Pod command remains:

```bash
python3 -m merry_runtime.jobs loop
```

Verify BigQuery from the operator machine:

```bash
bq query --use_legacy_sql=false \
  'select job_name, status, started_at, finished_at from `PROJECT.DATASET.agent_runs` order by started_at desc limit 10'
```

Verify the persistent wiki path inside the Runpod shell:

```bash
test -d /workspace/hermes/wiki
find /workspace/hermes/wiki -maxdepth 2 -type f | sort | head
```

Only after the one-cycle canary is reviewed, switch:

```text
AGENT_LOOP_MAX_CYCLES=0
AGENT_LOOP_INTERVAL_SECONDS=1800
```
