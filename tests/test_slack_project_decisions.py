from __future__ import annotations

from merry_runtime.slack_project_decisions import parse_project_decision_events, plan_rejection_notifications
from merry_runtime.slack_requester_resolver import resolve_requester_user_id, requester_aliases


def test_parse_innerplatform_messages_and_ignore_non_review_text() -> None:
    text = """innerplatform-alerts [InnerPlatform] CIC 대표 검토 결과
프로젝트명: 2026 CTS2
공식 계약명: 2023-2026 창업투자 전문기관을 통한 혁신적기술프로그램(CTS)참여기업 역량 강화 용역
계약 대상: KOICA
담당조직(CIC): 개발협력센터
결정: 수정 요청 후 반려
사유: 서류상 참여인력 기준으로 팀원 업데이트 부탁드립니다!
우선 사업비는 4개년 전체 계약금을 기준으로 작성 부탁드립니다.
검토자: Inhyo Ko (베리)
요청자: 김현지(데이지)
requestId: pr-1773906226325
projectId: p1773906226325[오후 1:28]qa 등록 @솔_하송희 님이 제출하신 QA 가 접수되었습니다.[오후 2:17][InnerPlatform] CIC 대표 검토 결과
프로젝트명: 26예비그린유니콘
결정: 승인 완료
사유: -
검토자: 이예지(메씨리) Yeji Lee
요청자: 백민혁(혜윰) Minhyeok Baek
requestId: pr-1778036126702
projectId: p1778036126702"""

    events = parse_project_decision_events(text, channel="G123", message_ts="177.1")

    assert len(events) == 2
    assert events[0].project_name == "2026 CTS2"
    assert events[0].decision == "수정 요청 후 반려"
    assert events[0].reason == "서류상 참여인력 기준으로 팀원 업데이트 부탁드립니다!\n우선 사업비는 4개년 전체 계약금을 기준으로 작성 부탁드립니다."
    assert events[1].decision == "승인 완료"


def test_parse_slack_block_mrkdwn_values() -> None:
    text = """*[InnerPlatform] CIC 대표 검토 결과*
프로젝트명: `JLIN IBS`
공식 계약명: 혼합금융 기반 동남아 임팩트 생태계 조성 및 스케일업 투자 사업
계약 대상: KOICA
담당조직(CIC): 개발협력센터
결정: 수정 요청 후 반려
사유: 금액과 입금 계획, 계약서 누락되어 있어 반려
검토자: 이예지(메씨리) Yeji Lee
요청자: 김혜령 (테일러)
requestId: `pr-1776054335896`
projectId: `p1776054335896`"""

    [event] = parse_project_decision_events(text)

    assert event.project_name == "JLIN IBS"
    assert event.request_id == "pr-1776054335896"
    assert event.project_id == "p1776054335896"


def test_requester_aliases_and_explicit_resolution() -> None:
    assert requester_aliases("김현지(데이지)") == ("김현지(데이지)", "데이지", "김현지", "김현지 (데이지)")
    assert resolve_requester_user_id("김현지(데이지)", {"데이지": "U123"}) == "U123"
    assert resolve_requester_user_id("김현지(데이지)", {"김현지": "U456"}) == "U456"


def test_plan_notifications_only_mentions_rejections_with_mapping() -> None:
    text = """[InnerPlatform] CIC 대표 검토 결과
프로젝트명: 2026 CTS2
결정: 수정 요청 후 반려
사유: 금액과 입금 계획, 서류상인력 내용이 누락되어 있습니다
검토자: 이예지(메씨리) Yeji Lee
요청자: 김현지(데이지)
requestId: pr-1
projectId: p1
[InnerPlatform] CIC 대표 검토 결과
프로젝트명: GGGI 베트남1
결정: 승인 완료
사유: -
검토자: 이예지(메씨리) Yeji Lee
요청자: 김혜령 (테일러)
requestId: pr-2
projectId: p2
[InnerPlatform] CIC 대표 검토 결과
프로젝트명: JLIN IBS
결정: 수정 요청 후 반려
사유: 계약서 누락
검토자: 이예지(메씨리) Yeji Lee
요청자: 김혜령 (테일러)
requestId: pr-3
projectId: p3"""

    events = parse_project_decision_events(text)
    notifications, skipped = plan_rejection_notifications(
        events,
        requester_map={"데이지": "U_DAISY"},
        sent_keys={"pr-0|p0|수정 요청 후 반려|아무개"},
    )

    assert len(notifications) == 1
    assert notifications[0].requester_slack_user_id == "U_DAISY"
    assert "<@U_DAISY> 확인해주세요 :-)" in notifications[0].text
    assert "프로젝트명: 2026 CTS2" in notifications[0].text
    assert {item["reason"] for item in skipped} == {"decision_not_target", "requester_mapping_missing"}


def test_sent_keys_skip_duplicate_rejection_notification() -> None:
    event = parse_project_decision_events(
        """[InnerPlatform] CIC 대표 검토 결과
프로젝트명: 2026 CTS2
결정: 수정 요청 후 반려
사유: 누락
검토자: 이예지
요청자: 김현지(데이지)
requestId: pr-1
projectId: p1"""
    )[0]

    notifications, skipped = plan_rejection_notifications(
        [event],
        requester_map={"데이지": "U_DAISY"},
        sent_keys={event.dedupe_key},
    )

    assert notifications == []
    assert skipped == [{"request_id": "pr-1", "reason": "already_sent", "decision": "수정 요청 후 반려"}]


def test_duplicate_rejection_in_same_batch_is_not_notified_twice() -> None:
    events = parse_project_decision_events(
        """[InnerPlatform] CIC 대표 검토 결과
프로젝트명: 2026 CTS2
결정: 수정 요청 후 반려
사유: 첫 번째 반려
검토자: 베리
요청자: 김현지(데이지)
requestId: pr-1
projectId: p1
[InnerPlatform] CIC 대표 검토 결과
프로젝트명: 2026 CTS2
결정: 수정 요청 후 반려
사유: 두 번째 반려
검토자: 메씨리
요청자: 김현지(데이지)
requestId: pr-1
projectId: p1"""
    )

    notifications, skipped = plan_rejection_notifications(events, requester_map={"데이지": "U_DAISY"})

    assert len(notifications) == 1
    assert skipped == [{"request_id": "pr-1", "reason": "already_sent", "decision": "수정 요청 후 반려"}]
