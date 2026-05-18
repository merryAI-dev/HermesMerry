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


def test_mcp_server_calls_registered_handler() -> None:
    seen_payloads = []
    server = MerryMCPServer(handlers={"record_review_feedback": lambda payload: seen_payloads.append(payload) or {"ok": True}})

    result = server.call_tool(
        "record_review_feedback",
        {"card_id": "card_1", "reviewer": "boram", "decision": "advance"},
    )

    assert result == {"ok": True}
    assert seen_payloads == [{"card_id": "card_1", "reviewer": "boram", "decision": "advance"}]


def test_mcp_server_redacts_pii_before_slack_summary_handler() -> None:
    seen_payloads = []
    server = MerryMCPServer(handlers={"send_slack_summary": lambda payload: seen_payloads.append(payload) or {"ok": True}})

    server.call_tool("send_slack_summary", {"channel": "C123", "summary": "Contact min@example.com / 010-1234-5678"})

    assert seen_payloads[0]["summary"] == "Contact [REDACTED_EMAIL] / [REDACTED_PHONE]"
