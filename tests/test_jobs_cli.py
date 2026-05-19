import json

from merry_runtime.adapters.fakes import FakeNotifier, FakeObjectStore, FakeReviewQueue, FakeStructuredStore
from merry_runtime.job_runner import RuntimeAdapters
from merry_runtime.jobs import main
from merry_runtime.runtime_config import RuntimeConfig
from merry_runtime.wiki_store import SQLiteWikiStore


class FailingAgentRunStore(FakeStructuredStore):
    def upsert_rows(self, *, table: str, rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> int:
        if table == "agent_runs":
            raise RuntimeError("secondary persistence failed with private source payload")
        return super().upsert_rows(table=table, rows=rows, key_fields=key_fields)


def test_jobs_cli_run_invokes_runtime_runner(monkeypatch, tmp_path, capsys) -> None:
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="raw-bucket",
        review_sheet_id="sheet-1",
        slack_channel="C123",
        gmail_label_id="Label_123",
        default_ac_id="ac_climate",
        wiki_root=tmp_path,
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

    exit_code = main(["run", "score-candidates", "--ac-id", "ac_climate"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["job_name"] == "score-candidates"
    assert output["card_count"] == 1


def test_jobs_cli_accepts_sources_json(monkeypatch, tmp_path, capsys) -> None:
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="raw-bucket",
        wiki_root=tmp_path,
    )
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
        wiki_store=SQLiteWikiStore(root=tmp_path),
    )
    sources_json = json.dumps([{"channel": "external_referral", "payload": {"company": "Merry AI", "region": "Seoul"}}])

    monkeypatch.setattr("merry_runtime.jobs.RuntimeConfig.from_env", lambda: config)
    monkeypatch.setattr("merry_runtime.jobs.build_runtime", lambda config: runtime)

    exit_code = main(["run", "ingest-sources", "--sources-json", sources_json])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["job_name"] == "ingest-sources"
    assert output["raw_source_count"] == 1


def test_jobs_cli_accepts_sources_file_for_crawl_sources(monkeypatch, tmp_path, capsys) -> None:
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        object_store_backend="local",
        raw_root=tmp_path / "raw",
        wiki_root=tmp_path / "wiki",
    )
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
        wiki_store=SQLiteWikiStore(root=tmp_path / "wiki"),
    )
    sources_file = tmp_path / "crawl-targets.json"
    sources_file.write_text(json.dumps([{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}]), encoding="utf-8")

    monkeypatch.setattr("merry_runtime.jobs.RuntimeConfig.from_env", lambda: config)
    monkeypatch.setattr("merry_runtime.jobs.build_runtime", lambda config: runtime)
    monkeypatch.setattr(
        "merry_runtime.jobs.run_job",
        lambda job_name, **kwargs: {"job_name": job_name, "target_count": 1, "crawled_source_count": 5},
    )

    exit_code = main(["run", "crawl-sources", "--sources-file", str(sources_file)])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["job_name"] == "crawl-sources"
    assert output["crawled_source_count"] == 5


def test_jobs_cli_accepts_sources_file_for_ingest_ac_profiles(monkeypatch, tmp_path, capsys) -> None:
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="",
        wiki_root=tmp_path,
    )
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
        wiki_store=SQLiteWikiStore(root=tmp_path),
    )
    sources_file = tmp_path / "ac-reports.json"
    sources_file.write_text(
        json.dumps(
            [
                {
                    "payload": """
                        AC ID: ac_climate_local
                        AC Name: Climate Local Impact AC
                        Fund Purpose: climate adaptation fund
                        Hypothesis Tags: climate
                        Impact Priorities: carbon
                    """,
                }
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("merry_runtime.jobs.RuntimeConfig.from_env", lambda: config)
    monkeypatch.setattr("merry_runtime.jobs.build_runtime", lambda config: runtime)

    exit_code = main(["run", "ingest-ac-profiles", "--sources-file", str(sources_file)])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["job_name"] == "ingest-ac-profiles"
    assert output["profile_count"] == 1


def test_jobs_cli_runs_calibrate_scores(monkeypatch, tmp_path, capsys) -> None:
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="raw-bucket",
        review_sheet_id="sheet-1",
        default_ac_id="ac_climate",
        wiki_root=tmp_path,
    )
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
        wiki_store=SQLiteWikiStore(root=tmp_path),
    )

    monkeypatch.setattr("merry_runtime.jobs.RuntimeConfig.from_env", lambda: config)
    monkeypatch.setattr("merry_runtime.jobs.build_runtime", lambda config: runtime)

    exit_code = main(["run", "calibrate-scores", "--ac-id", "ac_climate"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["job_name"] == "calibrate-scores"
    assert output["sample_count"] == 0


def test_jobs_cli_runs_backup_export(monkeypatch, tmp_path, capsys) -> None:
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        wiki_root=tmp_path / "wiki",
        backup_root=tmp_path / "backups",
        mother_db_path=tmp_path / "mother.db",
        structured_store_backend="sqlite",
    )
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
        wiki_store=SQLiteWikiStore(root=tmp_path / "wiki"),
    )

    monkeypatch.setattr("merry_runtime.jobs.RuntimeConfig.from_env", lambda: config)
    monkeypatch.setattr("merry_runtime.jobs.build_runtime", lambda config: runtime)
    monkeypatch.setattr(
        "merry_runtime.jobs.run_job",
        lambda job_name, **kwargs: {"job_name": job_name, "manifest_path": "backup/manifest.json"},
    )

    exit_code = main(["run", "backup-export"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["job_name"] == "backup-export"
    assert output["manifest_path"] == "backup/manifest.json"


def test_jobs_cli_runs_enrich_sminfo(monkeypatch, tmp_path, capsys) -> None:
    config = RuntimeConfig(
        project_id="",
        dataset_id="",
        raw_bucket="",
        review_sheet_id="sheet-1",
        wiki_root=tmp_path / "wiki",
        mother_db_path=tmp_path / "mother.db",
        structured_store_backend="sqlite",
        sminfo_user_id="user",
        sminfo_password="password",
    )
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FakeStructuredStore(),
        review_queue=FakeReviewQueue(),
        wiki_store=SQLiteWikiStore(root=tmp_path / "wiki"),
    )

    monkeypatch.setattr("merry_runtime.jobs.RuntimeConfig.from_env", lambda: config)
    monkeypatch.setattr("merry_runtime.jobs.build_runtime", lambda config: runtime)
    monkeypatch.setattr(
        "merry_runtime.jobs.run_job",
        lambda job_name, **kwargs: {"job_name": job_name, "processed_count": 1, "matched_count": 1},
    )

    exit_code = main(["run", "enrich-sminfo"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["job_name"] == "enrich-sminfo"
    assert output["matched_count"] == 1


def test_jobs_cli_persists_unexpected_job_failure_after_runtime_creation(monkeypatch, tmp_path, capsys) -> None:
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="raw-bucket",
        review_sheet_id="sheet-1",
        slack_channel="C123",
        gmail_label_id="Label_123",
        default_ac_id="ac_climate",
        wiki_root=tmp_path,
    )
    store = FakeStructuredStore.seed_climate_candidate()
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=store,
        review_queue=FakeReviewQueue(),
        notifier=FakeNotifier(),
        wiki_store=SQLiteWikiStore(root=tmp_path),
    )

    def fail_job(*args, **kwargs):
        raise RuntimeError("adapter exploded " + "x" * 1200)

    monkeypatch.setattr("merry_runtime.jobs.RuntimeConfig.from_env", lambda: config)
    monkeypatch.setattr("merry_runtime.jobs.build_runtime", lambda config: runtime)
    monkeypatch.setattr("merry_runtime.jobs.run_job", fail_job)

    exit_code = main(["run", "score-candidates", "--ac-id", "ac_climate"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Job failed:" in captured.err
    [failure_row] = store.tables["agent_runs"]
    assert failure_row["job_name"] == "score-candidates"
    assert failure_row["status"] == "failed"
    assert failure_row["input_count"] == 0
    assert failure_row["output_count"] == 0
    assert failure_row["started_at"]
    assert failure_row["finished_at"]
    assert failure_row["error_message"].startswith("RuntimeError: adapter exploded")
    assert len(failure_row["error_message"]) <= 1000


def test_jobs_cli_preserves_original_failure_when_failure_record_write_fails(monkeypatch, tmp_path, capsys) -> None:
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="raw-bucket",
        review_sheet_id="sheet-1",
        slack_channel="C123",
        gmail_label_id="Label_123",
        default_ac_id="ac_climate",
        wiki_root=tmp_path,
    )
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=FailingAgentRunStore(),
        review_queue=FakeReviewQueue(),
        notifier=FakeNotifier(),
        wiki_store=SQLiteWikiStore(root=tmp_path),
    )

    def fail_job(*args, **kwargs):
        raise RuntimeError("primary adapter exploded")

    monkeypatch.setattr("merry_runtime.jobs.RuntimeConfig.from_env", lambda: config)
    monkeypatch.setattr("merry_runtime.jobs.build_runtime", lambda config: runtime)
    monkeypatch.setattr("merry_runtime.jobs.run_job", fail_job)

    exit_code = main(["run", "score-candidates", "--ac-id", "ac_climate"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Job failed: RuntimeError: primary adapter exploded" in captured.err
    assert "secondary persistence failed" not in captured.err


def test_jobs_cli_invalid_sources_json_returns_job_error_without_failure_row(monkeypatch, tmp_path, capsys) -> None:
    config = RuntimeConfig(
        project_id="project-1",
        dataset_id="merry",
        raw_bucket="raw-bucket",
        wiki_root=tmp_path,
    )
    store = FakeStructuredStore()
    runtime = RuntimeAdapters(
        object_store=FakeObjectStore(bucket="raw-bucket"),
        structured_store=store,
        review_queue=FakeReviewQueue(),
        wiki_store=SQLiteWikiStore(root=tmp_path),
    )

    monkeypatch.setattr("merry_runtime.jobs.RuntimeConfig.from_env", lambda: config)
    monkeypatch.setattr("merry_runtime.jobs.build_runtime", lambda config: runtime)

    exit_code = main(["run", "ingest-sources", "--sources-json", "{not-json"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Job failed: sources JSON is invalid" in captured.err
    assert store.tables["agent_runs"] == []
