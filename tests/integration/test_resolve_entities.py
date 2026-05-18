from merry_runtime.adapters.fakes import FakeReviewQueue, FakeStructuredStore
from merry_runtime.pipelines.resolve_entities import resolve_entities


def test_resolve_entities_persists_high_probability_merge_candidate_without_deleting_rows() -> None:
    store = FakeStructuredStore()
    store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": "ent_existing",
                "entity_type": "startup",
                "name": "CareFarm Carbon",
                "normalized_name": "carefarmcarbon",
                "region": "Jeonbuk",
                "industry": "AgriTech",
                "homepage": "https://carefarm.example",
                "first_seen_at": "2026-05-01T00:00:00+00:00",
                "last_seen_at": "2026-05-01T00:00:00+00:00",
            },
            {
                "entity_id": "ent_candidate",
                "entity_type": "startup",
                "name": "CareFarm",
                "normalized_name": "carefarm",
                "region": "Jeonbuk",
                "industry": "AgriTech",
                "homepage": "https://carefarm.example",
                "first_seen_at": "2026-05-18T00:00:00+00:00",
                "last_seen_at": "2026-05-18T00:00:00+00:00",
            },
        ],
        key_fields=("entity_id",),
    )
    queue = FakeReviewQueue()

    result = resolve_entities(structured_store=store, review_queue=queue, run_id="run_resolve_test")

    assert result.event_count == 1
    assert result.merge_candidate_count == 1
    assert result.needs_review_count == 0
    event = store.tables["entity_resolution_events"][0]
    assert event["candidate_entity_id"] == "ent_candidate"
    assert event["matched_entity_id"] == "ent_existing"
    assert event["action"] == "merge_candidate"
    assert event["status"] == "pending_review"
    assert [row["entity_id"] for row in store.tables["mother_entities"]] == ["ent_existing", "ent_candidate"]
    assert queue.published["entity_resolution"][0]["candidate_entity_id"] == "ent_candidate"
    assert store.tables["agent_runs"][0]["output_count"] == 1


def test_resolve_entities_rerun_does_not_duplicate_pending_events_or_sheet_rows() -> None:
    store = FakeStructuredStore()
    store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": "ent_existing",
                "entity_type": "startup",
                "name": "CareFarm Carbon",
                "normalized_name": "carefarmcarbon",
                "region": "Jeonbuk",
                "industry": "AgriTech",
                "homepage": "https://carefarm.example",
                "first_seen_at": "2026-05-01T00:00:00+00:00",
                "last_seen_at": "2026-05-01T00:00:00+00:00",
            },
            {
                "entity_id": "ent_candidate",
                "entity_type": "startup",
                "name": "CareFarm",
                "normalized_name": "carefarm",
                "region": "Jeonbuk",
                "industry": "AgriTech",
                "homepage": "https://carefarm.example",
                "first_seen_at": "2026-05-18T00:00:00+00:00",
                "last_seen_at": "2026-05-18T00:00:00+00:00",
            },
        ],
        key_fields=("entity_id",),
    )
    queue = FakeReviewQueue()

    first = resolve_entities(structured_store=store, review_queue=queue)
    second = resolve_entities(structured_store=store, review_queue=queue)

    assert first.event_count == 1
    assert second.event_count == 1
    assert len(store.tables["entity_resolution_events"]) == 1
    assert len(queue.published["entity_resolution"]) == 1
    assert [row["entity_id"] for row in store.tables["mother_entities"]] == ["ent_existing", "ent_candidate"]


def test_resolve_entities_compares_candidates_only_against_earlier_sorted_observations() -> None:
    store = FakeStructuredStore()
    store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": "ent_z_candidate",
                "entity_type": "startup",
                "name": "Merry",
                "normalized_name": "merry",
                "region": "Seoul",
                "industry": "SaaS",
                "homepage": "https://merry.example",
                "first_seen_at": "2026-05-18T00:00:00+00:00",
                "last_seen_at": "2026-05-18T00:00:00+00:00",
            },
            {
                "entity_id": "ent_a_existing",
                "entity_type": "startup",
                "name": "Merry AI",
                "normalized_name": "merryai",
                "region": "Seoul",
                "industry": "SaaS",
                "homepage": "https://merry.example",
                "first_seen_at": "2026-05-01T00:00:00+00:00",
                "last_seen_at": "2026-05-01T00:00:00+00:00",
            },
        ],
        key_fields=("entity_id",),
    )

    result = resolve_entities(structured_store=store, review_queue=FakeReviewQueue(), run_id="run_order_test")

    assert result.event_count == 1
    event = store.tables["entity_resolution_events"][0]
    assert event["candidate_entity_id"] == "ent_z_candidate"
    assert event["matched_entity_id"] == "ent_a_existing"


def test_resolve_entities_persists_needs_review_event_for_ambiguous_match() -> None:
    store = FakeStructuredStore()
    store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": "ent_impact_existing",
                "entity_type": "startup",
                "name": "Impact Foundry",
                "normalized_name": "impactfoundry",
                "region": "Busan",
                "industry": "Manufacturing",
                "homepage": "https://impactfoundry.example",
                "representative": "Min Kim",
                "first_seen_at": "2026-05-01T00:00:00+00:00",
                "last_seen_at": "2026-05-01T00:00:00+00:00",
            },
            {
                "entity_id": "ent_impact_candidate",
                "entity_type": "startup",
                "name": "Impact Foundry",
                "normalized_name": "impactfoundry",
                "region": "Seoul",
                "industry": "SaaS",
                "homepage": "https://impactfoundry-ai.example",
                "representative": "Jin Park",
                "first_seen_at": "2026-05-18T00:00:00+00:00",
                "last_seen_at": "2026-05-18T00:00:00+00:00",
            },
        ],
        key_fields=("entity_id",),
    )
    queue = FakeReviewQueue()

    result = resolve_entities(structured_store=store, review_queue=queue, run_id="run_review_test")

    assert result.event_count == 1
    assert result.merge_candidate_count == 0
    assert result.needs_review_count == 1
    event = store.tables["entity_resolution_events"][0]
    assert event["candidate_entity_id"] == "ent_impact_candidate"
    assert event["matched_entity_id"] == "ent_impact_existing"
    assert event["action"] == "needs_review"
    assert event["status"] == "pending_review"
    assert queue.published["entity_resolution"][0]["action"] == "needs_review"


def test_resolve_entities_does_not_publish_event_for_create_decision() -> None:
    store = FakeStructuredStore()
    store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": "ent_carefarm",
                "entity_type": "startup",
                "name": "CareFarm Carbon",
                "normalized_name": "carefarmcarbon",
                "region": "Jeonbuk",
                "industry": "AgriTech",
                "homepage": "https://carefarm.example",
                "first_seen_at": "2026-05-01T00:00:00+00:00",
                "last_seen_at": "2026-05-01T00:00:00+00:00",
            },
            {
                "entity_id": "ent_merry",
                "entity_type": "startup",
                "name": "Merry AI",
                "normalized_name": "merryai",
                "region": "Seoul",
                "industry": "SaaS",
                "homepage": "https://merry.example",
                "first_seen_at": "2026-05-18T00:00:00+00:00",
                "last_seen_at": "2026-05-18T00:00:00+00:00",
            },
        ],
        key_fields=("entity_id",),
    )
    queue = FakeReviewQueue()

    result = resolve_entities(structured_store=store, review_queue=queue, run_id="run_create_test")

    assert result.event_count == 0
    assert store.tables["entity_resolution_events"] == []
    assert queue.published["entity_resolution"] == []
