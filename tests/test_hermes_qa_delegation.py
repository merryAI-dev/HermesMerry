from __future__ import annotations

from pathlib import Path

from merry_runtime.github_qa_context import RepoEvidence
from merry_runtime.hermes_qa_delegation import build_hermes_qa_prompt, run_hermes_qa_handoff
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
