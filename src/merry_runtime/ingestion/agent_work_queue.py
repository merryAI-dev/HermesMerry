from __future__ import annotations

import hashlib
import json
from typing import Any


RETRYABLE_AGENT_WORK_STATUSES = {"pending", "retry"}
TERMINAL_AGENT_WORK_STATUSES = {"done", "failed", "blocked"}


def build_agent_work_task(
    *,
    chain_id: str,
    stage: str,
    job_name: str,
    payload: dict[str, object],
    now: str,
    dependency_task_id: str = "",
    priority: int = 100,
    max_attempts: int = 3,
) -> dict[str, object]:
    payload_json = _payload_json(payload)
    return {
        "task_id": agent_work_task_id(
            chain_id=chain_id,
            stage=stage,
            job_name=job_name,
            payload_json=payload_json,
            dependency_task_id=dependency_task_id,
        ),
        "chain_id": chain_id,
        "stage": stage,
        "job_name": job_name,
        "payload_json": payload_json,
        "dependency_task_id": dependency_task_id,
        "status": "pending",
        "priority": priority,
        "attempt_count": 0,
        "max_attempts": max(max_attempts, 1),
        "next_run_at": now,
        "locked_at": "",
        "locked_by": "",
        "last_error": "",
        "created_at": now,
        "updated_at": now,
        "completed_at": "",
    }


def agent_work_task_id(
    *,
    chain_id: str,
    stage: str,
    job_name: str,
    payload_json: str,
    dependency_task_id: str,
) -> str:
    digest = hashlib.sha1(
        "\n".join((chain_id, stage, job_name, payload_json, dependency_task_id)).encode("utf-8")
    ).hexdigest()[:16]
    return f"agent_task_{digest}"


def is_blocking_agent_work_error(exc: Exception) -> bool:
    message = f"{type(exc).__name__}: {exc}".casefold()
    blocking_fragments = (
        "missing required environment",
        "requires a configured",
        "requires --sources-json",
        "requires ac_id",
        "review_sheet_id is required",
        "not configured",
    )
    return any(fragment in message for fragment in blocking_fragments)


def _payload_json(payload: dict[str, object]) -> str:
    return json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
