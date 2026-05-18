import sqlite3

from merry_runtime.models import MotherEntity, RawSource, Signal
from merry_runtime.ontology import build_startup_graph
from merry_runtime.wiki_store import SQLiteWikiStore


def test_sqlite_wiki_store_initializes_memory_schema(tmp_path) -> None:
    store = SQLiteWikiStore(root=tmp_path)
    store.initialize()

    with sqlite3.connect(tmp_path / "wiki.db") as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table' order by name"
            ).fetchall()
        }

    assert {"pages", "links", "sources", "log_entries"}.issubset(tables)
    assert (tmp_path / "raw").is_dir()
    assert (tmp_path / "wiki").is_dir()
    assert (tmp_path / "wiki" / "index.md").exists()
    assert (tmp_path / "wiki" / "log.md").exists()
    assert (tmp_path / "AGENTS.md").exists()


def test_sqlite_wiki_store_writes_obsidian_pages_index_links_and_log(tmp_path) -> None:
    store = SQLiteWikiStore(root=tmp_path)
    graph = build_startup_graph(
        entity=MotherEntity(entity_id="ent_1", name="CareFarm Carbon", region="Jeonbuk", industry="AgriTech"),
        raw_sources=[
            RawSource(
                source_id="src_referral",
                source_type="sheet_row",
                channel="external_referral",
                uri="google-sheet://referrals",
                title="Judge referral",
            )
        ],
        signals=[
            Signal(
                signal_id="sig_impact",
                entity_id="ent_1",
                signal_type="impact",
                evidence_text="Targets income stabilization for older farming households.",
                source_id="src_referral",
                confidence=0.91,
                tags=("social_problem:older_farming_household_income", "beneficiary:older_farmers"),
            )
        ],
    )

    result = store.upsert_startup_graph(graph, startup_id="ent_1", operation="ingest", source_title="Judge referral")

    startup_page = tmp_path / "wiki" / "entities" / "carefarm-carbon.md"
    index_page = tmp_path / "wiki" / "index.md"
    log_page = tmp_path / "wiki" / "log.md"

    assert result.page_path == "entities/carefarm-carbon.md"
    assert startup_page.exists()
    assert "[[channels/external-referral]]" in startup_page.read_text()
    assert "[[concepts/social_problem/older-farming-household-income]]" in startup_page.read_text()
    assert "- [[entities/carefarm-carbon|CareFarm Carbon]] - Startup" in index_page.read_text()
    assert "ingest | Judge referral" in log_page.read_text()

    with sqlite3.connect(tmp_path / "wiki.db") as connection:
        page_rows = connection.execute("select path, title, kind from pages").fetchall()
        link_rows = connection.execute("select from_path, to_path, relation from links").fetchall()
        source_rows = connection.execute("select source_id, channel, title from sources").fetchall()

    assert ("entities/carefarm-carbon.md", "CareFarm Carbon", "Startup") in page_rows
    assert ("entities/carefarm-carbon.md", "channels/external-referral.md", "OBSERVED_VIA") in link_rows
    assert ("src_referral", "external_referral", "Judge referral") in source_rows


def test_sqlite_wiki_store_sanitizes_page_paths_without_changing_titles(tmp_path) -> None:
    store = SQLiteWikiStore(root=tmp_path)
    graph = build_startup_graph(
        entity=MotherEntity(entity_id="ent_1", name="../../=IMPORTDATA evil", region="Jeonbuk", industry="AgriTech"),
        raw_sources=[
            RawSource(
                source_id="src_referral",
                source_type="sheet_row",
                channel="../external/referral",
                uri="google-sheet://referrals",
                title="Judge referral",
            )
        ],
        signals=[
            Signal(
                signal_id="sig_impact",
                entity_id="ent_1",
                signal_type="impact",
                evidence_text="Targets income stabilization for older farming households.",
                source_id="src_referral",
                confidence=0.91,
                tags=("social_problem:../../income", "beneficiary:\t=HYPERLINK"),
            )
        ],
    )

    result = store.upsert_startup_graph(graph, startup_id="ent_1", operation="ingest", source_title="Judge referral")

    assert result.page_path == "entities/importdata-evil.md"
    assert (tmp_path / "wiki" / "entities" / "importdata-evil.md").exists()
    assert not (tmp_path / "escape.md").exists()
    with sqlite3.connect(tmp_path / "wiki.db") as connection:
        page_rows = connection.execute("select path, title from pages").fetchall()

    assert ("entities/importdata-evil.md", "../../=IMPORTDATA evil") in page_rows
    assert all(".." not in path and not path.startswith("/") for path, _title in page_rows)
