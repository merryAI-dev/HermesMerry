from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from merry_runtime.adapters.interfaces import ReviewQueue, StructuredStore
from merry_runtime.clock import now_kst
from merry_runtime.models import ACProfile, MotherEntity, Signal
from merry_runtime.probabilistic_scoring import PriorityScoringModel
from merry_runtime.scoring import score_candidate


@dataclass(frozen=True, slots=True)
class ScoreResult:
    run_id: str
    score_count: int
    card_count: int


def score_candidates(
    *,
    structured_store: StructuredStore,
    review_queue: ReviewQueue,
    ac_id: str,
    run_id: str | None = None,
) -> ScoreResult:
    started_at = _now()
    run_id = run_id or f"run_score_{ac_id}_{_short_digest(started_at)}"
    entities = [_entity_from_row(row) for row in structured_store.query_rows(sql="select * from mother_entities", parameters={})]
    signals_by_entity = _signals_by_entity(
        [_signal_from_row(row) for row in structured_store.query_rows(sql="select * from signals", parameters={})]
    )
    profile = _profile_from_rows(
        structured_store.query_rows(sql="select * from ac_profiles where ac_id=@ac_id", parameters={"ac_id": ac_id}),
        ac_id,
    )
    priority_model = _priority_model_from_rows(
        structured_store.query_rows(
            sql="select * from ac_scoring_coefficients where ac_id=@ac_id",
            parameters={"ac_id": ac_id},
        )
    )
    existing_cards = {
        str(row["card_id"]): row
        for row in structured_store.query_rows(sql="select * from candidate_cards where ac_id=@ac_id", parameters={"ac_id": ac_id})
    }

    score_rows: list[dict[str, object]] = []
    card_rows: list[dict[str, object]] = []
    sheet_rows: list[dict[str, object]] = []
    for entity in entities:
        entity_signals = signals_by_entity.get(entity.entity_id, [])
        if not entity_signals:
            continue

        score = score_candidate(entity, entity_signals, profile, priority_model=priority_model)
        score_row = asdict(score)
        score_row["scored_at"] = started_at
        score_rows.append(score_row)

        card_id = f"card_{_short_digest(profile.ac_id, entity.entity_id)}"
        summary = _candidate_summary(entity, score.rationale)
        existing_card = existing_cards.get(card_id)
        card_row = {
            "card_id": card_id,
            "ac_id": profile.ac_id,
            "entity_id": entity.entity_id,
            "summary": summary,
            "recommended_action": score.recommended_action,
            "queue_type": score.queue_type,
            "status": str(existing_card.get("status", "new")) if existing_card else "new",
            "created_at": existing_card.get("created_at", started_at) if existing_card else started_at,
        }
        card_rows.append(card_row)
        if existing_card is None:
            sheet_rows.append(
                {
                    "card_id": card_id,
                    "entity_id": entity.entity_id,
                    "company": entity.name,
                    "region": entity.region,
                    "industry": entity.industry,
                    "total_score": score.total_score,
                    "recommended_action": score.recommended_action,
                    "queue_type": score.queue_type,
                    "priority_probability": score.priority_probability,
                    "rationale": score.rationale,
                    "decision": "",
                    "review_memo": "",
                    "reviewer": "",
                    "contact_email": entity.contact_email,
                }
            )

    structured_store.upsert_rows(table="ac_scores", rows=score_rows, key_fields=("score_id",))
    structured_store.upsert_rows(table="candidate_cards", rows=card_rows, key_fields=("card_id",))
    if sheet_rows:
        review_queue.publish_cards(sheet_tab=profile.ac_id, rows=sheet_rows)

    result = ScoreResult(run_id=run_id, score_count=len(score_rows), card_count=len(card_rows))
    structured_store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": run_id,
                "job_name": "score-candidates",
                "status": "success",
                "started_at": started_at,
                "finished_at": _now(),
                "input_count": len(entities),
                "output_count": len(card_rows),
                "error_message": "",
            }
        ],
        key_fields=("run_id",),
    )
    return result


def _entity_from_row(row: dict[str, Any]) -> MotherEntity:
    return MotherEntity(
        entity_id=str(row["entity_id"]),
        name=str(row["name"]),
        entity_type=str(row.get("entity_type", "startup")),
        normalized_name=row.get("normalized_name"),
        region=str(row.get("region", "")),
        industry=str(row.get("industry", "")),
        homepage=row.get("homepage"),
        representative=str(row.get("representative", "")),
        contact_email=str(row.get("contact_email", "")),
    )


def _signal_from_row(row: dict[str, Any]) -> Signal:
    tags = row.get("tags") or []
    return Signal(
        signal_id=str(row["signal_id"]),
        entity_id=str(row["entity_id"]),
        signal_type=str(row["signal_type"]),
        evidence_text=str(row["evidence_text"]),
        source_id=str(row["source_id"]),
        confidence=float(row["confidence"]),
        tags=tuple(str(tag) for tag in tags),
    )


def _profile_from_rows(rows: list[dict[str, Any]], ac_id: str) -> ACProfile:
    if not rows:
        raise ValueError(f"Unknown AC profile: {ac_id}")
    row = rows[0]
    return ACProfile(
        ac_id=str(row["ac_id"]),
        ac_name=str(row["ac_name"]),
        fund_purpose=str(row["fund_purpose"]),
        recruiting_area=str(row.get("recruiting_area", "")),
        hypothesis_tags=tuple(row.get("hypothesis_tags") or ()),
        impact_priority=tuple(row.get("impact_priority") or ()),
        region_preferences=tuple(row.get("region_preferences") or ()),
        industry_preferences=tuple(row.get("industry_preferences") or ()),
        tech_preferences=tuple(row.get("tech_preferences") or ()),
    )


def _priority_model_from_rows(rows: list[dict[str, Any]]) -> PriorityScoringModel:
    if not rows:
        return PriorityScoringModel.default()
    return PriorityScoringModel.from_coefficient_row(rows[0])


def _signals_by_entity(signals: list[Signal]) -> dict[str, list[Signal]]:
    grouped: dict[str, list[Signal]] = {}
    for signal in signals:
        grouped.setdefault(signal.entity_id, []).append(signal)
    return grouped


def _candidate_summary(entity: MotherEntity, rationale: str) -> str:
    parts = [entity.name]
    if entity.region:
        parts.append(entity.region)
    if entity.industry:
        parts.append(entity.industry)
    return " / ".join(parts) + f" - {rationale}"


def _short_digest(*parts: str) -> str:
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def _now() -> str:
    return now_kst()
