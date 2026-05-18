from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from merry_runtime.adapters.interfaces import StructuredStore
from merry_runtime.calibration import ReviewCalibrationExample, calibrate_priority_model


@dataclass(frozen=True, slots=True)
class CalibrationPipelineResult:
    run_id: str
    sample_count: int
    coefficient_count: int


def calibrate_scores(
    *,
    structured_store: StructuredStore,
    ac_id: str,
    run_id: str | None = None,
) -> CalibrationPipelineResult:
    started_at = _now()
    run_id = run_id or f"run_calibrate_{ac_id}_{_short_digest(started_at)}"
    examples = _load_examples(structured_store=structured_store, ac_id=ac_id)
    calibration = calibrate_priority_model(examples)
    coefficient_rows: list[dict[str, object]] = []
    if calibration.sample_count > 0:
        coefficient_rows.append(
            {
                "ac_id": ac_id,
                "beta0": calibration.model.beta0,
                "fund_fit": calibration.model.fund_fit,
                "recruitment_fit": calibration.model.recruitment_fit,
                "impact_fit": calibration.model.impact_fit,
                "channel_trust": calibration.model.channel_trust,
                "multi_channel_signal": calibration.model.multi_channel_signal,
                "prior_decision": calibration.model.prior_decision,
                "freshness": calibration.model.freshness,
                "risk": calibration.model.risk,
                "sample_count": calibration.sample_count,
                "model_version": calibration.model.model_version,
                "updated_at": _now(),
            }
        )
        structured_store.upsert_rows(
            table="ac_scoring_coefficients",
            rows=coefficient_rows,
            key_fields=("ac_id",),
        )

    result = CalibrationPipelineResult(
        run_id=run_id,
        sample_count=calibration.sample_count,
        coefficient_count=len(coefficient_rows),
    )
    structured_store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": run_id,
                "job_name": "calibrate-scores",
                "status": "success",
                "started_at": started_at,
                "finished_at": _now(),
                "input_count": calibration.sample_count,
                "output_count": len(coefficient_rows),
                "error_message": "",
            }
        ],
        key_fields=("run_id",),
    )
    return result


def _load_examples(*, structured_store: StructuredStore, ac_id: str) -> list[ReviewCalibrationExample]:
    cards = {
        str(row["card_id"]): row
        for row in structured_store.query_rows(
            sql="select * from candidate_cards where ac_id=@ac_id",
            parameters={"ac_id": ac_id},
        )
    }
    scores = {
        str(row["entity_id"]): row
        for row in structured_store.query_rows(
            sql="select * from ac_scores where ac_id=@ac_id",
            parameters={"ac_id": ac_id},
        )
    }
    reviews = structured_store.query_rows(sql="select * from reviews", parameters={})

    examples: list[ReviewCalibrationExample] = []
    for review in reviews:
        card = cards.get(str(review.get("card_id", "")))
        if not card:
            continue
        score = scores.get(str(card.get("entity_id", "")))
        if not score:
            continue
        examples.append(
            ReviewCalibrationExample(
                decision=str(review.get("decision", "")),
                fund_fit=_normalized(score, "fund_fit_score", 15.0),
                recruitment_fit=_normalized(score, "recruiting_fit_score", 15.0),
                impact_fit=_normalized(score, "impact_fit_score", 20.0),
            )
        )
    return examples


def _normalized(row: dict[str, Any], field_name: str, denominator: float) -> float:
    return max(0.0, min(1.0, float(row.get(field_name, 0.0)) / denominator))


def _short_digest(*parts: str) -> str:
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def _now() -> str:
    return datetime.now(UTC).isoformat()
