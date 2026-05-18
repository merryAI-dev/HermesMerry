# SQLite Sheet Runtime Design

## Decision

Hermes staging moves BigQuery out of the critical path. The primary runtime
memory is a SQLite database on the Runpod persistent volume, the Obsidian wiki
remains the human-readable projection, and Google Sheets becomes the human
operating console for review, settings, exploration, and run visibility.

BigQuery stays as an optional warehouse/export target. The runtime must not
require BigQuery billing for the always-on loop.

## Runtime Architecture

Runpod owns the long-lived loop and stores durable state under
`/workspace/hermes`:

- `MOTHER_DB_PATH=/workspace/hermes/mother.db`
- `WIKI_ROOT=/workspace/hermes/wiki`
- `RAW_ROOT=/workspace/hermes/raw`
- `BACKUP_ROOT=/workspace/hermes/backups`

`SQLiteStructuredStore` implements the existing `StructuredStore` protocol so
pipelines can keep using `upsert_rows()` and `query_rows()`. BigQuery remains
available through `STRUCTURED_STORE_BACKEND=bigquery`; SQLite becomes the
default for Runpod with `STRUCTURED_STORE_BACKEND=sqlite`.

## Sheet Console

The Sheet is not the database. It is the human front. Hermes publishes stable,
ID-based rows and only consumes constrained human-editable fields.

Tabs:

- `Review Queue`: daily candidate queue for human decisions.
- `Candidate Detail`: richer candidate facts, latest score, and evidence text.
- `Evidence`: source and signal rows with trust, PII, and evidence metadata.
- `Decision Log`: append-only review history.
- `AC Settings`: editable AC thesis, recruiting scope, exclusions, and weight
  overrides.
- `Exploration Queue`: uncertain or hypothesis-challenging candidates.
- `Run Log`: agent run status and failure summaries.

Humans may edit decision, memo, reviewer, owner, next action, due date, and
override fields. Hermes must not depend on row order.

## Backup And Export

The runtime adds a `backup-export` job that writes:

- a SQLite backup copy,
- CSV exports for all structured tables,
- JSONL exports for all structured tables,
- a compressed wiki archive,
- a manifest with timestamp and row counts.

The backup job is local-first and can later copy artifacts to GCS or Drive.

## Safety

SQLite replaces BigQuery only as the operational store. The safety boundary
remains: Hermes writes through domain-specific adapters, humans decide through
Sheets, raw files stay under the configured raw root, and generated wiki files
stay under the configured wiki root.

Runpod one-cycle canaries should still sleep after the finite command to avoid
restart loops. Always-on mode is allowed with SQLite because it does not need
BigQuery DML/MERGE.

## Success Criteria

- `make verify` passes.
- Runtime can be built with `STRUCTURED_STORE_BACKEND=sqlite` without importing
  `google.cloud.bigquery`.
- Core jobs read/write SQLite through the existing `StructuredStore` protocol.
- Sheet headers expose the stronger console tabs.
- `backup-export` creates restorable SQLite and portable CSV/JSONL artifacts.
- Runpod docs describe SQLite + Sheet as the primary staging path and BigQuery
  as optional export infrastructure.
