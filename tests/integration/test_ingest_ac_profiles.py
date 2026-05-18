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

    ac_page = tmp_path / "wiki" / "ac" / "climate-local-impact-ac.md"
    thesis_page = tmp_path / "wiki" / "concepts" / "impact_thesis" / "carbon.md"
    index_page = tmp_path / "wiki" / "index.md"
    assert ac_page.exists()
    assert thesis_page.exists()
    assert "[[concepts/impact_thesis/carbon]]" in ac_page.read_text()
    assert "[[ac/climate-local-impact-ac|Climate Local Impact AC]]" in index_page.read_text()
    assert "[[concepts/impact_thesis/carbon|carbon]]" in index_page.read_text()

    with sqlite3.connect(tmp_path / "wiki.db") as connection:
        link_rows = connection.execute("select from_path, to_path, relation from links").fetchall()

    assert ("ac/climate-local-impact-ac.md", "concepts/impact_thesis/carbon.md", "MATCHES_THESIS") in link_rows


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
