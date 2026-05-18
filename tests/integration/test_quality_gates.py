from merry_runtime.adapters.fakes import FakeObjectStore, FakeReviewQueue, FakeStructuredStore
from merry_runtime.hermes_profile import HermesProfileError, build_production_profile, validate_tool_lockdown
from merry_runtime.pipelines.ingest_sources import ingest_sources
from merry_runtime.pipelines.score_candidates import score_candidates
from merry_runtime.pipelines.sync_review_sheet import sync_review_sheet


def test_50_candidate_dry_run_preserves_evidence_rationale() -> None:
    store = _seed_candidate_store(50)
    queue = FakeReviewQueue()

    result = score_candidates(structured_store=store, review_queue=queue, ac_id="ac_climate")

    assert result.card_count == 50
    assert len(store.tables["ac_scores"]) == 50
    assert all("source_signals=sig_" in row["rationale"] for row in store.tables["ac_scores"])
    assert all(row["decision"] == "" for row in queue.published["ac_climate"])


def test_human_review_dry_run_updates_one_review_and_one_card_status() -> None:
    store = FakeStructuredStore.seed_candidate_card()
    queue = FakeReviewQueue()
    queue.seed_reviews("ac_climate", [{"card_id": "card_1", "reviewer": "boram", "decision": "advance"}])

    result = sync_review_sheet(structured_store=store, review_queue=queue, ac_id="ac_climate")

    assert result.review_count == 1
    assert len(store.tables["reviews"]) == 1
    assert store.tables["candidate_cards"][0]["status"] == "advanced"


def test_safety_dry_run_fails_when_dangerous_toolset_is_enabled() -> None:
    profile = build_production_profile()
    profile["toolsets"]["file"] = True

    try:
        validate_tool_lockdown(profile)
    except HermesProfileError as exc:
        assert "Dangerous toolsets" in str(exc)
    else:
        raise AssertionError("Expected HermesProfileError")


def test_privacy_and_operations_dry_run_redacts_signals_and_writes_agent_run() -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    store = FakeStructuredStore()

    ingest_sources(
        sources=[
            {
                "channel": "info_mail",
                "payload": "Subject: Info mail\nFrom: founder@merry.ai\nCompany: Merry AI\nRegion: Seoul\nIndustry: AI\nSignal: traction\nConfidence: 0.8\nTags: ai\nEvidence: Contact founder@merry.ai / 010-1234-5678.",
            }
        ],
        object_store=object_store,
        structured_store=store,
    )

    assert store.tables["signals"][0]["evidence_text"] == "Contact [REDACTED_EMAIL] / [REDACTED_PHONE]."
    assert store.tables["agent_runs"][0]["job_name"] == "ingest-sources"
    assert store.tables["agent_runs"][0]["status"] == "success"


def test_1000_candidate_scale_dry_run_scores_all_candidates() -> None:
    store = _seed_candidate_store(1000)
    queue = FakeReviewQueue()

    result = score_candidates(structured_store=store, review_queue=queue, ac_id="ac_climate")

    assert result.score_count == 1000
    assert result.card_count == 1000
    assert len(queue.published["ac_climate"]) == 1000


def _seed_candidate_store(candidate_count: int) -> FakeStructuredStore:
    store = FakeStructuredStore()
    store.upsert_rows(
        table="ac_profiles",
        rows=[
            {
                "ac_id": "ac_climate",
                "ac_name": "Climate Impact AC",
                "fund_purpose": "climate impact fund",
                "recruiting_area": "Jeonbuk",
                "hypothesis_tags": ["climate", "agritech"],
                "impact_priority": ["carbon", "rural"],
                "region_preferences": ["Jeonbuk"],
                "industry_preferences": ["AgriTech"],
                "tech_preferences": ["AI"],
            }
        ],
        key_fields=("ac_id",),
    )
    store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": f"ent_{index}",
                "name": f"CareFarm Carbon {index}",
                "region": "Jeonbuk",
                "industry": "AgriTech",
                "homepage": f"https://carefarm-{index}.example",
            }
            for index in range(candidate_count)
        ],
        key_fields=("entity_id",),
    )
    store.upsert_rows(
        table="signals",
        rows=[
            {
                "signal_id": f"sig_{index}",
                "entity_id": f"ent_{index}",
                "signal_type": "impact",
                "evidence_text": "Reduces carbon emissions for small farms with verified pilots.",
                "source_id": f"src_{index}",
                "confidence": 0.9,
                "tags": ["climate", "carbon", "rural", "impact"],
            }
            for index in range(candidate_count)
        ],
        key_fields=("signal_id",),
    )
    return store
