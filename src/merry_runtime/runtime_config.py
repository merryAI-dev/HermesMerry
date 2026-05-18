from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class RuntimeConfigError(ValueError):
    pass


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
        )

    def validate_for_job(self, job_name: str, *, has_inline_sources: bool = False) -> None:
        required = ["GCP_PROJECT_ID", "BIGQUERY_DATASET"]
        if job_name == "ingest-sources":
            required.append("RAW_BUCKET")
            if not has_inline_sources:
                required.append("GMAIL_LABEL_ID")
        elif job_name == "ingest-ac-profiles":
            pass
        elif job_name in {"score-candidates", "sync-review-sheet"}:
            required.extend(["REVIEW_SHEET_ID", "AC_ID"])
        elif job_name == "weekly-summary":
            required.append("SLACK_CHANNEL")
        elif job_name == "resolve-entities":
            pass
        else:
            raise RuntimeConfigError(f"Unknown job: {job_name}")

        missing = [name for name in required if not self._value_for_env_name(name)]
        if missing:
            raise RuntimeConfigError(f"Missing required environment for {job_name}: {', '.join(missing)}")

    def _value_for_env_name(self, name: str) -> str:
        return {
            "GCP_PROJECT_ID": self.project_id,
            "BIGQUERY_DATASET": self.dataset_id,
            "RAW_BUCKET": self.raw_bucket,
            "REVIEW_SHEET_ID": self.review_sheet_id,
            "SLACK_CHANNEL": self.slack_channel,
            "GMAIL_LABEL_ID": self.gmail_label_id,
            "AC_ID": self.default_ac_id,
        }[name]
