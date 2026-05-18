from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass
from typing import Any

from merry_runtime.adapters.interfaces import Notifier, ObjectStore, ReviewQueue, StructuredStore
from merry_runtime.pipelines.ingest_sources import ingest_sources
from merry_runtime.pipelines.resolve_entities import resolve_entities
from merry_runtime.pipelines.score_candidates import score_candidates
from merry_runtime.pipelines.sync_review_sheet import sync_review_sheet
from merry_runtime.runtime_config import RuntimeConfig
from merry_runtime.wiki_store import SQLiteWikiStore


class JobRunError(ValueError):
    pass


@dataclass(slots=True)
class RuntimeAdapters:
    object_store: ObjectStore
    structured_store: StructuredStore
    review_queue: ReviewQueue
    notifier: Notifier | None = None
    wiki_store: SQLiteWikiStore | None = None
    gmail_source: Any | None = None


def run_job(
    job_name: str,
    *,
    runtime: RuntimeAdapters,
    config: RuntimeConfig,
    sources_json: str = "",
    ac_id: str = "",
) -> dict[str, object]:
    if job_name == "ingest-sources":
        sources = _sources_from_json(sources_json) if sources_json else _sources_from_gmail(runtime)
        if not sources:
            raise JobRunError("ingest-sources requires --sources-json or a configured Gmail source with messages")
        result = ingest_sources(
            sources=sources,
            object_store=runtime.object_store,
            structured_store=runtime.structured_store,
            wiki_store=runtime.wiki_store,
        )
        return {"job_name": job_name, **asdict(result)}

    if job_name == "score-candidates":
        selected_ac_id = ac_id or config.default_ac_id
        if not selected_ac_id:
            raise JobRunError("score-candidates requires ac_id or AC_ID")
        result = score_candidates(structured_store=runtime.structured_store, review_queue=runtime.review_queue, ac_id=selected_ac_id)
        return {"job_name": job_name, **asdict(result)}

    if job_name == "sync-review-sheet":
        selected_ac_id = ac_id or config.default_ac_id
        if not selected_ac_id:
            raise JobRunError("sync-review-sheet requires ac_id or AC_ID")
        result = sync_review_sheet(structured_store=runtime.structured_store, review_queue=runtime.review_queue, ac_id=selected_ac_id)
        return {"job_name": job_name, **asdict(result)}

    if job_name == "weekly-summary":
        return _run_weekly_summary(runtime=runtime, config=config)

    if job_name == "resolve-entities":
        return _run_resolve_entities(runtime=runtime)

    raise JobRunError(f"Unknown job: {job_name}")


def _sources_from_json(value: str) -> list[dict[str, Any]]:
    payload = json.loads(value)
    if not isinstance(payload, list):
        raise JobRunError("sources JSON must be a list")
    return payload


def _sources_from_gmail(runtime: RuntimeAdapters) -> list[dict[str, Any]]:
    if not runtime.gmail_source:
        return []
    messages = runtime.gmail_source.fetch_labeled_messages()
    return [{"channel": "info_mail", "payload": _gmail_message_to_text(message)} for message in messages]


def _gmail_message_to_text(message: dict[str, Any]) -> str:
    if message.get("snippet"):
        return str(message["snippet"])
    payload = message.get("payload", {})
    text = _decode_body(payload.get("body", {}).get("data", ""))
    if text:
        return text
    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain":
            text = _decode_body(part.get("body", {}).get("data", ""))
            if text:
                return text
    return json.dumps(message, ensure_ascii=False, sort_keys=True)


def _decode_body(value: str) -> str:
    if not value:
        return ""
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")


def _run_weekly_summary(*, runtime: RuntimeAdapters, config: RuntimeConfig) -> dict[str, object]:
    if not runtime.notifier:
        raise JobRunError("weekly-summary requires notifier")
    if not config.slack_channel:
        raise JobRunError("weekly-summary requires SLACK_CHANNEL")
    cards = runtime.structured_store.query_rows(sql="select * from candidate_cards", parameters={})
    counts = _count_by_queue(cards)
    text = "Hermes weekly summary: " + ", ".join(f"{queue}={count}" for queue, count in sorted(counts.items()))
    message_id = runtime.notifier.send_message(channel=config.slack_channel, text=text)
    return {"job_name": "weekly-summary", "message_id": message_id, "card_count": len(cards), "counts": counts}


def _run_resolve_entities(*, runtime: RuntimeAdapters) -> dict[str, object]:
    result = resolve_entities(structured_store=runtime.structured_store, review_queue=runtime.review_queue)
    return {"job_name": "resolve-entities", **asdict(result)}


def _count_by_queue(cards: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for card in cards:
        queue = str(card.get("queue_type") or "priority")
        counts[queue] = counts.get(queue, 0) + 1
    return counts
