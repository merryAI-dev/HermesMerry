from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from merry_runtime.adapters.interfaces import KVICDataClient, ReviewQueue, StructuredStore, WebSearchClient
from merry_runtime.clock import now_kst
from merry_runtime.ingestion.kvic import build_kvic_investor_profiles, parse_kvic_fund_types, parse_kvic_funds
from merry_runtime.pipelines.research_investors import publish_investor_db


FUND_DB_TAB = "Fund DB"
FUND_DB_HEADERS: tuple[str, ...] = (
    "펀드명",
    "운용사",
    "펀드종류",
    "출자분야",
    "결성연도",
    "만기일",
    "운영상태",
    "펀드규모(억원)",
    "약정액(억원)",
    "펀드 설명",
    "설명 근거 제목",
    "설명 근거 URL",
    "설명 상태",
    "검색어",
    "수집시각",
)
_STATE_KEY = "fund_snapshot"


@dataclass(frozen=True, slots=True)
class KVICSyncResult:
    run_id: str
    status: str
    fund_type_count: int
    fund_count: int
    manager_count: int
    described_fund_count: int = 0
    skipped_reason: str = ""


def sync_kvic_funds(
    *,
    structured_store: StructuredStore,
    client: KVICDataClient,
    review_queue: ReviewQueue | None = None,
    search_client: WebSearchClient | None = None,
    reference_date: str | None = None,
    collected_at: str | None = None,
    sync_interval_seconds: int = 86400,
    fund_description_batch_limit: int = 50,
    fund_description_stale_days: int = 30,
    fund_search_max_results: int = 5,
    run_id: str | None = None,
) -> KVICSyncResult:
    collected_at = collected_at or now_kst()
    reference_date = reference_date or collected_at[:10]
    run_id = run_id or f"run_kvic_{_short_digest(collected_at)}"
    previous_state = _latest_state(structured_store)
    if _is_fresh(previous_state, collected_at=collected_at, sync_interval_seconds=sync_interval_seconds):
        described_fund_count = 0
        if search_client is not None:
            described_fund_count = _refresh_fund_descriptions(
                structured_store=structured_store,
                funds=_query_all(structured_store, "kvic_funds"),
                search_client=search_client,
                collected_at=collected_at,
                batch_limit=fund_description_batch_limit,
                stale_days=fund_description_stale_days,
                max_results=fund_search_max_results,
            )
        result = KVICSyncResult(
            run_id=run_id,
            status="skipped",
            fund_type_count=int(previous_state.get("fund_type_count") or 0),
            fund_count=int(previous_state.get("fund_count") or 0),
            manager_count=int(previous_state.get("manager_count") or 0),
            described_fund_count=described_fund_count,
            skipped_reason="fresh_snapshot",
        )
        if review_queue is not None:
            _publish_sheets(structured_store=structured_store, review_queue=review_queue)
        _persist_state(structured_store=structured_store, result=result, collected_at=collected_at, latest_success_at=previous_state.get("latest_success_at"))
        _record_agent_run(structured_store=structured_store, result=result, started_at=collected_at, finished_at=now_kst())
        return result

    fund_types = parse_kvic_fund_types(client.fetch_fund_types(), collected_at=collected_at)
    funds = parse_kvic_funds(
        client.fetch_funds(),
        collected_at=collected_at,
        reference_date=reference_date,
    )
    profiles = build_kvic_investor_profiles(funds, collected_at=collected_at)

    structured_store.upsert_rows(table="kvic_fund_types", rows=fund_types, key_fields=("fund_code",))
    structured_store.upsert_rows(table="kvic_funds", rows=funds, key_fields=("fund_id",))
    structured_store.upsert_rows(table="kvic_investor_managers", rows=profiles, key_fields=("manager_id",))

    described_fund_count = 0
    if search_client is not None:
        described_fund_count = _refresh_fund_descriptions(
            structured_store=structured_store,
            funds=funds,
            search_client=search_client,
            collected_at=collected_at,
            batch_limit=fund_description_batch_limit,
            stale_days=fund_description_stale_days,
            max_results=fund_search_max_results,
        )

    if review_queue is not None:
        _publish_sheets(structured_store=structured_store, review_queue=review_queue)

    result = KVICSyncResult(
        run_id=run_id,
        status="success",
        fund_type_count=len(fund_types),
        fund_count=len(funds),
        manager_count=len(profiles),
        described_fund_count=described_fund_count,
    )
    _persist_state(structured_store=structured_store, result=result, collected_at=collected_at, latest_success_at=collected_at)
    _record_agent_run(structured_store=structured_store, result=result, started_at=collected_at, finished_at=now_kst())
    return result


def _publish_sheets(*, structured_store: StructuredStore, review_queue: ReviewQueue) -> None:
    fund_types = _query_all(structured_store, "kvic_fund_types")
    funds = _query_all(structured_store, "kvic_funds")
    descriptions = _query_all(structured_store, "kvic_fund_descriptions")
    publish_investor_db(structured_store=structured_store, review_queue=review_queue)
    review_queue.replace_rows(
        sheet_tab=FUND_DB_TAB,
        headers=FUND_DB_HEADERS,
        rows=_fund_sheet_rows(funds=funds, fund_types=fund_types, descriptions=descriptions),
    )


def _fund_sheet_rows(
    *,
    funds: list[dict[str, object]],
    fund_types: list[dict[str, object]],
    descriptions: list[dict[str, object]],
) -> list[dict[str, object]]:
    fund_type_names = {str(row.get("fund_code") or ""): str(row.get("fund_name") or "") for row in fund_types}
    description_by_fund_id = {str(row.get("fund_id") or ""): row for row in descriptions}
    rows: list[dict[str, object]] = []
    for fund in sorted(funds, key=_fund_sort_key):
        description = description_by_fund_id.get(str(fund.get("fund_id") or ""), {})
        rows.append(
            {
                "펀드명": fund.get("association_name", ""),
                "운용사": fund.get("manager_name", ""),
                "펀드종류": fund_type_names.get(str(fund.get("fund_type_code") or ""), ""),
                "출자분야": fund.get("field_name", ""),
                "결성연도": fund.get("fund_year", ""),
                "만기일": fund.get("expires_at", ""),
                "운영상태": "활성" if bool(fund.get("is_active")) else "만기",
                "펀드규모(억원)": fund.get("amount_eok", ""),
                "약정액(억원)": fund.get("commitment_eok", ""),
                "펀드 설명": description.get("description", ""),
                "설명 근거 제목": description.get("source_title", ""),
                "설명 근거 URL": description.get("source_url", ""),
                "설명 상태": description.get("status", ""),
                "검색어": description.get("search_query", ""),
                "수집시각": fund.get("collected_at", ""),
            }
        )
    return rows


def _refresh_fund_descriptions(
    *,
    structured_store: StructuredStore,
    funds: list[dict[str, object]],
    search_client: WebSearchClient,
    collected_at: str,
    batch_limit: int,
    stale_days: int,
    max_results: int,
) -> int:
    if batch_limit <= 0 or max_results <= 0:
        return 0
    existing = {str(row.get("fund_id") or ""): row for row in _query_all(structured_store, "kvic_fund_descriptions")}
    selected = [
        fund
        for fund in sorted(funds, key=_fund_sort_key)
        if _needs_description_refresh(
            existing.get(str(fund.get("fund_id") or "")),
            collected_at=collected_at,
            stale_days=stale_days,
        )
    ][:batch_limit]
    rows = [
        _describe_fund(
            fund=fund,
            search_client=search_client,
            collected_at=collected_at,
            max_results=max_results,
        )
        for fund in selected
    ]
    structured_store.upsert_rows(table="kvic_fund_descriptions", rows=rows, key_fields=("fund_id",))
    return len(rows)


def _describe_fund(
    *,
    fund: dict[str, object],
    search_client: WebSearchClient,
    collected_at: str,
    max_results: int,
) -> dict[str, object]:
    query = _fund_search_query(fund)
    base = {
        "fund_id": fund["fund_id"],
        "description": _fund_description_from_fund(fund=fund),
        "source_title": "",
        "source_url": "",
        "source_snippet": "",
        "search_query": query,
        "status": "no_result",
        "error_message": "",
        "collected_at": collected_at,
        "updated_at": collected_at,
    }
    try:
        result = _select_search_result(
            fund=fund,
            results=search_client.search(query, max_results=max_results),
        )
    except Exception as exc:
        return {**base, "status": "error", "error_message": f"{type(exc).__name__}: {exc}"[:1000]}
    if result is None:
        return base
    return {
        **base,
        "description": _fund_description_from_result(fund=fund, result=result),
        "source_title": result.get("title", ""),
        "source_url": result.get("url", ""),
        "source_snippet": result.get("snippet", ""),
        "status": "success",
    }


def _select_search_result(*, fund: dict[str, object], results: list[dict[str, str]]) -> dict[str, str] | None:
    association_name = _normalize_text(fund.get("association_name", ""))
    manager_name = _normalize_text(fund.get("manager_name", ""))
    field_name = _normalize_text(fund.get("field_name", ""))
    for result in results:
        text = _normalize_text(" ".join(str(result.get(key, "")) for key in ("title", "snippet")))
        if association_name and association_name in text:
            return result
        if manager_name and field_name and manager_name in text and field_name in text:
            return result
    return None


def _fund_description_from_result(*, fund: dict[str, object], result: dict[str, str]) -> str:
    description = _fund_description_from_fund(fund=fund)
    snippet = _first_sentence(str(result.get("snippet") or result.get("title") or ""))
    if not snippet:
        return description
    return f"{description} {snippet}".strip()


def _fund_description_from_fund(*, fund: dict[str, object]) -> str:
    association_name = str(fund.get("association_name") or "").strip()
    manager_name = str(fund.get("manager_name") or "").strip()
    field_name = str(fund.get("field_name") or "").strip()
    field_phrase = f" {field_name} 분야" if field_name else ""
    details: list[str] = []
    amount = fund.get("amount_eok")
    commitment = fund.get("commitment_eok")
    expires_at = str(fund.get("expires_at") or "").strip()
    if amount not in (None, ""):
        details.append(f"펀드규모 {amount}억원")
    if commitment not in (None, ""):
        details.append(f"약정액 {commitment}억원")
    if expires_at:
        details.append(f"만기 {expires_at}")
    suffix = f" ({', '.join(details)})" if details else ""
    return f"{association_name}은 {manager_name}{_subject_particle(manager_name)} 운용하는{field_phrase} 펀드입니다{suffix}.".strip()


def _fund_search_query(fund: dict[str, object]) -> str:
    association_name = str(fund.get("association_name") or "").strip()
    manager_name = str(fund.get("manager_name") or "").strip()
    field_name = str(fund.get("field_name") or "").strip()
    parts = [f'"{association_name}"', f'"{manager_name}"']
    if field_name:
        parts.append(field_name)
    return " ".join(part for part in parts if part.strip('"'))


def _needs_description_refresh(description: dict[str, object] | None, *, collected_at: str, stale_days: int) -> bool:
    if description is None:
        return True
    updated_at = _parse_datetime(str(description.get("updated_at") or ""))
    current = _parse_datetime(collected_at)
    if updated_at is None or current is None:
        return True
    refresh_days = max(1, stale_days) if description.get("status") == "success" else 1
    return (current - updated_at).days >= refresh_days


def _query_all(structured_store: StructuredStore, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in structured_store.query_rows(sql=f"select * from {table}", parameters={})]


def _latest_state(structured_store: StructuredStore) -> dict[str, object]:
    rows = structured_store.query_rows(
        sql="select * from kvic_sync_state where state_key=@state_key",
        parameters={"state_key": _STATE_KEY},
    )
    return rows[0] if rows else {}


def _is_fresh(state: dict[str, object], *, collected_at: str, sync_interval_seconds: int) -> bool:
    if not state.get("latest_success_at"):
        return False
    latest = _parse_datetime(str(state["latest_success_at"]))
    current = _parse_datetime(collected_at)
    if latest is None or current is None:
        return False
    return (current - latest).total_seconds() < sync_interval_seconds


def _persist_state(
    *,
    structured_store: StructuredStore,
    result: KVICSyncResult,
    collected_at: str,
    latest_success_at: object,
) -> None:
    structured_store.upsert_rows(
        table="kvic_sync_state",
        rows=[
            {
                "state_key": _STATE_KEY,
                "latest_success_at": latest_success_at or "",
                "status": result.status,
                "fund_type_count": result.fund_type_count,
                "fund_count": result.fund_count,
                "manager_count": result.manager_count,
                "skipped_reason": result.skipped_reason,
                "updated_at": collected_at,
            }
        ],
        key_fields=("state_key",),
    )


def _record_agent_run(
    *,
    structured_store: StructuredStore,
    result: KVICSyncResult,
    started_at: str,
    finished_at: str,
) -> None:
    structured_store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": result.run_id,
                "job_name": "sync-kvic-funds",
                "status": result.status,
                "started_at": started_at,
                "finished_at": finished_at,
                "input_count": 0,
                "output_count": result.manager_count,
                "error_message": result.skipped_reason,
            }
        ],
        key_fields=("run_id",),
    )


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _join(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value if str(item))
    return str(value or "")


def _fund_sort_key(fund: dict[str, object]) -> tuple[int, int, str, str]:
    return (
        0 if bool(fund.get("is_active")) else 1,
        -int(fund.get("fund_year") or 0),
        str(fund.get("expires_at") or "9999-99-99"),
        str(fund.get("association_name") or ""),
    )


def _normalize_text(value: object) -> str:
    return "".join(str(value or "").casefold().split())


def _subject_particle(value: str) -> str:
    if not value:
        return "가"
    code_point = ord(value[-1])
    if 0xAC00 <= code_point <= 0xD7A3:
        return "이" if (code_point - 0xAC00) % 28 else "가"
    return "가"


def _first_sentence(value: str, max_length: int = 240) -> str:
    text = " ".join(value.split())
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."


def _short_digest(*parts: str) -> str:
    payload = "\n".join(parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
