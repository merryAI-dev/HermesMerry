from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from merry_runtime.adapters.interfaces import Notifier, ObjectStore, ReviewQueue, StructuredStore
from merry_runtime.clock import now_kst, now_kst_datetime
from merry_runtime.ingestion.sminfo_queue import build_sminfo_task, is_terminal_queue_status, sminfo_queue_sheet_row
from merry_runtime.ingestion.platum import (
    PLATUM_INVESTMENT_CHANNEL,
    extract_platum_portfolio_news_sources,
    fetch_platum_facetwp_page,
)
from merry_runtime.ingestion.thevc import THEVC_INVESTMENT_CHANNEL, extract_thevc_investment_sources
from merry_runtime.ingestion.parsers import ParsedSource, parse_platum_portfolio_news, parse_thevc_investment_card
from merry_runtime.portfolio_watchlist import PortfolioKeyword, build_portfolio_watchlist, load_portfolio_watchlist
from merry_runtime.ingestion.web_crawler import CrawlFetchError, fetch_url as fetch_url_text
from merry_runtime.normalization import normalize_company_name
from merry_runtime.pipelines.ingest_sources import ingest_sources
from merry_runtime.regional_priority import evaluate_p1_regional_priority
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
    warning_count: int = 0


_PLATUM_DEFAULT_MAX_ARTICLES_PER_PAGE = 24
_PLATUM_DEFAULT_MAX_PAGES = 2
_PLATUM_MAX_PAGES = 50


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
    fetch_platum_page: Callable[[str, int], str] = fetch_platum_facetwp_page,
    sminfo_stale_days: int = 30,
    run_id: str | None = None,
) -> CrawlResult:
    started_at = _now()
    run_id = run_id or _stable_run_id(targets)
    active_targets = [_normalize_target(target) for target in targets if _is_active_target(target)]
    existing_portfolio_news_keys = _existing_portfolio_news_keys(review_queue=review_queue)

    sources: list[dict[str, str]] = []
    sheet_projection_sources: list[dict[str, str]] = []
    portfolio_news_sources: list[dict[str, str]] = []
    warnings: list[str] = []
    for target in active_targets:
        html = fetch_url(target["url"])
        if target["source_kind"] == THEVC_INVESTMENT_CHANNEL:
            extracted_sources = extract_thevc_investment_sources(
                html,
                source_url=target["url"],
                max_cards=int(target.get("max_cards") or 20),
                fetch_detail_url=fetch_url if _truthy(target.get("detail_enrichment"), default=True) else None,
            )
            sources.extend(extracted_sources)
            sheet_projection_sources.extend(extracted_sources)
            continue
        if target["source_kind"] == PLATUM_INVESTMENT_CHANNEL:
            extracted_sources, target_warnings = _extract_platum_sources_from_pages(
                first_page_html=html,
                target=target,
                fetch_platum_page=fetch_platum_page,
            )
            warnings.extend(target_warnings)
            new_sources = [
                source
                for source in extracted_sources
                if not _is_existing_platum_news_source(source=source, structured_store=structured_store)
            ]
            sources.extend(new_sources)
            new_sheet_sources = [
                source
                for source in new_sources
                if not _is_existing_portfolio_news_sheet_source(source=source, existing_keys=existing_portfolio_news_keys)
            ]
            sheet_projection_sources.extend(new_sheet_sources)
            portfolio_news_sources.extend(new_sheet_sources)
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
            _publish_sheet_projection(
                review_queue=review_queue,
                structured_store=structured_store,
                sources=sheet_projection_sources,
                collected_at=started_at,
            )
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
            if review_queue is not None and notified_count:
                _mark_portfolio_news_notified(
                    review_queue=review_queue,
                    sources=portfolio_news_sources,
                    collected_at=started_at,
                    notified_at=_now(),
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
        warning_count=len(warnings),
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
                "error_message": _join_warnings(warnings),
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


def _extract_platum_sources_from_pages(
    *,
    first_page_html: str,
    target: dict[str, Any],
    fetch_platum_page: Callable[[str, int], str],
) -> tuple[list[dict[str, str]], list[str]]:
    watchlist = _watchlist_for_target(target)
    max_articles = _target_positive_int(
        target.get("max_articles") or target.get("max_cards"),
        default=_PLATUM_DEFAULT_MAX_ARTICLES_PER_PAGE,
    )
    max_pages = _target_positive_int(
        target.get("max_pages"),
        default=_PLATUM_DEFAULT_MAX_PAGES,
        maximum=_PLATUM_MAX_PAGES,
    )
    extracted_sources: list[dict[str, str]] = []
    warnings: list[str] = []
    seen_keys: set[tuple[str, str]] = set()
    page_htmls = [first_page_html]
    for page in range(2, max_pages + 1):
        try:
            page_htmls.append(fetch_platum_page(target["url"], page))
        except CrawlFetchError as exc:
            warnings.append(f"Platum pagination failed for {target['url']} page {page}: {exc}")
            break
    for page_html in page_htmls:
        page_sources = extract_platum_portfolio_news_sources(
            page_html,
            source_url=target["url"],
            watchlist=watchlist,
            max_articles=max_articles,
        )
        for source in page_sources:
            fields = _payload_fields(str(source.get("payload") or ""))
            url = fields.get("url", "")
            company = fields.get("company", "")
            key = (url, company)
            if url and key in seen_keys:
                continue
            if url:
                seen_keys.add(key)
            extracted_sources.append(source)
    return extracted_sources, warnings


def _target_positive_int(value: Any, *, default: int, maximum: int | None = None) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    if maximum is not None:
        return min(parsed, maximum)
    return parsed


def _join_warnings(warnings: list[str], *, max_length: int = 1000) -> str:
    return "; ".join(warnings)[:max_length]


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


def _publish_sheet_projection(
    *,
    review_queue: ReviewQueue,
    structured_store: StructuredStore,
    sources: list[dict[str, str]],
    collected_at: str,
) -> None:
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
    kvic_profiles = _load_kvic_investor_profiles(structured_store)
    review_queue.upsert_cards(
        sheet_tab="Candidate Detail",
        rows=[
            _candidate_detail_row(parsed, collected_at=collected_at, kvic_profiles=kvic_profiles)
            for parsed in candidate_detail_sources
        ],
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


def _mark_portfolio_news_notified(
    *,
    review_queue: ReviewQueue,
    sources: list[dict[str, str]],
    collected_at: str,
    notified_at: str,
) -> None:
    parsed_sources = [_parse_projection_source(source) for source in sources]
    rows = []
    for parsed in parsed_sources:
        row = _portfolio_news_row(parsed, collected_at=collected_at)
        row["notified_at"] = notified_at
        rows.append(row)
    review_queue.upsert_cards(
        sheet_tab="Portfolio News",
        rows=rows,
        key_fields=("url", "company"),
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


def _candidate_detail_row(
    parsed: ParsedSource,
    *,
    collected_at: str,
    kvic_profiles: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    signal = parsed.signals[0]
    fields = _payload_fields(parsed.raw_text)
    business_model = fields.get("business model") or fields.get("product") or signal.evidence_text
    kvic_context = _kvic_investor_context(str(fields.get("investor", "")), kvic_profiles or [])
    p1_context = evaluate_p1_regional_priority(
        region=parsed.entity.region,
        business_model=business_model,
        industry=parsed.entity.industry,
    )
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
        "business_model": business_model,
        **p1_context,
        "investment_round": fields.get("investment round", ""),
        "investment_amount": fields.get("investment amount", ""),
        "investor": fields.get("investor", ""),
        "latest_score": "",
        "priority_probability": "",
        "queue_type": "new_source",
        "recommended_action": "score_candidates",
        "status": "crawled",
        "wiki_path": f"wiki/entities/{parsed.entity.name}.md",
        **kvic_context,
    }


def _load_kvic_investor_profiles(structured_store: StructuredStore) -> list[dict[str, Any]]:
    try:
        return [
            dict(row)
            for row in structured_store.query_rows(
                sql="select * from kvic_investor_managers",
                parameters={},
            )
        ]
    except Exception:
        return []


def _kvic_investor_context(investor_text: str, profiles: list[dict[str, Any]]) -> dict[str, object]:
    empty = {
        "kvic_matched_investors": "",
        "kvic_active_fund_count": "",
        "kvic_active_amount_eok": "",
        "kvic_fund_fields": "",
        "kvic_representative_funds": "",
        "kvic_profile_tags": "",
        "kvic_next_expiry_at": "",
    }
    if not investor_text.strip() or not profiles:
        return empty

    investor_tokens = [_normalize_investor_name(token) for token in _split_investors(investor_text)]
    matched = [
        profile
        for profile in profiles
        if _normalize_investor_name(str(profile.get("manager_name") or "")) in investor_tokens
    ]
    if not matched:
        return empty

    return {
        "kvic_matched_investors": ", ".join(str(profile.get("manager_name") or "") for profile in matched),
        "kvic_active_fund_count": sum(int(profile.get("active_fund_count") or 0) for profile in matched),
        "kvic_active_amount_eok": round(sum(float(profile.get("active_amount_eok") or 0.0) for profile in matched), 4),
        "kvic_fund_fields": _join_unique(profile.get("fund_fields") for profile in matched),
        "kvic_representative_funds": _join_unique(profile.get("representative_funds") for profile in matched),
        "kvic_profile_tags": _join_unique(profile.get("profile_tags") for profile in matched),
        "kvic_next_expiry_at": min(
            (str(profile.get("next_expiry_at") or "") for profile in matched if profile.get("next_expiry_at")),
            default="",
        ),
    }


def _split_investors(value: str) -> list[str]:
    normalized = value.replace("/", ",").replace("·", ",").replace(";", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def _normalize_investor_name(value: str) -> str:
    return (
        value.casefold()
        .replace(" ", "")
        .replace("(주)", "")
        .replace("㈜", "")
        .replace("주식회사", "")
        .replace("유한회사", "")
    )


def _join_unique(values: object) -> str:
    seen: list[str] = []
    for value in values:
        items = value if isinstance(value, (list, tuple)) else [value]
        for item in items:
            item_text = str(item).strip()
            if item_text and item_text not in seen:
                seen.append(item_text)
    return ", ".join(seen)


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
    company = fields.get("company", "").strip()
    existing_rows = structured_store.query_rows(
        sql="select * from raw_sources where url=@url and channel=@channel",
        parameters={"url": url, "channel": PLATUM_INVESTMENT_CHANNEL},
    )
    if not existing_rows or not company:
        return bool(existing_rows)
    expected_normalized = normalize_company_name(company)
    for row in existing_rows:
        source_id = str(row.get("source_id") or "")
        if _raw_source_has_company(source_id=source_id, normalized_company=expected_normalized, structured_store=structured_store):
            return True
    return False


def _raw_source_has_company(
    *,
    source_id: str,
    normalized_company: str,
    structured_store: StructuredStore,
) -> bool:
    if not source_id:
        return False
    signals = structured_store.query_rows(
        sql="select * from signals where source_id=@source_id",
        parameters={"source_id": source_id},
    )
    for signal in signals:
        entity_id = str(signal.get("entity_id") or "")
        if not entity_id:
            continue
        entities = structured_store.query_rows(
            sql="select * from mother_entities where entity_id=@entity_id",
            parameters={"entity_id": entity_id},
        )
        for entity in entities:
            existing_normalized = str(entity.get("normalized_name") or "") or normalize_company_name(
                str(entity.get("name") or "")
            )
            if existing_normalized == normalized_company:
                return True
    return False


def _existing_portfolio_news_keys(*, review_queue: ReviewQueue | None) -> set[tuple[str, str]]:
    if review_queue is None:
        return set()
    rows = review_queue.read_pending_reviews(sheet_tab="Portfolio News")
    return {
        (url, company)
        for row in rows
        if (url := str(row.get("url") or "").strip())
        for company in [str(row.get("company") or "").strip()]
    }


def _is_existing_portfolio_news_sheet_source(*, source: dict[str, str], existing_keys: set[tuple[str, str]]) -> bool:
    fields = _payload_fields(str(source.get("payload") or ""))
    url = fields.get("url", "").strip()
    company = fields.get("company", "").strip()
    return bool(url and ((url, company) in existing_keys or (url, "") in existing_keys))


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
