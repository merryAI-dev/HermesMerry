from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from merry_runtime.schema import BIGQUERY_TABLES


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FROM_TABLE = re.compile(r"\bfrom\s+`?([A-Za-z0-9_.-]+)`?", re.IGNORECASE)
_PARAMETER = re.compile(r"@([A-Za-z_][A-Za-z0-9_]*)")


class SQLiteStructuredStore:
    def __init__(self, *, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def upsert_rows(self, *, table: str, rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> int:
        if not rows:
            return 0
        self._validate_table(table)
        self._validate_fields(table, key_fields)

        field_names = tuple(field["name"] for field in BIGQUERY_TABLES[table])
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            self._ensure_unique_index(connection=connection, table=table, key_fields=key_fields)
            for row in rows:
                self._validate_fields(table, tuple(row.keys()))
                stored_row = {field: self._serialize_value(table=table, field=field, value=row.get(field)) for field in field_names}
                placeholders = ", ".join(f":{field}" for field in field_names)
                update_fields = tuple(field for field in field_names if field not in key_fields)
                update_clause = ", ".join(f"{field}=excluded.{field}" for field in update_fields)
                conflict_clause = ", ".join(key_fields)
                connection.execute(
                    f"insert into {table} ({', '.join(field_names)}) values ({placeholders}) "
                    f"on conflict ({conflict_clause}) do update set {update_clause}",
                    stored_row,
                )
        return len(rows)

    def query_rows(self, *, sql: str, parameters: dict[str, object]) -> list[dict[str, object]]:
        if not sql.lstrip().lower().startswith("select"):
            raise ValueError("Only SELECT queries are supported by SQLiteStructuredStore")
        table = self._table_from_sql(sql)
        self._validate_table(table)
        translated_sql = _PARAMETER.sub(r":\1", sql)
        translated_sql = translated_sql.replace(f"`{table}`", table)

        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(translated_sql, parameters).fetchall()
        return [self._deserialize_row(table=table, row=row) for row in rows]

    def _initialize_schema(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            for table, fields in BIGQUERY_TABLES.items():
                self._validate_identifier(table)
                columns = ", ".join(f"{field['name']} {self._sqlite_type(field['type'])}" for field in fields)
                connection.execute(f"create table if not exists {table} ({columns})")

    def _ensure_unique_index(
        self,
        *,
        connection: sqlite3.Connection,
        table: str,
        key_fields: tuple[str, ...],
    ) -> None:
        if not key_fields:
            raise ValueError("SQLiteStructuredStore upsert requires at least one key field")
        index_name = f"idx_{table}_{'_'.join(key_fields)}_uniq"
        self._validate_identifier(index_name)
        fields_sql = ", ".join(key_fields)
        connection.execute(f"create unique index if not exists {index_name} on {table} ({fields_sql})")

    def _deserialize_row(self, *, table: str, row: sqlite3.Row) -> dict[str, object]:
        result: dict[str, object] = {}
        for field in BIGQUERY_TABLES[table]:
            name = field["name"]
            value = row[name]
            if value is None:
                continue
            if field.get("mode") == "REPEATED":
                result[name] = json.loads(value)
            elif field["type"] == "BOOL":
                result[name] = bool(value)
            else:
                result[name] = value
        return result

    def _serialize_value(self, *, table: str, field: str, value: object) -> object:
        if value is None:
            return None
        schema_field = next(item for item in BIGQUERY_TABLES[table] if item["name"] == field)
        if schema_field.get("mode") == "REPEATED":
            return json.dumps(list(value) if isinstance(value, (list, tuple)) else [value], ensure_ascii=False, sort_keys=True)
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        if schema_field["type"] == "BOOL":
            return int(bool(value))
        return value

    def _table_from_sql(self, sql: str) -> str:
        match = _FROM_TABLE.search(sql)
        if not match:
            raise ValueError(f"Cannot infer table from SQL: {sql}")
        raw_table = match.group(1)
        return raw_table.split(".")[-1]

    def _validate_table(self, table: str) -> None:
        self._validate_identifier(table)
        if table not in BIGQUERY_TABLES:
            raise ValueError(f"Unknown structured table: {table}")

    def _validate_fields(self, table: str, fields: tuple[str, ...]) -> None:
        allowed = {field["name"] for field in BIGQUERY_TABLES[table]}
        for field in fields:
            self._validate_identifier(field)
            if field not in allowed:
                raise ValueError(f"Unknown field for {table}: {field}")

    @staticmethod
    def _validate_identifier(identifier: str) -> None:
        if not _IDENTIFIER.fullmatch(identifier):
            raise ValueError(f"Invalid SQLite identifier: {identifier}")

    @staticmethod
    def _sqlite_type(bigquery_type: str) -> str:
        return {
            "BOOL": "INTEGER",
            "FLOAT": "REAL",
            "INTEGER": "INTEGER",
            "STRING": "TEXT",
            "TIMESTAMP": "TEXT",
        }.get(bigquery_type, "TEXT")
