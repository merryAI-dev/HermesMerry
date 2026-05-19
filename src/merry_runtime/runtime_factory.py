from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from collections.abc import Callable
from types import ModuleType

from merry_runtime.adapters.bigquery import BigQueryStructuredStore
from merry_runtime.adapters.gcs import GCSObjectStore
from merry_runtime.adapters.gmail import GmailDraftClient, GmailLabelSource
from merry_runtime.adapters.google_sheets import GoogleSheetReviewQueue
from merry_runtime.adapters.local_files import LocalFileObjectStore
from merry_runtime.adapters.sminfo_playwright import SminfoPlaywrightClient
from merry_runtime.adapters.slack import SlackNotifier
from merry_runtime.adapters.sqlite_store import SQLiteStructuredStore
from merry_runtime.job_runner import RuntimeAdapters
from merry_runtime.runtime_config import RuntimeConfig, RuntimeConfigError
from merry_runtime.wiki_store import SQLiteWikiStore


def build_runtime(
    config: RuntimeConfig,
    *,
    import_module: Callable[[str], ModuleType | object] = importlib.import_module,
) -> RuntimeAdapters:
    object_store = _build_object_store(config=config, import_module=import_module)
    structured_store = _build_structured_store(config=config, import_module=import_module)
    discovery_module = (
        import_module("googleapiclient.discovery") if config.review_sheet_id or config.gmail_label_id else None
    )

    sheets_service = discovery_module.build("sheets", "v4") if discovery_module and config.review_sheet_id else None
    gmail_service = (
        discovery_module.build("gmail", "v1")
        if discovery_module and (config.review_sheet_id or config.gmail_label_id)
        else None
    )

    notifier = None
    slack_token = os.getenv("SLACK_BOT_TOKEN", "")
    if slack_token:
        slack_module = import_module("slack_sdk")
        notifier = SlackNotifier(client=slack_module.WebClient(token=slack_token))

    if config.slack_channel and notifier is None:
        raise RuntimeConfigError("SLACK_CHANNEL is configured but SLACK_BOT_TOKEN is missing")

    return RuntimeAdapters(
        object_store=object_store,
        structured_store=structured_store,
        review_queue=(
            GoogleSheetReviewQueue(service=sheets_service, spreadsheet_id=config.review_sheet_id)
            if sheets_service
            else UnavailableReviewQueue()
        ),
        notifier=notifier,
        wiki_store=SQLiteWikiStore(root=config.wiki_root),
        gmail_source=(
            GmailLabelSource(service=gmail_service, user_id="me", label_id=config.gmail_label_id)
            if gmail_service and config.gmail_label_id
            else None
        ),
        email_draft_client=GmailDraftClient(service=gmail_service, user_id="me", from_name="Merry") if gmail_service else None,
        sminfo_client=(
            SminfoPlaywrightClient(
                user_id=config.sminfo_user_id,
                password=config.sminfo_password,
                min_interval_seconds=config.sminfo_min_interval_seconds,
            )
            if config.sminfo_user_id and config.sminfo_password
            else None
        ),
    )


@dataclass(slots=True)
class UnavailableReviewQueue:
    def publish_cards(self, *, sheet_tab: str, rows: list[dict[str, object]]) -> int:
        raise RuntimeConfigError("REVIEW_SHEET_ID is required for Sheet review queue writes")

    def upsert_cards(self, *, sheet_tab: str, rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> int:
        raise RuntimeConfigError("REVIEW_SHEET_ID is required for Sheet review queue writes")

    def replace_rows(self, *, sheet_tab: str, headers: tuple[str, ...], rows: list[dict[str, object]]) -> int:
        raise RuntimeConfigError("REVIEW_SHEET_ID is required for Sheet review queue writes")

    def read_pending_reviews(self, *, sheet_tab: str) -> list[dict[str, str]]:
        raise RuntimeConfigError("REVIEW_SHEET_ID is required for Sheet review queue reads")


def _build_object_store(
    *,
    config: RuntimeConfig,
    import_module: Callable[[str], ModuleType | object],
) -> GCSObjectStore | LocalFileObjectStore:
    if config.object_store_backend == "local":
        return LocalFileObjectStore(root=config.raw_root)
    if config.object_store_backend != "gcs":
        raise RuntimeConfigError(f"Unsupported OBJECT_STORE_BACKEND: {config.object_store_backend}")
    storage_module = import_module("google.cloud.storage")
    return GCSObjectStore(client=storage_module.Client(project=config.project_id), bucket=config.raw_bucket)


def _build_structured_store(
    *,
    config: RuntimeConfig,
    import_module: Callable[[str], ModuleType | object],
) -> BigQueryStructuredStore | SQLiteStructuredStore:
    if config.structured_store_backend == "sqlite":
        return SQLiteStructuredStore(db_path=config.mother_db_path)
    if config.structured_store_backend != "bigquery":
        raise RuntimeConfigError(f"Unsupported STRUCTURED_STORE_BACKEND: {config.structured_store_backend}")
    bigquery_module = import_module("google.cloud.bigquery")
    return BigQueryStructuredStore(
        client=bigquery_module.Client(project=config.project_id),
        project_id=config.project_id,
        dataset_id=config.dataset_id,
        write_mode=config.bigquery_write_mode,
    )
