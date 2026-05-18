from merry_runtime.adapters.interfaces import Notifier, ObjectStore, ReviewQueue, StructuredStore


def test_adapter_protocols_define_required_runtime_methods() -> None:
    assert "write_raw_text" in ObjectStore.__dict__
    assert "upsert_rows" in StructuredStore.__dict__
    assert "query_rows" in StructuredStore.__dict__
    assert "publish_cards" in ReviewQueue.__dict__
    assert "upsert_cards" in ReviewQueue.__dict__
    assert "replace_rows" in ReviewQueue.__dict__
    assert "read_pending_reviews" in ReviewQueue.__dict__
    assert "send_message" in Notifier.__dict__
