from datetime import UTC, datetime, timedelta

from merry_runtime.adapters.fakes import FakeReviewQueue, FakeStructuredStore
from merry_runtime.ingestion.sminfo import SminfoProfile
from merry_runtime.ingestion.sminfo_queue import build_sminfo_task
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


class StoreCheckingSminfoClient(FakeSminfoClient):
    def __init__(self, store: FakeStructuredStore, task_id: str) -> None:
        super().__init__()
        self.store = store
        self.task_id = task_id

    def lookup_company(self, *, company_name: str, candidate: dict[str, str]) -> SminfoProfile:
        [task] = [row for row in self.store.tables["sminfo_enrichment_queue"] if row["task_id"] == self.task_id]
        assert task["status"] == "running"
        assert task["locked_by"] == "agent-test"
        assert task["locked_at"]
        return super().lookup_company(company_name=company_name, candidate=candidate)


class FailingSminfoClient:
    def __init__(self) -> None:
        self.closed = False

    def lookup_company(self, *, company_name: str, candidate: dict[str, str]) -> SminfoProfile:
        raise RuntimeError("connection reset")

    def close(self) -> None:
        self.closed = True


class FailingSheetProjectionQueue(FakeReviewQueue):
    def upsert_cards(self, *, sheet_tab: str, rows: list[dict[str, object]], key_fields: tuple[str, ...]) -> int:
        if sheet_tab == "SMINFO Enrichment":
            raise RuntimeError("sheet projection failed")
        return super().upsert_cards(sheet_tab=sheet_tab, rows=rows, key_fields=key_fields)


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
    assert profile_row["collected_at"].endswith("+09:00")

    [sheet_row] = queue.published["SMINFO Enrichment"]
    assert sheet_row["requested_company"] == "에이아이오"
    assert sheet_row["match_status"] == "matched"
    assert sheet_row["sminfo_url"].endswith("0007451769")
    assert sheet_row["collected_at"].endswith("+09:00")

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
    assert candidate_update["sminfo_collected_at"].endswith("+09:00")
    assert candidate_update["p1_region_match"] == "Y"
    assert candidate_update["p1_region_rule"] == "2_경기도_사회적경제"
    assert candidate_update["p1_region_detail"] == "경기"
    assert candidate_update["p1_purpose_match"] == "확인필요"


def test_enrich_sminfo_candidates_drains_due_sqlite_queue_before_sheet_fallback() -> None:
    queue = FakeReviewQueue()
    queue.seed_reviews("Candidate Detail", [{"company": "시트후보"}])
    store = FakeStructuredStore()
    now = datetime.now(UTC).isoformat()
    task = build_sminfo_task(
        {
            "company": "에이아이오",
            "normalized_name": "에이아이오",
            "representative": "권진형",
            "homepage": "https://the-aio.com/",
            "source_url": "https://thevc.kr/aio",
        },
        source_channel="thevc_investment_ma",
        now=now,
    )
    store.upsert_rows(table="sminfo_enrichment_queue", rows=[task], key_fields=("task_id",))
    client = StoreCheckingSminfoClient(store, str(task["task_id"]))

    result = enrich_sminfo_candidates(
        review_queue=queue,
        structured_store=store,
        client=client,
        max_items=1,
        min_interval_seconds=35,
        agent_id="agent-test",
        run_id="run_sminfo_queue",
    )

    assert result.processed_count == 1
    assert [item[0] for item in client.seen] == ["에이아이오"]
    [updated_task] = store.tables["sminfo_enrichment_queue"]
    assert updated_task["status"] == "matched"
    assert updated_task["completed_at"].endswith("+09:00")
    assert updated_task["updated_at"].endswith("+09:00")
    assert str(updated_task["last_profile_id"]).startswith("sminfo_")
    assert updated_task["last_error"] == ""
    [candidate_update] = queue.published["Candidate Detail"]
    assert candidate_update["company"] == "에이아이오"
    assert candidate_update["sminfo_revenue_krw_thousand"] == "17851006"
    [queue_projection] = queue.published["SMINFO Queue"]
    assert queue_projection["task_id"] == task["task_id"]
    assert queue_projection["company"] == "에이아이오"
    assert queue_projection["status"] == "matched"
    assert queue_projection["next_run_at"].endswith("+09:00")
    assert queue_projection["updated_at"].endswith("+09:00")


def test_enrich_sminfo_candidates_does_not_leave_queue_running_when_sheet_projection_fails() -> None:
    queue = FailingSheetProjectionQueue()
    store = FakeStructuredStore()
    now = datetime.now(UTC).isoformat()
    task = build_sminfo_task(
        {
            "company": "에이아이오",
            "normalized_name": "에이아이오",
            "representative": "권진형",
            "homepage": "https://the-aio.com/",
            "source_url": "https://thevc.kr/aio",
        },
        source_channel="thevc_investment_ma",
        now=now,
    )
    store.upsert_rows(table="sminfo_enrichment_queue", rows=[task], key_fields=("task_id",))

    try:
        enrich_sminfo_candidates(
            review_queue=queue,
            structured_store=store,
            client=FakeSminfoClient(),
            max_items=1,
            min_interval_seconds=35,
            agent_id="agent-test",
            run_id="run_sminfo_sheet_failure",
        )
    except RuntimeError as exc:
        assert "sheet projection failed" in str(exc)
    else:
        raise AssertionError("expected Sheet projection failure")

    [updated_task] = store.tables["sminfo_enrichment_queue"]
    assert updated_task["status"] == "matched"
    assert updated_task["locked_by"] == ""
    assert updated_task["completed_at"]


def test_enrich_sminfo_candidates_retries_queue_task_after_browser_error() -> None:
    queue = FakeReviewQueue()
    store = FakeStructuredStore()
    now = datetime.now(UTC).isoformat()
    task = build_sminfo_task(
        {"company": "에이아이오", "normalized_name": "에이아이오"},
        source_channel="thevc_investment_ma",
        now=now,
    )
    store.upsert_rows(table="sminfo_enrichment_queue", rows=[task], key_fields=("task_id",))

    result = enrich_sminfo_candidates(
        review_queue=queue,
        structured_store=store,
        client=FailingSminfoClient(),
        max_items=1,
        min_interval_seconds=35,
        agent_id="agent-test",
        run_id="run_sminfo_queue_retry",
    )

    assert result.error_count == 1
    [updated_task] = store.tables["sminfo_enrichment_queue"]
    assert updated_task["status"] == "retry"
    assert updated_task["attempt_count"] == 1
    assert updated_task["next_run_at"] > now
    assert updated_task["next_run_at"].endswith("+09:00")
    assert updated_task["updated_at"].endswith("+09:00")
    assert "RuntimeError: connection reset" in updated_task["last_error"]


def test_enrich_sminfo_candidates_does_not_use_sheet_fallback_when_queue_has_no_due_tasks() -> None:
    queue = FakeReviewQueue()
    queue.seed_reviews("Candidate Detail", [{"company": "시트후보"}])
    store = FakeStructuredStore()
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    task = build_sminfo_task(
        {"company": "에이아이오", "normalized_name": "에이아이오"},
        source_channel="thevc_investment_ma",
        now=future,
    )
    task["status"] = "retry"
    store.upsert_rows(table="sminfo_enrichment_queue", rows=[task], key_fields=("task_id",))
    client = FakeSminfoClient()

    result = enrich_sminfo_candidates(
        review_queue=queue,
        structured_store=store,
        client=client,
        max_items=1,
        min_interval_seconds=35,
        agent_id="agent-test",
        run_id="run_sminfo_queue_no_due",
    )

    assert result.processed_count == 0
    assert client.seen == []


def test_enrich_sminfo_candidates_does_not_use_company_names_to_bypass_queue_backoff() -> None:
    queue = FakeReviewQueue()
    queue.seed_reviews("Candidate Detail", [{"company": "에이아이오"}])
    store = FakeStructuredStore()
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    task = build_sminfo_task(
        {"company": "에이아이오", "normalized_name": "에이아이오"},
        source_channel="thevc_investment_ma",
        now=future,
    )
    task["status"] = "retry"
    store.upsert_rows(table="sminfo_enrichment_queue", rows=[task], key_fields=("task_id",))
    client = FakeSminfoClient()

    result = enrich_sminfo_candidates(
        review_queue=queue,
        structured_store=store,
        client=client,
        max_items=1,
        min_interval_seconds=35,
        company_names=["에이아이오"],
        agent_id="agent-test",
        run_id="run_sminfo_company_names_no_bypass",
    )

    assert result.processed_count == 0
    assert client.seen == []


def test_enrich_sminfo_candidates_marks_queue_task_failed_after_max_attempts() -> None:
    queue = FakeReviewQueue()
    store = FakeStructuredStore()
    now = datetime.now(UTC).isoformat()
    task = build_sminfo_task(
        {"company": "에이아이오", "normalized_name": "에이아이오"},
        source_channel="thevc_investment_ma",
        now=now,
    )
    task["attempt_count"] = 4
    task["max_attempts"] = 5
    store.upsert_rows(table="sminfo_enrichment_queue", rows=[task], key_fields=("task_id",))

    result = enrich_sminfo_candidates(
        review_queue=queue,
        structured_store=store,
        client=FailingSminfoClient(),
        max_items=1,
        min_interval_seconds=35,
        agent_id="agent-test",
        run_id="run_sminfo_queue_failed",
    )

    assert result.error_count == 1
    [updated_task] = store.tables["sminfo_enrichment_queue"]
    assert updated_task["status"] == "failed"
    assert updated_task["attempt_count"] == 5
    assert updated_task["completed_at"]


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
