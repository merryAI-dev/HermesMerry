from merry_runtime.probabilistic_resolution import EntityObservation, ProbabilisticEntityResolver


def test_probabilistic_resolution_merges_service_name_with_legal_name_when_context_matches() -> None:
    existing = [
        EntityObservation(
            entity_id="ent_1",
            name="CareFarm Carbon Co Ltd",
            aliases=("CareFarm",),
            founder_name="Min Kim",
            homepage="https://carefarm.example",
            email="hello@carefarm.example",
            description="Carbon reduction MRV for small farms",
            region="Jeonbuk",
            observed_at="2026-05-01",
            source_channel="hankyung_ceo_interview",
        )
    ]
    candidate = EntityObservation(
        entity_id="tmp_1",
        name="CareFarm",
        aliases=("CareFarm Carbon",),
        founder_name="Min Kim",
        homepage="https://www.carefarm.example/apply",
        email="founder@carefarm.example",
        description="MRV tool reducing carbon emissions for rural farms",
        region="Jeonbuk",
        observed_at="2026-05-18",
        source_channel="info_mail",
    )

    result = ProbabilisticEntityResolver().resolve(candidate, existing)

    assert result.action == "merge"
    assert result.entity_id == "ent_1"
    assert result.probability >= 0.9
    assert result.features["domain_match"] == 1.0
    assert result.features["founder_match"] == 1.0


def test_probabilistic_resolution_requires_review_for_name_match_but_conflicting_identity() -> None:
    existing = [
        EntityObservation(
            entity_id="ent_1",
            name="Impact Foundry",
            founder_name="Min Kim",
            homepage="https://impactfoundry.example",
            email="min@impactfoundry.example",
            description="Manufacturing support for local makers",
            region="Busan",
            observed_at="2026-05-01",
            source_channel="external_referral",
        )
    ]
    candidate = EntityObservation(
        entity_id="tmp_2",
        name="Impact Foundry",
        founder_name="Jin Park",
        homepage="https://impactfoundry-ai.example",
        email="jin@impactfoundry-ai.example",
        description="AI sales assistant for SaaS teams",
        region="Seoul",
        observed_at="2026-05-18",
        source_channel="info_mail",
    )

    result = ProbabilisticEntityResolver().resolve(candidate, existing)

    assert result.action == "needs_review"
    assert result.entity_id == "ent_1"
    assert 0.45 <= result.probability < 0.85
    assert result.features["region_match"] == 0.0


def test_probabilistic_resolution_creates_new_entity_when_overlap_is_low() -> None:
    existing = [
        EntityObservation(
            entity_id="ent_1",
            name="CareFarm Carbon",
            homepage="https://carefarm.example",
            description="Carbon reduction MRV for farms",
            region="Jeonbuk",
            observed_at="2026-05-01",
            source_channel="hankyung_ceo_interview",
        )
    ]
    candidate = EntityObservation(
        entity_id="tmp_3",
        name="Merry AI",
        homepage="https://merry.ai",
        description="AI productivity workflow automation",
        region="Seoul",
        observed_at="2026-05-18",
        source_channel="info_mail",
    )

    result = ProbabilisticEntityResolver().resolve(candidate, existing)

    assert result.action == "create"
    assert result.entity_id == "tmp_3"
    assert result.probability < 0.45
