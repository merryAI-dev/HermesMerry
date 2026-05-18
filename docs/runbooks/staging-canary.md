# Hermes Staging Canary Runbook

Use this runbook only for an isolated staging canary. The canary uses synthetic
data and must not touch production Google Cloud, Google Workspace, or Slack
resources.

## Preconditions

- Confirm the active gcloud project is the staging project:

  ```bash
  gcloud config get-value project
  ```

- Confirm these APIs are enabled in the staging project: Cloud Run, Cloud
  Scheduler, BigQuery, Cloud Storage, Artifact Registry, Secret Manager, Gmail
  API, and Sheets API.
- Confirm Slack Web API access is available through a staging Slack app and bot
  token for the Cloud Run `weekly-summary` job.
- Confirm `infra/terraform/staging.tfvars` exists and points only to staging
  resources.
- Confirm `project_id`, `dataset_id`, `raw_bucket_name`, `image_uri`,
  `service_account_id`, and `scheduler_service_account_id` in
  `infra/terraform/staging.tfvars` are staging IDs.
- Confirm `review_sheet_id` is a staging Sheet.
- Confirm `gmail_label_id` is a staging Gmail label.
- Confirm `slack_channel` is a staging Slack channel for the Cloud Run
  `weekly-summary` path.
- Confirm Secret Manager versions exist for `llm_api_key_secret_id` and
  `slack_bot_token_secret_id`.
- Confirm `ops_alert_email` is a staging/operator address, or
  `enable_ops_alerts = false`.

## Stop Condition

Stop before running any apply, image push, Cloud Run job command, or local
synthetic ingest if any resource ID is production, if the active gcloud project
is not the staging project, or if `infra/terraform/staging.tfvars` is absent.
Also stop if any local environment export differs from
`infra/terraform/staging.tfvars`, or if `STAGING_IMAGE_URI` does not contain the
staging project and end with `:staging`.

Do not run these commands when the stop condition is true:

- `tofu -chdir=infra/terraform apply -var-file=staging.tfvars`
- `docker push`
- `gcloud run jobs execute`
- `python3 -m merry_runtime.jobs run ingest-sources`

## Staging Shell Values

Before running Docker, local ingest, or evidence commands, copy these values
exactly from `infra/terraform/staging.tfvars`. Do not infer the Docker URI from
Terraform outputs; Cloud Run uses the full `image_uri` variable.

```bash
export STAGING_PROJECT='...'       # project_id
export STAGING_DATASET='...'       # dataset_id
export STAGING_RAW_BUCKET='...'    # raw_bucket_name
export STAGING_IMAGE_URI='...'     # image_uri
export STAGING_WIKI_ROOT='...'     # wiki_root
```

Check the copied values before continuing. Stop if any printed value differs
from `infra/terraform/staging.tfvars`.

```bash
printf 'STAGING_PROJECT=%s\n' "$STAGING_PROJECT"
printf 'STAGING_DATASET=%s\n' "$STAGING_DATASET"
printf 'STAGING_RAW_BUCKET=%s\n' "$STAGING_RAW_BUCKET"
printf 'STAGING_IMAGE_URI=%s\n' "$STAGING_IMAGE_URI"
printf 'STAGING_WIKI_ROOT=%s\n' "$STAGING_WIKI_ROOT"

ACTIVE_PROJECT="$(gcloud config get-value project)"
test "$ACTIVE_PROJECT" = "$STAGING_PROJECT" || {
  echo "STOP: active gcloud project is not the staging project"
  exit 1
}

case "$STAGING_IMAGE_URI" in
  *"$STAGING_PROJECT"*":staging") ;;
  *)
    echo "STOP: STAGING_IMAGE_URI must contain STAGING_PROJECT and end with :staging"
    exit 1
    ;;
esac

case "$(printf '%s\n' \
  "$STAGING_PROJECT" \
  "$STAGING_DATASET" \
  "$STAGING_RAW_BUCKET" \
  "$STAGING_IMAGE_URI" \
  "$STAGING_WIKI_ROOT" | tr '[:upper:]' '[:lower:]')" in
  *prod*|*production*)
    echo "STOP: staging shell values include a production-looking ID"
    exit 1
    ;;
esac
```

## Plan And Apply

Run the plan first and inspect it for staging-only resources, no destroy
actions, and no production project or resource names.

```bash
tofu -chdir=infra/terraform plan -var-file=staging.tfvars
```

Expected plan scope:

- Staging BigQuery dataset and tables.
- Staging GCS raw bucket.
- Staging Artifact Registry repository.
- Staging service accounts and IAM.
- Staging Secret Manager references.
- Staging Cloud Run jobs and Cloud Scheduler jobs.
- Optional staging ops alerting resources when `enable_ops_alerts = true`.

Apply only after the plan is confirmed staging-only.

```bash
tofu -chdir=infra/terraform apply -var-file=staging.tfvars
```

## Build, Tag, And Push Image

Build the staging image.

```bash
docker build -t hermes-merry:staging .
```

Tag it with the exact staging `image_uri` copied from
`infra/terraform/staging.tfvars`.

```bash
docker tag hermes-merry:staging "$STAGING_IMAGE_URI"
```

Push only after the `STAGING_IMAGE_URI` checks pass.

```bash
docker push "$STAGING_IMAGE_URI"
```

## Synthetic Ingest Source

The preferred canary path is the Cloud Run job sequence below. That path also
verifies the staging Slack channel when `weekly-summary` runs. Local synthetic
ingest is optional and is only for seeding one known synthetic candidate from an
operator machine. Do not run it with ambient local environment values or Slack
environment variables.

Before local synthetic ingest, derive only the ingest values from the staging
shell values copied from `infra/terraform/staging.tfvars`. Do not set
`SLACK_CHANNEL` or `SLACK_BOT_TOKEN` for local ingest.

```bash
GCP_PROJECT_ID="$STAGING_PROJECT"
BIGQUERY_DATASET="$STAGING_DATASET"
RAW_BUCKET="$STAGING_RAW_BUCKET"
WIKI_ROOT="$STAGING_WIKI_ROOT"
```

Echo the values, compare them with `infra/terraform/staging.tfvars`, and stop if
any value differs or points to production.

```bash
printf 'GCP_PROJECT_ID=%s\n' "$GCP_PROJECT_ID"
printf 'BIGQUERY_DATASET=%s\n' "$BIGQUERY_DATASET"
printf 'RAW_BUCKET=%s\n' "$RAW_BUCKET"
printf 'WIKI_ROOT=%s\n' "$WIKI_ROOT"

test "$GCP_PROJECT_ID" = "$STAGING_PROJECT" || {
  echo "STOP: GCP_PROJECT_ID differs from the staging project"
  exit 1
}
test "$BIGQUERY_DATASET" = "$STAGING_DATASET" || {
  echo "STOP: BIGQUERY_DATASET differs from the staging dataset"
  exit 1
}
test "$RAW_BUCKET" = "$STAGING_RAW_BUCKET" || {
  echo "STOP: RAW_BUCKET differs from the staging raw bucket"
  exit 1
}
test "$WIKI_ROOT" = "$STAGING_WIKI_ROOT" || {
  echo "STOP: WIKI_ROOT differs from the staging wiki root"
  exit 1
}

case "$BIGQUERY_DATASET" in
  *staging*) ;;
  *)
    echo "STOP: BIGQUERY_DATASET must be a staging dataset"
    exit 1
    ;;
esac

case "$RAW_BUCKET" in
  *staging*) ;;
  *)
    echo "STOP: RAW_BUCKET must be a staging bucket"
    exit 1
    ;;
esac

case "$WIKI_ROOT" in
  /*) ;;
  *)
    echo "STOP: WIKI_ROOT must be an absolute staging path"
    exit 1
    ;;
esac

case "$(printf '%s\n' \
  "$GCP_PROJECT_ID" \
  "$BIGQUERY_DATASET" \
  "$RAW_BUCKET" \
  "$WIKI_ROOT" | tr '[:upper:]' '[:lower:]')" in
  *prod*|*production*)
    echo "STOP: local ingest environment includes a production-looking ID"
    exit 1
    ;;
esac
```

Use one synthetic candidate as the optional local canary source.
This command intentionally starts from a clean environment and does not inherit
local Sheet, Gmail, or Slack variables. Authentication uses Application Default
Credentials from the operator's gcloud configuration under `HOME`; no auth
environment variable is required for the normal local canary.

```bash
env -i \
  PATH="$PATH" \
  HOME="$HOME" \
  GCP_PROJECT_ID="$GCP_PROJECT_ID" \
  BIGQUERY_DATASET="$BIGQUERY_DATASET" \
  RAW_BUCKET="$RAW_BUCKET" \
  WIKI_ROOT="$WIKI_ROOT" \
  python3 -m merry_runtime.jobs run ingest-sources --sources-json '[{"channel":"external_referral","payload":{"company":"Canary CareFarm","region":"Jeonbuk","industry":"AgriTech","reason":"Canary synthetic referral","tags":"social_problem:rural_income, beneficiary:older_farmers","confidence":"0.91"}}]'
```

## Curated Candidate Batch Import

Use curated CSV imports only for controlled Sheet, Gmail, or Drive exports. The
CSV must contain exactly these columns:

```text
company,brand,representative,homepage,region,industry,channel,evidence,confidence,tags,source_uri
```

Allowed `channel` values are `hankyung_ceo_interview`, `info_mail`,
`external_referral`, and `internal_screening_memo`. Keep the original export
location in `source_uri`; it is written through to `raw_sources.url` and linked
to each imported signal through the raw source row.

Run the no-write quality gate before staging import. This parses the file,
redacts PII in `evidence`, validates channels, and rejects batches where rows in
duplicate normalized company-name groups with conflicting non-empty homepages
exceed 5% of the batch.

```bash
export CANDIDATE_BATCH_CSV='tests/fixtures/candidate_batch_100.csv'

PYTHONPATH=src python3 - <<'PY'
import json
import os
from pathlib import Path

from merry_runtime.ingestion.batch_import import parse_candidate_batch_csv

batch = parse_candidate_batch_csv(Path(os.environ["CANDIDATE_BATCH_CSV"]).read_text(encoding="utf-8"))
print(json.dumps(
    {
        "row_count": batch.row_count,
        "quality_gate": {
            "passed": batch.quality_report.passed,
            "conflict_rate": batch.quality_report.conflict_rate,
            "conflicting_row_count": batch.quality_report.conflicting_row_count,
            "duplicate_conflicts": batch.quality_report.duplicate_conflicts[:10],
        },
    },
    ensure_ascii=False,
    sort_keys=True,
))
raise SystemExit(0 if batch.quality_report.passed else 2)
PY
```

After the quality gate passes, import into staging from a clean environment
using only the staging values copied above.

```bash
env -i \
  PATH="$PATH" \
  HOME="$HOME" \
  PYTHONPATH=src \
  GCP_PROJECT_ID="$GCP_PROJECT_ID" \
  BIGQUERY_DATASET="$BIGQUERY_DATASET" \
  RAW_BUCKET="$RAW_BUCKET" \
  WIKI_ROOT="$WIKI_ROOT" \
  CANDIDATE_BATCH_CSV="$CANDIDATE_BATCH_CSV" \
  python3 - <<'PY'
import json
import os
from pathlib import Path

from merry_runtime.pipelines.import_candidate_batch import import_candidate_batch
from merry_runtime.runtime_config import RuntimeConfig
from merry_runtime.runtime_factory import build_runtime

runtime = build_runtime(RuntimeConfig.from_env())
result = import_candidate_batch(
    csv_text=Path(os.environ["CANDIDATE_BATCH_CSV"]).read_text(encoding="utf-8"),
    object_store=runtime.object_store,
    structured_store=runtime.structured_store,
    wiki_store=runtime.wiki_store,
    run_id="run_staging_curated_candidate_batch",
)
print(json.dumps(
    {
        "run_id": result.run_id,
        "row_count": result.row_count,
        "imported_count": result.imported_count,
        "quality_gate_passed": result.quality_report.passed,
    },
    ensure_ascii=False,
    sort_keys=True,
))
PY
```

## Cloud Run Job Order

Run manual Cloud Run jobs in this order after Terraform apply and image push.

```bash
gcloud run jobs execute ingest-sources --region asia-northeast3 --wait
gcloud run jobs execute resolve-entities --region asia-northeast3 --wait
gcloud run jobs execute score-candidates --region asia-northeast3 --wait
gcloud run jobs execute sync-review-sheet --region asia-northeast3 --wait
gcloud run jobs execute weekly-summary --region asia-northeast3 --wait
```

Expected job result:

- Each job exits successfully.
- `agent_runs` contains one success row per job.

## Evidence Capture

Record the canary result in `docs/runbooks/staging-canary-results.md`.

Capture:

- Absolute date and time.
- Active gcloud project.
- `tofu output` summary.
- Cloud Run job execution names.
- BigQuery row counts.
- GCS raw synthetic source object path.
- Manual note that the staging Sheet was checked.
- Manual note that the staging Slack channel received the weekly summary.
- Confirmation that no production resource IDs appeared in logs or Terraform
  outputs.

Useful commands:

```bash
gcloud config get-value project
tofu -chdir=infra/terraform output
gcloud storage ls "gs://${STAGING_RAW_BUCKET}/**"
bq query --use_legacy_sql=false "
SELECT 'raw_sources' AS table_name, COUNT(*) AS row_count
FROM \`${STAGING_PROJECT}.${STAGING_DATASET}.raw_sources\`
UNION ALL SELECT 'mother_entities', COUNT(*)
FROM \`${STAGING_PROJECT}.${STAGING_DATASET}.mother_entities\`
UNION ALL SELECT 'signals', COUNT(*)
FROM \`${STAGING_PROJECT}.${STAGING_DATASET}.signals\`
UNION ALL SELECT 'ac_scores', COUNT(*)
FROM \`${STAGING_PROJECT}.${STAGING_DATASET}.ac_scores\`
UNION ALL SELECT 'candidate_cards', COUNT(*)
FROM \`${STAGING_PROJECT}.${STAGING_DATASET}.candidate_cards\`
UNION ALL SELECT 'agent_runs', COUNT(*)
FROM \`${STAGING_PROJECT}.${STAGING_DATASET}.agent_runs\`
"
gcloud run jobs executions list --region asia-northeast3 --job ingest-sources --limit 5
gcloud run jobs executions list --region asia-northeast3 --job resolve-entities --limit 5
gcloud run jobs executions list --region asia-northeast3 --job score-candidates --limit 5
gcloud run jobs executions list --region asia-northeast3 --job sync-review-sheet --limit 5
gcloud run jobs executions list --region asia-northeast3 --job weekly-summary --limit 5
```

Use staging dataset and bucket IDs from `infra/terraform/staging.tfvars` when
checking BigQuery and GCS evidence.

## Acceptance Checklist

- [ ] GCS has one raw synthetic source object.
- [ ] BigQuery has one raw source row.
- [ ] BigQuery has one mother entity row.
- [ ] BigQuery has at least one `signals` row.
- [ ] BigQuery has one `ac_scores` row.
- [ ] BigQuery has one candidate card row.
- [ ] BigQuery has one agent run row per executed job.
- [ ] Review Sheet has one candidate row.
- [ ] Slack receives the weekly summary in the staging channel.
- [ ] No production resource IDs appear in logs or Terraform outputs.
