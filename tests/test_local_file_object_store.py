import pytest

from merry_runtime.adapters.local_files import LocalFileObjectStore


def test_local_file_object_store_writes_create_only_raw_text(tmp_path) -> None:
    store = LocalFileObjectStore(root=tmp_path)

    uri = store.write_raw_text(path="raw/source.txt", text="first", content_type="text/plain")
    second_uri = store.write_raw_text(path="raw/source.txt", text="second", content_type="text/plain")

    assert uri == second_uri
    assert (tmp_path / "raw" / "source.txt").read_text(encoding="utf-8") == "first"
    assert uri.startswith("file://")


def test_local_file_object_store_rejects_path_traversal(tmp_path) -> None:
    store = LocalFileObjectStore(root=tmp_path)

    with pytest.raises(ValueError):
        store.write_raw_text(path="../secret.txt", text="x", content_type="text/plain")
