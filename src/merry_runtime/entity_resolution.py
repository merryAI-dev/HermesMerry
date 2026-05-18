from __future__ import annotations

from dataclasses import dataclass

from merry_runtime.models import EntityAlias, MotherEntity
from merry_runtime.normalization import normalize_company_name, normalize_domain, normalized_region


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    action: str
    entity_id: str
    reason: str


class EntityResolver:
    """Deterministic first-pass entity resolution for Mother DB ingestion."""

    def resolve(
        self,
        candidate: MotherEntity,
        existing_entities: list[MotherEntity],
        aliases: list[EntityAlias] | None = None,
    ) -> ResolutionResult:
        aliases = aliases or []
        candidate_domain = normalize_domain(candidate.homepage)
        candidate_name = _entity_normalized_name(candidate)
        candidate_region = normalized_region(candidate.region)

        if candidate_domain:
            for entity in existing_entities:
                if candidate_domain == normalize_domain(entity.homepage):
                    return ResolutionResult("merge", entity.entity_id, "homepage_domain")

        for alias in aliases:
            if candidate_name and candidate_name == alias.normalized_alias:
                return ResolutionResult("merge", alias.entity_id, "known_alias")

        for entity in existing_entities:
            existing_name = _entity_normalized_name(entity)
            if not candidate_name or candidate_name != existing_name:
                continue

            existing_region = normalized_region(entity.region)
            if candidate_region and existing_region and candidate_region != existing_region:
                return ResolutionResult("needs_review", entity.entity_id, "name_match_region_conflict")
            return ResolutionResult("merge", entity.entity_id, "normalized_name")

        return ResolutionResult("create", candidate.entity_id, "new_entity")


def _entity_normalized_name(entity: MotherEntity) -> str:
    return entity.normalized_name or normalize_company_name(entity.name)
