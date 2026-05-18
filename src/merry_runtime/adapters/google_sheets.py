from __future__ import annotations

from dataclasses import dataclass
from typing import Any


REVIEW_QUEUE_HEADERS: tuple[str, ...] = (
    "card_id",
    "entity_id",
    "company",
    "region",
    "industry",
    "total_score",
    "recommended_action",
    "queue_type",
    "priority_probability",
    "rationale",
    "decision",
    "review_memo",
    "reviewer",
    "contact_email",
)

ENTITY_RESOLUTION_HEADERS: tuple[str, ...] = (
    "event_id",
    "candidate_entity_id",
    "matched_entity_id",
    "action",
    "probability",
    "status",
    "rationale",
    "decision",
    "review_memo",
    "reviewer",
)

OPERATOR_CONSOLE_HEADERS: dict[str, tuple[str, ...]] = {
    "Review Queue": (
        "card_id",
        "ac_id",
        "entity_id",
        "company",
        "region",
        "industry",
        "total_score",
        "priority_probability",
        "recommended_action",
        "queue_type",
        "rationale",
        "decision",
        "review_memo",
        "reviewer",
        "owner",
        "next_action",
        "due_date",
        "override_reason",
        "status",
        "contact_email",
    ),
    "Candidate Detail": (
        "entity_id",
        "company",
        "normalized_name",
        "representative",
        "homepage",
        "region",
        "industry",
        "summary",
        "latest_score",
        "priority_probability",
        "queue_type",
        "recommended_action",
        "status",
        "wiki_path",
        "contact_email",
    ),
    "Evidence": (
        "source_id",
        "signal_id",
        "entity_id",
        "source_type",
        "channel",
        "title",
        "url",
        "signal_type",
        "evidence_text",
        "confidence",
        "tags",
        "contains_pii",
        "raw_text_path",
    ),
    "Decision Log": (
        "review_id",
        "card_id",
        "ac_id",
        "entity_id",
        "reviewer",
        "decision",
        "memo",
        "reviewed_at",
        "owner",
        "next_action",
        "due_date",
    ),
    "AC Settings": (
        "ac_id",
        "ac_name",
        "fund_purpose",
        "recruiting_area",
        "hypothesis_tags",
        "impact_priority",
        "region_preferences",
        "industry_preferences",
        "tech_preferences",
        "exclusion_rules",
        "weight_overrides",
        "active",
    ),
    "Exploration Queue": (
        "card_id",
        "ac_id",
        "entity_id",
        "company",
        "uncertainty",
        "exploration_reason",
        "priority_probability",
        "recommended_action",
        "queue_type",
        "rationale",
        "decision",
        "review_memo",
        "reviewer",
        "owner",
        "next_action",
        "due_date",
        "status",
        "contact_email",
    ),
    "Run Log": (
        "run_id",
        "job_name",
        "status",
        "started_at",
        "finished_at",
        "input_count",
        "output_count",
        "error_message",
        "next_action",
    ),
    "Crawl Sources": (
        "url",
        "source_kind",
        "channel",
        "company",
        "region",
        "industry",
        "tags",
        "confidence",
        "status",
        "last_crawled_at",
        "error_message",
    ),
}


@dataclass(slots=True)
class GoogleSheetReviewQueue:
    service: Any
    spreadsheet_id: str

    def publish_cards(self, *, sheet_tab: str, rows: list[dict[str, object]]) -> int:
        headers = self._ensure_headers(sheet_tab=sheet_tab)
        values = [_row_values(row, headers) for row in rows]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=_sheet_range(sheet_tab, headers),
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()
        return len(values)

    def read_pending_reviews(self, *, sheet_tab: str) -> list[dict[str, str]]:
        self._ensure_sheet_tab(sheet_tab=sheet_tab)
        headers = _headers_for_tab(sheet_tab)
        response = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=_sheet_range(sheet_tab, headers),
        ).execute()
        values = response.get("values", [])
        if not values:
            return []
        headers = [str(header) for header in values[0]]
        return [dict(zip(headers, [str(value) for value in row], strict=False)) for row in values[1:]]

    def _ensure_headers(self, *, sheet_tab: str) -> tuple[str, ...]:
        self._ensure_sheet_tab(sheet_tab=sheet_tab)
        headers = _headers_for_tab(sheet_tab)
        response = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{sheet_tab}!1:1",
        ).execute()
        header_rows = response.get("values") or [[]]
        existing = [str(header) for header in header_rows[0]]
        effective_headers = _merge_headers(existing=existing, canonical=list(headers))
        if existing == effective_headers:
            return tuple(effective_headers)
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=_sheet_range(sheet_tab, tuple(effective_headers), row="1"),
            valueInputOption="USER_ENTERED",
            body={"values": [effective_headers]},
        ).execute()
        return tuple(effective_headers)

    def _ensure_sheet_tab(self, *, sheet_tab: str) -> None:
        response = self.service.spreadsheets().get(
            spreadsheetId=self.spreadsheet_id,
            fields="sheets.properties.title",
        ).execute()
        existing_titles = {
            str(sheet.get("properties", {}).get("title", ""))
            for sheet in response.get("sheets", [])
            if isinstance(sheet, dict)
        }
        if sheet_tab in existing_titles:
            return
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": sheet_tab}}}]},
        ).execute()


def _headers_for_tab(sheet_tab: str) -> tuple[str, ...]:
    if sheet_tab in OPERATOR_CONSOLE_HEADERS:
        return OPERATOR_CONSOLE_HEADERS[sheet_tab]
    if sheet_tab == "entity_resolution":
        return ENTITY_RESOLUTION_HEADERS
    return REVIEW_QUEUE_HEADERS


def _merge_headers(*, existing: list[str], canonical: list[str]) -> list[str]:
    if not existing:
        return canonical
    merged = list(existing)
    merged.extend(header for header in canonical if header not in existing)
    return merged


def _sheet_range(sheet_tab: str, headers: tuple[str, ...], *, row: str = "") -> str:
    last_column = _column_name(len(headers))
    return f"{sheet_tab}!A{row}:{last_column}{row}"


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _row_values(row: dict[str, object], headers: tuple[str, ...]) -> list[object]:
    return [_safe_cell_value(row.get(key, "")) for key in headers]


def _safe_cell_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value
