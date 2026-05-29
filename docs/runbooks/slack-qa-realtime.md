# Slack QA 실시간 초안 에이전트

`axr-qa` 채널에 QA성 메시지가 올라오면 Hermes Merry가 최근 메시지를 주기적으로 읽고, 로컬 GitHub 코드 근거를 검색한 뒤 Hermes Agent 루프에 대응을 위임합니다. 워커는 Slack 입출력과 중복 방지만 담당하고, 판단/문구 작성은 Hermes가 맡습니다.

## 동작 방식

- 대상 채널: `C0AH3LQ00AD` (`axr-qa`)
- 실행 방식: Slack history polling, 기본 20초 간격
- 응답 방식: 새 QA 메시지의 스레드에 초안 작성
- 근거 수집: 설정된 repo에서 `rg`로 관련 키워드 사전 검색
- 답글 작성: 기본값은 `SLACK_QA_DELEGATE=hermes`, Hermes CLI의 기존 Agent 루프 사용
- GitHub 이슈화: `--send` 운영 시 Hermes 1차 진단을 GitHub issue로 생성. 기본 대상은 `merryAI-dev/InnerPlatform`
- Slack 응답: Hermes 1차 진단은 QA 접수 메시지 스레드 댓글, 생성한 GitHub issue 제목/본문도 같은 스레드 댓글로 발송, GitHub issue 제목/링크와 보람 멘션은 채널 일반 메시지로 발송
- 보람 멘션: 기본 reviewer Slack ID는 `U099F3KA1CL`
- fallback: Hermes 위임 실패 시 deterministic local 초안으로 대체
- 중복 방지: `tmp/hermes/slack-qa-realtime-state.json`에 처리 키 저장
- 과거 메시지 보호: 서비스 시작 시 `--ignore-existing-on-start`로 기존 QA는 처리 완료로만 표시

## InnerPlatform Firestore 기준

Hermes는 InnerPlatform QA에서 Firestore를 화면 상태 저장소가 아니라 tenant 단위 운영 원장으로 봅니다.

- canonical repo: `https://github.com/merryAI-dev/InnerPlatform`
- 로컬 경로: `/Users/boram/InnerPlatform`
- 운영 URL: `https://inner-platform.vercel.app/`
- 별칭 도메인: `https://submit-mysc.com`
- 기본 tenant: `mysc`
- Firebase 확인 파일:
  - `/Users/boram/InnerPlatform/firebase/firestore.rules`
  - `/Users/boram/InnerPlatform/firebase/storage.rules`
  - `/Users/boram/InnerPlatform/src/app/lib/firebase.ts`
  - `/Users/boram/InnerPlatform/src/app/lib/firebase-context.tsx`

Firestore 접근 원칙은 read-only audit입니다. Hermes는 `get/list/query`로만 정합성을 확인하고, `create/set/update/delete/batch/transaction`은 실행하지 않습니다. 불일치가 보이면 영향 범위와 추천 patch를 dry-run 계획으로만 제시합니다.

실물 조회는 JSON key를 저장하지 않고 서비스 계정 impersonation으로 수행합니다. 권장 서비스 계정은 `roles/datastore.viewer`만 갖고, 로컬 사용자에게는 해당 서비스 계정의 `roles/iam.serviceAccountTokenCreator`만 부여합니다.

```bash
HERMES_FIRESTORE_PROJECT_ID=inner-platform-live-20260316
HERMES_FIRESTORE_TENANT_ID=mysc
HERMES_FIRESTORE_IMPERSONATE_SERVICE_ACCOUNT=hermes-firestore-auditor@inner-platform-live-20260316.iam.gserviceaccount.com
```

수동 read-only audit:

```bash
uv run python scripts/firestore_readonly_audit.py --page-size 3
```

우선 확인 경로:

- `orgs/{tenantId}/members`
- `orgs/{tenantId}/projects`
- `orgs/{tenantId}/project_requests`
- `orgs/{tenantId}/transactions`
- `orgs/{tenantId}/cashflow_weeks`
- legacy 후보: `orgs/{tenantId}/cashflowWeeks`
- `orgs/{tenantId}/projects/{projectId}/expense_sheets`
- `orgs/{tenantId}/projects/{projectId}/expense_intake`
- `orgs/{tenantId}/audit_logs`

판단 기준은 이름 매칭이 아니라 ID 연결입니다. 권한은 `members/{uid}`, 프로젝트는 `projects/{projectId}`, 등록/승인은 `project_requests`와 linked project status를 우선합니다.

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
SLACK_QA_GITHUB_REPO=merryAI-dev/InnerPlatform
SLACK_QA_GITHUB_ASSIGNEES=merryAI-dev
SLACK_QA_REVIEWER_SLACK_USER_ID=U099F3KA1CL
```

Hermes 루프를 우회하고 deterministic 초안만 확인하려면:

```bash
uv run python scripts/slack_qa_realtime_agent.py --once --limit 20 --delegate local
```

Slack 채널에는 아래 형식으로 일반 메시지를 남깁니다. Hermes 진단 본문과 생성한 GitHub issue 제목/본문은 QA 접수 메시지의 스레드 댓글로 남깁니다.

```text
[QA 1차 진단] 기업에서 회원가입 요청까지 하신 기록은 있는데 플랫폼 내에서는 확인이 불가능합니다. 혹시 이 계정 삭제처리가 된 것일까요?
https://github.com/merryAI-dev/InnerPlatform/issues/123
깃허브 이슈로 처리해두었어요 :-) <@U099F3KA1CL> 검토해주세요 보람!
```
