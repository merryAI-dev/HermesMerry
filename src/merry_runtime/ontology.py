from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from merry_runtime.models import ACProfile, MotherEntity, RawSource, Review, Signal


class NodeKind(StrEnum):
    STARTUP = "Startup"
    FOUNDER = "Founder"
    DISCOVERY_CHANNEL = "DiscoveryChannel"
    EVIDENCE = "Evidence"
    SIGNAL = "Signal"
    FUND = "Fund"
    PROGRAM = "Program"
    AC = "AC"
    IMPACT_THESIS = "ImpactThesis"
    SOCIAL_PROBLEM = "SocialProblem"
    BENEFICIARY = "Beneficiary"
    DECISION = "Decision"


class EdgeKind(StrEnum):
    OBSERVED_VIA = "OBSERVED_VIA"
    HAS_EVIDENCE = "HAS_EVIDENCE"
    HAS_SIGNAL = "HAS_SIGNAL"
    SUPPORTED_BY = "SUPPORTED_BY"
    TARGETS_PROBLEM = "TARGETS_PROBLEM"
    SERVES_BENEFICIARY = "SERVES_BENEFICIARY"
    MATCHES_THESIS = "MATCHES_THESIS"
    CONSIDERED_FOR = "CONSIDERED_FOR"
    HAS_DECISION = "HAS_DECISION"


@dataclass(frozen=True, slots=True)
class DiscoveryChannelMeaning:
    channel: str
    meaning: str
    trust_tier: str
    description: str


CHANNEL_MEANINGS = {
    "hankyung_ceo_interview": DiscoveryChannelMeaning(
        channel="hankyung_ceo_interview",
        meaning="public_cold_lead",
        trust_tier="observed",
        description="Publicly observed cold lead from media/interview coverage.",
    ),
    "thevc_investment_ma": DiscoveryChannelMeaning(
        channel="thevc_investment_ma",
        meaning="public_investment_ma_signal",
        trust_tier="observed",
        description="Publicly observed investment or M&A card from THE VC.",
    ),
    "info_mail": DiscoveryChannelMeaning(
        channel="info_mail",
        meaning="inbound_intent",
        trust_tier="intent",
        description="Inbound lead with explicit contact or application intent.",
    ),
    "external_referral": DiscoveryChannelMeaning(
        channel="external_referral",
        meaning="referral_signal",
        trust_tier="trusted_referral",
        description="External judge or trusted recommender signal.",
    ),
    "internal_screening_memo": DiscoveryChannelMeaning(
        channel="internal_screening_memo",
        meaning="semi_qualified_signal",
        trust_tier="human_evaluated",
        description="Internal screening or review history with human evaluation.",
    ),
}


@dataclass(frozen=True, slots=True)
class KnowledgeNode:
    node_id: str
    kind: NodeKind
    label: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KnowledgeEdge:
    edge_id: str
    from_node_id: str
    to_node_id: str
    kind: EdgeKind
    source_id: str | None = None
    evidence_id: str | None = None
    confidence: float = 1.0


@dataclass(slots=True)
class StartupKnowledgeGraph:
    nodes: dict[str, KnowledgeNode] = field(default_factory=dict)
    edges: list[KnowledgeEdge] = field(default_factory=list)

    def add_node(self, node: KnowledgeNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: KnowledgeEdge) -> None:
        self.edges.append(edge)

    def node(self, node_id: str) -> KnowledgeNode:
        return self.nodes[node_id]

    def has_edge(self, from_node_id: str, to_node_id: str, kind: EdgeKind) -> bool:
        return any(edge.from_node_id == from_node_id and edge.to_node_id == to_node_id and edge.kind == kind for edge in self.edges)


def build_startup_graph(
    *,
    entity: MotherEntity,
    raw_sources: list[RawSource],
    signals: list[Signal],
    ac_profile: ACProfile | None = None,
    reviews: list[Review] | None = None,
) -> StartupKnowledgeGraph:
    graph = StartupKnowledgeGraph()
    graph.add_node(
        KnowledgeNode(
            node_id=entity.entity_id,
            kind=NodeKind.STARTUP,
            label=entity.name,
            properties={"region": entity.region, "industry": entity.industry, "homepage": entity.homepage or ""},
        )
    )

    source_by_id = {source.source_id: source for source in raw_sources}
    for source in raw_sources:
        channel = CHANNEL_MEANINGS.get(
            source.channel,
            DiscoveryChannelMeaning(source.channel, "unknown_channel", "unknown", "Unclassified discovery channel."),
        )
        channel_id = f"channel_{source.channel}"
        evidence_id = f"evidence_{source.source_id}"
        graph.add_node(
            KnowledgeNode(
                node_id=channel_id,
                kind=NodeKind.DISCOVERY_CHANNEL,
                label=source.channel,
                properties={"meaning": channel.meaning, "trust_tier": channel.trust_tier, "description": channel.description},
            )
        )
        graph.add_node(
            KnowledgeNode(
                node_id=evidence_id,
                kind=NodeKind.EVIDENCE,
                label=source.title or source.uri,
                properties={"uri": source.uri, "source_type": source.source_type, "channel": source.channel},
            )
        )
        graph.add_edge(_edge(entity.entity_id, channel_id, EdgeKind.OBSERVED_VIA, source_id=source.source_id))
        graph.add_edge(_edge(entity.entity_id, evidence_id, EdgeKind.HAS_EVIDENCE, source_id=source.source_id, evidence_id=evidence_id))

    for signal in signals:
        signal_id = signal.signal_id
        evidence_id = f"evidence_{signal.source_id}"
        graph.add_node(
            KnowledgeNode(
                node_id=signal_id,
                kind=NodeKind.SIGNAL,
                label=signal.signal_type,
                properties={"evidence_text": signal.evidence_text, "tags": list(signal.tags)},
            )
        )
        graph.add_edge(
            _edge(entity.entity_id, signal_id, EdgeKind.HAS_SIGNAL, source_id=signal.source_id, evidence_id=evidence_id, confidence=signal.confidence)
        )
        if signal.source_id in source_by_id:
            graph.add_edge(
                _edge(signal_id, evidence_id, EdgeKind.SUPPORTED_BY, source_id=signal.source_id, evidence_id=evidence_id, confidence=signal.confidence)
            )
        _add_signal_tag_nodes(graph, signal, evidence_id)

    if ac_profile:
        graph.add_node(
            KnowledgeNode(
                node_id=ac_profile.ac_id,
                kind=NodeKind.AC,
                label=ac_profile.ac_name,
                properties={"fund_purpose": ac_profile.fund_purpose, "recruiting_area": ac_profile.recruiting_area},
            )
        )
        graph.add_edge(_edge(entity.entity_id, ac_profile.ac_id, EdgeKind.CONSIDERED_FOR))

    for review in reviews or []:
        decision_id = f"decision_{review.card_id}"
        graph.add_node(
            KnowledgeNode(
                node_id=decision_id,
                kind=NodeKind.DECISION,
                label=review.decision.value,
                properties={"reviewer": review.reviewer, "memo": review.memo, "card_id": review.card_id},
            )
        )
        graph.add_edge(_edge(entity.entity_id, decision_id, EdgeKind.HAS_DECISION))

    return graph


def project_startup_wiki(graph: StartupKnowledgeGraph, *, startup_id: str) -> str:
    startup = graph.node(startup_id)
    lines = [f"# {startup.label}", "", f"- Region: {startup.properties.get('region', '')}", f"- Industry: {startup.properties.get('industry', '')}"]
    channel_nodes = _targets(graph, startup_id, EdgeKind.OBSERVED_VIA)
    if channel_nodes:
        lines.extend(["", "## Discovery Channels"])
        for node in channel_nodes:
            lines.append(f"- {node.label}: {node.properties.get('meaning')} ({node.properties.get('trust_tier')})")
    signal_nodes = _targets(graph, startup_id, EdgeKind.HAS_SIGNAL)
    if signal_nodes:
        lines.extend(["", "## Signals"])
        for node in signal_nodes:
            lines.append(f"- {node.label}: {node.properties.get('evidence_text')}")
    problem_nodes = [node for node in graph.nodes.values() if node.kind is NodeKind.SOCIAL_PROBLEM]
    if problem_nodes:
        lines.extend(["", "## Social Problems"])
        for node in problem_nodes:
            lines.append(f"- {node.label}")
    return "\n".join(lines)


def embedding_documents_from_graph(graph: StartupKnowledgeGraph) -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    for node in graph.nodes.values():
        if node.kind is not NodeKind.EVIDENCE:
            continue
        evidence_texts = [
            graph.node(edge.from_node_id).properties.get("evidence_text", "")
            for edge in graph.edges
            if edge.kind is EdgeKind.SUPPORTED_BY and edge.to_node_id == node.node_id
        ]
        text = "\n".join(part for part in [node.label, *evidence_texts] if part)
        documents.append({"document_id": f"embed_{node.node_id}", "source_node_id": node.node_id, "text": text})
    return sorted(documents, key=lambda document: document["document_id"])


def _add_signal_tag_nodes(graph: StartupKnowledgeGraph, signal: Signal, evidence_id: str) -> None:
    for tag in signal.tags:
        if ":" not in tag:
            continue
        tag_kind, value = tag.split(":", 1)
        node_id = f"{tag_kind}_{value}"
        if tag_kind == "social_problem":
            graph.add_node(KnowledgeNode(node_id=node_id, kind=NodeKind.SOCIAL_PROBLEM, label=value))
            graph.add_edge(_edge(signal.signal_id, node_id, EdgeKind.TARGETS_PROBLEM, source_id=signal.source_id, evidence_id=evidence_id, confidence=signal.confidence))
        elif tag_kind == "beneficiary":
            graph.add_node(KnowledgeNode(node_id=node_id, kind=NodeKind.BENEFICIARY, label=value))
            graph.add_edge(_edge(signal.signal_id, node_id, EdgeKind.SERVES_BENEFICIARY, source_id=signal.source_id, evidence_id=evidence_id, confidence=signal.confidence))
        elif tag_kind == "impact_thesis":
            graph.add_node(KnowledgeNode(node_id=node_id, kind=NodeKind.IMPACT_THESIS, label=value))
            graph.add_edge(_edge(signal.signal_id, node_id, EdgeKind.MATCHES_THESIS, source_id=signal.source_id, evidence_id=evidence_id, confidence=signal.confidence))


def _targets(graph: StartupKnowledgeGraph, from_node_id: str, kind: EdgeKind) -> list[KnowledgeNode]:
    return [graph.node(edge.to_node_id) for edge in graph.edges if edge.from_node_id == from_node_id and edge.kind is kind]


def _edge(
    from_node_id: str,
    to_node_id: str,
    kind: EdgeKind,
    *,
    source_id: str | None = None,
    evidence_id: str | None = None,
    confidence: float = 1.0,
) -> KnowledgeEdge:
    return KnowledgeEdge(
        edge_id=f"{from_node_id}__{kind.value}__{to_node_id}",
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        kind=kind,
        source_id=source_id,
        evidence_id=evidence_id,
        confidence=confidence,
    )
