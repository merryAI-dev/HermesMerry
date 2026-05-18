from merry_runtime.models import ACProfile, MotherEntity, Signal
from merry_runtime.scoring import score_candidate


def test_scores_candidate_with_evidence_and_ac_specific_fit() -> None:
    entity = MotherEntity(
        entity_id="ent_climate",
        name="CareFarm Carbon",
        region="Jeonbuk",
        industry="AgriTech",
        homepage="https://carefarm.example",
    )
    signals = [
        Signal(
            signal_id="sig_impact",
            entity_id="ent_climate",
            signal_type="impact",
            evidence_text="Reduces carbon emissions for small farms with verified pilots.",
            source_id="src_ceo",
            confidence=0.92,
            tags=("climate", "carbon", "rural", "impact"),
        ),
        Signal(
            signal_id="sig_growth",
            entity_id="ent_climate",
            signal_type="traction",
            evidence_text="Paid pilots with three agricultural cooperatives.",
            source_id="src_mail",
            confidence=0.84,
            tags=("traction", "pilot", "agritech"),
        ),
    ]
    profile = ACProfile(
        ac_id="ac_climate",
        ac_name="Climate Impact AC",
        fund_purpose="climate impact fund",
        recruiting_area="Jeonbuk",
        hypothesis_tags=("climate", "agritech"),
        impact_priority=("carbon", "rural"),
        region_preferences=("Jeonbuk",),
        industry_preferences=("AgriTech",),
    )

    score = score_candidate(entity, signals, profile)

    assert score.entity_id == "ent_climate"
    assert score.ac_id == "ac_climate"
    assert score.total_score >= 80
    assert score.recommended_action == "advance"
    assert score.priority_probability >= 0.75
    assert score.queue_type == "priority"
    assert "sig_impact" in score.rationale
    assert "impact evidence" in score.rationale.lower()


def test_scores_low_when_evidence_is_weak_and_profile_fit_is_missing() -> None:
    entity = MotherEntity(
        entity_id="ent_unclear",
        name="Generic SaaS",
        region="Seoul",
        industry="SalesTech",
    )
    signals = [
        Signal(
            signal_id="sig_weak",
            entity_id="ent_unclear",
            signal_type="mention",
            evidence_text="Mentioned in a newsletter without detail.",
            source_id="src_news",
            confidence=0.31,
            tags=("newsletter",),
        )
    ]
    profile = ACProfile(
        ac_id="ac_climate",
        ac_name="Climate Impact AC",
        fund_purpose="climate impact fund",
        recruiting_area="Jeonbuk",
        hypothesis_tags=("climate", "agritech"),
        impact_priority=("carbon", "rural"),
        region_preferences=("Jeonbuk",),
        industry_preferences=("AgriTech",),
    )

    score = score_candidate(entity, signals, profile)

    assert score.total_score < 45
    assert score.recommended_action == "archive"
    assert score.queue_type == "exploration"
    assert "weak evidence" in score.rationale.lower()
