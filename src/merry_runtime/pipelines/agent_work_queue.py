from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from merry_runtime.clock import now_kst
from merry_runtime.ingestion.agent_work_queue import build_agent_work_task, is_blocking_agent_work_error


@dataclass(frozen=True, slots=True)
class AgentWorkStage:
    stage: str
    job_name: str
    payload: dict[str, object]
    priority: int = 100
    max_attempts: int = 3


@dataclass(frozen=True, slots=True)
class AgentWorkQueueSpec:
    chain_id: str
    description: str
    stages: tuple[AgentWorkStage, ...]
    risks: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class AgentWorkQueueResult:
    run_id: str
    chain_id: str
    seeded_count: int
    processed_count: int
    enqueued_count: int
    done_count: int
    failed_count: int
    blocked_count: int


RunJobFn = Callable[..., dict[str, object]]
NowFn = Callable[[], str]


def load_agent_work_queue_spec(path: Path) -> AgentWorkQueueSpec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stages = tuple(
        AgentWorkStage(
            stage=str(stage["stage"]),
            job_name=str(stage["job_name"]),
            payload=dict(stage.get("payload") or {}),
            priority=_int(stage.get("priority"), default=100),
            max_attempts=max(_int(stage.get("max_attempts"), default=3), 1),
        )
        for stage in payload.get("stages", [])
    )
    if not stages:
        raise ValueError(f"Agent work queue spec has no stages: {path}")
    return AgentWorkQueueSpec(
        chain_id=str(payload["chain_id"]),
        description=str(payload.get("description") or ""),
        stages=stages,
        risks=tuple(dict(risk) for risk in payload.get("risks", [])),
    )


def run_agent_work_queue(
    *,
    runtime: object,
    config: object,
    structured_store: Any,
    spec: AgentWorkQueueSpec,
    max_tasks: int,
    agent_id: str,
    run_job_fn: RunJobFn,
    now_fn: NowFn = now_kst,
    run_id: str | None = None,
) -> AgentWorkQueueResult:
    started_at = now_fn()
    run_id = run_id or f"run_agent_work_queue_{_short_digest(spec.chain_id, started_at)}"
    seeded_count = _ensure_seed_task(structured_store=structured_store, spec=spec, now=started_at)
    processed_count = 0
    enqueued_count = 0
    done_count = 0
    failed_count = 0
    blocked_count = 0

    for _ in range(max(max_tasks, 0)):
        leased = _claim_agent_work_tasks(
            structured_store=structured_store,
            max_items=1,
            reference_time=now_fn(),
            agent_id=agent_id,
            leased_at=now_fn(),
        )
        if not leased:
            break
        task = leased[0]
        processed_count += 1
        try:
            run_job_fn(str(task["job_name"]), runtime=runtime, config=config)
        except Exception as exc:
            updated_task, blocked = _failed_task_update(task=task, exc=exc, now=now_fn())
            structured_store.upsert_rows(table="agent_work_queue", rows=[updated_task], key_fields=("task_id",))
            if blocked:
                blocked_count += 1
                break
            failed_count += 1
            continue

        finished_at = now_fn()
        done_task = {
            **task,
            "status": "done",
            "locked_at": "",
            "locked_by": "",
            "last_error": "",
            "updated_at": finished_at,
            "completed_at": finished_at,
        }
        structured_store.upsert_rows(table="agent_work_queue", rows=[done_task], key_fields=("task_id",))
        done_count += 1
        next_task = _next_task(spec=spec, current_task=done_task, now=finished_at)
        if next_task is not None and not _task_exists(
            structured_store=structured_store,
            task_id=str(next_task["task_id"]),
        ):
            structured_store.upsert_rows(table="agent_work_queue", rows=[next_task], key_fields=("task_id",))
            enqueued_count += 1

    result = AgentWorkQueueResult(
        run_id=run_id,
        chain_id=spec.chain_id,
        seeded_count=seeded_count,
        processed_count=processed_count,
        enqueued_count=enqueued_count,
        done_count=done_count,
        failed_count=failed_count,
        blocked_count=blocked_count,
    )
    _record_agent_run(
        structured_store=structured_store,
        result=result,
        started_at=started_at,
        finished_at=now_fn(),
    )
    return result


def _ensure_seed_task(*, structured_store: Any, spec: AgentWorkQueueSpec, now: str) -> int:
    existing = [
        row
        for row in _all_tasks(structured_store=structured_store)
        if str(row.get("chain_id") or "") == spec.chain_id
    ]
    if existing:
        return 0
    first = spec.stages[0]
    task = build_agent_work_task(
        chain_id=spec.chain_id,
        stage=first.stage,
        job_name=first.job_name,
        payload=first.payload,
        now=now,
        priority=first.priority,
        max_attempts=first.max_attempts,
    )
    structured_store.upsert_rows(table="agent_work_queue", rows=[task], key_fields=("task_id",))
    return 1


def _claim_agent_work_tasks(
    *,
    structured_store: Any,
    max_items: int,
    reference_time: str,
    agent_id: str,
    leased_at: str,
) -> list[dict[str, object]]:
    lease = getattr(structured_store, "lease_agent_work_tasks", None)
    if callable(lease):
        return list(
            lease(
                max_items=max_items,
                reference_time=reference_time,
                agent_id=agent_id,
                leased_at=leased_at,
            )
        )

    tasks = _due_tasks(structured_store=structured_store, reference_time=reference_time, max_items=max_items)
    if not tasks:
        return []
    leased = [
        {
            **task,
            "status": "running",
            "locked_at": leased_at,
            "locked_by": agent_id,
            "updated_at": leased_at,
        }
        for task in tasks
    ]
    structured_store.upsert_rows(table="agent_work_queue", rows=leased, key_fields=("task_id",))
    return leased


def _due_tasks(*, structured_store: Any, reference_time: str, max_items: int) -> list[dict[str, object]]:
    rows = _all_tasks(structured_store=structured_store)
    by_task_id = {str(row.get("task_id") or ""): row for row in rows}
    due_rows: list[dict[str, object]] = []
    for row in rows:
        status = str(row.get("status") or "")
        if status not in {"pending", "retry"}:
            continue
        if str(row.get("next_run_at") or "") > reference_time:
            continue
        dependency_task_id = str(row.get("dependency_task_id") or "")
        if dependency_task_id and str(by_task_id.get(dependency_task_id, {}).get("status") or "") != "done":
            continue
        due_rows.append(dict(row))
    return sorted(due_rows, key=lambda row: (_int(row.get("priority"), default=100), str(row.get("created_at") or "")))[
        : max(max_items, 0)
    ]


def _next_task(*, spec: AgentWorkQueueSpec, current_task: dict[str, object], now: str) -> dict[str, object] | None:
    current_stage = str(current_task.get("stage") or "")
    stages = list(spec.stages)
    for index, stage in enumerate(stages):
        if stage.stage == current_stage:
            if index + 1 >= len(stages):
                return None
            next_stage = stages[index + 1]
            return build_agent_work_task(
                chain_id=spec.chain_id,
                stage=next_stage.stage,
                job_name=next_stage.job_name,
                payload=next_stage.payload,
                now=now,
                dependency_task_id=str(current_task["task_id"]),
                priority=next_stage.priority,
                max_attempts=next_stage.max_attempts,
            )
    return None


def _failed_task_update(*, task: dict[str, object], exc: Exception, now: str) -> tuple[dict[str, object], bool]:
    attempt_count = _int(task.get("attempt_count"), default=0) + 1
    max_attempts = max(_int(task.get("max_attempts"), default=1), 1)
    blocked = is_blocking_agent_work_error(exc)
    status = "blocked" if blocked else "failed" if attempt_count >= max_attempts else "retry"
    return (
        {
            **task,
            "status": status,
            "attempt_count": attempt_count,
            "locked_at": "",
            "locked_by": "",
            "last_error": f"{type(exc).__name__}: {exc}"[:1000],
            "updated_at": now,
            "completed_at": now if status in {"blocked", "failed"} else "",
        },
        blocked,
    )


def _record_agent_run(
    *,
    structured_store: Any,
    result: AgentWorkQueueResult,
    started_at: str,
    finished_at: str,
) -> None:
    status = "success" if result.failed_count == 0 and result.blocked_count == 0 else "partial_success"
    error_message = ""
    if result.blocked_count:
        error_message = "agent_work_queue has blocked work items"
    elif result.failed_count:
        error_message = "agent_work_queue has failed work items"
    structured_store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": result.run_id,
                "job_name": "agent-work-queue",
                "status": status,
                "started_at": started_at,
                "finished_at": finished_at,
                "input_count": result.processed_count,
                "output_count": result.done_count,
                "error_message": error_message,
            }
        ],
        key_fields=("run_id",),
    )


def _task_exists(*, structured_store: Any, task_id: str) -> bool:
    return any(str(row.get("task_id") or "") == task_id for row in _all_tasks(structured_store=structured_store))


def _all_tasks(*, structured_store: Any) -> list[dict[str, object]]:
    return list(structured_store.query_rows(sql="SELECT * FROM agent_work_queue", parameters={}))


def _int(value: object, *, default: int) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _short_digest(*parts: str) -> str:
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:12]


def as_result_dict(result: AgentWorkQueueResult) -> dict[str, object]:
    return asdict(result)
