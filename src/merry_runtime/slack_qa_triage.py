from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from merry_runtime.github_qa_context import RepoEvidence


_INNERPLATFORM_DECISION_RE = re.compile(r"\[InnerPlatform\]\s*CIC 대표 검토 결과", re.IGNORECASE)
_REQUESTER_RE = re.compile(r"(?<!<)@(?P<name>[^\s@>]+)\s*님이\s*제출하신\s*QA")
_SLACK_MENTION_REQUESTER_RE = re.compile(r"<@(?P<user_id>U[A-Z0-9]+)>\s*님이\s*제출하신\s*QA")
_SPACES_RE = re.compile(r"\s+")

_QA_KEYWORDS = (
    "qa 등록",
    "qa가 접수",
    "qa 가 접수",
    "오류",
    "에러",
    "버그",
    "안됨",
    "안 돼",
    "안돼",
    "튕김",
    "홈으로 튕",
    "권한 없음",
    "화면이 깨",
    "저장 안",
    "로그인 안",
)

_STATUS_UPDATE_MARKERS = (
    "개선 공유",
    "*원인*",
    "해결 방법",
    "*해결",
    "기대효과",
    "배포 완료",
    "수정 완료",
)

_SEARCH_STOPWORDS = {
    "님이",
    "제출하신",
    "접수되었습니다",
    "등록",
    "가",
    "qa",
}


@dataclass(frozen=True, slots=True)
class QATriageEvent:
    summary: str
    requester_name: str = ""
    requester_slack_user_id: str = ""
    channel: str = ""
    message_ts: str = ""
    thread_ts: str = ""

    @property
    def dedupe_key(self) -> str:
        return "|".join((self.channel, self.message_ts or self.thread_ts, self.summary[:80]))

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def is_qa_message(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    if _INNERPLATFORM_DECISION_RE.search(normalized):
        return False
    if "requestId:" in normalized and "projectId:" in normalized:
        return False
    if any(marker in normalized for marker in _STATUS_UPDATE_MARKERS):
        return False

    lowered = normalized.lower()
    return any(keyword.lower() in lowered for keyword in _QA_KEYWORDS)


def extract_qa_event(
    text: str,
    *,
    channel: str = "",
    message_ts: str = "",
    thread_ts: str = "",
) -> QATriageEvent | None:
    if not is_qa_message(text):
        return None

    normalized = _normalize_text(text)
    requester_name = ""
    requester_user_id = ""

    requester = _REQUESTER_RE.search(normalized)
    if requester:
        requester_name = requester.group("name").strip()

    slack_requester = _SLACK_MENTION_REQUESTER_RE.search(normalized)
    if slack_requester:
        requester_user_id = slack_requester.group("user_id").strip()

    return QATriageEvent(
        summary=normalized,
        requester_name=requester_name,
        requester_slack_user_id=requester_user_id,
        channel=channel,
        message_ts=message_ts,
        thread_ts=thread_ts or message_ts,
    )


def build_github_search_terms(event: QATriageEvent) -> list[str]:
    summary = event.summary
    terms: list[str] = []

    keyword_map = {
        "튕": ["redirect", "router", "권한", "workspace", "project"],
        "홈": ["home", "redirect", "navigate"],
        "권한": ["permission", "role", "workspace", "forbidden"],
        "로그인": ["login", "auth", "session"],
        "저장": ["save", "persist", "update"],
        "화면": ["render", "component", "layout"],
        "qa": ["QA", "qa"],
    }
    for Korean, mapped_terms in keyword_map.items():
        if Korean in summary:
            terms.extend(mapped_terms)

    words = [
        word
        for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[가-힣]{2,}", summary)
        if word.lower() not in _SEARCH_STOPWORDS and not word.startswith("U0")
    ]
    terms.extend(words[:6])
    return _unique_terms(terms)[:12]


def build_qa_draft(event: QATriageEvent, evidence: list[RepoEvidence]) -> str:
    requester = f"<@{event.requester_slack_user_id}>" if event.requester_slack_user_id else event.requester_name
    requester_line = f"요청자: {requester}" if requester else "요청자: 미확인"
    confidence = "중간" if evidence else "낮음"

    lines = [
        ":mag: QA 원인 분석 초안입니다.",
        f"{requester_line}",
        f"요약: {event.summary}",
        f"신뢰도: {confidence}",
        "",
        "현재 판단:",
    ]
    if evidence:
        lines.append("관련 코드/문서 근거가 있어 아래 원인을 우선 의심합니다. 실제 수정 전에는 재현 확인이 필요합니다.")
    else:
        lines.append("아직 코드 근거가 충분하지 않아 원인은 추정 단계입니다. 재현 화면, URL, 계정 권한, 발생 시각을 같이 확인해야 합니다.")

    lines.extend(["", "근거:"])
    if evidence:
        lines.extend(_format_evidence_rows(evidence))
    else:
        lines.append("- 검색된 코드 근거 없음")

    lines.extend(
        [
            "",
            "답변 초안:",
            "접수된 QA를 확인했습니다. 재현 조건과 관련 코드 근거를 함께 확인해 원인을 좁히겠습니다.",
        ]
    )
    return "\n".join(lines)


def _format_evidence_rows(evidence: list[RepoEvidence]) -> list[str]:
    rows: list[str] = []
    for item in evidence[:8]:
        repo_name = Path(item.repo_path).name
        rows.append(f"- {repo_name}/{item.path}:{item.line_number} `{item.snippet[:120]}`")
    return rows


def _normalize_text(text: str) -> str:
    return _SPACES_RE.sub(" ", (text or "").replace("\u00a0", " ")).strip()


def _unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        normalized = term.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result
