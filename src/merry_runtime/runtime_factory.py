from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from collections.abc import Callable
from types import ModuleType

from merry_runtime.adapters.bigquery import BigQueryStructuredStore
from merry_runtime.adapters.gcs import GCSObjectStore
from merry_runtime.adapters.apps_script import AppsScriptDraftClient
from merry_runtime.adapters.gmail import GmailDraftClient, GmailLabelSource
from merry_runtime.adapters.google_sheets import GoogleSheetReviewQueue
from merry_runtime.adapters.anthropic import AnthropicMessagesClient
from merry_runtime.adapters.kvic import KVICClient
from merry_runtime.adapters.local_files import LocalFileObjectStore
from merry_runtime.adapters.sminfo_playwright import SminfoPlaywrightClient
from merry_runtime.adapters.slack import SlackNotifier
from merry_runtime.adapters.sqlite_store import SQLiteStructuredStore
from merry_runtime.adapters.web_search import PublicWebSearchClient
from merry_runtime.job_runner import RuntimeAdapters
from merry_runtime.runtime_config import RuntimeConfig, RuntimeConfigError
from merry_runtime.wiki_store import SQLiteWikiStore
from merry_runtime.adapters.thevc_playwright import TheVCPlaywrightClient


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
    needs_direct_gmail_draft_client = config.review_sheet_id and not config.apps_script_draft_webhook_url
    gmail_service = (
        discovery_module.build("gmail", "v1")
        if discovery_module and (config.gmail_label_id or needs_direct_gmail_draft_client)
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
            GmailLabelSource(service=gmail_service, user_id=config.gmail_user_id, label_id=config.gmail_label_id)
            if gmail_service and config.gmail_label_id
            else None
        ),
        email_draft_client=_build_email_draft_client(config=config, gmail_service=gmail_service),
        sminfo_client=(
            SminfoPlaywrightClient(
                user_id=config.sminfo_user_id,
                password=config.sminfo_password,
                min_interval_seconds=config.sminfo_min_interval_seconds,
            )
            if config.sminfo_user_id and config.sminfo_password
            else None
        ),
        kvic_client=(
            KVICClient(api_key=config.kvic_api_key, timeout_seconds=config.kvic_request_timeout_seconds)
            if config.kvic_api_key
            else None
        ),
        web_search_client=PublicWebSearchClient(timeout_seconds=config.kvic_request_timeout_seconds),
        llm_client=(
            AnthropicMessagesClient(
                api_key=config.anthropic_api_key,
                model=config.hermes_llm_model,
                timeout_seconds=config.hermes_llm_timeout_seconds,
            )
            if config.anthropic_api_key
            else None
        ),
        thevc_client=TheVCPlaywrightClient(
            user_email=config.thevc_user_email,
            password=config.thevc_password,
            storage_state_path=config.thevc_browser_state_path,
            headless=config.thevc_browser_headless,
            browser_channel=config.thevc_browser_channel,
            timeout_ms=config.thevc_timeout_seconds * 1000,
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


def _build_email_draft_client(*, config: RuntimeConfig, gmail_service: object | None) -> AppsScriptDraftClient | GmailDraftClient | None:
    if config.apps_script_draft_webhook_url and config.apps_script_draft_secret:
        return AppsScriptDraftClient(
            webhook_url=config.apps_script_draft_webhook_url,
            secret=config.apps_script_draft_secret,
            timeout_seconds=config.apps_script_draft_timeout_seconds,
        )
    if gmail_service:
        return GmailDraftClient(service=gmail_service, user_id=config.gmail_user_id, from_name=config.gmail_from_name)
    return None
