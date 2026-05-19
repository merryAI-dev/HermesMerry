from datetime import UTC, datetime, timedelta

from merry_runtime.adapters.fakes import FakeReviewQueue, FakeStructuredStore
from merry_runtime.ingestion.sminfo import SminfoProfile
from merry_runtime.pipelines.enrich_sminfo import enrich_sminfo_candidates


class FakeSminfoClient:
    def __init__(self) -> None:
        self.seen: list[tuple[str, dict[str, str]]] = []
        self.closed = False

    def lookup_company(self, *, company_name: str, candidate: dict[str, str]) -> SminfoProfile:
        self.seen.append((company_name, dict(candidate)))
        return SminfoProfile(
            requested_company=company_name,
            match_status="matched",
            matched_company="(주)에이아이오",
            representative="권진형",
            company_type="법인 또는 기타사업자",
            established_at="2011-05-13",
            road_address="경기 용인시 수지구 신수로 767",
            homepage="www.the-aio.com",
            main_products="낸드 플래시 컨트롤러 F/W 설계 등",
            standard_industry="전기용 기계·장비 및 관련 기자재 도매업",
            info_updated_at="2026-05-18",
            latest_financial_year="2025-12-31",
            revenue_krw_thousand="17851006",
            operating_income_krw_thousand="-13097004",
            net_income_krw_thousand="-19903884",
            total_assets_krw_thousand="27096382",
            shareholder_composition="권진형 52.00% (52,000주); 백상열 48.00% (48,000주)",
            largest_shareholder="권진형",
            largest_shareholder_ratio_pct="52.00",
            shareholder_count="2",
            sminfo_url="https://sminfo.mss.go.kr/si/ei/IEI001R0.do?cmd=com&kcd=0007451769",
        )

    def close(self) -> None:
        self.closed = True


def test_enrich_sminfo_candidates_persists_profile_to_sqlite_projection_and_sheet() -> None:
    queue = FakeReviewQueue()
    queue.seed_reviews(
        "Candidate Detail",
        [
            {
                "company": "에이아이오",
                "normalized_name": "에이아이오",
                "representative": "권진형∙백상열",
                "homepage": "https://the-aio.com/",
                "region": "경기 용인시",
            }
        ],
    )
    store = FakeStructuredStore()
    client = FakeSminfoClient()
    slept: list[int] = []

    result = enrich_sminfo_candidates(
        review_queue=queue,
        structured_store=store,
        client=client,
        max_items=1,
        min_interval_seconds=35,
        sleep_fn=lambda seconds: slept.append(seconds),
        run_id="run_sminfo_test",
    )

    assert result.processed_count == 1
    assert result.matched_count == 1
    assert slept == []
    assert client.seen[0][0] == "에이아이오"
    assert client.closed is True

    [profile_row] = store.tables["sminfo_company_profiles"]
    assert profile_row["requested_company"] == "에이아이오"
    assert profile_row["matched_company"] == "(주)에이아이오"
    assert profile_row["revenue_krw_thousand"] == "17851006"

    [sheet_row] = queue.published["SMINFO Enrichment"]
    assert sheet_row["requested_company"] == "에이아이오"
    assert sheet_row["match_status"] == "matched"
    assert sheet_row["sminfo_url"].endswith("0007451769")

    [candidate_update] = queue.published["Candidate Detail"]
    assert candidate_update["company"] == "에이아이오"
    assert candidate_update["homepage"] == "https://the-aio.com/"
    assert candidate_update["sminfo_status"] == "matched"
    assert candidate_update["sminfo_company"] == "(주)에이아이오"
    assert candidate_update["sminfo_latest_financial_year"] == "2025-12-31"
    assert candidate_update["sminfo_revenue_krw_thousand"] == "17851006"
    assert candidate_update["sminfo_shareholder_composition"] == "권진형 52.00% (52,000주); 백상열 48.00% (48,000주)"
    assert candidate_update["sminfo_largest_shareholder"] == "권진형"
    assert candidate_update["sminfo_largest_shareholder_ratio_pct"] == "52.00"
    assert candidate_update["sminfo_profile_url"].endswith("0007451769")


def test_enrich_sminfo_candidates_respects_rate_limit_between_multiple_candidates() -> None:
    queue = FakeReviewQueue()
    queue.seed_reviews(
        "Candidate Detail",
        [
            {"company": "에이아이오", "representative": "권진형"},
            {"company": "바이트랩", "representative": "조용훈"},
        ],
    )
    store = FakeStructuredStore()
    client = FakeSminfoClient()
    slept: list[int] = []

    enrich_sminfo_candidates(
        review_queue=queue,
        structured_store=store,
        client=client,
        max_items=2,
        min_interval_seconds=35,
        sleep_fn=lambda seconds: slept.append(seconds),
        run_id="run_sminfo_rate",
    )

    assert [item[0] for item in client.seen] == ["에이아이오", "바이트랩"]
    assert slept == [35]


def test_enrich_sminfo_candidates_skips_fresh_terminal_profiles() -> None:
    queue = FakeReviewQueue()
    queue.seed_reviews(
        "Candidate Detail",
        [
            {
                "company": "에이아이오",
                "sminfo_status": "matched",
                "sminfo_collected_at": datetime.now(UTC).isoformat(),
            }
        ],
    )
    store = FakeStructuredStore()
    client = FakeSminfoClient()

    result = enrich_sminfo_candidates(
        review_queue=queue,
        structured_store=store,
        client=client,
        max_items=1,
        min_interval_seconds=35,
        stale_days=30,
        run_id="run_sminfo_fresh_skip",
    )

    assert result.processed_count == 0
    assert client.seen == []


def test_enrich_sminfo_candidates_skips_header_placeholder_company_rows() -> None:
    queue = FakeReviewQueue()
    queue.seed_reviews(
        "Candidate Detail",
        [
            {"company": "기업명", "homepage": ""},
            {"company": "에이아이오", "representative": "권진형"},
        ],
    )
    store = FakeStructuredStore()
    client = FakeSminfoClient()

    result = enrich_sminfo_candidates(
        review_queue=queue,
        structured_store=store,
        client=client,
        max_items=1,
        min_interval_seconds=35,
        run_id="run_sminfo_skip_placeholder",
    )

    assert result.processed_count == 1
    assert client.seen[0][0] == "에이아이오"


def test_enrich_sminfo_candidates_rechecks_stale_terminal_profiles() -> None:
    queue = FakeReviewQueue()
    queue.seed_reviews(
        "Candidate Detail",
        [
            {
                "company": "에이아이오",
                "sminfo_status": "not_found",
                "sminfo_collected_at": (datetime.now(UTC) - timedelta(days=31)).isoformat(),
            }
        ],
    )
    store = FakeStructuredStore()
    client = FakeSminfoClient()

    result = enrich_sminfo_candidates(
        review_queue=queue,
        structured_store=store,
        client=client,
        max_items=1,
        min_interval_seconds=35,
        stale_days=30,
        run_id="run_sminfo_stale_recheck",
    )

    assert result.processed_count == 1
    assert [item[0] for item in client.seen] == ["에이아이오"]


def test_enrich_sminfo_candidates_caps_batch_to_twenty_even_when_misconfigured() -> None:
    queue = FakeReviewQueue()
    queue.seed_reviews("Candidate Detail", [{"company": f"기업{i}"} for i in range(25)])
    store = FakeStructuredStore()
    client = FakeSminfoClient()

    result = enrich_sminfo_candidates(
        review_queue=queue,
        structured_store=store,
        client=client,
        max_items=1000,
        min_interval_seconds=0,
        run_id="run_sminfo_batch_cap",
    )

    assert result.processed_count == 20
    assert len(client.seen) == 20
