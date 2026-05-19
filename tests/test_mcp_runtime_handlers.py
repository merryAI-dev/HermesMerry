import pytest

from merry_mcp.runtime_handlers import build_runtime_handlers
from merry_runtime.adapters.fakes import FakeObjectStore, FakeReviewQueue, FakeStructuredStore
from merry_runtime.job_runner import RuntimeAdapters
from merry_runtime.pipelines.crawl_sources import CrawlResult
from merry_runtime.pipelines.draft_outreach_emails import OutreachDraftResult
from merry_runtime.pipelines.enrich_sminfo import SminfoEnrichmentResult
from merry_runtime.pipelines.research_investors import InvestorResearchResult
from merry_runtime.pipelines.sync_kvic_funds import KVICSyncResult
from merry_runtime.runtime_config import RuntimeConfig


def test_runtime_handlers_wire_crawl_public_sources_to_pipeline(tmp_path) -> None:
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
    )
    config = RuntimeConfig(project_id="", dataset_id="", raw_bucket="", wiki_root=tmp_path)
    seen_targets = []

    def fake_crawl_sources(**kwargs):
        seen_targets.extend(kwargs["targets"])
        return CrawlResult(
            run_id="run_crawl_tool",
            target_count=1,
            crawled_source_count=5,
            ingested_raw_source_count=5,
            ingested_entity_count=5,
            ingested_signal_count=5,
        )

    handlers = build_runtime_handlers(runtime=runtime, config=config, crawl_sources_fn=fake_crawl_sources)

    result = handlers["crawl_public_sources"](
        {"targets": [{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma", "max_cards": 5}]}
    )

    assert result["job_name"] == "crawl-sources"
    assert result["crawled_source_count"] == 5
    assert seen_targets == [{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma", "max_cards": 5}]


def test_runtime_handlers_wire_enrich_sminfo_candidates_to_pipeline(tmp_path) -> None:
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
        sminfo_client=object(),
    )
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        review_sheet_id="sheet-1",
        wiki_root=tmp_path,
        sminfo_user_id="user",
        sminfo_password="password",
        sminfo_stale_days=14,
    )
    seen_payloads = []

    def fake_enrich_sminfo_candidates(**kwargs):
        seen_payloads.append(kwargs)
        return SminfoEnrichmentResult(
            run_id="run_sminfo_tool",
            candidate_count=2,
            processed_count=2,
            matched_count=1,
            not_found_count=1,
            ambiguous_count=0,
            error_count=0,
        )

    handlers = build_runtime_handlers(
        runtime=runtime,
        config=config,
        enrich_sminfo_candidates_fn=fake_enrich_sminfo_candidates,
    )

    result = handlers["enrich_sminfo_candidates"]({"max_items": 2, "company_names": ["에이아이오", "바이트랩"]})

    assert result["job_name"] == "enrich-sminfo"
    assert result["processed_count"] == 2
    assert seen_payloads[0]["max_items"] == 2
    assert seen_payloads[0]["company_names"] == ["에이아이오", "바이트랩"]
    assert seen_payloads[0]["client"] is runtime.sminfo_client
    assert seen_payloads[0]["stale_days"] == 14


def test_runtime_handlers_wire_draft_outreach_emails_to_pipeline(tmp_path) -> None:
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
        email_draft_client=object(),
    )
    config = RuntimeConfig(project_id="", dataset_id="", raw_bucket="", review_sheet_id="sheet-1", wiki_root=tmp_path)
    seen_payloads = []

    def fake_draft_outreach_emails(**kwargs):
        seen_payloads.append(kwargs)
        return OutreachDraftResult(
            run_id="run_outreach_tool",
            candidate_count=2,
            drafted_count=1,
            skipped_count=1,
            error_count=0,
        )

    handlers = build_runtime_handlers(
        runtime=runtime,
        config=config,
        draft_outreach_emails_fn=fake_draft_outreach_emails,
    )

    result = handlers["draft_outreach_emails"]({"max_items": 2, "company_names": ["에이아이오"]})

    assert result["job_name"] == "draft-outreach-emails"
    assert result["drafted_count"] == 1
    assert seen_payloads[0]["max_items"] == 2
    assert seen_payloads[0]["company_names"] == ["에이아이오"]
    assert seen_payloads[0]["draft_client"] is runtime.email_draft_client


def test_runtime_handlers_wire_sync_kvic_funds_to_pipeline(tmp_path) -> None:
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
        kvic_client=object(),
    )
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        review_sheet_id="sheet-1",
        wiki_root=tmp_path,
        kvic_api_key="public-key",
        kvic_sync_interval_seconds=86400,
    )
    seen_payloads = []

    def fake_sync_kvic_funds(**kwargs):
        seen_payloads.append(kwargs)
        return KVICSyncResult(
            run_id="run_kvic_tool",
            status="success",
            fund_type_count=1,
            fund_count=2,
            manager_count=1,
        )

    handlers = build_runtime_handlers(
        runtime=runtime,
        config=config,
        sync_kvic_funds_fn=fake_sync_kvic_funds,
    )

    result = handlers["sync_kvic_funds"]({"force": True})

    assert result["job_name"] == "sync-kvic-funds"
    assert result["manager_count"] == 1
    assert seen_payloads[0]["client"] is runtime.kvic_client
    assert seen_payloads[0]["review_queue"] is runtime.review_queue
    assert seen_payloads[0]["sync_interval_seconds"] == 0


def test_runtime_handlers_wire_research_investors_to_pipeline(tmp_path) -> None:
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
        web_search_client=object(),
        llm_client=object(),
    )
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        review_sheet_id="sheet-1",
        wiki_root=tmp_path,
        anthropic_api_key="anthropic-key",
        investor_research_batch_limit=10,
        investor_research_stale_days=7,
        investor_research_search_max_results=5,
    )
    seen_payloads = []

    def fake_research_investors(**kwargs):
        seen_payloads.append(kwargs)
        return InvestorResearchResult(
            run_id="run_investor_tool",
            status="success",
            investor_count=20,
            researched_count=10,
            success_count=7,
        )

    handlers = build_runtime_handlers(
        runtime=runtime,
        config=config,
        research_investors_fn=fake_research_investors,
    )

    result = handlers["research_investors"]({"max_items": 3})

    assert result["job_name"] == "research-investors"
    assert result["success_count"] == 7
    assert seen_payloads[0]["structured_store"] is runtime.structured_store
    assert seen_payloads[0]["review_queue"] is runtime.review_queue
    assert seen_payloads[0]["search_client"] is runtime.web_search_client
    assert seen_payloads[0]["llm_client"] is runtime.llm_client
    assert seen_payloads[0]["batch_limit"] == 3


def test_runtime_handlers_require_configured_sminfo_client_for_enrichment(tmp_path) -> None:
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
    )
    config = RuntimeConfig(project_id="", dataset_id="", raw_bucket="", review_sheet_id="sheet-1", wiki_root=tmp_path)

    handlers = build_runtime_handlers(runtime=runtime, config=config)

    with pytest.raises(RuntimeError, match="SMINFO client is not configured"):
        handlers["enrich_sminfo_candidates"]({"max_items": 1})


def test_runtime_handlers_require_configured_email_draft_client(tmp_path) -> None:
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
    )
    config = RuntimeConfig(project_id="", dataset_id="", raw_bucket="", review_sheet_id="sheet-1", wiki_root=tmp_path)

    handlers = build_runtime_handlers(runtime=runtime, config=config)

    with pytest.raises(RuntimeError, match="Email draft client is not configured"):
        handlers["draft_outreach_emails"]({"max_items": 1})


def test_runtime_handlers_require_configured_kvic_client(tmp_path) -> None:
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
    )
    config = RuntimeConfig(project_id="", dataset_id="", raw_bucket="", review_sheet_id="sheet-1", wiki_root=tmp_path)

    handlers = build_runtime_handlers(runtime=runtime, config=config)

    with pytest.raises(RuntimeError, match="KVIC client is not configured"):
        handlers["sync_kvic_funds"]({})


def test_runtime_handlers_require_configured_llm_client_for_investor_research(tmp_path) -> None:
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
        web_search_client=object(),
    )
    config = RuntimeConfig(project_id="", dataset_id="", raw_bucket="", review_sheet_id="sheet-1", wiki_root=tmp_path)

    handlers = build_runtime_handlers(runtime=runtime, config=config)

    with pytest.raises(RuntimeError, match="LLM client is not configured"):
        handlers["research_investors"]({})
