from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GoogleSheetReviewQueue:
    service: Any
    spreadsheet_id: str

    def publish_cards(self, *, sheet_tab: str, rows: list[dict[str, object]]) -> int:
        values = [_row_values(row) for row in rows]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"{sheet_tab}!A:K",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()
        return len(values)

    def read_pending_reviews(self, *, sheet_tab: str) -> list[dict[str, str]]:
        response = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{sheet_tab}!A:K",
        ).execute()
        values = response.get("values", [])
        if not values:
            return []
        headers = [str(header) for header in values[0]]
        return [dict(zip(headers, [str(value) for value in row], strict=False)) for row in values[1:]]


def _row_values(row: dict[str, object]) -> list[object]:
    return [row[key] for key in row.keys()]
