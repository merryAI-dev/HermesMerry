from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

from merry_runtime.adapters.interfaces import ObjectStore, StructuredStore
from merry_runtime.ingestion.thevc import THEVC_INVESTMENT_CHANNEL, extract_thevc_investment_sources
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


def _stable_run_id(targets: list[dict[str, Any]]) -> str:
    payload = json.dumps(targets, ensure_ascii=False, sort_keys=True)
    return f"run_crawl_{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:12]}"


def _now() -> str:
    return datetime.now(UTC).isoformat()
