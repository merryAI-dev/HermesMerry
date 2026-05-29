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


def build_hermes_qa_execution_prompt(
    event: QATriageEvent,
    evidence: list[RepoEvidence],
    *,
    repo_paths: Iterable[str | Path],
    github_repo: str,
    reviewer_slack_user_id: str,
    slack_channel: str,
    thread_ts: str,
    extra_context: str = "",
) -> str:
    requester = f"<@{event.requester_slack_user_id}>" if event.requester_slack_user_id else event.requester_name or "미확인"
    repo_lines = "\n".join(f"- {Path(path).expanduser().resolve()}" for path in repo_paths)
    evidence_lines = _format_evidence(evidence)

    return f"""당신은 AXR팀 QA 대응 에이전트 Hermes입니다.

이 작업은 초안 생성이 아니라 실제 실행 작업입니다. 아래 순서를 Hermes Agent loop 안에서 직접 수행하세요.

작업 대상:
- Slack 채널: {slack_channel}
- QA 접수 메시지 thread_ts: {thread_ts}
- 요청자: {requester}
- GitHub repo: {github_repo}
- 보람 Slack user ID: {reviewer_slack_user_id}

Firestore read-only 운영 원장 원칙:
{_firestore_read_only_guidance()}

Slack QA:
{event.summary}

확인할 repo:
{repo_lines or "- repo 미지정"}

사전 검색 근거:
{evidence_lines}

추가 컨텍스트:
{extra_context.strip() or "- 없음"}

실행해야 할 일:
1. repo 코드와 사전 검색 근거를 바탕으로 1차 진단을 작성하세요.
2. `gh issue create --repo {github_repo}`를 사용해 GitHub issue를 생성하세요.
   - 제목은 `[QA 1차 진단] ...` 형태로 작성하세요.
   - 본문에는 Hermes 1차 진단, Slack QA 원문, 확인한 코드/데이터 경로, 추가 확인 필요사항을 포함하세요.
3. Slack QA 접수 메시지 스레드(`channel={slack_channel}`, `thread_ts={thread_ts}`)에 댓글을 직접 남기세요.
   - 첫 번째 댓글: Hermes 1차 진단.
   - 두 번째 댓글: 생성한 GitHub issue 제목과 본문. 제목은 `[QA 1차 진단] ...`을 그대로 포함하세요.
   - `SLACK_BOT_TOKEN`은 환경변수에서 사용하고 절대 출력하지 마세요.
   - 필요하면 `python - <<'PY'`로 `slack_sdk.WebClient`를 사용하세요.
4. Slack 채널 일반 메시지로 아래 형식을 직접 발송하세요. 이 메시지는 스레드 댓글이 아닙니다.
   `[QA 1차 진단] <GitHub issue 제목>`
   `<GitHub issue URL>`
   `깃허브 이슈로 처리해두었어요 :-) <@{reviewer_slack_user_id}> 검토해주세요 보람!`

주의:
- 코드 수정/배포를 했다고 말하지 마세요. 이 작업은 1차 진단과 이슈화입니다.
- 근거가 부족하면 단정하지 말고 확인 필요로 표현하세요.
- Firestore는 read-only audit만 수행하세요. Firestore write/delete/update/set/batch/transaction은 어떤 경우에도 실행하지 마세요.
- 시크릿, 토큰, 쿠키는 출력하지 마세요.

최종 응답:
- 생성한 GitHub issue URL
- Slack 스레드 진단 댓글 발송 여부
- Slack 스레드 GitHub issue 본문 댓글 발송 여부
- Slack 채널 메시지 발송 여부
만 간단히 보고하세요.
"""


def _firestore_read_only_guidance() -> str:
    return """- Firestore는 화면 상태 저장소가 아니라 tenant 단위 운영 원장입니다.
- InnerPlatform canonical repo는 `https://github.com/merryAI-dev/InnerPlatform`, 로컬 경로는 `/Users/boram/InnerPlatform`입니다.
- 운영 URL은 `https://inner-platform.vercel.app/`, 별칭 도메인은 `https://submit-mysc.com`입니다.
- Firebase 프로젝트 ID와 설정은 코드상 Firebase 설정, `.env`, Vercel env를 기준으로 확인합니다.
- Firebase 관련 파일은 `/Users/boram/InnerPlatform/firebase/firestore.rules`, `/Users/boram/InnerPlatform/firebase/storage.rules`, `/Users/boram/InnerPlatform/src/app/lib/firebase.ts`, `/Users/boram/InnerPlatform/src/app/lib/firebase-context.tsx`를 우선 봅니다.
- Firestore 실물 조회가 필요하면 `scripts/firestore_readonly_audit.py`를 우선 사용합니다. 장기 JSON 키 대신 `HERMES_FIRESTORE_IMPERSONATE_SERVICE_ACCOUNT`로 read-only 서비스 계정 impersonation을 사용합니다.
- 모든 주요 데이터는 먼저 `orgs/{tenantId}/...` tenant scope에서 확인합니다. 현재 운영 tenant는 보통 `mysc`입니다.
- tenant가 다르면 같은 프로젝트명이어도 다른 데이터로 봅니다.
- `orgs/{orgId}/members/{uid}`가 권한 원장의 출발점입니다. email/name/label보다 uid와 role(admin, finance, pm, viewer)을 우선합니다.
- `orgs/{orgId}/projects/{projectId}`를 canonical project source로 봅니다. 프로젝트명, PM명, 등록자명은 display label일 수 있으므로 단독 기준으로 쓰지 않습니다.
- `project_requests`는 등록/승인 원문입니다. registrationSource보다 linked request status와 linked project를 우선 확인합니다.
- cashflow/actual/projection은 계산값이 아니라 저장 원장입니다. transactions는 actual의 근거, `cashflow_weeks` 또는 legacy `cashflowWeeks`는 주차별 저장 결과로 봅니다.
- 컬렉션명이 혼재될 수 있으니 `cashflow_weeks`와 legacy `cashflowWeeks`를 모두 schema alias 후보로 점검합니다.
- 우선 확인 컬렉션: `orgs/{tenantId}/members`, `orgs/{tenantId}/projects`, `orgs/{tenantId}/project_requests`, `orgs/{tenantId}/transactions`, `orgs/{tenantId}/cashflow_weeks`, `orgs/{tenantId}/cashflowWeeks`, `orgs/{tenantId}/projects/{projectId}/expense_sheets`, `orgs/{tenantId}/projects/{projectId}/expense_intake`, `orgs/{tenantId}/audit_logs`.
- Hermes는 Firestore를 직접 수정하는 자동화 봇이 아니라 운영 원장의 정합성을 점검하는 read-only 에이전트입니다.
- Firestore에서는 get/list/query만 허용됩니다. create/set/update/delete/batch/transaction은 금지입니다.
- 불일치가 있으면 영향 범위와 추천 patch를 dry-run 계획으로만 작성합니다. Hermes가 Firestore에 직접 쓰거나 지우면 안 됩니다.
- 삭제는 금지입니다. 삭제가 필요해 보여도 archived/trashed/status 필드 사용을 추천안으로만 제시합니다.
- nested object는 얕게 덮어쓰면 안 됩니다. cashflow, project financials, owner metadata는 기존 값을 읽고 필요한 필드만 deep merge하는 계획만 제시합니다.
- loading 중 null, 권한 sync 지연, project sync 지연을 오류로 단정하지 않습니다. 상태값 변화는 audit event로 보고 redirect나 destructive update의 근거로 삼지 않습니다.
- 핵심: 이름이 아니라 ID 연결을 보고, 쓰기 전 단계가 아니라 쓰기 제안 전 단계에서 read-only audit과 deep merge plan을 먼저 만듭니다."""


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
