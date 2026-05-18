from __future__ import annotations

import re

from merry_runtime.models import ACProfile, ACScore, MotherEntity, Signal
from merry_runtime.normalization import normalized_region
from merry_runtime.probabilistic_scoring import PriorityFeatures, PriorityScoringModel


_WORD_PATTERN = re.compile(r"[0-9a-zA-Z가-힣]+")
_GROWTH_SIGNAL_TYPES = {"traction", "growth", "revenue", "investment", "partnership"}
_IMPACT_SIGNAL_TYPES = {"impact", "social_impact", "esg", "climate"}


def score_candidate(
    entity: MotherEntity,
    signals: list[Signal],
    profile: ACProfile,
    *,
    priority_model: PriorityScoringModel | None = None,
) -> ACScore:
    signal_tags = _signal_tags(signals)
    evidence_tokens = _evidence_tokens(signals)
    average_confidence = _average_confidence(signals)

    base_score = _base_score(signals, average_confidence)
    fund_fit_score = _tag_or_token_score(_tokens(profile.fund_purpose), signal_tags | evidence_tokens, max_score=15)
    recruiting_fit_score = _recruiting_score(entity, profile)
    hypothesis_fit_score = _hypothesis_score(entity, profile, signal_tags | evidence_tokens)
    impact_fit_score = _tag_or_token_score(_lower_set(profile.impact_priority), signal_tags | evidence_tokens, max_score=20)
    uncertainty = _uncertainty(signals, average_confidence)
    priority = (priority_model or PriorityScoringModel.default()).score(
        PriorityFeatures(
            fund_fit=fund_fit_score / 15,
            recruitment_fit=recruiting_fit_score / 15,
            impact_fit=impact_fit_score / 20,
            channel_trust=_channel_trust(signal_tags),
            multi_channel_signal=_multi_channel_signal(signals),
            prior_decision=_prior_decision(signal_tags),
            freshness=_freshness(signal_tags),
            risk=_risk(signal_tags),
            uncertainty=uncertainty,
            thesis_conflict=1.0 if "thesis_conflict" in signal_tags else 0.0,
            new_channel="new_channel" in signal_tags,
        )
    )
    total_score = round(
        min(100.0, base_score + fund_fit_score + recruiting_fit_score + hypothesis_fit_score + impact_fit_score),
        2,
    )

    rationale = _build_rationale(
        signals=signals,
        average_confidence=average_confidence,
        base_score=base_score,
        fund_fit_score=fund_fit_score,
        recruiting_fit_score=recruiting_fit_score,
        hypothesis_fit_score=hypothesis_fit_score,
        impact_fit_score=impact_fit_score,
    )

    return ACScore(
        score_id=f"score_{profile.ac_id}_{entity.entity_id}",
        ac_id=profile.ac_id,
        entity_id=entity.entity_id,
        base_score=round(base_score, 2),
        fund_fit_score=round(fund_fit_score, 2),
        recruiting_fit_score=round(recruiting_fit_score, 2),
        hypothesis_fit_score=round(hypothesis_fit_score, 2),
        impact_fit_score=round(impact_fit_score, 2),
        total_score=total_score,
        rationale=rationale,
        recommended_action=_recommended_action(total_score),
        priority_probability=priority.probability,
        priority_utility=priority.utility,
        queue_type=priority.queue_type,
        uncertainty=uncertainty,
        model_version=priority.model_version,
    )


def _base_score(signals: list[Signal], average_confidence: float) -> float:
    if not signals:
        return 0.0

    evidence_quality = average_confidence * 20
    evidence_volume = min(len(signals), 3) / 3 * 5
    growth_signal = 5 if any(signal.signal_type in _GROWTH_SIGNAL_TYPES for signal in signals) else 0
    impact_signal = 5 if any(signal.signal_type in _IMPACT_SIGNAL_TYPES for signal in signals) else 0
    return min(35.0, evidence_quality + evidence_volume + growth_signal + impact_signal)


def _recruiting_score(entity: MotherEntity, profile: ACProfile) -> float:
    entity_region = normalized_region(entity.region)
    preferred_regions = {normalized_region(region) for region in profile.region_preferences}
    if profile.recruiting_area:
        preferred_regions.add(normalized_region(profile.recruiting_area))
    return 15.0 if entity_region and entity_region in preferred_regions else 0.0


def _hypothesis_score(entity: MotherEntity, profile: ACProfile, observed_terms: set[str]) -> float:
    desired_terms = _lower_set(profile.hypothesis_tags) | _lower_set(profile.industry_preferences) | _lower_set(
        profile.tech_preferences
    )
    if entity.industry:
        observed_terms.add(entity.industry.casefold())
    return _tag_or_token_score(desired_terms, observed_terms, max_score=15)


def _tag_or_token_score(expected: set[str], observed: set[str], max_score: float) -> float:
    if not expected:
        return 0.0

    overlap = expected & observed
    if not overlap:
        return 0.0
    return min(max_score, max_score * len(overlap) / len(expected))


def _signal_tags(signals: list[Signal]) -> set[str]:
    return {tag.casefold() for signal in signals for tag in signal.tags}


def _evidence_tokens(signals: list[Signal]) -> set[str]:
    tokens: set[str] = set()
    for signal in signals:
        tokens |= _tokens(signal.evidence_text)
    return tokens


def _tokens(value: str) -> set[str]:
    return {match.group(0).casefold() for match in _WORD_PATTERN.finditer(value or "")}


def _lower_set(values: tuple[str, ...]) -> set[str]:
    return {value.casefold() for value in values if value}


def _average_confidence(signals: list[Signal]) -> float:
    if not signals:
        return 0.0
    return sum(max(0.0, min(1.0, signal.confidence)) for signal in signals) / len(signals)


def _recommended_action(total_score: float) -> str:
    if total_score >= 75:
        return "advance"
    if total_score >= 55:
        return "watchlist"
    if total_score >= 40:
        return "request_more_info"
    return "archive"


def _channel_trust(signal_tags: set[str]) -> float:
    if {"internal_screening_memo", "semi_qualified_signal", "external_referral", "referral_signal"} & signal_tags:
        return 0.9
    if {"info_mail", "inbound_intent"} & signal_tags:
        return 0.7
    if {"hankyung_ceo_interview", "public_cold_lead"} & signal_tags:
        return 0.35
    return 0.55


def _multi_channel_signal(signals: list[Signal]) -> float:
    return 1.0 if len({signal.source_id for signal in signals}) >= 2 else 0.0


def _prior_decision(signal_tags: set[str]) -> float:
    if "prior_advance" in signal_tags:
        return 1.0
    if "prior_watchlist" in signal_tags or "prior_hold" in signal_tags:
        return 0.45
    if "prior_reject" in signal_tags:
        return 0.0
    return 0.2


def _freshness(signal_tags: set[str]) -> float:
    if "stale" in signal_tags:
        return 0.1
    if "fresh" in signal_tags:
        return 1.0
    return 0.65


def _risk(signal_tags: set[str]) -> float:
    if "high_risk" in signal_tags:
        return 0.9
    if "risk" in signal_tags:
        return 0.5
    return 0.1


def _uncertainty(signals: list[Signal], average_confidence: float) -> float:
    sparse_penalty = 0.25 if len(signals) <= 1 else 0.0
    return round(max(0.0, min(1.0, (1.0 - average_confidence) + sparse_penalty)), 4)


def _build_rationale(
    *,
    signals: list[Signal],
    average_confidence: float,
    base_score: float,
    fund_fit_score: float,
    recruiting_fit_score: float,
    hypothesis_fit_score: float,
    impact_fit_score: float,
) -> str:
    signal_ids = ", ".join(signal.signal_id for signal in signals) or "none"
    evidence_note = "Strong evidence" if average_confidence >= 0.7 else "Weak evidence"
    impact_note = "Impact evidence present" if any(signal.signal_type in _IMPACT_SIGNAL_TYPES for signal in signals) else "No direct impact evidence"
    return (
        f"{evidence_note}: avg_confidence={average_confidence:.2f}; "
        f"{impact_note}; source_signals={signal_ids}; "
        f"components base={base_score:.1f}, fund={fund_fit_score:.1f}, "
        f"recruiting={recruiting_fit_score:.1f}, hypothesis={hypothesis_fit_score:.1f}, "
        f"impact={impact_fit_score:.1f}."
    )
