from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from merry_runtime.ingestion.sminfo import SminfoProfile
from merry_runtime.normalization import normalize_company_name


TERMINAL_QUEUE_STATUSES = {"matched", "matched_no_financials", "not_found", "ambiguous"}
RETRYABLE_QUEUE_STATUSES = {"pending", "retry"}
DEFAULT_PRIORITY = 100
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RETRY_BASE_SECONDS = 3600


def build_sminfo_task(
    candidate: dict[str, object],
    *,
    source_channel: str,
    now: str,
    priority: int = DEFAULT_PRIORITY,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict[str, object]:
    company = _display_company(str(candidate.get("company") or candidate.get("normalized_name") or ""))
    normalized_name = normalize_company_name(str(candidate.get("normalized_name") or company))
    representative = str(candidate.get("representative") or "").strip()
    homepage = str(candidate.get("homepage") or "").strip()
    source_url = str(candidate.get("source_url") or candidate.get("url") or "").strip()
    return {
        "task_id": sminfo_task_id(
            company=company,
            normalized_name=normalized_name,
            representative=representative,
            homepage=homepage,
            source_channel=source_channel,
        ),
        "company": company,
        "normalized_name": normalized_name,
        "representative": representative,
        "homepage": homepage,
        "source_url": source_url,
        "source_channel": source_channel,
        "status": "pending",
        "priority": priority,
        "attempt_count": 0,
        "max_attempts": max_attempts,
        "next_run_at": now,
        "locked_at": "",
        "locked_by": "",
        "last_error": "",
        "last_profile_id": "",
        "created_at": now,
        "updated_at": now,
        "completed_at": "",
    }


def sminfo_task_id(
    *,
    company: str,
    normalized_name: str = "",
    representative: str = "",
    homepage: str = "",
    source_channel: str,
) -> str:
    normalized_company = normalize_company_name(normalized_name or company)
    normalized_homepage = _homepage_key(homepage)
    normalized_representative = normalize_company_name(representative)
    key_parts = [normalized_company]
    if normalized_homepage or normalized_representative:
        key_parts.extend([normalized_homepage, normalized_representative])
    else:
        key_parts.append(source_channel.strip())
    digest = hashlib.sha1("|".join(key_parts).encode("utf-8")).hexdigest()[:16]
    return f"sminfo_task_{digest}"


def is_terminal_queue_status(status: str) -> bool:
    return status.strip() in TERMINAL_QUEUE_STATUSES


def next_retry_at(
    *,
    attempt_count: int,
    now: datetime,
    base_seconds: int = DEFAULT_RETRY_BASE_SECONDS,
) -> str:
    multiplier = 2 ** max(attempt_count - 1, 0)
    return (now + timedelta(seconds=max(base_seconds, 1) * multiplier)).isoformat()


def queue_status_for_profile(profile: SminfoProfile) -> str:
    if profile.match_status != "matched":
        return profile.match_status
    if any(
        (
            profile.latest_financial_year,
            profile.revenue_krw_thousand,
            profile.operating_income_krw_thousand,
            profile.net_income_krw_thousand,
            profile.total_assets_krw_thousand,
        )
    ):
        return "matched"
    return "matched_no_financials"


def sminfo_queue_sheet_row(task: dict[str, object]) -> dict[str, object]:
    return {
        "task_id": task.get("task_id", ""),
        "company": task.get("company", ""),
        "status": task.get("status", ""),
        "priority": task.get("priority", ""),
        "attempt_count": task.get("attempt_count", ""),
        "next_run_at": task.get("next_run_at", ""),
        "locked_by": task.get("locked_by", ""),
        "last_error": task.get("last_error", ""),
        "last_profile_id": task.get("last_profile_id", ""),
        "source_url": task.get("source_url", ""),
        "updated_at": task.get("updated_at", ""),
    }


def _display_company(value: str) -> str:
    return normalize_company_name(value) or value.strip()


def _normalize_homepage(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    parsed = urlsplit(stripped)
    if not parsed.scheme and not parsed.netloc:
        return stripped.rstrip("/")
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def _homepage_key(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    parse_value = stripped if "://" in stripped else f"//{stripped}"
    parsed = urlsplit(parse_value)
    host = (parsed.netloc or parsed.path.split("/", 1)[0]).lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path if parsed.netloc else ""
    path = path.rstrip("/")
    return f"{host}{path}"
