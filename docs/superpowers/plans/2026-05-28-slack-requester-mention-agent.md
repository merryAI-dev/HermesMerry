# Slack Requester Mention Agent Plan

작성일: 2026-05-28
대상: Slack에서 들어온 프로젝트 판정 메시지를 Hermes Agent가 파싱하고 요청자에게 자동 확인 멘션을 남기는 기능
상태: 구현 전 계획

## 1. 문제 정의

Slack에 다음과 같은 프로젝트 판정 메시지가 들어왔을 때, Hermes가 요청자를 자동으로 찾아 thread에 확인 요청을 남기고 싶다.

```text
프로젝트명: 2026미실란
공식 계약명: 수출용 미숫가루 5종 포장 패키지 및 선물하기 전용 패키지 디자인 개발
계약 대상: 중소벤처기업진흥공단, 대한무역투자진흥공단
담당조직(CIC): DXR팀
결정: 중복·폐기
사유: 중복되어 폐기함
검토자: 이예지(메씨리) Yeji Lee
요청자: 장란영(바닐라)
requestId: pr-1775182242417
projectId: p1775182242417
```

기대 동작:

```text
<@SLACK_USER_ID> 확인해주세요 :-)

프로젝트명: 2026미실란
결정: 중복·폐기
사유: 중복되어 폐기함
requestId: pr-1775182242417
```

## 2. 현재 코드 근거

이미 있는 것:

- `src/merry_runtime/adapters/slack.py`
  - `SlackNotifier.send_message(channel, text)`만 존재한다.
- `src/merry_runtime/runtime_factory.py`
  - `SLACK_BOT_TOKEN`이 있으면 Slack WebClient를 만든다.
  - `SLACK_CHANNEL`만 있고 토큰이 없으면 설정 오류를 낸다.
- `src/merry_mcp/server.py`
  - MCP 툴 입력을 검증하고 `send_slack_summary`에서 PII를 redaction한다.
- `src/merry_mcp/registry.py`
  - 현재 허용된 Slack 관련 MCP 툴은 `send_slack_summary`뿐이다.

없는 것:

- Slack에서 들어오는 이벤트를 받는 listener가 없다.
- 메시지 본문을 프로젝트 판정 필드로 파싱하는 모듈이 없다.
- `요청자: 장란영(바닐라)`를 Slack user id로 바꾸는 resolver가 없다.
- `requestId` 기준 중복 답장 방지 저장소가 없다.
- thread reply 전송 메서드가 없다.

## 3. 설계 결정

### 3.1 1차 수신 방식은 Hermes Agent Slack Gateway

1차 구현은 이 repo 안에 별도 Slack listener를 새로 만들지 않고, 이미 설치된 Hermes Agent의 Slack gateway를 사용한다.

이유:

- `/Users/boram/.hermes/hermes-agent/gateway/platforms/slack.py`에 Slack Socket Mode gateway가 이미 있다.
- Hermes Agent는 Slack private/public channel에서 `@mention` 기반으로 메시지를 받아 thread에 답장하는 기능을 이미 갖고 있다.
- Hermes Agent 문서상 channel에서는 기본적으로 `@mention`이 있어야 응답하고, private channel도 bot을 invite하면 사용할 수 있다.
- 새 bot/listener를 만들면 "Hermes agent를 통해서"라는 사용자 의도에서 벗어난다.

참고:

- Slack Socket Mode Python SDK: https://docs.slack.dev/tools/python-slack-sdk/socket-mode
- Slack `app_mention` event: https://docs.slack.dev/reference/events/app_mention/
- Slack `chat.postMessage`: https://docs.slack.dev/reference/methods/chat.postMessage
- Hermes Agent Slack docs: `/Users/boram/.hermes/hermes-agent/website/docs/user-guide/messaging/slack.md`

추후 운영 안정화가 필요하면 Hermes Agent gateway 안에서 project-decision 전용 route/plugin으로 승격한다. 이 repo에 독립 Slack event daemon을 새로 만드는 것은 1차 권장안에서 제외한다.

### 3.2 자동 태그는 명시 매핑 기반

`요청자` 텍스트를 Slack user id로 변환할 때 Slack display name 검색만으로 추정하지 않는다.

1차 방식:

```bash
SLACK_REQUESTER_MAP_JSON={"장란영":"U123","바닐라":"U123","이예지":"U456","메씨리":"U456"}
```

또는:

```bash
SLACK_REQUESTER_MAP_PATH=configs/slack_requester_map.example.json
```

주의:

- 실제 매핑 파일은 개인정보가 들어갈 수 있으므로 `.env.local` 또는 ignored 로컬 파일로 둔다.
- 커밋되는 파일은 `.example.json`만 둔다.
- 매핑이 없으면 태그하지 않고 fallback 메시지를 남긴다.

Fallback 예:

```text
요청자 매핑을 찾지 못했습니다: 장란영(바닐라)
운영자가 Slack user id 매핑을 추가한 뒤 다시 처리해주세요.
```

### 3.3 `requestId` 기준 idempotency

Slack 이벤트는 재전송될 수 있다. 같은 `requestId`에 대해 같은 action을 여러 번 답장하면 안 된다.

저장 키:

- `requestId`
- `projectId`
- `decision`
- `channel`
- `thread_ts`
- `action`: `requester_confirmation`

1차 구현은 SQLite에 별도 테이블을 직접 만들기보다, 프로젝트 DB 스키마에 맞춰 명시 테이블을 추가하는 쪽이 안전하다.

후보 테이블:

```text
slack_project_decision_events
```

필드:

- `event_id`
- `request_id`
- `project_id`
- `project_name`
- `decision`
- `requester_text`
- `requester_slack_user_id`
- `channel`
- `message_ts`
- `thread_ts`
- `reply_ts`
- `status`
- `error_message`
- `created_at`
- `updated_at`

## 4. 구현 범위

### Phase 1. 파서 추가

파일:

- `src/merry_runtime/slack_project_decisions.py`
- `tests/test_slack_project_decisions.py`

기능:

- `parse_project_decision_message(text) -> ProjectDecisionMessage`
- `should_request_confirmation(parsed) -> bool`
- `normalize_requester_aliases("장란영(바닐라)") -> ["장란영", "바닐라"]`

파싱 규칙:

- `key: value` 형태를 기본으로 한다.
- 한국어 key와 영문 key를 모두 허용한다.
- 필수값:
  - `프로젝트명`
  - `결정`
  - `요청자`
  - `requestId`
  - `projectId`
- `결정`은 우선 다음만 처리한다.
  - `중복·폐기`
  - `중복 폐기`
  - `중복/폐기`
  - `폐기`
- 필수값 누락 시 자동 답장하지 않고 parse warning만 남긴다.

테스트:

- 사용자 예시 메시지를 정상 파싱한다.
- 괄호 닉네임을 alias로 분리한다.
- 결정값이 처리 대상이 아니면 false를 반환한다.
- `requestId`가 없으면 처리하지 않는다.

### Phase 2. 요청자 resolver 추가

파일:

- `src/merry_runtime/slack_requester_resolver.py`
- `tests/test_slack_requester_resolver.py`

기능:

- `.env.local`의 `SLACK_REQUESTER_MAP_JSON` 또는 `SLACK_REQUESTER_MAP_PATH`를 읽는다.
- 요청자 원문에서 이름과 닉네임 후보를 만든다.
- 후보 중 하나가 매핑되면 Slack user id를 반환한다.
- 매핑이 없으면 안전하게 `None`을 반환한다.

비목표:

- 1차에서는 Slack `users.list` 자동 추정을 기본값으로 쓰지 않는다.
- 필요하면 `SLACK_REQUESTER_RESOLVE_MODE=users_list` 옵션으로 별도 확장한다.

### Phase 3. Slack adapter 확장

파일:

- `src/merry_runtime/adapters/slack.py`
- `tests/test_adapter_contracts.py`

추가 메서드:

```python
def reply_in_thread(self, *, channel: str, thread_ts: str, text: str) -> str:
    ...
```

Slack `chat.postMessage`에 `thread_ts`를 전달한다.

테스트:

- `reply_in_thread`가 `channel`, `text`, `thread_ts`를 정확히 전달하는지 확인한다.

### Phase 4. Hermes Agent 연동 추가

파일:

- Hermes Agent 쪽 연동 지점 확인:
  - `/Users/boram/.hermes/hermes-agent/gateway/platforms/slack.py`
  - `/Users/boram/.hermes/hermes-agent/website/docs/user-guide/messaging/slack.md`
- 이 repo 쪽 deterministic action:
  - `src/merry_runtime/slack_project_decisions.py`
  - `src/merry_runtime/slack_requester_resolver.py`
  - `src/merry_runtime/adapters/slack.py`
  - `scripts/reply_slack_project_decision.py`

기능:

- Hermes Agent Slack gateway가 받은 메시지를 agent turn으로 전달한다.
- Hermes Agent가 이 repo의 script/tool을 호출해 메시지를 deterministic하게 파싱한다.
- 처리 대상이면 requester resolver로 Slack user id를 찾는다.
- 기존 Slack Web API client 또는 Hermes Agent reply channel을 통해 thread에 확인 요청을 남긴다.
- `requestId` 기준으로 중복 답장을 막는다.

1차 처리 대상:

- `app_mention`
- 또는 Hermes Agent의 `SLACK_FREE_RESPONSE_CHANNELS` / `slack.free_response_channels`로 opt-in된 channel

주의:

- private channel 전체 메시지를 읽으려면 Slack scope가 커진다.
- 초기에는 `@Hermes Agent` mention으로 시작하는 것이 권한이 작고 안전하다.

### Phase 5. 설정 추가

Hermes Agent `~/.hermes/.env`에 필요한 값:

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_ALLOWED_USERS=U...
```

이 repo `.env.local` 또는 ignored local config에 필요한 값:

```bash
SLACK_PROJECT_DECISION_CHANNEL=C... 또는 G...
SLACK_REQUESTER_MAP_JSON={"장란영":"U...","바닐라":"U..."}
```

Slack App 설정:

- Socket Mode enabled
- App-level token with `connections:write`
- Bot token scope:
  - `chat:write`
  - `app_mentions:read`
  - private channel 전체 메시지를 자동 감시할 경우 `groups:history`
  - public channel 전체 메시지를 자동 감시할 경우 `channels:history`
  - user 자동 조회를 켤 경우 `users:read`

공식 문서 기준:

- `app_mention`에는 `app_mentions:read`가 필요하다.
- `message.channels`에는 `channels:history`가 필요하다.
- `chat.postMessage`에는 `chat:write`가 필요하다.
- Socket Mode App-level token에는 `connections:write`가 필요하다.

### Phase 6. 운영 로그와 실패 처리

로그에 남길 상태:

- `parsed`
- `ignored_missing_required_fields`
- `ignored_unsupported_decision`
- `requester_unresolved`
- `reply_sent`
- `duplicate_ignored`
- `slack_post_failed`

운영자가 봐야 하는 메시지:

- 매핑 없음
- 권한 부족
- Slack token 누락
- Socket Mode 연결 실패
- 같은 requestId 중복 처리

## 5. 수용 기준

- 사용자가 준 샘플 메시지를 파싱한다.
- `요청자: 장란영(바닐라)`에서 `장란영`, `바닐라` alias를 만든다.
- 매핑이 있으면 `<@U...> 확인해주세요 :-)` 형태로 thread 답장을 보낸다.
- 매핑이 없으면 잘못된 사람을 태그하지 않는다.
- 같은 `requestId` 이벤트가 2번 들어와도 답장은 1번만 보낸다.
- Slack 토큰과 requester map은 커밋되지 않는다.
- 테스트가 통과한다.

## 6. 필요한 사용자 준비물

구현 전에 사용자에게 필요한 것은 코드가 아니라 Slack App 설정값이다.

필수:

- Slack Bot Token: `xoxb-...`
- Slack App Token: `xapp-...`
- 이벤트를 받을 채널 ID: `C...`
- 요청자 매핑:

```json
{
  "장란영": "U...",
  "바닐라": "U..."
}
```

선택:

- 채널 전체 메시지를 감시할지, 봇이 mention된 메시지만 처리할지 결정
- fallback 메시지를 thread에 남길지, 내부 로그만 남길지 결정

권장 결정:

- 1차: `app_mention`만 처리
- 1차: requester map 없으면 태그하지 않고 thread에 매핑 누락 안내
- 1차: decision은 `중복·폐기` 계열만 처리

## 7. 테스트 계획

단위 테스트:

- 파서 테스트
- requester resolver 테스트
- Slack adapter thread reply 테스트
- event agent idempotency 테스트

통합 dry-run:

```bash
uv run pytest tests/test_slack_project_decisions.py tests/test_slack_requester_resolver.py tests/test_adapter_contracts.py
```

수동 staging:

1. 테스트 Slack private channel 생성
2. Hermes Agent bot 초대
3. `~/.hermes/.env`에 active `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_ALLOWED_USERS` 확인
4. 이 repo `.env.local` 또는 ignored local config에 channel, requester map 입력
5. `hermes gateway` 실행
6. 샘플 메시지에 Hermes Agent bot mention
6. thread 답장 확인
7. 같은 메시지 재전송 후 중복 답장 없는지 확인

## 8. NOT in scope

- Slack modal UI
- 승인/반려 버튼
- 모든 프로젝트 결정 타입 처리
- Slack user directory 자동 동기화
- HTTP Events API 배포
- 계약서/프로젝트 DB 원본 시스템 쓰기

## 9. Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|----------------|-----------|-----------|----------|
| 1 | CEO | 1차 수신 방식을 Socket Mode로 선택 | Mechanical | Explicit over clever | 현재 Hermes는 job/loop 중심이고 외부 HTTP endpoint 없이 붙일 수 있다 | Events API HTTP endpoint |
| 2 | Eng | 요청자 태그는 명시 매핑 기반으로 제한 | Mechanical | Completeness | 동명이인과 display name 오탐을 피해야 한다 | Slack users.list 추정 태그 기본값 |
| 3 | Eng | `requestId` 기준 idempotency 필수 | Mechanical | Completeness | Slack 이벤트 재전송 시 같은 thread에 반복 답장이 생기면 운영 신뢰가 깨진다 | 단순 fire-and-forget 답장 |
| 4 | DX | 1차 처리 이벤트는 `app_mention` 권장 | Taste | Pragmatic | 권한이 작고 테스트하기 쉽다. 다만 채널 전체 자동 감시가 필요하면 `message.channels`가 더 편하다 | 처음부터 채널 전체 감시 |

## 10. GSTACK REVIEW REPORT

### CEO Review

이 기능의 가치는 "Slack 자동 답장"이 아니라 요청자가 중복·폐기 결정을 놓치지 않게 하는 운영 폐루프다. 따라서 첫 구현은 넓은 자동화보다 오탐 없는 확인 요청에 집중해야 한다. Hermes Agent를 메시지 수신/응답 gateway로 쓰고, 이 repo는 프로젝트 판정 파싱과 requester mapping을 담당한다.

### Design Review

초기 버전에는 별도 UI가 없다. 사용자 경험은 Slack thread reply 하나로 끝난다. 따라서 메시지는 짧고 맥락을 포함해야 한다. `<@user> 확인해주세요 :-)`만 보내면 정보가 부족하므로 프로젝트명, 결정, 사유, requestId를 함께 넣는다.

### Engineering Review

가장 작은 안전한 변경은 새 parser/resolver 모듈과 reply script를 추가하고, Hermes Agent가 그 script/tool을 호출하게 하는 것이다. 이 repo 안에 독립 Slack gateway를 새로 띄우면 agent 경로가 둘로 갈라져 운영자가 혼동한다.

### DX Review

운영자가 필요한 값은 Hermes Agent Slack token, channel, requester map이다. `~/.hermes/.env`는 agent gateway용, 이 repo `.env.local`은 프로젝트 판정 매핑용으로 역할을 분리한다. 실패 메시지는 "Hermes Agent Slack 미설정", "매핑 없음", "권한 없음", "중복 처리됨"을 구분해야 한다.

### Risks

- requester map이 없으면 자동 태그가 불가능하다.
- 채널 전체 감시는 `channels:history` 권한이 필요해 Slack 권한 범위가 커진다.
- Socket Mode는 실행 프로세스가 죽으면 이벤트를 받지 못한다. 이후 durable loop나 Runpod/Cloud Run supervision이 필요하다.

### Recommended Next Step

구현은 Phase 1부터 Phase 4까지 한 번에 진행하되, Slack App 설정은 `app_mention` 기준으로 시작한다. 사용자가 준비해야 할 것은 `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_PROJECT_DECISION_CHANNEL`, `SLACK_REQUESTER_MAP_JSON`이다.
