import json
import sqlite3
import tarfile

from merry_runtime.adapters.fakes import FakeObjectStore, FakeReviewQueue
from merry_runtime.adapters.sqlite_store import SQLiteStructuredStore
from merry_runtime.job_runner import RuntimeAdapters, run_job
from merry_runtime.pipelines.backup_export import (
    BACKUP_MANIFEST_HEADERS,
    SQLITE_BACKUP_HEADERS,
    WIKI_BACKUP_HEADERS,
    WIKI_CELL_CHUNK_SIZE,
)
from merry_runtime.runtime_config import RuntimeConfig
from merry_runtime.schema import BIGQUERY_TABLES
from merry_runtime.wiki_store import SQLiteWikiStore


def test_backup_export_writes_sqlite_copy_table_exports_wiki_archive_and_manifest(tmp_path) -> None:
    mother_db_path = tmp_path / "mother.db"
    backup_root = tmp_path / "backups"
    wiki_root = tmp_path / "wiki"
    wiki_store = SQLiteWikiStore(root=wiki_root)
    store = SQLiteStructuredStore(db_path=mother_db_path)
    store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": "ent_1",
                "entity_type": "startup",
                "name": "Merry AI",
                "normalized_name": "merry ai",
                "region": "Seoul",
                "industry": "AI",
                "first_seen_at": "2026-05-18T00:00:00+00:00",
                "last_seen_at": "2026-05-18T00:00:00+00:00",
            }
        ],
        key_fields=("entity_id",),
    )
    store.upsert_rows(
        table="signals",
        rows=[
            {
                "signal_id": "sig_large",
                "entity_id": "ent_1",
                "signal_type": "evidence",
                "evidence_text": "x" * (WIKI_CELL_CHUNK_SIZE + 1000),
                "source_id": "src_1",
                "confidence": 0.9,
                "tags": ["large"],
                "detected_at": "2026-05-18T00:00:00+00:00",
            }
        ],
        key_fields=("signal_id",),
    )
    (wiki_root / "entities").mkdir(parents=True)
    (wiki_root / "entities" / "merry-ai.md").write_text("# Merry AI\n", encoding="utf-8")
    review_queue = FakeReviewQueue()
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw"),
        structured_store=store,
        review_queue=review_queue,
        wiki_store=wiki_store,
    )
    config = RuntimeConfig(
        object_store_backend="local",
        structured_store_backend="sqlite",
        mother_db_path=mother_db_path,
        backup_root=backup_root,
        wiki_root=wiki_root,
        raw_root=tmp_path / "raw",
        project_id="",
        dataset_id="",
        raw_bucket="",
        review_sheet_id="sheet_1",
    )

    result = run_job("backup-export", runtime=runtime, config=config)

    manifest_path = backup_root / result["manifest_path"]
    db_backup_path = backup_root / result["sqlite_backup_path"]
    csv_path = backup_root / result["csv_paths"]["mother_entities"]
    jsonl_path = backup_root / result["jsonl_paths"]["mother_entities"]
    wiki_archive_path = backup_root / result["wiki_archive_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    jsonl_rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]

    assert result["job_name"] == "backup-export"
    assert manifest["row_counts"]["mother_entities"] == 1
    assert set(manifest["row_counts"]) == set(BIGQUERY_TABLES)
    assert db_backup_path.exists()
    assert csv_path.read_text(encoding="utf-8").splitlines()[0].startswith("entity_id,")
    assert jsonl_rows[0]["entity_id"] == "ent_1"
    with sqlite3.connect(db_backup_path) as connection:
        count = connection.execute("select count(*) from mother_entities").fetchone()[0]
    assert count == 1
    with tarfile.open(wiki_archive_path, "r:gz") as archive:
        assert "entities/merry-ai.md" in archive.getnames()

    assert result["sheet_backup_row_counts"]["SQLite Backup"] >= 1
    assert result["sheet_backup_row_counts"]["Wiki Backup"] == 1
    assert result["sheet_backup_row_counts"]["Backup Manifest"] >= 3
    assert review_queue.replaced_headers["SQLite Backup"] == SQLITE_BACKUP_HEADERS
    assert review_queue.replaced_headers["Wiki Backup"] == WIKI_BACKUP_HEADERS
    assert review_queue.replaced_headers["Backup Manifest"] == BACKUP_MANIFEST_HEADERS
    sqlite_backup_rows = review_queue.published["SQLite Backup"]
    assert any(
        row["table_name"] == "mother_entities" and '"entity_id": "ent_1"' in row["row_json"]
        for row in sqlite_backup_rows
    )
    large_signal_chunks = [
        row
        for row in sqlite_backup_rows
        if row["table_name"] == "signals" and row["row_index"] == 0
    ]
    assert len(large_signal_chunks) > 1
    assert {row["chunk_count"] for row in large_signal_chunks} == {len(large_signal_chunks)}
    assert {row["sha256"] for row in large_signal_chunks} == {large_signal_chunks[0]["sha256"]}
    assert all(len(str(row["row_json"])) <= WIKI_CELL_CHUNK_SIZE for row in large_signal_chunks)
    wiki_backup_rows = review_queue.published["Wiki Backup"]
    assert wiki_backup_rows == [
        {
            "backup_run_id": result["run_id"],
            "path": "entities/merry-ai.md",
            "chunk_index": 0,
            "chunk_count": 1,
            "sha256": wiki_backup_rows[0]["sha256"],
            "content": "# Merry AI\n",
        }
    ]
    assert review_queue.published["Backup Manifest"][0]["backup_run_id"] == result["run_id"]
