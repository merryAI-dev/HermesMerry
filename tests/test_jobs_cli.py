import json

from merry_runtime.adapters.fakes import FakeNotifier, FakeObjectStore, FakeReviewQueue, FakeStructuredStore
from merry_runtime.job_runner import RuntimeAdapters
from merry_runtime.jobs import main
from merry_runtime.runtime_config import RuntimeConfig
from merry_runtime.wiki_store import SQLiteWikiStore


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
