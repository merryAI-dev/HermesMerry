from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Decision(StrEnum):
    ADVANCE = "advance"
    WATCHLIST = "watchlist"
    REJECT = "reject"
    REQUEST_MORE_INFO = "request_more_info"


@dataclass(slots=True)
class RawSource:
    source_id: str
    source_type: str
    channel: str
    uri: str
    title: str = ""
    raw_text_path: str = ""
    published_at: str | None = None
    collected_at: str | None = None
    checksum: str = ""
    contains_pii: bool = False


@dataclass(slots=True)
class MotherEntity:
    entity_id: str
    name: str
    entity_type: str = "startup"
    normalized_name: str | None = None
    region: str = ""
    industry: str = ""
    homepage: str | None = None
    representative: str = ""
    first_seen_at: str | None = None
    last_seen_at: str | None = None


@dataclass(slots=True)
class EntityAlias:
    entity_id: str
    alias: str
    normalized_alias: str
    alias_id: str | None = None
    source_id: str | None = None
    created_at: str | None = None


@dataclass(slots=True)
class Signal:
    signal_id: str
    entity_id: str
    signal_type: str
    evidence_text: str
    source_id: str
    confidence: float
    tags: tuple[str, ...] = field(default_factory=tuple)
    detected_at: str | None = None


@dataclass(slots=True)
class ACProfile:
    ac_id: str
    ac_name: str
    fund_purpose: str
    recruiting_area: str
    hypothesis_tags: tuple[str, ...] = field(default_factory=tuple)
    impact_priority: tuple[str, ...] = field(default_factory=tuple)
    region_preferences: tuple[str, ...] = field(default_factory=tuple)
    industry_preferences: tuple[str, ...] = field(default_factory=tuple)
    tech_preferences: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class ACScore:
    score_id: str
    ac_id: str
    entity_id: str
    base_score: float
    fund_fit_score: float
    recruiting_fit_score: float
    hypothesis_fit_score: float
    impact_fit_score: float
    total_score: float
    rationale: str
    recommended_action: str
    priority_probability: float = 0.0
    priority_utility: float = 0.0
    queue_type: str = "archive"
    uncertainty: float = 0.0
    model_version: str = "manual-v1"


@dataclass(slots=True)
class CandidateCard:
    card_id: str
    ac_id: str
    entity_id: str
    summary: str
    recommended_action: str
    queue_type: str = "archive"
    status: str = "new"
    created_at: str | None = None


@dataclass(slots=True)
class Review:
    card_id: str
    reviewer: str
    decision: Decision
    memo: str = ""
    review_id: str | None = None
    reviewed_at: str | None = None
