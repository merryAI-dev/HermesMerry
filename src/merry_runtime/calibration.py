from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from merry_runtime.probabilistic_scoring import PriorityScoringModel


CALIBRATED_MODEL_VERSION = "calibrated-v1"

_DECISION_WEIGHTS = {
    "advance": 1.0,
    "watchlist": 0.35,
    "request_more_info": -0.25,
    "reject": -1.0,
}


@dataclass(frozen=True, slots=True)
class ReviewCalibrationExample:
    decision: str
    fund_fit: float
    recruitment_fit: float
    impact_fit: float
    review_id: str = ""
    card_id: str = ""
    entity_id: str = ""


@dataclass(frozen=True, slots=True)
class CalibrationConfig:
    learning_rate: float = 0.25
    max_delta: float = 0.2
    coefficient_floor: float = 0.0
    coefficient_ceiling: float = 5.0


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    model: PriorityScoringModel
    sample_count: int


def calibrate_priority_model(
    examples: Iterable[ReviewCalibrationExample],
    *,
    config: CalibrationConfig | None = None,
    default_model: PriorityScoringModel | None = None,
) -> CalibrationResult:
    config = config or CalibrationConfig()
    default_model = default_model or PriorityScoringModel.default()
    usable_examples = [example for example in examples if _decision_weight(example.decision) is not None]
    if not usable_examples:
        return CalibrationResult(model=default_model, sample_count=0)

    fund_delta = _feature_delta(usable_examples, "fund_fit", config)
    recruitment_delta = _feature_delta(usable_examples, "recruitment_fit", config)
    impact_delta = _feature_delta(usable_examples, "impact_fit", config)
    intercept_delta = _intercept_delta(usable_examples, config)

    return CalibrationResult(
        model=PriorityScoringModel(
            beta0=round(default_model.beta0 + intercept_delta, 6),
            fund_fit=_bounded(default_model.fund_fit + fund_delta, config),
            recruitment_fit=_bounded(default_model.recruitment_fit + recruitment_delta, config),
            impact_fit=_bounded(default_model.impact_fit + impact_delta, config),
            channel_trust=default_model.channel_trust,
            multi_channel_signal=default_model.multi_channel_signal,
            prior_decision=default_model.prior_decision,
            freshness=default_model.freshness,
            risk=default_model.risk,
            link=default_model.link,
            model_version=CALIBRATED_MODEL_VERSION,
        ),
        sample_count=len(usable_examples),
    )


def _feature_delta(examples: list[ReviewCalibrationExample], field_name: str, config: CalibrationConfig) -> float:
    aggregate = sum(_decision_weight(example.decision) * _clamp01(getattr(example, field_name)) for example in examples)
    raw_delta = config.learning_rate * aggregate / len(examples)
    return _clamp(raw_delta, -config.max_delta, config.max_delta)


def _intercept_delta(examples: list[ReviewCalibrationExample], config: CalibrationConfig) -> float:
    aggregate = sum(_decision_weight(example.decision) for example in examples)
    raw_delta = config.learning_rate * aggregate / len(examples) * 0.25
    return _clamp(raw_delta, -config.max_delta, config.max_delta)


def _decision_weight(decision: str) -> float | None:
    return _DECISION_WEIGHTS.get(decision.casefold())


def is_usable_decision(decision: str) -> bool:
    return _decision_weight(decision) is not None


def _bounded(value: float, config: CalibrationConfig) -> float:
    return round(_clamp(value, config.coefficient_floor, config.coefficient_ceiling), 6)


def _clamp01(value: float) -> float:
    return _clamp(value, 0.0, 1.0)


def _clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, value))
