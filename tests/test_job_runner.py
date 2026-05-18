import json

import pytest

from merry_runtime.adapters.fakes import FakeNotifier, FakeObjectStore, FakeReviewQueue, FakeStructuredStore
from merry_runtime.job_runner import JobRunError, RuntimeAdapters, run_job
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


def test_run_score_candidates_routes_to_sheet_queue(tmp_path) -> None:
    store = FakeStructuredStore.seed_climate_candidate()
    runtime = _runtime(tmp_path, store=store)

    result = run_job("score-candidates", runtime=runtime, config=_config(tmp_path), ac_id="ac_climate")

    assert result["job_name"] == "score-candidates"
    assert result["card_count"] == 1
    assert runtime.review_queue.published["ac_climate"][0]["queue_type"] == "priority"


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


def test_run_job_rejects_missing_ingest_sources(tmp_path) -> None:
    with pytest.raises(JobRunError):
        run_job("ingest-sources", runtime=_runtime(tmp_path), config=_config(tmp_path))
