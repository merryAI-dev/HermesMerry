from merry_runtime.adapters.fakes import FakeReviewQueue, FakeStructuredStore
from merry_runtime.pipelines.score_candidates import score_candidates


def test_score_candidates_creates_ac_scores_cards_and_sheet_rows() -> None:
    store = FakeStructuredStore.seed_climate_candidate()
    queue = FakeReviewQueue()

    result = score_candidates(structured_store=store, review_queue=queue, ac_id="ac_climate")

    assert result.score_count == 1
    assert result.card_count == 1
    assert store.tables["ac_scores"][0]["recommended_action"] == "advance"
    assert store.tables["ac_scores"][0]["priority_probability"] >= 0.75
    assert store.tables["ac_scores"][0]["queue_type"] == "priority"
    assert store.tables["candidate_cards"][0]["status"] == "new"
    assert store.tables["candidate_cards"][0]["queue_type"] == "priority"
    assert queue.published["ac_climate"][0]["decision"] == ""
    assert queue.published["ac_climate"][0]["review_memo"] == ""
    assert queue.published["ac_climate"][0]["queue_type"] == "priority"
    assert queue.published["ac_climate"][0]["contact_email"] == "hello@carefarm.example"
    assert store.tables["agent_runs"][0]["job_name"] == "score-candidates"


def test_score_candidates_skips_entities_without_signals() -> None:
    store = FakeStructuredStore.seed_climate_candidate()
    store.upsert_rows(
        table="mother_entities",
        rows=[{"entity_id": "ent_empty", "name": "No Signal Co", "region": "Jeonbuk", "industry": "AgriTech"}],
        key_fields=("entity_id",),
    )
    queue = FakeReviewQueue()

    result = score_candidates(structured_store=store, review_queue=queue, ac_id="ac_climate")

    assert result.score_count == 1
    assert [row["entity_id"] for row in store.tables["ac_scores"]] == ["ent_climate"]


def test_score_candidates_preserves_human_status_and_does_not_republish_existing_cards() -> None:
    store = FakeStructuredStore.seed_climate_candidate()
    queue = FakeReviewQueue()
    score_candidates(structured_store=store, review_queue=queue, ac_id="ac_climate")
    existing_card = dict(store.tables["candidate_cards"][0])
    existing_card["status"] = "watchlist"
    store.upsert_rows(table="candidate_cards", rows=[existing_card], key_fields=("card_id",))

    result = score_candidates(structured_store=store, review_queue=queue, ac_id="ac_climate")

    assert result.card_count == 1
    assert store.tables["candidate_cards"][0]["status"] == "watchlist"
    assert len(queue.published["ac_climate"]) == 1
