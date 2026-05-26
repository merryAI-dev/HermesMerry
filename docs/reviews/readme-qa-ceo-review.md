# README QA 및 CEO Review

검토일: 2026-05-26

검토 범위:

- `README.md`
- `docs/ONBOARDING.md`

## QA 결과

결론: 통과. 단, 실제 운영 완료를 주장하지 않도록 조건과 리스크를 명시해야 합니다.

README는 현재 구현된 기능과 아직 조건부인 통합을 분리해서 설명합니다. 특히 “완성된 자동 의사결정 시스템”이나 “밤사이 실제 운영이 검증된 시스템”처럼 읽히지 않도록, credential 기반 staging 검증이 필요하다는 문장을 남겼습니다.

코드 기준으로 확인한 내용은 다음과 같습니다.

- `agent_work_queue` 체인은 `src/merry_runtime/pipelines/agent_work_queue.py`와 `configs/agent_work_queue.discovery.json`에 구현되어 있습니다.
- SMINFO 큐 동작은 `src/merry_runtime/pipelines/enrich_sminfo.py`, `src/merry_runtime/ingestion/sminfo_queue.py`, integration test에 반영되어 있습니다.
- THE VC Playwright 기반 수집 로직은 `src/merry_runtime/adapters/thevc_playwright.py`에 있습니다.
- 로컬 AIOps 대시보드 렌더링은 `src/merry_runtime/loop_dashboard.py`에 있습니다.
- Gmail은 자동 발송이 아니라 draft 생성으로 설명되어 있으며, 현재 안전 경계와 맞습니다.

남은 리스크는 다음과 같습니다.

- Google Sheets, SMINFO, THE VC는 실제 계정과 권한이 들어간 staging run으로 검증해야 합니다.
- 공개 소스 사이트는 구조가 바뀔 수 있습니다.
- THE VC human verification은 코드만으로 항상 우회할 수 있는 문제가 아닙니다.
- Runpod 장시간 실행은 비용을 만들 수 있으므로 CPU-first, finite batch 검증이 먼저입니다.
- `uv.lock`은 아직 커밋하지 않았습니다. 프로젝트가 lockfile을 버전 관리하기로 정하면 별도 커밋으로 다루는 편이 좋습니다.

## CEO Review 결과

결론: 비개발자 대상 설명으로 읽을 수 있는 수준입니다. 다만 임원 보고에서는 “AI 자동화”보다 “증거 기반 발굴 운영 체계”로 설명하는 것이 정확합니다.

비개발자가 이해해야 하는 핵심 메시지는 네 가지입니다.

- 왜 필요한가: 후보 기업 발굴과 모니터링이 수작업으로 흩어져 있기 때문입니다.
- 무엇을 해주는가: 공개 신호 수집, 후보 기업 저장, SMINFO 보강, Sheet 반영, 실행 상태 시각화를 해줍니다.
- 무엇을 아직 보장하지 않는가: 외부 사이트 로그인, credential 설정, 실제 staging run 성공은 별도 검증이 필요합니다.
- 어디를 보면 되는가: Sheet, dashboard, `agent_runs`, queue 상태를 보면 됩니다.

임원진에게는 아래 표현이 가장 안전합니다.

> HermesMerry는 액셀러레이터 후보 기업 발굴을 자동 의사결정으로 대체하는 시스템이 아니라, 공개 근거와 기업 정보를 모아 사람이 검토 가능한 상태로 정리하는 운영 자동화 기반입니다. 현재는 큐, SMINFO 보강, Sheet 반영, 대시보드까지 구현되어 있으며, 실제 운영 전에는 credential이 설정된 staging run으로 결과를 확인해야 합니다.

## 과장 방지 기준

문서에서 피해야 할 표현:

- “완전 자동”
- “운영 검증 완료”
- “모든 후보를 정확히 판별”
- “THE VC/SMINFO를 항상 안정적으로 수집”
- “GPU/LLM으로 판단 정확도 보장”

대신 사용할 표현:

- “증거 기반”
- “운영자가 검토 가능한 상태로 정리”
- “credential 설정 시 동작”
- “외부 사이트 상태에 따라 경고/오류 기록”
- “staging run 검증 필요”
