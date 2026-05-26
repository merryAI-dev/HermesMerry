import pytest

from merry_runtime.runtime_config import RuntimeConfig, RuntimeConfigError


def test_runtime_config_reads_required_environment(monkeypatch) -> None:
    monkeypatch.setenv("GCP_PROJECT_ID", "project-1")
    monkeypatch.setenv("BIGQUERY_DATASET", "merry")
    monkeypatch.setenv("RAW_BUCKET", "raw-bucket")
    monkeypatch.setenv("REVIEW_SHEET_ID", "sheet-1")
    monkeypatch.setenv("SLACK_CHANNEL", "C123")
    monkeypatch.setenv("GMAIL_LABEL_ID", "Label_123")
    monkeypatch.setenv("GMAIL_USER_ID", "operator@mysc.co.kr")
    monkeypatch.setenv("GMAIL_FROM_NAME", "Merry")
    monkeypatch.setenv("APPS_SCRIPT_DRAFT_WEBHOOK_URL", "https://script.google.com/macros/s/deployment/exec")
    monkeypatch.setenv("APPS_SCRIPT_DRAFT_SECRET", "shared-secret")
    monkeypatch.setenv("APPS_SCRIPT_DRAFT_TIMEOUT_SECONDS", "9")
    monkeypatch.setenv("AC_ID", "ac_climate")
    monkeypatch.setenv("WIKI_ROOT", "/tmp/wiki")
    monkeypatch.setenv("SMINFO_USER_ID", "sminfo-user")
    monkeypatch.setenv("SMINFO_PASSWORD", "sminfo-password")
    monkeypatch.setenv("SMINFO_LOGIN_URL", "https://example.test/sminfo-login")
    monkeypatch.setenv("SMINFO_MIN_INTERVAL_SECONDS", "35")
    monkeypatch.setenv("SMINFO_BATCH_LIMIT", "20")
    monkeypatch.setenv("SMINFO_STALE_DAYS", "30")
    monkeypatch.setenv("HERMES_AGENT_ID", "runpod-pod-1")
    monkeypatch.setenv("AGENT_WORK_QUEUE_SPEC_PATH", "configs/test-chain.json")
    monkeypatch.setenv("AGENT_WORK_QUEUE_BATCH_LIMIT", "17")
    monkeypatch.setenv("KVIC_API_KEY", "public-kvic-key")
    monkeypatch.setenv("KVIC_SYNC_INTERVAL_SECONDS", "86400")
    monkeypatch.setenv("KVIC_FUND_DESCRIPTION_BATCH_LIMIT", "25")
    monkeypatch.setenv("KVIC_FUND_DESCRIPTION_STALE_DAYS", "45")
    monkeypatch.setenv("KVIC_FUND_SEARCH_MAX_RESULTS", "7")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("HERMES_LLM_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("HERMES_LLM_TIMEOUT_SECONDS", "31")
    monkeypatch.setenv("INVESTOR_RESEARCH_BATCH_LIMIT", "12")
    monkeypatch.setenv("INVESTOR_RESEARCH_STALE_DAYS", "9")
    monkeypatch.setenv("INVESTOR_RESEARCH_SEARCH_MAX_RESULTS", "8")
    monkeypatch.setenv("THEVC_USER_EMAIL", "operator@mysc.co.kr")
    monkeypatch.setenv("THEVC_PASSWORD", "thevc-password")
    monkeypatch.setenv("THEVC_BROWSER_STATE_PATH", "/tmp/thevc-state.json")
    monkeypatch.setenv("THEVC_BROWSER_HEADLESS", "0")
    monkeypatch.setenv("THEVC_BROWSER_CHANNEL", "chrome")
    monkeypatch.setenv("THEVC_TIMEOUT_SECONDS", "45")

    config = RuntimeConfig.from_env()

    assert config.project_id == "project-1"
    assert config.dataset_id == "merry"
    assert config.raw_bucket == "raw-bucket"
    assert config.review_sheet_id == "sheet-1"
    assert config.slack_channel == "C123"
    assert config.gmail_label_id == "Label_123"
    assert config.gmail_user_id == "operator@mysc.co.kr"
    assert config.gmail_from_name == "Merry"
    assert config.apps_script_draft_webhook_url == "https://script.google.com/macros/s/deployment/exec"
    assert config.apps_script_draft_secret == "shared-secret"
    assert config.apps_script_draft_timeout_seconds == 9
    assert config.default_ac_id == "ac_climate"
    assert str(config.wiki_root) == "/tmp/wiki"
    assert config.object_store_backend == "gcs"
    assert config.structured_store_backend == "sqlite"
    assert str(config.mother_db_path) == "/workspace/hermes/mother.db"
    assert str(config.backup_root) == "/workspace/hermes/backups"
    assert config.bigquery_write_mode == "merge"
    assert config.sminfo_user_id == "sminfo-user"
    assert config.sminfo_password == "sminfo-password"
    assert config.sminfo_login_url == "https://example.test/sminfo-login"
    assert config.sminfo_min_interval_seconds == 35
    assert config.sminfo_batch_limit == 20
    assert config.sminfo_stale_days == 30
    assert config.hermes_agent_id == "runpod-pod-1"
    assert str(config.agent_work_queue_spec_path) == "configs/test-chain.json"
    assert config.agent_work_queue_batch_limit == 17
    assert config.kvic_api_key == "public-kvic-key"
    assert config.kvic_sync_interval_seconds == 86400
    assert config.kvic_fund_description_batch_limit == 25
    assert config.kvic_fund_description_stale_days == 45
    assert config.kvic_fund_search_max_results == 7
    assert config.anthropic_api_key == "anthropic-key"
    assert config.hermes_llm_model == "claude-sonnet-4-6"
    assert config.hermes_llm_timeout_seconds == 31
    assert config.investor_research_batch_limit == 12
    assert config.investor_research_stale_days == 9
    assert config.investor_research_search_max_results == 8
    assert config.thevc_user_email == "operator@mysc.co.kr"
    assert config.thevc_password == "thevc-password"
    assert str(config.thevc_browser_state_path) == "/tmp/thevc-state.json"
    assert config.thevc_browser_headless is False
    assert config.thevc_browser_channel == "chrome"
    assert config.thevc_timeout_seconds == 45


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


def test_runtime_config_accepts_crawl_sources_with_inline_targets(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "local")
    monkeypatch.setenv("RAW_ROOT", str(tmp_path / "raw"))

    config = RuntimeConfig.from_env()

    config.validate_for_job("crawl-sources", has_inline_sources=True)


def test_runtime_config_requires_review_sheet_for_crawl_sources_without_inline_targets(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "local")
    monkeypatch.setenv("RAW_ROOT", str(tmp_path / "raw"))

    config = RuntimeConfig.from_env()

    with pytest.raises(RuntimeConfigError) as error:
        config.validate_for_job("crawl-sources", has_inline_sources=False)

    assert "REVIEW_SHEET_ID" in str(error.value)


def test_runtime_config_accepts_crawl_sources_with_configured_targets(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "local")
    monkeypatch.setenv("RAW_ROOT", str(tmp_path / "raw"))
    monkeypatch.setenv("CRAWL_TARGETS_JSON", '[{"url":"https://thevc.kr/","source_kind":"thevc_investment_ma"}]')

    config = RuntimeConfig.from_env()

    config.validate_for_job("crawl-sources", has_inline_sources=False)
    assert config.crawl_targets_json.startswith("[")


def test_runtime_config_requires_sminfo_credentials_and_review_sheet(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STRUCTURED_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("MOTHER_DB_PATH", str(tmp_path / "mother.db"))

    config = RuntimeConfig.from_env()

    with pytest.raises(RuntimeConfigError) as error:
        config.validate_for_job("enrich-sminfo")

    assert "REVIEW_SHEET_ID" in str(error.value)
    assert "SMINFO_USER_ID" in str(error.value)
    assert "SMINFO_PASSWORD" in str(error.value)


def test_runtime_config_requires_review_sheet_for_draft_outreach_emails(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STRUCTURED_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("MOTHER_DB_PATH", str(tmp_path / "mother.db"))

    config = RuntimeConfig.from_env()

    with pytest.raises(RuntimeConfigError) as error:
        config.validate_for_job("draft-outreach-emails")

    assert "REVIEW_SHEET_ID" in str(error.value)


def test_runtime_config_requires_apps_script_secret_when_gateway_url_is_configured(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STRUCTURED_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("MOTHER_DB_PATH", str(tmp_path / "mother.db"))
    monkeypatch.setenv("REVIEW_SHEET_ID", "sheet-1")
    monkeypatch.setenv("APPS_SCRIPT_DRAFT_WEBHOOK_URL", "https://script.google.com/macros/s/deployment/exec")

    config = RuntimeConfig.from_env()

    with pytest.raises(RuntimeConfigError) as error:
        config.validate_for_job("draft-outreach-emails")

    assert "APPS_SCRIPT_DRAFT_SECRET" in str(error.value)


def test_runtime_config_requires_kvic_api_key_for_sync_kvic_funds(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STRUCTURED_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("MOTHER_DB_PATH", str(tmp_path / "mother.db"))

    config = RuntimeConfig.from_env()

    with pytest.raises(RuntimeConfigError) as error:
        config.validate_for_job("sync-kvic-funds")

    assert "KVIC_API_KEY" in str(error.value)


def test_runtime_config_accepts_sync_kvic_funds_with_daily_interval(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STRUCTURED_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("MOTHER_DB_PATH", str(tmp_path / "mother.db"))
    monkeypatch.setenv("KVIC_API_KEY", "public-kvic-key")
    monkeypatch.setenv("KVIC_SYNC_INTERVAL_SECONDS", "3600")

    config = RuntimeConfig.from_env()

    config.validate_for_job("sync-kvic-funds")
    assert config.kvic_sync_interval_seconds == 86400


def test_runtime_config_bounds_kvic_fund_description_search_controls(monkeypatch) -> None:
    monkeypatch.setenv("KVIC_FUND_DESCRIPTION_BATCH_LIMIT", "999")
    monkeypatch.setenv("KVIC_FUND_DESCRIPTION_STALE_DAYS", "0")
    monkeypatch.setenv("KVIC_FUND_SEARCH_MAX_RESULTS", "99")

    config = RuntimeConfig.from_env()

    assert config.kvic_fund_description_batch_limit == 100
    assert config.kvic_fund_description_stale_days == 1
    assert config.kvic_fund_search_max_results == 10


def test_runtime_config_requires_anthropic_key_for_investor_research(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STRUCTURED_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("MOTHER_DB_PATH", str(tmp_path / "mother.db"))

    config = RuntimeConfig.from_env()

    with pytest.raises(RuntimeConfigError) as error:
        config.validate_for_job("research-investors")

    assert "ANTHROPIC_API_KEY" in str(error.value)


def test_runtime_config_bounds_investor_research_controls(monkeypatch) -> None:
    monkeypatch.setenv("INVESTOR_RESEARCH_BATCH_LIMIT", "999")
    monkeypatch.setenv("INVESTOR_RESEARCH_STALE_DAYS", "0")
    monkeypatch.setenv("INVESTOR_RESEARCH_SEARCH_MAX_RESULTS", "99")
    monkeypatch.setenv("HERMES_LLM_TIMEOUT_SECONDS", "0")

    config = RuntimeConfig.from_env()

    assert config.investor_research_batch_limit == 50
    assert config.investor_research_stale_days == 1
    assert config.investor_research_search_max_results == 10
    assert config.hermes_llm_timeout_seconds == 1


def test_runtime_config_bounds_sminfo_batch_limit_to_site_safe_range(monkeypatch) -> None:
    monkeypatch.setenv("SMINFO_BATCH_LIMIT", "999")
    assert RuntimeConfig.from_env().sminfo_batch_limit == 20

    monkeypatch.setenv("SMINFO_BATCH_LIMIT", "0")
    assert RuntimeConfig.from_env().sminfo_batch_limit == 1


def test_runtime_config_reads_env_local_without_overriding_shell_env(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            (
                "SMINFO_USER_ID=file-user",
                "SMINFO_PASSWORD='file-password'",
                "SMINFO_LOGIN_URL=https://sminfo.example/file-login",
                "HERMES_AGENT_ID=file-agent",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HERMES_ENV_FILE", str(env_file))
    monkeypatch.setenv("SMINFO_USER_ID", "shell-user")

    config = RuntimeConfig.from_env()

    assert config.sminfo_user_id == "shell-user"
    assert config.sminfo_password == "file-password"
    assert config.sminfo_login_url == "https://sminfo.example/file-login"
    assert config.hermes_agent_id == "file-agent"


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
