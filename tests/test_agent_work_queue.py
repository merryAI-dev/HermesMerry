from __future__ import annotations

import json
from pathlib import Path

from merry_runtime.adapters.fakes import FakeStructuredStore
from merry_runtime.pipelines.agent_work_queue import load_agent_work_queue_spec, run_agent_work_queue


def _write_spec(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "chain_id": "test_discovery_chain",
                "description": "Test chain",
                "stages": [
                    {"stage": "crawl", "job_name": "crawl-sources"},
                    {"stage": "sminfo", "job_name": "enrich-sminfo"},
                    {"stage": "backup", "job_name": "backup-export"},
                ],
                "risks": [
                    {
                        "id": "missing_sminfo_credentials",
                        "stage": "sminfo",
                        "severity": "high",
                        "mitigation": "Block the queue item instead of retrying without credentials.",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_agent_work_queue_chains_jobs_from_json_spec(tmp_path) -> None:
    store = FakeStructuredStore()
    spec = load_agent_work_queue_spec(_write_spec(tmp_path / "chain.json"))
    calls: list[str] = []

    def run_job_fn(job_name: str, *, runtime: object, config: object) -> dict[str, object]:
        calls.append(job_name)
        return {"job_name": job_name, "status": "success"}

    result = run_agent_work_queue(
        runtime=object(),
        config=object(),
        structured_store=store,
        spec=spec,
        max_tasks=3,
        agent_id="agent-test",
        run_job_fn=run_job_fn,
        now_fn=lambda: "2026-05-26T12:00:00+09:00",
    )

    assert calls == ["crawl-sources", "enrich-sminfo", "backup-export"]
    assert result.processed_count == 3
    assert result.done_count == 3
    assert result.blocked_count == 0
    assert [row["stage"] for row in store.tables["agent_work_queue"]] == ["crawl", "sminfo", "backup"]
    assert {row["status"] for row in store.tables["agent_work_queue"]} == {"done"}
    assert store.tables["agent_work_queue"][1]["dependency_task_id"] == store.tables["agent_work_queue"][0]["task_id"]


def test_agent_work_queue_blocks_missing_credentials_without_spinning(tmp_path) -> None:
    store = FakeStructuredStore()
    spec = load_agent_work_queue_spec(_write_spec(tmp_path / "chain.json"))
    calls: list[str] = []

    def run_job_fn(job_name: str, *, runtime: object, config: object) -> dict[str, object]:
        calls.append(job_name)
        if job_name == "enrich-sminfo":
            raise RuntimeError("enrich-sminfo requires a configured SMINFO client")
        return {"job_name": job_name, "status": "success"}

    result = run_agent_work_queue(
        runtime=object(),
        config=object(),
        structured_store=store,
        spec=spec,
        max_tasks=3,
        agent_id="agent-test",
        run_job_fn=run_job_fn,
        now_fn=lambda: "2026-05-26T12:00:00+09:00",
    )

    assert calls == ["crawl-sources", "enrich-sminfo"]
    assert result.processed_count == 2
    assert result.done_count == 1
    assert result.blocked_count == 1
    assert {row["stage"]: row["status"] for row in store.tables["agent_work_queue"]} == {
        "crawl": "done",
        "sminfo": "blocked",
    }
    blocked = store.tables["agent_work_queue"][1]
    assert "requires a configured SMINFO client" in blocked["last_error"]
    assert not any(row["stage"] == "backup" for row in store.tables["agent_work_queue"])
