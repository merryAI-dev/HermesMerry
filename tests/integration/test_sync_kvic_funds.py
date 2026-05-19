from dataclasses import dataclass
from typing import Any

from merry_runtime.adapters.fakes import FakeReviewQueue
from merry_runtime.adapters.sqlite_store import SQLiteStructuredStore
from merry_runtime.pipelines.sync_kvic_funds import INVESTOR_DB_HEADERS, sync_kvic_funds


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

    assert review_queue.replaced_headers["Investor DB"] == INVESTOR_DB_HEADERS
    assert review_queue.published["Investor DB"] == [
        {
            "투자사": "디쓰리쥬빌리파트너스",
            "활성 펀드 수": 2,
            "전체 펀드 수": 2,
            "활성 운용액(억원)": 435.0,
            "활성 약정액(억원)": 270.0,
            "출자 분야": "미래환경산업, 소셜임팩트",
            "대표 펀드": "디쓰리 미래환경 ECO 벤처투자조합, D3 임팩트 벤처투자조합 제1호",
            "프로필 태그": "climate_environment, impact",
            "다음 만기일": "2026-08-16",
            "최종 만기일": "2029-08-25",
            "수집시각": "2026-05-19T16:00:00+09:00",
        }
    ]


def test_sync_kvic_funds_skips_when_latest_success_is_fresher_than_daily_interval(tmp_path) -> None:
    store = SQLiteStructuredStore(db_path=tmp_path / "mother.db")
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
    client = FakeKVICClient(fund_types_payload={"result": []}, funds_payload={"result_11": []})

    result = sync_kvic_funds(
        structured_store=store,
        client=client,
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
