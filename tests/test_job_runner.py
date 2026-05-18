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
    [run_row] = store.tables["agent_runs"]
    assert run_row["run_id"] == result["run_id"]
    assert run_row["job_name"] == "weekly-summary"
    assert run_row["status"] == "success"
    assert run_row["started_at"]
    assert run_row["finished_at"]
    assert run_row["input_count"] == 1
    assert run_row["output_count"] == 1
    assert run_row["error_message"] == ""


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


def test_run_job_rejects_missing_ingest_sources(tmp_path) -> None:
    with pytest.raises(JobRunError):
        run_job("ingest-sources", runtime=_runtime(tmp_path), config=_config(tmp_path))
