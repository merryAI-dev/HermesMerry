from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from merry_runtime.adapters.interfaces import Notifier, ObjectStore, ReviewQueue, StructuredStore
from merry_runtime.clock import now_kst, now_kst_datetime
from merry_runtime.ingestion.sminfo_queue import build_sminfo_task, is_terminal_queue_status, sminfo_queue_sheet_row
from merry_runtime.ingestion.platum import PLATUM_INVESTMENT_CHANNEL, extract_platum_portfolio_news_sources
from merry_runtime.ingestion.thevc import THEVC_INVESTMENT_CHANNEL, extract_thevc_investment_sources
from merry_runtime.ingestion.parsers import ParsedSource, parse_platum_portfolio_news, parse_thevc_investment_card
from merry_runtime.portfolio_watchlist import PortfolioKeyword, build_portfolio_watchlist, load_portfolio_watchlist
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
    notified_count: int = 0
    enqueued_sminfo_task_count: int = 0


def crawl_sources(
    *,
    targets: list[dict[str, Any]],
    object_store: ObjectStore,
    structured_store: StructuredStore,
    review_queue: ReviewQueue | None = None,
    notifier: Notifier | None = None,
    slack_channel: str = "",
    wiki_store: SQLiteWikiStore | None = None,
    fetch_url: Callable[[str], str] = fetch_url_text,
    sminfo_stale_days: int = 30,
    run_id: str | None = None,
) -> CrawlResult:
    started_at = _now()
    run_id = run_id or _stable_run_id(targets)
    active_targets = [_normalize_target(target) for target in targets if _is_active_target(target)]

    sources: list[dict[str, str]] = []
    portfolio_news_sources: list[dict[str, str]] = []
    for target in active_targets:
        html = fetch_url(target["url"])
        if target["source_kind"] == THEVC_INVESTMENT_CHANNEL:
            sources.extend(
                extract_thevc_investment_sources(
                    html,
                    source_url=target["url"],
                    max_cards=int(target.get("max_cards") or 20),
                    fetch_detail_url=fetch_url if _truthy(target.get("detail_enrichment"), default=True) else None,
                )
            )
            continue
        if target["source_kind"] == PLATUM_INVESTMENT_CHANNEL:
            extracted_sources = extract_platum_portfolio_news_sources(
                html,
                source_url=target["url"],
                watchlist=_watchlist_for_target(target),
                max_articles=int(target.get("max_articles") or target.get("max_cards") or 20),
            )
            new_sources = [
                source
                for source in extracted_sources
                if not _is_existing_platum_news_source(source=source, structured_store=structured_store)
            ]
            sources.extend(new_sources)
            portfolio_news_sources.extend(new_sources)
            continue
        raise ValueError(f"Unsupported crawl source_kind: {target['source_kind']}")

    ingest_result = None
    notified_count = 0
    enqueued_sminfo_tasks: list[dict[str, object]] = []
    if sources:
        ingest_result = ingest_sources(
            sources=sources,
            object_store=object_store,
            structured_store=structured_store,
            wiki_store=wiki_store,
            run_id=f"{run_id}_ingest",
        )
        if review_queue is not None:
            _publish_sheet_projection(review_queue=review_queue, sources=sources, collected_at=started_at)
        enqueued_sminfo_tasks = _enqueue_sminfo_tasks(
            structured_store=structured_store,
            sources=sources,
            collected_at=started_at,
            stale_days=sminfo_stale_days,
        )
        if review_queue is not None and enqueued_sminfo_tasks:
            _publish_sminfo_queue_projection(review_queue=review_queue, tasks=enqueued_sminfo_tasks)
        if portfolio_news_sources and notifier is not None and slack_channel:
            notified_count = _notify_portfolio_news(
                notifier=notifier,
                slack_channel=slack_channel,
                sources=portfolio_news_sources,
            )

    result = CrawlResult(
        run_id=run_id,
        target_count=len(active_targets),
        crawled_source_count=len(sources),
        ingested_raw_source_count=ingest_result.raw_source_count if ingest_result else 0,
        ingested_entity_count=ingest_result.entity_count if ingest_result else 0,
        ingested_signal_count=ingest_result.signal_count if ingest_result else 0,
        notified_count=notified_count,
        enqueued_sminfo_task_count=len(enqueued_sminfo_tasks),
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
    source_kind = _canonical_source_kind(str(target.get("source_kind") or target.get("channel") or THEVC_INVESTMENT_CHANNEL).strip())
    return {**target, "url": url, "source_kind": source_kind}


def _canonical_source_kind(source_kind: str) -> str:
    aliases = {
        "platum_investment": PLATUM_INVESTMENT_CHANNEL,
        "platum": PLATUM_INVESTMENT_CHANNEL,
        "thevc": THEVC_INVESTMENT_CHANNEL,
    }
    return aliases.get(source_kind.casefold(), source_kind)


def _is_active_target(target: dict[str, Any]) -> bool:
    status = str(target.get("status") or "").strip().casefold()
    return status not in {"done", "disabled", "skip", "skipped", "inactive"}


def _truthy(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().casefold() not in {"0", "false", "no", "n", "off", "disabled"}


def _publish_sheet_projection(*, review_queue: ReviewQueue, sources: list[dict[str, str]], collected_at: str) -> None:
    parsed_sources = [_parse_projection_source(source) for source in sources]
    review_queue.upsert_cards(
        sheet_tab="Evidence",
        rows=[_evidence_row(parsed) for parsed in parsed_sources],
        key_fields=("source_id", "url"),
    )
    portfolio_news_sources = [parsed for parsed in parsed_sources if parsed.raw_source.channel == PLATUM_INVESTMENT_CHANNEL]
    if portfolio_news_sources:
        review_queue.upsert_cards(
            sheet_tab="Portfolio News",
            rows=[_portfolio_news_row(parsed, collected_at=collected_at) for parsed in portfolio_news_sources],
            key_fields=("url", "company"),
        )
    candidate_detail_sources = [parsed for parsed in parsed_sources if parsed.raw_source.channel == THEVC_INVESTMENT_CHANNEL]
    if not candidate_detail_sources:
        return
    review_queue.upsert_cards(
        sheet_tab="Candidate Detail",
        rows=[_candidate_detail_row(parsed, collected_at=collected_at) for parsed in candidate_detail_sources],
        key_fields=("company", "homepage"),
    )


def _enqueue_sminfo_tasks(
    *,
    structured_store: StructuredStore,
    sources: list[dict[str, str]],
    collected_at: str,
    stale_days: int,
) -> list[dict[str, object]]:
    parsed_sources = [
        _parse_projection_source(source)
        for source in sources
        if source.get("channel") == THEVC_INVESTMENT_CHANNEL
    ]
    if not parsed_sources:
        return []
    existing_tasks = {
        str(row.get("task_id") or ""): row
        for row in structured_store.query_rows(
            sql="SELECT * FROM sminfo_enrichment_queue",
            parameters={},
        )
    }
    reference_time = _parse_timestamp(collected_at) or now_kst_datetime()
    tasks: list[dict[str, object]] = []
    for parsed in parsed_sources:
        candidate = _sminfo_task_candidate(parsed=parsed, collected_at=collected_at)
        task = build_sminfo_task(
            candidate,
            source_channel=THEVC_INVESTMENT_CHANNEL,
            now=collected_at,
        )
        existing = _matching_existing_sminfo_task(existing_tasks=existing_tasks, task=task)
        if existing:
            task["task_id"] = existing.get("task_id") or task["task_id"]
        if existing and _has_fresh_terminal_queue_status(existing, stale_days=stale_days, reference_time=reference_time):
            continue
        if existing and str(existing.get("status") or "") in {"retry", "running", "failed"}:
            continue
        if existing:
            task["created_at"] = existing.get("created_at") or task["created_at"]
        tasks.append(task)
    if not tasks:
        return []
    structured_store.upsert_rows(
        table="sminfo_enrichment_queue",
        rows=tasks,
        key_fields=("task_id",),
    )
    return tasks


def _matching_existing_sminfo_task(
    *,
    existing_tasks: dict[str, dict[str, Any]],
    task: dict[str, object],
) -> dict[str, Any] | None:
    direct = existing_tasks.get(str(task.get("task_id") or ""))
    if direct:
        return direct
    normalized_name = str(task.get("normalized_name") or task.get("company") or "")
    source_channel = str(task.get("source_channel") or "")
    for existing in existing_tasks.values():
        existing_name = str(existing.get("normalized_name") or existing.get("company") or "")
        if existing_name == normalized_name and str(existing.get("source_channel") or "") == source_channel:
            return existing
    return None


def _publish_sminfo_queue_projection(*, review_queue: ReviewQueue, tasks: list[dict[str, object]]) -> None:
    review_queue.upsert_cards(
        sheet_tab="SMINFO Queue",
        rows=[sminfo_queue_sheet_row(task) for task in tasks],
        key_fields=("task_id",),
    )


def _sminfo_task_candidate(*, parsed: ParsedSource, collected_at: str) -> dict[str, object]:
    candidate = _candidate_detail_row(parsed, collected_at=collected_at)
    fields = _payload_fields(parsed.raw_text)
    return {
        **candidate,
        "source_url": fields.get("source uri") or parsed.raw_source.uri,
    }


def _parse_projection_source(source: dict[str, str]) -> ParsedSource:
    if source.get("channel") == THEVC_INVESTMENT_CHANNEL:
        return parse_thevc_investment_card(str(source.get("payload") or ""))
    if source.get("channel") == PLATUM_INVESTMENT_CHANNEL:
        return parse_platum_portfolio_news(str(source.get("payload") or ""))
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


def _portfolio_news_row(parsed: ParsedSource, *, collected_at: str) -> dict[str, object]:
    fields = _payload_fields(parsed.raw_text)
    return {
        "collected_at": collected_at,
        "company": parsed.entity.name,
        "title": parsed.raw_source.title,
        "summary": fields.get("summary", ""),
        "url": parsed.raw_source.uri,
        "published_at": parsed.raw_source.published_at or "",
        "source": "Platum",
        "channel": parsed.raw_source.channel,
        "matched_companies": fields.get("matched companies", parsed.entity.name),
        "notified_at": "",
        "status": "new",
    }


def _candidate_detail_row(parsed: ParsedSource, *, collected_at: str) -> dict[str, object]:
    signal = parsed.signals[0]
    fields = _payload_fields(parsed.raw_text)
    return {
        "collected_at": collected_at,
        "company": parsed.entity.name,
        "normalized_name": parsed.entity.normalized_name or "",
        "representative": parsed.entity.representative,
        "homepage": parsed.entity.homepage or "",
        "contact_email": parsed.entity.contact_email,
        "region": parsed.entity.region,
        "industry": parsed.entity.industry,
        "summary": f"공개 카드 -> {parsed.entity.name}",
        "business_model": fields.get("business model") or fields.get("product") or signal.evidence_text,
        "investment_round": fields.get("investment round", ""),
        "investment_amount": fields.get("investment amount", ""),
        "investor": fields.get("investor", ""),
        "latest_score": "",
        "priority_probability": "",
        "queue_type": "new_source",
        "recommended_action": "score_candidates",
        "status": "crawled",
        "wiki_path": f"wiki/entities/{parsed.entity.name}.md",
    }


def _payload_fields(raw_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in raw_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().casefold()] = value.strip()
    return fields


def _has_fresh_terminal_queue_status(
    task: dict[str, Any],
    *,
    stale_days: int,
    reference_time: datetime,
) -> bool:
    if not is_terminal_queue_status(str(task.get("status") or "")):
        return False
    timestamp = _parse_timestamp(str(task.get("completed_at") or task.get("updated_at") or ""))
    if timestamp is None:
        return False
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return reference_time - timestamp < timedelta(days=max(stale_days, 0))


def _parse_timestamp(value: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _watchlist_for_target(target: dict[str, Any]) -> tuple[PortfolioKeyword, ...]:
    companies = target.get("portfolio_companies")
    if isinstance(companies, list):
        return build_portfolio_watchlist([str(company) for company in companies])
    watchlist_path = str(target.get("portfolio_watchlist_path") or "configs/portfolio_watchlist.txt").strip()
    return load_portfolio_watchlist(watchlist_path)


def _is_existing_platum_news_source(*, source: dict[str, str], structured_store: StructuredStore) -> bool:
    fields = _payload_fields(str(source.get("payload") or ""))
    url = fields.get("url", "")
    if not url:
        return False
    existing_rows = structured_store.query_rows(
        sql="select * from raw_sources where url=@url and channel=@channel",
        parameters={"url": url, "channel": PLATUM_INVESTMENT_CHANNEL},
    )
    return bool(existing_rows)


def _notify_portfolio_news(*, notifier: Notifier, slack_channel: str, sources: list[dict[str, str]]) -> int:
    items = [_payload_fields(str(source.get("payload") or "")) for source in sources]
    lines = ["Hermes 포트폴리오 뉴스 감지"]
    for item in items[:10]:
        company = item.get("company", "")
        title = item.get("title", "")
        published = item.get("published", "")
        summary = item.get("summary", "")
        url = item.get("url", "")
        lines.append(f"- {company} | {published} | {title}")
        if summary:
            lines.append(f"  {summary[:240]}")
        lines.append(f"  {url}")
    if len(items) > 10:
        lines.append(f"- 외 {len(items) - 10}건")
    notifier.send_message(channel=slack_channel, text="\n".join(lines))
    return len(items)


def _stable_run_id(targets: list[dict[str, Any]]) -> str:
    payload = json.dumps(targets, ensure_ascii=False, sort_keys=True)
    return f"run_crawl_{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:12]}"


def _now() -> str:
    return now_kst()
