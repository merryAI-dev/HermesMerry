from merry_mcp.runtime_handlers import build_runtime_handlers
from merry_runtime.adapters.fakes import FakeObjectStore, FakeReviewQueue, FakeStructuredStore
from merry_runtime.job_runner import RuntimeAdapters
from merry_runtime.pipelines.crawl_sources import CrawlResult
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
