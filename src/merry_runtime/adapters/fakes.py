from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FakeObjectStore:
    bucket: str
    objects: dict[str, dict[str, str]] = field(default_factory=dict)

    def write_raw_text(self, *, path: str, text: str, content_type: str) -> str:
        normalized_path = path.lstrip("/")
        self.objects[normalized_path] = {"text": text, "content_type": content_type}
        return f"gs://{self.bucket}/{normalized_path}"


@dataclass(slots=True)
class FakeStructuredStore:
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))

    def upsert_rows(self, *, table: str, rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> int:
        existing_rows = self.tables[table]
        for row in rows:
            row_copy = dict(row)
            match_index = self._find_index(existing_rows, row_copy, key_fields)
            if match_index is None:
                existing_rows.append(row_copy)
            else:
                existing_rows[match_index] = row_copy
        return len(rows)

    def query_rows(self, *, sql: str, parameters: dict[str, object]) -> list[dict[str, Any]]:
        table = _table_from_sql(sql)
        rows = self.tables.get(table, [])
        if not parameters:
            return deepcopy(rows)
        return [deepcopy(row) for row in rows if all(row.get(key) == value for key, value in parameters.items())]

    @classmethod
    def seed_climate_candidate(cls) -> FakeStructuredStore:
        store = cls()
        store.upsert_rows(
            table="mother_entities",
            rows=[
                {
                    "entity_id": "ent_climate",
                    "name": "CareFarm Carbon",
                    "region": "Jeonbuk",
                    "industry": "AgriTech",
                    "homepage": "https://carefarm.example",
                    "contact_email": "hello@carefarm.example",
                }
            ],
            key_fields=("entity_id",),
        )
        store.upsert_rows(
            table="signals",
            rows=[
                {
                    "signal_id": "sig_impact",
                    "entity_id": "ent_climate",
                    "signal_type": "impact",
                    "evidence_text": "Reduces carbon emissions for small farms with verified pilots.",
                    "source_id": "src_article",
                    "confidence": 0.92,
                    "tags": ["climate", "carbon", "rural", "impact"],
                },
                {
                    "signal_id": "sig_growth",
                    "entity_id": "ent_climate",
                    "signal_type": "traction",
                    "evidence_text": "Paid pilots with three agricultural cooperatives.",
                    "source_id": "src_mail",
                    "confidence": 0.84,
                    "tags": ["traction", "pilot", "agritech"],
                },
            ],
            key_fields=("signal_id",),
        )
        store.upsert_rows(
            table="ac_profiles",
            rows=[
                {
                    "ac_id": "ac_climate",
                    "ac_name": "Climate Impact AC",
                    "fund_purpose": "climate impact fund",
                    "recruiting_area": "Jeonbuk",
                    "hypothesis_tags": ["climate", "agritech"],
                    "impact_priority": ["carbon", "rural"],
                    "region_preferences": ["Jeonbuk"],
                    "industry_preferences": ["AgriTech"],
                    "tech_preferences": ["AI"],
                }
            ],
            key_fields=("ac_id",),
        )
        return store

    @classmethod
    def seed_candidate_card(cls) -> FakeStructuredStore:
        store = cls()
        store.upsert_rows(
            table="candidate_cards",
            rows=[
                {
                    "card_id": "card_1",
                    "ac_id": "ac_climate",
                    "entity_id": "ent_climate",
                    "summary": "Strong climate impact candidate.",
                    "recommended_action": "advance",
                    "queue_type": "priority",
                    "status": "new",
                }
            ],
            key_fields=("card_id",),
        )
        return store

    @staticmethod
    def _find_index(rows: list[dict[str, Any]], candidate: dict[str, Any], key_fields: tuple[str, ...]) -> int | None:
        for index, row in enumerate(rows):
            if all(row.get(field) == candidate.get(field) for field in key_fields):
                return index
        return None


@dataclass(slots=True)
class FakeReviewQueue:
    published: dict[str, list[dict[str, object]]] = field(default_factory=lambda: defaultdict(list))
    reviews: dict[str, list[dict[str, str]]] = field(default_factory=lambda: defaultdict(list))

    def publish_cards(self, *, sheet_tab: str, rows: list[dict[str, object]]) -> int:
        self.published[sheet_tab].extend(dict(row) for row in rows)
        return len(rows)

    def upsert_cards(self, *, sheet_tab: str, rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> int:
        existing_rows = self.published[sheet_tab]
        for row in rows:
            row_copy = dict(row)
            match_index = FakeStructuredStore._find_index(existing_rows, row_copy, key_fields)
            if match_index is None:
                existing_rows.append(row_copy)
            else:
                existing_rows[match_index] = row_copy
        return len(rows)

    def read_pending_reviews(self, *, sheet_tab: str) -> list[dict[str, str]]:
        rows = [dict(row) for row in self.reviews.get(sheet_tab, [])]
        rows.extend({key: str(value) for key, value in row.items()} for row in self.published.get(sheet_tab, []))
        return rows

    def seed_reviews(self, sheet_tab: str, rows: list[dict[str, str]]) -> None:
        self.reviews[sheet_tab].extend(dict(row) for row in rows)


@dataclass(slots=True)
class FakeNotifier:
    messages: list[dict[str, str]] = field(default_factory=list)

    def send_message(self, *, channel: str, text: str) -> str:
        message_id = f"msg_{len(self.messages) + 1:06d}"
        self.messages.append({"message_id": message_id, "channel": channel, "text": text})
        return message_id


def _table_from_sql(sql: str) -> str:
    tokens = sql.replace("\n", " ").split()
    lowered = [token.casefold() for token in tokens]
    if "from" not in lowered:
        raise ValueError(f"Cannot infer table from SQL: {sql}")
    return tokens[lowered.index("from") + 1].strip("`")
