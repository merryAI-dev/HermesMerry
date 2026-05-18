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


@dataclass(slots=True)
class GoogleSheetReviewQueue:
    service: Any
    spreadsheet_id: str

    def publish_cards(self, *, sheet_tab: str, rows: list[dict[str, object]]) -> int:
        headers = _headers_for_tab(sheet_tab)
        self._ensure_headers(sheet_tab=sheet_tab)
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

    def _ensure_headers(self, *, sheet_tab: str) -> None:
        headers = _headers_for_tab(sheet_tab)
        response = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=_sheet_range(sheet_tab, headers, row="1"),
        ).execute()
        header_rows = response.get("values") or [[]]
        existing = [str(header) for header in header_rows[0]]
        if existing == list(headers):
            return
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=_sheet_range(sheet_tab, headers, row="1"),
            valueInputOption="USER_ENTERED",
            body={"values": [list(headers)]},
        ).execute()


def _headers_for_tab(sheet_tab: str) -> tuple[str, ...]:
    if sheet_tab == "entity_resolution":
        return ENTITY_RESOLUTION_HEADERS
    return REVIEW_QUEUE_HEADERS


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
