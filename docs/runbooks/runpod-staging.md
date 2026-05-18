# Hermes Runpod Staging Runbook

Use this runbook for the primary staging path. Runpod is the execution backend.
GCP is the minimum data layer for BigQuery, GCS, Gmail API, Sheets API, and one
least-privilege runtime service account.

## Backend

Runpod runs the long-lived Hermes agent loop from a private Docker Hub image:

```bash
docker.io/boram1220/hermes-merry:staging
```

The Pod command is:

```bash
python3 -m merry_runtime.jobs loop
```

Cloud Run is optional and belongs to `docs/runbooks/staging-canary.md`.

## Required Values

- `DOCKERHUB_USERNAME=boram1220`
- `GCP_PROJECT_ID`
- `BIGQUERY_DATASET`
- `RAW_BUCKET`
- `OBJECT_STORE_BACKEND=local`
- `RAW_ROOT=/workspace/hermes/raw`
- `BIGQUERY_WRITE_MODE=merge` for the always-on loop
- `BIGQUERY_WRITE_MODE=append` only with `AGENT_LOOP_MAX_CYCLES=1` when the
  staging GCP project has billing disabled and BigQuery DML is unavailable
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

- `docker buildx` is unavailable.
- Docker Hub is not logged in as `boram1220`.
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
  -t "docker.io/boram1220/hermes-merry:staging" \
  --push .
```

Also publish an immutable tag for the exact commit:

```bash
COMMIT="$(git rev-parse --short HEAD)"
docker tag hermes-merry:runpod-staging "docker.io/boram1220/hermes-merry:staging-${COMMIT}"
docker push "docker.io/boram1220/hermes-merry:staging-${COMMIT}"
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
- Staging GCS raw bucket only when `create_raw_bucket = true`.
- Runpod local raw storage under `/workspace/hermes/raw` when
  `OBJECT_STORE_BACKEND=local`.
- Hermes runtime service account and least-privilege IAM.
- No Cloud Run jobs.
- No Cloud Scheduler jobs.
- No Artifact Registry repository.
- No Secret Manager secrets.
- No destroy actions.

## Runpod Pod

Configure the Pod with:

```text
Image: docker.io/boram1220/hermes-merry:staging
Command: python3 -m merry_runtime.jobs loop
Volume path: /workspace
WIKI_ROOT: /workspace/hermes/wiki
OBJECT_STORE_BACKEND: local
RAW_ROOT: /workspace/hermes/raw
BIGQUERY_WRITE_MODE: append
AGENT_LOOP_MAX_CYCLES: 1
```

Store sensitive values as Runpod secrets. `GOOGLE_APPLICATION_CREDENTIALS_JSON`
must be a Runpod secret, not a committed file. For the private image, configure
Runpod Container Registry Auth with the Docker Hub user `boram1220` and a Docker
Hub access token.

The prepared one-cycle template is:

```text
Template: hermes-merry-staging-one-cycle
Template ID: 7s0amucf96
GCP secret reference: {{ RUNPOD_SECRET_hermes_gcp_sa_staging_json }}
```

If the Runpod REST API key cannot access GraphQL `secretCreate`, create the
`hermes_gcp_sa_staging_json` secret in the Runpod console before launching the
template. Do not paste the service account JSON into plain Pod environment
variables for the always-on runtime.

The one-cycle template overrides the container command to run the loop once and
then sleep:

```text
dockerEntrypoint: /bin/sh -lc
dockerStartCmd: runpod-entrypoint python3 -m merry_runtime.jobs loop; status=$?; echo HERMES_CANARY_DONE status=$status; sleep infinity
```

This prevents Runpod from restarting a finite command repeatedly while the Pod
desired status remains `RUNNING`. Delete the Pod after BigQuery evidence is
captured.

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

`BIGQUERY_WRITE_MODE=append` only with `AGENT_LOOP_MAX_CYCLES=1`; it writes
direct load-job appends and can duplicate logical rows if left on in a loop.

Only after the one-cycle canary is reviewed, switch:

```text
BIGQUERY_WRITE_MODE=merge
AGENT_LOOP_MAX_CYCLES=0
AGENT_LOOP_INTERVAL_SECONDS=1800
```
