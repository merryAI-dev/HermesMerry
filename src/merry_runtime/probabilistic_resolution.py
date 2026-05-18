from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from merry_runtime.normalization import normalize_company_name, normalize_domain, normalized_region


@dataclass(frozen=True, slots=True)
class EntityObservation:
    entity_id: str
    name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    founder_name: str = ""
    homepage: str = ""
    email: str = ""
    description: str = ""
    region: str = ""
    observed_at: str = ""
    source_channel: str = ""


@dataclass(frozen=True, slots=True)
class ProbabilisticResolutionResult:
    action: str
    entity_id: str
    probability: float
    features: dict[str, float]
    rationale: str


class ProbabilisticEntityResolver:
    def __init__(self, merge_threshold: float = 0.85, review_threshold: float = 0.45) -> None:
        self.merge_threshold = merge_threshold
        self.review_threshold = review_threshold

    def resolve(
        self,
        candidate: EntityObservation,
        existing: list[EntityObservation],
    ) -> ProbabilisticResolutionResult:
        if not existing:
            return ProbabilisticResolutionResult("create", candidate.entity_id, 0.0, {}, "No existing observations.")

        scored = [(entity, _same_entity_probability(candidate, entity)) for entity in existing]
        best_entity, best = max(scored, key=lambda item: item[1].probability)
        if best.probability >= self.merge_threshold:
            action = "merge"
            entity_id = best_entity.entity_id
        elif best.probability >= self.review_threshold:
            action = "needs_review"
            entity_id = best_entity.entity_id
        else:
            action = "create"
            entity_id = candidate.entity_id

        return ProbabilisticResolutionResult(
            action=action,
            entity_id=entity_id,
            probability=round(best.probability, 4),
            features=best.features,
            rationale=best.rationale,
        )


@dataclass(frozen=True, slots=True)
class _Score:
    probability: float
    features: dict[str, float]
    rationale: str


def _same_entity_probability(candidate: EntityObservation, existing: EntityObservation) -> _Score:
    features = {
        "domain_match": _domain_match(candidate, existing),
        "email_domain_match": _email_domain_match(candidate, existing),
        "founder_match": _founder_match(candidate, existing),
        "name_or_alias_overlap": _name_or_alias_overlap(candidate, existing),
        "description_overlap": _description_overlap(candidate, existing),
        "region_match": _region_match(candidate, existing),
        "source_time_context": _source_time_context(candidate, existing),
    }
    utility = (
        -2.4
        + 3.2 * features["domain_match"]
        + 1.4 * features["email_domain_match"]
        + 1.6 * features["founder_match"]
        + 1.8 * features["name_or_alias_overlap"]
        + 1.2 * features["description_overlap"]
        + 0.8 * features["region_match"]
        + 0.4 * features["source_time_context"]
    )
    probability = 1.0 / (1.0 + math.exp(-utility))
    rationale = ", ".join(f"{name}={value:.2f}" for name, value in features.items())
    return _Score(probability=probability, features=features, rationale=rationale)


def _domain_match(candidate: EntityObservation, existing: EntityObservation) -> float:
    candidate_domain = normalize_domain(candidate.homepage)
    existing_domain = normalize_domain(existing.homepage)
    return 1.0 if candidate_domain and candidate_domain == existing_domain else 0.0


def _email_domain_match(candidate: EntityObservation, existing: EntityObservation) -> float:
    candidate_domain = _email_domain(candidate.email)
    existing_domain = _email_domain(existing.email)
    return 1.0 if candidate_domain and candidate_domain == existing_domain else 0.0


def _founder_match(candidate: EntityObservation, existing: EntityObservation) -> float:
    candidate_founder = normalize_company_name(candidate.founder_name)
    existing_founder = normalize_company_name(existing.founder_name)
    return 1.0 if candidate_founder and candidate_founder == existing_founder else 0.0


def _name_or_alias_overlap(candidate: EntityObservation, existing: EntityObservation) -> float:
    candidate_names = {normalize_company_name(candidate.name), *(normalize_company_name(alias) for alias in candidate.aliases)}
    existing_names = {normalize_company_name(existing.name), *(normalize_company_name(alias) for alias in existing.aliases)}
    candidate_names.discard("")
    existing_names.discard("")
    if candidate_names & existing_names:
        return 1.0
    candidate_tokens = set().union(*(_tokens(name) for name in candidate_names)) if candidate_names else set()
    existing_tokens = set().union(*(_tokens(name) for name in existing_names)) if existing_names else set()
    return _jaccard(candidate_tokens, existing_tokens)


def _description_overlap(candidate: EntityObservation, existing: EntityObservation) -> float:
    return _jaccard(_tokens(candidate.description), _tokens(existing.description))


def _region_match(candidate: EntityObservation, existing: EntityObservation) -> float:
    candidate_region = normalized_region(candidate.region)
    existing_region = normalized_region(existing.region)
    if not candidate_region or not existing_region:
        return 0.5
    return 1.0 if candidate_region == existing_region else 0.0


def _source_time_context(candidate: EntityObservation, existing: EntityObservation) -> float:
    if not candidate.observed_at or not existing.observed_at:
        return 0.5
    return 1.0 if candidate.observed_at[:4] == existing.observed_at[:4] else 0.2


def _email_domain(email: str) -> str:
    if "@" not in email:
        return ""
    return normalize_domain(email.split("@", 1)[1])


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[0-9a-zA-Z가-힣]+", value or "") if len(token) > 1}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
