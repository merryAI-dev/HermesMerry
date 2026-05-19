from dataclasses import dataclass
from typing import Any

from merry_runtime.adapters.fakes import FakeReviewQueue
from merry_runtime.adapters.sqlite_store import SQLiteStructuredStore
from merry_runtime.pipelines.research_investors import INVESTOR_RESEARCH_HEADERS
from merry_runtime.pipelines.sync_kvic_funds import (
    FUND_DB_HEADERS,
    _needs_description_refresh,
    sync_kvic_funds,
)


@dataclass(slots=True)
class FakeKVICClient:
    fund_types_payload: dict[str, Any]
    funds_payload: dict[str, Any]
    fund_fetch_count: int = 0

    def fetch_fund_types(self, *, b_type: str = "0", output_format: str = "1") -> dict[str, Any]:
        return self.fund_types_payload

    def fetch_funds(self, *, fund_type: str = "00", output_format: str = "1") -> dict[str, Any]:
        self.fund_fetch_count += 1
        return self.funds_payload


@dataclass(slots=True)
class FakeSearchClient:
    results_by_query: dict[str, list[dict[str, str]]]
    queries: list[str]

    def search(self, query: str, *, max_results: int) -> list[dict[str, str]]:
        self.queries.append(query)
        return self.results_by_query.get(query, [])[:max_results]


def test_sync_kvic_funds_upserts_funds_profiles_state_and_investor_sheet(tmp_path) -> None:
    store = SQLiteStructuredStore(db_path=tmp_path / "mother.db")
    review_queue = FakeReviewQueue()
    client = FakeKVICClient(
        fund_types_payload={"result": [{"fundCode": "11", "fundName": "한국모태펀드"}]},
        funds_payload={
            "result_11": [
                {
                    "year": "2021년",
                    "fd": "미래환경산업",
                    "mng": "디쓰리쥬빌리파트너스",
                    "asn": "디쓰리 미래환경 ECO 벤처투자조합",
                    "exp": "2029-08-25",
                    "amt": "28500",
                    "ca": "15000",
                },
                {
                    "year": "2018년",
                    "fd": "소셜임팩트",
                    "mng": "디쓰리쥬빌리파트너스",
                    "asn": "D3 임팩트 벤처투자조합 제1호",
                    "exp": "2026-08-16",
                    "amt": "15000",
                    "ca": "12000",
                },
            ]
        },
    )

    result = sync_kvic_funds(
        structured_store=store,
        client=client,
        review_queue=review_queue,
        reference_date="2026-05-19",
        collected_at="2026-05-19T16:00:00+09:00",
        sync_interval_seconds=86400,
    )

    assert result.status == "success"
    assert result.fund_type_count == 1
    assert result.fund_count == 2
    assert result.manager_count == 1
    assert client.fund_fetch_count == 1

    [fund_type] = store.query_rows(sql="select * from kvic_fund_types", parameters={})
    assert fund_type["fund_code"] == "11"
    funds = store.query_rows(sql="select * from kvic_funds", parameters={})
    assert len(funds) == 2
    assert funds[0]["manager_name"] == "디쓰리쥬빌리파트너스"
    [profile] = store.query_rows(sql="select * from kvic_investor_managers", parameters={})
    assert profile["active_fund_count"] == 2
    assert profile["fund_fields"] == ["미래환경산업", "소셜임팩트"]
    [state] = store.query_rows(sql="select * from kvic_sync_state", parameters={})
    assert state["state_key"] == "fund_snapshot"
    assert state["status"] == "success"
    assert state["fund_count"] == 2
    assert state["manager_count"] == 1

    assert review_queue.replaced_headers["Investor DB"] == INVESTOR_RESEARCH_HEADERS
    assert review_queue.published["Investor DB"] == [
        {
            "투자사": "디쓰리쥬빌리파트너스",
            "KVIC 공개 활성 펀드 수": 2,
            "KVIC 공개 전체 펀드 수": 2,
            "KVIC 공개 활성 운용액(억원)": 435.0,
            "KVIC 공개 활성 약정액(억원)": 270.0,
            "외부 공개 AUM(억원)": "",
            "외부 공개 운용 조합 수": "",
            "외부 공개 누적 투자액(억원)": "",
            "AUM 설명": "",
            "AUM 근거 제목": "",
            "AUM 근거 URL": "",
            "AUM 신뢰도": "",
            "AUM 상태": "",
            "출자 분야": "미래환경산업, 소셜임팩트",
            "대표 펀드": "디쓰리 미래환경 ECO 벤처투자조합, D3 임팩트 벤처투자조합 제1호",
            "프로필 태그": "climate_environment, impact",
            "다음 만기일": "2026-08-16",
            "최종 만기일": "2029-08-25",
            "수집시각": "2026-05-19T16:00:00+09:00",
        }
    ]
    assert review_queue.replaced_headers["Fund DB"] == FUND_DB_HEADERS
    assert review_queue.published["Fund DB"][0]["펀드명"] == "디쓰리 미래환경 ECO 벤처투자조합"
    assert review_queue.published["Fund DB"][0]["운용사"] == "디쓰리쥬빌리파트너스"
    assert review_queue.published["Fund DB"][0]["펀드종류"] == "한국모태펀드"
    assert review_queue.published["Fund DB"][0]["출자분야"] == "미래환경산업"
    assert review_queue.published["Fund DB"][0]["운영상태"] == "활성"
    assert review_queue.published["Fund DB"][0]["펀드규모(억원)"] == 285.0
    assert review_queue.published["Fund DB"][0]["약정액(억원)"] == 150.0


def test_sync_kvic_funds_enriches_fund_db_with_web_search_descriptions(tmp_path) -> None:
    store = SQLiteStructuredStore(db_path=tmp_path / "mother.db")
    review_queue = FakeReviewQueue()
    client = FakeKVICClient(
        fund_types_payload={"result": [{"fundCode": "11", "fundName": "한국모태펀드"}]},
        funds_payload={
            "result_11": [
                {
                    "year": "2024",
                    "fd": "미래환경산업",
                    "mng": "디쓰리쥬빌리파트너스",
                    "asn": "디쓰리 미래환경 ECO 벤처투자조합",
                    "exp": "2032-08-25",
                    "amt": "28500",
                    "ca": "15000",
                }
            ]
        },
    )
    search_client = FakeSearchClient(
        queries=[],
        results_by_query={
            "\"디쓰리 미래환경 ECO 벤처투자조합\" \"디쓰리쥬빌리파트너스\" 미래환경산업": [
                {
                    "title": "디쓰리 미래환경 ECO 벤처투자조합 결성",
                    "url": "https://example.com/d3-eco",
                    "snippet": "디쓰리쥬빌리파트너스가 운용하는 디쓰리 미래환경 ECO 벤처투자조합은 미래환경산업과 기후 기술 기업에 투자하는 펀드다.",
                }
            ]
        },
    )

    sync_kvic_funds(
        structured_store=store,
        client=client,
        review_queue=review_queue,
        search_client=search_client,
        reference_date="2026-05-19",
        collected_at="2026-05-19T16:00:00+09:00",
        sync_interval_seconds=86400,
        fund_description_batch_limit=10,
        fund_search_max_results=5,
    )

    [description] = store.query_rows(sql="select * from kvic_fund_descriptions", parameters={})
    assert description["status"] == "success"
    assert description["source_title"] == "디쓰리 미래환경 ECO 벤처투자조합 결성"
    assert description["source_url"] == "https://example.com/d3-eco"
    assert "기후 기술 기업에 투자" in str(description["description"])
    [fund_row] = review_queue.published["Fund DB"]
    assert fund_row["펀드 설명"] == description["description"]
    assert fund_row["설명 근거 URL"] == "https://example.com/d3-eco"
    assert fund_row["설명 상태"] == "success"
    assert fund_row["검색어"] == search_client.queries[0]


def test_sync_kvic_funds_records_no_result_when_search_evidence_does_not_match(tmp_path) -> None:
    store = SQLiteStructuredStore(db_path=tmp_path / "mother.db")
    client = FakeKVICClient(
        fund_types_payload={"result": [{"fundCode": "11", "fundName": "한국모태펀드"}]},
        funds_payload={
            "result_11": [
                {
                    "year": "2024",
                    "fd": "바이오",
                    "mng": "메리벤처스",
                    "asn": "메리 바이오 투자조합",
                    "exp": "2032-01-01",
                    "amt": "10000",
                    "ca": "7000",
                }
            ]
        },
    )
    search_client = FakeSearchClient(
        queries=[],
        results_by_query={
            "\"메리 바이오 투자조합\" \"메리벤처스\" 바이오": [
                {"title": "무관한 뉴스", "url": "https://example.com/noise", "snippet": "다른 회사의 일반 기사"}
            ]
        },
    )

    sync_kvic_funds(
        structured_store=store,
        client=client,
        search_client=search_client,
        reference_date="2026-05-19",
        collected_at="2026-05-19T16:00:00+09:00",
        fund_description_batch_limit=10,
    )

    [description] = store.query_rows(sql="select * from kvic_fund_descriptions", parameters={})
    assert description["status"] == "no_result"
    assert description["description"] == "메리 바이오 투자조합은 메리벤처스가 운용하는 바이오 분야 펀드입니다 (펀드규모 100.0억원, 약정액 70.0억원, 만기 2032-01-01)."
    assert description["source_url"] == ""


def test_unsuccessful_kvic_fund_descriptions_retry_daily_before_success_stale_window() -> None:
    assert not _needs_description_refresh(
        {"status": "success", "updated_at": "2026-05-01T00:00:00+09:00"},
        collected_at="2026-05-20T00:00:00+09:00",
        stale_days=30,
    )
    assert not _needs_description_refresh(
        {"status": "no_result", "updated_at": "2026-05-19T12:00:00+09:00"},
        collected_at="2026-05-19T18:00:00+09:00",
        stale_days=30,
    )
    assert _needs_description_refresh(
        {"status": "no_result", "updated_at": "2026-05-19T00:00:00+09:00"},
        collected_at="2026-05-20T00:00:00+09:00",
        stale_days=30,
    )
    assert _needs_description_refresh(
        {"status": "error", "updated_at": "2026-05-19T00:00:00+09:00"},
        collected_at="2026-05-20T00:00:00+09:00",
        stale_days=30,
    )


def test_sync_kvic_funds_skips_when_latest_success_is_fresher_than_daily_interval(tmp_path) -> None:
    store = SQLiteStructuredStore(db_path=tmp_path / "mother.db")
    review_queue = FakeReviewQueue()
    store.upsert_rows(
        table="kvic_sync_state",
        rows=[
            {
                "state_key": "fund_snapshot",
                "latest_success_at": "2026-05-19T09:00:00+09:00",
                "status": "success",
                "fund_type_count": 1,
                "fund_count": 2,
                "manager_count": 1,
                "skipped_reason": "",
                "updated_at": "2026-05-19T09:00:00+09:00",
            }
        ],
        key_fields=("state_key",),
    )
    store.upsert_rows(
        table="kvic_fund_types",
        rows=[
            {
                "fund_code": "11",
                "fund_name": "한국모태펀드",
                "source_url": "https://www.kvic.or.kr/api/businessType",
                "collected_at": "2026-05-19T09:00:00+09:00",
            }
        ],
        key_fields=("fund_code",),
    )
    store.upsert_rows(
        table="kvic_funds",
        rows=[
            {
                "fund_id": "kvic_fund_existing",
                "fund_type_code": "11",
                "year_label": "2021년",
                "fund_year": 2021,
                "field_name": "미래환경산업",
                "manager_name": "디쓰리쥬빌리파트너스",
                "association_name": "디쓰리 미래환경 ECO 벤처투자조합",
                "expires_at": "2029-08-25",
                "amount_raw": "28500",
                "commitment_raw": "15000",
                "amount_eok": 285.0,
                "commitment_eok": 150.0,
                "is_active": True,
                "source_url": "https://www.kvic.or.kr/api/fundType",
                "raw_json": "{}",
                "collected_at": "2026-05-19T09:00:00+09:00",
            }
        ],
        key_fields=("fund_id",),
    )
    store.upsert_rows(
        table="kvic_investor_managers",
        rows=[
            {
                "manager_id": "kvic_mgr_d3",
                "manager_name": "디쓰리쥬빌리파트너스",
                "total_fund_count": 1,
                "active_fund_count": 1,
                "total_amount_eok": 285.0,
                "active_amount_eok": 285.0,
                "total_commitment_eok": 150.0,
                "active_commitment_eok": 150.0,
                "fund_fields": ["미래환경산업"],
                "representative_funds": ["디쓰리 미래환경 ECO 벤처투자조합"],
                "profile_tags": ["climate_environment"],
                "latest_fund_year": 2021,
                "next_expiry_at": "2029-08-25",
                "latest_expiry_at": "2029-08-25",
                "collected_at": "2026-05-19T09:00:00+09:00",
            }
        ],
        key_fields=("manager_id",),
    )
    client = FakeKVICClient(fund_types_payload={"result": []}, funds_payload={"result_11": []})

    result = sync_kvic_funds(
        structured_store=store,
        client=client,
        review_queue=review_queue,
        reference_date="2026-05-19",
        collected_at="2026-05-19T16:00:00+09:00",
        sync_interval_seconds=86400,
    )

    assert result.status == "skipped"
    assert result.skipped_reason == "fresh_snapshot"
    assert client.fund_fetch_count == 0
    [state] = store.query_rows(sql="select * from kvic_sync_state", parameters={})
    assert state["status"] == "skipped"
    assert state["fund_count"] == 2
    assert review_queue.replaced_headers["Fund DB"] == FUND_DB_HEADERS
    assert review_queue.published["Fund DB"][0]["펀드명"] == "디쓰리 미래환경 ECO 벤처투자조합"


def test_sync_kvic_funds_enriches_descriptions_even_when_snapshot_is_fresh(tmp_path) -> None:
    store = SQLiteStructuredStore(db_path=tmp_path / "mother.db")
    review_queue = FakeReviewQueue()
    store.upsert_rows(
        table="kvic_sync_state",
        rows=[
            {
                "state_key": "fund_snapshot",
                "latest_success_at": "2026-05-19T09:00:00+09:00",
                "status": "success",
                "fund_type_count": 1,
                "fund_count": 1,
                "manager_count": 1,
                "skipped_reason": "",
                "updated_at": "2026-05-19T09:00:00+09:00",
            }
        ],
        key_fields=("state_key",),
    )
    store.upsert_rows(
        table="kvic_fund_types",
        rows=[
            {
                "fund_code": "11",
                "fund_name": "한국모태펀드",
                "source_url": "https://www.kvic.or.kr/api/businessType",
                "collected_at": "2026-05-19T09:00:00+09:00",
            }
        ],
        key_fields=("fund_code",),
    )
    store.upsert_rows(
        table="kvic_funds",
        rows=[
            {
                "fund_id": "kvic_fund_existing",
                "fund_type_code": "11",
                "year_label": "2024",
                "fund_year": 2024,
                "field_name": "소셜임팩트",
                "manager_name": "옐로우독",
                "association_name": "옐로우독 같이하다 투자조합",
                "expires_at": "2032-07-10",
                "amount_raw": "20200",
                "commitment_raw": "16000",
                "amount_eok": 202.0,
                "commitment_eok": 160.0,
                "is_active": True,
                "source_url": "https://www.kvic.or.kr/api/fundType",
                "raw_json": "{}",
                "collected_at": "2026-05-19T09:00:00+09:00",
            }
        ],
        key_fields=("fund_id",),
    )
    store.upsert_rows(
        table="kvic_investor_managers",
        rows=[
            {
                "manager_id": "kvic_mgr_yellowdog",
                "manager_name": "옐로우독",
                "total_fund_count": 1,
                "active_fund_count": 1,
                "total_amount_eok": 202.0,
                "active_amount_eok": 202.0,
                "total_commitment_eok": 160.0,
                "active_commitment_eok": 160.0,
                "fund_fields": ["소셜임팩트"],
                "representative_funds": ["옐로우독 같이하다 투자조합"],
                "profile_tags": ["impact"],
                "latest_fund_year": 2024,
                "next_expiry_at": "2032-07-10",
                "latest_expiry_at": "2032-07-10",
                "collected_at": "2026-05-19T09:00:00+09:00",
            }
        ],
        key_fields=("manager_id",),
    )
    search_client = FakeSearchClient(
        queries=[],
        results_by_query={
            "\"옐로우독 같이하다 투자조합\" \"옐로우독\" 소셜임팩트": [
                {
                    "title": "옐로우독 같이하다 투자조합 운용",
                    "url": "https://example.com/yellowdog-impact",
                    "snippet": "옐로우독 같이하다 투자조합은 소셜임팩트 스타트업에 투자하는 펀드다.",
                }
            ]
        },
    )
    client = FakeKVICClient(fund_types_payload={"result": []}, funds_payload={})

    result = sync_kvic_funds(
        structured_store=store,
        client=client,
        review_queue=review_queue,
        search_client=search_client,
        collected_at="2026-05-19T16:00:00+09:00",
        sync_interval_seconds=86400,
        fund_description_batch_limit=10,
        fund_search_max_results=5,
    )

    assert result.status == "skipped"
    assert result.described_fund_count == 1
    assert client.fund_fetch_count == 0
    [description] = store.query_rows(sql="select * from kvic_fund_descriptions", parameters={})
    assert description["status"] == "success"
    assert description["source_url"] == "https://example.com/yellowdog-impact"
    [fund_row] = review_queue.published["Fund DB"]
    assert fund_row["펀드 설명"] == description["description"]
    assert fund_row["설명 상태"] == "success"
