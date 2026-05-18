from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from merry_runtime.job_runner import run_job


@dataclass(frozen=True, slots=True)
class LoopJobResult:
    job_name: str
    status: str
    payload: dict[str, object] = field(default_factory=dict)
    error_message: str = ""


@dataclass(frozen=True, slots=True)
class LoopResult:
    cycle_count: int
    success_count: int
    failure_count: int
    results: tuple[LoopJobResult, ...]


def run_agent_loop(
    *,
    runtime: Any,
    config: Any,
    jobs: Iterable[str],
    interval_seconds: int,
    max_cycles: int,
    run_job_fn: Callable[..., dict[str, object]] = run_job,
    sleep_fn: Callable[[int], None],
) -> LoopResult:
    cycle_count = 0
    results: list[LoopJobResult] = []
    job_names = tuple(jobs)

    while max_cycles <= 0 or cycle_count < max_cycles:
        cycle_count += 1
        for job_name in job_names:
            try:
                payload = run_job_fn(job_name, runtime=runtime, config=config)
            except Exception as exc:
                _record_failed_job(runtime=runtime, job_name=job_name, exc=exc)
                results.append(
                    LoopJobResult(
                        job_name=job_name,
                        status="failed",
                        error_message=f"{type(exc).__name__}: {exc}"[:1000],
                    )
                )
                continue
            results.append(LoopJobResult(job_name=job_name, status="success", payload=payload))

        if max_cycles > 0 and cycle_count >= max_cycles:
            break
        sleep_fn(interval_seconds)

    success_count = sum(1 for result in results if result.status == "success")
    failure_count = sum(1 for result in results if result.status == "failed")
    return LoopResult(
        cycle_count=cycle_count,
        success_count=success_count,
        failure_count=failure_count,
        results=tuple(results),
    )


def _record_failed_job(*, runtime: Any, job_name: str, exc: Exception) -> None:
    structured_store = getattr(runtime, "structured_store", None)
    if structured_store is None:
        return
    now = datetime.now(UTC).isoformat()
    run_id = f"run_failed_{_safe_job_name(job_name)}_{_short_digest(now, type(exc).__name__, str(exc))}"
    try:
        structured_store.upsert_rows(
            table="agent_runs",
            rows=[
                {
                    "run_id": run_id,
                    "job_name": job_name,
                    "status": "failed",
                    "started_at": now,
                    "finished_at": now,
                    "input_count": 0,
                    "output_count": 0,
                    "error_message": f"{type(exc).__name__}: {exc}"[:1000],
                }
            ],
            key_fields=("run_id",),
        )
    except Exception:
        return


def _safe_job_name(job_name: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in job_name)


def _short_digest(*parts: str) -> str:
    payload = "\n".join(parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
