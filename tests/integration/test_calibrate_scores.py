from merry_runtime.adapters.fakes import FakeReviewQueue, FakeStructuredStore
from merry_runtime.pipelines.calibrate_scores import calibrate_scores
from merry_runtime.pipelines.score_candidates import score_candidates
from merry_runtime.probabilistic_scoring import PriorityScoringModel


def test_calibrate_scores_writes_coefficients_and_agent_run_from_review_corpus() -> None:
    store = _review_corpus_store()

    result = calibrate_scores(structured_store=store, ac_id="ac_climate", run_id="run_calibrate_test")

    assert result.run_id == "run_calibrate_test"
    assert result.sample_count == 10
    assert result.coefficient_count == 1
    [row] = store.tables["ac_scoring_coefficients"]
    assert row["ac_id"] == "ac_climate"
    assert row["sample_count"] == 10
    assert row["model_version"] == "calibrated-v1"
    assert row["corpus_hash"]
    assert row["fund_fit"] > PriorityScoringModel.default().fund_fit
    [agent_run] = store.tables["agent_runs"]
    assert agent_run["job_name"] == "calibrate-scores"
    assert agent_run["status"] == "success"
    assert agent_run["input_count"] == 10
    assert agent_run["output_count"] == 1


def test_calibrate_scores_writes_zero_output_agent_run_when_no_usable_reviews() -> None:
    store = FakeStructuredStore()

    result = calibrate_scores(structured_store=store, ac_id="ac_climate", run_id="run_empty_calibrate")

    assert result.sample_count == 0
    assert result.coefficient_count == 0
    assert store.tables["ac_scoring_coefficients"] == []
    [agent_run] = store.tables["agent_runs"]
    assert agent_run["job_name"] == "calibrate-scores"
    assert agent_run["input_count"] == 0
    assert agent_run["output_count"] == 0


def test_score_candidates_uses_ac_specific_coefficient_row_when_present() -> None:
    store = FakeStructuredStore.seed_climate_candidate()
    result = score_candidates(
        structured_store=store,
        review_queue=FakeReviewQueue(),
        ac_id="ac_climate",
        run_id="run_score_default",
    )
    assert result.score_count == 1
    store.tables["ac_scores"] = []
    store.tables["candidate_cards"] = []
    store.tables["agent_runs"] = []
    store.upsert_rows(
        table="ac_scoring_coefficients",
        rows=[
            {
                "ac_id": "ac_climate",
                "beta0": -8.0,
                "fund_fit": 1.5,
                "recruitment_fit": 1.2,
                "impact_fit": 1.8,
                "channel_trust": 1.4,
                "multi_channel_signal": 0.8,
                "prior_decision": 0.7,
                "freshness": 0.5,
                "risk": 1.1,
                "sample_count": 10,
                "model_version": "calibrated-v1",
                "corpus_hash": "corpus-1",
                "updated_at": "2026-05-18T00:00:00+00:00",
            }
        ],
        key_fields=("ac_id",),
    )

    score_candidates(
        structured_store=store,
        review_queue=FakeReviewQueue(),
        ac_id="ac_climate",
        run_id="run_score_calibrated",
    )

    [score_row] = store.tables["ac_scores"]
    assert score_row["model_version"] == "calibrated-v1"
    assert score_row["priority_probability"] < 0.75


def test_calibrate_scores_disables_stale_coefficients_when_review_corpus_disappears() -> None:
    store = FakeStructuredStore.seed_climate_candidate()
    store.upsert_rows(
        table="ac_scoring_coefficients",
        rows=[
            {
                "ac_id": "ac_climate",
                "beta0": -8.0,
                "fund_fit": 1.5,
                "recruitment_fit": 1.2,
                "impact_fit": 1.8,
                "channel_trust": 1.4,
                "multi_channel_signal": 0.8,
                "prior_decision": 0.7,
                "freshness": 0.5,
                "risk": 1.1,
                "sample_count": 10,
                "model_version": "calibrated-v1",
                "corpus_hash": "old-corpus",
                "updated_at": "2026-05-18T00:00:00+00:00",
            }
        ],
        key_fields=("ac_id",),
    )

    result = calibrate_scores(structured_store=store, ac_id="ac_climate", run_id="run_disable_stale")

    assert result.sample_count == 0
    assert result.coefficient_count == 1
    [disabled_row] = store.tables["ac_scoring_coefficients"]
    assert disabled_row["sample_count"] == 0
    assert disabled_row["model_version"] == "manual-v1"
    assert disabled_row["corpus_hash"] == "no-usable-examples"

    score_candidates(
        structured_store=store,
        review_queue=FakeReviewQueue(),
        ac_id="ac_climate",
        run_id="run_score_after_disable",
    )

    [score_row] = store.tables["ac_scores"]
    assert score_row["model_version"] == "manual-v1"
    assert score_row["priority_probability"] >= 0.75


def test_calibrate_scores_does_not_rewrite_unchanged_review_corpus() -> None:
    store = _review_corpus_store()
    first = calibrate_scores(structured_store=store, ac_id="ac_climate", run_id="run_calibrate_first")
    assert first.coefficient_count == 1
    first_row = dict(store.tables["ac_scoring_coefficients"][0])
    first_row["updated_at"] = "2026-05-18T00:00:00+00:00"
    store.upsert_rows(table="ac_scoring_coefficients", rows=[first_row], key_fields=("ac_id",))

    second = calibrate_scores(structured_store=store, ac_id="ac_climate", run_id="run_calibrate_second")

    [row] = store.tables["ac_scoring_coefficients"]
    assert second.sample_count == 10
    assert second.coefficient_count == 0
    assert row["corpus_hash"] == first_row["corpus_hash"]
    assert row["updated_at"] == "2026-05-18T00:00:00+00:00"
    assert store.tables["agent_runs"][-1]["output_count"] == 0


def _review_corpus_store() -> FakeStructuredStore:
    store = FakeStructuredStore()
    for index in range(10):
        entity_id = f"ent_{index}"
        card_id = f"card_{index}"
        store.upsert_rows(
            table="candidate_cards",
            rows=[
                {
                    "card_id": card_id,
                    "ac_id": "ac_climate",
                    "entity_id": entity_id,
                    "summary": "Strong climate impact candidate.",
                    "recommended_action": "advance",
                    "queue_type": "priority",
                    "status": "new",
                    "created_at": "2026-05-18T00:00:00+00:00",
                }
            ],
            key_fields=("card_id",),
        )
        store.upsert_rows(
            table="ac_scores",
            rows=[
                {
                    "score_id": f"score_ac_climate_{entity_id}",
                    "ac_id": "ac_climate",
                    "entity_id": entity_id,
                    "base_score": 30.0,
                    "fund_fit_score": 14.0,
                    "recruiting_fit_score": 13.0,
                    "hypothesis_fit_score": 15.0,
                    "impact_fit_score": 19.0,
                    "total_score": 91.0,
                    "priority_probability": 0.91,
                    "priority_utility": 2.3,
                    "queue_type": "priority",
                    "uncertainty": 0.1,
                    "model_version": "manual-v1",
                    "rationale": "components only",
                    "recommended_action": "advance",
                    "scored_at": "2026-05-18T00:00:00+00:00",
                }
            ],
            key_fields=("score_id",),
        )
        store.upsert_rows(
            table="reviews",
            rows=[
                {
                    "review_id": f"review_{index}",
                    "card_id": card_id,
                    "reviewer": "boram",
                    "decision": "advance",
                    "memo": "",
                    "reviewed_at": "2026-05-18T00:01:00+00:00",
                }
            ],
            key_fields=("review_id",),
        )
    return store
