from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from merry_runtime.adapters.interfaces import StructuredStore
from merry_runtime.ingestion.ac_profile_parser import parse_ac_hypothesis_report
from merry_runtime.wiki_store import SQLiteWikiStore


@dataclass(frozen=True, slots=True)
class IngestACProfilesResult:
    run_id: str
    profile_count: int


def ingest_ac_profiles(
    *,
    sources: list[dict[str, Any]],
    structured_store: StructuredStore,
    wiki_store: SQLiteWikiStore | None = None,
    run_id: str | None = None,
) -> IngestACProfilesResult:
    started_at = _now()
    run_id = run_id or _stable_run_id(sources)
    profiles = [parse_ac_hypothesis_report(_source_text(source)) for source in sources]

    profile_rows: list[dict[str, object]] = []
    for profile, source in zip(profiles, sources, strict=True):
        row = asdict(profile)
        for key, value in row.items():
            if isinstance(value, tuple):
                row[key] = list(value)
        profile_rows.append(row)
        if wiki_store:
            wiki_store.upsert_ac_profile(
                profile,
                operation="ingest-ac-profile",
                source_title=str(source.get("title") or profile.ac_name),
            )

    structured_store.upsert_rows(table="ac_profiles", rows=profile_rows, key_fields=("ac_id",))
    result = IngestACProfilesResult(run_id=run_id, profile_count=len(profile_rows))
    structured_store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": run_id,
                "job_name": "ingest-ac-profiles",
                "status": "success",
                "started_at": started_at,
                "finished_at": _now(),
                "input_count": len(sources),
                "output_count": len(profile_rows),
                "error_message": "",
            }
        ],
        key_fields=("run_id",),
    )
    return result


def _source_text(source: dict[str, Any]) -> str:
    for key in ("payload", "text", "report", "body"):
        value = source.get(key)
        if isinstance(value, str):
            return value
    raise ValueError("AC profile source must include a text payload")


def _stable_run_id(sources: list[dict[str, Any]]) -> str:
    payload = json.dumps(sources, ensure_ascii=False, sort_keys=True)
    return f"run_ingest_ac_profiles_{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:12]}"


def _now() -> str:
    return datetime.now(UTC).isoformat()
