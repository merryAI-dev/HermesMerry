from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any


BUSINESS_TYPE_URL = "https://www.kvic.or.kr/api/businessType"
FUND_TYPE_URL = "https://www.kvic.or.kr/api/fundType"

_YEAR_PATTERN = re.compile(r"(\d{4})")
_TAG_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("climate_environment", ("환경", "기후", "그린", "탄소", "미래환경", "해양")),
    ("impact", ("소셜", "사회", "임팩트")),
    ("local_regional", ("지역", "지방", "로컬")),
    ("agrifood", ("농", "수산", "식품", "푸드")),
    ("early_stage", ("창업초기", "청년", "엔젤", "마이크로")),
    ("healthcare", ("바이오", "헬스", "의료")),
    ("content", ("문화", "콘텐츠", "영화", "게임")),
)


def parse_kvic_fund_types(payload: dict[str, Any], *, collected_at: str) -> list[dict[str, object]]:
    rows = payload.get("result") or []
    if not isinstance(rows, list):
        return []

    fund_types: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        fund_code = str(row.get("fundCode") or "").strip()
        fund_name = str(row.get("fundName") or "").strip()
        if not fund_code or not fund_name:
            continue
        fund_types.append(
            {
                "fund_code": fund_code,
                "fund_name": fund_name,
                "source_url": BUSINESS_TYPE_URL,
                "collected_at": collected_at,
            }
        )
    return fund_types


def parse_kvic_funds(
    payload: dict[str, Any],
    *,
    collected_at: str,
    reference_date: str,
) -> list[dict[str, object]]:
    funds: list[dict[str, object]] = []
    for result_key in sorted(key for key in payload if key.startswith("result_")):
        rows = payload.get(result_key) or []
        if not isinstance(rows, list):
            continue
        fund_type_code = result_key.removeprefix("result_")
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue
            normalized = _normalize_fund_row(
                raw_row,
                fund_type_code=fund_type_code,
                collected_at=collected_at,
                reference_date=reference_date,
            )
            if normalized:
                funds.append(normalized)
    return funds


def build_kvic_investor_profiles(funds: list[dict[str, object]], *, collected_at: str) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for fund in funds:
        manager_name = str(fund.get("manager_name") or "").strip()
        if manager_name:
            grouped[manager_name].append(fund)

    profiles: list[dict[str, object]] = []
    for manager_name, manager_funds in grouped.items():
        active_funds = [fund for fund in manager_funds if bool(fund.get("is_active"))]
        profile_basis = active_funds or manager_funds
        fund_fields = _unique_sorted(str(fund.get("field_name") or "") for fund in profile_basis)
        representative_funds = _representative_funds(profile_basis)
        active_expiries = sorted(str(fund.get("expires_at") or "") for fund in active_funds if fund.get("expires_at"))
        all_expiries = sorted(str(fund.get("expires_at") or "") for fund in manager_funds if fund.get("expires_at"))
        profiles.append(
            {
                "manager_id": f"kvic_mgr_{_short_digest(manager_name)}",
                "manager_name": manager_name,
                "total_fund_count": len(manager_funds),
                "active_fund_count": len(active_funds),
                "total_amount_eok": _sum_float(manager_funds, "amount_eok"),
                "active_amount_eok": _sum_float(active_funds, "amount_eok"),
                "total_commitment_eok": _sum_float(manager_funds, "commitment_eok"),
                "active_commitment_eok": _sum_float(active_funds, "commitment_eok"),
                "fund_fields": fund_fields,
                "representative_funds": representative_funds,
                "profile_tags": _profile_tags(profile_basis),
                "latest_fund_year": max((int(fund.get("fund_year") or 0) for fund in manager_funds), default=0),
                "next_expiry_at": active_expiries[0] if active_expiries else "",
                "latest_expiry_at": all_expiries[-1] if all_expiries else "",
                "collected_at": collected_at,
            }
        )
    return sorted(profiles, key=lambda row: (-int(row["active_fund_count"]), str(row["manager_name"])))


def _normalize_fund_row(
    raw_row: dict[str, Any],
    *,
    fund_type_code: str,
    collected_at: str,
    reference_date: str,
) -> dict[str, object] | None:
    manager_name = str(raw_row.get("mng") or "").strip()
    association_name = str(raw_row.get("asn") or "").strip()
    if not manager_name or not association_name:
        return None

    year_label = str(raw_row.get("year") or "").strip()
    field_name = str(raw_row.get("fd") or "").strip()
    expires_at = str(raw_row.get("exp") or "").strip()
    amount_raw = _raw_amount(raw_row.get("amt"))
    commitment_raw = _raw_amount(raw_row.get("ca"))
    fund_year = _parse_year(year_label)
    return {
        "fund_id": f"kvic_fund_{_short_digest(fund_type_code, year_label, field_name, manager_name, association_name, expires_at)}",
        "fund_type_code": fund_type_code,
        "year_label": year_label,
        "fund_year": fund_year,
        "field_name": field_name,
        "manager_name": manager_name,
        "association_name": association_name,
        "expires_at": expires_at,
        "amount_raw": amount_raw,
        "commitment_raw": commitment_raw,
        "amount_eok": _amount_to_eok(amount_raw),
        "commitment_eok": _amount_to_eok(commitment_raw),
        "is_active": bool(expires_at and expires_at >= reference_date),
        "source_url": FUND_TYPE_URL,
        "raw_json": json.dumps(raw_row, ensure_ascii=False, sort_keys=True),
        "collected_at": collected_at,
    }


def _parse_year(value: str) -> int:
    match = _YEAR_PATTERN.search(value)
    return int(match.group(1)) if match else 0


def _raw_amount(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _amount_to_eok(value: str) -> float:
    if not value:
        return 0.0
    normalized = value.replace(",", "")
    try:
        return round(float(normalized) / 100, 4)
    except ValueError:
        return 0.0


def _sum_float(rows: list[dict[str, object]], field: str) -> float:
    return round(sum(float(row.get(field) or 0.0) for row in rows), 4)


def _representative_funds(funds: list[dict[str, object]], *, limit: int = 5) -> list[str]:
    sorted_funds = sorted(
        funds,
        key=lambda fund: (-int(fund.get("fund_year") or 0), str(fund.get("association_name") or "")),
    )
    return [str(fund["association_name"]) for fund in sorted_funds[:limit] if fund.get("association_name")]


def _profile_tags(funds: list[dict[str, object]]) -> list[str]:
    corpus = " ".join(
        " ".join(
            [
                str(fund.get("field_name") or ""),
                str(fund.get("association_name") or ""),
            ]
        )
        for fund in funds
    )
    tags = [tag for tag, needles in _TAG_RULES if any(needle in corpus for needle in needles)]
    return tags


def _unique_sorted(values: object) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _short_digest(*parts: str) -> str:
    payload = "\n".join(parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
