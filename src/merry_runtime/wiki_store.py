from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re

from merry_runtime.ontology import EdgeKind, NodeKind, StartupKnowledgeGraph, project_startup_wiki


@dataclass(frozen=True, slots=True)
class WikiWriteResult:
    page_path: str
    link_count: int
    source_count: int


@dataclass(slots=True)
class SQLiteWikiStore:
    root: Path

    @property
    def db_path(self) -> Path:
        return self.root / "wiki.db"

    @property
    def wiki_dir(self) -> Path:
        return self.root / "wiki"

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    def initialize(self) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        (self.wiki_dir / "entities").mkdir(parents=True, exist_ok=True)
        (self.wiki_dir / "channels").mkdir(parents=True, exist_ok=True)
        (self.wiki_dir / "concepts" / "social_problem").mkdir(parents=True, exist_ok=True)
        (self.wiki_dir / "concepts" / "beneficiary").mkdir(parents=True, exist_ok=True)
        self._write_if_missing(self.wiki_dir / "index.md", "# Index\n\n")
        self._write_if_missing(self.wiki_dir / "log.md", "# Log\n\n")
        self._write_if_missing(self.root / "AGENTS.md", _schema_doc())

        with sqlite3.connect(self.db_path) as connection:
            connection.executescript(
                """
                create table if not exists pages (
                    path text primary key,
                    title text not null,
                    kind text not null,
                    summary text not null default '',
                    updated_at text not null
                );

                create table if not exists links (
                    from_path text not null,
                    to_path text not null,
                    relation text not null,
                    source_id text,
                    confidence real not null default 1.0,
                    primary key (from_path, to_path, relation)
                );

                create table if not exists sources (
                    source_id text primary key,
                    channel text not null,
                    title text not null,
                    uri text not null,
                    raw_path text not null default '',
                    checksum text not null default '',
                    ingested_at text not null
                );

                create table if not exists log_entries (
                    entry_id text primary key,
                    timestamp text not null,
                    operation text not null,
                    title text not null,
                    page_path text not null
                );
                """
            )

    def upsert_startup_graph(
        self,
        graph: StartupKnowledgeGraph,
        *,
        startup_id: str,
        operation: str,
        source_title: str,
    ) -> WikiWriteResult:
        self.initialize()
        startup = graph.node(startup_id)
        page_path = _node_page_path(startup)
        page_file = self.wiki_dir / page_path
        page_file.parent.mkdir(parents=True, exist_ok=True)
        page_file.write_text(_frontmatter(title=startup.label, kind=startup.kind.value) + _obsidian_startup_page(graph, startup_id), encoding="utf-8")

        now = _now()
        links = _obsidian_links(graph, startup_id, page_path)
        sources = _sources(graph)
        pages = _pages(graph, startup_id, page_path)

        with sqlite3.connect(self.db_path) as connection:
            connection.executemany(
                """
                insert into pages(path, title, kind, summary, updated_at)
                values(?, ?, ?, ?, ?)
                on conflict(path) do update set
                    title=excluded.title,
                    kind=excluded.kind,
                    summary=excluded.summary,
                    updated_at=excluded.updated_at
                """,
                [(path, title, kind, summary, now) for path, title, kind, summary in pages],
            )
            connection.executemany(
                """
                insert into links(from_path, to_path, relation, source_id, confidence)
                values(?, ?, ?, ?, ?)
                on conflict(from_path, to_path, relation) do update set
                    source_id=excluded.source_id,
                    confidence=excluded.confidence
                """,
                links,
            )
            connection.executemany(
                """
                insert into sources(source_id, channel, title, uri, raw_path, checksum, ingested_at)
                values(?, ?, ?, ?, ?, ?, ?)
                on conflict(source_id) do update set
                    channel=excluded.channel,
                    title=excluded.title,
                    uri=excluded.uri,
                    raw_path=excluded.raw_path,
                    checksum=excluded.checksum
                """,
                [(source_id, channel, title, uri, raw_path, checksum, now) for source_id, channel, title, uri, raw_path, checksum in sources],
            )

        self._rewrite_index()
        self._append_log(operation=operation, title=source_title, page_path=page_path, timestamp=now)
        return WikiWriteResult(page_path=page_path, link_count=len(links), source_count=len(sources))

    def _rewrite_index(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute("select path, title, kind, summary from pages order by kind, title").fetchall()
        lines = ["# Index", ""]
        current_kind = ""
        for path, title, kind, summary in rows:
            if kind != current_kind:
                current_kind = kind
                lines.extend(["", f"## {kind}"])
            link = path.removesuffix(".md")
            suffix = f" - {summary}" if summary else f" - {kind}"
            lines.append(f"- [[{link}|{title}]]{suffix}")
        (self.wiki_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _append_log(self, *, operation: str, title: str, page_path: str, timestamp: str) -> None:
        entry_id = f"{timestamp}|{operation}|{title}"
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                insert or ignore into log_entries(entry_id, timestamp, operation, title, page_path)
                values(?, ?, ?, ?, ?)
                """,
                (entry_id, timestamp, operation, title, page_path),
            )
        log_path = self.wiki_dir / "log.md"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"## [{timestamp[:10]}] {operation} | {title}\n")
            handle.write(f"- Updated: [[{page_path.removesuffix('.md')}]]\n\n")

    @staticmethod
    def _write_if_missing(path: Path, text: str) -> None:
        if not path.exists():
            path.write_text(text, encoding="utf-8")


def _obsidian_startup_page(graph: StartupKnowledgeGraph, startup_id: str) -> str:
    base = project_startup_wiki(graph, startup_id=startup_id)
    links = _page_link_lines(graph, startup_id)
    return base + "\n\n## Obsidian Links\n" + "\n".join(links) + "\n"


def _page_link_lines(graph: StartupKnowledgeGraph, startup_id: str) -> list[str]:
    lines: list[str] = []
    for edge in graph.edges:
        if edge.from_node_id != startup_id:
            continue
        target = graph.node(edge.to_node_id)
        target_path = _node_page_path(target)
        if target_path:
            lines.append(f"- {edge.kind.value}: [[{target_path.removesuffix('.md')}]]")
    for edge in graph.edges:
        if edge.kind in {EdgeKind.TARGETS_PROBLEM, EdgeKind.SERVES_BENEFICIARY, EdgeKind.MATCHES_THESIS}:
            target = graph.node(edge.to_node_id)
            target_path = _node_page_path(target)
            if target_path:
                lines.append(f"- {edge.kind.value}: [[{target_path.removesuffix('.md')}]]")
    return sorted(set(lines))


def _obsidian_links(graph: StartupKnowledgeGraph, startup_id: str, page_path: str) -> list[tuple[str, str, str, str | None, float]]:
    rows: list[tuple[str, str, str, str | None, float]] = []
    for edge in graph.edges:
        from_page = page_path if edge.from_node_id == startup_id else _node_page_path(graph.node(edge.from_node_id))
        to_page = _node_page_path(graph.node(edge.to_node_id))
        if from_page and to_page:
            rows.append((from_page, to_page, edge.kind.value, edge.source_id, edge.confidence))
    return rows


def _pages(graph: StartupKnowledgeGraph, startup_id: str, startup_page_path: str) -> list[tuple[str, str, str, str]]:
    rows = [(startup_page_path, graph.node(startup_id).label, NodeKind.STARTUP.value, "Startup")]
    for node in graph.nodes.values():
        path = _node_page_path(node)
        if not path or path == startup_page_path:
            continue
        rows.append((path, node.label, node.kind.value, node.properties.get("meaning", node.kind.value)))
    return rows


def _sources(graph: StartupKnowledgeGraph) -> list[tuple[str, str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str, str]] = []
    for node in graph.nodes.values():
        if node.kind is NodeKind.EVIDENCE:
            source_id = node.node_id.removeprefix("evidence_")
            rows.append(
                (
                    source_id,
                    str(node.properties.get("channel", "")),
                    node.label,
                    str(node.properties.get("uri", "")),
                    str(node.properties.get("raw_text_path", "")),
                    str(node.properties.get("checksum", "")),
                )
            )
    return rows


def _node_page_path(node) -> str:
    if node.kind is NodeKind.STARTUP:
        return f"entities/{_slugify(node.label)}.md"
    if node.kind is NodeKind.DISCOVERY_CHANNEL:
        return f"channels/{_slugify(node.label)}.md"
    if node.kind is NodeKind.SOCIAL_PROBLEM:
        return f"concepts/social_problem/{_slugify(node.label)}.md"
    if node.kind is NodeKind.BENEFICIARY:
        return f"concepts/beneficiary/{_slugify(node.label)}.md"
    if node.kind is NodeKind.IMPACT_THESIS:
        return f"concepts/impact_thesis/{_slugify(node.label)}.md"
    if node.kind is NodeKind.AC:
        return f"ac/{_slugify(node.label)}.md"
    if node.kind is NodeKind.DECISION:
        return f"decisions/{_slugify(node.label)}.md"
    return ""


def _slugify(label: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣._ -]+", " ", label).strip().casefold()
    slug = re.sub(r"[./\\\s_-]+", "-", slug).strip("-")
    return slug or "untitled"


def _frontmatter(*, title: str, kind: str) -> str:
    return f"---\ntitle: {title}\nkind: {kind}\n---\n\n"


def _schema_doc() -> str:
    return """# Hermes Merry Wiki Schema

This wiki is maintained by the LLM agent.

Rules:
- Raw sources in `raw/` are immutable.
- Markdown pages in `wiki/` are the human-readable projection.
- `wiki.db` is the agent memory index for pages, links, sources, and logs.
- Use Obsidian links for relationships.
- Preserve source-channel meaning before scoring.
- Do not use an external graph database.
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()
