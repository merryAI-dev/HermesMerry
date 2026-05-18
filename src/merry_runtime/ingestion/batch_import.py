from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from typing import Any

from merry_runtime.normalization import normalize_company_name
from merry_runtime.pii import redact_pii


REQUIRED_COLUMNS: tuple[str, ...] = (
    "company",
    "brand",
    "representative",
    "homepage",
    "region",
    "industry",
    "channel",
    "evidence",
    "confidence",
    "tags",
    "source_uri",
)
ALLOWED_CHANNELS: set[str] = {
    "hankyung_ceo_interview",
    "thevc_investment_ma",
    "info_mail",
    "external_referral",
    "internal_screening_memo",
}
MAX_CONFLICT_RATE = 0.05


class CandidateBatchValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DuplicateHomepageConflict:
    normalized_company: str
    row_numbers: list[int]
    homepages: list[str]

    def as_dict(self) -> dict[str, object]:
        return {
            "normalized_company": self.normalized_company,
            "row_numbers": self.row_numbers,
            "homepages": self.homepages,
        }


@dataclass(frozen=True, slots=True)
class QualityGateReport:
    total_rows: int
    conflicting_row_count: int
    conflict_rate: float
    passed: bool
    duplicate_conflicts: list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class CandidateBatch:
    row_count: int
    sources: list[dict[str, Any]]
    quality_report: QualityGateReport


def parse_candidate_batch_csv(csv_text: str) -> CandidateBatch:
    reader = csv.DictReader(StringIO(csv_text))
    _validate_columns(reader.fieldnames)

    rows: list[dict[str, str]] = []
    row_numbers: list[int] = []
    for row in reader:
        cleaned = {column: (row.get(column) or "").strip() for column in REQUIRED_COLUMNS}
        channel = cleaned["channel"]
        if channel not in ALLOWED_CHANNELS:
            raise CandidateBatchValidationError(f"unknown discovery channel on row {reader.line_num}: {channel}")
        rows.append(cleaned)
        row_numbers.append(reader.line_num)

    quality_report = _build_quality_report(rows=rows, row_numbers=row_numbers)
    sources = [_source_from_row(row) for row in rows]
    return CandidateBatch(row_count=len(rows), sources=sources, quality_report=quality_report)


def _validate_columns(fieldnames: list[str] | None) -> None:
    if not fieldnames:
        raise CandidateBatchValidationError("candidate batch CSV must include a header row")

    normalized = [field.strip() for field in fieldnames]
    missing = [column for column in REQUIRED_COLUMNS if column not in normalized]
    extra = [column for column in normalized if column not in REQUIRED_COLUMNS]
    if missing:
        raise CandidateBatchValidationError(f"missing required columns: {missing}")
    if extra:
        raise CandidateBatchValidationError(f"unexpected columns: {extra}")


def _source_from_row(row: dict[str, str]) -> dict[str, Any]:
    channel = row["channel"]
    evidence = redact_pii(row["evidence"])
    if channel == "external_referral":
        return {
            "channel": channel,
            "payload": {
                "company": row["company"],
                "brand": row["brand"],
                "representative": row["representative"],
                "homepage": row["homepage"],
                "region": row["region"],
                "industry": row["industry"],
                "signal": "curated_batch",
                "reason": evidence,
                "evidence": evidence,
                "confidence": row["confidence"],
                "tags": _normalize_tags(row["tags"]),
                "source_uri": row["source_uri"],
                "url": row["source_uri"],
            },
        }

    return {"channel": channel, "payload": _text_payload(row=row, evidence=evidence)}


def _text_payload(*, row: dict[str, str], evidence: str) -> str:
    return "\n".join(
        [
            f"Title: Curated candidate: {row['company']}",
            f"Subject: Curated candidate: {row['company']}",
            f"Memo: Curated candidate: {row['company']}",
            f"Company: {row['company']}",
            f"Brand: {row['brand']}",
            f"Representative: {row['representative']}",
            f"Homepage: {row['homepage']}",
            f"Region: {row['region']}",
            f"Industry: {row['industry']}",
            "Signal: curated_batch",
            f"Confidence: {row['confidence']}",
            f"Tags: {_normalize_tags(row['tags'])}",
            f"Evidence: {evidence}",
            f"URL: {row['source_uri']}",
            f"Source_URI: {row['source_uri']}",
            f"From: {row['source_uri']}",
        ]
    )


def _build_quality_report(*, rows: list[dict[str, str]], row_numbers: list[int]) -> QualityGateReport:
    grouped: dict[str, list[tuple[int, str]]] = {}
    for row, row_number in zip(rows, row_numbers, strict=True):
        normalized_company = normalize_company_name(row["company"])
        if not normalized_company:
            continue
        grouped.setdefault(normalized_company, []).append((row_number, _normalize_homepage(row["homepage"])))

    conflicts: list[DuplicateHomepageConflict] = []
    conflicting_rows: set[int] = set()
    for normalized_company in sorted(grouped):
        group = grouped[normalized_company]
        homepages = sorted({homepage for _row_number, homepage in group if homepage})
        if len(homepages) <= 1:
            continue
        row_numbers_for_group = [row_number for row_number, _homepage in group]
        conflicting_rows.update(row_numbers_for_group)
        conflicts.append(
            DuplicateHomepageConflict(
                normalized_company=normalized_company,
                row_numbers=row_numbers_for_group,
                homepages=homepages,
            )
        )

    total_rows = len(rows)
    conflict_rate = (len(conflicting_rows) / total_rows) if total_rows else 0.0
    return QualityGateReport(
        total_rows=total_rows,
        conflicting_row_count=len(conflicting_rows),
        conflict_rate=conflict_rate,
        passed=conflict_rate <= MAX_CONFLICT_RATE,
        duplicate_conflicts=[conflict.as_dict() for conflict in conflicts],
    )


def _normalize_homepage(homepage: str) -> str:
    return homepage.strip().casefold().rstrip("/")


def _normalize_tags(value: str) -> str:
    return ", ".join(tag.strip() for tag in value.replace(";", ",").split(",") if tag.strip())
