from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


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
        "collected_at",
        "company",
        "normalized_name",
        "representative",
        "homepage",
        "contact_email",
        "region",
        "industry",
        "summary",
        "business_model",
        "investment_round",
        "investment_amount",
        "investor",
        "latest_score",
        "priority_probability",
        "queue_type",
        "recommended_action",
        "status",
        "wiki_path",
        "sminfo_status",
        "sminfo_company",
        "sminfo_latest_financial_year",
        "sminfo_revenue_krw_thousand",
        "sminfo_operating_income_krw_thousand",
        "sminfo_net_income_krw_thousand",
        "sminfo_total_assets_krw_thousand",
        "sminfo_shareholder_composition",
        "sminfo_largest_shareholder",
        "sminfo_largest_shareholder_ratio_pct",
        "sminfo_error_message",
        "sminfo_profile_url",
        "sminfo_collected_at",
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
    "Portfolio News": (
        "collected_at",
        "company",
        "title",
        "summary",
        "url",
        "published_at",
        "source",
        "channel",
        "matched_companies",
        "notified_at",
        "status",
    ),
    "SMINFO Enrichment": (
        "collected_at",
        "requested_company",
        "match_status",
        "matched_company",
        "representative",
        "company_type",
        "established_at",
        "road_address",
        "homepage",
        "main_products",
        "standard_industry",
        "info_updated_at",
        "latest_financial_year",
        "revenue_krw_thousand",
        "operating_income_krw_thousand",
        "net_income_krw_thousand",
        "total_assets_krw_thousand",
        "shareholder_composition",
        "largest_shareholder",
        "largest_shareholder_ratio_pct",
        "shareholder_count",
        "sminfo_url",
        "error_message",
    ),
    "SMINFO Queue": (
        "task_id",
        "company",
        "status",
        "priority",
        "attempt_count",
        "next_run_at",
        "locked_by",
        "last_error",
        "last_profile_id",
        "source_url",
        "updated_at",
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
OPERATOR_CONSOLE_LABELS: dict[str, dict[str, str]] = {
    "Candidate Detail": {
        "collected_at": "수집시각",
        "company": "기업명",
        "normalized_name": "정규화명",
        "representative": "대표자",
        "homepage": "홈페이지",
        "contact_email": "연락처 이메일",
        "region": "지역",
        "industry": "산업",
        "summary": "요약",
        "business_model": "비즈니스모델",
        "investment_round": "투자 단계",
        "investment_amount": "투자 금액",
        "investor": "투자자",
        "latest_score": "최근 점수",
        "priority_probability": "우선검토 확률",
        "queue_type": "큐 유형",
        "recommended_action": "추천 액션",
        "status": "상태",
        "wiki_path": "위키 경로",
        "sminfo_status": "중기현황 상태",
        "sminfo_company": "중기현황 기업명",
        "sminfo_latest_financial_year": "최근 결산연도",
        "sminfo_revenue_krw_thousand": "매출액(천원)",
        "sminfo_operating_income_krw_thousand": "영업이익(천원)",
        "sminfo_net_income_krw_thousand": "당기순이익(천원)",
        "sminfo_total_assets_krw_thousand": "총자산(천원)",
        "sminfo_shareholder_composition": "주주 구성",
        "sminfo_largest_shareholder": "최대주주",
        "sminfo_largest_shareholder_ratio_pct": "최대주주 지분율(%)",
        "sminfo_error_message": "중기현황 오류",
        "sminfo_profile_url": "중기현황 URL",
        "sminfo_collected_at": "중기현황 수집시각",
    },
    "SMINFO Enrichment": {
        "collected_at": "수집시각",
        "requested_company": "요청 기업명",
        "match_status": "매칭 상태",
        "matched_company": "매칭 기업명",
        "representative": "대표자",
        "company_type": "기업형태",
        "established_at": "설립일",
        "road_address": "도로명주소",
        "homepage": "홈페이지",
        "main_products": "주생산품",
        "standard_industry": "표준산업",
        "info_updated_at": "정보수정일자",
        "latest_financial_year": "최근 결산연도",
        "revenue_krw_thousand": "매출액(천원)",
        "operating_income_krw_thousand": "영업이익(천원)",
        "net_income_krw_thousand": "당기순이익(천원)",
        "total_assets_krw_thousand": "총자산(천원)",
        "shareholder_composition": "주주 구성",
        "largest_shareholder": "최대주주",
        "largest_shareholder_ratio_pct": "최대주주 지분율(%)",
        "shareholder_count": "주주 수",
        "sminfo_url": "중기현황 URL",
        "error_message": "오류",
    },
    "SMINFO Queue": {
        "task_id": "작업 ID",
        "company": "기업명",
        "status": "상태",
        "priority": "우선순위",
        "attempt_count": "시도 횟수",
        "next_run_at": "다음 실행시각",
        "locked_by": "처리 에이전트",
        "last_error": "최근 오류",
        "last_profile_id": "최근 프로필 ID",
        "source_url": "출처 URL",
        "updated_at": "수정시각",
    },
}
SHEET_OWNED_UPDATE_FIELDS: dict[str, set[str]] = {
    "Candidate Detail": {"latest_score", "priority_probability", "status"},
}
KNOWN_BAD_EMAIL_DOMAINS = {"thevc.kr", "www.thevc.kr"}
KNOWN_BAD_HOMEPAGE_DOMAINS = {
    "thevc.kr",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
}
SIMPLE_SHEET_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
REPLACE_ROWS_BATCH_SIZE = 500
LOSSLESS_REPLACE_TABS = {"SQLite Backup", "Wiki Backup", "Backup Manifest"}


@dataclass(slots=True)
class GoogleSheetReviewQueue:
    service: Any
    spreadsheet_id: str

    def publish_cards(self, *, sheet_tab: str, rows: list[dict[str, object]]) -> int:
        headers = self._ensure_headers(sheet_tab=sheet_tab)
        return self._append_rows(sheet_tab=sheet_tab, headers=headers, rows=rows)

    def _append_rows(self, *, sheet_tab: str, headers: tuple[str, ...], rows: list[dict[str, object]]) -> int:
        values = [_row_values(row, headers) for row in rows]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=_sheet_range(sheet_tab, headers),
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()
        return len(values)

    def upsert_cards(self, *, sheet_tab: str, rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> int:
        if not rows:
            return 0
        deduped_rows = _dedupe_rows_by_key(rows=rows, key_fields=key_fields)
        header_state = self._ensure_headers_state(sheet_tab=sheet_tab)
        headers = header_state.headers
        existing_response = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=_sheet_range(sheet_tab, headers),
        ).execute()
        existing_values = existing_response.get("values", [])
        existing_row_count = len(existing_values)
        preamble = _sheet_preamble(sheet_tab=sheet_tab, headers=headers, existing_values=existing_values)
        rewrite_projection = header_state.replaced_schema or _has_legacy_candidate_detail_rows(
            sheet_tab=sheet_tab,
            headers=headers,
            existing_values=existing_values,
        )
        if rewrite_projection:
            existing_values = [list(row) for row in preamble]
        if len(key_fields) > 1 or rewrite_projection:
            compacted_rows = _compact_sheet_rows(
                sheet_tab=sheet_tab,
                headers=headers,
                existing_values=existing_values,
                incoming_rows=deduped_rows,
                key_fields=key_fields,
            )
            rewritten_values = [*preamble, *[_row_values(row, headers) for row in compacted_rows]]
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=_sheet_range_rows(sheet_tab, headers, start_row=1, end_row=len(rewritten_values)),
                valueInputOption="RAW",
                body={"values": rewritten_values},
            ).execute()
            if existing_row_count > len(rewritten_values):
                self.service.spreadsheets().values().clear(
                    spreadsheetId=self.spreadsheet_id,
                    range=_sheet_range_rows(
                        sheet_tab,
                        headers,
                        start_row=len(rewritten_values) + 1,
                        end_row=existing_row_count,
                    ),
                    body={},
                ).execute()
            return len(deduped_rows)

        existing_index = _existing_row_index(
            sheet_tab=sheet_tab,
            existing_values=existing_values,
            headers=headers,
            key_fields=key_fields,
        )

        append_rows: list[dict[str, object]] = []
        for row in deduped_rows:
            key = _row_key(row, key_fields=key_fields)
            existing = existing_index.get(key) if key else None
            row_number = existing[0] if existing else None
            if row_number is None:
                append_rows.append(row)
                continue
            merged_row = _merge_existing_row(sheet_tab=sheet_tab, headers=headers, existing=existing[1], incoming=row)
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=_sheet_range(sheet_tab, headers, row=str(row_number)),
                valueInputOption="RAW",
                body={"values": [_row_values(merged_row, headers)]},
            ).execute()

        if append_rows:
            self._append_rows(sheet_tab=sheet_tab, headers=headers, rows=append_rows)
        return len(deduped_rows)

    def replace_rows(self, *, sheet_tab: str, headers: tuple[str, ...], rows: list[dict[str, object]]) -> int:
        if not headers:
            raise ValueError("replace_rows requires at least one header")
        self._ensure_sheet_tab(sheet_tab=sheet_tab)
        existing_response = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=_sheet_range(sheet_tab, headers),
        ).execute()
        existing_values = existing_response.get("values", [])
        escape_formula_cells = sheet_tab not in LOSSLESS_REPLACE_TABS
        rewritten_values = [
            list(headers),
            *[_row_values(row, headers, escape_formula_cells=escape_formula_cells) for row in rows],
        ]
        for start_index in range(0, len(rewritten_values), REPLACE_ROWS_BATCH_SIZE):
            batch = rewritten_values[start_index : start_index + REPLACE_ROWS_BATCH_SIZE]
            start_row = start_index + 1
            end_row = start_row + len(batch) - 1
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=_sheet_range_rows(sheet_tab, headers, start_row=start_row, end_row=end_row),
                valueInputOption="RAW",
                body={"values": batch},
            ).execute()
        if len(existing_values) > len(rewritten_values):
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=_sheet_range_rows(
                    sheet_tab,
                    headers,
                    start_row=len(rewritten_values) + 1,
                    end_row=len(existing_values),
                ),
                body={},
            ).execute()
        return len(rows)

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
        return [
            dict(zip(headers, [str(value) for value in row], strict=False))
            for row in _data_value_rows(sheet_tab=sheet_tab, headers=tuple(headers), existing_values=values)
        ]

    def _ensure_headers(self, *, sheet_tab: str) -> tuple[str, ...]:
        return self._ensure_headers_state(sheet_tab=sheet_tab).headers

    def _ensure_headers_state(self, *, sheet_tab: str) -> "HeaderState":
        self._ensure_sheet_tab(sheet_tab=sheet_tab)
        headers = _headers_for_tab(sheet_tab)
        response = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{_sheet_name(sheet_tab)}!1:2",
        ).execute()
        header_rows = response.get("values") or [[]]
        existing = [str(header) for header in header_rows[0]]
        effective_headers = _effective_headers(sheet_tab=sheet_tab, existing=existing, canonical=list(headers))
        replaced_schema = bool(existing) and _replaces_candidate_detail_schema(sheet_tab=sheet_tab, existing=existing)
        if existing == effective_headers:
            return HeaderState(headers=tuple(effective_headers), previous_headers=tuple(existing), replaced_schema=False)
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=_sheet_range(sheet_tab, tuple(effective_headers), row="1"),
            valueInputOption="USER_ENTERED",
            body={"values": [effective_headers]},
        ).execute()
        return HeaderState(headers=tuple(effective_headers), previous_headers=tuple(existing), replaced_schema=replaced_schema)

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


@dataclass(frozen=True, slots=True)
class HeaderState:
    headers: tuple[str, ...]
    previous_headers: tuple[str, ...]
    replaced_schema: bool


def _headers_for_tab(sheet_tab: str) -> tuple[str, ...]:
    if sheet_tab in OPERATOR_CONSOLE_HEADERS:
        return OPERATOR_CONSOLE_HEADERS[sheet_tab]
    if sheet_tab == "entity_resolution":
        return ENTITY_RESOLUTION_HEADERS
    return REVIEW_QUEUE_HEADERS


def _effective_headers(*, sheet_tab: str, existing: list[str], canonical: list[str]) -> list[str]:
    if _replaces_candidate_detail_schema(sheet_tab=sheet_tab, existing=existing):
        return canonical + [header for header in existing if header and header not in canonical and header != "entity_id"]
    return _merge_headers(existing=existing, canonical=canonical)


def _replaces_candidate_detail_schema(*, sheet_tab: str, existing: list[str]) -> bool:
    return sheet_tab == "Candidate Detail" and "entity_id" in existing


def _merge_headers(*, existing: list[str], canonical: list[str]) -> list[str]:
    if not existing:
        return canonical
    merged = list(existing)
    merged.extend(header for header in canonical if header not in existing)
    return merged


def _sheet_range(sheet_tab: str, headers: tuple[str, ...], *, row: str = "") -> str:
    last_column = _column_name(len(headers))
    return f"{_sheet_name(sheet_tab)}!A{row}:{last_column}{row}"


def _sheet_range_rows(sheet_tab: str, headers: tuple[str, ...], *, start_row: int, end_row: int) -> str:
    last_column = _column_name(len(headers))
    return f"{_sheet_name(sheet_tab)}!A{start_row}:{last_column}{end_row}"


def _sheet_name(sheet_tab: str) -> str:
    if SIMPLE_SHEET_NAME.fullmatch(sheet_tab):
        return sheet_tab
    escaped = sheet_tab.replace("'", "''")
    return f"'{escaped}'"


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _row_values(row: dict[str, object], headers: tuple[str, ...], *, escape_formula_cells: bool = True) -> list[object]:
    values = [row.get(key, "") for key in headers]
    if not escape_formula_cells:
        return values
    return [_safe_cell_value(value) for value in values]


def _sheet_preamble(
    *,
    sheet_tab: str,
    headers: tuple[str, ...],
    existing_values: list[list[object]],
) -> list[list[object]]:
    preamble: list[list[object]] = [list(headers)]
    label_row = _existing_display_label_row(sheet_tab=sheet_tab, headers=headers, existing_values=existing_values)
    if label_row is not None:
        preamble.append(label_row)
    return preamble


def _data_value_rows(
    *,
    sheet_tab: str,
    headers: tuple[str, ...],
    existing_values: list[list[object]],
) -> list[list[object]]:
    data_rows: list[list[object]] = []
    for values in existing_values[1:]:
        if _is_display_label_row(sheet_tab=sheet_tab, headers=headers, values=values):
            continue
        data_rows.append(values)
    return data_rows


def _existing_display_label_row(
    *,
    sheet_tab: str,
    headers: tuple[str, ...],
    existing_values: list[list[object]],
) -> list[object] | None:
    if len(existing_values) < 2:
        return None
    values = existing_values[1]
    if not _is_display_label_row(sheet_tab=sheet_tab, headers=headers, values=values):
        return None
    return _effective_display_label_row(sheet_tab=sheet_tab, headers=headers, existing=values)


def _is_display_label_row(*, sheet_tab: str, headers: tuple[str, ...], values: list[object]) -> bool:
    expected = _display_label_row(sheet_tab=sheet_tab, headers=headers)
    if expected is None:
        return False
    matches = 0
    for index, value in enumerate(values):
        if index >= len(expected):
            break
        if str(value or "").strip() and str(value or "").strip() == expected[index]:
            matches += 1
    return matches > 0


def _effective_display_label_row(
    *,
    sheet_tab: str,
    headers: tuple[str, ...],
    existing: list[object],
) -> list[object]:
    expected = _display_label_row(sheet_tab=sheet_tab, headers=headers) or [""] * len(headers)
    effective: list[object] = []
    for index, fallback in enumerate(expected):
        value = existing[index] if index < len(existing) else ""
        effective.append(fallback if fallback else value)
    return effective


def _display_label_row(*, sheet_tab: str, headers: tuple[str, ...]) -> list[str] | None:
    labels = OPERATOR_CONSOLE_LABELS.get(sheet_tab)
    if labels is None:
        return None
    return [labels.get(header, "") for header in headers]


def _has_legacy_candidate_detail_rows(
    *,
    sheet_tab: str,
    headers: tuple[str, ...],
    existing_values: list[list[object]],
) -> bool:
    if sheet_tab != "Candidate Detail" or not existing_values:
        return False
    for values in _data_value_rows(sheet_tab=sheet_tab, headers=headers, existing_values=existing_values):
        row = dict(zip(headers, values, strict=False))
        if _is_blank(row.get("company", "")):
            continue
        summary = str(row.get("summary") or "").strip()
        if _is_blank(row.get("collected_at", "")):
            return True
        if summary and not summary.startswith("공개 카드 -> "):
            return True
    return False


def _existing_row_index(
    *,
    sheet_tab: str,
    existing_values: list[list[object]],
    headers: tuple[str, ...],
    key_fields: tuple[str, ...],
) -> dict[tuple[str, str], tuple[int, dict[str, object]]]:
    if not existing_values:
        return {}
    row_index: dict[tuple[str, str], tuple[int, dict[str, object]]] = {}
    for sheet_row_number, values in enumerate(existing_values[1:], start=2):
        if _is_display_label_row(sheet_tab=sheet_tab, headers=headers, values=values):
            continue
        row = dict(zip(headers, values, strict=False))
        key = _row_key(row, key_fields=key_fields)
        if key and key not in row_index:
            row_index[key] = (sheet_row_number, row)
    return row_index


def _dedupe_rows_by_key(
    *,
    rows: list[dict[str, object]],
    key_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    order: list[tuple[str, str]] = []
    merged_rows: dict[tuple[str, str], dict[str, object]] = {}
    keyless_rows: list[dict[str, object]] = []
    for row in rows:
        key = _row_key(row, key_fields=key_fields)
        if key is None:
            keyless_rows.append(dict(row))
            continue
        if key not in merged_rows:
            order.append(key)
            merged_rows[key] = dict(row)
            continue
        merged_rows[key] = _merge_generated_rows(existing=merged_rows[key], incoming=row)
    return [merged_rows[key] for key in order] + keyless_rows


def _compact_sheet_rows(
    *,
    sheet_tab: str,
    headers: tuple[str, ...],
    existing_values: list[list[object]],
    incoming_rows: list[dict[str, object]],
    key_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    compacted: list[dict[str, object]] = []
    key_to_index: dict[tuple[str, str], int] = {}

    for values in _data_value_rows(sheet_tab=sheet_tab, headers=headers, existing_values=existing_values):
        row = _clean_known_bad_cells(dict(zip(headers, values, strict=False)))
        key = _first_existing_key(row=row, key_fields=key_fields, key_to_index=key_to_index)
        if key is None:
            _register_compacted_row(compacted=compacted, key_to_index=key_to_index, row=row, key_fields=key_fields)
            continue
        index = key_to_index[key]
        compacted[index] = _merge_sheet_duplicate(headers=headers, existing=compacted[index], incoming=row)
        _register_row_keys(key_to_index=key_to_index, row=compacted[index], key_fields=key_fields, index=index)

    for incoming in incoming_rows:
        key = _first_existing_key(row=incoming, key_fields=key_fields, key_to_index=key_to_index)
        if key is None:
            row = {header: incoming.get(header, "") for header in headers}
            _register_compacted_row(compacted=compacted, key_to_index=key_to_index, row=row, key_fields=key_fields)
            continue
        index = key_to_index[key]
        compacted[index] = _merge_existing_row(
            sheet_tab=sheet_tab,
            headers=headers,
            existing=compacted[index],
            incoming=incoming,
        )
        _register_row_keys(key_to_index=key_to_index, row=compacted[index], key_fields=key_fields, index=index)

    return compacted


def _register_compacted_row(
    *,
    compacted: list[dict[str, object]],
    key_to_index: dict[tuple[str, str], int],
    row: dict[str, object],
    key_fields: tuple[str, ...],
) -> None:
    index = len(compacted)
    compacted.append(row)
    _register_row_keys(key_to_index=key_to_index, row=row, key_fields=key_fields, index=index)


def _register_row_keys(
    *,
    key_to_index: dict[tuple[str, str], int],
    row: dict[str, object],
    key_fields: tuple[str, ...],
    index: int,
) -> None:
    for key in _row_keys(row, key_fields=key_fields):
        key_to_index[key] = index


def _first_existing_key(
    *,
    row: dict[str, object],
    key_fields: tuple[str, ...],
    key_to_index: dict[tuple[str, str], int],
) -> tuple[str, str] | None:
    for key in _row_keys(row, key_fields=key_fields):
        if key in key_to_index:
            return key
    return None


def _merge_sheet_duplicate(
    *,
    headers: tuple[str, ...],
    existing: dict[str, object],
    incoming: dict[str, object],
) -> dict[str, object]:
    merged = {header: existing.get(header, "") for header in headers}
    for field in headers:
        value = incoming.get(field, "")
        if _should_clear_known_bad_value(field=field, existing=merged.get(field, "")):
            merged[field] = ""
        if _is_blank(merged.get(field, "")) and not _is_blank(value):
            if _should_clear_known_bad_value(field=field, existing=value):
                continue
            merged[field] = value
    return merged


def _clean_known_bad_cells(row: dict[str, object]) -> dict[str, object]:
    cleaned = dict(row)
    for field, value in row.items():
        if _should_clear_known_bad_value(field=field, existing=value):
            cleaned[field] = ""
    return cleaned


def _merge_generated_rows(*, existing: dict[str, object], incoming: dict[str, object]) -> dict[str, object]:
    merged = dict(existing)
    for field, value in incoming.items():
        if _is_blank(value) and not _should_clear_known_bad_value(field=field, existing=merged.get(field, "")):
            continue
        merged[field] = value
    return merged


def _merge_existing_row(
    *,
    sheet_tab: str,
    headers: tuple[str, ...],
    existing: dict[str, object],
    incoming: dict[str, object],
) -> dict[str, object]:
    merged = {header: existing.get(header, "") for header in headers}
    protected_fields = SHEET_OWNED_UPDATE_FIELDS.get(sheet_tab, set())
    for field, value in incoming.items():
        if field not in merged:
            continue
        existing_value = merged.get(field, "")
        if field in protected_fields and not _is_blank(existing_value):
            continue
        if _is_blank(value) and not _should_clear_known_bad_value(field=field, existing=existing_value):
            continue
        merged[field] = value
    return merged


def _row_key(row: dict[str, object], *, key_fields: tuple[str, ...]) -> tuple[str, str] | None:
    keys = _row_keys(row, key_fields=key_fields)
    return keys[0] if keys else None


def _row_keys(row: dict[str, object], *, key_fields: tuple[str, ...]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    for field in key_fields:
        value = str(row.get(field) or "").strip()
        if value:
            keys.append((field, value.casefold()))
    return keys


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _should_clear_known_bad_value(*, field: str, existing: object) -> bool:
    existing_value = str(existing or "").strip()
    if not existing_value:
        return False
    if field == "contact_email":
        domain = existing_value.rsplit("@", 1)[-1].casefold()
        return domain in KNOWN_BAD_EMAIL_DOMAINS
    if field == "homepage":
        return not _looks_like_valid_homepage(existing_value)
    return False


def _looks_like_valid_homepage(value: str) -> bool:
    parsed = urlparse(value)
    hostname = (parsed.netloc or parsed.path.split("/", 1)[0]).casefold()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    if "." not in hostname:
        return False
    return not any(hostname == domain or hostname.endswith(f".{domain}") for domain in KNOWN_BAD_HOMEPAGE_DOMAINS)


def _safe_cell_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value
