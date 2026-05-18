from __future__ import annotations

import re


_BIGQUERY_FIELD_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def build_merge_sql(
    *,
    target_table_id: str,
    staging_table_id: str,
    field_names: tuple[str, ...],
    key_fields: tuple[str, ...],
) -> str:
    if not key_fields:
        raise ValueError("key_fields must not be empty")
    if not field_names:
        raise ValueError("field_names must not be empty")
    missing_keys = set(key_fields) - set(field_names)
    if missing_keys:
        raise ValueError(f"key_fields must exist in field_names: {sorted(missing_keys)}")
    for field in field_names:
        _validate_field_identifier(field)
    for field in key_fields:
        _validate_field_identifier(field)

    on_clause = " AND ".join(f"T.{field} = S.{field}" for field in key_fields)
    update_fields = tuple(field for field in field_names if field not in key_fields)
    update_clause = ", ".join(f"{field} = S.{field}" for field in update_fields) or ", ".join(
        f"{field} = S.{field}" for field in key_fields
    )
    insert_columns = ", ".join(f"`{field}`" for field in field_names)
    insert_values = ", ".join(f"S.{field}" for field in field_names)

    return f"""
MERGE `{target_table_id}` T
USING `{staging_table_id}` S
ON {on_clause}
WHEN MATCHED THEN UPDATE SET {update_clause}
WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})
""".strip()


def _validate_field_identifier(field: str) -> None:
    if not _BIGQUERY_FIELD_IDENTIFIER.fullmatch(field):
        raise ValueError(f"invalid BigQuery field identifier: {field}")
