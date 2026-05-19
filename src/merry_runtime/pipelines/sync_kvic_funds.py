from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from merry_runtime.adapters.interfaces import KVICDataClient, ReviewQueue, StructuredStore
from merry_runtime.clock import now_kst
from merry_runtime.ingestion.kvic import build_kvic_investor_profiles, parse_kvic_fund_types, parse_kvic_funds


INVESTOR_DB_TAB = "Investor DB"
INVESTOR_DB_HEADERS: tuple[str, ...] = (
    "manager_name",
    "active_fund_count",
    "total_fund_count",
    "active_amount_eok",
    "active_commitment_eok",
    "fund_fields",
    "representative_funds",
    "profile_tags",
    "next_expiry_at",
    "latest_expiry_at",
    "collected_at",
)
_STATE_KEY = "fund_snapshot"


@dataclass(frozen=True, slots=True)
class KVICSyncResult:
    run_id: str
    status: str
    fund_type_count: int
    fund_count: int
    manager_count: int
    skipped_reason: str = ""


def sync_kvic_funds(
    *,
    structured_store: StructuredStore,
    client: KVICDataClient,
    review_queue: ReviewQueue | None = None,
    reference_date: str | None = None,
    collected_at: str | None = None,
    sync_interval_seconds: int = 86400,
    run_id: str | None = None,
) -> KVICSyncResult:
    collected_at = collected_at or now_kst()
    reference_date = reference_date or collected_at[:10]
    run_id = run_id or f"run_kvic_{_short_digest(collected_at)}"
    previous_state = _latest_state(structured_store)
    if _is_fresh(previous_state, collected_at=collected_at, sync_interval_seconds=sync_interval_seconds):
        result = KVICSyncResult(
            run_id=run_id,
            status="skipped",
            fund_type_count=int(previous_state.get("fund_type_count") or 0),
            fund_count=int(previous_state.get("fund_count") or 0),
            manager_count=int(previous_state.get("manager_count") or 0),
            skipped_reason="fresh_snapshot",
        )
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

    if review_queue is not None:
        review_queue.replace_rows(
            sheet_tab=INVESTOR_DB_TAB,
            headers=INVESTOR_DB_HEADERS,
            rows=_sheet_rows(profiles),
        )

    result = KVICSyncResult(
        run_id=run_id,
        status="success",
        fund_type_count=len(fund_types),
        fund_count=len(funds),
        manager_count=len(profiles),
    )
    _persist_state(structured_store=structured_store, result=result, collected_at=collected_at, latest_success_at=collected_at)
    _record_agent_run(structured_store=structured_store, result=result, started_at=collected_at, finished_at=now_kst())
    return result


def _sheet_rows(profiles: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for profile in profiles:
        rows.append(
            {
                "manager_name": profile["manager_name"],
                "active_fund_count": profile["active_fund_count"],
                "total_fund_count": profile["total_fund_count"],
                "active_amount_eok": profile["active_amount_eok"],
                "active_commitment_eok": profile["active_commitment_eok"],
                "fund_fields": _join(profile.get("fund_fields")),
                "representative_funds": _join(profile.get("representative_funds")),
                "profile_tags": _join(profile.get("profile_tags")),
                "next_expiry_at": profile.get("next_expiry_at", ""),
                "latest_expiry_at": profile.get("latest_expiry_at", ""),
                "collected_at": profile["collected_at"],
            }
        )
    return rows


def _latest_state(structured_store: StructuredStore) -> dict[str, object]:
    rows = structured_store.query_rows(
        sql="select * from kvic_sync_state where state_key=@state_key",
        parameters={"state_key": _STATE_KEY},
    )
    return rows[0] if rows else {}


def _is_fresh(state: dict[str, object], *, collected_at: str, sync_interval_seconds: int) -> bool:
    if state.get("status") != "success" or not state.get("latest_success_at"):
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


def _short_digest(*parts: str) -> str:
    payload = "\n".join(parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
