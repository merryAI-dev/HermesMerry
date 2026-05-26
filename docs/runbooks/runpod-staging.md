# Hermes Runpod Staging Runbook

Use this runbook for the primary staging path. Runpod is the execution backend.
SQLite on the Runpod container disk is the primary Mother DB until a persistent
volume is explicitly attached. Google Sheets is the human operating console, the
Obsidian wiki is the readable projection, and GCP is limited to Google Workspace
API access for Gmail and Sheets. BigQuery is optional warehouse/export
infrastructure.

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
- `MOTHER_DB_PATH=/home/hermes/hermes/mother.db`
- `OBJECT_STORE_BACKEND=local`
- `RAW_ROOT=/home/hermes/hermes/raw`
- `BACKUP_ROOT=/home/hermes/hermes/backups`
- `REVIEW_SHEET_ID`
- `AC_ID`
- `GMAIL_LABEL_ID`
- `APPS_SCRIPT_DRAFT_WEBHOOK_URL`
- `APPS_SCRIPT_DRAFT_SECRET`
- `SLACK_CHANNEL`
- `SLACK_BOT_TOKEN`
- `GOOGLE_APPLICATION_CREDENTIALS_JSON`
- `WIKI_ROOT=/home/hermes/hermes/wiki`
- `HERMES_AGENT_ID=runpod-hermes-staging`
- `KVIC_API_KEY`
- `KVIC_SYNC_INTERVAL_SECONDS=86400`
- `KVIC_FUND_DESCRIPTION_BATCH_LIMIT=50`
- `KVIC_FUND_DESCRIPTION_STALE_DAYS=30`
- `KVIC_FUND_SEARCH_MAX_RESULTS=5`
- `ANTHROPIC_API_KEY`
- `HERMES_LLM_MODEL=claude-sonnet-4-6`
- `INVESTOR_RESEARCH_BATCH_LIMIT=20`
- `INVESTOR_RESEARCH_STALE_DAYS=7`
- `INVESTOR_RESEARCH_SEARCH_MAX_RESULTS=5`
- `THEVC_USER_EMAIL`
- `THEVC_PASSWORD`
- `THEVC_BROWSER_STATE_PATH=/home/hermes/hermes/thevc-state.json`
- `CRAWL_SHEET_TAB=Crawl Sources`
- `CRAWL_TARGETS_JSON=[{"url":"https://thevc.kr/","source_kind":"thevc_investment_ma","max_cards":20,"max_pages":3,"thevc_backend":"playwright"},{"url":"https://platum.kr/archives/category/investment","source_kind":"platum_investment_news","max_articles":24,"max_pages":2,"portfolio_watchlist_path":"configs/portfolio_watchlist.txt"},{"url":"https://platum.kr/archives/category/investment","source_kind":"platum_investment_news","max_articles":24,"max_pages":2,"portfolio_watchlist_sheet_tab":"Accelerator Watchlist","portfolio_news_sheet_tab":"Accelerator News","portfolio_news_slack_heading":"Hermes 육성기업 뉴스 감지","portfolio_notify_recent_days":2}]`
- `AGENT_LOOP_JOBS=agent-work-queue`
- `AGENT_LOOP_INTERVAL_SECONDS=3600`
- `AGENT_LOOP_MAX_CYCLES=0` for the always-on SQLite loop that repeats every 1 hour
- `HERMES_ALLOW_UNBOUNDED_LOOP=1` for any intentional always-on loop

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
  `/home/hermes/hermes` for CPU Pods without an attached persistent volume.
- `WIKI_ROOT` is not under `/home/hermes/hermes`.
- `REVIEW_SHEET_ID`, `GMAIL_LABEL_ID`, or `SLACK_CHANNEL` points to a
  production resource.
- You have not reviewed `scripts/runpod_cost_audit.sh --days 3` output for
  running Pods, active Serverless workers, network volumes, and recent billing.
- The runtime is on a GPU Pod but the job mix is only crawl, Sheet, backup, or
  SMINFO work. Those are Hermes control-plane jobs and should run on CPU or as a
  finite batch.
- A Gemma, Qwen, or other local model endpoint has active/min workers enabled
  without an explicit low-latency requirement.

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

- Runpod local raw storage under `/home/hermes/hermes/raw` when
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
Volume path: /workspace when a persistent volume is attached; otherwise use /home/hermes/hermes
WIKI_ROOT: /home/hermes/hermes/wiki
STRUCTURED_STORE_BACKEND: sqlite
MOTHER_DB_PATH: /home/hermes/hermes/mother.db
OBJECT_STORE_BACKEND: local
RAW_ROOT: /home/hermes/hermes/raw
BACKUP_ROOT: /home/hermes/hermes/backups
HERMES_AGENT_ID: runpod-hermes-staging
KVIC_API_KEY: Runpod secret or public KVIC fund-status API key
KVIC_SYNC_INTERVAL_SECONDS: 86400
KVIC_REQUEST_TIMEOUT_SECONDS: 15
KVIC_FUND_DESCRIPTION_BATCH_LIMIT: 50
KVIC_FUND_DESCRIPTION_STALE_DAYS: 30
KVIC_FUND_SEARCH_MAX_RESULTS: 5
ANTHROPIC_API_KEY: Runpod secret for Claude Messages API
HERMES_LLM_MODEL: claude-sonnet-4-6
HERMES_LLM_TIMEOUT_SECONDS: 30
INVESTOR_RESEARCH_BATCH_LIMIT: 20
INVESTOR_RESEARCH_STALE_DAYS: 7
INVESTOR_RESEARCH_SEARCH_MAX_RESULTS: 5
THEVC_USER_EMAIL: Runpod secret or local .env.local value
THEVC_PASSWORD: Runpod secret or local .env.local value
THEVC_BROWSER_STATE_PATH: /home/hermes/hermes/thevc-state.json
THEVC_BROWSER_HEADLESS: 1
THEVC_TIMEOUT_SECONDS: 30
CRAWL_SHEET_TAB: Crawl Sources
CRAWL_TARGETS_JSON: [{"url":"https://thevc.kr/","source_kind":"thevc_investment_ma","max_cards":20,"max_pages":3,"thevc_backend":"playwright"},{"url":"https://platum.kr/archives/category/investment","source_kind":"platum_investment_news","max_articles":24,"max_pages":2,"portfolio_watchlist_path":"configs/portfolio_watchlist.txt"},{"url":"https://platum.kr/archives/category/investment","source_kind":"platum_investment_news","max_articles":24,"max_pages":2,"portfolio_watchlist_sheet_tab":"Accelerator Watchlist","portfolio_news_sheet_tab":"Accelerator News","portfolio_news_slack_heading":"Hermes 육성기업 뉴스 감지","portfolio_notify_recent_days":2}]
AGENT_LOOP_JOBS: sync-kvic-funds,research-investors,crawl-sources,draft-outreach-emails,enrich-sminfo,backup-export
AGENT_LOOP_INTERVAL_SECONDS: 3600
AGENT_LOOP_MAX_CYCLES: 0
HERMES_ALLOW_UNBOUNDED_LOOP: 1
```

`sync-kvic-funds` may run inside the hourly loop, but it enforces
`KVIC_SYNC_INTERVAL_SECONDS=86400` internally. Fresh snapshots are skipped, so
KVIC is called effectively every day while `agent_runs` still records that the
job was checked.
Keep it before `crawl-sources` so new The VC rows can immediately attach KVIC
investor profile fields into `Candidate Detail`.

For outreach drafts, prefer the Apps Script gateway:

```text
APPS_SCRIPT_DRAFT_WEBHOOK_URL: https://script.google.com/macros/s/deployment-id/exec
APPS_SCRIPT_DRAFT_SECRET: Runpod secret matching HERMES_DRAFT_SECRET in Apps Script
APPS_SCRIPT_DRAFT_TIMEOUT_SECONDS: 10
```

Store sensitive values as Runpod secrets. `GOOGLE_APPLICATION_CREDENTIALS_JSON`
`APPS_SCRIPT_DRAFT_SECRET`, and `ANTHROPIC_API_KEY` must be Runpod secrets, not
committed files. For the private image, configure Runpod Container Registry Auth
with the Docker Hub user `boram1220` and a Docker Hub access token.

The prepared one-cycle template is:

```text
Template: hermes-merry-staging-sqlite-canary
Template ID: 7s0amucf96
Image: docker.io/boram1220/hermes-merry:staging-cb0ddd0
```

The SQLite canary does not require BigQuery billing. Add the Google service
account secret back when the template enables Gmail, Sheets, or Sheet-driven
crawl jobs.

The one-cycle template overrides the container command to run the loop once and
then sleep:

```text
dockerEntrypoint: /bin/sh -lc
dockerStartCmd: runpod-entrypoint python3 -m merry_runtime.jobs loop; status=$?; echo HERMES_CANARY_DONE status=$status; sleep infinity
```

This prevents Runpod from restarting a finite command repeatedly while the Pod
desired status remains `RUNNING`. Delete one-cycle canary Pods after SQLite,
Sheet, wiki, and backup evidence is captured.

## Cost Control

The Hermes crawl/sheet/backup loop is the control plane. It does not need a GPU.
Use an always-on loop only when it is deliberately placed on a CPU or other
low-cost runtime and `HERMES_ALLOW_UNBOUNDED_LOOP=1` is set. Keep local model
serving separate: Gemma, Qwen, or similar GPU workloads should live behind a
Runpod Serverless endpoint with scale-to-zero settings for normal monitoring
workloads. Use active workers only for a conscious low-latency serving period.

Before and after any Runpod deployment, capture a billing snapshot:

```bash
scripts/runpod_cost_audit.sh --days 3
```

Review all four surfaces: Pods, Serverless endpoints/workers, network volumes,
and daily billing buckets. A one-cycle canary that ends with `sleep infinity`
still accrues Pod compute charges until the Pod is deleted.

## One-cycle Canary

Set `AGENT_LOOP_MAX_CYCLES=1` for the first Runpod run. Start the Pod and wait
for one loop result.

The Pod command remains:

```bash
python3 -m merry_runtime.jobs loop
```

Verify the SQLite Mother DB and backup artifacts inside the Runpod shell:

```bash
test -f /home/hermes/hermes/mother.db
find /home/hermes/hermes/backups -maxdepth 3 -type f | sort | tail
```

Verify the persistent wiki path inside the Runpod shell:

```bash
test -d /home/hermes/hermes/wiki
find /home/hermes/hermes/wiki -maxdepth 2 -type f | sort | head
```

Verify Sheet console tabs:

```text
Crawl Sources
Accelerator Watchlist
Accelerator News
Review Queue
Candidate Detail
Evidence
Decision Log
AC Settings
Exploration Queue
Investor DB
Fund DB
Run Log
SQLite Backup
Wiki Backup
Backup Manifest
```

`SQLite Backup`, `Wiki Backup`, and `Backup Manifest` are agent-owned backup
tabs. Each `backup-export` run rewrites them as the latest snapshot, then clears
stale tail rows only after the new snapshot has been written.

`Investor DB` and `Fund DB` are also agent-owned. `sync-kvic-funds` rewrites
them from SQLite `kvic_investor_managers`, `kvic_funds`, and
`kvic_fund_descriptions` so humans can inspect investment managers, active fund
counts, representative fund names, public KVIC amount/commitment, fund fields,
profile tags, and fund-level descriptions without opening SQLite. When
`ANTHROPIC_API_KEY` is configured, fund descriptions are encoded by Claude from
selected public-search evidence; Hermes still publishes only evidence-matched
source URLs. `research-investors` then enriches the same `Investor DB` from
`investor_external_profiles` using public web search and Claude as an evidence
encoder.

`Investor DB` uses Korean sheet headers because it is a human-facing operator
view:

```text
투자사
KVIC 공개 활성 펀드 수
KVIC 공개 전체 펀드 수
KVIC 공개 활성 운용액(억원)
KVIC 공개 활성 약정액(억원)
외부 공개 AUM(억원)
외부 공개 운용 조합 수
외부 공개 누적 투자액(억원)
AUM 설명
AUM 근거 제목
AUM 근거 URL
AUM 신뢰도
AUM 상태
출자 분야
대표 펀드
프로필 태그
다음 만기일
최종 만기일
수집시각
```

`Fund DB` is the fund-by-fund view. It is backed by `kvic_funds`,
`kvic_fund_types`, and `kvic_fund_descriptions`; Hermes enriches it with bounded
public web search results so humans can quickly see what each fund appears to
focus on without treating the web summary as a source of truth. If web search
does not return matching evidence, Hermes writes a conservative KVIC-field
summary and leaves the source URL empty with `설명 상태` set to `no_result`.

```text
펀드명
운용사
펀드종류
출자분야
결성연도
만기일
운영상태
펀드규모(억원)
약정액(억원)
펀드 설명
설명 근거 제목
설명 근거 URL
설명 상태
검색어
수집시각
```

Runpod staging should delegate the refresh to Hermes every day:

```text
AGENT_WORK_QUEUE_SPEC_PATH=configs/agent_work_queue.discovery.json
AGENT_WORK_QUEUE_BATCH_LIMIT=10
AGENT_LOOP_JOBS=agent-work-queue
KVIC_SYNC_INTERVAL_SECONDS=86400
KVIC_FUND_DESCRIPTION_BATCH_LIMIT=50
KVIC_FUND_DESCRIPTION_STALE_DAYS=30
KVIC_FUND_SEARCH_MAX_RESULTS=5
ANTHROPIC_API_KEY=<runpod-secret>
HERMES_LLM_MODEL=claude-sonnet-4-6
INVESTOR_RESEARCH_BATCH_LIMIT=20
INVESTOR_RESEARCH_STALE_DAYS=7
```

Seed the `Crawl Sources` tab with at least:

```text
url: https://thevc.kr/
source_kind: thevc_investment_ma
max_cards: 20
max_pages: 3
thevc_backend: playwright
detail_enrichment: true
thevc_login_required: false
status: pending
```

For accelerator-company monitoring, add a separate Platum row:

```text
url: https://platum.kr/archives/category/investment
source_kind: platum_investment_news
portfolio_watchlist_sheet_tab: Accelerator Watchlist
portfolio_news_sheet_tab: Accelerator News
portfolio_news_slack_heading: Hermes 육성기업 뉴스 감지
portfolio_notify_recent_days: 2
status: active
```

Seed `Accelerator Watchlist` from `configs/accelerator_watchlist.txt` with
columns `company`, `aliases`, `normalized_name`, `status`, and `notes`. Hermes
uses active rows only; deleting or marking a row inactive removes it from the
next crawl without touching the investment portfolio watchlist.

The THE VC crawler is limited to public HTML paths. Do not configure `/api`
targets. `https://thevc.kr/robots.txt` currently allows `/` and disallows
`/api`; treat that as the runtime boundary. For richer pagination, set
`thevc_backend=playwright`; Hermes will drive the visible home-page buttons
and reuse the login session stored at `THEVC_BROWSER_STATE_PATH` when login
succeeds. Keep `thevc_login_required=false` unless the run should fail when
THE VC rejects automated login. When login fails in optional mode, Hermes keeps
the public crawl result and records the fallback warning in `agent_runs` and the
Sheet `Crawl Sources.error_message` field. Human Verification pages are treated
as explicit warnings instead of silently producing an empty result.

The VC browser credentials stay out of Git:

```text
THEVC_USER_EMAIL=
THEVC_PASSWORD=
THEVC_BROWSER_STATE_PATH=/home/hermes/hermes/thevc-state.json
THEVC_BROWSER_HEADLESS=1
THEVC_BROWSER_CHANNEL=
THEVC_TIMEOUT_SECONDS=30
```

Crawler backend behavior:

- Uses `crawl4ai` first when it is installed in the runtime image.
- Falls back to a bounded stdlib HTML fetch for server-rendered pages.
- Uses Playwright only for THE VC rows marked `thevc_backend=playwright`.
- Records THE VC login fallback and Human Verification blocks as crawl warnings.
- Keeps target count bounded through the `crawl_public_sources` MCP contract.

BigQuery is optional. Use it only as a warehouse/export mirror after billing and
IAM are explicitly enabled:

```text
STRUCTURED_STORE_BACKEND=bigquery
BIGQUERY_DATASET=merry_ac_discovery_staging
BIGQUERY_WRITE_MODE=merge
```
