from __future__ import annotations

import sqlite3

from merry_runtime.jobs import main
from merry_runtime.loop_dashboard import render_loop_dashboard


def test_render_loop_dashboard_shows_job_lanes_failures_and_queue_counts(tmp_path) -> None:
    db_path = tmp_path / "mother.db"
    output_path = tmp_path / "loop-dashboard.html"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            create table agent_runs (
              run_id text,
              job_name text,
              status text,
              started_at text,
              finished_at text,
              input_count integer,
              output_count integer,
              error_message text
            )
            """
        )
        connection.executemany(
            "insert into agent_runs values (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "run_crawl_1",
                    "crawl-sources",
                    "success",
                    "2026-05-26T10:10:00+09:00",
                    "2026-05-26T10:11:00+09:00",
                    2,
                    8,
                    "",
                ),
                (
                    "run_score_1",
                    "score-candidates",
                    "failed",
                    "2026-05-26T10:11:10+09:00",
                    "2026-05-26T10:11:15+09:00",
                    8,
                    0,
                    "Unknown AC profile",
                ),
            ],
        )
        connection.execute(
            """
            create table sminfo_enrichment_queue (
              task_id text,
              status text
            )
            """
        )
        connection.executemany(
            "insert into sminfo_enrichment_queue values (?, ?)",
            [("task_1", "pending"), ("task_2", "done"), ("task_3", "pending")],
        )
        connection.execute(
            """
            create table agent_work_queue (
              task_id text,
              status text
            )
            """
        )
        connection.executemany(
            "insert into agent_work_queue values (?, ?)",
            [("task_1", "done"), ("task_2", "blocked")],
        )
        connection.commit()

    result_path = render_loop_dashboard(db_path=db_path, output_path=output_path)

    html = result_path.read_text(encoding="utf-8")
    assert "Hermes 루프 콘솔" in html
    assert "파이프라인 토폴로지" in html
    assert "AIOps 상태" in html
    assert "최근 실행" in html
    assert "최근 성공" in html
    assert "최근 실패" in html
    assert "장애" in html
    assert "2026-05-26T10:11:10+09:00" in html
    assert "/* AIOps 상태 색상" in html
    assert "/* 토폴로지 캔버스" in html
    assert "<svg" in html
    assert "marker-end" in html
    assert "수집기" in html
    assert "Mother DB" in html
    assert "리뷰 시트" in html
    assert "crawl-sources" in html
    assert "score-candidates" in html
    assert "node failed" in html
    assert "Unknown AC profile" in html
    assert "SMINFO 큐" in html
    assert "Agent Work 큐" in html
    assert "blocked" in html
    assert "pending" in html
    assert "2" in html


def test_jobs_cli_renders_loop_dashboard_from_configured_sqlite_path(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "mother.db"
    output_path = tmp_path / "dashboard.html"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            create table agent_runs (
              run_id text,
              job_name text,
              status text,
              started_at text,
              finished_at text,
              input_count integer,
              output_count integer,
              error_message text
            )
            """
        )
        connection.execute(
            "insert into agent_runs values (?, ?, ?, ?, ?, ?, ?, ?)",
            ("run_backup_1", "backup-export", "success", "2026-05-26T10:12:00+09:00", "", 0, 1, ""),
        )
        connection.commit()
    monkeypatch.setenv("MOTHER_DB_PATH", str(db_path))

    exit_code = main(["render-loop-dashboard", "--output", str(output_path)])

    assert exit_code == 0
    assert str(output_path) in capsys.readouterr().out
    assert "backup-export" in output_path.read_text(encoding="utf-8")
