import pytest

from merry_runtime.runtime_config import RuntimeConfig, RuntimeConfigError


def test_runtime_config_reads_required_environment(monkeypatch) -> None:
    monkeypatch.setenv("GCP_PROJECT_ID", "project-1")
    monkeypatch.setenv("BIGQUERY_DATASET", "merry")
    monkeypatch.setenv("RAW_BUCKET", "raw-bucket")
    monkeypatch.setenv("REVIEW_SHEET_ID", "sheet-1")
    monkeypatch.setenv("SLACK_CHANNEL", "C123")
    monkeypatch.setenv("GMAIL_LABEL_ID", "Label_123")
    monkeypatch.setenv("AC_ID", "ac_climate")
    monkeypatch.setenv("WIKI_ROOT", "/tmp/wiki")

    config = RuntimeConfig.from_env()

    assert config.project_id == "project-1"
    assert config.dataset_id == "merry"
    assert config.raw_bucket == "raw-bucket"
    assert config.review_sheet_id == "sheet-1"
    assert config.slack_channel == "C123"
    assert config.gmail_label_id == "Label_123"
    assert config.default_ac_id == "ac_climate"
    assert str(config.wiki_root) == "/tmp/wiki"
    assert config.object_store_backend == "gcs"
    assert config.structured_store_backend == "sqlite"
    assert str(config.mother_db_path) == "/workspace/hermes/mother.db"
    assert str(config.backup_root) == "/workspace/hermes/backups"
    assert config.bigquery_write_mode == "merge"


def test_runtime_config_requires_job_specific_fields(monkeypatch) -> None:
    monkeypatch.setenv("GCP_PROJECT_ID", "project-1")
    monkeypatch.setenv("BIGQUERY_DATASET", "merry")
    monkeypatch.setenv("RAW_BUCKET", "raw-bucket")

    config = RuntimeConfig.from_env()

    with pytest.raises(RuntimeConfigError) as error:
        config.validate_for_job("score-candidates")

    assert "REVIEW_SHEET_ID" in str(error.value)
    assert "AC_ID" in str(error.value)


def test_runtime_config_accepts_ingest_ac_profiles_without_raw_bucket_or_scheduler_inputs(monkeypatch) -> None:
    monkeypatch.setenv("GCP_PROJECT_ID", "project-1")
    monkeypatch.setenv("BIGQUERY_DATASET", "merry")

    config = RuntimeConfig.from_env()

    config.validate_for_job("ingest-ac-profiles", has_inline_sources=True)


def test_runtime_config_accepts_calibrate_scores_without_review_sheet(monkeypatch) -> None:
    monkeypatch.setenv("GCP_PROJECT_ID", "project-1")
    monkeypatch.setenv("BIGQUERY_DATASET", "merry")
    monkeypatch.setenv("AC_ID", "ac_climate")

    config = RuntimeConfig.from_env()

    config.validate_for_job("calibrate-scores")


def test_runtime_config_accepts_local_object_store_for_ingest(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GCP_PROJECT_ID", "project-1")
    monkeypatch.setenv("BIGQUERY_DATASET", "merry")
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "local")
    monkeypatch.setenv("RAW_ROOT", str(tmp_path / "raw"))

    config = RuntimeConfig.from_env()

    config.validate_for_job("ingest-sources", has_inline_sources=True)
    assert config.object_store_backend == "local"
    assert config.raw_root == tmp_path / "raw"


def test_runtime_config_reads_sqlite_structured_store_paths(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STRUCTURED_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("MOTHER_DB_PATH", str(tmp_path / "mother.db"))
    monkeypatch.setenv("BACKUP_ROOT", str(tmp_path / "backups"))

    config = RuntimeConfig.from_env()

    assert config.structured_store_backend == "sqlite"
    assert config.mother_db_path == tmp_path / "mother.db"
    assert config.backup_root == tmp_path / "backups"


def test_runtime_config_rejects_unknown_structured_store_backend(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURED_STORE_BACKEND", "warehouse")

    config = RuntimeConfig.from_env()

    with pytest.raises(RuntimeConfigError) as error:
        config.validate_for_job("resolve-entities")

    assert "STRUCTURED_STORE_BACKEND" in str(error.value)
    assert "warehouse" in str(error.value)


def test_runtime_config_reads_bigquery_append_write_mode(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_WRITE_MODE", "append")

    config = RuntimeConfig.from_env()

    assert config.bigquery_write_mode == "append"


def test_runtime_config_rejects_unknown_bigquery_write_mode(monkeypatch) -> None:
    monkeypatch.setenv("GCP_PROJECT_ID", "project-1")
    monkeypatch.setenv("BIGQUERY_DATASET", "merry")
    monkeypatch.setenv("BIGQUERY_WRITE_MODE", "truncate")

    config = RuntimeConfig.from_env()

    with pytest.raises(RuntimeConfigError) as error:
        config.validate_for_job("resolve-entities")

    assert "BIGQUERY_WRITE_MODE" in str(error.value)
    assert "truncate" in str(error.value)
