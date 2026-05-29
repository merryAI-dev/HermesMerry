from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_realtime_agent_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "slack_qa_realtime_agent.py"
    spec = importlib.util.spec_from_file_location("slack_qa_realtime_agent", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_post_plan_sends_diagnosis_to_thread_and_issue_notice_to_channel() -> None:
    module = _load_realtime_agent_module()
    calls: list[dict[str, str]] = []

    class FakeClient:
        def chat_postMessage(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append({key: str(value) for key, value in kwargs.items()})

    module._post_plan(
        FakeClient(),
        channel="C123",
        plan={
            "thread_ts": "177.1",
            "thread_draft": "Hermes 1차 진단입니다.",
            "channel_notice": "[QA 1차 진단] 기업 회원가입 요청 확인 불가\n깃허브 이슈로 처리해두었어요 :-) <@U099F3KA1CL> 검토해주세요 보람!",
        },
    )

    assert calls == [
        {"channel": "C123", "thread_ts": "177.1", "text": "Hermes 1차 진단입니다."},
        {
            "channel": "C123",
            "text": "[QA 1차 진단] 기업 회원가입 요청 확인 불가\n깃허브 이슈로 처리해두었어요 :-) <@U099F3KA1CL> 검토해주세요 보람!",
        },
    ]


def test_post_plan_skips_when_hermes_loop_already_handled_actions() -> None:
    module = _load_realtime_agent_module()
    calls: list[dict[str, str]] = []

    class FakeClient:
        def chat_postMessage(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append({key: str(value) for key, value in kwargs.items()})

    module._post_plan(
        FakeClient(),
        channel="C123",
        plan={
            "handled_by_hermes": True,
            "thread_ts": "177.1",
            "thread_draft": "이미 Hermes가 보냄",
            "channel_notice": "이미 Hermes가 보냄",
        },
    )

    assert calls == []


def test_default_github_repo_targets_innerplatform_for_firestore_qa() -> None:
    module = _load_realtime_agent_module()

    assert module.DEFAULT_GITHUB_REPO == "merryAI-dev/InnerPlatform"
