from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from merry_runtime.adapters.interfaces import StructuredStore
from merry_runtime.calibration import ReviewCalibrationExample, calibrate_priority_model, is_usable_decision
from merry_runtime.clock import now_kst
from merry_runtime.probabilistic_scoring import PriorityScoringModel


NO_USABLE_EXAMPLES_HASH = "no-usable-examples"


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
    corpus_hash = _corpus_hash(examples)
    existing_row = _coefficient_row(structured_store=structured_store, ac_id=ac_id)
    calibration = calibrate_priority_model(examples)
    coefficient_rows: list[dict[str, object]] = []
    if calibration.sample_count == 0:
        if existing_row and not _is_disabled_default_row(existing_row):
            coefficient_rows.append(
                _coefficient_row_from_model(
                    ac_id=ac_id,
                    model=PriorityScoringModel.default(),
                    sample_count=0,
                    corpus_hash=NO_USABLE_EXAMPLES_HASH,
                )
            )
    elif _is_unchanged_calibration(existing_row=existing_row, corpus_hash=corpus_hash, model_version=calibration.model.model_version):
        coefficient_rows = []
    else:
        coefficient_rows.append(
            _coefficient_row_from_model(
                ac_id=ac_id,
                model=calibration.model,
                sample_count=calibration.sample_count,
                corpus_hash=corpus_hash,
            )
        )
    if coefficient_rows:
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
                review_id=str(review.get("review_id", "")),
                card_id=str(review.get("card_id", "")),
                entity_id=str(card.get("entity_id", "")),
            )
        )
    return examples


def _coefficient_row(*, structured_store: StructuredStore, ac_id: str) -> dict[str, Any] | None:
    rows = structured_store.query_rows(
        sql="select * from ac_scoring_coefficients where ac_id=@ac_id",
        parameters={"ac_id": ac_id},
    )
    return rows[0] if rows else None


def _coefficient_row_from_model(
    *,
    ac_id: str,
    model: PriorityScoringModel,
    sample_count: int,
    corpus_hash: str,
) -> dict[str, object]:
    return {
        "ac_id": ac_id,
        "beta0": model.beta0,
        "fund_fit": model.fund_fit,
        "recruitment_fit": model.recruitment_fit,
        "impact_fit": model.impact_fit,
        "channel_trust": model.channel_trust,
        "multi_channel_signal": model.multi_channel_signal,
        "prior_decision": model.prior_decision,
        "freshness": model.freshness,
        "risk": model.risk,
        "sample_count": sample_count,
        "model_version": model.model_version,
        "corpus_hash": corpus_hash,
        "updated_at": _now(),
    }


def _corpus_hash(examples: list[ReviewCalibrationExample]) -> str:
    payload = [
        {
            "review_id": example.review_id,
            "card_id": example.card_id,
            "entity_id": example.entity_id,
            "decision": example.decision.casefold(),
            "fund_fit": round(example.fund_fit, 6),
            "recruitment_fit": round(example.recruitment_fit, 6),
            "impact_fit": round(example.impact_fit, 6),
        }
        for example in examples
        if is_usable_decision(example.decision)
    ]
    if not payload:
        return NO_USABLE_EXAMPLES_HASH
    payload.sort(key=lambda item: (item["review_id"], item["card_id"], item["entity_id"]))
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _is_unchanged_calibration(*, existing_row: dict[str, Any] | None, corpus_hash: str, model_version: str) -> bool:
    if not existing_row:
        return False
    return existing_row.get("corpus_hash") == corpus_hash and existing_row.get("model_version") == model_version


def _is_disabled_default_row(row: dict[str, Any]) -> bool:
    return int(row.get("sample_count", 0)) == 0 and row.get("model_version") == PriorityScoringModel.default().model_version


def _normalized(row: dict[str, Any], field_name: str, denominator: float) -> float:
    return max(0.0, min(1.0, float(row.get(field_name, 0.0)) / denominator))


def _short_digest(*parts: str) -> str:
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def _now() -> str:
    return now_kst()
