from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol

from merry_runtime.adapters.interfaces import ReviewQueue, StructuredStore
from merry_runtime.clock import now_kst, now_kst_datetime
from merry_runtime.ingestion.sminfo import SminfoProfile, sminfo_profile_row, sminfo_sheet_row
from merry_runtime.ingestion.sminfo_queue import (
    RETRYABLE_QUEUE_STATUSES,
    next_retry_at,
    queue_status_for_profile,
    sminfo_queue_sheet_row,
)
from merry_runtime.regional_priority import evaluate_p1_regional_priority


_TERMINAL_SMINFO_STATUSES = {"matched", "not_found", "ambiguous"}
_MAX_SMINFO_BATCH_SIZE = 20
_PLACEHOLDER_COMPANY_NAMES = {"company", "기업명", "회사명", "업체명", "상호"}


class SminfoClient(Protocol):
    def lookup_company(self, *, company_name: str, candidate: dict[str, str]) -> SminfoProfile: ...


@dataclass(frozen=True, slots=True)
class SminfoEnrichmentResult:
    run_id: str
    candidate_count: int
    processed_count: int
    matched_count: int
    not_found_count: int
    ambiguous_count: int
    error_count: int


def enrich_sminfo_candidates(
    *,
    review_queue: ReviewQueue,
    structured_store: StructuredStore,
    client: SminfoClient,
    max_items: int,
    min_interval_seconds: int,
    stale_days: int = 30,
    company_names: list[str] | None = None,
    agent_id: str = "hermes-agent",
    use_queue: bool = True,
    retry_base_seconds: int = 3600,
    sleep_fn: Callable[[int], None] = time.sleep,
    run_id: str | None = None,
) -> SminfoEnrichmentResult:
    started_at = _now()
    run_id = run_id or f"run_sminfo_{_short_digest(started_at)}"
    bounded_max_items = min(max(max_items, 1), _MAX_SMINFO_BATCH_SIZE)
    reference_time = now_kst_datetime()
    queue_has_rows = _has_sminfo_queue_rows(structured_store=structured_store) if use_queue else False
    queue_tasks = (
        _claim_due_queue_tasks(
            structured_store=structured_store,
            max_items=bounded_max_items,
            reference_time=reference_time,
            agent_id=agent_id,
            leased_at=started_at,
        )
        if use_queue and not company_names
        else []
    )
    if queue_tasks:
        candidates = [_candidate_from_queue_task(task) for task in queue_tasks]
    elif queue_has_rows:
        candidates = []
    else:
        candidates = _candidate_rows(
            rows=review_queue.read_pending_reviews(sheet_tab="Candidate Detail"),
            company_names=company_names or [],
            max_items=bounded_max_items,
            stale_days=stale_days,
            reference_time=reference_time,
        )
    profiles: list[SminfoProfile] = []

    try:
        for index, candidate in enumerate(candidates):
            if index > 0:
                sleep_fn(min_interval_seconds)
            company_name = _candidate_company(candidate)
            try:
                profiles.append(client.lookup_company(company_name=company_name, candidate=candidate))
            except Exception as exc:
                profiles.append(
                    SminfoProfile(
                        requested_company=company_name,
                        match_status="error",
                        error_message=f"{type(exc).__name__}: {exc}"[:1000],
                    )
                )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    collected_at = _now()
    structured_rows = [
        sminfo_profile_row(profile=profile, profile_id=_profile_id(profile), collected_at=collected_at)
        for profile in profiles
    ]
    structured_store.upsert_rows(
        table="sminfo_company_profiles",
        rows=structured_rows,
        key_fields=("profile_id",),
    )
    queue_update_rows: list[dict[str, object]] = []
    if queue_tasks:
        queue_update_rows = [
            _queue_task_update(
                task=task,
                profile=profile,
                profile_id=_profile_id(profile),
                collected_at=collected_at,
                retry_base_seconds=retry_base_seconds,
            )
            for task, profile in zip(queue_tasks, profiles, strict=False)
        ]
        structured_store.upsert_rows(
            table="sminfo_enrichment_queue",
            rows=queue_update_rows,
            key_fields=("task_id",),
        )
    review_queue.upsert_cards(
        sheet_tab="SMINFO Enrichment",
        rows=[sminfo_sheet_row(profile=profile, collected_at=collected_at) for profile in profiles],
        key_fields=("requested_company", "sminfo_url"),
    )
    review_queue.upsert_cards(
        sheet_tab="Candidate Detail",
        rows=[_candidate_detail_update(candidate=candidate, profile=profile, collected_at=collected_at) for candidate, profile in zip(candidates, profiles, strict=False)],
        key_fields=("company", "homepage"),
    )
    if queue_update_rows:
        review_queue.upsert_cards(
            sheet_tab="SMINFO Queue",
            rows=[sminfo_queue_sheet_row(task) for task in queue_update_rows],
            key_fields=("task_id",),
        )
    result = SminfoEnrichmentResult(
        run_id=run_id,
        candidate_count=len(candidates),
        processed_count=len(profiles),
        matched_count=sum(1 for profile in profiles if profile.match_status == "matched"),
        not_found_count=sum(1 for profile in profiles if profile.match_status == "not_found"),
        ambiguous_count=sum(1 for profile in profiles if profile.match_status == "ambiguous"),
        error_count=sum(1 for profile in profiles if profile.match_status == "error"),
    )
    structured_store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": run_id,
                "job_name": "enrich-sminfo",
                "status": "success",
                "started_at": started_at,
                "finished_at": _now(),
                "input_count": len(candidates),
                "output_count": len(profiles),
                "error_message": "",
            }
        ],
        key_fields=("run_id",),
    )
    return result


def _candidate_rows(
    *,
    rows: list[dict[str, str]],
    company_names: list[str],
    max_items: int,
    stale_days: int,
    reference_time: datetime,
) -> list[dict[str, str]]:
    allowed = {name.strip() for name in company_names if name.strip()}
    candidates: list[dict[str, str]] = []
    for row in rows:
        candidate = {str(key): str(value) for key, value in row.items()}
        company = _candidate_company(candidate)
        if not company:
            continue
        if company.strip().casefold() in _PLACEHOLDER_COMPANY_NAMES:
            continue
        if allowed and company not in allowed:
            continue
        if not allowed and _has_fresh_terminal_sminfo_status(candidate, stale_days=stale_days, reference_time=reference_time):
            continue
        candidates.append(candidate)
        if len(candidates) >= max_items:
            break
    return candidates


def _has_sminfo_queue_rows(*, structured_store: StructuredStore) -> bool:
    return bool(
        structured_store.query_rows(
            sql="SELECT * FROM sminfo_enrichment_queue",
            parameters={},
        )
    )


def _claim_due_queue_tasks(
    *,
    structured_store: StructuredStore,
    max_items: int,
    reference_time: datetime,
    agent_id: str,
    leased_at: str,
) -> list[dict[str, object]]:
    lease = getattr(structured_store, "lease_sminfo_tasks", None)
    if callable(lease):
        return list(
            lease(
                max_items=max_items,
                reference_time=reference_time.isoformat(),
                agent_id=agent_id,
                leased_at=leased_at,
            )
        )
    tasks = _due_queue_tasks(
        structured_store=structured_store,
        max_items=max_items,
        reference_time=reference_time,
    )
    if tasks:
        _lease_queue_tasks(
            structured_store=structured_store,
            tasks=tasks,
            agent_id=agent_id,
            leased_at=leased_at,
        )
    return tasks


def _due_queue_tasks(
    *,
    structured_store: StructuredStore,
    max_items: int,
    reference_time: datetime,
) -> list[dict[str, object]]:
    rows = structured_store.query_rows(
        sql="SELECT * FROM sminfo_enrichment_queue",
        parameters={},
    )
    due_rows: list[dict[str, object]] = []
    for row in rows:
        status = str(row.get("status") or "")
        if status not in RETRYABLE_QUEUE_STATUSES:
            continue
        next_run_at = _parse_timestamp(str(row.get("next_run_at") or ""))
        if next_run_at is None:
            continue
        if next_run_at.tzinfo is None:
            next_run_at = next_run_at.replace(tzinfo=UTC)
        if next_run_at <= reference_time:
            due_rows.append(row)
    return sorted(due_rows, key=_queue_sort_key)[:max_items]


def _lease_queue_tasks(
    *,
    structured_store: StructuredStore,
    tasks: list[dict[str, object]],
    agent_id: str,
    leased_at: str,
) -> None:
    leased_tasks = [
        {
            **task,
            "status": "running",
            "locked_at": leased_at,
            "locked_by": agent_id,
            "updated_at": leased_at,
        }
        for task in tasks
    ]
    structured_store.upsert_rows(
        table="sminfo_enrichment_queue",
        rows=leased_tasks,
        key_fields=("task_id",),
    )


def _candidate_from_queue_task(task: dict[str, object]) -> dict[str, str]:
    return {str(key): "" if value is None else str(value) for key, value in task.items()}


def _queue_task_update(
    *,
    task: dict[str, object],
    profile: SminfoProfile,
    profile_id: str,
    collected_at: str,
    retry_base_seconds: int,
) -> dict[str, object]:
    attempt_count = _int_value(task.get("attempt_count")) + 1
    max_attempts = max(_int_value(task.get("max_attempts")), 1)
    updated = {
        **task,
        "attempt_count": attempt_count,
        "locked_at": "",
        "locked_by": "",
        "last_profile_id": profile_id,
        "updated_at": collected_at,
    }
    if profile.match_status == "error":
        failed = attempt_count >= max_attempts
        retry_time = _parse_timestamp(collected_at) or now_kst_datetime()
        return {
            **updated,
            "status": "failed" if failed else "retry",
            "next_run_at": collected_at if failed else next_retry_at(
                attempt_count=attempt_count,
                now=retry_time,
                base_seconds=retry_base_seconds,
            ),
            "last_error": profile.error_message,
            "completed_at": collected_at if failed else "",
        }
    return {
        **updated,
        "status": queue_status_for_profile(profile),
        "next_run_at": collected_at,
        "last_error": profile.error_message,
        "completed_at": collected_at,
    }


def _queue_sort_key(task: dict[str, object]) -> tuple[int, str]:
    return (_int_value(task.get("priority"), default=100), str(task.get("created_at") or ""))


def _int_value(value: object, *, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _candidate_company(candidate: dict[str, str]) -> str:
    return str(candidate.get("company") or candidate.get("normalized_name") or "").strip()


def _has_fresh_terminal_sminfo_status(
    candidate: dict[str, str],
    *,
    stale_days: int,
    reference_time: datetime,
) -> bool:
    if str(candidate.get("sminfo_status") or "") not in _TERMINAL_SMINFO_STATUSES:
        return False
    collected_at = _parse_timestamp(str(candidate.get("sminfo_collected_at") or ""))
    if collected_at is None:
        return False
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=UTC)
    return reference_time - collected_at < timedelta(days=max(stale_days, 0))


def _parse_timestamp(value: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _candidate_detail_update(*, candidate: dict[str, str], profile: SminfoProfile, collected_at: str) -> dict[str, object]:
    p1_context = evaluate_p1_regional_priority(
        region=candidate.get("region", ""),
        road_address=profile.road_address,
        business_model=candidate.get("business_model", ""),
        industry=candidate.get("industry", ""),
        company_type=profile.company_type,
        main_products=profile.main_products,
        standard_industry=profile.standard_industry,
    )
    return {
        "company": _candidate_company(candidate),
        "homepage": candidate.get("homepage", ""),
        "sminfo_status": profile.match_status,
        "sminfo_company": profile.matched_company,
        "sminfo_latest_financial_year": profile.latest_financial_year,
        "sminfo_revenue_krw_thousand": profile.revenue_krw_thousand,
        "sminfo_operating_income_krw_thousand": profile.operating_income_krw_thousand,
        "sminfo_net_income_krw_thousand": profile.net_income_krw_thousand,
        "sminfo_total_assets_krw_thousand": profile.total_assets_krw_thousand,
        "sminfo_shareholder_composition": profile.shareholder_composition,
        "sminfo_largest_shareholder": profile.largest_shareholder,
        "sminfo_largest_shareholder_ratio_pct": profile.largest_shareholder_ratio_pct,
        "sminfo_error_message": profile.error_message,
        "sminfo_profile_url": profile.sminfo_url,
        "sminfo_collected_at": collected_at,
        **p1_context,
    }


def _profile_id(profile: SminfoProfile) -> str:
    return "sminfo_" + _short_digest(profile.requested_company, profile.matched_company, profile.sminfo_url)


def _short_digest(*parts: str) -> str:
    return hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()[:12]


def _now() -> str:
    return now_kst()
