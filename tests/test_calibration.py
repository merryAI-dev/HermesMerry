import pytest

from merry_runtime.calibration import (
    CalibrationConfig,
    ReviewCalibrationExample,
    calibrate_priority_model,
)
from merry_runtime.probabilistic_scoring import PriorityScoringModel


def _example(decision: str, *, fund: float = 0.9, recruitment: float = 0.85, impact: float = 0.95) -> ReviewCalibrationExample:
    return ReviewCalibrationExample(
        decision=decision,
        fund_fit=fund,
        recruitment_fit=recruitment,
        impact_fit=impact,
    )


def test_positive_reviews_lift_relevant_coefficients_within_per_run_cap() -> None:
    default = PriorityScoringModel.default()
    config = CalibrationConfig(learning_rate=0.5, max_delta=0.2)
    examples = [_example("advance") for _ in range(10)]

    calibrated = calibrate_priority_model(examples, config=config)

    assert calibrated.model.fund_fit > default.fund_fit
    assert calibrated.model.recruitment_fit > default.recruitment_fit
    assert calibrated.model.impact_fit > default.impact_fit
    assert calibrated.model.fund_fit == pytest.approx(default.fund_fit + config.max_delta)
    assert calibrated.model.recruitment_fit == pytest.approx(default.recruitment_fit + config.max_delta)
    assert calibrated.model.impact_fit == pytest.approx(default.impact_fit + config.max_delta)
    assert calibrated.sample_count == 10
    assert calibrated.model.model_version == "calibrated-v1"


def test_reject_reviews_lower_relevant_coefficients_without_crossing_floor() -> None:
    default = PriorityScoringModel.default()
    config = CalibrationConfig(learning_rate=0.5, max_delta=0.4, coefficient_floor=1.0)
    examples = [_example("reject") for _ in range(10)]

    calibrated = calibrate_priority_model(examples, config=config)

    assert calibrated.model.fund_fit < default.fund_fit
    assert calibrated.model.recruitment_fit < default.recruitment_fit
    assert calibrated.model.impact_fit < default.impact_fit
    assert calibrated.model.fund_fit >= config.coefficient_floor
    assert calibrated.model.recruitment_fit >= config.coefficient_floor
    assert calibrated.model.impact_fit >= config.coefficient_floor


def test_single_outlier_review_cannot_move_any_coefficient_beyond_cap() -> None:
    default = PriorityScoringModel.default()
    config = CalibrationConfig(learning_rate=10.0, max_delta=0.05)

    calibrated = calibrate_priority_model([_example("advance", fund=1.0, recruitment=1.0, impact=1.0)], config=config)

    assert calibrated.model.fund_fit <= default.fund_fit + config.max_delta + 1e-9
    assert calibrated.model.recruitment_fit <= default.recruitment_fit + config.max_delta + 1e-9
    assert calibrated.model.impact_fit <= default.impact_fit + config.max_delta + 1e-9


def test_request_more_info_is_a_mild_negative_signal() -> None:
    default = PriorityScoringModel.default()
    config = CalibrationConfig(learning_rate=0.4, max_delta=0.2)

    calibrated = calibrate_priority_model([_example("request_more_info") for _ in range(10)], config=config)

    assert calibrated.model.fund_fit < default.fund_fit
    assert calibrated.model.fund_fit > default.fund_fit - config.max_delta
