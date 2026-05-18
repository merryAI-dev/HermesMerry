from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from merry_runtime.adapters.interfaces import StructuredStore

_QUEUE_TYPES = frozenset({"priority", "exploration", "watchlist", "archive"})
_REVIEW_DECISIONS = frozenset({"advance", "watchlist", "reject", "request_more_info"})


@dataclass(frozen=True, slots=True)
class WeeklySummaryResult:
    text: str
    card_count: int
    counts: dict[str, int]


def build_weekly_summary(*, structured_store: StructuredStore, max_length: int = 500) -> WeeklySummaryResult:
    cards = structured_store.query_rows(sql="select * from candidate_cards", parameters={})
    reviews = structured_store.query_rows(sql="select * from reviews", parameters={})
    agent_runs = structured_store.query_rows(sql="select * from agent_runs", parameters={})
    resolution_events = structured_store.query_rows(sql="select * from entity_resolution_events", parameters={})

    counts: dict[str, int] = {
        **_count_by_field(cards, "queue_type", default="priority", allowed_values=_QUEUE_TYPES),
        "failed_jobs": sum(1 for row in agent_runs if row.get("status") == "failed"),
        "reviews": len(reviews),
        "resolution_pending": sum(1 for row in resolution_events if row.get("status") == "pending_review"),
    }
    for decision, count in _count_by_field(
        reviews,
        "decision",
        prefix="review",
        default="unknown",
        allowed_values=_REVIEW_DECISIONS,
    ).items():
        counts[decision] = count

    ordered_keys = [key for key in ("failed_jobs", "reviews", "resolution_pending") if key in counts]
    ordered_keys.extend(sorted(key for key in counts if key not in set(ordered_keys)))
    text = "Hermes weekly summary: " + ", ".join(f"{key}={counts[key]}" for key in ordered_keys)
    if len(text) > max_length:
        text = text[: max_length - 3].rstrip(" ,") + "..."
    return WeeklySummaryResult(text=text, card_count=len(cards), counts=counts)


def _count_by_field(
    rows: list[dict[str, Any]],
    field: str,
    *,
    default: str,
    prefix: str = "",
    allowed_values: frozenset[str] | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = _safe_token(row.get(field) or default)
        if allowed_values is not None and value not in allowed_values:
            value = "unknown"
        key = f"{prefix}_{value}" if prefix else value
        counts[key] = counts.get(key, 0) + 1
    return counts


def _safe_token(value: object) -> str:
    token = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
    return "".join(character for character in token if character.isalnum() or character == "_") or "unknown"
