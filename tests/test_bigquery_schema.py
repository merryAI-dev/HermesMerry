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
        "outreach_email_drafts",
        "kvic_fund_types",
        "kvic_funds",
        "kvic_fund_descriptions",
        "kvic_investor_managers",
        "investor_external_profiles",
        "kvic_sync_state",
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


def test_outreach_email_drafts_schema_captures_gmail_draft_state() -> None:
    fields = table_field_names("outreach_email_drafts")

    assert {
        "outreach_id",
        "company",
        "contact_email",
        "subject",
        "body_text",
        "gmail_draft_id",
        "status",
        "source_url",
        "drafted_at",
        "error_message",
    }.issubset(fields)


def test_kvic_schema_captures_investor_fund_mother_db() -> None:
    fund_fields = table_field_names("kvic_funds")
    manager_fields = table_field_names("kvic_investor_managers")
    description_fields = table_field_names("kvic_fund_descriptions")
    state_fields = table_field_names("kvic_sync_state")

    assert {
        "fund_id",
        "fund_type_code",
        "fund_year",
        "field_name",
        "manager_name",
        "association_name",
        "expires_at",
        "amount_raw",
        "commitment_raw",
        "amount_eok",
        "commitment_eok",
        "is_active",
        "raw_json",
        "collected_at",
    }.issubset(fund_fields)
    assert {
        "manager_id",
        "manager_name",
        "total_fund_count",
        "active_fund_count",
        "active_amount_eok",
        "fund_fields",
        "representative_funds",
        "profile_tags",
        "next_expiry_at",
    }.issubset(manager_fields)
    assert {
        "fund_id",
        "description",
        "source_title",
        "source_url",
        "source_snippet",
        "search_query",
        "status",
        "error_message",
        "collected_at",
        "updated_at",
    }.issubset(description_fields)
    assert {"state_key", "latest_success_at", "status", "fund_count", "manager_count", "updated_at"}.issubset(state_fields)
