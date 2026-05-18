from __future__ import annotations

from dataclasses import dataclass
import importlib
import logging
from types import SimpleNamespace
from typing import Any
import uuid

from merry_runtime.adapters.bigquery_merge import build_merge_sql
from merry_runtime.schema import BIGQUERY_TABLES


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BigQueryStructuredStore:
    client: Any
    project_id: str
    dataset_id: str

    def upsert_rows(self, *, table: str, rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> int:
        if not rows:
            return 0
        _validate_unique_batch_keys(rows, key_fields)
        table_id = self._table_id(table)
        staging_table_id = self._table_id(f"_staging_{table}_{uuid.uuid4().hex}")
        field_names = _field_names(table, rows)
        merge_sql = build_merge_sql(
            target_table_id=table_id,
            staging_table_id=staging_table_id,
            field_names=field_names,
            key_fields=key_fields,
        )
        try:
            self.client.load_table_from_json(
                rows,
                staging_table_id,
                job_config=_load_job_config(table),
            ).result()
            self.client.query(
                merge_sql,
                job_config=build_query_job_config({}, default_dataset=f"{self.project_id}.{self.dataset_id}"),
            ).result()
        finally:
            try:
                self.client.delete_table(staging_table_id, not_found_ok=True)
            except Exception as exc:
                logger.warning("failed to delete BigQuery staging table %s: %s", staging_table_id, exc)
        return len(rows)

    def query_rows(self, *, sql: str, parameters: dict[str, object]) -> list[dict[str, object]]:
        query_job = self.client.query(
            sql,
            job_config=build_query_job_config(parameters, default_dataset=f"{self.project_id}.{self.dataset_id}"),
        )
        return [dict(row) for row in query_job.result()]

    def _table_id(self, table: str) -> str:
        return f"{self.project_id}.{self.dataset_id}.{table}"


def build_query_job_config(
    parameters: dict[str, object],
    *,
    bigquery_module: Any | None = None,
    default_dataset: str | None = None,
) -> object:
    if bigquery_module is None:
        try:
            bigquery_module = importlib.import_module("google.cloud.bigquery")
        except ImportError:
            return SimpleNamespace(parameters=dict(parameters), default_dataset=default_dataset)

    config = bigquery_module.QueryJobConfig(
        query_parameters=[
            bigquery_module.ScalarQueryParameter(name, _bigquery_type(value), value) for name, value in parameters.items()
        ]
    )
    if default_dataset:
        config.default_dataset = default_dataset
    return config


def _load_job_config(table: str) -> object:
    schema = BIGQUERY_TABLES.get(table, [])
    try:
        bigquery_module = importlib.import_module("google.cloud.bigquery")
    except ImportError:
        return SimpleNamespace(schema=list(schema), write_disposition="WRITE_TRUNCATE")

    return bigquery_module.LoadJobConfig(
        schema=[
            bigquery_module.SchemaField(field["name"], field["type"], mode=field.get("mode", "NULLABLE"))
            for field in schema
        ],
        write_disposition=bigquery_module.WriteDisposition.WRITE_TRUNCATE,
    )


def _field_names(table: str, rows: list[dict[str, object]]) -> tuple[str, ...]:
    schema = BIGQUERY_TABLES.get(table)
    if schema:
        return tuple(field["name"] for field in schema)

    names: list[str] = []
    for row in rows:
        for name in row:
            if name not in names:
                names.append(name)
    return tuple(names)


def _validate_unique_batch_keys(rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> None:
    if not key_fields:
        raise ValueError("key_fields must not be empty")

    seen: set[tuple[object, ...]] = set()
    for row in rows:
        key = tuple(row[field] for field in key_fields)
        if key in seen:
            raise ValueError(f"duplicate key_fields value in upsert batch: {key}")
        seen.add(key)


def _bigquery_type(value: object) -> str:
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT64"
    if isinstance(value, float):
        return "FLOAT64"
    return "STRING"
