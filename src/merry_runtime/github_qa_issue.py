from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable, Iterable, Protocol

from merry_runtime.github_qa_context import RepoEvidence
from merry_runtime.slack_qa_triage import QATriageEvent


class CompletedProcessLike(Protocol):
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[..., CompletedProcessLike]


def build_qa_issue_title(event: QATriageEvent) -> str:
    summary = _clean_summary_for_title(event.summary)
    if not summary:
        summary = "Slack QA 항목 확인 필요"
    return f"[QA 1차 진단] {_truncate(summary, 80)}"


def build_qa_issue_body(
    event: QATriageEvent,
    *,
    hermes_diagnosis: str,
    evidence: list[RepoEvidence],
) -> str:
    requester = f"<@{event.requester_slack_user_id}>" if event.requester_slack_user_id else event.requester_name or "미확인"
    evidence_lines = _format_evidence(evidence)
    return "\n".join(
        [
            "## Hermes 1차 진단",
            hermes_diagnosis.strip() or "Hermes 진단 결과가 비어 있습니다.",
            "",
            "## Slack QA 원문",
            f"- 요청자: {requester}",
            f"- 채널: {event.channel or '-'}",
            f"- 메시지 ts: {event.message_ts or '-'}",
            f"- 내용: {event.summary}",
            "",
            "## 사전 검색 근거",
            evidence_lines,
            "",
            "## 처리 메모",
            "- 이 이슈는 Slack QA 워커가 Hermes Agent 루프에 위임해 생성한 1차 진단입니다.",
            "- 실제 데이터 상태, 첨부 이미지, 재현 조건은 담당자가 최종 확인해야 합니다.",
        ]
    )


def create_github_issue(
    *,
    repo_full_name: str,
    title: str,
    body: str,
    assignees: Iterable[str] = (),
    labels: Iterable[str] = (),
    runner: Runner = subprocess.run,
) -> str:
    command = [
        "gh",
        "issue",
        "create",
        "--repo",
        repo_full_name,
        "--title",
        title,
        "--body",
        body,
    ]
    for assignee in [item.strip() for item in assignees if item and item.strip()]:
        command.extend(["--assignee", assignee])
    for label in [item.strip() for item in labels if item and item.strip()]:
        command.extend(["--label", label])

    result = runner(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "").strip() or f"gh issue create failed with exit code {result.returncode}")

    url = (result.stdout or "").strip().splitlines()[-1].strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"gh issue create did not return issue URL: {url}")
    return url


def build_slack_issue_reply(*, issue_url: str, reviewer_slack_user_id: str) -> str:
    reviewer = f"<@{reviewer_slack_user_id}>" if reviewer_slack_user_id else "보람"
    return "\n".join(
        [
            f"{issue_url}",
            f"깃허브 이슈로 처리해두었어요 :-) {reviewer} 검토해주세요 보람!",
        ]
    )


def _format_evidence(evidence: list[RepoEvidence]) -> str:
    if not evidence:
        return "- 사전 검색 근거 없음"
    rows = []
    for item in evidence[:10]:
        repo_name = Path(item.repo_path).name
        rows.append(f"- `{repo_name}/{item.path}:{item.line_number}`: {item.snippet[:180]}")
    return "\n".join(rows)


def _clean_summary_for_title(summary: str) -> str:
    cleaned = re.sub(r"<@[A-Z0-9]+>", "", summary or "")
    cleaned = cleaned.replace("님이 제출하신 QA 가 접수되었습니다.", "")
    cleaned = cleaned.replace("님이 제출하신 QA가 접수되었습니다.", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:|")
    return cleaned


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 1].rstrip() + "…"
