from merry_runtime.adapters.bigquery import BigQueryStructuredStore
from merry_runtime.adapters.gcs import GCSObjectStore
from merry_runtime.adapters.gmail import GmailDraftClient, GmailLabelSource
from merry_runtime.adapters.google_sheets import GoogleSheetReviewQueue
from merry_runtime.adapters.local_files import LocalFileObjectStore
from merry_runtime.adapters.sminfo_playwright import SminfoPlaywrightClient
from merry_runtime.adapters.sqlite_store import SQLiteStructuredStore
from merry_runtime.adapters.slack import SlackNotifier
from merry_runtime.runtime_config import RuntimeConfig
from merry_runtime.runtime_factory import build_runtime
from merry_runtime.wiki_store import SQLiteWikiStore


class FakeStorageModule:
    class Client:
        def __init__(self, *, project: str) -> None:
            self.project = project


class FakeBigQueryModule:
    class Client:
        def __init__(self, *, project: str) -> None:
            self.project = project


class FakeSlackModule:
    class WebClient:
        def __init__(self, *, token: str) -> None:
            self.token = token


def test_runtime_factory_builds_production_adapters(monkeypatch, tmp_path) -> None:
    built_services = []

    def fake_build(service_name: str, version: str):
        built_services.append((service_name, version))
        return {"service": service_name, "version": version}

    def fake_import(name: str):
        modules = {
            "google.cloud.storage": FakeStorageModule,
            "google.cloud.bigquery": FakeBigQueryModule,
            "googleapiclient.discovery": type("Discovery", (), {"build": staticmethod(fake_build)}),
            "slack_sdk": FakeSlackModule,
        }
        return modules[name]

    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-token")
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="raw-bucket",
        review_sheet_id="sheet-1",
        slack_channel="C123",
        gmail_label_id="Label_123",
        default_ac_id="ac_climate",
        wiki_root=tmp_path,
        structured_store_backend="bigquery",
    )

    runtime = build_runtime(config, import_module=fake_import)

    assert isinstance(runtime.object_store, GCSObjectStore)
    assert isinstance(runtime.structured_store, BigQueryStructuredStore)
    assert isinstance(runtime.review_queue, GoogleSheetReviewQueue)
    assert isinstance(runtime.gmail_source, GmailLabelSource)
    assert isinstance(runtime.email_draft_client, GmailDraftClient)
    assert isinstance(runtime.notifier, SlackNotifier)
    assert isinstance(runtime.wiki_store, SQLiteWikiStore)
    assert runtime.structured_store.write_mode == "merge"
    assert built_services == [("sheets", "v4"), ("gmail", "v1")]


def test_runtime_factory_builds_gmail_draft_client_for_sheet_runtime(monkeypatch, tmp_path) -> None:
    built_services = []

    def fake_build(service_name: str, version: str):
        built_services.append((service_name, version))
        return {"service": service_name, "version": version}

    def fake_import(name: str):
        modules = {
            "googleapiclient.discovery": type("Discovery", (), {"build": staticmethod(fake_build)}),
        }
        return modules[name]

    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        review_sheet_id="sheet-1",
        wiki_root=tmp_path / "wiki",
        object_store_backend="local",
        raw_root=tmp_path / "raw",
        structured_store_backend="sqlite",
        mother_db_path=tmp_path / "mother.db",
        gmail_label_id="",
    )

    runtime = build_runtime(config, import_module=fake_import)

    assert isinstance(runtime.email_draft_client, GmailDraftClient)
    assert runtime.gmail_source is None
    assert built_services == [("sheets", "v4"), ("gmail", "v1")]


def test_runtime_factory_uses_local_object_store_without_storage_client(monkeypatch, tmp_path) -> None:
    imported_modules = []

    def fake_build(service_name: str, version: str):
        return {"service": service_name, "version": version}

    def fake_import(name: str):
        imported_modules.append(name)
        modules = {
            "google.cloud.bigquery": FakeBigQueryModule,
            "googleapiclient.discovery": type("Discovery", (), {"build": staticmethod(fake_build)}),
        }
        return modules[name]

    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="",
        review_sheet_id="sheet-1",
        wiki_root=tmp_path / "wiki",
        object_store_backend="local",
        raw_root=tmp_path / "raw",
        structured_store_backend="bigquery",
        bigquery_write_mode="append",
    )

    runtime = build_runtime(config, import_module=fake_import)

    assert isinstance(runtime.object_store, LocalFileObjectStore)
    assert runtime.structured_store.write_mode == "append"
    assert "google.cloud.storage" not in imported_modules


def test_runtime_factory_uses_sqlite_structured_store_without_bigquery_client(monkeypatch, tmp_path) -> None:
    imported_modules = []

    def fake_build(service_name: str, version: str):
        return {"service": service_name, "version": version}

    def fake_import(name: str):
        imported_modules.append(name)
        modules = {
            "googleapiclient.discovery": type("Discovery", (), {"build": staticmethod(fake_build)}),
        }
        return modules[name]

    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        review_sheet_id="sheet-1",
        wiki_root=tmp_path / "wiki",
        object_store_backend="local",
        raw_root=tmp_path / "raw",
        structured_store_backend="sqlite",
        mother_db_path=tmp_path / "mother.db",
    )

    runtime = build_runtime(config, import_module=fake_import)

    assert isinstance(runtime.object_store, LocalFileObjectStore)
    assert isinstance(runtime.structured_store, SQLiteStructuredStore)
    assert runtime.structured_store.db_path == tmp_path / "mother.db"
    assert "google.cloud.bigquery" not in imported_modules


def test_runtime_factory_builds_sminfo_client_only_when_credentials_are_configured(monkeypatch, tmp_path) -> None:
    def fake_build(service_name: str, version: str):
        return {"service": service_name, "version": version}

    def fake_import(name: str):
        return {"googleapiclient.discovery": type("Discovery", (), {"build": staticmethod(fake_build)})}[name]

    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        review_sheet_id="sheet-1",
        wiki_root=tmp_path / "wiki",
        object_store_backend="local",
        raw_root=tmp_path / "raw",
        structured_store_backend="sqlite",
        mother_db_path=tmp_path / "mother.db",
        sminfo_user_id="user",
        sminfo_password="password",
        sminfo_min_interval_seconds=35,
    )

    runtime = build_runtime(config, import_module=fake_import)

    assert isinstance(runtime.sminfo_client, SminfoPlaywrightClient)
    assert runtime.sminfo_client.user_id == "user"
    assert runtime.sminfo_client.min_interval_seconds == 35


def test_runtime_factory_uses_sqlite_backup_runtime_without_google_clients(monkeypatch, tmp_path) -> None:
    imported_modules = []

    def fake_import(name: str):
        imported_modules.append(name)
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        wiki_root=tmp_path / "wiki",
        object_store_backend="local",
        raw_root=tmp_path / "raw",
        structured_store_backend="sqlite",
        mother_db_path=tmp_path / "mother.db",
        review_sheet_id="",
        gmail_label_id="",
    )

    runtime = build_runtime(config, import_module=fake_import)

    assert isinstance(runtime.object_store, LocalFileObjectStore)
    assert isinstance(runtime.structured_store, SQLiteStructuredStore)
    assert imported_modules == []
