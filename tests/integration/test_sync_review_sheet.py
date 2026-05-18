from merry_runtime.adapters.fakes import FakeReviewQueue, FakeStructuredStore
from merry_runtime.pipelines.sync_review_sheet import sync_review_sheet


def test_sync_review_sheet_persists_human_decisions_and_updates_cards() -> None:
    store = FakeStructuredStore.seed_candidate_card()
    queue = FakeReviewQueue()
    queue.seed_reviews(
        "ac_climate",
        [{"card_id": "card_1", "reviewer": "boram", "decision": "watchlist", "review_memo": "Need sales proof"}],
    )

    result = sync_review_sheet(structured_store=store, review_queue=queue, ac_id="ac_climate")

    assert result.review_count == 1
    assert result.rejected_row_count == 0
    assert store.tables["candidate_cards"][0]["status"] == "watchlist"
    assert store.tables["reviews"][0]["decision"] == "watchlist"
    assert store.tables["reviews"][0]["memo"] == "Need sales proof"
    assert store.tables["agent_runs"][0]["status"] == "success"


def test_sync_review_sheet_records_invalid_review_rows_without_updating_cards() -> None:
    store = FakeStructuredStore.seed_candidate_card()
    queue = FakeReviewQueue()
    queue.seed_reviews("ac_climate", [{"card_id": "card_1", "reviewer": "boram", "decision": "maybe"}])

    result = sync_review_sheet(structured_store=store, review_queue=queue, ac_id="ac_climate")

    assert result.review_count == 0
    assert result.rejected_row_count == 1
    assert store.tables["candidate_cards"][0]["status"] == "new"
    assert store.tables["agent_runs"][0]["status"] == "partial_success"
    assert "Invalid decision" in store.tables["agent_runs"][0]["error_message"]
