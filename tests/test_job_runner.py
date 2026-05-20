import json

import pytest

from merry_runtime.adapters.fakes import FakeNotifier, FakeObjectStore, FakeReviewQueue, FakeStructuredStore
from merry_runtime.job_runner import JobRunError, RuntimeAdapters, run_job
from merry_runtime.pipelines.draft_outreach_emails import OutreachDraftResult
from merry_runtime.pipelines.enrich_sminfo import SminfoEnrichmentResult
from merry_runtime.pipelines.crawl_sources import CrawlResult
from merry_runtime.pipelines.research_investors import InvestorResearchResult
from merry_runtime.pipelines.sync_kvic_funds import KVICSyncResult
from merry_runtime.runtime_config import RuntimeConfig
from merry_runtime.wiki_store import SQLiteWikiStore


def _config(tmp_path, *, ac_id: str = "ac_climate") -> RuntimeConfig:
    return RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="raw-bucket",
        review_sheet_id="sheet-1",
        slack_channel="C123",
        gmail_label_id="Label_123",
        default_ac_id=ac_id,
        wiki_root=tmp_path,
    )


def _runtime(tmp_path, store: FakeStructuredStore | None = None) -> RuntimeAdapters:
    return RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=store or FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
        notifier=FakeNotifier(),
        wiki_store=SQLiteWikiStore(root=tmp_path),
        gmail_source=None,
        kvic_client=object(),
        web_search_client=object(),
        llm_client=object(),
    )


def test_run_ingest_sources_uses_sources_json_and_updates_wiki(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    sources_json = json.dumps(
        [
            {
                "channel": "external_referral",
                "payload": {
                    "company": "CareFarm Carbon",
                    "region": "Jeonbuk",
                    "industry": "AgriTech",
                    "reason": "Targets income stabilization for older farming households.",
                    "tags": "social_problem:older_farming_household_income",
                },
            }
        ]
    )

    result = run_job("ingest-sources", runtime=runtime, config=_config(tmp_path), sources_json=sources_json)

    assert result["job_name"] == "ingest-sources"
    assert result["raw_source_count"] == 1
    assert (tmp_path / "wiki" / "entities" / "carefarm-carbon.md").exists()


def test_run_crawl_sources_uses_sources_json_and_updates_wiki(monkeypatch, tmp_path) -> None:
    runtime = _runtime(tmp_path)
    sources_json = json.dumps([{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}])

    monkeypatch.setattr(
        "merry_runtime.job_runner.crawl_sources",
        lambda **kwargs: CrawlResult(
            run_id="run_crawl_test",
            target_count=1,
            crawled_source_count=5,
            ingested_raw_source_count=5,
            ingested_entity_count=5,
            ingested_signal_count=5,
        ),
    )

    result = run_job("crawl-sources", runtime=runtime, config=_config(tmp_path), sources_json=sources_json)

    assert result["job_name"] == "crawl-sources"
    assert result["crawled_source_count"] == 5


def test_run_crawl_sources_reads_targets_from_sheet_when_json_missing(monkeypatch, tmp_path) -> None:
    runtime = _runtime(tmp_path)
    runtime.review_queue.seed_reviews("Crawl Sources", [{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}])
    seen_targets = []

    def fake_crawl_sources(**kwargs):
        seen_targets.extend(kwargs["targets"])
        return CrawlResult(
            run_id="run_crawl_sheet",
            target_count=1,
            crawled_source_count=1,
            ingested_raw_source_count=1,
            ingested_entity_count=1,
            ingested_signal_count=1,
        )

    monkeypatch.setattr("merry_runtime.job_runner.crawl_sources", fake_crawl_sources)

    result = run_job("crawl-sources", runtime=runtime, config=_config(tmp_path))

    assert result["job_name"] == "crawl-sources"
    assert result["target_count"] == 1
    assert seen_targets == [{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}]


def test_run_crawl_sources_passes_sminfo_stale_days(monkeypatch, tmp_path) -> None:
    runtime = _runtime(tmp_path)
    runtime.review_queue.seed_reviews("Crawl Sources", [{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}])
    seen: dict[str, object] = {}

    def fake_crawl_sources(**kwargs):
        seen["sminfo_stale_days"] = kwargs["sminfo_stale_days"]
        return CrawlResult(
            run_id="run_crawl_stale",
            target_count=1,
            crawled_source_count=1,
            ingested_raw_source_count=1,
            ingested_entity_count=1,
            ingested_signal_count=1,
        )

    monkeypatch.setattr("merry_runtime.job_runner.crawl_sources", fake_crawl_sources)
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="raw-bucket",
        review_sheet_id="sheet-1",
        wiki_root=tmp_path,
        sminfo_stale_days=17,
    )

    run_job("crawl-sources", runtime=runtime, config=config)

    assert seen["sminfo_stale_days"] == 17


def test_run_crawl_sources_falls_back_to_configured_targets_when_sheet_is_empty(monkeypatch, tmp_path) -> None:
    runtime = _runtime(tmp_path)
    seen_targets = []

    def fake_crawl_sources(**kwargs):
        seen_targets.extend(kwargs["targets"])
        return CrawlResult(
            run_id="run_crawl_env",
            target_count=1,
            crawled_source_count=1,
            ingested_raw_source_count=1,
            ingested_entity_count=1,
            ingested_signal_count=1,
        )

    monkeypatch.setattr("merry_runtime.job_runner.crawl_sources", fake_crawl_sources)
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="raw-bucket",
        review_sheet_id="sheet-1",
        crawl_targets_json='[{"url":"https://thevc.kr/","source_kind":"thevc_investment_ma"}]',
        wiki_root=tmp_path,
    )

    result = run_job("crawl-sources", runtime=runtime, config=config)

    assert result["job_name"] == "crawl-sources"
    assert seen_targets == [{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}]


def test_run_crawl_sources_ignores_inactive_sheet_targets_and_uses_config_fallback(monkeypatch, tmp_path) -> None:
    runtime = _runtime(tmp_path)
    runtime.review_queue.seed_reviews(
        "Crawl Sources",
        [
            {"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma", "status": "disabled"},
            {"url": "", "source_kind": "platum_investment_news", "status": "active"},
        ],
    )
    seen_targets = []

    def fake_crawl_sources(**kwargs):
        seen_targets.extend(kwargs["targets"])
        return CrawlResult(
            run_id="run_crawl_env_after_inactive_sheet",
            target_count=1,
            crawled_source_count=1,
            ingested_raw_source_count=1,
            ingested_entity_count=1,
            ingested_signal_count=1,
        )

    monkeypatch.setattr("merry_runtime.job_runner.crawl_sources", fake_crawl_sources)
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="raw-bucket",
        review_sheet_id="sheet-1",
        crawl_targets_json='[{"url":"https://platum.kr/archives/category/investment","source_kind":"platum_investment_news"}]',
        wiki_root=tmp_path,
    )

    result = run_job("crawl-sources", runtime=runtime, config=config)

    assert result["job_name"] == "crawl-sources"
    assert seen_targets == [
        {"url": "https://platum.kr/archives/category/investment", "source_kind": "platum_investment_news"}
    ]


def test_run_crawl_sources_passes_only_active_sheet_targets(monkeypatch, tmp_path) -> None:
    runtime = _runtime(tmp_path)
    runtime.review_queue.seed_reviews(
        "Crawl Sources",
        [
            {"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma", "status": "active"},
            {"url": "https://platum.kr/archives/category/investment", "source_kind": "platum_investment_news", "status": "done"},
        ],
    )
    seen_targets = []

    def fake_crawl_sources(**kwargs):
        seen_targets.extend(kwargs["targets"])
        return CrawlResult(
            run_id="run_crawl_active_sheet_only",
            target_count=1,
            crawled_source_count=1,
            ingested_raw_source_count=1,
            ingested_entity_count=1,
            ingested_signal_count=1,
        )

    monkeypatch.setattr("merry_runtime.job_runner.crawl_sources", fake_crawl_sources)

    result = run_job("crawl-sources", runtime=runtime, config=_config(tmp_path))

    assert result["job_name"] == "crawl-sources"
    assert seen_targets == [{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma", "status": "active"}]


def test_run_ingest_ac_profiles_uses_sources_json_and_updates_wiki(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    sources_json = json.dumps(
        [
            {
                "payload": """
                    AC ID: ac_climate_local
                    AC Name: Climate Local Impact AC
                    Fund Purpose: climate adaptation fund
                    Hypothesis Tags: climate
                    Impact Priorities: carbon
                """,
            }
        ]
    )

    result = run_job("ingest-ac-profiles", runtime=runtime, config=_config(tmp_path), sources_json=sources_json)

    assert result["job_name"] == "ingest-ac-profiles"
    assert result["profile_count"] == 1
    assert runtime.structured_store.tables["ac_profiles"][0]["ac_id"] == "ac_climate_local"
    assert (tmp_path / "wiki" / "ac" / "ac-climate-local.md").exists()


def test_run_score_candidates_routes_to_sheet_queue(tmp_path) -> None:
    store = FakeStructuredStore.seed_climate_candidate()
    runtime = _runtime(tmp_path, store=store)

    result = run_job("score-candidates", runtime=runtime, config=_config(tmp_path), ac_id="ac_climate")

    assert result["job_name"] == "score-candidates"
    assert result["card_count"] == 1
    assert runtime.review_queue.published["ac_climate"][0]["queue_type"] == "priority"


def test_run_calibrate_scores_persists_ac_coefficients(tmp_path) -> None:
    store = FakeStructuredStore.seed_climate_candidate()
    score_runtime = _runtime(tmp_path, store=store)
    run_job("score-candidates", runtime=score_runtime, config=_config(tmp_path), ac_id="ac_climate")
    store.upsert_rows(
        table="reviews",
        rows=[
            {
                "review_id": "review_1",
                "card_id": store.tables["candidate_cards"][0]["card_id"],
                "reviewer": "boram",
                "decision": "advance",
                "memo": "",
                "reviewed_at": "2026-05-18T00:00:00+00:00",
            }
        ],
        key_fields=("review_id",),
    )
    runtime = _runtime(tmp_path, store=store)

    result = run_job("calibrate-scores", runtime=runtime, config=_config(tmp_path), ac_id="ac_climate")

    assert result["job_name"] == "calibrate-scores"
    assert result["sample_count"] == 1
    assert store.tables["ac_scoring_coefficients"][0]["ac_id"] == "ac_climate"


def test_run_sync_review_sheet_persists_reviews(tmp_path) -> None:
    store = FakeStructuredStore.seed_candidate_card()
    runtime = _runtime(tmp_path, store=store)
    runtime.review_queue.seed_reviews("ac_climate", [{"card_id": "card_1", "reviewer": "boram", "decision": "advance"}])

    result = run_job("sync-review-sheet", runtime=runtime, config=_config(tmp_path), ac_id="ac_climate")

    assert result["job_name"] == "sync-review-sheet"
    assert result["review_count"] == 1
    assert store.tables["candidate_cards"][0]["status"] == "advanced"


def test_run_weekly_summary_posts_slack_counts(tmp_path) -> None:
    store = FakeStructuredStore.seed_candidate_card()
    runtime = _runtime(tmp_path, store=store)

    result = run_job("weekly-summary", runtime=runtime, config=_config(tmp_path))

    assert result["job_name"] == "weekly-summary"
    assert result["message_id"] == "msg_000001"
    assert "priority=1" in runtime.notifier.messages[0]["text"]
    [run_row] = store.tables["agent_runs"]
    assert run_row["run_id"] == result["run_id"]
    assert run_row["job_name"] == "weekly-summary"
    assert run_row["status"] == "success"
    assert run_row["started_at"]
    assert run_row["finished_at"]
    assert run_row["input_count"] == 1
    assert run_row["output_count"] == 1
    assert run_row["error_message"] == ""


def test_run_sync_kvic_funds_routes_to_pipeline(monkeypatch, tmp_path) -> None:
    runtime = _runtime(tmp_path)
    seen: dict[str, object] = {}

    def fake_sync_kvic_funds(**kwargs):
        seen.update(kwargs)
        return KVICSyncResult(
            run_id="run_kvic_test",
            status="success",
            fund_type_count=1,
            fund_count=2,
            manager_count=1,
        )

    monkeypatch.setattr("merry_runtime.job_runner.sync_kvic_funds", fake_sync_kvic_funds)
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        review_sheet_id="sheet-1",
        wiki_root=tmp_path,
        structured_store_backend="sqlite",
        kvic_api_key="public-key",
        kvic_sync_interval_seconds=86400,
        kvic_fund_description_batch_limit=25,
        kvic_fund_description_stale_days=45,
        kvic_fund_search_max_results=7,
    )

    result = run_job("sync-kvic-funds", runtime=runtime, config=config)

    assert result["job_name"] == "sync-kvic-funds"
    assert result["fund_count"] == 2
    assert seen["client"] is runtime.kvic_client
    assert seen["review_queue"] is runtime.review_queue
    assert seen["search_client"] is runtime.web_search_client
    assert seen["llm_client"] is runtime.llm_client
    assert seen["sync_interval_seconds"] == 86400
    assert seen["fund_description_batch_limit"] == 25
    assert seen["fund_description_stale_days"] == 45
    assert seen["fund_search_max_results"] == 7


def test_run_research_investors_routes_to_pipeline(monkeypatch, tmp_path) -> None:
    runtime = _runtime(tmp_path)
    seen: dict[str, object] = {}

    def fake_research_investors(**kwargs):
        seen.update(kwargs)
        return InvestorResearchResult(
            run_id="run_investor_research_test",
            status="success",
            investor_count=12,
            researched_count=3,
            success_count=2,
        )

    monkeypatch.setattr("merry_runtime.job_runner.research_investors", fake_research_investors)
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        review_sheet_id="sheet-1",
        wiki_root=tmp_path,
        structured_store_backend="sqlite",
        anthropic_api_key="anthropic-key",
        investor_research_batch_limit=3,
        investor_research_stale_days=5,
        investor_research_search_max_results=8,
    )

    result = run_job("research-investors", runtime=runtime, config=config)

    assert result["job_name"] == "research-investors"
    assert result["researched_count"] == 3
    assert seen["structured_store"] is runtime.structured_store
    assert seen["review_queue"] is runtime.review_queue
    assert seen["search_client"] is runtime.web_search_client
    assert seen["llm_client"] is runtime.llm_client
    assert seen["batch_limit"] == 3
    assert seen["stale_days"] == 5
    assert seen["search_max_results"] == 8


def test_run_weekly_summary_includes_failures_reviews_and_resolution_events(tmp_path) -> None:
    store = FakeStructuredStore.seed_candidate_card()
    store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": "run_failed",
                "job_name": "score-candidates",
                "status": "failed",
                "started_at": "2026-05-18T00:00:00+00:00",
                "finished_at": "2026-05-18T00:01:00+00:00",
                "input_count": 1,
                "output_count": 0,
                "error_message": "RuntimeError: source body included founder@example.com",
            }
        ],
        key_fields=("run_id",),
    )
    store.upsert_rows(
        table="reviews",
        rows=[
            {
                "review_id": "review_1",
                "card_id": "card_1",
                "reviewer": "boram",
                "decision": "advance",
                "memo": "contains private notes",
                "reviewed_at": "2026-05-18T00:02:00+00:00",
            }
        ],
        key_fields=("review_id",),
    )
    store.upsert_rows(
        table="entity_resolution_events",
        rows=[
            {
                "event_id": "evt_1",
                "candidate_entity_id": "ent_new",
                "matched_entity_id": "ent_old",
                "action": "merge_candidate",
                "probability": 0.87,
                "features_json": "{}",
                "rationale": "May include private rationale",
                "status": "pending_review",
                "created_at": "2026-05-18T00:03:00+00:00",
            }
        ],
        key_fields=("event_id",),
    )
    runtime = _runtime(tmp_path, store=store)

    result = run_job("weekly-summary", runtime=runtime, config=_config(tmp_path))

    text = runtime.notifier.messages[0]["text"]
    assert result["job_name"] == "weekly-summary"
    assert "failed_jobs=1" in text
    assert "reviews=1" in text
    assert "resolution_pending=1" in text
    assert "priority=1" in text
    assert "founder@example.com" not in text
    assert "private" not in text


def test_run_resolve_entities_persists_resolution_events(tmp_path) -> None:
    store = FakeStructuredStore()
    store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": "ent_a",
                "entity_type": "startup",
                "name": "Merry AI",
                "normalized_name": "merryai",
                "region": "Seoul",
                "homepage": "https://merry.example",
                "first_seen_at": "2026-05-01T00:00:00+00:00",
                "last_seen_at": "2026-05-01T00:00:00+00:00",
            },
            {
                "entity_id": "ent_b",
                "entity_type": "startup",
                "name": "Merry",
                "normalized_name": "merry",
                "region": "Seoul",
                "homepage": "https://merry.example",
                "first_seen_at": "2026-05-18T00:00:00+00:00",
                "last_seen_at": "2026-05-18T00:00:00+00:00",
            },
        ],
        key_fields=("entity_id",),
    )
    runtime = _runtime(tmp_path, store=store)

    result = run_job("resolve-entities", runtime=runtime, config=_config(tmp_path))

    assert result["job_name"] == "resolve-entities"
    assert result["event_count"] == 1
    assert result["merge_candidate_count"] == 1
    assert result["needs_review_count"] == 0
    assert store.tables["entity_resolution_events"][0]["status"] == "pending_review"
    assert [row["entity_id"] for row in store.tables["mother_entities"]] == ["ent_a", "ent_b"]


def test_run_enrich_sminfo_passes_agent_identity(monkeypatch, tmp_path) -> None:
    runtime = _runtime(tmp_path)
    runtime.sminfo_client = object()
    seen: dict[str, object] = {}

    def fake_enrich_sminfo_candidates(**kwargs):
        seen["agent_id"] = kwargs["agent_id"]
        seen["stale_days"] = kwargs["stale_days"]
        return SminfoEnrichmentResult(
            run_id="run_sminfo_agent",
            candidate_count=0,
            processed_count=0,
            matched_count=0,
            not_found_count=0,
            ambiguous_count=0,
            error_count=0,
        )

    monkeypatch.setattr("merry_runtime.job_runner.enrich_sminfo_candidates", fake_enrich_sminfo_candidates)
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        review_sheet_id="sheet-1",
        wiki_root=tmp_path,
        sminfo_user_id="user",
        sminfo_password="password",
        hermes_agent_id="runpod-pod-1",
        sminfo_stale_days=17,
    )

    result = run_job("enrich-sminfo", runtime=runtime, config=config)

    assert result["job_name"] == "enrich-sminfo"
    assert seen == {"agent_id": "runpod-pod-1", "stale_days": 17}


def test_run_draft_outreach_emails_uses_candidate_detail_contacts(monkeypatch, tmp_path) -> None:
    runtime = _runtime(tmp_path)
    runtime.email_draft_client = object()
    seen: dict[str, object] = {}

    def fake_draft_outreach_emails(**kwargs):
        seen["draft_client"] = kwargs["draft_client"]
        seen["max_items"] = kwargs["max_items"]
        return OutreachDraftResult(
            run_id="run_outreach_job",
            candidate_count=2,
            drafted_count=1,
            skipped_count=1,
            error_count=0,
        )

    monkeypatch.setattr("merry_runtime.job_runner.draft_outreach_emails", fake_draft_outreach_emails)

    result = run_job("draft-outreach-emails", runtime=runtime, config=_config(tmp_path))

    assert result["job_name"] == "draft-outreach-emails"
    assert result["drafted_count"] == 1
    assert seen["draft_client"] is runtime.email_draft_client
    assert seen["max_items"] == 10


def test_run_job_rejects_missing_ingest_sources(tmp_path) -> None:
    with pytest.raises(JobRunError):
        run_job("ingest-sources", runtime=_runtime(tmp_path), config=_config(tmp_path))


def test_run_job_rejects_missing_ingest_ac_profile_sources(tmp_path) -> None:
    with pytest.raises(JobRunError):
        run_job("ingest-ac-profiles", runtime=_runtime(tmp_path), config=_config(tmp_path))
