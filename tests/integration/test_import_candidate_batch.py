from pathlib import Path

import pytest

from merry_runtime.adapters.fakes import FakeObjectStore, FakeStructuredStore
from merry_runtime.pipelines.import_candidate_batch import CandidateBatchRejectedError, import_candidate_batch
from merry_runtime.wiki_store import SQLiteWikiStore


HEADER = "company,brand,representative,homepage,region,industry,channel,evidence,confidence,tags,source_uri"


def _csv(rows: list[str]) -> str:
    return "\n".join((HEADER, *rows))


def _row(index: int, *, company: str | None = None, homepage: str | None = None, channel: str | None = None) -> str:
    company = company or f"Candidate {index:04d}"
    homepage = homepage or f"https://candidate-{index:04d}.example"
    channel = channel or ("external_referral", "info_mail", "hankyung_ceo_interview", "internal_screening_memo")[index % 4]
    return ",".join(
        [
            company,
            f"Brand {index:04d}",
            f"Rep {index:04d}",
            homepage,
            "Seoul",
            "AI",
            channel,
            f"Curated evidence {index:04d}",
            "0.82",
            "ai;impact",
            f"drive://candidate-batch.csv#row={index + 2}",
        ]
    )


def test_import_candidate_batch_fixture_creates_raw_entities_signals_and_wiki_pages(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    wiki_store = SQLiteWikiStore(root=tmp_path)
    csv_text = Path("tests/fixtures/candidate_batch_100.csv").read_text(encoding="utf-8")

    result = import_candidate_batch(
        csv_text=csv_text,
        object_store=object_store,
        structured_store=structured_store,
        wiki_store=wiki_store,
        run_id="run_candidate_batch_100",
    )

    assert result.row_count == 100
    assert result.imported_count == 100
    assert len(object_store.objects) == 100
    assert len(structured_store.tables["raw_sources"]) == 100
    assert len(structured_store.tables["mother_entities"]) == 100
    assert len(structured_store.tables["signals"]) == 100
    assert len(list((tmp_path / "wiki" / "entities").glob("*.md"))) == 100
    assert {row["channel"] for row in structured_store.tables["raw_sources"]} == {
        "hankyung_ceo_interview",
        "info_mail",
        "external_referral",
        "internal_screening_memo",
    }
    assert all(str(row["url"]).startswith("drive://candidate-batch.csv#row=") for row in structured_store.tables["raw_sources"])


def test_import_candidate_batch_ingests_1000_synthetic_candidates_without_network(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    wiki_store = SQLiteWikiStore(root=tmp_path)
    csv_text = _csv([_row(index) for index in range(1000)])

    result = import_candidate_batch(
        csv_text=csv_text,
        object_store=object_store,
        structured_store=structured_store,
        wiki_store=wiki_store,
        run_id="run_candidate_batch_1000",
    )

    assert result.row_count == 1000
    assert result.imported_count == 1000
    assert len(structured_store.tables["raw_sources"]) == 1000
    assert len(structured_store.tables["mother_entities"]) == 1000
    assert len(structured_store.tables["signals"]) == 1000
    assert all(row["channel"] in {"hankyung_ceo_interview", "info_mail", "external_referral", "internal_screening_memo"} for row in structured_store.tables["raw_sources"])
    assert all(str(row["url"]).startswith("drive://candidate-batch.csv#row=") for row in structured_store.tables["raw_sources"])
    assert all(";" not in tag for row in structured_store.tables["signals"] for tag in row["tags"])


def test_import_candidate_batch_rejects_conflicts_before_any_write(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    wiki_store = SQLiteWikiStore(root=tmp_path)
    rows = [
        _row(index, company="Conflict Co", homepage=f"https://conflict-{index % 2}.example")
        for index in range(6)
    ]
    rows.extend(_row(index) for index in range(6, 100))

    with pytest.raises(CandidateBatchRejectedError) as exc_info:
        import_candidate_batch(
            csv_text=_csv(rows),
            object_store=object_store,
            structured_store=structured_store,
            wiki_store=wiki_store,
            run_id="run_rejected_candidate_batch",
        )

    assert exc_info.value.quality_report.conflict_rate == pytest.approx(0.06)
    assert not object_store.objects
    assert not structured_store.tables
    assert not (tmp_path / "wiki").exists()
