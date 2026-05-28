# Slack QA 실시간 초안 에이전트

`axr-qa` 채널에 QA성 메시지가 올라오면 Hermes Merry가 최근 메시지를 주기적으로 읽고, 로컬 GitHub 코드 근거를 검색한 뒤 Hermes Agent 루프에 대응을 위임합니다. 워커는 Slack 입출력과 중복 방지만 담당하고, 판단/문구 작성은 Hermes가 맡습니다.

## 동작 방식

- 대상 채널: `C0AH3LQ00AD` (`axr-qa`)
- 실행 방식: Slack history polling, 기본 20초 간격
- 응답 방식: 새 QA 메시지의 스레드에 초안 작성
- 근거 수집: 설정된 repo에서 `rg`로 관련 키워드 사전 검색
- 답글 작성: 기본값은 `SLACK_QA_DELEGATE=hermes`, Hermes CLI의 기존 Agent 루프 사용
- GitHub 이슈화: `--send` 운영 시 Hermes 1차 진단을 GitHub issue로 생성하고 Slack 스레드에는 이슈 링크를 남김
- 보람 멘션: 기본 reviewer Slack ID는 `U099F3KA1CL`
- fallback: Hermes 위임 실패 시 deterministic local 초안으로 대체
- 중복 방지: `tmp/hermes/slack-qa-realtime-state.json`에 처리 키 저장
- 과거 메시지 보호: 서비스 시작 시 `--ignore-existing-on-start`로 기존 QA는 처리 완료로만 표시

## 실행/중지

현재 로컬 launchd 서비스로 등록되어 있습니다.

```bash
launchctl print gui/$(id -u)/ai.axr.qa-realtime
launchctl kickstart -k gui/$(id -u)/ai.axr.qa-realtime
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/ai.axr.qa-realtime.plist
```

로그는 아래에서 확인합니다.

```bash
tail -f tmp/hermes/logs/slack-qa-realtime.out.log
tail -f tmp/hermes/logs/slack-qa-realtime.err.log
```

## 수동 점검

실제 Slack에 쓰지 않고 최근 메시지만 분석합니다.

```bash
uv run python scripts/slack_qa_realtime_agent.py --once --limit 20
```

실제 스레드에 초안을 남깁니다.

```bash
uv run python scripts/slack_qa_realtime_agent.py --once --limit 20 --send
```

## 필요한 시크릿

스크립트는 현재 shell 환경변수, repo `.env.local`, `~/.hermes/.env` 순서로 Slack 토큰을 찾습니다.

- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`은 Socket Mode 옵션을 쓸 때만 필요합니다.

기본 운영은 Socket Mode가 아니라 polling입니다. 기존 Hermes Slack gateway와 이벤트 수신을 두고 경쟁하지 않기 위해서입니다.

## Hermes 위임 설정

기본값은 Hermes 위임입니다.

```bash
SLACK_QA_DELEGATE=hermes
SLACK_QA_HERMES_PROVIDER=openai-codex
SLACK_QA_HERMES_MODEL=gpt-5.3-codex
SLACK_QA_HERMES_TOOLSETS=terminal
SLACK_QA_HERMES_MAX_TURNS=20
SLACK_QA_CREATE_GITHUB_ISSUE=1
SLACK_QA_GITHUB_REPO=merryAI-dev/startup-diagnostic-platform
SLACK_QA_GITHUB_ASSIGNEES=merryAI-dev
SLACK_QA_REVIEWER_SLACK_USER_ID=U099F3KA1CL
```

Hermes 루프를 우회하고 deterministic 초안만 확인하려면:

```bash
uv run python scripts/slack_qa_realtime_agent.py --once --limit 20 --delegate local
```

Slack 스레드에는 아래 형식으로 남깁니다.

```text
https://github.com/merryAI-dev/startup-diagnostic-platform/issues/123
깃허브 이슈로 처리해두었어요 :-) <@U099F3KA1CL> 검토해주세요 보람!
```
