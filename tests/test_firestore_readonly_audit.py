from __future__ import annotations

import pytest

from merry_runtime.firestore_readonly import (
    DEFAULT_AUDIT_COLLECTIONS,
    build_access_token_command,
    build_documents_list_url,
    validate_collection_path,
)


def test_default_audit_collections_stay_inside_mysc_tenant() -> None:
    for path in DEFAULT_AUDIT_COLLECTIONS:
        assert validate_collection_path(path, tenant_id="mysc") == path


def test_collection_path_validation_rejects_cross_tenant_and_write_like_paths() -> None:
    with pytest.raises(ValueError, match="tenant"):
        validate_collection_path("orgs/other/projects", tenant_id="mysc")

    with pytest.raises(ValueError, match="collection"):
        validate_collection_path("orgs/mysc/projects/p1", tenant_id="mysc")

    with pytest.raises(ValueError, match="unsafe"):
        validate_collection_path("../orgs/mysc/projects", tenant_id="mysc")


def test_documents_list_url_uses_firestore_rest_read_endpoint() -> None:
    url = build_documents_list_url(
        project_id="inner-platform-live-20260316",
        collection_path="orgs/mysc/projects",
        page_size=3,
    )

    assert url.startswith("https://firestore.googleapis.com/v1/projects/inner-platform-live-20260316/")
    assert "/databases/(default)/documents/orgs/mysc/projects" in url
    assert "pageSize=3" in url


def test_access_token_command_uses_service_account_impersonation_without_keys() -> None:
    command = build_access_token_command("hermes-firestore-auditor@example.iam.gserviceaccount.com")

    assert command == [
        "gcloud",
        "auth",
        "print-access-token",
        "--impersonate-service-account",
        "hermes-firestore-auditor@example.iam.gserviceaccount.com",
    ]
