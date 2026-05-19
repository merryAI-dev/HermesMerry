from datetime import UTC, datetime, timedelta

from merry_runtime.ingestion.sminfo import SminfoProfile
from merry_runtime.ingestion.sminfo_queue import (
    build_sminfo_task,
    is_terminal_queue_status,
    next_retry_at,
    queue_status_for_profile,
    sminfo_task_id,
)


def test_sminfo_task_id_is_stable_and_uses_candidate_hints() -> None:
    first = sminfo_task_id(
        company="(주)에이아이오",
        normalized_name="에이아이오",
        representative="권진형",
        homepage="https://the-aio.com/",
        source_channel="thevc_investment_ma",
    )
    second = sminfo_task_id(
        company="에이아이오",
        normalized_name="에이아이오",
        representative="권진형",
        homepage="https://the-aio.com",
        source_channel="thevc_investment_ma",
    )

    assert first == second
    assert first.startswith("sminfo_task_")


def test_sminfo_task_id_normalizes_equivalent_homepage_forms() -> None:
    expected = sminfo_task_id(
        company="에이아이오",
        normalized_name="에이아이오",
        homepage="https://the-aio.com/",
        source_channel="thevc_investment_ma",
    )

    for homepage in (
        "http://the-aio.com",
        "https://www.the-aio.com/",
        "the-aio.com/",
        "https://the-aio.com/?utm_source=thevc",
    ):
        assert (
            sminfo_task_id(
                company="에이아이오",
                normalized_name="에이아이오",
                homepage=homepage,
                source_channel="thevc_investment_ma",
            )
            == expected
        )


def test_build_sminfo_task_sets_pending_due_work_defaults() -> None:
    now = datetime(2026, 5, 19, 3, 0, tzinfo=UTC).isoformat()

    task = build_sminfo_task(
        {
            "company": "(주)에이아이오",
            "normalized_name": "에이아이오",
            "representative": "권진형",
            "homepage": "https://the-aio.com/",
            "url": "https://thevc.kr/aio",
        },
        source_channel="thevc_investment_ma",
        now=now,
    )

    assert task["task_id"].startswith("sminfo_task_")
    assert task["company"] == "에이아이오"
    assert task["normalized_name"] == "에이아이오"
    assert task["representative"] == "권진형"
    assert task["homepage"] == "https://the-aio.com/"
    assert task["source_url"] == "https://thevc.kr/aio"
    assert task["source_channel"] == "thevc_investment_ma"
    assert task["status"] == "pending"
    assert task["priority"] == 100
    assert task["attempt_count"] == 0
    assert task["max_attempts"] == 5
    assert task["next_run_at"] == now
    assert task["created_at"] == now
    assert task["updated_at"] == now


def test_queue_terminal_statuses_are_classified() -> None:
    assert is_terminal_queue_status("matched")
    assert is_terminal_queue_status("matched_no_financials")
    assert is_terminal_queue_status("not_found")
    assert is_terminal_queue_status("ambiguous")
    assert not is_terminal_queue_status("pending")
    assert not is_terminal_queue_status("retry")
    assert not is_terminal_queue_status("failed")


def test_next_retry_at_uses_exponential_backoff() -> None:
    now = datetime(2026, 5, 19, 3, 0, tzinfo=UTC)

    assert next_retry_at(attempt_count=1, now=now, base_seconds=60) == (now + timedelta(seconds=60)).isoformat()
    assert next_retry_at(attempt_count=3, now=now, base_seconds=60) == (now + timedelta(seconds=240)).isoformat()


def test_queue_status_for_profile_separates_matched_without_financials() -> None:
    assert (
        queue_status_for_profile(
            SminfoProfile(
                requested_company="오르빗코리아",
                match_status="matched",
                matched_company="오르빗코리아",
            )
        )
        == "matched_no_financials"
    )
    assert (
        queue_status_for_profile(
            SminfoProfile(
                requested_company="바이트랩",
                match_status="matched",
                matched_company="(주)바이트랩",
                revenue_krw_thousand="46817005",
            )
        )
        == "matched"
    )
    assert queue_status_for_profile(SminfoProfile(requested_company="없는회사", match_status="not_found")) == "not_found"
