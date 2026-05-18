from merry_runtime.adapters.fakes import FakeObjectStore, FakeStructuredStore
from merry_runtime.pipelines.ingest_sources import ingest_sources
from merry_runtime.wiki_store import SQLiteWikiStore


def test_ingest_sources_writes_raw_sources_entities_signals_and_agent_run() -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()

    result = ingest_sources(
        sources=[
            {
                "channel": "external_referral",
                "payload": {
                    "company": "Merry AI",
                    "region": "Seoul",
                    "industry": "AI",
                    "homepage": "https://merry.ai",
                    "reason": "impact referral",
                    "tags": "impact, ai",
                    "confidence": "0.77",
                },
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
    )

    assert result.raw_source_count == 1
    assert result.entity_count == 1
    assert result.signal_count == 1
    assert structured_store.tables["raw_sources"][0]["raw_text_path"].startswith("gs://raw-bucket/")
    assert structured_store.tables["mother_entities"][0]["name"] == "Merry AI"
    assert structured_store.tables["signals"][0]["source_id"].startswith("src_")
    assert structured_store.tables["agent_runs"][0]["run_id"] == result.run_id
    assert structured_store.tables["agent_runs"][0]["status"] == "success"


def test_ingest_sources_keeps_pii_in_raw_store_but_redacts_signal_evidence() -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()

    ingest_sources(
        sources=[
            {
                "channel": "info_mail",
                "payload": "Subject: Info mail\nFrom: founder@merry.ai\nCompany: Merry AI\nRegion: Seoul\nIndustry: AI\nHomepage: https://merry.ai\nSignal: traction\nConfidence: 0.81\nTags: ai, traction\nEvidence: Contact founder@merry.ai / 010-1234-5678 for proof.",
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
    )

    raw_source = structured_store.tables["raw_sources"][0]
    signal = structured_store.tables["signals"][0]

    assert raw_source["contains_pii"] is True
    assert "founder@merry.ai" in next(iter(object_store.objects.values()))["text"]
    assert "founder@merry.ai" not in signal["evidence_text"]
    assert "[REDACTED_PHONE]" in signal["evidence_text"]


def test_ingest_sources_can_update_sqlite_obsidian_wiki(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    wiki_store = SQLiteWikiStore(root=tmp_path)

    ingest_sources(
        sources=[
            {
                "channel": "external_referral",
                "payload": {
                    "company": "CareFarm Carbon",
                    "region": "Jeonbuk",
                    "industry": "AgriTech",
                    "reason": "Targets income stabilization for older farming households.",
                    "tags": "social_problem:older_farming_household_income, beneficiary:older_farmers",
                    "confidence": "0.91",
                },
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        wiki_store=wiki_store,
    )

    startup_page = tmp_path / "wiki" / "entities" / "carefarm-carbon.md"
    assert startup_page.exists()
    assert "[[channels/external-referral]]" in startup_page.read_text()
    assert "CareFarm Carbon" in (tmp_path / "wiki" / "index.md").read_text()
    assert "ingest | Referral: CareFarm Carbon" in (tmp_path / "wiki" / "log.md").read_text()
