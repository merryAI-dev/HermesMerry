# HermesMerry

HermesMerry는 액셀러레이터 후보 기업을 더 체계적으로 발굴하기 위한 Python 기반 운영 런타임입니다.

한 줄로 말하면, 공개적으로 접근 가능한 기업/투자/뉴스 신호를 모으고, 후보 기업을 SQLite 기반 Mother DB에 누적한 뒤, 필요한 경우 SMINFO(중소기업현황정보)로 기업 정보를 보강하고, 사람이 검토할 수 있도록 Google Sheets와 로컬 AIOps 대시보드에 상태를 보여주는 시스템입니다.

이 저장소는 “완성된 자동 의사결정 서비스”가 아닙니다. 현재는 실제 운영을 준비하기 위한 런타임 기반, 큐 구조, 크롤러 어댑터, SMINFO 보강 루프, Sheet 반영, 테스트, 운영 문서를 갖춘 상태입니다. 실제 운영 품질은 계정/시크릿 설정, 외부 사이트 응답, Google Sheets 권한, 그리고 운영자의 검토 절차에 따라 달라집니다.

## 왜 만드는가

액셀러레이터 발굴 업무는 보통 다음 문제가 반복됩니다.

- 여러 뉴스/투자 DB/공개 사이트를 사람이 계속 확인해야 합니다.
- 같은 기업이 다른 이름으로 반복 등장합니다.
- “관심 기업인지”, “육성 기업인지”, “투자 포트폴리오 소식인지”가 섞입니다.
- 밤사이 루프가 실제로 돌았는지, 어디서 멈췄는지 확인하기 어렵습니다.
- 후보 기업의 매출, 영업이익, 주주, 대표자 같은 기본 정보가 따로 흩어져 있습니다.

HermesMerry는 이 문제를 한 번에 “AI가 알아서 결정”하는 방식으로 풀기보다, 증거를 남기고 사람이 검토할 수 있는 운영 흐름으로 정리합니다. 핵심은 자동화보다 추적 가능성입니다. 어떤 루프가 언제 돌았고, 어떤 기업이 왜 큐에 들어왔고, 어디서 막혔는지를 확인할 수 있어야 합니다.

## 현재 할 수 있는 일

- 투자 포트폴리오 관련 뉴스와 우리 육성 기업 모니터링 대상을 분리합니다.
- 사용자가 준 기업명 원문은 보존하고, 검색 키워드에는 `(주)`, `주식회사`, `농업회사법인` 같은 좁은 법인 표기만 보수적으로 제거합니다.
- THE VC, Platum 등 설정된 공개 소스를 제한된 범위 안에서 수집합니다.
- 후보 기업, 원천 URL, 수집 결과, 실행 이력, 큐 상태를 SQLite-backed Mother DB에 저장합니다.
- `agent_work_queue`를 통해 `crawl -> sminfo -> resolve -> score -> sync -> backup` 순서의 체인 루프를 관리합니다.
- `sminfo_enrichment_queue`를 통해 기업별 SMINFO 조회 대상을 따로 관리하고, 재시도/대기/실패/완료 상태를 남깁니다.
- Google Sheets를 사람이 보는 운영 콘솔로 사용합니다. 운영자는 시트에서 후보 기업과 상태를 확인하고, 필요한 수정을 할 수 있습니다.
- 로컬 AIOps 대시보드를 HTML로 렌더링해 최근 실행 시간, 큐 상태, 테이블 카운트, 루프 구조를 확인합니다.
- Gmail 연동은 발송이 아니라 draft 생성까지만 다룹니다. 자동 발송은 하지 않습니다.

## 아직 조건부인 것

- THE VC 로그인 자동화는 사이트 구조 변경, 캡차, human verification에 막힐 수 있습니다. 이 경우 실패를 숨기지 않고 경고/오류로 기록하는 것이 현재 설계입니다.
- SMINFO 보강은 `SMINFO_USER_ID`, `SMINFO_PASSWORD`, `REVIEW_SHEET_ID`, Playwright 실행 환경이 있어야 실제로 동작합니다.
- Google Sheets, Gmail, Slack, Claude, KVIC, Runpod 연동은 `.env.local` 또는 배포 시크릿이 필요합니다.
- 현재 크롤링, 큐, Sheet 반영, SMINFO 루프에는 GPU가 필요하지 않습니다. Gemma, Qwen 같은 로컬 모델을 붙이는 경우에도 먼저 별도 scale-to-zero endpoint로 분리하는 편이 비용 관리에 안전합니다.
- BigQuery와 Cloud Run은 선택지로 남겨둔 인프라입니다. 지금 기본 방향은 SQLite-first, Runpod/CPU-friendly staging입니다.

## Runpod-first staging

기본 staging 경로는 Runpod Pod가 아래 Docker 이미지를 당겨 실행하는 방식입니다.

```bash
docker.io/boram1220/hermes-merry:staging
```

이 모드에서 Hermes는 persistent runtime volume 위의 SQLite-backed Mother DB를 기본 저장소로 사용하고, Google Sheets를 사람이 보는 운영 콘솔로 사용합니다. BigQuery는 추후 warehouse/export가 필요할 때 붙이는 선택지입니다. Cloud Run is optional and remains available through the separate Cloud Run runbook path.

Runpod에서 장시간 루프를 켤 때는 비용 리스크가 있으므로 `HERMES_ALLOW_UNBOUNDED_LOOP=1`을 명시해야 합니다. 이 장치는 실수로 무한 루프를 켜서 CPU/GPU 비용이 누적되는 것을 막기 위한 안전장치입니다.

## 전체 흐름

```text
크롤링 대상 설정
        |
        v
crawl-sources
        |
        +--> raw_sources / signals / candidate records
        |
        +--> sminfo_enrichment_queue
                  |
                  v
             enrich-sminfo
                  |
                  +--> sminfo_company_profiles
                  +--> Candidate Detail / SMINFO Queue Sheet projection

agent_work_queue 체인:
crawl -> sminfo -> resolve -> score -> sync -> backup
```

각 단계의 의미는 다음과 같습니다.

1. `crawl-sources`: 설정된 URL 또는 Sheet의 Crawl Sources 탭을 읽고 공개 소스를 수집합니다.
2. 후보 기업 저장: 수집된 기업/뉴스/투자 신호를 Mother DB에 저장합니다.
3. SMINFO 큐 생성: 기업명이 확인되면 SMINFO 조회 대상으로 `sminfo_enrichment_queue`에 넣습니다.
4. `enrich-sminfo`: 조회 가능한 기업을 제한된 배치로 처리하고, 매출/영업이익/대표자/주주 등 구조화 정보를 저장합니다.
5. `resolve-entities`: 중복 가능성이 있는 기업을 정리합니다. 단, 애매한 기업은 사람 검토가 가능하도록 보수적으로 남깁니다.
6. `score-candidates`: AC 관점의 우선순위를 계산합니다.
7. `sync-review-sheet`: Google Sheets에 사람이 볼 수 있는 형태로 반영합니다.
8. `backup-export`: SQLite, wiki, Sheet-facing 상태를 백업 표면으로 내보냅니다.
9. `render-loop-dashboard`: 최근 실행 시간과 큐 상태를 HTML 대시보드로 렌더링합니다.

체인 정의는 `configs/agent_work_queue.discovery.json`에 있습니다.

## 빠른 시작

```bash
cd /Users/boram/hermes-merry-ac-discovery
python3 -m pip install -e ".[dev]"
make verify
```

`uv`를 쓰는 경우 전체 테스트는 아래처럼 실행할 수 있습니다.

```bash
uv run pytest
```

## 로컬 설정

시크릿은 `.env.local`에 넣습니다. 이 파일은 Git에 올라가지 않도록 `.gitignore`에 포함되어 있습니다.

예시 파일에서 시작합니다.

```bash
cp configs/runpod.env.example .env.local
```

전체 체인을 돌리기 위한 최소 설정 예시는 아래와 같습니다.

```bash
STRUCTURED_STORE_BACKEND=sqlite
MOTHER_DB_PATH=/Users/boram/hermes-merry-ac-discovery/tmp/hermes/mother.db
REVIEW_SHEET_ID=your-google-sheet-id
AGENT_WORK_QUEUE_SPEC_PATH=configs/agent_work_queue.discovery.json
AGENT_LOOP_JOBS=agent-work-queue
SMINFO_USER_ID=your-sminfo-id
SMINFO_PASSWORD=your-sminfo-password
THEVC_USER_EMAIL=optional-thevc-email
THEVC_PASSWORD=optional-thevc-password
ANTHROPIC_API_KEY=optional-claude-key
```

다음 파일은 커밋하면 안 됩니다.

- `.env.local`
- 브라우저 세션 파일
- SQLite DB 파일
- `tmp/` 아래 실행 산출물
- Google/Slack/Claude/Runpod 관련 토큰

## 자주 쓰는 명령

체인 큐를 한 번 실행합니다.

```bash
python3 -m merry_runtime.jobs run agent-work-queue
```

장시간 루프를 실행합니다. 운영 환경을 명시적으로 준비했을 때만 사용합니다.

```bash
HERMES_ALLOW_UNBOUNDED_LOOP=1 python3 -m merry_runtime.jobs loop
```

로컬 AIOps 대시보드를 만듭니다.

```bash
python3 -m merry_runtime.jobs render-loop-dashboard --output tmp/hermes/loop-dashboard.html
```

Runpod 비용 스냅샷을 읽습니다. 인프라를 변경하지 않는 read-only 명령입니다.

```bash
scripts/runpod_cost_audit.sh --days 3
```

THE VC 계정을 `.env.local`에 저장합니다. 커밋 대상에는 포함되지 않습니다.

```bash
scripts/save_thevc_credentials.sh
```

## 주요 모듈

```text
src/merry_runtime/
  jobs.py                         CLI 진입점
  runtime_config.py               환경변수 파싱과 잡별 필수 조건 검증
  runtime_factory.py              SQLite/Sheets/Gmail 등 런타임 어댑터 구성
  agent_loop.py                   반복 실행 루프
  job_runner.py                   job 이름을 실제 pipeline 함수로 연결
  loop_dashboard.py               로컬 AIOps 대시보드 렌더러
  schema.py                       SQLite/warehouse 테이블 스키마
  pipelines/
    agent_work_queue.py           체인 큐 실행기
    crawl_sources.py              소스 수집과 후보 기업 추출
    enrich_sminfo.py              SMINFO 큐 처리와 Sheet 반영
  ingestion/
    agent_work_queue.py           체인 task 생성/재시도 helper
    sminfo_queue.py               SMINFO task 정규화/재시도 helper
    thevc.py                      THE VC HTML/텍스트 파서
  adapters/
    sqlite_store.py               SQLite Mother DB 어댑터
    google_sheets.py              Google Sheets 반영 어댑터
    thevc_playwright.py           브라우저 기반 THE VC 어댑터
    sminfo_playwright.py          브라우저 기반 SMINFO 어댑터
```

## 운영자가 확인해야 할 것

밤사이 루프가 “돌았는지”는 커밋 기록만으로 판단하면 안 됩니다. 아래를 확인해야 합니다.

- `agent_runs`: 어떤 job이 언제 시작/종료됐는지, 성공/실패가 무엇인지 확인합니다.
- `agent_work_queue`: 체인 단계가 pending/running/done/failed/blocked 중 어디에 있는지 확인합니다.
- `sminfo_enrichment_queue`: 기업별 SMINFO 조회가 대기/재시도/완료/실패 중 어디에 있는지 확인합니다.
- Google Sheets: 후보 기업과 운영자가 봐야 할 컬럼이 실제로 반영됐는지 확인합니다.
- 로컬 대시보드: 최근 실행 시간, 실패 메시지, 큐 상태를 한 화면에서 확인합니다.

## 문서

- `docs/ONBOARDING.md`: 신규 합류자와 운영자를 위한 상세 구조 설명입니다.
- `docs/SAFETY.md`: 안전장치와 운영 가드레일입니다.
- `docs/runbooks/runpod-staging.md`: Runpod staging 운영 절차입니다.
- `configs/runpod.env.example`: 환경변수 예시입니다.
- `.understand-anything/knowledge-graph.json`: Understand 기반 코드베이스 그래프입니다.

## 현재 상태

현재 `main` 브랜치에는 체인 큐, 육성기업 watchlist 분리, THE VC Playwright 개선, SMINFO 큐 연동, 로컬 AIOps 대시보드, 관련 테스트가 포함되어 있습니다.

다만 “운영 완료”로 보려면 credential이 설정된 staging run을 실제로 수행한 뒤, Sheet 결과, SQLite 큐 상태, dashboard timestamp, 외부 사이트 오류 여부를 함께 확인해야 합니다.
