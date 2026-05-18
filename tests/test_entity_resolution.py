from merry_runtime.entity_resolution import EntityResolver
from merry_runtime.models import EntityAlias, MotherEntity
from merry_runtime.normalization import normalize_company_name, normalize_domain


def test_normalizes_company_names_and_domains() -> None:
    assert normalize_company_name("Merry AI, Inc.") == "merry ai"
    assert normalize_company_name("(주) 메리테크") == "메리테크"
    assert normalize_domain("https://www.merry.ai/about?ref=ceo") == "merry.ai"


def test_resolves_same_homepage_domain_to_existing_entity() -> None:
    existing = [
        MotherEntity(
            entity_id="ent_001",
            name="Merry AI",
            region="Seoul",
            industry="AI",
            homepage="https://merry.ai",
        )
    ]
    candidate = MotherEntity(
        entity_id="tmp_001",
        name="Merry AI Inc.",
        region="Seoul",
        industry="AI",
        homepage="https://www.merry.ai/jobs",
    )

    result = EntityResolver().resolve(candidate, existing)

    assert result.action == "merge"
    assert result.entity_id == "ent_001"
    assert result.reason == "homepage_domain"


def test_resolves_known_alias_to_existing_entity() -> None:
    existing = [
        MotherEntity(
            entity_id="ent_002",
            name="Merry Climate",
            region="Jeonbuk",
            industry="Climate",
        )
    ]
    aliases = [
        EntityAlias(
            entity_id="ent_002",
            alias="Merry Climate Labs",
            normalized_alias=normalize_company_name("Merry Climate Labs"),
        )
    ]
    candidate = MotherEntity(
        entity_id="tmp_002",
        name="Merry Climate Labs",
        region="Jeonbuk",
        industry="Climate",
    )

    result = EntityResolver().resolve(candidate, existing, aliases)

    assert result.action == "merge"
    assert result.entity_id == "ent_002"
    assert result.reason == "known_alias"


def test_same_name_different_region_requires_human_review() -> None:
    existing = [
        MotherEntity(
            entity_id="ent_003",
            name="Impact Foundry",
            region="Busan",
            industry="Manufacturing",
        )
    ]
    candidate = MotherEntity(
        entity_id="tmp_003",
        name="Impact Foundry",
        region="Seoul",
        industry="Manufacturing",
    )

    result = EntityResolver().resolve(candidate, existing)

    assert result.action == "needs_review"
    assert result.entity_id == "ent_003"
    assert result.reason == "name_match_region_conflict"
