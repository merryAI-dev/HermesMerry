from __future__ import annotations

from pathlib import Path

from merry_runtime.github_qa_context import RepoEvidence
from merry_runtime.hermes_qa_delegation import (
    build_hermes_qa_execution_prompt,
    build_hermes_qa_prompt,
    run_hermes_qa_handoff,
)
from merry_runtime.slack_qa_triage import QATriageEvent


def test_build_hermes_prompt_assigns_qa_work_to_hermes_agent(tmp_path: Path) -> None:
    repo = tmp_path / "startup-diagnostic-platform"
    event = QATriageEvent(
        summary="기업에서 회원가입 요청까지 하신 기록은 있는데 플랫폼 내에서는 확인이 불가능합니다.",
        requester_slack_user_id="U09AT2VU9PU",
        channel="C123",
        message_ts="177.1",
    )
    evidence = [
        RepoEvidence(
            repo_path=repo,
            path=Path("src/firebase/profile.ts"),
            line_number=267,
            snippet='await setDoc(doc(db, "signupRequests", uid), signupRequestData, { merge: true })',
            term="signupRequests",
        )
    ]

    prompt = build_hermes_qa_prompt(event, evidence, repo_paths=[repo])

    assert "AXR팀 QA 대응 에이전트" in prompt
    assert "startup-diagnostic-platform" in prompt
    assert "회원가입 요청" in prompt
    assert "src/firebase/profile.ts:267" in prompt
    assert "Slack 스레드 답글 초안만" in prompt
    assert "단정하지 마세요" in prompt


def test_run_hermes_handoff_invokes_hermes_cli_with_query_and_image(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    image = tmp_path / "qa.png"
    image.write_bytes(b"fake")

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        calls.append({"command": command, "kwargs": kwargs})

        class Result:
            returncode = 0
            stdout = "Hermes 초안입니다.\n"
            stderr = ""

        return Result()

    output = run_hermes_qa_handoff(
        "프롬프트",
        repo_cwd=tmp_path,
        image_paths=[image],
        runner=fake_run,
        timeout_seconds=30,
    )

    assert output == "Hermes 초안입니다."
    command = calls[0]["command"]
    assert isinstance(command, list)
    assert "--query" in command
    assert "--image" in command
    assert str(image) in command
    assert calls[0]["kwargs"]["cwd"] == tmp_path


def test_build_execution_prompt_makes_hermes_own_github_and_slack_actions(tmp_path: Path) -> None:
    repo = tmp_path / "startup-diagnostic-platform"
    event = QATriageEvent(
        summary="기업 회원가입 요청이 플랫폼에서 보이지 않습니다.",
        requester_slack_user_id="U09AT2VU9PU",
        channel="C0AH3LQ00AD",
        message_ts="177.1",
        thread_ts="177.1",
    )

    prompt = build_hermes_qa_execution_prompt(
        event,
        [],
        repo_paths=[repo],
        github_repo="merryAI-dev/startup-diagnostic-platform",
        reviewer_slack_user_id="U099F3KA1CL",
        slack_channel="C0AH3LQ00AD",
        thread_ts="177.1",
    )

    assert "초안 생성이 아니라 실제 실행 작업" in prompt
    assert "gh issue create --repo merryAI-dev/startup-diagnostic-platform" in prompt
    assert "slack_sdk.WebClient" in prompt
    assert "channel=C0AH3LQ00AD" in prompt
    assert "thread_ts=177.1" in prompt
    assert "두 번째 댓글: 생성한 GitHub issue 제목과 본문" in prompt
    assert "[QA 1차 진단] <GitHub issue 제목>" in prompt
    assert "이 메시지는 스레드 댓글이 아닙니다" in prompt


def test_execution_prompt_enforces_firestore_read_only_tenant_ledger_rules(tmp_path: Path) -> None:
    repo = tmp_path / "innerplatform"
    event = QATriageEvent(
        summary="PM 포털에서 프로젝트가 보이지 않습니다.",
        requester_slack_user_id="U123",
        channel="C123",
        message_ts="177.1",
        thread_ts="177.1",
    )

    prompt = build_hermes_qa_execution_prompt(
        event,
        [],
        repo_paths=[repo],
        github_repo="merryAI-dev/InnerPlatform",
        reviewer_slack_user_id="U099F3KA1CL",
        slack_channel="C123",
        thread_ts="177.1",
    )

    assert "Firestore read-only 운영 원장 원칙" in prompt
    assert "https://github.com/merryAI-dev/InnerPlatform" in prompt
    assert "/Users/boram/InnerPlatform" in prompt
    assert "https://inner-platform.vercel.app/" in prompt
    assert "https://submit-mysc.com" in prompt
    assert "/Users/boram/InnerPlatform/firebase/firestore.rules" in prompt
    assert "/Users/boram/InnerPlatform/src/app/lib/firebase.ts" in prompt
    assert "현재 운영 tenant는 보통 `mysc`" in prompt
    assert "scripts/firestore_readonly_audit.py" in prompt
    assert "HERMES_FIRESTORE_IMPERSONATE_SERVICE_ACCOUNT" in prompt
    assert "orgs/{tenantId}/..." in prompt
    assert "orgs/{orgId}/members/{uid}" in prompt
    assert "orgs/{orgId}/projects/{projectId}" in prompt
    assert "project_requests" in prompt
    assert "cashflow_weeks" in prompt
    assert "cashflowWeeks" in prompt
    assert "get/list/query만 허용" in prompt
    assert "create/set/update/delete/batch/transaction은 금지" in prompt
    assert "Hermes가 Firestore에 직접 쓰거나 지우면 안 됩니다" in prompt
