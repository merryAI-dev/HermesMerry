from __future__ import annotations

from typing import Protocol


class ObjectStore(Protocol):
    def write_raw_text(self, *, path: str, text: str, content_type: str) -> str: ...


class StructuredStore(Protocol):
    def upsert_rows(self, *, table: str, rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> int: ...

    def query_rows(self, *, sql: str, parameters: dict[str, object]) -> list[dict[str, object]]: ...


class ReviewQueue(Protocol):
    def publish_cards(self, *, sheet_tab: str, rows: list[dict[str, object]]) -> int: ...

    def upsert_cards(self, *, sheet_tab: str, rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> int: ...

    def replace_rows(self, *, sheet_tab: str, headers: tuple[str, ...], rows: list[dict[str, object]]) -> int: ...

    def read_pending_reviews(self, *, sheet_tab: str) -> list[dict[str, str]]: ...


class Notifier(Protocol):
    def send_message(self, *, channel: str, text: str) -> str: ...


class EmailDraftClient(Protocol):
    def create_draft(self, *, to: str, subject: str, body_text: str) -> str: ...


class KVICDataClient(Protocol):
    def fetch_fund_types(self, *, b_type: str = "0", output_format: str = "1") -> dict[str, object]: ...

    def fetch_funds(self, *, fund_type: str = "00", output_format: str = "1") -> dict[str, object]: ...


class WebSearchClient(Protocol):
    def search(self, query: str, *, max_results: int) -> list[dict[str, str]]: ...


class LLMClient(Protocol):
    def complete_json(self, *, system_prompt: str, user_prompt: str, max_tokens: int) -> dict[str, object]: ...
