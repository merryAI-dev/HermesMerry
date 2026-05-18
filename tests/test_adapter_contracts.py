from merry_runtime.adapters.bigquery import BigQueryStructuredStore, build_query_job_config
from merry_runtime.adapters.gcs import GCSObjectStore
from merry_runtime.adapters.gmail import GmailLabelSource
from merry_runtime.adapters.google_sheets import GoogleSheetReviewQueue
from merry_runtime.adapters.slack import SlackNotifier


class FakeBlob:
    def __init__(self) -> None:
        self.uploaded: dict[str, str] = {}

    def upload_from_string(self, text: str, *, content_type: str) -> None:
        self.uploaded = {"text": text, "content_type": content_type}


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


def test_gcs_object_store_uploads_text_and_returns_gs_uri() -> None:
    client = FakeGCSClient()
    store = GCSObjectStore(client=client, bucket="raw-bucket")

    uri = store.write_raw_text(path="/raw/a.txt", text="hello", content_type="text/plain")

    assert uri == "gs://raw-bucket/raw/a.txt"
    assert client.bucket_name == "raw-bucket"
    assert client.bucket_obj.blobs["raw/a.txt"].uploaded == {"text": "hello", "content_type": "text/plain"}


class FakeQueryJob:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or []

    def result(self) -> list[dict[str, object]]:
        return self.rows


class FakeBigQueryClient:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, object]]] = []
        self.inserted: list[tuple[str, list[dict[str, object]]]] = []

    def query(self, sql: str, job_config: object | None = None) -> FakeQueryJob:
        self.queries.append((sql, getattr(job_config, "parameters", {})))
        return FakeQueryJob([{"entity_id": "ent_1", "name": "Merry AI"}])

    def insert_rows_json(self, table_id: str, rows: list[dict[str, object]]) -> list[object]:
        self.inserted.append((table_id, rows))
        return []


def test_bigquery_structured_store_deletes_keys_then_inserts_rows() -> None:
    client = FakeBigQueryClient()
    store = BigQueryStructuredStore(client=client, project_id="p", dataset_id="d")

    count = store.upsert_rows(table="mother_entities", rows=[{"entity_id": "ent_1", "name": "Merry AI"}], key_fields=("entity_id",))

    assert count == 1
    assert "DELETE FROM `p.d.mother_entities`" in client.queries[0][0]
    assert client.inserted == [("p.d.mother_entities", [{"entity_id": "ent_1", "name": "Merry AI"}])]


def test_bigquery_structured_store_query_rows_returns_dicts() -> None:
    client = FakeBigQueryClient()
    store = BigQueryStructuredStore(client=client, project_id="p", dataset_id="d")

    rows = store.query_rows(sql="select * from mother_entities", parameters={"entity_id": "ent_1"})

    assert rows == [{"entity_id": "ent_1", "name": "Merry AI"}]


class FakeScalarQueryParameter:
    def __init__(self, name: str, parameter_type: str, value: object) -> None:
        self.name = name
        self.parameter_type = parameter_type
        self.value = value


class FakeQueryJobConfig:
    def __init__(self, *, query_parameters: list[FakeScalarQueryParameter]) -> None:
        self.query_parameters = query_parameters


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

    def append(self, **kwargs: object) -> "FakeValues":
        self.append_kwargs = kwargs
        self.append_body = kwargs["body"]  # type: ignore[index]
        return self

    def get(self, **kwargs: object) -> "FakeValues":
        self.get_kwargs = kwargs
        return self

    def execute(self) -> dict[str, object]:
        if hasattr(self, "get_kwargs"):
            return {"values": [["card_id", "reviewer", "decision"], ["card_1", "boram", "advance"]]}
        return {"updates": {"updatedRows": 1}}


class FakeSheetsService:
    def __init__(self) -> None:
        self.values_obj = FakeValues()

    def spreadsheets(self) -> "FakeSheetsService":
        return self

    def values(self) -> FakeValues:
        return self.values_obj


def test_google_sheet_review_queue_publishes_rows_and_reads_reviews() -> None:
    service = FakeSheetsService()
    queue = GoogleSheetReviewQueue(service=service, spreadsheet_id="sheet_1")

    published = queue.publish_cards(sheet_tab="ac_climate", rows=[{"card_id": "card_1", "decision": ""}])
    reviews = queue.read_pending_reviews(sheet_tab="ac_climate")

    assert published == 1
    assert service.values_obj.append_body == {"values": [["card_1", ""]]}
    assert reviews == [{"card_id": "card_1", "reviewer": "boram", "decision": "advance"}]


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
