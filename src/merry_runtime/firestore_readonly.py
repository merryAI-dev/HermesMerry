from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


DEFAULT_PROJECT_ID = "inner-platform-live-20260316"
DEFAULT_TENANT_ID = "mysc"
DEFAULT_AUDIT_COLLECTIONS = [
    "orgs/mysc/members",
    "orgs/mysc/projects",
    "orgs/mysc/project_requests",
    "orgs/mysc/transactions",
    "orgs/mysc/cashflow_weeks",
    "orgs/mysc/cashflowWeeks",
    "orgs/mysc/audit_logs",
]


@dataclass(frozen=True)
class CollectionSnapshot:
    path: str
    ok: bool
    document_count: int
    sample_names: list[str]
    error: str = ""


def validate_collection_path(path: str, *, tenant_id: str) -> str:
    normalized = path.strip().strip("/")
    parts = [part for part in normalized.split("/") if part]
    if any(part in {".", ".."} for part in parts) or normalized != path.strip().strip("/"):
        raise ValueError(f"unsafe Firestore collection path: {path}")
    if len(parts) < 3 or len(parts) % 2 == 0:
        raise ValueError(f"path must point to a Firestore collection, not a document: {path}")
    if parts[0] != "orgs" or parts[1] != tenant_id:
        raise ValueError(f"path is outside tenant {tenant_id}: {path}")
    return normalized


def build_documents_list_url(*, project_id: str, collection_path: str, page_size: int = 10) -> str:
    safe_project_id = project_id.strip()
    if not safe_project_id:
        raise ValueError("project_id is required")
    safe_page_size = max(1, min(int(page_size), 100))
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in collection_path.split("/"))
    query = urllib.parse.urlencode({"pageSize": safe_page_size})
    return (
        "https://firestore.googleapis.com/v1/"
        f"projects/{urllib.parse.quote(safe_project_id, safe='')}/databases/(default)/documents/{encoded_path}?{query}"
    )


def build_access_token_command(impersonate_service_account: str | None = None) -> list[str]:
    command = ["gcloud", "auth", "print-access-token"]
    if impersonate_service_account:
        command.extend(["--impersonate-service-account", impersonate_service_account])
    return command


def get_access_token(*, impersonate_service_account: str | None = None) -> str:
    result = subprocess.run(
        build_access_token_command(impersonate_service_account),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "gcloud auth failed").strip())
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty access token")
    return token


def list_collection(
    *,
    project_id: str,
    tenant_id: str,
    collection_path: str,
    access_token: str,
    page_size: int = 10,
) -> CollectionSnapshot:
    safe_path = validate_collection_path(collection_path, tenant_id=tenant_id)
    url = build_documents_list_url(project_id=project_id, collection_path=safe_path, page_size=page_size)
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return CollectionSnapshot(path=safe_path, ok=False, document_count=0, sample_names=[], error=detail or str(exc))
    except Exception as exc:
        return CollectionSnapshot(path=safe_path, ok=False, document_count=0, sample_names=[], error=str(exc))

    documents = payload.get("documents", []) if isinstance(payload, dict) else []
    names = [str(item.get("name", "")) for item in documents if isinstance(item, dict) and item.get("name")]
    return CollectionSnapshot(path=safe_path, ok=True, document_count=len(names), sample_names=names)


def audit_collections(
    *,
    project_id: str,
    tenant_id: str,
    collection_paths: Iterable[str],
    impersonate_service_account: str | None = None,
    page_size: int = 10,
) -> list[CollectionSnapshot]:
    token = get_access_token(impersonate_service_account=impersonate_service_account)
    return [
        list_collection(
            project_id=project_id,
            tenant_id=tenant_id,
            collection_path=path,
            access_token=token,
            page_size=page_size,
        )
        for path in collection_paths
    ]


def _default_collections_for_tenant(tenant_id: str) -> list[str]:
    return [path.replace(f"orgs/{DEFAULT_TENANT_ID}/", f"orgs/{tenant_id}/", 1) for path in DEFAULT_AUDIT_COLLECTIONS]


def _to_dict(snapshot: CollectionSnapshot) -> dict[str, Any]:
    return {
        "path": snapshot.path,
        "ok": snapshot.ok,
        "document_count": snapshot.document_count,
        "sample_names": snapshot.sample_names,
        "error": snapshot.error,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Firestore tenant ledger audit.")
    parser.add_argument("--project-id", default=os.getenv("HERMES_FIRESTORE_PROJECT_ID", DEFAULT_PROJECT_ID))
    parser.add_argument("--tenant-id", default=os.getenv("HERMES_FIRESTORE_TENANT_ID", DEFAULT_TENANT_ID))
    parser.add_argument(
        "--impersonate-service-account",
        default=os.getenv("HERMES_FIRESTORE_IMPERSONATE_SERVICE_ACCOUNT", ""),
        help="Service account email to impersonate. Prefer this over JSON keys.",
    )
    parser.add_argument("--collection", action="append", default=[], help="Tenant-scoped collection path to list.")
    parser.add_argument("--page-size", type=int, default=10)
    args = parser.parse_args(argv)

    collections = args.collection or _default_collections_for_tenant(args.tenant_id)
    snapshots = audit_collections(
        project_id=args.project_id,
        tenant_id=args.tenant_id,
        collection_paths=collections,
        impersonate_service_account=args.impersonate_service_account or None,
        page_size=args.page_size,
    )
    print(json.dumps([_to_dict(item) for item in snapshots], ensure_ascii=False, indent=2))
    return 0 if all(item.ok for item in snapshots) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
