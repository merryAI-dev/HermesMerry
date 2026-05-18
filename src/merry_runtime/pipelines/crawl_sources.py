from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

from merry_runtime.adapters.interfaces import ObjectStore, ReviewQueue, StructuredStore
from merry_runtime.ingestion.thevc import THEVC_INVESTMENT_CHANNEL, extract_thevc_investment_sources
from merry_runtime.ingestion.parsers import ParsedSource, parse_thevc_investment_card
from merry_runtime.ingestion.web_crawler import fetch_url as fetch_url_text
from merry_runtime.pipelines.ingest_sources import ingest_sources
from merry_runtime.wiki_store import SQLiteWikiStore


@dataclass(frozen=True, slots=True)
class CrawlResult:
    run_id: str
    target_count: int
    crawled_source_count: int
    ingested_raw_source_count: int
    ingested_entity_count: int
    ingested_signal_count: int


def crawl_sources(
    *,
    targets: list[dict[str, Any]],
    object_store: ObjectStore,
    structured_store: StructuredStore,
    review_queue: ReviewQueue | None = None,
    wiki_store: SQLiteWikiStore | None = None,
    fetch_url: Callable[[str], str] = fetch_url_text,
    run_id: str | None = None,
) -> CrawlResult:
    started_at = _now()
    run_id = run_id or _stable_run_id(targets)
    active_targets = [_normalize_target(target) for target in targets if _is_active_target(target)]

    sources: list[dict[str, str]] = []
    for target in active_targets:
        html = fetch_url(target["url"])
        if target["source_kind"] == THEVC_INVESTMENT_CHANNEL:
            sources.extend(
                extract_thevc_investment_sources(
                    html,
                    source_url=target["url"],
                    max_cards=int(target.get("max_cards") or 20),
                )
            )
            continue
        raise ValueError(f"Unsupported crawl source_kind: {target['source_kind']}")

    ingest_result = None
    if sources:
        ingest_result = ingest_sources(
            sources=sources,
            object_store=object_store,
            structured_store=structured_store,
            wiki_store=wiki_store,
            run_id=f"{run_id}_ingest",
        )
        if review_queue is not None:
            _publish_sheet_projection(review_queue=review_queue, sources=sources)

    result = CrawlResult(
        run_id=run_id,
        target_count=len(active_targets),
        crawled_source_count=len(sources),
        ingested_raw_source_count=ingest_result.raw_source_count if ingest_result else 0,
        ingested_entity_count=ingest_result.entity_count if ingest_result else 0,
        ingested_signal_count=ingest_result.signal_count if ingest_result else 0,
    )
    structured_store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": run_id,
                "job_name": "crawl-sources",
                "status": "success",
                "started_at": started_at,
                "finished_at": _now(),
                "input_count": len(active_targets),
                "output_count": len(sources),
                "error_message": "",
            }
        ],
        key_fields=("run_id",),
    )
    return result


def _normalize_target(target: dict[str, Any]) -> dict[str, Any]:
    url = str(target.get("url") or "").strip()
    if not url:
        raise ValueError("crawl target requires url")
    source_kind = str(target.get("source_kind") or target.get("channel") or THEVC_INVESTMENT_CHANNEL).strip()
    return {**target, "url": url, "source_kind": source_kind}


def _is_active_target(target: dict[str, Any]) -> bool:
    status = str(target.get("status") or "").strip().casefold()
    return status not in {"done", "disabled", "skip", "skipped", "inactive"}


def _publish_sheet_projection(*, review_queue: ReviewQueue, sources: list[dict[str, str]]) -> None:
    parsed_sources = [_parse_projection_source(source) for source in sources]
    review_queue.publish_cards(sheet_tab="Evidence", rows=[_evidence_row(parsed) for parsed in parsed_sources])
    review_queue.publish_cards(sheet_tab="Candidate Detail", rows=[_candidate_detail_row(parsed) for parsed in parsed_sources])


def _parse_projection_source(source: dict[str, str]) -> ParsedSource:
    if source.get("channel") == THEVC_INVESTMENT_CHANNEL:
        return parse_thevc_investment_card(str(source.get("payload") or ""))
    raise ValueError(f"Unsupported sheet projection channel: {source.get('channel')}")


def _evidence_row(parsed: ParsedSource) -> dict[str, object]:
    signal = parsed.signals[0]
    return {
        "source_id": parsed.raw_source.source_id,
        "signal_id": signal.signal_id,
        "entity_id": parsed.entity.entity_id,
        "source_type": parsed.raw_source.source_type,
        "channel": parsed.raw_source.channel,
        "title": parsed.raw_source.title,
        "url": parsed.raw_source.uri,
        "signal_type": signal.signal_type,
        "evidence_text": signal.evidence_text,
        "confidence": signal.confidence,
        "tags": ", ".join(signal.tags),
        "contains_pii": parsed.raw_source.contains_pii,
        "raw_text_path": parsed.raw_source.raw_text_path,
    }


def _candidate_detail_row(parsed: ParsedSource) -> dict[str, object]:
    signal = parsed.signals[0]
    return {
        "entity_id": parsed.entity.entity_id,
        "company": parsed.entity.name,
        "normalized_name": parsed.entity.normalized_name or "",
        "representative": parsed.entity.representative,
        "homepage": parsed.entity.homepage or "",
        "region": parsed.entity.region,
        "industry": parsed.entity.industry,
        "summary": signal.evidence_text,
        "latest_score": "",
        "priority_probability": "",
        "queue_type": "new_source",
        "recommended_action": "score_candidates",
        "status": "crawled",
        "wiki_path": f"wiki/entities/{parsed.entity.name}.md",
    }


def _stable_run_id(targets: list[dict[str, Any]]) -> str:
    payload = json.dumps(targets, ensure_ascii=False, sort_keys=True)
    return f"run_crawl_{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:12]}"


def _now() -> str:
    return datetime.now(UTC).isoformat()
