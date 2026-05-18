import hashlib
import sqlite3

from merry_runtime.adapters.fakes import FakeReviewQueue, FakeStructuredStore
from merry_runtime.pipelines.ingest_ac_profiles import ingest_ac_profiles
from merry_runtime.pipelines.score_candidates import score_candidates
from merry_runtime.wiki_store import SQLiteWikiStore


def test_ingest_ac_profiles_upserts_profiles_and_writes_wiki_projection(tmp_path) -> None:
    store = FakeStructuredStore()
    wiki_store = SQLiteWikiStore(root=tmp_path)

    result = ingest_ac_profiles(
        sources=[
            {
                "source_id": "src_ac_climate",
                "title": "Climate local thesis",
                "uri": "drive://reports/climate",
                "payload": """
                    AC ID: ac_climate_local
                    AC Name: Climate Local Impact AC
                    Fund Purpose: climate adaptation and rural resilience fund
                    Recruiting Area: Jeonbuk
                    Hypothesis Tags: climate, agritech
                    Impact Priorities: carbon; rural resilience
                    Region Preferences: Jeonbuk
                    Industry Preferences: AgriTech
                    Tech Preferences: AI
                """,
            }
        ],
        structured_store=store,
        wiki_store=wiki_store,
    )

    assert result.profile_count == 1
    assert store.tables["ac_profiles"] == [
        {
            "ac_id": "ac_climate_local",
            "ac_name": "Climate Local Impact AC",
            "fund_purpose": "climate adaptation and rural resilience fund",
            "recruiting_area": "Jeonbuk",
            "hypothesis_tags": ["climate", "agritech"],
            "impact_priority": ["carbon", "rural resilience"],
            "region_preferences": ["Jeonbuk"],
            "industry_preferences": ["AgriTech"],
            "tech_preferences": ["AI"],
        }
    ]
    assert store.tables["agent_runs"][0]["job_name"] == "ingest-ac-profiles"

    ac_page = tmp_path / "wiki" / "ac" / "ac-climate-local.md"
    thesis_page = tmp_path / "wiki" / "concepts" / "impact_thesis" / "carbon.md"
    index_page = tmp_path / "wiki" / "index.md"
    assert ac_page.exists()
    assert thesis_page.exists()
    assert "[[concepts/impact_thesis/carbon]]" in ac_page.read_text()
    assert "[[ac/ac-climate-local|Climate Local Impact AC]]" in index_page.read_text()
    assert "[[concepts/impact_thesis/carbon|carbon]]" in index_page.read_text()

    with sqlite3.connect(tmp_path / "wiki.db") as connection:
        link_rows = connection.execute("select from_path, to_path, relation from links").fetchall()

    assert ("ac/ac-climate-local.md", "concepts/impact_thesis/carbon.md", "MATCHES_THESIS") in link_rows


def test_ingest_ac_profiles_keys_wiki_pages_by_ac_id_when_names_collide(tmp_path) -> None:
    store = FakeStructuredStore()
    wiki_store = SQLiteWikiStore(root=tmp_path)

    ingest_ac_profiles(
        sources=[
            {
                "payload": """
                    AC ID: ac_first
                    AC Name: Shared Display Name
                    Fund Purpose: climate fund
                    Hypothesis Tags: climate
                    Impact Priorities: carbon
                """,
            },
            {
                "payload": """
                    AC ID: ac_second
                    AC Name: Shared Display Name
                    Fund Purpose: care fund
                    Hypothesis Tags: care
                    Impact Priorities: access
                """,
            },
        ],
        structured_store=store,
        wiki_store=wiki_store,
    )

    first_page = tmp_path / "wiki" / "ac" / "ac-first.md"
    second_page = tmp_path / "wiki" / "ac" / "ac-second.md"
    assert first_page.exists()
    assert second_page.exists()
    assert "title: Shared Display Name" in first_page.read_text()
    assert "title: Shared Display Name" in second_page.read_text()
    assert not (tmp_path / "wiki" / "ac" / "shared-display-name.md").exists()

    with sqlite3.connect(tmp_path / "wiki.db") as connection:
        page_rows = connection.execute("select path, title, kind from pages where kind = 'AC' order by path").fetchall()

    assert page_rows == [
        ("ac/ac-first.md", "Shared Display Name", "AC"),
        ("ac/ac-second.md", "Shared Display Name", "AC"),
    ]


def test_ingest_ac_profiles_updates_remove_stale_thesis_links_without_deleting_shared_theses(tmp_path) -> None:
    store = FakeStructuredStore()
    wiki_store = SQLiteWikiStore(root=tmp_path)

    ingest_ac_profiles(
        sources=[
            {
                "payload": """
                    AC ID: ac_first
                    AC Name: First AC
                    Fund Purpose: climate fund
                    Hypothesis Tags: climate
                    Impact Priorities: carbon, shared thesis
                """,
            },
            {
                "payload": """
                    AC ID: ac_second
                    AC Name: Second AC
                    Fund Purpose: care fund
                    Hypothesis Tags: care
                    Impact Priorities: shared thesis
                """,
            },
        ],
        structured_store=store,
        wiki_store=wiki_store,
    )

    ingest_ac_profiles(
        sources=[
            {
                "payload": """
                    AC ID: ac_first
                    AC Name: First AC Renamed
                    Fund Purpose: water fund
                    Hypothesis Tags: water
                    Impact Priorities: water, shared thesis
                """,
            }
        ],
        structured_store=store,
        wiki_store=wiki_store,
    )

    index_text = (tmp_path / "wiki" / "index.md").read_text()
    first_page_text = (tmp_path / "wiki" / "ac" / "ac-first.md").read_text()
    assert "concepts/impact_thesis/carbon" not in index_text
    assert "concepts/impact_thesis/carbon" not in first_page_text
    assert "[[concepts/impact_thesis/water|water]]" in index_text
    assert "[[concepts/impact_thesis/shared-thesis|shared thesis]]" in index_text
    assert not (tmp_path / "wiki" / "concepts" / "impact_thesis" / "carbon.md").exists()
    assert (tmp_path / "wiki" / "concepts" / "impact_thesis" / "shared-thesis.md").exists()
    assert (tmp_path / "wiki" / "ac" / "ac-first.md").exists()
    assert not (tmp_path / "wiki" / "ac" / "first-ac.md").exists()

    with sqlite3.connect(tmp_path / "wiki.db") as connection:
        links = connection.execute("select from_path, to_path from links order by from_path, to_path").fetchall()
        pages = connection.execute("select path from pages order by path").fetchall()

    assert ("ac/ac-first.md", "concepts/impact_thesis/carbon.md") not in links
    assert ("ac/ac-second.md", "concepts/impact_thesis/shared-thesis.md") in links
    assert ("concepts/impact_thesis/carbon.md",) not in pages


def test_ingest_ac_profiles_writes_source_provenance_and_links_with_source_id(tmp_path) -> None:
    source_text = """
        AC ID: ac_provenance
        AC Name: Provenance AC
        Fund Purpose: climate fund
        Hypothesis Tags: climate
        Impact Priorities: carbon
    """
    store = FakeStructuredStore()
    wiki_store = SQLiteWikiStore(root=tmp_path)

    result = ingest_ac_profiles(
        sources=[
            {
                "source_id": "src_ac_report_1",
                "channel": "drive_report",
                "title": "Drive AC report",
                "uri": "drive://ac/report-1",
                "raw_text_path": "gs://raw-bucket/ac/report-1.md",
                "payload": source_text,
            }
        ],
        structured_store=store,
        wiki_store=wiki_store,
    )

    assert result.profile_count == 1
    with sqlite3.connect(tmp_path / "wiki.db") as connection:
        source_rows = connection.execute("select source_id, channel, title, uri, raw_path, checksum from sources").fetchall()
        link_rows = connection.execute("select from_path, to_path, relation, source_id from links").fetchall()

    assert source_rows == [
        (
            "src_ac_report_1",
            "drive_report",
            "Drive AC report",
            "drive://ac/report-1",
            "gs://raw-bucket/ac/report-1.md",
            hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        )
    ]
    assert ("ac/ac-provenance.md", "concepts/impact_thesis/carbon.md", "MATCHES_THESIS", "src_ac_report_1") in link_rows


def test_ingested_ac_profiles_change_transparent_scoring_features_and_rationale(tmp_path) -> None:
    store = FakeStructuredStore.seed_climate_candidate()
    store.tables["ac_profiles"] = []

    ingest_ac_profiles(
        sources=[
            {
                "payload": """
                    AC ID: ac_climate
                    AC Name: Climate Impact AC
                    Fund Purpose: climate impact fund
                    Recruiting Area: Jeonbuk
                    Hypothesis Tags: climate, agritech
                    Impact Priorities: carbon, rural
                    Region Preferences: Jeonbuk
                    Industry Preferences: AgriTech
                """,
            },
            {
                "payload": """
                    AC ID: ac_care
                    AC Name: Care Access AC
                    Fund Purpose: eldercare access fund
                    Recruiting Area: Seoul
                    Hypothesis Tags: eldercare, care coordination
                    Impact Priorities: patient access, caregiver burden
                    Region Preferences: Seoul
                    Industry Preferences: HealthTech
                """,
            },
        ],
        structured_store=store,
        wiki_store=SQLiteWikiStore(root=tmp_path),
    )

    score_candidates(structured_store=store, review_queue=FakeReviewQueue(), ac_id="ac_climate")
    score_candidates(structured_store=store, review_queue=FakeReviewQueue(), ac_id="ac_care")

    climate_score = next(row for row in store.tables["ac_scores"] if row["ac_id"] == "ac_climate")
    care_score = next(row for row in store.tables["ac_scores"] if row["ac_id"] == "ac_care")
    assert climate_score["fund_fit_score"] != care_score["fund_fit_score"]
    assert climate_score["hypothesis_fit_score"] != care_score["hypothesis_fit_score"]
    assert climate_score["impact_fit_score"] != care_score["impact_fit_score"]
    assert climate_score["rationale"] != care_score["rationale"]
