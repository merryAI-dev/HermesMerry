from merry_runtime.schema import BIGQUERY_TABLES, table_field_names


def test_bigquery_schema_contains_required_mother_tables() -> None:
    assert {
        "raw_sources",
        "mother_entities",
        "entity_aliases",
        "signals",
        "ac_profiles",
        "ac_scores",
        "candidate_cards",
        "reviews",
        "ac_scoring_coefficients",
        "agent_runs",
    }.issubset(BIGQUERY_TABLES.keys())


def test_entity_resolution_events_schema_captures_probabilistic_decisions() -> None:
    fields = {field["name"] for field in BIGQUERY_TABLES["entity_resolution_events"]}

    assert {
        "event_id",
        "candidate_entity_id",
        "matched_entity_id",
        "action",
        "probability",
        "features_json",
        "rationale",
        "status",
        "created_at",
    }.issubset(fields)


def test_mother_entity_schema_matches_development_plan_fields() -> None:
    fields = table_field_names("mother_entities")

    assert {
        "entity_id",
        "entity_type",
        "name",
        "normalized_name",
        "region",
        "industry",
        "homepage",
        "first_seen_at",
        "last_seen_at",
    }.issubset(fields)


def test_ac_score_schema_preserves_score_components_and_rationale() -> None:
    fields = table_field_names("ac_scores")

    assert {
        "score_id",
        "ac_id",
        "entity_id",
        "base_score",
        "fund_fit_score",
        "recruiting_fit_score",
        "hypothesis_fit_score",
        "impact_fit_score",
        "total_score",
        "priority_probability",
        "priority_utility",
        "queue_type",
        "uncertainty",
        "model_version",
        "rationale",
    }.issubset(fields)


def test_ac_scoring_coefficients_schema_covers_priority_model_fields() -> None:
    fields = table_field_names("ac_scoring_coefficients")

    assert {
        "ac_id",
        "beta0",
        "fund_fit",
        "recruitment_fit",
        "impact_fit",
        "channel_trust",
        "multi_channel_signal",
        "prior_decision",
        "freshness",
        "risk",
        "sample_count",
        "model_version",
        "updated_at",
    }.issubset(fields)
