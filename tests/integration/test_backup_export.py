import json
import sqlite3
import tarfile

from merry_runtime.adapters.fakes import FakeObjectStore, FakeReviewQueue
from merry_runtime.adapters.sqlite_store import SQLiteStructuredStore
from merry_runtime.job_runner import RuntimeAdapters, run_job
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
    (wiki_root / "entities").mkdir(parents=True)
    (wiki_root / "entities" / "merry-ai.md").write_text("# Merry AI\n", encoding="utf-8")
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw"),
        structured_store=store,
        review_queue=FakeReviewQueue(),
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
