from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from merry_runtime.adapters.interfaces import ObjectStore, StructuredStore
from merry_runtime.ingestion.parsers import ParsedSource, parse_article, parse_email, parse_internal_memo, parse_referral_row
from merry_runtime.ontology import build_startup_graph
from merry_runtime.wiki_store import SQLiteWikiStore


@dataclass(frozen=True, slots=True)
class IngestResult:
    run_id: str
    raw_source_count: int
    entity_count: int
    signal_count: int


def ingest_sources(
    *,
    sources: list[dict[str, Any]],
    object_store: ObjectStore,
    structured_store: StructuredStore,
    wiki_store: SQLiteWikiStore | None = None,
    run_id: str | None = None,
) -> IngestResult:
    started_at = _now()
    run_id = run_id or _stable_run_id(sources)
    parsed_sources = [_parse_source(source) for source in sources]

    raw_rows: list[dict[str, object]] = []
    entity_rows: list[dict[str, object]] = []
    signal_rows: list[dict[str, object]] = []

    for parsed in parsed_sources:
        raw_uri = object_store.write_raw_text(
            path=parsed.raw_source.raw_text_path,
            text=parsed.raw_text,
            content_type="text/plain; charset=utf-8",
        )

        raw_row = asdict(parsed.raw_source)
        raw_row["url"] = raw_row.pop("uri")
        raw_row["raw_text_path"] = raw_uri
        raw_row["collected_at"] = raw_row.get("collected_at") or started_at
        raw_rows.append(raw_row)

        entity_row = asdict(parsed.entity)
        entity_row["first_seen_at"] = entity_row.get("first_seen_at") or started_at
        entity_row["last_seen_at"] = entity_row.get("last_seen_at") or started_at
        entity_rows.append(entity_row)

        for signal in parsed.signals:
            signal_row = asdict(signal)
            signal_row["tags"] = list(signal.tags)
            signal_row["detected_at"] = signal_row.get("detected_at") or started_at
            signal_rows.append(signal_row)

        if wiki_store:
            graph = build_startup_graph(entity=parsed.entity, raw_sources=[parsed.raw_source], signals=parsed.signals)
            wiki_store.upsert_startup_graph(
                graph,
                startup_id=parsed.entity.entity_id,
                operation="ingest",
                source_title=parsed.raw_source.title or parsed.entity.name,
            )

    structured_store.upsert_rows(table="raw_sources", rows=raw_rows, key_fields=("source_id",))
    structured_store.upsert_rows(table="mother_entities", rows=entity_rows, key_fields=("entity_id",))
    structured_store.upsert_rows(table="signals", rows=signal_rows, key_fields=("signal_id",))

    result = IngestResult(
        run_id=run_id,
        raw_source_count=len(raw_rows),
        entity_count=len(entity_rows),
        signal_count=len(signal_rows),
    )
    structured_store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": run_id,
                "job_name": "ingest-sources",
                "status": "success",
                "started_at": started_at,
                "finished_at": _now(),
                "input_count": len(sources),
                "output_count": len(raw_rows) + len(entity_rows) + len(signal_rows),
                "error_message": "",
            }
        ],
        key_fields=("run_id",),
    )
    return result


def _parse_source(source: dict[str, Any]) -> ParsedSource:
    channel = source.get("channel")
    payload = source.get("payload")
    if channel == "external_referral" and isinstance(payload, dict):
        return parse_referral_row(payload)
    if channel == "info_mail" and isinstance(payload, str):
        return parse_email(payload)
    if channel == "hankyung_ceo_interview" and isinstance(payload, str):
        return parse_article(payload)
    if channel == "internal_screening_memo" and isinstance(payload, str):
        return parse_internal_memo(payload)
    raise ValueError(f"Unsupported source channel or payload type: {channel}")


def _stable_run_id(sources: list[dict[str, Any]]) -> str:
    payload = json.dumps(sources, ensure_ascii=False, sort_keys=True)
    return f"run_{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:12]}"


def _now() -> str:
    return datetime.now(UTC).isoformat()
