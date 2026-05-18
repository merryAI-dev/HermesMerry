from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class RuntimeConfigError(ValueError):
    pass


_BIGQUERY_WRITE_MODES = {"merge", "append"}


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    project_id: str
    dataset_id: str
    raw_bucket: str
    review_sheet_id: str = ""
    slack_channel: str = ""
    gmail_label_id: str = ""
    default_ac_id: str = ""
    wiki_root: Path = Path("/tmp/hermes-merry-wiki")
    object_store_backend: str = "gcs"
    raw_root: Path = Path("/workspace/hermes/raw")
    bigquery_write_mode: str = "merge"
    agent_loop_jobs: tuple[str, ...] = (
        "ingest-sources",
        "resolve-entities",
        "score-candidates",
        "sync-review-sheet",
        "calibrate-scores",
    )
    agent_loop_interval_seconds: int = 1800
    agent_loop_max_cycles: int = 0

    @classmethod
    def from_env(cls) -> RuntimeConfig:
        return cls(
            project_id=os.getenv("GCP_PROJECT_ID", ""),
            dataset_id=os.getenv("BIGQUERY_DATASET", ""),
            raw_bucket=os.getenv("RAW_BUCKET", ""),
            review_sheet_id=os.getenv("REVIEW_SHEET_ID", ""),
            slack_channel=os.getenv("SLACK_CHANNEL", ""),
            gmail_label_id=os.getenv("GMAIL_LABEL_ID", ""),
            default_ac_id=os.getenv("AC_ID", ""),
            wiki_root=Path(os.getenv("WIKI_ROOT", "/tmp/hermes-merry-wiki")),
            object_store_backend=os.getenv("OBJECT_STORE_BACKEND", "gcs"),
            raw_root=Path(os.getenv("RAW_ROOT", "/workspace/hermes/raw")),
            bigquery_write_mode=_parse_bigquery_write_mode(os.getenv("BIGQUERY_WRITE_MODE", "merge")),
            agent_loop_jobs=_parse_jobs(os.getenv("AGENT_LOOP_JOBS", "")),
            agent_loop_interval_seconds=_parse_int(os.getenv("AGENT_LOOP_INTERVAL_SECONDS", ""), default=1800),
            agent_loop_max_cycles=_parse_int(os.getenv("AGENT_LOOP_MAX_CYCLES", ""), default=0),
        )

    def validate_for_job(self, job_name: str, *, has_inline_sources: bool = False) -> None:
        self._validate_bigquery_write_mode()
        required = ["GCP_PROJECT_ID", "BIGQUERY_DATASET"]
        if job_name == "ingest-sources":
            if self.object_store_backend == "local":
                required.append("RAW_ROOT")
            else:
                required.append("RAW_BUCKET")
            if not has_inline_sources:
                required.append("GMAIL_LABEL_ID")
        elif job_name == "ingest-ac-profiles":
            pass
        elif job_name in {"score-candidates", "sync-review-sheet"}:
            required.extend(["REVIEW_SHEET_ID", "AC_ID"])
        elif job_name == "calibrate-scores":
            required.append("AC_ID")
        elif job_name == "weekly-summary":
            required.append("SLACK_CHANNEL")
        elif job_name == "resolve-entities":
            pass
        else:
            raise RuntimeConfigError(f"Unknown job: {job_name}")

        missing = [name for name in required if not self._value_for_env_name(name)]
        if missing:
            raise RuntimeConfigError(f"Missing required environment for {job_name}: {', '.join(missing)}")

    def validate_for_loop(self, *, max_cycles: int) -> None:
        self._validate_bigquery_write_mode()
        if self.bigquery_write_mode == "append" and max_cycles != 1:
            raise RuntimeConfigError(
                "BIGQUERY_WRITE_MODE=append is limited to one-cycle canaries; "
                "set AGENT_LOOP_MAX_CYCLES=1 or use BIGQUERY_WRITE_MODE=merge for an always-on loop"
            )

    def _validate_bigquery_write_mode(self) -> None:
        if self.bigquery_write_mode not in _BIGQUERY_WRITE_MODES:
            allowed = ", ".join(sorted(_BIGQUERY_WRITE_MODES))
            raise RuntimeConfigError(
                f"Unsupported BIGQUERY_WRITE_MODE={self.bigquery_write_mode!r}; expected one of: {allowed}"
            )

    def _value_for_env_name(self, name: str) -> str:
        return {
            "GCP_PROJECT_ID": self.project_id,
            "BIGQUERY_DATASET": self.dataset_id,
            "RAW_BUCKET": self.raw_bucket,
            "REVIEW_SHEET_ID": self.review_sheet_id,
            "SLACK_CHANNEL": self.slack_channel,
            "GMAIL_LABEL_ID": self.gmail_label_id,
            "AC_ID": self.default_ac_id,
            "RAW_ROOT": str(self.raw_root),
        }[name]


def _parse_jobs(value: str) -> tuple[str, ...]:
    if not value.strip():
        return (
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


def _parse_int(value: str, *, default: int) -> int:
    if not value.strip():
        return default
    return int(value)
