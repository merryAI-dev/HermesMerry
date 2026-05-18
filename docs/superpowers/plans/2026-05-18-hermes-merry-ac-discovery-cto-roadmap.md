# Hermes Merry AC Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a safe, evidence-first AC discovery MVP that ingests candidate sources, builds the Mother DB, scores AC-specific Son DB queues, and routes final judgment to humans through Google Sheets.

**Architecture:** Hermes runs as an orchestration runtime with generic local tools disabled. The production surface is a whitelisted Merry MCP server backed by BigQuery, GCS, Google Sheets, Gmail, and Slack. OpenTofu is the primary IaC runner; Terraform is installed for compatibility but should not be alternated against the same lock file.

**Tech Stack:** Python 3.12+, pytest, Hermes Agent, OpenTofu 1.12.0, Terraform 1.15.3, GCP BigQuery, GCS, Cloud Run Jobs, Cloud Scheduler, Secret Manager, Google Sheets API, Gmail API, Slack Web API.

---

## Current State

Completed:

- Created repo at `/Users/boram/hermes-merry-ac-discovery`.
- Implemented core runtime modules under `src/merry_runtime`.
- Implemented whitelisted MCP tool registry under `src/merry_mcp/registry.py`.
- Implemented MCP dispatcher under `src/merry_mcp/server.py` with allowed-tool enforcement, required payload validation, payload size guard, and Slack summary PII redaction.
- Added Hermes production safety profile at `configs/hermes-production-profile.json`.
- Added BigQuery schema source of truth in `src/merry_runtime/schema.py`.
- Added OpenTofu/Terraform GCP skeleton under `infra/terraform`.
- Added Dockerfile, README, safety doc, and example configs.
- Installed OpenTofu 1.12.0 and Terraform 1.15.3 locally.
- Implemented adapter protocol interfaces and in-memory fake adapters.
- Implemented deterministic source parsers for article, info mail, external referral rows, and internal screening memos.
- Implemented ingest, score, and review feedback pipelines with no-network integration tests.
- Implemented thin production adapter wrappers for GCS, BigQuery, Google Sheets, Gmail, and Slack using injected clients.
- Implemented SQLite-backed LLM Wiki memory store with Obsidian markdown projection, `index.md`, `log.md`, page/link/source indexes, and ingest integration.
- Implemented probabilistic entity resolution using name/alias, founder, domain, email domain, description, region, and observation context.
- Implemented logit/probit priority scoring with utility, probability, uncertainty, model version, and exploration queue routing.
- Implemented Cloud Run job entrypoint wiring through env-backed runtime config, production adapter factory, and job runner.
- Added `Makefile` and GitHub Actions CI workflow.
- Verified `python3 -m pytest` with 74 passing tests.
- Verified `tofu fmt -check`, `tofu init -backend=false`, and `tofu validate`.

Not completed:

- Production adapter wrappers and `merry_runtime.jobs` now bind Google/Slack clients from environment and ADC; real GCP credentials and API enablement still need staging validation.
- MCP dispatcher exists, but a full stdio/SSE MCP protocol runner is not wired yet.
- Cloud Run image has not been built or pushed to Artifact Registry.
- GCP project variables, secrets, service account permissions, and API enablement are not configured.
- No staging `terraform.tfvars` or production state backend is configured.
- AC hypothesis report ingestion is not implemented.
- Score calibration from human review feedback is not implemented beyond manual priors and stored decisions.
- Monitoring, alerting, and weekly report generation are not implemented.
- 1,000-candidate Mother DB acquisition process is not implemented.

## CTO Decisions

- **IaC standard:** Use OpenTofu as the primary command in docs, CI, and deployment scripts. Keep Terraform installed for compatibility diagnostics only.
- **Safety standard:** Hermes never receives generic terminal, file, code execution, browser, delegation, or cron tools in production.
- **Data standard:** Raw documents live in GCS. Structured facts, scores, cards, reviews, and run logs live in BigQuery.
- **Decision standard:** The system recommends; humans decide. Final AC decisions are only accepted through Sheet review sync.
- **LLM standard:** Provider access stays behind env/Secret Manager. Runtime code uses provider-neutral interfaces so local Ollama, OpenAI-compatible APIs, or enterprise providers can be swapped.
- **Ontology standard:** Mother DB is not a flat company list. It is an evidence-backed discovery knowledge graph across Startup, Founder, DiscoveryChannel, Evidence, Signal, Fund, Program, AC, ImpactThesis, SocialProblem, Beneficiary, and Decision.
- **Scoring standard:** LLM text is not the score. Priority review is estimated by a transparent utility model and converted to probability with logit/probit. Human decisions become calibration data.
- **Exploration standard:** The agent must preserve exploration. High uncertainty, new-channel, contradiction-to-thesis, and strong-impact counterexamples can enter a separate exploration queue even when the priority score is not high.

## Core Technical Challenges

1. **Ontology-based Mother DB:** Preserve source meaning before scoring. Hankyung CEO interviews are public cold leads, info mail is inbound intent, external judge referral is a trust/referral signal, and internal screening history is a semi-qualified human-evaluated signal. The system must store these as different graph relationships rather than flattening them into one list.
2. **Probabilistic entity resolution:** Resolve legal name, service name, brand name, English name, founder name, homepage domain, email domain, IR title, business description, region, and observation time together. Avoid both duplicate inflation and false merges.
3. **Logit/probit first-pass scoring:** Estimate `P(priority_review = 1)` from `U(startup, ac) = beta0 + beta1 FundFit + beta2 RecruitmentFit + beta3 ImpactFit + beta4 ChannelTrust + beta5 MultiChannelSignal + beta6 PriorDecision + beta7 Freshness - beta8 Risk`.
4. **Auto-regressive feedback loop with bias control:** Use human decisions as priors for the next collection/scoring run, but reserve exploration capacity for uncertain, new-channel, thesis-conflicting, or high-impact counterexample candidates.
5. **Secure GCP frontless operation:** Separate raw source, AI extraction, probability score, and human judgment. Enforce least-privilege service accounts, Secret Manager, Cloud Run isolation, Scheduler/PubSub async execution, Cloud Logging audit trails, BigQuery row/column-level controls, PII masking, and raw retention.
6. **SQLite-backed LLM Wiki projection:** The durable memory layer is a local SQLite wiki index plus Obsidian-compatible markdown pages. Embeddings, if added later, are only a search aid over wiki/evidence pages; Neo4j or other third-party graph databases are explicitly out of scope.

## File Ownership Map

- `src/merry_runtime/adapters/`: GCP, Google Workspace, Slack, and LLM provider adapters.
- `src/merry_runtime/ontology.py`: in-process node/edge model, source-channel semantics, Wiki/evidence projection.
- `src/merry_runtime/wiki_store.py`: SQLite-backed wiki memory store that writes Obsidian markdown pages, `index.md`, `log.md`, source indexes, and link indexes.
- `src/merry_runtime/probabilistic_resolution.py`: probabilistic entity matching for aliases, domains, founders, descriptions, regions, and observation context.
- `src/merry_runtime/probabilistic_scoring.py`: logit/probit utility model, probability conversion, and exploration queue policy.
- `src/merry_runtime/ingestion/`: source-specific parsers for articles, Gmail messages, referral rows, and Drive memos.
- `src/merry_runtime/pipelines/`: Cloud Run job orchestration for ingest, resolve, score, review sync, and weekly summary.
- `src/merry_mcp/server.py`: MCP server that exposes only `TOOL_REGISTRY` operations.
- `tests/fixtures/`: deterministic source fixtures for integration tests.
- `tests/integration/`: end-to-end pipeline tests using fake adapters.
- `infra/terraform/`: GCP resources, IAM, scheduler, jobs, secrets, and outputs.
- `.github/workflows/ci.yml`: tests, safety checks, and OpenTofu validation.

## Phase 0.5: SQLite Wiki Memory, Probability, And Exploration Foundations

### Task 0.5.1: SQLite Wiki Memory Model

**Files:**
- Create: `src/merry_runtime/ontology.py`
- Create: `src/merry_runtime/wiki_store.py`
- Test: `tests/test_ontology.py`
- Test: `tests/test_wiki_store.py`

- [x] **Step 1: Write failing tests for channel semantics and graph edges**

Expected: public article, info mail, referral, and internal review sources produce distinct `DiscoveryChannel` meanings and evidence-backed edges.

- [x] **Step 2: Implement ontology node/edge model**

Expected: graph contains Startup, DiscoveryChannel, Evidence, Signal, ImpactThesis/SocialProblem/Beneficiary, AC, and Decision node kinds without relying on embedding similarity.

- [x] **Step 3: Add SQLite-backed wiki memory**

Expected: `wiki.db` contains `pages`, `links`, `sources`, and `log_entries`; `wiki/index.md`, `wiki/log.md`, and entity/concept/channel pages are Obsidian-compatible markdown projections.

- [x] **Step 4: Verify**

Run: `python3 -m pytest tests/test_ontology.py tests/test_wiki_store.py tests/test_bigquery_schema.py -v`
Expected: pass.

### Task 0.5.2: Probabilistic Entity Resolution

**Files:**
- Create: `src/merry_runtime/probabilistic_resolution.py`
- Test: `tests/test_probabilistic_resolution.py`

- [x] **Step 1: Write failing tests for alias/domain/founder/description/region matching**

Expected: service-name vs legal-name observations can merge with high probability; same name with conflicting founder/domain requires review; low-overlap observations create a new entity.

- [x] **Step 2: Implement feature extraction and probability model**

Expected: model returns probability, action, matched entity ID, and feature contributions.

- [x] **Step 3: Verify**

Run: `python3 -m pytest tests/test_probabilistic_resolution.py -v`
Expected: pass.

### Task 0.5.3: Logit/Probit Scoring And Exploration Queue

**Files:**
- Create: `src/merry_runtime/probabilistic_scoring.py`
- Modify: `src/merry_runtime/pipelines/score_candidates.py`
- Modify: `src/merry_runtime/schema.py`
- Test: `tests/test_probabilistic_scoring.py`
- Test: `tests/integration/test_score_candidates.py`

- [x] **Step 1: Write failing tests for utility, sigmoid/probit conversion, and exploration routing**

Expected: referral/internal-review channels lift `ChannelTrust`; multi-channel signals lift priority; high uncertainty or strong impact contradiction routes to exploration.

- [x] **Step 2: Implement utility model**

Expected: `PriorityFeatures` maps to utility and probability through `logit` or `probit`.

- [x] **Step 3: Implement exploration policy**

Expected: output queue is `priority`, `exploration`, `watchlist`, or `archive`.

- [x] **Step 4: Store probability metadata in score rows**

Expected: `ac_scores` can carry `priority_probability`, `priority_utility`, `queue_type`, `uncertainty`, and `model_version`.

- [x] **Step 5: Verify**

Run: `python3 -m pytest tests/test_probabilistic_scoring.py tests/integration/test_score_candidates.py -v`
Expected: pass.

## Phase 1: Make The Runtime Executable

### Task 1: Add Adapter Interfaces

**Files:**
- Create: `src/merry_runtime/adapters/interfaces.py`
- Create: `tests/test_adapter_interfaces.py`

- [x] **Step 1: Write the failing test**

```python
from merry_runtime.adapters.interfaces import ObjectStore, ReviewQueue, StructuredStore


def test_adapter_protocols_define_required_runtime_methods() -> None:
    assert "write_raw_text" in ObjectStore.__dict__
    assert "upsert_rows" in StructuredStore.__dict__
    assert "read_pending_reviews" in ReviewQueue.__dict__
```

- [x] **Step 2: Run the test**

Run: `python3 -m pytest tests/test_adapter_interfaces.py -v`
Expected: fail with `ModuleNotFoundError`.

- [x] **Step 3: Implement the interfaces**

```python
from __future__ import annotations

from typing import Protocol


class ObjectStore(Protocol):
    def write_raw_text(self, *, path: str, text: str, content_type: str) -> str: ...


class StructuredStore(Protocol):
    def upsert_rows(self, *, table: str, rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> int: ...
    def query_rows(self, *, sql: str, parameters: dict[str, object]) -> list[dict[str, object]]: ...


class ReviewQueue(Protocol):
    def publish_cards(self, *, sheet_tab: str, rows: list[dict[str, object]]) -> int: ...
    def read_pending_reviews(self, *, sheet_tab: str) -> list[dict[str, str]]: ...


class Notifier(Protocol):
    def send_message(self, *, channel: str, text: str) -> str: ...
```

- [x] **Step 4: Verify**

Run: `python3 -m pytest tests/test_adapter_interfaces.py -v`
Expected: pass.

### Task 2: Add Fake Adapters For Integration Tests

**Files:**
- Create: `src/merry_runtime/adapters/fakes.py`
- Create: `tests/test_fake_adapters.py`

- [x] **Step 1: Write fake adapter tests**

```python
from merry_runtime.adapters.fakes import FakeObjectStore, FakeReviewQueue, FakeStructuredStore


def test_fake_structured_store_upserts_by_key() -> None:
    store = FakeStructuredStore()
    store.upsert_rows(table="mother_entities", rows=[{"entity_id": "ent_1", "name": "A"}], key_fields=("entity_id",))
    store.upsert_rows(table="mother_entities", rows=[{"entity_id": "ent_1", "name": "B"}], key_fields=("entity_id",))
    assert store.tables["mother_entities"] == [{"entity_id": "ent_1", "name": "B"}]


def test_fake_object_store_returns_gs_uri() -> None:
    store = FakeObjectStore(bucket="raw-bucket")
    assert store.write_raw_text(path="raw/a.txt", text="hello", content_type="text/plain") == "gs://raw-bucket/raw/a.txt"


def test_fake_review_queue_round_trips_review_rows() -> None:
    queue = FakeReviewQueue()
    queue.seed_reviews("ac_climate", [{"card_id": "card_1", "reviewer": "boram", "decision": "advance"}])
    assert queue.read_pending_reviews(sheet_tab="ac_climate")[0]["decision"] == "advance"
```

- [x] **Step 2: Run the tests**

Run: `python3 -m pytest tests/test_fake_adapters.py -v`
Expected: fail with missing fake classes.

- [x] **Step 3: Implement fake adapters**

Implement in-memory stores with deterministic dictionaries and no network calls.

- [x] **Step 4: Verify**

Run: `python3 -m pytest tests/test_fake_adapters.py -v`
Expected: pass.

## Phase 2: Build Source Ingestion

### Task 3: Add Source Parsers

**Files:**
- Create: `src/merry_runtime/ingestion/parsers.py`
- Create: `tests/fixtures/hankyung_article.txt`
- Create: `tests/fixtures/info_mail.txt`
- Create: `tests/fixtures/referral_row.json`
- Create: `tests/fixtures/internal_memo.txt`
- Create: `tests/test_source_parsers.py`

- [x] **Step 1: Write parser tests**

```python
from pathlib import Path

from merry_runtime.ingestion.parsers import parse_article, parse_email, parse_internal_memo, parse_referral_row


FIXTURES = Path("tests/fixtures")


def test_article_parser_extracts_company_and_evidence() -> None:
    parsed = parse_article(FIXTURES.joinpath("hankyung_article.txt").read_text())
    assert parsed.entity.name == "CareFarm Carbon"
    assert any(signal.signal_type == "impact" for signal in parsed.signals)


def test_referral_parser_preserves_channel_meaning() -> None:
    parsed = parse_referral_row({"company": "Merry AI", "region": "Seoul", "reason": "external judge referral"})
    assert parsed.raw_source.channel == "external_referral"
```

- [x] **Step 2: Run parser tests**

Run: `python3 -m pytest tests/test_source_parsers.py -v`
Expected: fail with missing parsers.

- [x] **Step 3: Implement deterministic parsers**

Implement simple structured extraction first: explicit company, region, industry, homepage, signal type, evidence, confidence, and tags. Use regex only where the fixture format is intentionally semi-structured.

- [x] **Step 4: Verify**

Run: `python3 -m pytest tests/test_source_parsers.py -v`
Expected: pass.

### Task 4: Add Ingest Pipeline

**Files:**
- Create: `src/merry_runtime/pipelines/ingest_sources.py`
- Create: `tests/integration/test_ingest_sources.py`

- [x] **Step 1: Write integration test**

```python
from merry_runtime.adapters.fakes import FakeObjectStore, FakeStructuredStore
from merry_runtime.pipelines.ingest_sources import ingest_sources


def test_ingest_sources_writes_raw_sources_entities_and_signals() -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    result = ingest_sources(
        sources=[{"channel": "external_referral", "payload": {"company": "Merry AI", "region": "Seoul", "reason": "impact referral"}}],
        object_store=object_store,
        structured_store=structured_store,
    )
    assert result.raw_source_count == 1
    assert structured_store.tables["mother_entities"][0]["name"] == "Merry AI"
    assert structured_store.tables["signals"][0]["source_id"].startswith("src_")
```

- [x] **Step 2: Run integration test**

Run: `python3 -m pytest tests/integration/test_ingest_sources.py -v`
Expected: fail with missing pipeline.

- [x] **Step 3: Implement pipeline**

Implement source parse, PII detection, GCS raw write, BigQuery row upsert, and `agent_runs` result counters.

- [x] **Step 4: Verify**

Run: `python3 -m pytest tests/integration/test_ingest_sources.py -v`
Expected: pass.

## Phase 3: Son DB Scoring And Review Loop

### Task 5: Add Score Pipeline

**Files:**
- Create: `src/merry_runtime/pipelines/score_candidates.py`
- Create: `tests/integration/test_score_candidates.py`

- [x] **Step 1: Write score pipeline test**

```python
from merry_runtime.adapters.fakes import FakeReviewQueue, FakeStructuredStore
from merry_runtime.pipelines.score_candidates import score_candidates


def test_score_candidates_creates_ac_scores_and_cards() -> None:
    store = FakeStructuredStore.seed_climate_candidate()
    queue = FakeReviewQueue()
    result = score_candidates(structured_store=store, review_queue=queue, ac_id="ac_climate")
    assert result.card_count == 1
    assert store.tables["ac_scores"][0]["recommended_action"] == "advance"
    assert queue.published["ac_climate"][0]["decision"] == ""
```

- [x] **Step 2: Run the test**

Run: `python3 -m pytest tests/integration/test_score_candidates.py -v`
Expected: fail with missing pipeline.

- [x] **Step 3: Implement pipeline**

Load `mother_entities`, `signals`, and `ac_profiles`, call `score_candidate`, create `ac_scores`, create `candidate_cards`, and publish Sheet queue rows with blank human decision fields.

- [x] **Step 4: Verify**

Run: `python3 -m pytest tests/integration/test_score_candidates.py -v`
Expected: pass.

### Task 6: Add Review Feedback Pipeline

**Files:**
- Create: `src/merry_runtime/pipelines/sync_review_sheet.py`
- Create: `tests/integration/test_sync_review_sheet.py`

- [x] **Step 1: Write review sync test**

```python
from merry_runtime.adapters.fakes import FakeReviewQueue, FakeStructuredStore
from merry_runtime.pipelines.sync_review_sheet import sync_review_sheet


def test_sync_review_sheet_persists_human_decisions() -> None:
    store = FakeStructuredStore.seed_candidate_card()
    queue = FakeReviewQueue()
    queue.seed_reviews("ac_climate", [{"card_id": "card_1", "reviewer": "boram", "decision": "watchlist", "review_memo": "Need sales proof"}])
    result = sync_review_sheet(structured_store=store, review_queue=queue, ac_id="ac_climate")
    assert result.review_count == 1
    assert store.tables["candidate_cards"][0]["status"] == "watchlist"
```

- [x] **Step 2: Run the test**

Run: `python3 -m pytest tests/integration/test_sync_review_sheet.py -v`
Expected: fail with missing pipeline.

- [x] **Step 3: Implement pipeline**

Read Sheet rows, call `parse_review_row`, update `candidate_cards`, append `reviews`, and write rejected rows to `agent_runs.error_message`.

- [x] **Step 4: Verify**

Run: `python3 -m pytest tests/integration/test_sync_review_sheet.py -v`
Expected: pass.

## Phase 4: Real Integrations

### Task 7: Add GCP And Workspace Adapters

**Files:**
- Create: `src/merry_runtime/adapters/gcs.py`
- Create: `src/merry_runtime/adapters/bigquery.py`
- Create: `src/merry_runtime/adapters/google_sheets.py`
- Create: `src/merry_runtime/adapters/gmail.py`
- Create: `src/merry_runtime/adapters/slack.py`
- Create: `tests/test_adapter_contracts.py`

- [x] **Step 1: Write contract tests with monkeypatched clients**

Run all adapters with fake client objects and assert exact method calls, table names, bucket paths, Sheet ranges, Gmail label filters, and Slack channel payloads.

- [x] **Step 2: Implement adapters**

Use official Google and Slack SDK clients behind thin classes. Keep credentials injected through environment and Secret Manager, not hardcoded values.

- [x] **Step 3: Verify**

Run: `python3 -m pytest tests/test_adapter_contracts.py -v`
Expected: pass without network calls.

### Task 8: Add Real MCP Server

**Files:**
- Create: `src/merry_mcp/server.py`
- Create: `tests/test_mcp_server.py`

- [x] **Step 1: Write server tests**

Assert the server exposes exactly `allowed_tool_names()` and rejects any tool name not in `TOOL_REGISTRY`.

- [x] **Step 2: Implement server**

Map each MCP tool contract to a pipeline or adapter method. Enforce max payload length and redact PII before any LLM summary call.

- [x] **Step 3: Verify**

Run: `python3 -m pytest tests/test_mcp_server.py -v`
Expected: pass.

## Phase 5: Deployable Beta

### Task 9: Add CI And Deployment Checks

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `Makefile`

- [x] **Step 1: Add Makefile targets**

```makefile
.PHONY: test safety-check tofu-validate

test:
	python3 -m pytest

safety-check:
	PYTHONPATH=src python3 -m merry_runtime.jobs validate-hermes-profile
	PYTHONPATH=src python3 -m merry_runtime.jobs list-mcp-tools

tofu-validate:
	tofu -chdir=infra/terraform fmt -check
	TF_DATA_DIR=/tmp/hermes-merry-tofu tofu -chdir=infra/terraform init -backend=false
	TF_DATA_DIR=/tmp/hermes-merry-tofu tofu -chdir=infra/terraform validate
```

- [x] **Step 2: Add CI workflow**

Run `make test`, `make safety-check`, and `make tofu-validate` on every push.

- [x] **Step 3: Verify locally**

Run: `make test safety-check tofu-validate`
Expected: all targets exit 0.

### Task 10: Configure Staging GCP

**Files:**
- Create: `infra/terraform/staging.tfvars.example`
- Modify: `infra/terraform/main.tf`

- [x] **Step 1: Add tfvars example**

```hcl
project_id      = "my-staging-project"
region          = "asia-northeast3"
raw_bucket_name = "my-staging-hermes-merry-raw"
image_uri       = "asia-northeast3-docker.pkg.dev/my-staging-project/hermes-merry/runtime:staging"
review_sheet_id = "google-sheet-id"
slack_channel   = "slack-channel-id"
```

- [x] **Step 2: Add Artifact Registry**

Create `google_artifact_registry_repository` named `hermes-merry` in `asia-northeast3`.

- [ ] **Step 3: Verify plan**

Run: `tofu -chdir=infra/terraform plan -var-file=staging.tfvars`
Expected: creates dataset, bucket, service account, secrets, jobs, schedules, and artifact registry with no destroy actions.

## Phase 6: Quality Gates Before Live AC Use

- [x] Local 50-candidate dry run: all recommendations include evidence source IDs and rationale.
- [x] Local human review dry run: every Sheet decision writes one `reviews` row and updates one `candidate_cards.status`.
- [x] Local safety dry run: Hermes profile validation fails if any dangerous toolset is enabled.
- [x] Local privacy dry run: email and phone values are redacted before Slack and LLM summary payloads.
- [x] Local operations dry run: pipeline executions write `agent_runs` rows.
- [x] Local scale dry run: 1,000 synthetic candidates score with fake adapters.
- [ ] Staging Cloud Run scale dry run: 1,000 synthetic candidates score under the Cloud Run timeout configured for staging.

## Release Gates

- Gate A: Unit and integration tests pass locally and in CI.
- Gate B: OpenTofu validates and staging plan has no destroy actions.
- Gate C: Staging Cloud Run jobs complete one full ingest-resolve-score-review-summary cycle.
- Gate D: AC reviewers confirm Sheet columns and Slack summaries match their operating workflow.
- Gate E: First real AC batch runs with human-only final decision authority.
