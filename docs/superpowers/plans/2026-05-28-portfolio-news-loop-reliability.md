# Portfolio News Loop Reliability Plan

작성일: 2026-05-28
대상: Hermes Merry AC Discovery 포트폴리오 뉴스 반복 수집 루프
상태: 구현 전 계획

## 1. 문제 정의

포트폴리오 뉴스 루프가 "안 돈다"는 현상은 단일 크롤러 오류라기보다 반복 실행, 수집 대상 설정, Slack 알림 설정, 실행 상태 관측이 한 화면에서 구분되지 않는 운영 문제다.

현재 확인된 사실은 다음과 같다.

- `crawl-sources`를 직접 실행하면 정상 종료된다.
- 로컬 DB의 `agent_runs`에는 최근 `crawl-sources` 성공 기록이 남는다.
- 최신 직접 실행 결과는 `target_count=2`, `crawled_source_count=5`, `notified_count=0`이다.
- 최신 수집 5건은 The VC 쪽으로 보이며, Platum 포트폴리오 뉴스는 신규 고유 매칭이 없었거나 중복 처리되었을 가능성이 높다.
- `.env.local`에는 Slack 알림에 필요한 `SLACK_CHANNEL`, `SLACK_BOT_TOKEN`이 없다.
- `AGENT_LOOP_JOBS=agent-work-queue`는 반복 뉴스 모니터링용 설정으로 부적합하다. `agent-work-queue`는 이미 생성된 체인 작업을 처리하는 큐이며, 완료된 체인이 자동으로 매시간 새 작업을 만드는 스케줄러는 아니다.
- 현재 로컬에는 `uv run python -m merry_runtime.jobs loop` 프로세스가 살아 있지만, Codex 터미널 세션에 의존하므로 durable service로 보기는 어렵다.

따라서 목표는 크롤러만 고치는 것이 아니라, 포트폴리오 뉴스 루프를 "반복 실행되고 있는지", "어떤 소스가 돌았는지", "왜 Slack이 안 갔는지", "Platum 신규 뉴스가 0건인지"를 운영자가 즉시 구분할 수 있게 만드는 것이다.

## 2. 목표

1. 포트폴리오 뉴스 감시는 `agent-work-queue`가 아니라 `agent_loop`의 반복 잡으로 명확히 분리한다.
2. `crawl-sources` 결과를 소스별로 분해해서 The VC와 Platum 상태를 구분한다.
3. Slack 알림 비활성 상태를 `notified_count=0` 안에 숨기지 않고 명시적으로 경고한다.
4. 대시보드와 실행 로그에서 최근 실행 시각, 최근 Platum 수집 시각, Slack 설정 여부, active 수집 행 수를 확인할 수 있게 한다.
5. 로컬과 Runpod에서 같은 방식으로 루프를 시작, 중지, 상태 확인할 수 있게 한다.

## 3. 비목표

- Platum 페이지 구조를 전면 재작성하지 않는다.
- The VC 로그인 기반 Playwright 개선과 본 계획을 한 번에 묶지 않는다.
- Slack 토큰, SMINFO 계정, The VC 계정 등 민감정보를 커밋하지 않는다.
- inactive 상태인 스프레드시트 행을 코드가 임의로 active로 바꾸지 않는다.

## 4. 설계 방향

### 4.1 반복 루프와 체인 큐를 분리한다

반복 뉴스 감시 기본값은 다음 프로필로 둔다.

```bash
AGENT_LOOP_JOBS=crawl-sources,backup-export
AGENT_LOOP_INTERVAL_SECONDS=3600
AGENT_LOOP_MAX_CYCLES=0
HERMES_ALLOW_UNBOUNDED_LOOP=1
```

`agent-work-queue`는 다음 같은 finite chain에만 사용한다.

- 후보 발굴 후 SMINFO 보강
- Candidate Detail 업데이트
- 시트 백업 체인
- 특정 canary 백업 체인

이렇게 분리하지 않으면, "큐에 남은 작업이 없는 정상 상태"와 "뉴스 루프가 죽은 상태"가 계속 섞인다.

### 4.2 수집 결과를 소스별로 기록한다

현재 `crawled_source_count=5`는 운영자가 보기에 부족하다. 최소한 다음 카운터를 추가한다.

- `thevc_source_count`
- `platum_extracted_count`
- `platum_new_source_count`
- `portfolio_signal_count`
- `portfolio_sheet_inserted_count`
- `portfolio_notifiable_count`
- `portfolio_notified_count`
- `notification_status`: `enabled`, `disabled_missing_channel`, `disabled_missing_token`, `no_recent_items`

이 값은 `agent_runs.output_json`에 남기고 대시보드에도 표시한다.

### 4.3 Slack 비활성은 성공이 아니라 경고로 노출한다

Slack 설정이 없을 때 크롤링 자체는 성공으로 처리하되, 실행 결과에는 다음 문장을 남긴다.

```text
Slack notification disabled: missing SLACK_CHANNEL or SLACK_BOT_TOKEN
```

DB에는 `warning_count` 또는 `warnings` 배열로 저장한다. 이렇게 해야 "새 뉴스가 없어서 0건"과 "Slack 설정이 없어서 0건"을 구분할 수 있다.

### 4.4 대시보드는 운영 화면이어야 한다

`tmp/hermes/loop-dashboard.html` 또는 관련 대시보드 생성 로직에 다음 상태를 추가한다.

- 루프 프로세스 감지 여부
- 최근 `crawl-sources` 실행 시각
- 최근 `crawl-sources` 성공 여부
- 최근 The VC 수집 시각
- 최근 Platum 수집 시각
- 최근 Portfolio News 시트 반영 시각
- Slack 설정 여부
- `Crawl Sources` 시트 active 행 수
- inactive이지만 watchlist가 존재하는 Accelerator News 행 경고
- 다음 실행 예상 시각

문구는 비개발자도 이해할 수 있게 작성한다.

예:

- "포트폴리오 뉴스 수집은 실행 중입니다."
- "Slack 알림은 꺼져 있습니다. 토큰 또는 채널 설정이 없습니다."
- "Platum에서 이번 실행에 새로 추가된 포트폴리오 뉴스는 없습니다."
- "수집 행은 활성화되어 있지만 신규 중복 제거 후 0건입니다."

## 5. 구현 단계

### Phase 1. 설정 예시와 문서 정리

작업:

- `configs/runpod.env.example`의 기본 `AGENT_LOOP_JOBS=agent-work-queue`를 재검토한다.
- 반복 뉴스 감시용 예시를 추가한다.
  - 후보 파일명: `configs/portfolio_news_loop.env.example`
- README 또는 runbook에 두 실행 모드를 분리해서 설명한다.
  - 반복 뉴스 감시: `crawl-sources,backup-export`
  - 체인 처리: `agent-work-queue`

검증:

- 문서만 보고 운영자가 어떤 모드를 켜야 하는지 판단 가능해야 한다.

### Phase 2. 실행 전 설정 진단 추가

작업:

- `merry_runtime.jobs loop` 시작 시 설정 진단을 출력한다.
- `crawl-sources`가 포함되어 있는데 `REVIEW_SHEET_ID`와 `CRAWL_TARGETS_JSON`이 모두 없으면 명확한 오류로 중단한다.
- `crawl-sources`가 포함되어 있는데 Slack 설정이 없으면 경고를 출력하되 크롤링은 계속한다.
- `agent-work-queue`가 포함되어 있는데 처리할 due task가 없으면 "큐가 비어 있음"을 명시한다.

검증:

```bash
uv run python -m merry_runtime.jobs loop --max-cycles 1 --interval-seconds 1
```

출력과 `agent_runs.output_json`에 설정 진단 결과가 남아야 한다.

### Phase 3. `crawl-sources` 결과 카운터 세분화

작업:

- `src/merry_runtime/pipelines/crawl_sources.py`의 결과 객체를 확장한다.
- Platum, The VC, portfolio signal, sheet insert, Slack notification 카운터를 분리한다.
- 기존 aggregate 필드는 호환을 위해 유지한다.
- `src/merry_runtime/job_runner.py`에서 새 카운터를 `output_json`에 저장한다.

검증:

- The VC만 수집된 경우에도 결과에 `platum_new_source_count=0`이 명시되어야 한다.
- Platum이 신규 중복 없음 상태라면 "실행됨, 신규 없음"으로 보인다.

### Phase 4. 대시보드 상태 개선

작업:

- 루프 대시보드 생성 로직을 찾아 최근 실행, 소스별 수집, Slack 설정 상태, active row 상태를 표시한다.
- 한국어 설명을 붙인다.
- 단순 로그 나열이 아니라 AIOps 운영판처럼 "현재 상태", "주의 필요", "최근 실행"을 구분한다.

검증:

- HTML을 열었을 때 비개발자도 다음 질문에 답할 수 있어야 한다.
  - 지금 루프가 도는가?
  - 마지막으로 언제 돌았는가?
  - Platum도 돌았는가?
  - Slack이 안 간 이유는 무엇인가?
  - 설정 문제인가, 신규 뉴스 0건인가?

### Phase 5. 로컬 durable loop 스크립트 추가

작업:

- `scripts/start_local_agent_loop.sh` 추가
  - `.env.local` 존재 확인
  - 중복 프로세스 방지
  - 로그 경로 `tmp/hermes/agent_loop.log`
  - PID 경로 `tmp/hermes/agent_loop.pid`
  - 기본 실행: `uv run python -m merry_runtime.jobs loop`
- `scripts/stop_local_agent_loop.sh` 추가
- `scripts/status_local_agent_loop.sh` 추가

검증:

```bash
scripts/start_local_agent_loop.sh
scripts/status_local_agent_loop.sh
scripts/stop_local_agent_loop.sh
```

각 명령이 수동 `ps`, 수동 DB SQL 없이 상태를 설명해야 한다.

### Phase 6. 테스트 추가

작업:

- Slack 설정 누락 시 경고가 남는지 테스트한다.
- Platum 신규 0건과 Slack 비활성을 구분하는 테스트를 추가한다.
- `agent-work-queue` 큐 비어 있음 상태가 실패처럼 보이지 않는지 테스트한다.
- 대시보드가 핵심 상태 텍스트를 포함하는지 테스트한다.

후보 테스트:

- `tests/integration/test_crawl_sources.py`
- `tests/test_jobs_cli.py`
- `tests/test_loop_dashboard.py`

검증:

```bash
uv run pytest
```

## 6. 배포 순서

1. 테스트를 추가하고 현재 실패를 확인한다.
2. `crawl-sources` 결과 카운터를 확장한다.
3. loop 설정 진단을 추가한다.
4. 대시보드 상태 표시를 개선한다.
5. 로컬 loop 스크립트를 추가한다.
6. `uv run pytest`를 통과시킨다.
7. 로컬에서 1회 루프를 실행한다.
8. DB와 시트에서 다음을 확인한다.
   - `agent_runs` 최신 `crawl-sources` 성공
   - `output_json`에 소스별 카운터 존재
   - `Portfolio News` 신규 반영 또는 신규 0건 상태 확인
   - Slack 설정 상태 명시
9. 필요하면 durable local loop를 시작한다.

## 7. 수용 기준

- `uv run python -m merry_runtime.jobs loop --max-cycles 1 --interval-seconds 1` 결과가 소스별로 해석 가능하다.
- The VC만 수집되어도 Platum이 "안 돈 것"인지 "돌았지만 신규 없음"인지 구분된다.
- Slack 설정이 없으면 `notified_count=0`만 보이지 않고, 명시적 경고가 남는다.
- 반복 뉴스 감시 기본 문서가 `crawl-sources,backup-export`를 안내한다.
- `agent-work-queue`는 recurring scheduler가 아니라 chain queue라고 문서화된다.
- 대시보드에서 최근 실행 시각과 Slack 설정 상태를 확인할 수 있다.
- 테스트가 통과한다.

## 8. 리스크와 대응

### 리스크 1. 카운터 추가가 기존 시트 반영을 깨뜨릴 수 있다

대응:

- 기존 필드는 유지하고 새 필드만 추가한다.
- `CrawlResult` 직렬화 테스트를 먼저 둔다.

### 리스크 2. Slack 경고를 오류로 처리하면 크롤링이 중단될 수 있다

대응:

- Slack 누락은 warning으로 처리한다.
- 크롤링과 시트 반영은 계속 진행한다.

### 리스크 3. Platum 구조 변경 문제와 운영 설정 문제가 섞일 수 있다

대응:

- 이번 계획에서는 구조 변경 탐지를 위한 카운터와 상태만 추가한다.
- 실제 selector 개선은 별도 Playwright 개선 계획으로 분리한다.

### 리스크 4. 로컬 loop 스크립트가 중복 실행을 만들 수 있다

대응:

- PID 파일과 실제 프로세스 확인을 함께 사용한다.
- 이미 실행 중이면 새 프로세스를 띄우지 않는다.

## 9. GSTACK Review Report

### CEO Review

핵심 문제는 "크롤러가 한 번 더 도는가"가 아니라 "운영자가 루프 상태를 믿을 수 있는가"다. 현재 상태에서는 수집이 성공해도 Slack이 꺼져 있으면 실패처럼 보이고, Platum 신규가 0건이어도 루프가 죽은 것처럼 보인다. 임원 보고나 운영 판단에 필요한 것은 건수보다 원인 구분이다. 따라서 이번 수정은 crawler tweak보다 observability와 runtime profile 분리가 우선이다.

### Engineering Review

`agent-work-queue`를 스케줄러처럼 확장하는 것은 피한다. 이미 있는 `agent_loop`가 반복 실행 책임을 갖고 있고, `agent-work-queue`는 finite chain queue로 두는 편이 구조가 단순하다. 변경 범위는 `crawl_sources`, `job_runner`, dashboard, scripts, docs, tests로 제한한다.

### DX Review

운영자가 매번 `ps`, SQLite 쿼리, 시트 확인을 직접 하는 구조는 유지보수 비용이 높다. `start/status/stop` 스크립트와 대시보드 상태 문구를 추가하면 "지금 도는가"를 10초 안에 확인할 수 있다.

### Design Review

대시보드는 개발자 로그가 아니라 운영판이어야 한다. 색상이나 카드보다 중요한 것은 상태 구분이다. "정상", "주의", "설정 필요", "신규 없음"을 명확히 분리하고 한국어 설명을 붙인다.

### QA Review

과장하면 안 되는 지점은 "Platum 개선"이다. 이번 계획은 Platum 신규 뉴스가 실제로 더 잘 잡힌다고 보장하지 않는다. 보장할 수 있는 것은 루프 실행 여부와 신규 0건/알림 비활성/설정 누락을 구분하는 것이다.

## 10. 권장 다음 액션

바로 구현한다면 Phase 2와 Phase 3부터 시작한다. 이 두 단계가 들어가야 다음 실행에서 "왜 안 돌았는지"를 로그와 대시보드가 직접 설명할 수 있다. 그다음 Phase 5로 durable local loop를 붙이면, 매번 터미널 세션에 의존하는 문제가 줄어든다.
