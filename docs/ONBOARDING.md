# HermesMerry 온보딩

이 문서는 HermesMerry 저장소를 처음 보는 개발자와 운영자가 전체 구조를 빠르게 이해하기 위한 안내서입니다. `/Understand` 그래프와 현재 코드 구조를 기준으로 작성했습니다.

## 먼저 이해해야 할 한 문장

HermesMerry는 “후보 기업 발굴을 위한 큐 기반 운영 시스템”입니다. 공개 소스에서 기업 신호를 수집하고, 후보 기업을 SQLite에 저장하고, SMINFO로 기업 정보를 보강한 뒤, Google Sheets에서 사람이 검토할 수 있도록 보여줍니다.

중요한 점은 HermesMerry가 후보를 최종 결정하는 시스템이 아니라는 것입니다. HermesMerry는 증거 수집, 상태 추적, 반복 작업 자동화, 검토 표면 제공을 맡고, 최종 판단은 사람이 합니다.

## 큰 구조

```text
1. 운영자가 Crawl Sources 또는 설정 파일에 수집 대상을 넣는다.
        |
        v
2. crawl-sources가 공개 소스를 수집한다.
        |
        +--> 원문/신호/후보 기업을 Mother DB에 저장한다.
        |
        +--> SMINFO 조회가 필요한 기업을 sminfo_enrichment_queue에 넣는다.
                  |
                  v
3. enrich-sminfo가 기업별 SMINFO 작업을 처리한다.
                  |
                  +--> sminfo_company_profiles에 구조화 정보를 저장한다.
                  +--> Candidate Detail / SMINFO Queue Sheet에 반영한다.

4. agent_work_queue는 전체 루프를 순서대로 연결한다.
   crawl -> sminfo -> resolve -> score -> sync -> backup
```

## 두 개의 큐

HermesMerry에서 가장 중요한 개념은 큐입니다.

### `agent_work_queue`

전체 작업 순서를 관리하는 체인 큐입니다. 예를 들어 `crawl`이 끝나야 `sminfo`가 실행되고, `sminfo`가 끝나야 `resolve`가 실행되는 식입니다.

이 큐가 필요한 이유는 다음과 같습니다.

- 밤사이 어떤 단계까지 실행됐는지 확인할 수 있습니다.
- 중간 단계가 실패하면 다음 단계로 넘어가지 않게 할 수 있습니다.
- blocked/failed/retry 상태를 명시적으로 남길 수 있습니다.
- 나중에 Dify나 Kafka처럼 “어떤 루프가 어떻게 흘렀는지” 시각화하기 쉽습니다.

체인 정의 파일은 `configs/agent_work_queue.discovery.json`입니다.

### `sminfo_enrichment_queue`

기업별 SMINFO 조회 작업을 관리하는 큐입니다. 전체 체인 중 `sminfo` 단계 안에서 사용됩니다.

이 큐가 필요한 이유는 다음과 같습니다.

- 기업별 조회 성공/실패를 따로 추적할 수 있습니다.
- SMINFO 사이트의 속도 제한과 연결 오류에 대응할 수 있습니다.
- 이미 최근에 조회한 기업은 다시 조회하지 않도록 stale window를 둘 수 있습니다.
- 실패한 기업을 무한 재시도하지 않고 max attempts 이후 failed/blocked로 남길 수 있습니다.

## 주요 파일 설명

- `configs/agent_work_queue.discovery.json`: 전체 체인 순서와 주요 리스크가 정의된 파일입니다.
- `src/merry_runtime/jobs.py`: CLI 진입점입니다. `python3 -m merry_runtime.jobs ...` 명령이 여기로 들어옵니다.
- `src/merry_runtime/runtime_config.py`: `.env.local`과 환경변수를 읽고, job별 필수 설정이 있는지 검증합니다.
- `src/merry_runtime/runtime_factory.py`: SQLite, Google Sheets, Gmail, Slack 등 실제 어댑터를 구성합니다.
- `src/merry_runtime/job_runner.py`: `crawl-sources`, `enrich-sminfo` 같은 job 이름을 실제 함수로 연결합니다.
- `src/merry_runtime/agent_loop.py`: 설정된 job을 주기적으로 반복 실행합니다.
- `src/merry_runtime/pipelines/agent_work_queue.py`: 체인 큐의 task를 lease하고, 성공 시 다음 단계 task를 생성합니다.
- `src/merry_runtime/pipelines/crawl_sources.py`: THE VC, Platum 등 수집 대상을 읽고 후보 기업/뉴스/SMINFO task를 생성합니다.
- `src/merry_runtime/pipelines/enrich_sminfo.py`: SMINFO 큐를 처리하고 SQLite와 Sheet에 결과를 반영합니다.
- `src/merry_runtime/ingestion/sminfo_queue.py`: 기업명 정규화, task id 생성, 재시도 상태 계산을 담당합니다.
- `src/merry_runtime/adapters/thevc_playwright.py`: 브라우저 기반 THE VC 수집 로직입니다.
- `src/merry_runtime/adapters/sminfo_playwright.py`: 브라우저 기반 SMINFO 조회 로직입니다.
- `src/merry_runtime/adapters/sqlite_store.py`: Mother DB의 실제 저장소 구현입니다.
- `src/merry_runtime/adapters/google_sheets.py`: Google Sheets 반영 로직입니다.
- `src/merry_runtime/loop_dashboard.py`: 로컬 AIOps HTML 대시보드 생성기입니다.

## 데이터가 저장되는 곳

- SQLite Mother DB: 운영 상태의 기준 저장소입니다. 후보, 신호, 큐, 실행 이력, SMINFO 결과가 들어갑니다.
- Google Sheets: 사람이 보는 검토/운영 콘솔입니다. source of truth는 SQLite이고, Sheet는 운영 표면에 가깝습니다.
- `tmp/`: 로컬 실행 산출물, dashboard HTML, 임시 DB가 들어갈 수 있습니다. Git에 올리지 않습니다.
- wiki/backup 경로: loop 결과를 사람이 읽기 쉬운 형태로 내보내거나 백업하기 위한 표면입니다.
- 외부 서비스: Gmail draft, Slack 알림, Claude 요약, KVIC 데이터, Runpod runtime은 설정이 있을 때만 사용합니다.

## 루프가 실제로 돌았는지 확인하는 방법

커밋이 있다고 해서 루프가 돈 것은 아닙니다. 프로세스가 시작됐다고 해서 끝까지 성공한 것도 아닙니다. 아래 순서로 확인해야 합니다.

1. `MOTHER_DB_PATH`가 가리키는 SQLite DB가 실제로 존재하는지 확인합니다.
2. `agent_runs` 테이블에서 최근 실행 시간이 있는지 봅니다.
3. `agent_runs.status`와 `error_message`를 봅니다.
4. `agent_work_queue`에서 체인 단계가 어디까지 done인지 확인합니다.
5. `sminfo_enrichment_queue`에서 기업별 SMINFO task가 pending/retry/failed/blocked/done 중 어디에 있는지 확인합니다.
6. Google Sheets의 `Candidate Detail`, `SMINFO Queue`, `Accelerator News` 같은 탭이 갱신됐는지 봅니다.
7. `render-loop-dashboard`로 HTML 대시보드를 만들고 최근 이벤트와 큐 상태를 확인합니다.

대시보드 생성 명령은 아래와 같습니다.

```bash
python3 -m merry_runtime.jobs render-loop-dashboard --output tmp/hermes/loop-dashboard.html
```

## 자주 생기는 장애와 해석

- SMINFO credential 누락: `SMINFO_USER_ID` 또는 `SMINFO_PASSWORD`가 없으면 SMINFO 단계는 진행할 수 없습니다.
- Google Sheet ID 누락: `REVIEW_SHEET_ID`가 없으면 Sheet 반영은 실패하지만 SQLite에는 일부 상태가 남아 있을 수 있습니다.
- THE VC human verification: 로그인 또는 더보기 흐름이 human verification에 막힐 수 있습니다. 이 경우 경고/오류가 남아야 정상입니다.
- 외부 사이트 rate limit: SMINFO나 THE VC가 연결을 끊으면 retry/backoff 상태로 남겨야 합니다.
- 중복 기업명: 기업명 정규화는 의도적으로 보수적입니다. 확신이 낮은 중복은 사람이 볼 수 있게 남기는 쪽이 안전합니다.
- Runpod 비용 증가: 현재 루프는 GPU가 필요하지 않습니다. GPU Pod가 켜져 있으면 비용이 빠르게 쌓일 수 있습니다.

## 개발자가 처음 볼 때 추천 순서

1. `README.md`를 읽고 시스템의 목적과 현재 한계를 파악합니다.
2. `configs/agent_work_queue.discovery.json`에서 전체 체인 순서를 봅니다.
3. `src/merry_runtime/jobs.py`에서 CLI 진입점을 봅니다.
4. `src/merry_runtime/job_runner.py`에서 job 이름과 pipeline 함수 연결을 봅니다.
5. `src/merry_runtime/pipelines/agent_work_queue.py`에서 체인 큐 동작을 봅니다.
6. `src/merry_runtime/pipelines/crawl_sources.py`에서 후보 기업이 어떻게 생기는지 봅니다.
7. `src/merry_runtime/pipelines/enrich_sminfo.py`에서 SMINFO 결과가 어떻게 반영되는지 봅니다.
8. `tests/test_agent_work_queue.py`, `tests/integration/test_crawl_sources.py`, `tests/integration/test_enrich_sminfo.py`로 기대 동작을 확인합니다.

## 운영자가 처음 볼 때 추천 순서

1. `.env.local`에 필요한 계정과 Sheet ID가 있는지 확인합니다.
2. `configs/runpod.env.example`을 보며 staging 환경과 차이를 확인합니다.
3. 작은 배치로 `agent-work-queue`를 한 번 실행합니다.
4. SQLite의 `agent_runs`, `agent_work_queue`, `sminfo_enrichment_queue`를 확인합니다.
5. Google Sheets가 갱신됐는지 확인합니다.
6. dashboard HTML을 렌더링해 최근 실행 시간이 보이는지 확인합니다.
7. 문제가 있으면 큐 상태와 `error_message`를 기준으로 어디서 막혔는지 판단합니다.

## 테스트

전체 테스트:

```bash
uv run pytest
```

현재 큐/대시보드 작업과 직접 관련된 테스트:

```bash
uv run pytest tests/test_agent_work_queue.py tests/test_loop_dashboard.py tests/integration/test_crawl_sources.py tests/integration/test_enrich_sminfo.py
```

문서/Runpod 관련 테스트:

```bash
uv run pytest tests/test_runpod_docs.py
```

## 운영 원칙

- Sheet는 사람이 보는 콘솔이고, 기준 상태는 SQLite에 있습니다.
- 외부 사이트 실패는 숨기지 말고 큐와 실행 로그에 남깁니다.
- 무한 루프를 켜기 전에 작은 배치로 먼저 검증합니다.
- 현재 crawl/sheet/SMINFO 루프에는 GPU가 필요하지 않습니다.
- LLM이 붙더라도 근거 URL과 원천 데이터 없이 판단을 확정하지 않습니다.
- 밤사이 실행 여부는 dashboard timestamp, `agent_runs`, Sheet 결과를 함께 보고 판단합니다.
