from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any


@dataclass(slots=True)
class BigQueryStructuredStore:
    client: Any
    project_id: str
    dataset_id: str

    def upsert_rows(self, *, table: str, rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> int:
        if not rows:
            return 0
        table_id = self._table_id(table)
        for row in rows:
            delete_sql, parameters = self._delete_sql(table_id, row, key_fields)
            self.client.query(delete_sql, job_config=_job_config(parameters)).result()
        errors = self.client.insert_rows_json(table_id, rows)
        if errors:
            raise RuntimeError(f"BigQuery insert_rows_json failed for {table_id}: {errors}")
        return len(rows)

    def query_rows(self, *, sql: str, parameters: dict[str, object]) -> list[dict[str, object]]:
        query_job = self.client.query(sql, job_config=_job_config(parameters))
        return [dict(row) for row in query_job.result()]

    def _table_id(self, table: str) -> str:
        return f"{self.project_id}.{self.dataset_id}.{table}"

    @staticmethod
    def _delete_sql(table_id: str, row: dict[str, object], key_fields: tuple[str, ...]) -> tuple[str, dict[str, object]]:
        if not key_fields:
            raise ValueError("key_fields must not be empty")
        predicates = [f"{field} = @{field}" for field in key_fields]
        parameters = {field: row[field] for field in key_fields}
        return f"DELETE FROM `{table_id}` WHERE {' AND '.join(predicates)}", parameters


def _job_config(parameters: dict[str, object]) -> object:
    return SimpleNamespace(parameters=dict(parameters))
