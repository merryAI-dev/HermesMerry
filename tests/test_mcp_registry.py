from merry_mcp.registry import TOOL_REGISTRY, allowed_tool_names


def test_mcp_registry_exposes_only_domain_tools() -> None:
    assert set(allowed_tool_names()) == {
        "ingest_raw_source",
        "crawl_public_sources",
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
