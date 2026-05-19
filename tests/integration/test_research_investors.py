from __future__ import annotations

from dataclasses import dataclass, field

from merry_runtime.adapters.fakes import FakeReviewQueue
from merry_runtime.adapters.sqlite_store import SQLiteStructuredStore
from merry_runtime.pipelines.research_investors import INVESTOR_RESEARCH_HEADERS, research_investors


@dataclass(slots=True)
class FakeSearchClient:
    results_by_query: dict[str, list[dict[str, str]]]
    queries: list[str] = field(default_factory=list)

    def search(self, query: str, *, max_results: int) -> list[dict[str, str]]:
        self.queries.append(query)
        return self.results_by_query.get(query, [])[:max_results]


@dataclass(slots=True)
class FakeLLMClient:
    response: dict[str, object]
    prompts: list[dict[str, object]] = field(default_factory=list)

    def complete_json(self, *, system_prompt: str, user_prompt: str, max_tokens: int) -> dict[str, object]:
        self.prompts.append({"system_prompt": system_prompt, "user_prompt": user_prompt, "max_tokens": max_tokens})
        return dict(self.response)


def test_research_investors_uses_claude_as_evidence_encoder_and_updates_investor_db(tmp_path) -> None:
    store = SQLiteStructuredStore(db_path=tmp_path / "mother.db")
    review_queue = FakeReviewQueue()
    store.upsert_rows(
        table="kvic_investor_managers",
        rows=[
            {
                "manager_id": "kvic_mgr_mysc",
                "manager_name": "엠와이소셜컴퍼니",
                "total_fund_count": 3,
                "active_fund_count": 3,
                "total_amount_eok": 180.0,
                "active_amount_eok": 180.0,
                "total_commitment_eok": 57.0,
                "active_commitment_eok": 57.0,
                "fund_fields": ["사회적기업", "지방기업"],
                "representative_funds": [
                    "엑스트라마일 임팩트 6호 벤처투자조합",
                    "엑스트라마일 임팩트 5호 벤처투자조합",
                ],
                "profile_tags": ["impact", "local_regional"],
                "latest_fund_year": 2023,
                "next_expiry_at": "2027-02-24",
                "latest_expiry_at": "2031-11-12",
                "collected_at": "2026-05-19T09:00:00+09:00",
            }
        ],
        key_fields=("manager_id",),
    )
    search_client = FakeSearchClient(
        results_by_query={
            "MYSC AUM 운용자산": [
                {
                    "title": "MYSC 임팩트 투자조합 소개",
                    "url": "https://example.com/mysc-aum",
                    "snippet": "MYSC는 누적 운영 투자조합 20개, AUM 1,107억 원 규모의 임팩트 투자사다.",
                }
            ]
        }
    )
    llm_client = FakeLLMClient(
        response={
            "status": "success",
            "external_aum_eok": 1107,
            "external_fund_count": 20,
            "external_cumulative_investment_eok": 910,
            "description": "누적 운영 투자조합 20개, AUM 1,107억 원 규모의 임팩트 투자사.",
            "evidence_title": "MYSC 임팩트 투자조합 소개",
            "evidence_url": "https://example.com/mysc-aum",
            "confidence": 0.86,
        }
    )

    result = research_investors(
        structured_store=store,
        review_queue=review_queue,
        search_client=search_client,
        llm_client=llm_client,
        collected_at="2026-05-19T18:20:00+09:00",
        batch_limit=10,
        stale_days=7,
        search_max_results=5,
    )

    assert result.status == "success"
    assert result.researched_count == 1
    assert search_client.queries == ["MYSC AUM 운용자산"]
    assert "AUM 1,107억" in str(llm_client.prompts[0]["user_prompt"])
    [profile] = store.query_rows(sql="select * from investor_external_profiles", parameters={})
    assert profile["manager_id"] == "kvic_mgr_mysc"
    assert profile["manager_name"] == "엠와이소셜컴퍼니"
    assert profile["external_aum_eok"] == 1107.0
    assert profile["external_fund_count"] == 20
    assert profile["external_cumulative_investment_eok"] == 910.0
    assert profile["status"] == "success"
    assert profile["evidence_url"] == "https://example.com/mysc-aum"
    assert profile["confidence"] == 0.86
    assert review_queue.replaced_headers["Investor DB"] == INVESTOR_RESEARCH_HEADERS
    [sheet_row] = review_queue.published["Investor DB"]
    assert sheet_row["투자사"] == "엠와이소셜컴퍼니"
    assert sheet_row["KVIC 공개 활성 운용액(억원)"] == 180.0
    assert sheet_row["외부 공개 AUM(억원)"] == 1107.0
    assert sheet_row["외부 공개 운용 조합 수"] == 20
    assert sheet_row["AUM 근거 URL"] == "https://example.com/mysc-aum"


def test_research_investors_records_no_result_without_search_evidence(tmp_path) -> None:
    store = SQLiteStructuredStore(db_path=tmp_path / "mother.db")
    store.upsert_rows(
        table="kvic_investor_managers",
        rows=[
            {
                "manager_id": "kvic_mgr_empty",
                "manager_name": "무근거벤처스",
                "total_fund_count": 1,
                "active_fund_count": 1,
                "total_amount_eok": 10.0,
                "active_amount_eok": 10.0,
                "total_commitment_eok": 5.0,
                "active_commitment_eok": 5.0,
                "fund_fields": [],
                "representative_funds": ["무근거 투자조합"],
                "profile_tags": [],
                "latest_fund_year": 2024,
                "next_expiry_at": "2032-01-01",
                "latest_expiry_at": "2032-01-01",
                "collected_at": "2026-05-19T09:00:00+09:00",
            }
        ],
        key_fields=("manager_id",),
    )
    llm_client = FakeLLMClient(response={"status": "success"})

    result = research_investors(
        structured_store=store,
        search_client=FakeSearchClient(results_by_query={}),
        llm_client=llm_client,
        collected_at="2026-05-19T18:20:00+09:00",
        batch_limit=10,
    )

    assert result.researched_count == 1
    assert llm_client.prompts == []
    [profile] = store.query_rows(sql="select * from investor_external_profiles", parameters={})
    assert profile["status"] == "no_result"
    assert profile["external_aum_eok"] == 0.0
    assert profile["evidence_url"] == ""
