from __future__ import annotations

import json

from merry_runtime.adapters.fakes import FakeNotifier, FakeObjectStore, FakeReviewQueue, FakeStructuredStore
from merry_runtime.agent_loop import run_agent_loop
from merry_runtime.job_runner import RuntimeAdapters
from merry_runtime.jobs import main
from merry_runtime.runtime_config import RuntimeConfig
from merry_runtime.wiki_store import SQLiteWikiStore


class FakeRuntime:
    pass


def test_agent_loop_runs_configured_jobs_in_order() -> None:
    calls: list[str] = []

    def run_job_fn(job_name, *, runtime, config, sources_json="", ac_id=""):
        calls.append(job_name)
        return {"job_name": job_name, "status": "success"}

    result = run_agent_loop(
        runtime=FakeRuntime(),
        config=object(),
        jobs=("resolve-entities", "score-candidates", "calibrate-scores"),
        interval_seconds=0,
        max_cycles=1,
        run_job_fn=run_job_fn,
        sleep_fn=lambda seconds: None,
    )

    assert calls == ["resolve-entities", "score-candidates", "calibrate-scores"]
    assert result.cycle_count == 1
    assert result.failure_count == 0


def test_agent_loop_records_failures_and_continues_to_next_job() -> None:
    calls: list[str] = []

    def run_job_fn(job_name, *, runtime, config, sources_json="", ac_id=""):
        calls.append(job_name)
        if job_name == "score-candidates":
            raise RuntimeError("score failed")
        return {"job_name": job_name, "status": "success"}

    result = run_agent_loop(
        runtime=FakeRuntime(),
        config=object(),
        jobs=("resolve-entities", "score-candidates", "calibrate-scores"),
        interval_seconds=0,
        max_cycles=1,
        run_job_fn=run_job_fn,
        sleep_fn=lambda seconds: None,
    )

    assert calls == ["resolve-entities", "score-candidates", "calibrate-scores"]
    assert result.failure_count == 1
    assert result.results[1].status == "failed"
    assert "RuntimeError: score failed" in result.results[1].error_message


def test_agent_loop_persists_failed_job_run_for_backup_visibility() -> None:
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
    )

    def run_job_fn(job_name, *, runtime, config, sources_json="", ac_id=""):
        if job_name == "crawl-sources":
            raise RuntimeError("crawl failed")
        return {"job_name": job_name, "status": "success"}

    result = run_agent_loop(
        runtime=runtime,
        config=object(),
        jobs=("crawl-sources", "backup-export"),
        interval_seconds=0,
        max_cycles=1,
        run_job_fn=run_job_fn,
        sleep_fn=lambda seconds: None,
    )

    failed_rows = [
        row
        for row in runtime.structured_store.tables["agent_runs"]
        if row["job_name"] == "crawl-sources" and row["status"] == "failed"
    ]
    assert result.failure_count == 1
    assert len(failed_rows) == 1
    assert "RuntimeError: crawl failed" in failed_rows[0]["error_message"]
    assert failed_rows[0]["started_at"].endswith("+09:00")
    assert failed_rows[0]["finished_at"].endswith("+09:00")


def test_runtime_config_reads_agent_loop_environment(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LOOP_JOBS", "resolve-entities,score-candidates")
    monkeypatch.setenv("AGENT_LOOP_INTERVAL_SECONDS", "90")
    monkeypatch.setenv("AGENT_LOOP_MAX_CYCLES", "2")
    monkeypatch.setenv("HERMES_ALLOW_UNBOUNDED_LOOP", "true")

    config = RuntimeConfig.from_env()

    assert config.agent_loop_jobs == ("resolve-entities", "score-candidates")
    assert config.agent_loop_interval_seconds == 90
    assert config.agent_loop_max_cycles == 2
    assert config.allow_unbounded_loop is True


def test_runtime_config_defaults_runpod_wiki_root(monkeypatch) -> None:
    monkeypatch.setenv("WIKI_ROOT", "/workspace/hermes/wiki")

    config = RuntimeConfig.from_env()

    assert str(config.wiki_root) == "/workspace/hermes/wiki"


def test_runtime_config_defaults_to_every_one_hour_agent_work_queue_loop(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LOOP_JOBS", raising=False)
    monkeypatch.delenv("AGENT_LOOP_INTERVAL_SECONDS", raising=False)

    config = RuntimeConfig.from_env()

    assert config.agent_loop_jobs == ("agent-work-queue",)
    assert config.agent_loop_interval_seconds == 3600


def test_jobs_cli_loop_runs_one_cycle(monkeypatch, tmp_path, capsys) -> None:
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="raw-bucket",
        review_sheet_id="sheet-1",
        default_ac_id="ac_climate",
        wiki_root=tmp_path,
        agent_loop_jobs=("score-candidates",),
        agent_loop_interval_seconds=0,
        agent_loop_max_cycles=1,
    )
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore.seed_climate_candidate(),
        review_queue=FakeReviewQueue(),
        notifier=FakeNotifier(),
        wiki_store=SQLiteWikiStore(root=tmp_path),
    )

    monkeypatch.setattr("merry_runtime.jobs.RuntimeConfig.from_env", lambda: config)
    monkeypatch.setattr("merry_runtime.jobs.build_runtime", lambda config: runtime)
    monkeypatch.setattr("merry_runtime.jobs.time.sleep", lambda seconds: None)

    exit_code = main(["loop", "--max-cycles", "1", "--interval-seconds", "0"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["cycle_count"] == 1
    assert output["failure_count"] == 0
    assert output["results"][0]["job_name"] == "score-candidates"


def test_jobs_cli_loop_rejects_append_mode_for_unbounded_loop(monkeypatch, capsys) -> None:
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="raw-bucket",
        structured_store_backend="bigquery",
        bigquery_write_mode="append",
        agent_loop_jobs=("resolve-entities",),
        agent_loop_max_cycles=0,
    )

    monkeypatch.setattr("merry_runtime.jobs.RuntimeConfig.from_env", lambda: config)
    monkeypatch.setattr(
        "merry_runtime.jobs.build_runtime",
        lambda config: (_ for _ in ()).throw(AssertionError("build_runtime should not be called")),
    )

    exit_code = main(["loop"])

    stderr = capsys.readouterr().err
    assert exit_code == 2
    assert "BIGQUERY_WRITE_MODE=append" in stderr
    assert "AGENT_LOOP_MAX_CYCLES=1" in stderr


def test_jobs_cli_loop_rejects_unbounded_loop_without_explicit_cost_ack(monkeypatch, capsys) -> None:
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        structured_store_backend="sqlite",
        mother_db_path="/tmp/hermes-mother.db",
        agent_loop_jobs=("backup-export",),
        agent_loop_max_cycles=0,
        allow_unbounded_loop=False,
    )

    monkeypatch.setattr("merry_runtime.jobs.RuntimeConfig.from_env", lambda: config)
    monkeypatch.setattr(
        "merry_runtime.jobs.build_runtime",
        lambda config: (_ for _ in ()).throw(AssertionError("build_runtime should not be called")),
    )

    exit_code = main(["loop"])

    stderr = capsys.readouterr().err
    assert exit_code == 2
    assert "AGENT_LOOP_MAX_CYCLES=0" in stderr
    assert "HERMES_ALLOW_UNBOUNDED_LOOP=1" in stderr


def test_runtime_config_accepts_unbounded_loop_with_explicit_cost_ack(tmp_path) -> None:
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        structured_store_backend="sqlite",
        mother_db_path=tmp_path / "mother.db",
        agent_loop_max_cycles=0,
        allow_unbounded_loop=True,
    )

    config.validate_for_loop(max_cycles=config.agent_loop_max_cycles)
