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
        "sminfo_company_profiles",
        "sminfo_enrichment_queue",
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
        "contact_email",
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
        "corpus_hash",
        "updated_at",
    }.issubset(fields)


def test_sminfo_company_profiles_schema_captures_government_enrichment() -> None:
    fields = table_field_names("sminfo_company_profiles")

    assert {
        "profile_id",
        "requested_company",
        "match_status",
        "matched_company",
        "representative",
        "company_type",
        "established_at",
        "road_address",
        "homepage",
        "main_products",
        "standard_industry",
        "info_updated_at",
        "latest_financial_year",
        "revenue_krw_thousand",
        "operating_income_krw_thousand",
        "net_income_krw_thousand",
        "total_assets_krw_thousand",
        "shareholder_composition",
        "largest_shareholder",
        "largest_shareholder_ratio_pct",
        "shareholder_count",
        "sminfo_url",
        "raw_json",
        "error_message",
        "collected_at",
    }.issubset(fields)


def test_sminfo_enrichment_queue_schema_captures_agent_work_state() -> None:
    fields = table_field_names("sminfo_enrichment_queue")

    assert {
        "task_id",
        "company",
        "normalized_name",
        "representative",
        "homepage",
        "source_url",
        "source_channel",
        "status",
        "priority",
        "attempt_count",
        "max_attempts",
        "next_run_at",
        "locked_at",
        "locked_by",
        "last_error",
        "last_profile_id",
        "created_at",
        "updated_at",
        "completed_at",
    }.issubset(fields)
