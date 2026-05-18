from __future__ import annotations

import re

from merry_runtime.models import ACProfile


class ACProfileParseError(ValueError):
    pass


_FIELD_ALIASES = {
    "ac id": "ac_id",
    "ac_id": "ac_id",
    "ac name": "ac_name",
    "ac_name": "ac_name",
    "fund purpose": "fund_purpose",
    "fund_purpose": "fund_purpose",
    "recruiting area": "recruiting_area",
    "recruiting_area": "recruiting_area",
    "hypothesis tags": "hypothesis_tags",
    "hypothesis_tags": "hypothesis_tags",
    "impact priorities": "impact_priority",
    "impact priority": "impact_priority",
    "impact_priority": "impact_priority",
    "region preferences": "region_preferences",
    "region_preferences": "region_preferences",
    "industry preferences": "industry_preferences",
    "industry_preferences": "industry_preferences",
    "tech preferences": "tech_preferences",
    "tech_preferences": "tech_preferences",
}
_FIELD_PATTERN = re.compile(r"^\s*(?:[-*]\s*)?(?:#{1,6}\s*)?([A-Za-z_ ]+?)\s*:\s*(.*)$")
_BULLET_PATTERN = re.compile(r"^\s*[-*]\s+(.*)$")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def parse_ac_hypothesis_report(text: str) -> ACProfile:
    fields = _extract_fields(text)

    ac_id = _first_value(fields, "ac_id")
    fund_purpose = _first_value(fields, "fund_purpose")
    hypothesis_tags = _list_values(fields, "hypothesis_tags", normalize_case=True)
    impact_priority = _list_values(fields, "impact_priority")

    if not ac_id:
        raise ACProfileParseError("AC ID must not be empty")
    if not fund_purpose:
        raise ACProfileParseError("Fund Purpose must not be empty")
    if not hypothesis_tags and not impact_priority:
        raise ACProfileParseError("Report must include hypothesis or impact tags")

    return ACProfile(
        ac_id=ac_id,
        ac_name=_first_value(fields, "ac_name") or ac_id,
        fund_purpose=fund_purpose,
        recruiting_area=_first_value(fields, "recruiting_area"),
        hypothesis_tags=hypothesis_tags,
        impact_priority=impact_priority,
        region_preferences=_list_values(fields, "region_preferences"),
        industry_preferences=_list_values(fields, "industry_preferences"),
        tech_preferences=_list_values(fields, "tech_preferences"),
    )


def _extract_fields(text: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    current_key = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        field_match = _FIELD_PATTERN.match(line)
        if field_match:
            key = _FIELD_ALIASES.get(_normalize_key(field_match.group(1)))
            if key:
                current_key = key
                fields.setdefault(key, [])
                value = _clean_value(field_match.group(2))
                if value:
                    fields[key].append(value)
                continue

        bullet_match = _BULLET_PATTERN.match(line)
        if bullet_match and current_key:
            value = _clean_value(bullet_match.group(1))
            if value:
                fields.setdefault(current_key, []).append(value)

    return fields


def _first_value(fields: dict[str, list[str]], key: str) -> str:
    values = fields.get(key) or []
    return _clean_value(values[0]) if values else ""


def _list_values(fields: dict[str, list[str]], key: str, *, normalize_case: bool = False) -> tuple[str, ...]:
    values: list[str] = []
    for raw_value in fields.get(key) or []:
        for value in re.split(r"[,;]", raw_value):
            cleaned = _clean_value(value)
            if normalize_case:
                cleaned = cleaned.casefold()
            if cleaned:
                values.append(cleaned)
    return _dedupe(values)


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return tuple(unique)


def _normalize_key(value: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", value.replace("_", " ")).strip().casefold()


def _clean_value(value: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", value.strip().strip("\"'`")).strip()
