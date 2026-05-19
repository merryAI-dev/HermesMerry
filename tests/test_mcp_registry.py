from merry_mcp.registry import TOOL_REGISTRY, allowed_tool_names


def test_mcp_registry_exposes_only_domain_tools() -> None:
    assert set(allowed_tool_names()) == {
        "ingest_raw_source",
        "crawl_public_sources",
        "enrich_sminfo_candidates",
        "draft_outreach_emails",
        "sync_kvic_funds",
        "research_investors",
        "upsert_entity_signal",
        "enqueue_candidate_card",
        "record_review_feedback",
        "send_slack_summary",
    }


def test_mcp_registry_does_not_expose_generic_local_access() -> None:
    forbidden_scopes = {"terminal", "filesystem", "code_execution", "computer_use"}

    assert all(tool.side_effect_scope not in forbidden_scopes for tool in TOOL_REGISTRY.values())


def test_crawl_public_sources_tool_accepts_bounded_public_targets() -> None:
    tool = TOOL_REGISTRY["crawl_public_sources"]

    assert tool.side_effect_scope == "public_web_sqlite_wiki"
    assert tool.input_schema["required"] == ["targets"]
    assert tool.input_schema["properties"]["targets"]["type"] == "array"


def test_enrich_sminfo_candidates_tool_is_bounded_to_candidate_names() -> None:
    tool = TOOL_REGISTRY["enrich_sminfo_candidates"]

    assert tool.side_effect_scope == "sminfo_sheets_sqlite"
    assert tool.input_schema["additionalProperties"] is False
    assert tool.input_schema["properties"]["max_items"]["maximum"] == 20
    assert tool.input_schema["properties"]["company_names"]["maxItems"] == 20
    assert "url" not in tool.input_schema["properties"]


def test_draft_outreach_emails_tool_only_creates_bounded_drafts_from_existing_candidates() -> None:
    tool = TOOL_REGISTRY["draft_outreach_emails"]

    assert tool.side_effect_scope == "gmail_drafts_sheets_sqlite"
    assert tool.input_schema["additionalProperties"] is False
    assert tool.input_schema["properties"]["max_items"]["maximum"] == 20
    assert tool.input_schema["properties"]["company_names"]["maxItems"] == 20
    assert "body" not in tool.input_schema["properties"]


def test_sync_kvic_funds_tool_exposes_daily_investor_db_refresh() -> None:
    tool = TOOL_REGISTRY["sync_kvic_funds"]

    assert tool.side_effect_scope == "kvic_sqlite_sheets"
    assert tool.input_schema["required"] == []
    assert tool.input_schema["additionalProperties"] is False
    assert tool.input_schema["properties"]["force"]["type"] == "boolean"


def test_research_investors_tool_is_bounded_to_investor_profiles() -> None:
    tool = TOOL_REGISTRY["research_investors"]

    assert tool.side_effect_scope == "public_web_llm_sqlite_sheets"
    assert tool.input_schema["required"] == []
    assert tool.input_schema["additionalProperties"] is False
    assert tool.input_schema["properties"]["max_items"]["maximum"] == 50
    assert "url" not in tool.input_schema["properties"]
