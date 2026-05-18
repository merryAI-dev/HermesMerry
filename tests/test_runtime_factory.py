from merry_runtime.adapters.bigquery import BigQueryStructuredStore
from merry_runtime.adapters.gcs import GCSObjectStore
from merry_runtime.adapters.gmail import GmailLabelSource
from merry_runtime.adapters.google_sheets import GoogleSheetReviewQueue
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
    )

    runtime = build_runtime(config, import_module=fake_import)

    assert isinstance(runtime.object_store, GCSObjectStore)
    assert isinstance(runtime.structured_store, BigQueryStructuredStore)
    assert isinstance(runtime.review_queue, GoogleSheetReviewQueue)
    assert isinstance(runtime.gmail_source, GmailLabelSource)
    assert isinstance(runtime.notifier, SlackNotifier)
    assert isinstance(runtime.wiki_store, SQLiteWikiStore)
    assert built_services == [("sheets", "v4"), ("gmail", "v1")]
