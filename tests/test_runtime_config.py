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
