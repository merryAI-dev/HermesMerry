from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from merry_runtime.normalization import normalize_company_name, normalized_region


SMINFO_CHANNEL = "sminfo_company_profile"
_REPRESENTATIVE_SPLIT = re.compile(r"[∙·,/\s]+|외|및|ㆍ")
_NUMBER = re.compile(r"[^0-9-]")
_PROFILE_RAW_FIELDS = (
    "기업명",
    "대표자명",
    "기업형태",
    "설립일",
    "주소(도로명)",
    "주소",
    "홈페이지",
    "주생산품",
    "표준산업",
    "정보수정일자",
)
_FINANCIAL_RAW_FIELDS = ("결산년도", "총자산", "매출액", "영업이익", "당기순이익")


@dataclass(frozen=True, slots=True)
class SminfoSearchResult:
    company_name: str
    representative: str
    company_type: str
    industry: str
    road_address: str
    result_index: int


@dataclass(frozen=True, slots=True)
class SminfoMatchDecision:
    status: str
    result: SminfoSearchResult | None = None
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class SminfoProfile:
    requested_company: str
    match_status: str
    matched_company: str = ""
    representative: str = ""
    company_type: str = ""
    established_at: str = ""
    road_address: str = ""
    homepage: str = ""
    main_products: str = ""
    standard_industry: str = ""
    info_updated_at: str = ""
    latest_financial_year: str = ""
    revenue_krw_thousand: str = ""
    operating_income_krw_thousand: str = ""
    net_income_krw_thousand: str = ""
    total_assets_krw_thousand: str = ""
    sminfo_url: str = ""
    error_message: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)


def choose_sminfo_search_result(
    *,
    requested_company: str,
    candidate: dict[str, str],
    results: list[SminfoSearchResult],
) -> SminfoMatchDecision:
    if not results:
        return SminfoMatchDecision(status="not_found", rationale="no search results")

    requested_normalized = normalize_company_name(requested_company)
    exact_matches = [result for result in results if normalize_company_name(result.company_name) == requested_normalized]
    candidates = exact_matches or (results if len(results) == 1 else [])
    if not candidates:
        return SminfoMatchDecision(status="ambiguous", rationale="multiple partial search results")
    if len(candidates) == 1:
        return SminfoMatchDecision(status="matched", result=candidates[0], rationale="single matching result")

    representative_match = _filter_by_representative(candidates, str(candidate.get("representative") or ""))
    if len(representative_match) == 1:
        return SminfoMatchDecision(status="matched", result=representative_match[0], rationale="representative matched")

    region_match = _filter_by_region(representative_match or candidates, str(candidate.get("region") or ""))
    if len(region_match) == 1:
        return SminfoMatchDecision(status="matched", result=region_match[0], rationale="region matched")

    return SminfoMatchDecision(status="ambiguous", rationale="duplicate names need human review")


def parse_sminfo_profile_tables(
    *,
    requested_company: str,
    sminfo_url: str,
    tables: list[dict[str, object]],
) -> SminfoProfile:
    profile_fields = _profile_fields(_table_rows(tables, "기업프로필정보"))
    financial_fields = _latest_financial_fields(_table_rows(tables, "매출현황"))
    return SminfoProfile(
        requested_company=requested_company,
        match_status="matched",
        matched_company=profile_fields.get("기업명", ""),
        representative=profile_fields.get("대표자명", ""),
        company_type=profile_fields.get("기업형태", ""),
        established_at=profile_fields.get("설립일", ""),
        road_address=profile_fields.get("주소(도로명)", "") or profile_fields.get("주소", ""),
        homepage=profile_fields.get("홈페이지", ""),
        main_products=profile_fields.get("주생산품", ""),
        standard_industry=profile_fields.get("표준산업", ""),
        info_updated_at=profile_fields.get("정보수정일자", ""),
        latest_financial_year=financial_fields.get("결산년도", ""),
        revenue_krw_thousand=_clean_number(financial_fields.get("매출액", "")),
        operating_income_krw_thousand=_clean_number(financial_fields.get("영업이익", "")),
        net_income_krw_thousand=_clean_number(financial_fields.get("당기순이익", "")),
        total_assets_krw_thousand=_clean_number(financial_fields.get("총자산", "")),
        sminfo_url=sminfo_url,
        raw_payload={
            "profile_fields": _allowlisted_fields(profile_fields, _PROFILE_RAW_FIELDS),
            "latest_financial_fields": _allowlisted_fields(financial_fields, _FINANCIAL_RAW_FIELDS),
        },
    )


def sminfo_profile_row(*, profile: SminfoProfile, profile_id: str, collected_at: str) -> dict[str, object]:
    return {
        "profile_id": profile_id,
        "requested_company": profile.requested_company,
        "match_status": profile.match_status,
        "matched_company": profile.matched_company,
        "representative": profile.representative,
        "company_type": profile.company_type,
        "established_at": profile.established_at,
        "road_address": profile.road_address,
        "homepage": profile.homepage,
        "main_products": profile.main_products,
        "standard_industry": profile.standard_industry,
        "info_updated_at": profile.info_updated_at,
        "latest_financial_year": profile.latest_financial_year,
        "revenue_krw_thousand": profile.revenue_krw_thousand,
        "operating_income_krw_thousand": profile.operating_income_krw_thousand,
        "net_income_krw_thousand": profile.net_income_krw_thousand,
        "total_assets_krw_thousand": profile.total_assets_krw_thousand,
        "sminfo_url": profile.sminfo_url,
        "raw_json": json.dumps(profile.raw_payload or asdict(profile), ensure_ascii=False, sort_keys=True),
        "error_message": profile.error_message,
        "collected_at": collected_at,
    }


def sminfo_sheet_row(*, profile: SminfoProfile, collected_at: str) -> dict[str, object]:
    row = sminfo_profile_row(profile=profile, profile_id="", collected_at=collected_at)
    row.pop("profile_id", None)
    row.pop("raw_json", None)
    return row


def _filter_by_representative(results: list[SminfoSearchResult], representative: str) -> list[SminfoSearchResult]:
    names = {normalize_company_name(name) for name in _REPRESENTATIVE_SPLIT.split(representative) if name.strip()}
    if not names:
        return []
    return [result for result in results if normalize_company_name(result.representative) in names]


def _filter_by_region(results: list[SminfoSearchResult], region: str) -> list[SminfoSearchResult]:
    normalized = normalized_region(region)
    if not normalized:
        return []
    region_tokens = [token for token in normalized.split() if len(token) >= 2]
    if not region_tokens:
        return []
    return [
        result
        for result in results
        if any(token in normalized_region(result.road_address) for token in region_tokens)
    ]


def _table_rows(tables: list[dict[str, object]], caption: str) -> list[list[str]]:
    for table in tables:
        if str(table.get("caption") or "").strip() == caption:
            rows = table.get("rows") or []
            return [[str(cell).strip() for cell in row] for row in rows if isinstance(row, list)]
    return []


def _profile_fields(rows: list[list[str]]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for row in rows:
        index = 0
        while index + 1 < len(row):
            key = row[index].strip()
            value = row[index + 1].strip()
            if key:
                fields[key] = value
            index += 2
    return fields


def _latest_financial_fields(rows: list[list[str]]) -> dict[str, str]:
    if len(rows) < 2:
        return {}
    headers = rows[0]
    values = rows[1]
    return dict(zip(headers, values, strict=False))


def _clean_number(value: str) -> str:
    return _NUMBER.sub("", value)


def _allowlisted_fields(fields: dict[str, str], allowed_keys: tuple[str, ...]) -> dict[str, str]:
    return {key: fields[key] for key in allowed_keys if fields.get(key)}
