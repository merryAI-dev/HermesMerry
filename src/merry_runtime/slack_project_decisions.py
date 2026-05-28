from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from merry_runtime.slack_requester_resolver import resolve_requester_user_id


REJECTION_DECISION = "수정 요청 후 반려"

_HEADER_RE = re.compile(r"(?:innerplatform-alerts\s*)?\[InnerPlatform\]\s*CIC 대표 검토 결과")
_TIME_MARKER_RE = re.compile(r"\[(?:오전|오후)\s+\d{1,2}:\d{2}\]")
_LABEL_RE = re.compile(
    r"^(프로젝트명|공식 계약명|계약 대상|담당조직\(CIC\)|결정|사유|검토자|요청자|requestId|projectId):\s*(.*)$"
)


@dataclass(frozen=True, slots=True)
class SlackProjectDecisionEvent:
    project_name: str
    contract_name: str
    contract_target: str
    cic: str
    decision: str
    reason: str
    reviewer: str
    requester: str
    request_id: str
    project_id: str
    channel: str = ""
    message_ts: str = ""
    thread_ts: str = ""

    @property
    def dedupe_key(self) -> str:
        return "|".join((self.request_id, self.project_id, self.decision, self.requester))

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProjectDecisionNotification:
    event: SlackProjectDecisionEvent
    requester_slack_user_id: str
    text: str

    @property
    def dedupe_key(self) -> str:
        return self.event.dedupe_key

    def to_dict(self) -> dict[str, object]:
        return {
            "dedupe_key": self.dedupe_key,
            "requester_slack_user_id": self.requester_slack_user_id,
            "text": self.text,
            "event": self.event.to_dict(),
        }


def parse_project_decision_events(
    text: str,
    *,
    channel: str = "",
    message_ts: str = "",
    thread_ts: str = "",
) -> list[SlackProjectDecisionEvent]:
    starts = [match.start() for match in _HEADER_RE.finditer(text or "")]
    events: list[SlackProjectDecisionEvent] = []

    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        row = _parse_block(text[start:end])
        event = _event_from_row(row, channel=channel, message_ts=message_ts, thread_ts=thread_ts)
        if event is not None:
            events.append(event)

    return events


def plan_rejection_notifications(
    events: list[SlackProjectDecisionEvent],
    *,
    requester_map: dict[str, str],
    sent_keys: set[str] | None = None,
) -> tuple[list[ProjectDecisionNotification], list[dict[str, str]]]:
    seen_keys = set(sent_keys or set())
    notifications: list[ProjectDecisionNotification] = []
    skipped: list[dict[str, str]] = []

    for event in events:
        if event.decision != REJECTION_DECISION:
            skipped.append({"request_id": event.request_id, "reason": "decision_not_target", "decision": event.decision})
            continue
        if event.dedupe_key in seen_keys:
            skipped.append({"request_id": event.request_id, "reason": "already_sent", "decision": event.decision})
            continue

        requester_user_id = resolve_requester_user_id(event.requester, requester_map)
        if not requester_user_id:
            skipped.append({"request_id": event.request_id, "reason": "requester_mapping_missing", "requester": event.requester})
            continue

        notifications.append(
            ProjectDecisionNotification(
                event=event,
                requester_slack_user_id=requester_user_id,
                text=build_rejection_confirmation_text(event, requester_user_id),
            )
        )
        seen_keys.add(event.dedupe_key)

    return notifications, skipped


def build_rejection_confirmation_text(event: SlackProjectDecisionEvent, requester_slack_user_id: str) -> str:
    reason = event.reason.strip() or "-"
    return "\n".join(
        [
            f"<@{requester_slack_user_id}> 확인해주세요 :-)",
            f"프로젝트명: {event.project_name}",
            f"결정: {event.decision}",
            f"사유: {reason}",
            f"requestId: {event.request_id}",
        ]
    )


def _parse_block(block: str) -> dict[str, str]:
    row: dict[str, str] = {}
    current_key = ""
    normalized = _TIME_MARKER_RE.sub("\n", block)

    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line or "[InnerPlatform]" in line:
            continue

        label = _LABEL_RE.match(line)
        if label:
            current_key = label.group(1)
            row[current_key] = _clean_slack_mrkdwn_value(label.group(2))
            continue

        if current_key:
            row[current_key] = f"{row[current_key]}\n{_clean_slack_mrkdwn_value(line)}".strip()

    return row


def _clean_slack_mrkdwn_value(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned.startswith("`") and cleaned.endswith("`"):
        cleaned = cleaned[1:-1]
    return cleaned.strip()


def _event_from_row(
    row: dict[str, str],
    *,
    channel: str,
    message_ts: str,
    thread_ts: str,
) -> SlackProjectDecisionEvent | None:
    required = ("프로젝트명", "결정", "요청자", "requestId", "projectId")
    if any(not row.get(key, "").strip() for key in required):
        return None

    return SlackProjectDecisionEvent(
        project_name=row.get("프로젝트명", "").strip(),
        contract_name=row.get("공식 계약명", "").strip(),
        contract_target=row.get("계약 대상", "").strip(),
        cic=row.get("담당조직(CIC)", "").strip(),
        decision=row.get("결정", "").strip(),
        reason=row.get("사유", "").strip(),
        reviewer=row.get("검토자", "").strip(),
        requester=row.get("요청자", "").strip(),
        request_id=row.get("requestId", "").strip(),
        project_id=row.get("projectId", "").strip(),
        channel=channel,
        message_ts=message_ts,
        thread_ts=thread_ts,
    )
