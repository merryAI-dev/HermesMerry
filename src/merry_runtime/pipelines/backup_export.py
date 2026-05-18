from __future__ import annotations

import csv
import json
import sqlite3
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from merry_runtime.adapters.interfaces import StructuredStore
from merry_runtime.schema import BIGQUERY_TABLES


@dataclass(frozen=True, slots=True)
class BackupExportResult:
    run_id: str
    manifest_path: str
    sqlite_backup_path: str
    wiki_archive_path: str
    csv_paths: dict[str, str]
    jsonl_paths: dict[str, str]
    row_counts: dict[str, int]


def backup_export(
    *,
    structured_store: StructuredStore,
    backup_root: Path,
    wiki_root: Path,
    run_id: str | None = None,
) -> BackupExportResult:
    source_db_path = _sqlite_db_path(structured_store)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
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
    for table, fields in BIGQUERY_TABLES.items():
        rows = structured_store.query_rows(sql=f"select * from {table}", parameters={})
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
    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "source_db_path": str(source_db_path),
        "wiki_root": str(wiki_root),
        "sqlite_backup_path": _relative(path=sqlite_backup_path, root=backup_root),
        "wiki_archive_path": _relative(path=wiki_archive_path, root=backup_root),
        "csv_paths": csv_paths,
        "jsonl_paths": jsonl_paths,
        "row_counts": row_counts,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    return BackupExportResult(
        run_id=run_id,
        manifest_path=_relative(path=manifest_path, root=backup_root),
        sqlite_backup_path=_relative(path=sqlite_backup_path, root=backup_root),
        wiki_archive_path=_relative(path=wiki_archive_path, root=backup_root),
        csv_paths=csv_paths,
        jsonl_paths=jsonl_paths,
        row_counts=row_counts,
    )


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
