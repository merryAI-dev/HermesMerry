from merry_runtime.models import ACProfile, Decision, MotherEntity, RawSource, Review, Signal
from merry_runtime.ontology import (
    CHANNEL_MEANINGS,
    EdgeKind,
    NodeKind,
    build_startup_graph,
    embedding_documents_from_graph,
    project_startup_wiki,
)


def test_discovery_channel_meanings_preserve_source_semantics() -> None:
    assert CHANNEL_MEANINGS["hankyung_ceo_interview"].meaning == "public_cold_lead"
    assert CHANNEL_MEANINGS["thevc_investment_ma"].meaning == "public_investment_ma_signal"
    assert CHANNEL_MEANINGS["info_mail"].meaning == "inbound_intent"
    assert CHANNEL_MEANINGS["external_referral"].meaning == "referral_signal"
    assert CHANNEL_MEANINGS["internal_screening_memo"].meaning == "semi_qualified_signal"


def test_build_startup_graph_preserves_channel_evidence_signal_and_decision_relations() -> None:
    entity = MotherEntity(entity_id="ent_1", name="CareFarm Carbon", region="Jeonbuk", industry="AgriTech")
    raw_sources = [
        RawSource(
            source_id="src_referral",
            source_type="sheet_row",
            channel="external_referral",
            uri="google-sheet://referrals",
            title="Judge referral",
        ),
        RawSource(
            source_id="src_internal",
            source_type="drive_doc",
            channel="internal_screening_memo",
            uri="drive://memo",
            title="Internal screening note",
        ),
    ]
    signals = [
        Signal(
            signal_id="sig_impact",
            entity_id="ent_1",
            signal_type="impact",
            evidence_text="Targets income stabilization for older farming households.",
            source_id="src_referral",
            confidence=0.91,
            tags=("social_problem:older_farming_household_income", "beneficiary:older_farmers", "impact_thesis:local_impact"),
        )
    ]
    profile = ACProfile(ac_id="ac_local", ac_name="Local Impact AC", fund_purpose="local impact", recruiting_area="Jeonbuk")
    reviews = [Review(card_id="card_1", reviewer="boram", decision=Decision.WATCHLIST, memo="Strong impact, sales unclear")]

    graph = build_startup_graph(entity=entity, raw_sources=raw_sources, signals=signals, ac_profile=profile, reviews=reviews)

    assert graph.node("ent_1").kind is NodeKind.STARTUP
    assert graph.node("channel_external_referral").properties["meaning"] == "referral_signal"
    assert graph.has_edge("ent_1", "channel_external_referral", EdgeKind.OBSERVED_VIA)
    assert graph.has_edge("sig_impact", "evidence_src_referral", EdgeKind.SUPPORTED_BY)
    assert graph.has_edge("sig_impact", "social_problem_older_farming_household_income", EdgeKind.TARGETS_PROBLEM)
    assert graph.has_edge("sig_impact", "beneficiary_older_farmers", EdgeKind.SERVES_BENEFICIARY)
    assert graph.has_edge("ent_1", "decision_card_1", EdgeKind.HAS_DECISION)


def test_wiki_and_embedding_are_projections_not_source_of_truth() -> None:
    entity = MotherEntity(entity_id="ent_1", name="CareFarm Carbon", region="Jeonbuk", industry="AgriTech")
    raw_source = RawSource(
        source_id="src_referral",
        source_type="sheet_row",
        channel="external_referral",
        uri="google-sheet://referrals",
        title="Judge referral",
    )
    signal = Signal(
        signal_id="sig_impact",
        entity_id="ent_1",
        signal_type="impact",
        evidence_text="Targets income stabilization for older farming households.",
        source_id="src_referral",
        confidence=0.91,
        tags=("social_problem:older_farming_household_income", "beneficiary:older_farmers"),
    )
    graph = build_startup_graph(entity=entity, raw_sources=[raw_source], signals=[signal])

    wiki = project_startup_wiki(graph, startup_id="ent_1")
    documents = embedding_documents_from_graph(graph)

    assert "# CareFarm Carbon" in wiki
    assert "referral_signal" in wiki
    assert "older_farming_household_income" in wiki
    assert documents == [
        {
            "document_id": "embed_evidence_src_referral",
            "source_node_id": "evidence_src_referral",
            "text": "Judge referral\nTargets income stabilization for older farming households.",
        }
    ]
