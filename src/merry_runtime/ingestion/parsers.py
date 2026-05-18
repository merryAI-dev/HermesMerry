from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from merry_runtime.models import MotherEntity, RawSource, Signal
from merry_runtime.normalization import normalize_company_name
from merry_runtime.pii import detect_pii, redact_pii


@dataclass(frozen=True, slots=True)
class ParsedSource:
    raw_source: RawSource
    entity: MotherEntity
    signals: list[Signal]
    raw_text: str


def parse_article(text: str) -> ParsedSource:
    fields = _parse_key_value_text(text)
    return _parsed_from_fields(
        fields=fields,
        raw_text=text,
        source_type="article",
        channel="hankyung_ceo_interview",
        uri=_source_uri(fields, "url"),
        title=fields.get("title", ""),
    )


def parse_email(text: str) -> ParsedSource:
    fields = _parse_key_value_text(text)
    return _parsed_from_fields(
        fields=fields,
        raw_text=text,
        source_type="email",
        channel="info_mail",
        uri=_source_uri(fields, "from"),
        title=fields.get("subject", ""),
    )


def parse_internal_memo(text: str) -> ParsedSource:
    fields = _parse_key_value_text(text)
    return _parsed_from_fields(
        fields=fields,
        raw_text=text,
        source_type="drive_doc",
        channel="internal_screening_memo",
        uri=_source_uri(fields, "homepage"),
        title=fields.get("memo", ""),
    )


def parse_thevc_investment_card(text: str) -> ParsedSource:
    fields = _parse_key_value_text(text)
    return _parsed_from_fields(
        fields=fields,
        raw_text=text,
        source_type="web_listing",
        channel="thevc_investment_ma",
        uri=_source_uri(fields, "url"),
        title=fields.get("title", ""),
    )


def parse_referral_row(row: dict[str, Any]) -> ParsedSource:
    fields = {str(key).casefold(): str(value) for key, value in row.items() if value is not None}
    raw_text = json.dumps(row, ensure_ascii=False, sort_keys=True)
    fields.setdefault("signal", "referral")
    fields.setdefault("evidence", fields.get("reason", "External referral"))
    return _parsed_from_fields(
        fields=fields,
        raw_text=raw_text,
        source_type="sheet_row",
        channel="external_referral",
        uri=_source_uri(fields, "source_uri", default="google-sheet://external-referrals"),
        title=f"Referral: {fields.get('company', '')}",
    )


def _parsed_from_fields(
    *,
    fields: dict[str, str],
    raw_text: str,
    source_type: str,
    channel: str,
    uri: str,
    title: str,
) -> ParsedSource:
    source_id = _stable_id("src", channel, raw_text)
    entity_name = fields.get("company", "").strip()
    entity_id = _stable_id("ent", normalize_company_name(entity_name) or entity_name, fields.get("homepage", ""))
    signal_id = _stable_id("sig", source_id, fields.get("signal", ""), fields.get("evidence", ""))
    evidence = fields.get("evidence", "").strip()
    tags = _parse_tags(fields.get("tags", ""))
    confidence = _parse_confidence(fields.get("confidence", "0.5"))
    contains_pii = bool(detect_pii(raw_text))

    raw_source = RawSource(
        source_id=source_id,
        source_type=source_type,
        channel=channel,
        uri=uri,
        title=title,
        raw_text_path=f"raw/{channel}/{source_id}.txt",
        published_at=fields.get("published") or None,
        checksum=_checksum(raw_text),
        contains_pii=contains_pii,
    )
    entity = MotherEntity(
        entity_id=entity_id,
        name=entity_name,
        normalized_name=normalize_company_name(entity_name),
        region=fields.get("region", ""),
        industry=fields.get("industry", ""),
        homepage=fields.get("homepage") or None,
        representative=fields.get("representative", ""),
        contact_email=fields.get("contact email", "") or fields.get("email", ""),
    )
    signal = Signal(
        signal_id=signal_id,
        entity_id=entity_id,
        signal_type=fields.get("signal", "mention").strip() or "mention",
        evidence_text=redact_pii(evidence),
        source_id=source_id,
        confidence=confidence,
        tags=tags,
    )
    return ParsedSource(raw_source=raw_source, entity=entity, signals=[signal], raw_text=raw_text)


def _parse_key_value_text(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().casefold()] = value.strip()
    return fields


def _parse_tags(value: str) -> tuple[str, ...]:
    return tuple(tag.strip().casefold() for tag in value.split(",") if tag.strip())


def _parse_confidence(value: str) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except ValueError:
        return 0.5


def _source_uri(fields: dict[str, str], fallback_key: str, *, default: str = "") -> str:
    if fields.get("source_uri"):
        return fields["source_uri"]
    if fields.get("source uri"):
        return fields["source uri"]
    if fields.get("url"):
        return fields["url"]
    return fields.get(fallback_key, default)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _checksum(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
