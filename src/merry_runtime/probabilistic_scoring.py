from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PriorityFeatures:
    fund_fit: float
    recruitment_fit: float
    impact_fit: float
    channel_trust: float
    multi_channel_signal: float
    prior_decision: float
    freshness: float
    risk: float
    uncertainty: float
    thesis_conflict: float = 0.0
    new_channel: bool = False


@dataclass(frozen=True, slots=True)
class PriorityScore:
    utility: float
    probability: float
    queue_type: str
    rationale: str
    model_version: str


@dataclass(frozen=True, slots=True)
class PriorityScoringModel:
    beta0: float
    fund_fit: float
    recruitment_fit: float
    impact_fit: float
    channel_trust: float
    multi_channel_signal: float
    prior_decision: float
    freshness: float
    risk: float
    link: str = "logit"
    model_version: str = "manual-v1"

    @classmethod
    def default(cls) -> PriorityScoringModel:
        return cls(
            beta0=-2.0,
            fund_fit=1.5,
            recruitment_fit=1.2,
            impact_fit=1.8,
            channel_trust=1.4,
            multi_channel_signal=0.8,
            prior_decision=0.7,
            freshness=0.5,
            risk=1.1,
        )

    @classmethod
    def from_coefficient_row(cls, row: dict[str, Any]) -> PriorityScoringModel:
        default = cls.default()
        return cls(
            beta0=float(row.get("beta0", default.beta0)),
            fund_fit=float(row.get("fund_fit", default.fund_fit)),
            recruitment_fit=float(row.get("recruitment_fit", default.recruitment_fit)),
            impact_fit=float(row.get("impact_fit", default.impact_fit)),
            channel_trust=float(row.get("channel_trust", default.channel_trust)),
            multi_channel_signal=float(row.get("multi_channel_signal", default.multi_channel_signal)),
            prior_decision=float(row.get("prior_decision", default.prior_decision)),
            freshness=float(row.get("freshness", default.freshness)),
            risk=float(row.get("risk", default.risk)),
            link=default.link,
            model_version=str(row.get("model_version", default.model_version)),
        )

    def score(self, features: PriorityFeatures) -> PriorityScore:
        utility = (
            self.beta0
            + self.fund_fit * _clip(features.fund_fit)
            + self.recruitment_fit * _clip(features.recruitment_fit)
            + self.impact_fit * _clip(features.impact_fit)
            + self.channel_trust * _clip(features.channel_trust)
            + self.multi_channel_signal * _clip(features.multi_channel_signal)
            + self.prior_decision * _clip(features.prior_decision)
            + self.freshness * _clip(features.freshness)
            - self.risk * _clip(features.risk)
        )
        probability = sigmoid(utility) if self.link == "logit" else normal_cdf(utility)
        queue_type = route_candidate(
            probability=probability,
            uncertainty=features.uncertainty,
            impact_fit=features.impact_fit,
            thesis_conflict=features.thesis_conflict,
            new_channel=features.new_channel,
        )
        return PriorityScore(
            utility=round(utility, 4),
            probability=round(probability, 4),
            queue_type=queue_type,
            rationale=_rationale(features, utility, probability),
            model_version=self.model_version,
        )


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)


def normal_cdf(value: float) -> float:
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))


def route_candidate(
    *,
    probability: float,
    uncertainty: float,
    impact_fit: float,
    thesis_conflict: float,
    new_channel: bool,
) -> str:
    if probability >= 0.75:
        return "priority"
    if uncertainty >= 0.65:
        return "exploration"
    if impact_fit >= 0.8 and thesis_conflict >= 0.6:
        return "exploration"
    if impact_fit >= 0.75 and new_channel:
        return "exploration"
    if probability >= 0.4:
        return "watchlist"
    return "archive"


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def _rationale(features: PriorityFeatures, utility: float, probability: float) -> str:
    return (
        f"Utility={utility:.3f}; P(priority_review)={probability:.3f}; "
        f"FundFit={features.fund_fit:.2f}; RecruitmentFit={features.recruitment_fit:.2f}; "
        f"ImpactFit={features.impact_fit:.2f}; ChannelTrust={features.channel_trust:.2f}; "
        f"MultiChannelSignal={features.multi_channel_signal:.2f}; PriorDecision={features.prior_decision:.2f}; "
        f"Freshness={features.freshness:.2f}; Risk={features.risk:.2f}; Uncertainty={features.uncertainty:.2f}."
    )
