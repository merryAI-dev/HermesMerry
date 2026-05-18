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
  token.
- Confirm `infra/terraform/staging.tfvars` exists and points only to staging
  resources.
- Confirm `project_id`, `dataset_id`, `raw_bucket_name`, `image_uri`,
  `service_account_id`, and `scheduler_service_account_id` in
  `infra/terraform/staging.tfvars` are staging IDs.
- Confirm `review_sheet_id` is a staging Sheet.
- Confirm `gmail_label_id` is a staging Gmail label.
- Confirm `slack_channel` is a staging Slack channel.
- Confirm Secret Manager versions exist for `llm_api_key_secret_id` and
  `slack_bot_token_secret_id`.
- Confirm `ops_alert_email` is a staging/operator address, or
  `enable_ops_alerts = false`.

## Stop Condition

Stop before running any apply, image push, or Cloud Run job command if any
resource ID is production, if the active gcloud project is not the staging
project, or if `infra/terraform/staging.tfvars` is absent.

Do not run these commands when the stop condition is true:

- `tofu -chdir=infra/terraform apply -var-file=staging.tfvars`
- `docker push`
- `gcloud run jobs execute`

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

Tag it with the Artifact Registry repository from Terraform output.

```bash
docker tag hermes-merry:staging "$(tofu -chdir=infra/terraform output -raw artifact_registry_repository)/hermes-merry:staging"
```

Push only after the repository output is confirmed staging-only.

```bash
docker push "$(tofu -chdir=infra/terraform output -raw artifact_registry_repository)/hermes-merry:staging"
```

## Synthetic Ingest Source

Use one synthetic candidate as the canary source.

```bash
python3 -m merry_runtime.jobs run ingest-sources --sources-json '[{"channel":"external_referral","payload":{"company":"Canary CareFarm","region":"Jeonbuk","industry":"AgriTech","reason":"Canary synthetic referral","tags":"social_problem:rural_income, beneficiary:older_farmers","confidence":"0.91"}}]'
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
UNION ALL SELECT 'entity_signals', COUNT(*)
FROM \`${STAGING_PROJECT}.${STAGING_DATASET}.entity_signals\`
UNION ALL SELECT 'candidate_scores', COUNT(*)
FROM \`${STAGING_PROJECT}.${STAGING_DATASET}.candidate_scores\`
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
- [ ] BigQuery has at least one signal row.
- [ ] BigQuery has one score row.
- [ ] BigQuery has one candidate card row.
- [ ] BigQuery has one agent run row per executed job.
- [ ] Review Sheet has one candidate row.
- [ ] Slack receives the weekly summary in the staging channel.
- [ ] No production resource IDs appear in logs or Terraform outputs.
