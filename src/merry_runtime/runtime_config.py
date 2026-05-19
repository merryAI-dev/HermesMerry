from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class RuntimeConfigError(ValueError):
    pass


_BIGQUERY_WRITE_MODES = {"merge", "append"}
_STRUCTURED_STORE_BACKENDS = {"sqlite", "bigquery"}
_SMINFO_BATCH_LIMIT_MIN = 1
_SMINFO_BATCH_LIMIT_MAX = 20
_OUTREACH_DRAFT_BATCH_LIMIT_MIN = 1
_OUTREACH_DRAFT_BATCH_LIMIT_MAX = 20
_KVIC_SYNC_INTERVAL_SECONDS_MIN = 86400


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    project_id: str
    dataset_id: str
    raw_bucket: str
    review_sheet_id: str = ""
    slack_channel: str = ""
    gmail_label_id: str = ""
    gmail_user_id: str = "me"
    gmail_from_name: str = "Merry"
    apps_script_draft_webhook_url: str = ""
    apps_script_draft_secret: str = ""
    apps_script_draft_timeout_seconds: int = 10
    crawl_sheet_tab: str = "Crawl Sources"
    crawl_targets_json: str = ""
    default_ac_id: str = ""
    wiki_root: Path = Path("/tmp/hermes-merry-wiki")
    object_store_backend: str = "gcs"
    raw_root: Path = Path("/workspace/hermes/raw")
    structured_store_backend: str = "sqlite"
    mother_db_path: Path = Path("/workspace/hermes/mother.db")
    backup_root: Path = Path("/workspace/hermes/backups")
    bigquery_write_mode: str = "merge"
    agent_loop_jobs: tuple[str, ...] = (
        "crawl-sources",
        "ingest-sources",
        "resolve-entities",
        "score-candidates",
        "sync-review-sheet",
        "calibrate-scores",
    )
    agent_loop_interval_seconds: int = 3600
    agent_loop_max_cycles: int = 0
    hermes_agent_id: str = "hermes-agent"
    sminfo_user_id: str = ""
    sminfo_password: str = ""
    sminfo_min_interval_seconds: int = 35
    sminfo_batch_limit: int = 20
    sminfo_stale_days: int = 30
    outreach_draft_batch_limit: int = 10
    kvic_api_key: str = ""
    kvic_sync_interval_seconds: int = 86400
    kvic_request_timeout_seconds: int = 15

    @classmethod
    def from_env(cls) -> RuntimeConfig:
        return cls(
            project_id=os.getenv("GCP_PROJECT_ID", ""),
            dataset_id=os.getenv("BIGQUERY_DATASET", ""),
            raw_bucket=os.getenv("RAW_BUCKET", ""),
            review_sheet_id=os.getenv("REVIEW_SHEET_ID", ""),
            slack_channel=os.getenv("SLACK_CHANNEL", ""),
            gmail_label_id=os.getenv("GMAIL_LABEL_ID", ""),
            gmail_user_id=os.getenv("GMAIL_USER_ID", "me"),
            gmail_from_name=os.getenv("GMAIL_FROM_NAME", "Merry"),
            apps_script_draft_webhook_url=os.getenv("APPS_SCRIPT_DRAFT_WEBHOOK_URL", ""),
            apps_script_draft_secret=os.getenv("APPS_SCRIPT_DRAFT_SECRET", ""),
            apps_script_draft_timeout_seconds=max(
                1,
                _parse_int(os.getenv("APPS_SCRIPT_DRAFT_TIMEOUT_SECONDS", ""), default=10),
            ),
            crawl_sheet_tab=os.getenv("CRAWL_SHEET_TAB", "Crawl Sources"),
            crawl_targets_json=os.getenv("CRAWL_TARGETS_JSON", ""),
            default_ac_id=os.getenv("AC_ID", ""),
            wiki_root=Path(os.getenv("WIKI_ROOT", "/tmp/hermes-merry-wiki")),
            object_store_backend=os.getenv("OBJECT_STORE_BACKEND", "gcs"),
            raw_root=Path(os.getenv("RAW_ROOT", "/workspace/hermes/raw")),
            structured_store_backend=_parse_structured_store_backend(os.getenv("STRUCTURED_STORE_BACKEND", "sqlite")),
            mother_db_path=Path(os.getenv("MOTHER_DB_PATH", "/workspace/hermes/mother.db")),
            backup_root=Path(os.getenv("BACKUP_ROOT", "/workspace/hermes/backups")),
            bigquery_write_mode=_parse_bigquery_write_mode(os.getenv("BIGQUERY_WRITE_MODE", "merge")),
            agent_loop_jobs=_parse_jobs(os.getenv("AGENT_LOOP_JOBS", "")),
            agent_loop_interval_seconds=_parse_int(os.getenv("AGENT_LOOP_INTERVAL_SECONDS", ""), default=3600),
            agent_loop_max_cycles=_parse_int(os.getenv("AGENT_LOOP_MAX_CYCLES", ""), default=0),
            hermes_agent_id=_parse_agent_id(),
            sminfo_user_id=os.getenv("SMINFO_USER_ID", ""),
            sminfo_password=os.getenv("SMINFO_PASSWORD", ""),
            sminfo_min_interval_seconds=max(
                35,
                _parse_int(os.getenv("SMINFO_MIN_INTERVAL_SECONDS", ""), default=35),
            ),
            sminfo_batch_limit=_parse_bounded_int(
                os.getenv("SMINFO_BATCH_LIMIT", ""),
                default=20,
                minimum=_SMINFO_BATCH_LIMIT_MIN,
                maximum=_SMINFO_BATCH_LIMIT_MAX,
            ),
            sminfo_stale_days=_parse_int(os.getenv("SMINFO_STALE_DAYS", ""), default=30),
            outreach_draft_batch_limit=_parse_bounded_int(
                os.getenv("OUTREACH_DRAFT_BATCH_LIMIT", ""),
                default=10,
                minimum=_OUTREACH_DRAFT_BATCH_LIMIT_MIN,
                maximum=_OUTREACH_DRAFT_BATCH_LIMIT_MAX,
            ),
            kvic_api_key=os.getenv("KVIC_API_KEY", ""),
            kvic_sync_interval_seconds=max(
                _KVIC_SYNC_INTERVAL_SECONDS_MIN,
                _parse_int(os.getenv("KVIC_SYNC_INTERVAL_SECONDS", ""), default=86400),
            ),
            kvic_request_timeout_seconds=max(
                1,
                _parse_int(os.getenv("KVIC_REQUEST_TIMEOUT_SECONDS", ""), default=15),
            ),
        )

    def validate_for_job(self, job_name: str, *, has_inline_sources: bool = False) -> None:
        self._validate_structured_store_backend()
        self._validate_bigquery_write_mode()
        required = self._structured_store_required_env()
        if job_name == "ingest-sources":
            if self.object_store_backend == "local":
                required.append("RAW_ROOT")
            else:
                required.append("GCP_PROJECT_ID")
                required.append("RAW_BUCKET")
            if not has_inline_sources:
                required.append("GMAIL_LABEL_ID")
        elif job_name == "crawl-sources":
            if self.object_store_backend == "local":
                required.append("RAW_ROOT")
            else:
                required.append("GCP_PROJECT_ID")
                required.append("RAW_BUCKET")
            if not has_inline_sources and not self.crawl_targets_json.strip():
                required.append("REVIEW_SHEET_ID")
        elif job_name == "ingest-ac-profiles":
            pass
        elif job_name in {"score-candidates", "sync-review-sheet"}:
            required.extend(["REVIEW_SHEET_ID", "AC_ID"])
        elif job_name == "calibrate-scores":
            required.append("AC_ID")
        elif job_name == "weekly-summary":
            required.append("SLACK_CHANNEL")
        elif job_name == "backup-export":
            required.extend(["MOTHER_DB_PATH", "BACKUP_ROOT"])
        elif job_name == "enrich-sminfo":
            required.extend(["REVIEW_SHEET_ID", "SMINFO_USER_ID", "SMINFO_PASSWORD"])
        elif job_name == "draft-outreach-emails":
            required.append("REVIEW_SHEET_ID")
            if self.apps_script_draft_webhook_url:
                required.append("APPS_SCRIPT_DRAFT_SECRET")
            if self.apps_script_draft_secret:
                required.append("APPS_SCRIPT_DRAFT_WEBHOOK_URL")
        elif job_name == "sync-kvic-funds":
            required.append("KVIC_API_KEY")
        elif job_name == "resolve-entities":
            pass
        else:
            raise RuntimeConfigError(f"Unknown job: {job_name}")

        missing = [name for name in required if not self._value_for_env_name(name)]
        if missing:
            raise RuntimeConfigError(f"Missing required environment for {job_name}: {', '.join(missing)}")

    def validate_for_loop(self, *, max_cycles: int) -> None:
        self._validate_structured_store_backend()
        self._validate_bigquery_write_mode()
        if self.structured_store_backend == "bigquery" and self.bigquery_write_mode == "append" and max_cycles != 1:
            raise RuntimeConfigError(
                "BIGQUERY_WRITE_MODE=append is limited to one-cycle canaries; "
                "set AGENT_LOOP_MAX_CYCLES=1 or use BIGQUERY_WRITE_MODE=merge for an always-on loop"
            )

    def _validate_structured_store_backend(self) -> None:
        if self.structured_store_backend not in _STRUCTURED_STORE_BACKENDS:
            allowed = ", ".join(sorted(_STRUCTURED_STORE_BACKENDS))
            raise RuntimeConfigError(
                f"Unsupported STRUCTURED_STORE_BACKEND={self.structured_store_backend!r}; expected one of: {allowed}"
            )

    def _validate_bigquery_write_mode(self) -> None:
        if self.bigquery_write_mode not in _BIGQUERY_WRITE_MODES:
            allowed = ", ".join(sorted(_BIGQUERY_WRITE_MODES))
            raise RuntimeConfigError(
                f"Unsupported BIGQUERY_WRITE_MODE={self.bigquery_write_mode!r}; expected one of: {allowed}"
            )

    def _structured_store_required_env(self) -> list[str]:
        if self.structured_store_backend == "bigquery":
            return ["GCP_PROJECT_ID", "BIGQUERY_DATASET"]
        if self.structured_store_backend == "sqlite":
            return ["MOTHER_DB_PATH"]
        return []

    def _value_for_env_name(self, name: str) -> str:
        return {
            "GCP_PROJECT_ID": self.project_id,
            "BIGQUERY_DATASET": self.dataset_id,
            "RAW_BUCKET": self.raw_bucket,
            "MOTHER_DB_PATH": str(self.mother_db_path),
            "BACKUP_ROOT": str(self.backup_root),
            "REVIEW_SHEET_ID": self.review_sheet_id,
            "SLACK_CHANNEL": self.slack_channel,
            "GMAIL_LABEL_ID": self.gmail_label_id,
            "GMAIL_USER_ID": self.gmail_user_id,
            "GMAIL_FROM_NAME": self.gmail_from_name,
            "APPS_SCRIPT_DRAFT_WEBHOOK_URL": self.apps_script_draft_webhook_url,
            "APPS_SCRIPT_DRAFT_SECRET": self.apps_script_draft_secret,
            "APPS_SCRIPT_DRAFT_TIMEOUT_SECONDS": str(self.apps_script_draft_timeout_seconds),
            "CRAWL_SHEET_TAB": self.crawl_sheet_tab,
            "AC_ID": self.default_ac_id,
            "RAW_ROOT": str(self.raw_root),
            "HERMES_AGENT_ID": self.hermes_agent_id,
            "SMINFO_USER_ID": self.sminfo_user_id,
            "SMINFO_PASSWORD": self.sminfo_password,
            "OUTREACH_DRAFT_BATCH_LIMIT": str(self.outreach_draft_batch_limit),
            "KVIC_API_KEY": self.kvic_api_key,
            "KVIC_SYNC_INTERVAL_SECONDS": str(self.kvic_sync_interval_seconds),
            "KVIC_REQUEST_TIMEOUT_SECONDS": str(self.kvic_request_timeout_seconds),
        }[name]


def _parse_jobs(value: str) -> tuple[str, ...]:
    if not value.strip():
        return (
            "crawl-sources",
            "ingest-sources",
            "resolve-entities",
            "score-candidates",
            "sync-review-sheet",
            "calibrate-scores",
        )
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parse_bigquery_write_mode(value: str) -> str:
    if not value.strip():
        return "merge"
    return value.strip().lower()


def _parse_structured_store_backend(value: str) -> str:
    if not value.strip():
        return "sqlite"
    return value.strip().lower()


def _parse_agent_id() -> str:
    for name in ("HERMES_AGENT_ID", "RUNPOD_POD_ID", "HOSTNAME"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return "hermes-agent"


def _parse_int(value: str, *, default: int) -> int:
    if not value.strip():
        return default
    return int(value)


def _parse_bounded_int(value: str, *, default: int, minimum: int, maximum: int) -> int:
    parsed = _parse_int(value, default=default)
    return min(max(parsed, minimum), maximum)
