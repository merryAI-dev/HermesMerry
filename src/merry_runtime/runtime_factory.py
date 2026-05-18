from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from types import ModuleType

from merry_runtime.adapters.bigquery import BigQueryStructuredStore
from merry_runtime.adapters.gcs import GCSObjectStore
from merry_runtime.adapters.gmail import GmailLabelSource
from merry_runtime.adapters.google_sheets import GoogleSheetReviewQueue
from merry_runtime.adapters.local_files import LocalFileObjectStore
from merry_runtime.adapters.slack import SlackNotifier
from merry_runtime.job_runner import RuntimeAdapters
from merry_runtime.runtime_config import RuntimeConfig, RuntimeConfigError
from merry_runtime.wiki_store import SQLiteWikiStore


def build_runtime(
    config: RuntimeConfig,
    *,
    import_module: Callable[[str], ModuleType | object] = importlib.import_module,
) -> RuntimeAdapters:
    bigquery_module = import_module("google.cloud.bigquery")
    discovery_module = import_module("googleapiclient.discovery")
    object_store = _build_object_store(config=config, import_module=import_module)

    sheets_service = discovery_module.build("sheets", "v4")
    gmail_service = discovery_module.build("gmail", "v1") if config.gmail_label_id else None

    notifier = None
    slack_token = os.getenv("SLACK_BOT_TOKEN", "")
    if slack_token:
        slack_module = import_module("slack_sdk")
        notifier = SlackNotifier(client=slack_module.WebClient(token=slack_token))

    if config.slack_channel and notifier is None:
        raise RuntimeConfigError("SLACK_CHANNEL is configured but SLACK_BOT_TOKEN is missing")

    return RuntimeAdapters(
        object_store=object_store,
        structured_store=BigQueryStructuredStore(
            client=bigquery_module.Client(project=config.project_id),
            project_id=config.project_id,
            dataset_id=config.dataset_id,
            write_mode=config.bigquery_write_mode,
        ),
        review_queue=GoogleSheetReviewQueue(service=sheets_service, spreadsheet_id=config.review_sheet_id),
        notifier=notifier,
        wiki_store=SQLiteWikiStore(root=config.wiki_root),
        gmail_source=GmailLabelSource(service=gmail_service, user_id="me", label_id=config.gmail_label_id) if gmail_service else None,
    )


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
