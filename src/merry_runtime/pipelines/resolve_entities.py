from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from merry_runtime.adapters.interfaces import ReviewQueue, StructuredStore
from merry_runtime.probabilistic_resolution import EntityObservation, ProbabilisticEntityResolver


@dataclass(frozen=True, slots=True)
class ResolveEntitiesResult:
    run_id: str
    entity_count: int
    event_count: int
    merge_candidate_count: int
    needs_review_count: int


def resolve_entities(
    *,
    structured_store: StructuredStore,
    review_queue: ReviewQueue,
    run_id: str | None = None,
    resolver: ProbabilisticEntityResolver | None = None,
) -> ResolveEntitiesResult:
    started_at = _now()
    run_id = run_id or f"run_resolve_{_short_digest(started_at)}"
    resolver = resolver or ProbabilisticEntityResolver()

    entity_rows = structured_store.query_rows(sql="select * from mother_entities", parameters={})
    alias_rows = structured_store.query_rows(sql="select * from entity_aliases", parameters={})
    aliases_by_entity = _aliases_by_entity(alias_rows)
    observations = sorted(
        (_observation_from_row(row, aliases_by_entity.get(str(row["entity_id"]), ())) for row in entity_rows),
        key=_observation_sort_key,
    )

    existing: list[EntityObservation] = []
    event_rows: list[dict[str, object]] = []
    for candidate in observations:
        resolution = resolver.resolve(candidate, existing)
        if resolution.action in {"merge", "needs_review"}:
            action = "merge_candidate" if resolution.action == "merge" else "needs_review"
            event_rows.append(
                {
                    "event_id": _event_id(run_id, candidate.entity_id, resolution.entity_id, action),
                    "candidate_entity_id": candidate.entity_id,
                    "matched_entity_id": resolution.entity_id,
                    "action": action,
                    "probability": resolution.probability,
                    "features_json": json.dumps(resolution.features, ensure_ascii=False, sort_keys=True),
                    "rationale": resolution.rationale,
                    "status": "pending_review",
                    "created_at": started_at,
                }
            )
        existing.append(candidate)

    structured_store.upsert_rows(table="entity_resolution_events", rows=event_rows, key_fields=("event_id",))
    if event_rows:
        review_queue.publish_cards(sheet_tab="entity_resolution", rows=event_rows)

    merge_candidate_count = sum(1 for row in event_rows if row["action"] == "merge_candidate")
    needs_review_count = sum(1 for row in event_rows if row["action"] == "needs_review")
    result = ResolveEntitiesResult(
        run_id=run_id,
        entity_count=len(observations),
        event_count=len(event_rows),
        merge_candidate_count=merge_candidate_count,
        needs_review_count=needs_review_count,
    )
    structured_store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": run_id,
                "job_name": "resolve-entities",
                "status": "success",
                "started_at": started_at,
                "finished_at": _now(),
                "input_count": len(observations),
                "output_count": len(event_rows),
                "error_message": "",
            }
        ],
        key_fields=("run_id",),
    )
    return result


def _observation_from_row(row: dict[str, Any], aliases: tuple[str, ...]) -> EntityObservation:
    return EntityObservation(
        entity_id=str(row["entity_id"]),
        name=str(row["name"]),
        aliases=aliases,
        founder_name=str(row.get("representative", "")),
        homepage=str(row.get("homepage", "")),
        email=str(row.get("email", "")),
        description=str(row.get("description") or row.get("industry") or ""),
        region=str(row.get("region", "")),
        observed_at=str(row.get("last_seen_at") or row.get("first_seen_at") or ""),
        source_channel=str(row.get("source_channel", "")),
    )


def _aliases_by_entity(rows: list[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        entity_id = str(row.get("entity_id", ""))
        alias = str(row.get("alias", ""))
        if entity_id and alias:
            grouped.setdefault(entity_id, []).append(alias)
    return {entity_id: tuple(sorted(aliases)) for entity_id, aliases in grouped.items()}


def _observation_sort_key(observation: EntityObservation) -> tuple[str, str]:
    return (observation.observed_at, observation.entity_id)


def _event_id(run_id: str, candidate_entity_id: str, matched_entity_id: str, action: str) -> str:
    return f"er_{_short_digest(run_id, candidate_entity_id, matched_entity_id, action)}"


def _short_digest(*parts: str) -> str:
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def _now() -> str:
    return datetime.now(UTC).isoformat()
