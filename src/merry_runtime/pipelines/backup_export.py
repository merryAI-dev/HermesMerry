from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from merry_runtime.adapters.interfaces import ReviewQueue, StructuredStore
from merry_runtime.clock import compact_kst_timestamp, now_kst
from merry_runtime.schema import BIGQUERY_TABLES

SQLITE_BACKUP_TAB = "SQLite Backup"
WIKI_BACKUP_TAB = "Wiki Backup"
BACKUP_MANIFEST_TAB = "Backup Manifest"
SQLITE_BACKUP_HEADERS = ("backup_run_id", "table_name", "row_index", "chunk_index", "chunk_count", "sha256", "row_json")
WIKI_BACKUP_HEADERS = ("backup_run_id", "path", "chunk_index", "chunk_count", "sha256", "content")
BACKUP_MANIFEST_HEADERS = ("backup_run_id", "created_at", "artifact", "path", "row_count", "details_json")
WIKI_CELL_CHUNK_SIZE = 45_000


@dataclass(frozen=True, slots=True)
class BackupExportResult:
    run_id: str
    manifest_path: str
    sqlite_backup_path: str
    wiki_archive_path: str
    csv_paths: dict[str, str]
    jsonl_paths: dict[str, str]
    row_counts: dict[str, int]
    sheet_backup_row_counts: dict[str, int]


def backup_export(
    *,
    structured_store: StructuredStore,
    backup_root: Path,
    wiki_root: Path,
    review_queue: ReviewQueue | None = None,
    run_id: str | None = None,
) -> BackupExportResult:
    source_db_path = _sqlite_db_path(structured_store)
    timestamp = compact_kst_timestamp()
    run_id = run_id or f"backup_{timestamp}"
    export_root = backup_root / run_id
    csv_root = export_root / "csv"
    jsonl_root = export_root / "jsonl"
    csv_root.mkdir(parents=True, exist_ok=True)
    jsonl_root.mkdir(parents=True, exist_ok=True)

    sqlite_backup_path = export_root / "mother.db"
    _backup_sqlite(source_db_path=source_db_path, target_db_path=sqlite_backup_path)

    row_counts: dict[str, int] = {}
    csv_paths: dict[str, str] = {}
    jsonl_paths: dict[str, str] = {}
    table_rows: dict[str, list[dict[str, Any]]] = {}
    for table, fields in BIGQUERY_TABLES.items():
        rows = structured_store.query_rows(sql=f"select * from {table}", parameters={})
        table_rows[table] = rows
        row_counts[table] = len(rows)
        headers = [field["name"] for field in fields]
        csv_path = csv_root / f"{table}.csv"
        jsonl_path = jsonl_root / f"{table}.jsonl"
        _write_csv(path=csv_path, headers=headers, rows=rows)
        _write_jsonl(path=jsonl_path, rows=rows)
        csv_paths[table] = _relative(path=csv_path, root=backup_root)
        jsonl_paths[table] = _relative(path=jsonl_path, root=backup_root)

    wiki_archive_path = export_root / "wiki.tar.gz"
    _archive_wiki(wiki_root=wiki_root, target_path=wiki_archive_path)

    manifest_path = export_root / "manifest.json"
    relative_manifest_path = _relative(path=manifest_path, root=backup_root)
    manifest = {
        "run_id": run_id,
        "created_at": now_kst(),
        "source_db_path": str(source_db_path),
        "wiki_root": str(wiki_root),
        "manifest_path": relative_manifest_path,
        "sqlite_backup_path": _relative(path=sqlite_backup_path, root=backup_root),
        "wiki_archive_path": _relative(path=wiki_archive_path, root=backup_root),
        "csv_paths": csv_paths,
        "jsonl_paths": jsonl_paths,
        "row_counts": row_counts,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    sheet_backup_row_counts = _write_sheet_backup(
        review_queue=review_queue,
        run_id=run_id,
        created_at=str(manifest["created_at"]),
        table_rows=table_rows,
        wiki_root=wiki_root,
        manifest=manifest,
    )

    return BackupExportResult(
        run_id=run_id,
        manifest_path=relative_manifest_path,
        sqlite_backup_path=_relative(path=sqlite_backup_path, root=backup_root),
        wiki_archive_path=_relative(path=wiki_archive_path, root=backup_root),
        csv_paths=csv_paths,
        jsonl_paths=jsonl_paths,
        row_counts=row_counts,
        sheet_backup_row_counts=sheet_backup_row_counts,
    )


def _write_sheet_backup(
    *,
    review_queue: ReviewQueue | None,
    run_id: str,
    created_at: str,
    table_rows: dict[str, list[dict[str, Any]]],
    wiki_root: Path,
    manifest: dict[str, Any],
) -> dict[str, int]:
    if review_queue is None:
        return {}

    sqlite_rows = _sqlite_sheet_rows(run_id=run_id, table_rows=table_rows)
    wiki_rows = _wiki_sheet_rows(run_id=run_id, wiki_root=wiki_root)
    manifest_rows = _manifest_sheet_rows(run_id=run_id, created_at=created_at, manifest=manifest)
    return {
        SQLITE_BACKUP_TAB: review_queue.replace_rows(
            sheet_tab=SQLITE_BACKUP_TAB,
            headers=SQLITE_BACKUP_HEADERS,
            rows=sqlite_rows,
        ),
        WIKI_BACKUP_TAB: review_queue.replace_rows(
            sheet_tab=WIKI_BACKUP_TAB,
            headers=WIKI_BACKUP_HEADERS,
            rows=wiki_rows,
        ),
        BACKUP_MANIFEST_TAB: review_queue.replace_rows(
            sheet_tab=BACKUP_MANIFEST_TAB,
            headers=BACKUP_MANIFEST_HEADERS,
            rows=manifest_rows,
        ),
    }


def _sqlite_sheet_rows(*, run_id: str, table_rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for table in sorted(table_rows):
        for index, row in enumerate(table_rows[table]):
            row_json = json.dumps(row, ensure_ascii=False, sort_keys=True)
            chunks = _chunk_text(row_json)
            digest = hashlib.sha256(row_json.encode("utf-8")).hexdigest()
            for chunk_index, chunk in enumerate(chunks):
                rows.append(
                    {
                        "backup_run_id": run_id,
                        "table_name": table,
                        "row_index": index,
                        "chunk_index": chunk_index,
                        "chunk_count": len(chunks),
                        "sha256": digest,
                        "row_json": chunk,
                    }
                )
    return rows


def _wiki_sheet_rows(*, run_id: str, wiki_root: Path) -> list[dict[str, object]]:
    if not wiki_root.exists():
        return []
    rows: list[dict[str, object]] = []
    for path in sorted(wiki_root.rglob("*.md")):
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        chunks = _chunk_text(content)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        relative_path = path.relative_to(wiki_root).as_posix()
        for index, chunk in enumerate(chunks):
            rows.append(
                {
                    "backup_run_id": run_id,
                    "path": relative_path,
                    "chunk_index": index,
                    "chunk_count": len(chunks),
                    "sha256": digest,
                    "content": chunk,
                }
            )
    return rows


def _manifest_sheet_rows(*, run_id: str, created_at: str, manifest: dict[str, Any]) -> list[dict[str, object]]:
    artifacts = [
        ("sqlite", manifest["sqlite_backup_path"], sum(int(count) for count in manifest["row_counts"].values())),
        ("wiki_archive", manifest["wiki_archive_path"], 0),
        ("manifest", manifest["manifest_path"], 1),
    ]
    for table, path in sorted(manifest["csv_paths"].items()):
        artifacts.append((f"csv:{table}", path, int(manifest["row_counts"].get(table, 0))))
    for table, path in sorted(manifest["jsonl_paths"].items()):
        artifacts.append((f"jsonl:{table}", path, int(manifest["row_counts"].get(table, 0))))
    return [
        {
            "backup_run_id": run_id,
            "created_at": created_at,
            "artifact": artifact,
            "path": path,
            "row_count": row_count,
            "details_json": json.dumps({"row_counts": manifest["row_counts"]}, ensure_ascii=False, sort_keys=True),
        }
        for artifact, path, row_count in artifacts
    ]


def _chunk_text(text: str) -> list[str]:
    if text == "":
        return [""]
    return [text[index : index + WIKI_CELL_CHUNK_SIZE] for index in range(0, len(text), WIKI_CELL_CHUNK_SIZE)]


def _sqlite_db_path(structured_store: StructuredStore) -> Path:
    db_path = getattr(structured_store, "db_path", None)
    if db_path is None:
        raise ValueError("backup-export requires a SQLite structured store with db_path")
    return Path(db_path)


def _backup_sqlite(*, source_db_path: Path, target_db_path: Path) -> None:
    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source_db_path) as source, sqlite3.connect(target_db_path) as target:
        source.backup(target)


def _write_csv(*, path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: _export_value(row.get(header, "")) for header in headers})


def _write_jsonl(*, path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            file.write("\n")


def _archive_wiki(*, wiki_root: Path, target_path: Path) -> None:
    with tarfile.open(target_path, "w:gz") as archive:
        if not wiki_root.exists():
            return
        for path in sorted(wiki_root.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(wiki_root))


def _export_value(value: object) -> object:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _relative(*, path: Path, root: Path) -> str:
    return str(path.relative_to(root))
