from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, Protocol

from merry_runtime.github_qa_context import RepoEvidence
from merry_runtime.slack_qa_triage import QATriageEvent


DEFAULT_HERMES_CLI = Path.home() / ".hermes" / "hermes-agent" / "cli.py"
DEFAULT_HERMES_PYTHON = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python"


class CompletedProcessLike(Protocol):
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[..., CompletedProcessLike]


def build_hermes_qa_prompt(
    event: QATriageEvent,
    evidence: list[RepoEvidence],
    *,
    repo_paths: Iterable[str | Path],
    extra_context: str = "",
) -> str:
    requester = f"<@{event.requester_slack_user_id}>" if event.requester_slack_user_id else event.requester_name or "미확인"
    repo_lines = "\n".join(f"- {Path(path).expanduser().resolve()}" for path in repo_paths)
    evidence_lines = _format_evidence(evidence)

    return f"""당신은 AXR팀 QA 대응 에이전트 Hermes입니다.

목표:
- Slack QA 항목을 보고, 관련 GitHub 코드/문서 근거를 확인해 원인 후보와 다음 액션을 제시합니다.
- 최종 출력은 Slack 스레드 답글 초안만 작성합니다.
- 증거가 부족하면 단정하지 마세요. 확인이 필요한 정보와 확인 경로를 먼저 말하세요.
- 사용자가 이해하기 쉽게 한국어로 답하세요.
- 코드 수정이나 배포가 필요하다고 판단되면, 지금 바로 고쳤다고 말하지 말고 "수정 필요 후보"로 표현하세요.

Slack QA:
- 요청자: {requester}
- 채널: {event.channel}
- 메시지 ts: {event.message_ts}
- 내용: {event.summary}

확인할 repo:
{repo_lines or "- repo 미지정"}

사전 검색 근거:
{evidence_lines}

추가 컨텍스트:
{extra_context.strip() or "- 없음"}

반드시 포함할 것:
1. 접수 확인
2. 현재 가장 가능성이 높은 원인 후보
3. 확인한 코드/데이터 경로 또는 추가로 확인해야 할 경로
4. 요청자에게 필요한 추가 정보가 있으면 짧게 요청

출력 형식:
Slack 스레드 답글 초안만 출력하세요. 제목이나 분석 로그는 붙이지 마세요.
"""


def run_hermes_qa_handoff(
    prompt: str,
    *,
    repo_cwd: str | Path,
    image_paths: Iterable[str | Path] = (),
    runner: Runner = subprocess.run,
    timeout_seconds: int = 240,
) -> str:
    hermes_python = Path(os.getenv("HERMES_PYTHON", str(DEFAULT_HERMES_PYTHON))).expanduser()
    hermes_cli = Path(os.getenv("HERMES_CLI", str(DEFAULT_HERMES_CLI))).expanduser()

    if not hermes_python.exists():
        hermes_python = Path(sys.executable)
    if not hermes_cli.exists():
        raise RuntimeError(f"Hermes CLI not found: {hermes_cli}")

    command = [
        str(hermes_python),
        str(hermes_cli),
        "--query",
        prompt,
        "--toolsets",
        os.getenv("SLACK_QA_HERMES_TOOLSETS", "terminal"),
        "--provider",
        os.getenv("SLACK_QA_HERMES_PROVIDER", "openai-codex"),
        "--model",
        os.getenv("SLACK_QA_HERMES_MODEL", "gpt-5.3-codex"),
        "--max_turns",
        os.getenv("SLACK_QA_HERMES_MAX_TURNS", "20"),
        "--quiet",
    ]

    for image_path in image_paths:
        resolved = Path(image_path).expanduser().resolve()
        if resolved.exists():
            command.extend(["--image", str(resolved)])

    result = runner(
        command,
        cwd=Path(repo_cwd).expanduser().resolve(),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(stderr or f"Hermes QA handoff failed with exit code {result.returncode}")

    output = _clean_hermes_output(result.stdout)
    if not output:
        raise RuntimeError("Hermes QA handoff returned empty output")
    return output


def _format_evidence(evidence: list[RepoEvidence]) -> str:
    if not evidence:
        return "- 사전 검색 근거 없음"
    lines = []
    for item in evidence[:10]:
        repo_name = Path(item.repo_path).name
        lines.append(f"- {repo_name}/{item.path}:{item.line_number} `{item.snippet[:160]}`")
    return "\n".join(lines)


def _clean_hermes_output(stdout: str) -> str:
    lines = [line.rstrip() for line in (stdout or "").splitlines()]
    noisy_prefixes = (
        "INFO:",
        "WARNING:",
        "Loaded environment",
    )
    cleaned = [line for line in lines if line.strip() and not line.startswith(noisy_prefixes)]
    return "\n".join(cleaned).strip()
