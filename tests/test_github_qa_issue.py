from __future__ import annotations

from pathlib import Path

from merry_runtime.github_qa_context import RepoEvidence
from merry_runtime.github_qa_issue import build_qa_issue_body, build_qa_issue_title, build_slack_issue_reply, create_github_issue
from merry_runtime.slack_qa_triage import QATriageEvent


def test_build_issue_title_and_body_include_hermes_diagnosis() -> None:
    event = QATriageEvent(
        summary="기업에서 회원가입 요청까지 하신 기록은 있는데 플랫폼 내에서는 확인이 불가능합니다.",
        requester_slack_user_id="U09AT2VU9PU",
        channel="C123",
        message_ts="177.1",
    )
    evidence = [
        RepoEvidence(
            repo_path=Path("/repo/startup-diagnostic-platform"),
            path=Path("src/redesign/app/AppContent.tsx"),
            line_number=1712,
            snippet="const pendingProfileApprovals = useMemo<PendingProfileApproval[]>(() => {",
            term="signupRequests",
        )
    ]

    title = build_qa_issue_title(event)
    body = build_qa_issue_body(event, hermes_diagnosis="승인 후 signupRequests 삭제 가능성이 있습니다.", evidence=evidence)

    assert title.startswith("[QA 1차 진단]")
    assert "회원가입 요청" in title
    assert "Hermes 1차 진단" in body
    assert "승인 후 signupRequests 삭제 가능성" in body
    assert "src/redesign/app/AppContent.tsx:1712" in body
    assert "C123" in body


def test_create_github_issue_uses_gh_cli_and_returns_url() -> None:
    calls: list[dict[str, object]] = []

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        calls.append({"command": command, "kwargs": kwargs})

        class Result:
            returncode = 0
            stdout = "https://github.com/merryAI-dev/startup-diagnostic-platform/issues/123\n"
            stderr = ""

        return Result()

    url = create_github_issue(
        repo_full_name="merryAI-dev/startup-diagnostic-platform",
        title="[QA 1차 진단] 테스트",
        body="본문",
        assignees=["merryAI-dev"],
        labels=[],
        runner=fake_run,
    )

    assert url.endswith("/issues/123")
    command = calls[0]["command"]
    assert isinstance(command, list)
    assert command[:5] == ["gh", "issue", "create", "--repo", "merryAI-dev/startup-diagnostic-platform"]
    assert "--assignee" in command
    assert "merryAI-dev" in command


def test_slack_issue_reply_fixed_mentions_boram() -> None:
    reply = build_slack_issue_reply(
        issue_url="https://github.com/merryAI-dev/startup-diagnostic-platform/issues/123",
        reviewer_slack_user_id="U099F3KA1CL",
    )

    assert "깃허브 이슈로 처리해두었어요 :-)" in reply
    assert "<@U099F3KA1CL>" in reply
    assert "검토해주세요 보람!" in reply
    assert "https://github.com/merryAI-dev/startup-diagnostic-platform/issues/123" in reply
