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
_KVIC_FUND_DESCRIPTION_BATCH_LIMIT_MIN = 1
_KVIC_FUND_DESCRIPTION_BATCH_LIMIT_MAX = 100
_KVIC_FUND_SEARCH_MAX_RESULTS_MIN = 1
_KVIC_FUND_SEARCH_MAX_RESULTS_MAX = 10
_INVESTOR_RESEARCH_BATCH_LIMIT_MIN = 1
_INVESTOR_RESEARCH_BATCH_LIMIT_MAX = 50
_INVESTOR_RESEARCH_SEARCH_MAX_RESULTS_MIN = 1
_INVESTOR_RESEARCH_SEARCH_MAX_RESULTS_MAX = 10
_AGENT_WORK_QUEUE_BATCH_LIMIT_MIN = 1
_AGENT_WORK_QUEUE_BATCH_LIMIT_MAX = 50


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
    agent_loop_jobs: tuple[str, ...] = ("agent-work-queue",)
    agent_loop_interval_seconds: int = 3600
    agent_loop_max_cycles: int = 0
    allow_unbounded_loop: bool = False
    hermes_agent_id: str = "hermes-agent"
    agent_work_queue_spec_path: Path = Path("configs/agent_work_queue.discovery.json")
    agent_work_queue_batch_limit: int = 10
    sminfo_user_id: str = ""
    sminfo_password: str = ""
    sminfo_login_url: str = "https://sminfo.mss.go.kr/cm/sv/CSV001R0.do"
    sminfo_min_interval_seconds: int = 35
    sminfo_batch_limit: int = 20
    sminfo_stale_days: int = 30
    outreach_draft_batch_limit: int = 10
    kvic_api_key: str = ""
    kvic_sync_interval_seconds: int = 86400
    kvic_request_timeout_seconds: int = 15
    kvic_fund_description_batch_limit: int = 50
    kvic_fund_description_stale_days: int = 30
    kvic_fund_search_max_results: int = 5
    anthropic_api_key: str = ""
    hermes_llm_model: str = "claude-sonnet-4-6"
    hermes_llm_timeout_seconds: int = 30
    investor_research_batch_limit: int = 20
    investor_research_stale_days: int = 7
    investor_research_search_max_results: int = 5
    thevc_user_email: str = ""
    thevc_password: str = ""
    thevc_browser_state_path: Path = Path("/workspace/hermes/thevc-state.json")
    thevc_browser_headless: bool = True
    thevc_browser_channel: str = ""
    thevc_timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> RuntimeConfig:
        env_file_values = _load_env_file_values(Path(os.getenv("HERMES_ENV_FILE", ".env.local")))
        getenv = lambda key, default="": os.environ.get(key, env_file_values.get(key, default))
        return cls(
            project_id=getenv("GCP_PROJECT_ID"),
            dataset_id=getenv("BIGQUERY_DATASET"),
            raw_bucket=getenv("RAW_BUCKET"),
            review_sheet_id=getenv("REVIEW_SHEET_ID"),
            slack_channel=getenv("SLACK_CHANNEL"),
            gmail_label_id=getenv("GMAIL_LABEL_ID"),
            gmail_user_id=getenv("GMAIL_USER_ID", "me"),
            gmail_from_name=getenv("GMAIL_FROM_NAME", "Merry"),
            apps_script_draft_webhook_url=getenv("APPS_SCRIPT_DRAFT_WEBHOOK_URL"),
            apps_script_draft_secret=getenv("APPS_SCRIPT_DRAFT_SECRET"),
            apps_script_draft_timeout_seconds=max(
                1,
                _parse_int(getenv("APPS_SCRIPT_DRAFT_TIMEOUT_SECONDS"), default=10),
            ),
            crawl_sheet_tab=getenv("CRAWL_SHEET_TAB", "Crawl Sources"),
            crawl_targets_json=getenv("CRAWL_TARGETS_JSON"),
            default_ac_id=getenv("AC_ID"),
            wiki_root=Path(getenv("WIKI_ROOT", "/tmp/hermes-merry-wiki")),
            object_store_backend=getenv("OBJECT_STORE_BACKEND", "gcs"),
            raw_root=Path(getenv("RAW_ROOT", "/workspace/hermes/raw")),
            structured_store_backend=_parse_structured_store_backend(getenv("STRUCTURED_STORE_BACKEND", "sqlite")),
            mother_db_path=Path(getenv("MOTHER_DB_PATH", "/workspace/hermes/mother.db")),
            backup_root=Path(getenv("BACKUP_ROOT", "/workspace/hermes/backups")),
            bigquery_write_mode=_parse_bigquery_write_mode(getenv("BIGQUERY_WRITE_MODE", "merge")),
            agent_loop_jobs=_parse_jobs(getenv("AGENT_LOOP_JOBS")),
            agent_loop_interval_seconds=_parse_int(getenv("AGENT_LOOP_INTERVAL_SECONDS"), default=3600),
            agent_loop_max_cycles=_parse_int(getenv("AGENT_LOOP_MAX_CYCLES"), default=0),
            allow_unbounded_loop=_parse_bool(getenv("HERMES_ALLOW_UNBOUNDED_LOOP"), default=False),
            hermes_agent_id=_parse_agent_id(env_file_values=env_file_values),
            agent_work_queue_spec_path=Path(
                getenv("AGENT_WORK_QUEUE_SPEC_PATH", "configs/agent_work_queue.discovery.json")
            ),
            agent_work_queue_batch_limit=_parse_bounded_int(
                getenv("AGENT_WORK_QUEUE_BATCH_LIMIT"),
                default=10,
                minimum=_AGENT_WORK_QUEUE_BATCH_LIMIT_MIN,
                maximum=_AGENT_WORK_QUEUE_BATCH_LIMIT_MAX,
            ),
            sminfo_user_id=getenv("SMINFO_USER_ID"),
            sminfo_password=getenv("SMINFO_PASSWORD"),
            sminfo_login_url=getenv("SMINFO_LOGIN_URL", "https://sminfo.mss.go.kr/cm/sv/CSV001R0.do"),
            sminfo_min_interval_seconds=max(
                35,
                _parse_int(getenv("SMINFO_MIN_INTERVAL_SECONDS"), default=35),
            ),
            sminfo_batch_limit=_parse_bounded_int(
                getenv("SMINFO_BATCH_LIMIT"),
                default=20,
                minimum=_SMINFO_BATCH_LIMIT_MIN,
                maximum=_SMINFO_BATCH_LIMIT_MAX,
            ),
            sminfo_stale_days=_parse_int(getenv("SMINFO_STALE_DAYS"), default=30),
            outreach_draft_batch_limit=_parse_bounded_int(
                getenv("OUTREACH_DRAFT_BATCH_LIMIT"),
                default=10,
                minimum=_OUTREACH_DRAFT_BATCH_LIMIT_MIN,
                maximum=_OUTREACH_DRAFT_BATCH_LIMIT_MAX,
            ),
            kvic_api_key=getenv("KVIC_API_KEY"),
            kvic_sync_interval_seconds=max(
                _KVIC_SYNC_INTERVAL_SECONDS_MIN,
                _parse_int(getenv("KVIC_SYNC_INTERVAL_SECONDS"), default=86400),
            ),
            kvic_request_timeout_seconds=max(
                1,
                _parse_int(getenv("KVIC_REQUEST_TIMEOUT_SECONDS"), default=15),
            ),
            kvic_fund_description_batch_limit=_parse_bounded_int(
                getenv("KVIC_FUND_DESCRIPTION_BATCH_LIMIT"),
                default=50,
                minimum=_KVIC_FUND_DESCRIPTION_BATCH_LIMIT_MIN,
                maximum=_KVIC_FUND_DESCRIPTION_BATCH_LIMIT_MAX,
            ),
            kvic_fund_description_stale_days=max(
                1,
                _parse_int(getenv("KVIC_FUND_DESCRIPTION_STALE_DAYS"), default=30),
            ),
            kvic_fund_search_max_results=_parse_bounded_int(
                getenv("KVIC_FUND_SEARCH_MAX_RESULTS"),
                default=5,
                minimum=_KVIC_FUND_SEARCH_MAX_RESULTS_MIN,
                maximum=_KVIC_FUND_SEARCH_MAX_RESULTS_MAX,
            ),
            anthropic_api_key=getenv("ANTHROPIC_API_KEY"),
            hermes_llm_model=getenv("HERMES_LLM_MODEL", "claude-sonnet-4-6"),
            hermes_llm_timeout_seconds=max(
                1,
                _parse_int(getenv("HERMES_LLM_TIMEOUT_SECONDS"), default=30),
            ),
            investor_research_batch_limit=_parse_bounded_int(
                getenv("INVESTOR_RESEARCH_BATCH_LIMIT"),
                default=20,
                minimum=_INVESTOR_RESEARCH_BATCH_LIMIT_MIN,
                maximum=_INVESTOR_RESEARCH_BATCH_LIMIT_MAX,
            ),
            investor_research_stale_days=max(
                1,
                _parse_int(getenv("INVESTOR_RESEARCH_STALE_DAYS"), default=7),
            ),
            investor_research_search_max_results=_parse_bounded_int(
                getenv("INVESTOR_RESEARCH_SEARCH_MAX_RESULTS"),
                default=5,
                minimum=_INVESTOR_RESEARCH_SEARCH_MAX_RESULTS_MIN,
                maximum=_INVESTOR_RESEARCH_SEARCH_MAX_RESULTS_MAX,
            ),
            thevc_user_email=getenv("THEVC_USER_EMAIL"),
            thevc_password=getenv("THEVC_PASSWORD"),
            thevc_browser_state_path=Path(getenv("THEVC_BROWSER_STATE_PATH", "/workspace/hermes/thevc-state.json")),
            thevc_browser_headless=_parse_bool(getenv("THEVC_BROWSER_HEADLESS"), default=True),
            thevc_browser_channel=getenv("THEVC_BROWSER_CHANNEL"),
            thevc_timeout_seconds=max(
                1,
                _parse_int(getenv("THEVC_TIMEOUT_SECONDS"), default=30),
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
        elif job_name == "agent-work-queue":
            pass
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
        elif job_name == "research-investors":
            required.append("ANTHROPIC_API_KEY")
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
        if max_cycles <= 0 and not self.allow_unbounded_loop:
            raise RuntimeConfigError(
                "AGENT_LOOP_MAX_CYCLES=0 starts an unbounded loop and can accrue Runpod compute charges. "
                "Set HERMES_ALLOW_UNBOUNDED_LOOP=1 only for an intentionally always-on CPU/control-plane runtime, "
                "or use AGENT_LOOP_MAX_CYCLES=1 for canaries and batch runs."
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
            "AGENT_WORK_QUEUE_SPEC_PATH": str(self.agent_work_queue_spec_path),
            "AGENT_WORK_QUEUE_BATCH_LIMIT": str(self.agent_work_queue_batch_limit),
            "SMINFO_USER_ID": self.sminfo_user_id,
            "SMINFO_PASSWORD": self.sminfo_password,
            "SMINFO_LOGIN_URL": self.sminfo_login_url,
            "OUTREACH_DRAFT_BATCH_LIMIT": str(self.outreach_draft_batch_limit),
            "KVIC_API_KEY": self.kvic_api_key,
            "KVIC_SYNC_INTERVAL_SECONDS": str(self.kvic_sync_interval_seconds),
            "KVIC_REQUEST_TIMEOUT_SECONDS": str(self.kvic_request_timeout_seconds),
            "KVIC_FUND_DESCRIPTION_BATCH_LIMIT": str(self.kvic_fund_description_batch_limit),
            "KVIC_FUND_DESCRIPTION_STALE_DAYS": str(self.kvic_fund_description_stale_days),
            "KVIC_FUND_SEARCH_MAX_RESULTS": str(self.kvic_fund_search_max_results),
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "HERMES_LLM_MODEL": self.hermes_llm_model,
            "HERMES_LLM_TIMEOUT_SECONDS": str(self.hermes_llm_timeout_seconds),
            "INVESTOR_RESEARCH_BATCH_LIMIT": str(self.investor_research_batch_limit),
            "INVESTOR_RESEARCH_STALE_DAYS": str(self.investor_research_stale_days),
            "INVESTOR_RESEARCH_SEARCH_MAX_RESULTS": str(self.investor_research_search_max_results),
            "THEVC_USER_EMAIL": self.thevc_user_email,
            "THEVC_PASSWORD": self.thevc_password,
            "THEVC_BROWSER_STATE_PATH": str(self.thevc_browser_state_path),
            "THEVC_BROWSER_HEADLESS": "1" if self.thevc_browser_headless else "0",
            "THEVC_BROWSER_CHANNEL": self.thevc_browser_channel,
            "THEVC_TIMEOUT_SECONDS": str(self.thevc_timeout_seconds),
        }[name]


def _parse_jobs(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ("agent-work-queue",)
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parse_bigquery_write_mode(value: str) -> str:
    if not value.strip():
        return "merge"
    return value.strip().lower()


def _parse_structured_store_backend(value: str) -> str:
    if not value.strip():
        return "sqlite"
    return value.strip().lower()


def _parse_agent_id(*, env_file_values: dict[str, str] | None = None) -> str:
    for name in ("HERMES_AGENT_ID", "RUNPOD_POD_ID", "HOSTNAME"):
        value = os.getenv(name, env_file_values.get(name, "") if env_file_values else "").strip()
        if value:
            return value
    return "hermes-agent"


def _load_env_file_values(path: Path) -> dict[str, str]:
    if not path.exists() or not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = _strip_env_value(value.strip())
    return values


def _strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_int(value: str, *, default: int) -> int:
    if not value.strip():
        return default
    return int(value)


def _parse_bool(value: str, *, default: bool) -> bool:
    if not value.strip():
        return default
    return value.strip().casefold() in {"1", "true", "yes", "y", "on"}


def _parse_bounded_int(value: str, *, default: int, minimum: int, maximum: int) -> int:
    parsed = _parse_int(value, default=default)
    return min(max(parsed, minimum), maximum)
