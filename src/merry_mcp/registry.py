from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class MCPToolContract:
    name: str
    description: str
    side_effect_scope: str
    input_schema: dict[str, Any]


_TOOLS = {
    "ingest_raw_source": MCPToolContract(
        name="ingest_raw_source",
        description="Store a raw source payload and register metadata in the Mother DB.",
        side_effect_scope="raw_store_structured_store",
        input_schema={
            "type": "object",
            "required": ["source_type", "channel", "uri", "raw_text"],
            "additionalProperties": False,
            "properties": {
                "source_type": {"type": "string"},
                "channel": {"type": "string"},
                "uri": {"type": "string"},
                "title": {"type": "string"},
                "raw_text": {"type": "string", "maxLength": 20000},
            },
        },
    ),
    "crawl_public_sources": MCPToolContract(
        name="crawl_public_sources",
        description="Crawl explicitly configured public source targets and ingest discovered startup signals.",
        side_effect_scope="public_web_sqlite_wiki",
        input_schema={
            "type": "object",
            "required": ["targets"],
            "additionalProperties": False,
            "properties": {
                "targets": {"type": "array", "items": {"type": "object"}, "maxItems": 20},
                "reason": {"type": "string", "maxLength": 1000},
            },
        },
    ),
    "enrich_sminfo_candidates": MCPToolContract(
        name="enrich_sminfo_candidates",
        description="Enrich bounded Candidate Detail companies from the SMINFO government company profile site.",
        side_effect_scope="sminfo_sheets_sqlite",
        input_schema={
            "type": "object",
            "required": [],
            "additionalProperties": False,
            "properties": {
                "max_items": {"type": "integer", "minimum": 1, "maximum": 20},
                "company_names": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
                "reason": {"type": "string", "maxLength": 1000},
            },
        },
    ),
    "draft_outreach_emails": MCPToolContract(
        name="draft_outreach_emails",
        description="Create bounded Gmail drafts from existing Candidate Detail contact emails without sending them.",
        side_effect_scope="gmail_drafts_sheets_sqlite",
        input_schema={
            "type": "object",
            "required": [],
            "additionalProperties": False,
            "properties": {
                "max_items": {"type": "integer", "minimum": 1, "maximum": 20},
                "company_names": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
                "reason": {"type": "string", "maxLength": 1000},
            },
        },
    ),
    "sync_kvic_funds": MCPToolContract(
        name="sync_kvic_funds",
        description="Refresh the KVIC public investor/fund snapshot into SQLite and the Investor DB Sheet tab.",
        side_effect_scope="kvic_sqlite_sheets",
        input_schema={
            "type": "object",
            "required": [],
            "additionalProperties": False,
            "properties": {
                "force": {"type": "boolean"},
                "reason": {"type": "string", "maxLength": 1000},
            },
        },
    ),
    "research_investors": MCPToolContract(
        name="research_investors",
        description="Research bounded investor AUM/profile evidence with public search and an LLM encoder, then update SQLite and Investor DB.",
        side_effect_scope="public_web_llm_sqlite_sheets",
        input_schema={
            "type": "object",
            "required": [],
            "additionalProperties": False,
            "properties": {
                "max_items": {"type": "integer", "minimum": 1, "maximum": 50},
                "reason": {"type": "string", "maxLength": 1000},
            },
        },
    ),
    "upsert_entity_signal": MCPToolContract(
        name="upsert_entity_signal",
        description="Create or merge a Mother DB entity and attach evidence-backed signals.",
        side_effect_scope="structured_store",
        input_schema={
            "type": "object",
            "required": ["entity", "signals"],
            "additionalProperties": False,
            "properties": {
                "entity": {"type": "object"},
                "signals": {"type": "array", "items": {"type": "object"}},
            },
        },
    ),
    "enqueue_candidate_card": MCPToolContract(
        name="enqueue_candidate_card",
        description="Write an AC candidate card to the Mother DB and the review Sheet queue.",
        side_effect_scope="structured_store_sheets",
        input_schema={
            "type": "object",
            "required": ["ac_id", "entity_id", "summary", "recommended_action"],
            "additionalProperties": False,
            "properties": {
                "ac_id": {"type": "string"},
                "entity_id": {"type": "string"},
                "summary": {"type": "string", "maxLength": 3000},
                "recommended_action": {"type": "string"},
            },
        },
    ),
    "record_review_feedback": MCPToolContract(
        name="record_review_feedback",
        description="Persist human Sheet review decisions and update card status.",
        side_effect_scope="structured_store",
        input_schema={
            "type": "object",
            "required": ["card_id", "reviewer", "decision"],
            "additionalProperties": False,
            "properties": {
                "card_id": {"type": "string"},
                "reviewer": {"type": "string"},
                "decision": {
                    "type": "string",
                    "enum": ["advance", "watchlist", "reject", "request_more_info"],
                },
                "review_memo": {"type": "string", "maxLength": 3000},
            },
        },
    ),
    "send_slack_summary": MCPToolContract(
        name="send_slack_summary",
        description="Send a bounded summary of new cards and weekly review deltas to Slack.",
        side_effect_scope="slack",
        input_schema={
            "type": "object",
            "required": ["summary"],
            "additionalProperties": False,
            "properties": {
                "summary": {"type": "string", "maxLength": 3000},
            },
        },
    ),
}


TOOL_REGISTRY = MappingProxyType(_TOOLS)


def allowed_tool_names() -> tuple[str, ...]:
    return tuple(TOOL_REGISTRY.keys())
