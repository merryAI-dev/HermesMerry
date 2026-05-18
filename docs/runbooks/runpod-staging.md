# Hermes Runpod Staging Runbook

Use this runbook for the primary staging path. Runpod is the execution backend.
SQLite on the Runpod persistent volume is the primary Mother DB. Google Sheets
is the human operating console, the Obsidian wiki is the readable projection,
and GCP is limited to Google Workspace API access for Gmail and Sheets.
BigQuery is optional warehouse/export infrastructure.

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
- `STRUCTURED_STORE_BACKEND=sqlite`
- `MOTHER_DB_PATH=/workspace/hermes/mother.db`
- `OBJECT_STORE_BACKEND=local`
- `RAW_ROOT=/workspace/hermes/raw`
- `BACKUP_ROOT=/workspace/hermes/backups`
- `REVIEW_SHEET_ID`
- `AC_ID`
- `GMAIL_LABEL_ID`
- `SLACK_CHANNEL`
- `SLACK_BOT_TOKEN`
- `GOOGLE_APPLICATION_CREDENTIALS_JSON`
- `WIKI_ROOT=/workspace/hermes/wiki`
- `AGENT_LOOP_JOBS=ingest-sources,resolve-entities,score-candidates,sync-review-sheet,calibrate-scores,backup-export`
- `AGENT_LOOP_INTERVAL_SECONDS=1800`
- `AGENT_LOOP_MAX_CYCLES=0` for the always-on SQLite loop

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
- `MOTHER_DB_PATH`, `RAW_ROOT`, `BACKUP_ROOT`, or `WIKI_ROOT` is outside
  `/workspace/hermes`.
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

- Runpod local raw storage under `/workspace/hermes/raw` when
  `OBJECT_STORE_BACKEND=local`.
- Hermes runtime service account with Gmail and Sheets API access.
- No required BigQuery dataset.
- No required GCS raw bucket.
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
STRUCTURED_STORE_BACKEND: sqlite
MOTHER_DB_PATH: /workspace/hermes/mother.db
OBJECT_STORE_BACKEND: local
RAW_ROOT: /workspace/hermes/raw
BACKUP_ROOT: /workspace/hermes/backups
AGENT_LOOP_JOBS: ingest-sources,resolve-entities,score-candidates,sync-review-sheet,calibrate-scores,backup-export
AGENT_LOOP_MAX_CYCLES: 0
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
desired status remains `RUNNING`. Delete one-cycle canary Pods after SQLite,
Sheet, wiki, and backup evidence is captured.

## One-cycle Canary

Set `AGENT_LOOP_MAX_CYCLES=1` for the first Runpod run. Start the Pod and wait
for one loop result.

The Pod command remains:

```bash
python3 -m merry_runtime.jobs loop
```

Verify the SQLite Mother DB and backup artifacts inside the Runpod shell:

```bash
test -f /workspace/hermes/mother.db
find /workspace/hermes/backups -maxdepth 3 -type f | sort | tail
```

Verify the persistent wiki path inside the Runpod shell:

```bash
test -d /workspace/hermes/wiki
find /workspace/hermes/wiki -maxdepth 2 -type f | sort | head
```

Verify Sheet console tabs:

```text
Review Queue
Candidate Detail
Evidence
Decision Log
AC Settings
Exploration Queue
Run Log
```

BigQuery is optional. Use it only as a warehouse/export mirror after billing and
IAM are explicitly enabled:

```text
STRUCTURED_STORE_BACKEND=bigquery
BIGQUERY_DATASET=merry_ac_discovery_staging
BIGQUERY_WRITE_MODE=merge
```
