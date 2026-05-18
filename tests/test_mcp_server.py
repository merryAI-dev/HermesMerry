import pytest

from merry_mcp.registry import allowed_tool_names
from merry_mcp.server import MCPPayloadError, MerryMCPServer, UnknownMCPToolError


def test_mcp_server_exposes_exactly_registry_tools() -> None:
    server = MerryMCPServer(handlers={})

    assert server.list_tools() == allowed_tool_names()


def test_mcp_server_rejects_unknown_tool() -> None:
    server = MerryMCPServer(handlers={})

    with pytest.raises(UnknownMCPToolError):
        server.call_tool("terminal", {})


def test_mcp_server_validates_required_payload_fields() -> None:
    server = MerryMCPServer(handlers={"enqueue_candidate_card": lambda payload: {"ok": True}})

    with pytest.raises(MCPPayloadError):
        server.call_tool("enqueue_candidate_card", {"ac_id": "ac_1"})


def test_mcp_server_enforces_schema_types_enums_lengths_and_extra_fields() -> None:
    server = MerryMCPServer(handlers={"record_review_feedback": lambda payload: {"ok": True}})

    with pytest.raises(MCPPayloadError, match="additional"):
        server.call_tool(
            "record_review_feedback",
            {"card_id": "card_1", "reviewer": "boram", "decision": "advance", "shell": "rm -rf /"},
        )
    with pytest.raises(MCPPayloadError, match="must be string"):
        server.call_tool("record_review_feedback", {"card_id": "card_1", "reviewer": ["boram"], "decision": "advance"})
    with pytest.raises(MCPPayloadError, match="not allowed"):
        server.call_tool("record_review_feedback", {"card_id": "card_1", "reviewer": "boram", "decision": "maybe"})

    slack_server = MerryMCPServer(handlers={"send_slack_summary": lambda payload: {"ok": True}}, slack_channel="C123")
    with pytest.raises(MCPPayloadError, match="too long"):
        slack_server.call_tool("send_slack_summary", {"summary": "x" * 3001})


def test_mcp_server_calls_registered_handler() -> None:
    seen_payloads = []
    server = MerryMCPServer(handlers={"record_review_feedback": lambda payload: seen_payloads.append(payload) or {"ok": True}})

    result = server.call_tool(
        "record_review_feedback",
        {"card_id": "card_1", "reviewer": "boram", "decision": "advance"},
    )

    assert result == {"ok": True}
    assert seen_payloads == [{"card_id": "card_1", "reviewer": "boram", "decision": "advance"}]


def test_mcp_server_allows_crawl_public_sources_handler() -> None:
    seen_payloads = []
    server = MerryMCPServer(handlers={"crawl_public_sources": lambda payload: seen_payloads.append(payload) or {"crawled_source_count": 5}})

    result = server.call_tool(
        "crawl_public_sources",
        {
            "targets": [{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma", "max_cards": 5}],
            "reason": "hourly discovery loop",
        },
    )

    assert result == {"crawled_source_count": 5}
    assert seen_payloads[0]["targets"][0]["url"] == "https://thevc.kr/"


def test_mcp_server_redacts_pii_before_slack_summary_handler() -> None:
    seen_payloads = []
    server = MerryMCPServer(handlers={"send_slack_summary": lambda payload: seen_payloads.append(payload) or {"ok": True}}, slack_channel="C123")

    server.call_tool("send_slack_summary", {"summary": "Contact min@example.com / 010-1234-5678"})

    assert seen_payloads[0]["channel"] == "C123"
    assert seen_payloads[0]["summary"] == "Contact [REDACTED_EMAIL] / [REDACTED_PHONE]"


def test_mcp_server_rejects_agent_supplied_slack_channel() -> None:
    server = MerryMCPServer(handlers={"send_slack_summary": lambda payload: {"ok": True}}, slack_channel="C123")

    with pytest.raises(MCPPayloadError, match="additional"):
        server.call_tool("send_slack_summary", {"channel": "C999", "summary": "Weekly update"})
