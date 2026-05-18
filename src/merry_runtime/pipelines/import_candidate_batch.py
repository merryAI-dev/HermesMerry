from __future__ import annotations

from dataclasses import dataclass

from merry_runtime.adapters.interfaces import ObjectStore, StructuredStore
from merry_runtime.ingestion.batch_import import QualityGateReport, parse_candidate_batch_csv
from merry_runtime.pipelines.ingest_sources import ingest_sources
from merry_runtime.wiki_store import SQLiteWikiStore


class CandidateBatchRejectedError(ValueError):
    def __init__(self, quality_report: QualityGateReport) -> None:
        super().__init__(
            "candidate batch rejected by quality gate: "
            f"{quality_report.conflicting_row_count}/{quality_report.total_rows} rows conflict "
            f"({quality_report.conflict_rate:.2%})"
        )
        self.quality_report = quality_report


@dataclass(frozen=True, slots=True)
class CandidateBatchImportResult:
    run_id: str
    row_count: int
    imported_count: int
    raw_source_count: int
    entity_count: int
    signal_count: int
    quality_report: QualityGateReport


def import_candidate_batch(
    *,
    csv_text: str,
    object_store: ObjectStore,
    structured_store: StructuredStore,
    wiki_store: SQLiteWikiStore | None = None,
    run_id: str | None = None,
) -> CandidateBatchImportResult:
    batch = parse_candidate_batch_csv(csv_text)
    if not batch.quality_report.passed:
        raise CandidateBatchRejectedError(batch.quality_report)

    ingest_result = ingest_sources(
        sources=batch.sources,
        object_store=object_store,
        structured_store=structured_store,
        wiki_store=wiki_store,
        run_id=run_id,
    )
    return CandidateBatchImportResult(
        run_id=ingest_result.run_id,
        row_count=batch.row_count,
        imported_count=ingest_result.entity_count,
        raw_source_count=ingest_result.raw_source_count,
        entity_count=ingest_result.entity_count,
        signal_count=ingest_result.signal_count,
        quality_report=batch.quality_report,
    )
