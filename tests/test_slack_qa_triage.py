from __future__ import annotations

from pathlib import Path

from merry_runtime.github_qa_context import collect_repo_evidence
from merry_runtime.slack_qa_triage import (
    QATriageEvent,
    build_github_search_terms,
    build_qa_draft,
    extract_qa_event,
    is_qa_message,
)


def test_detects_qa_registration_message_and_extracts_requester() -> None:
    text = "qa 등록 @솔_하송희 님이 제출하신 QA 가 접수되었습니다."

    event = extract_qa_event(text, channel="C123", message_ts="177.1")

    assert is_qa_message(text)
    assert event is not None
    assert event.requester_name == "솔_하송희"
    assert event.summary == "qa 등록 @솔_하송희 님이 제출하신 QA 가 접수되었습니다."
    assert event.channel == "C123"
    assert event.message_ts == "177.1"


def test_extracts_slack_mention_requester_without_polluting_search_terms() -> None:
    text = "<@U09AT2VU9PU> 님이 제출하신 QA 가 접수되었습니다."

    event = extract_qa_event(text)

    assert event is not None
    assert event.requester_slack_user_id == "U09AT2VU9PU"
    assert event.requester_name == ""
    assert build_qa_draft(event, [])  # smoke test for mention formatting
    assert "님이" not in build_github_search_terms(event)


def test_ignores_innerplatform_project_decision_messages() -> None:
    text = """[InnerPlatform] CIC 대표 검토 결과
프로젝트명: 2026 CTS2
결정: 수정 요청 후 반려
요청자: 김현지(데이지)
requestId: pr-1773906226325"""

    assert not is_qa_message(text)
    assert extract_qa_event(text) is None


def test_ignores_status_update_messages_that_describe_fixed_qa() -> None:
    text = """:memo: *포털 화면 튕김 현상 개선 공유*
:mag: *원인*
권한 없음으로 판단하는 리디렉션 로직이 다시 실행됐습니다.
:wrench: *해결 방법*
상태값 변화만으로 자동 이동하던 로직을 제거했습니다.
:sparkles: *기대효과*
작업 중 홈으로 튕기는 현상 감소"""

    assert not is_qa_message(text)
    assert extract_qa_event(text) is None


def test_collect_repo_evidence_searches_files_and_keeps_line_numbers(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source_dir = repo / "src"
    source_dir.mkdir(parents=True)
    (repo / ".git").mkdir()
    (source_dir / "router.ts").write_text(
        "export function guard() {\n"
        "  return redirect('/home')\n"
        "}\n",
        encoding="utf-8",
    )

    evidence = collect_repo_evidence(["redirect", "권한"], repo_paths=[repo], limit=3)

    assert len(evidence) == 1
    assert evidence[0].repo_path == repo
    assert evidence[0].path == Path("src/router.ts")
    assert evidence[0].line_number == 2
    assert "redirect('/home')" in evidence[0].snippet


def test_build_draft_mentions_evidence_without_overclaiming(tmp_path: Path) -> None:
    event = QATriageEvent(
        summary="작업 중 홈으로 튕기는 현상",
        requester_name="하송희",
        channel="C123",
        message_ts="177.1",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    evidence = collect_repo_evidence(["없는키워드"], repo_paths=[repo], limit=3)

    draft = build_qa_draft(event, evidence)

    assert "QA 원인 분석 초안" in draft
    assert "작업 중 홈으로 튕기는 현상" in draft
    assert "추정" in draft
    assert "단정" not in draft
