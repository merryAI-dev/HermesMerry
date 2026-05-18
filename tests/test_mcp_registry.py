from merry_mcp.registry import TOOL_REGISTRY, allowed_tool_names


def test_mcp_registry_exposes_only_domain_tools() -> None:
    assert set(allowed_tool_names()) == {
        "ingest_raw_source",
        "upsert_entity_signal",
        "enqueue_candidate_card",
        "record_review_feedback",
        "send_slack_summary",
    }


def test_mcp_registry_does_not_expose_generic_local_access() -> None:
    forbidden_scopes = {"terminal", "filesystem", "code_execution", "computer_use"}

    assert all(tool.side_effect_scope not in forbidden_scopes for tool in TOOL_REGISTRY.values())
