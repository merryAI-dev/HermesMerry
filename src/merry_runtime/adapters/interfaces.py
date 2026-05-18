from __future__ import annotations

from typing import Protocol


class ObjectStore(Protocol):
    def write_raw_text(self, *, path: str, text: str, content_type: str) -> str: ...


class StructuredStore(Protocol):
    def upsert_rows(self, *, table: str, rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> int: ...

    def query_rows(self, *, sql: str, parameters: dict[str, object]) -> list[dict[str, object]]: ...


class ReviewQueue(Protocol):
    def publish_cards(self, *, sheet_tab: str, rows: list[dict[str, object]]) -> int: ...

    def read_pending_reviews(self, *, sheet_tab: str) -> list[dict[str, str]]: ...


class Notifier(Protocol):
    def send_message(self, *, channel: str, text: str) -> str: ...
