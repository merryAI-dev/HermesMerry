from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol

from merry_runtime.adapters.interfaces import ReviewQueue, StructuredStore
from merry_runtime.ingestion.sminfo import SminfoProfile, sminfo_profile_row, sminfo_sheet_row


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
    sleep_fn: Callable[[int], None] = time.sleep,
    run_id: str | None = None,
) -> SminfoEnrichmentResult:
    started_at = _now()
    run_id = run_id or f"run_sminfo_{_short_digest(started_at)}"
    bounded_max_items = min(max(max_items, 1), _MAX_SMINFO_BATCH_SIZE)
    candidates = _candidate_rows(
        rows=review_queue.read_pending_reviews(sheet_tab="Candidate Detail"),
        company_names=company_names or [],
        max_items=bounded_max_items,
        stale_days=stale_days,
        reference_time=datetime.now(UTC),
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
    }


def _profile_id(profile: SminfoProfile) -> str:
    return "sminfo_" + _short_digest(profile.requested_company, profile.matched_company, profile.sminfo_url)


def _short_digest(*parts: str) -> str:
    return hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()[:12]


def _now() -> str:
    return datetime.now(UTC).isoformat()
