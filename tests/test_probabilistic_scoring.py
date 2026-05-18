from merry_runtime.probabilistic_scoring import (
    PriorityFeatures,
    PriorityScoringModel,
    normal_cdf,
    route_candidate,
    sigmoid,
)


def test_sigmoid_and_probit_probability_transforms_are_monotonic() -> None:
    assert sigmoid(-1.0) < sigmoid(0.0) < sigmoid(1.0)
    assert normal_cdf(-1.0) < normal_cdf(0.0) < normal_cdf(1.0)
    assert sigmoid(0.0) == 0.5
    assert normal_cdf(0.0) == 0.5


def test_priority_model_lifts_referral_internal_review_and_multi_channel_signals() -> None:
    model = PriorityScoringModel.default()
    weak = PriorityFeatures(
        fund_fit=0.4,
        recruitment_fit=0.4,
        impact_fit=0.4,
        channel_trust=0.2,
        multi_channel_signal=0.0,
        prior_decision=0.0,
        freshness=0.5,
        risk=0.2,
        uncertainty=0.2,
    )
    strong = PriorityFeatures(
        fund_fit=0.8,
        recruitment_fit=0.8,
        impact_fit=0.9,
        channel_trust=0.9,
        multi_channel_signal=1.0,
        prior_decision=0.5,
        freshness=0.8,
        risk=0.1,
        uncertainty=0.2,
    )

    weak_score = model.score(weak)
    strong_score = model.score(strong)

    assert strong_score.utility > weak_score.utility
    assert strong_score.probability > weak_score.probability
    assert strong_score.queue_type == "priority"
    assert "ChannelTrust" in strong_score.rationale


def test_exploration_policy_routes_uncertain_or_thesis_conflicting_candidates() -> None:
    assert route_candidate(probability=0.82, uncertainty=0.2, impact_fit=0.8, thesis_conflict=0.0, new_channel=False) == "priority"
    assert route_candidate(probability=0.48, uncertainty=0.75, impact_fit=0.5, thesis_conflict=0.0, new_channel=False) == "exploration"
    assert route_candidate(probability=0.5, uncertainty=0.2, impact_fit=0.85, thesis_conflict=0.9, new_channel=False) == "exploration"
    assert route_candidate(probability=0.52, uncertainty=0.2, impact_fit=0.8, thesis_conflict=0.0, new_channel=True) == "exploration"
    assert route_candidate(probability=0.2, uncertainty=0.2, impact_fit=0.2, thesis_conflict=0.0, new_channel=False) == "archive"
