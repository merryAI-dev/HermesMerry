import pytest

from merry_runtime.adapters.bigquery_merge import build_merge_sql


def test_build_merge_sql_updates_existing_rows_and_inserts_new_rows() -> None:
    sql = build_merge_sql(
        target_table_id="project.dataset.mother_entities",
        staging_table_id="project.dataset._staging_mother_entities_run1",
        field_names=("entity_id", "name", "normalized_name", "last_seen_at"),
        key_fields=("entity_id",),
    )

    assert "MERGE `project.dataset.mother_entities` T" in sql
    assert "USING `project.dataset._staging_mother_entities_run1` S" in sql
    assert "ON T.entity_id = S.entity_id" in sql
    assert "WHEN MATCHED THEN UPDATE SET" in sql
    assert "name = S.name" in sql
    assert "normalized_name = S.normalized_name" in sql
    assert "last_seen_at = S.last_seen_at" in sql
    assert "WHEN NOT MATCHED THEN INSERT" in sql
    assert "`entity_id`, `name`, `normalized_name`, `last_seen_at`" in sql


def test_build_merge_sql_rejects_invalid_field_identifiers() -> None:
    with pytest.raises(ValueError, match="invalid BigQuery field identifier"):
        build_merge_sql(
            target_table_id="project.dataset.mother_entities",
            staging_table_id="project.dataset._staging_mother_entities_run1",
            field_names=("entity_id", "name; DROP TABLE mother_entities"),
            key_fields=("entity_id",),
        )
