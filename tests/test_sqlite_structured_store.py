import sqlite3

import pytest

from merry_runtime.adapters.sqlite_store import SQLiteStructuredStore
from merry_runtime.schema import BIGQUERY_TABLES


def test_sqlite_store_initializes_tables_from_structured_schema(tmp_path) -> None:
    store = SQLiteStructuredStore(db_path=tmp_path / "mother.db")

    with sqlite3.connect(store.db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table' order by name"
            ).fetchall()
        }

    assert set(BIGQUERY_TABLES).issubset(tables)


def test_sqlite_store_adds_new_schema_columns_to_existing_tables(tmp_path) -> None:
    db_path = tmp_path / "mother.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("create table mother_entities (entity_id TEXT, name TEXT)")

    store = SQLiteStructuredStore(db_path=db_path)

    store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": "ent_1",
                "entity_type": "startup",
                "name": "AIO",
                "normalized_name": "aio",
                "contact_email": "hello@the-aio.com",
                "first_seen_at": "2026-05-18T00:00:00+00:00",
                "last_seen_at": "2026-05-18T00:00:00+00:00",
            }
        ],
        key_fields=("entity_id",),
    )

    rows = store.query_rows(
        sql="select * from mother_entities where entity_id = @entity_id",
        parameters={"entity_id": "ent_1"},
    )

    assert rows[0]["contact_email"] == "hello@the-aio.com"


def test_sqlite_store_upserts_by_key_fields_and_round_trips_json_values(tmp_path) -> None:
    store = SQLiteStructuredStore(db_path=tmp_path / "mother.db")

    inserted = store.upsert_rows(
        table="signals",
        rows=[
            {
                "signal_id": "sig_1",
                "entity_id": "ent_1",
                "signal_type": "impact",
                "evidence_text": "Supports local care workers.",
                "source_id": "src_1",
                "confidence": 0.8,
                "tags": ["care", "local"],
                "detected_at": "2026-05-18T00:00:00+00:00",
            }
        ],
        key_fields=("signal_id",),
    )
    replaced = store.upsert_rows(
        table="signals",
        rows=[
            {
                "signal_id": "sig_1",
                "entity_id": "ent_1",
                "signal_type": "impact",
                "evidence_text": "Updated evidence.",
                "source_id": "src_1",
                "confidence": 0.95,
                "tags": ["care", "updated"],
                "detected_at": "2026-05-18T00:01:00+00:00",
            }
        ],
        key_fields=("signal_id",),
    )

    rows = store.query_rows(
        sql="select * from signals where entity_id = @entity_id",
        parameters={"entity_id": "ent_1"},
    )

    assert inserted == 1
    assert replaced == 1
    assert rows == [
        {
            "signal_id": "sig_1",
            "entity_id": "ent_1",
            "signal_type": "impact",
            "evidence_text": "Updated evidence.",
            "source_id": "src_1",
            "confidence": 0.95,
            "tags": ["care", "updated"],
            "detected_at": "2026-05-18T00:01:00+00:00",
        }
    ]


def test_sqlite_store_rejects_unknown_tables_and_unsafe_queries(tmp_path) -> None:
    store = SQLiteStructuredStore(db_path=tmp_path / "mother.db")

    with pytest.raises(ValueError, match="Unknown structured table"):
        store.upsert_rows(table="missing", rows=[{"id": "1"}], key_fields=("id",))

    with pytest.raises(ValueError, match="Only SELECT queries are supported"):
        store.query_rows(sql="delete from signals", parameters={})
