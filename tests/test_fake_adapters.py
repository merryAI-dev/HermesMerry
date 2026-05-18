from merry_runtime.adapters.fakes import FakeNotifier, FakeObjectStore, FakeReviewQueue, FakeStructuredStore


def test_fake_structured_store_upserts_by_key() -> None:
    store = FakeStructuredStore()

    store.upsert_rows(table="mother_entities", rows=[{"entity_id": "ent_1", "name": "A"}], key_fields=("entity_id",))
    store.upsert_rows(table="mother_entities", rows=[{"entity_id": "ent_1", "name": "B"}], key_fields=("entity_id",))

    assert store.tables["mother_entities"] == [{"entity_id": "ent_1", "name": "B"}]


def test_fake_structured_store_query_rows_filters_by_parameters() -> None:
    store = FakeStructuredStore()
    store.upsert_rows(
        table="signals",
        rows=[
            {"signal_id": "sig_1", "entity_id": "ent_1"},
            {"signal_id": "sig_2", "entity_id": "ent_2"},
        ],
        key_fields=("signal_id",),
    )

    rows = store.query_rows(sql="select * from signals where entity_id=@entity_id", parameters={"entity_id": "ent_1"})

    assert rows == [{"signal_id": "sig_1", "entity_id": "ent_1"}]


def test_fake_object_store_returns_gs_uri_and_keeps_payload() -> None:
    store = FakeObjectStore(bucket="raw-bucket")

    uri = store.write_raw_text(path="raw/a.txt", text="hello", content_type="text/plain")

    assert uri == "gs://raw-bucket/raw/a.txt"
    assert store.objects["raw/a.txt"] == {"text": "hello", "content_type": "text/plain"}


def test_fake_review_queue_round_trips_review_rows() -> None:
    queue = FakeReviewQueue()

    queue.seed_reviews("ac_climate", [{"card_id": "card_1", "reviewer": "boram", "decision": "advance"}])

    assert queue.read_pending_reviews(sheet_tab="ac_climate")[0]["decision"] == "advance"


def test_fake_review_queue_publishes_cards_to_sheet_tab() -> None:
    queue = FakeReviewQueue()

    published_count = queue.publish_cards(sheet_tab="ac_climate", rows=[{"card_id": "card_1", "decision": ""}])

    assert published_count == 1
    assert queue.published["ac_climate"] == [{"card_id": "card_1", "decision": ""}]


def test_fake_notifier_records_messages() -> None:
    notifier = FakeNotifier()

    message_id = notifier.send_message(channel="C123", text="Weekly summary")

    assert message_id == "msg_000001"
    assert notifier.messages == [{"message_id": "msg_000001", "channel": "C123", "text": "Weekly summary"}]
