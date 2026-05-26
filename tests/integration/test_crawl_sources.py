from datetime import UTC, datetime

import merry_runtime.pipelines.crawl_sources as crawl_sources_module
from merry_runtime.adapters.fakes import FakeNotifier, FakeObjectStore, FakeReviewQueue, FakeStructuredStore
from merry_runtime.adapters.thevc_playwright import TheVCFetchResult, TheVCHumanVerificationError
from merry_runtime.clock import KST
from merry_runtime.ingestion.sminfo_queue import build_sminfo_task
from merry_runtime.ingestion.web_crawler import CrawlFetchError
from merry_runtime.pipelines.crawl_sources import crawl_sources
from merry_runtime.wiki_store import SQLiteWikiStore


def test_crawl_sources_fetches_thevc_visible_investment_cards_into_mother_db(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()
    wiki_store = SQLiteWikiStore(root=tmp_path)

    result = crawl_sources(
        targets=[{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        wiki_store=wiki_store,
        fetch_url=lambda url: """
            <script type="application/ld+json">
            {
              "@type": "Organization",
              "sameAs": ["https://the-aio.com/"],
              "email": "hello@the-aio.com",
              "address": {
                "@type": "PostalAddress",
                "addressCountry": "한국",
                "addressRegion": "경기도",
                "addressLocality": "용인시"
              },
              "employee": [
                {"@type": "Person", "name": "권진형", "jobTitle": "경영 · 대표이사"}
              ]
            }
            </script>
        """
        if url == "https://thevc.kr/aio"
        else """
            <tr>
              <td><time datetime="2026-05-15T05:14:25.919Z">2026-05-15</time><button>보도자료</button></td>
              <td><span>에이아이오</span><span>낸드컨트롤러</span><div>낸드플래시 시스템 반도체</div></td>
              <td><div>투자대상분야</div><div>반도체/디스플레이</div></td>
              <td><div>투자단계</div><div>Pre-IPO</div></td>
              <td><div>투자금액</div><button>로그인 필요</button></td>
              <td><div>투자자</div><span>비엔더블유인베스트먼트</span></td>
              <td><a href="/aio">프로필 확인</a></td>
            </tr>
        """,
    )

    assert result.target_count == 1
    assert result.crawled_source_count == 1
    assert result.enqueued_sminfo_task_count == 1
    assert result.ingested_entity_count == 1
    assert structured_store.tables["mother_entities"][0]["name"] == "에이아이오"
    assert structured_store.tables["mother_entities"][0]["representative"] == "권진형"
    assert structured_store.tables["mother_entities"][0]["homepage"] == "https://the-aio.com/"
    assert structured_store.tables["mother_entities"][0]["region"] == "한국, 경기도, 용인시"
    assert structured_store.tables["mother_entities"][0]["contact_email"] == "hello@the-aio.com"
    assert structured_store.tables["signals"][0]["signal_type"] == "investment"
    assert structured_store.tables["raw_sources"][0]["channel"] == "thevc_investment_ma"
    assert review_queue.published["Evidence"][0]["channel"] == "thevc_investment_ma"
    candidate_detail = review_queue.published["Candidate Detail"][0]
    assert "entity_id" not in candidate_detail
    assert candidate_detail["collected_at"].startswith("20")
    assert candidate_detail["collected_at"].endswith("+09:00")
    assert candidate_detail["company"] == "에이아이오"
    assert candidate_detail["summary"] == "공개 카드 -> 에이아이오"
    assert candidate_detail["business_model"] == "낸드컨트롤러 - 낸드플래시 시스템 반도체"
    assert candidate_detail["p1_region_match"] == "Y"
    assert candidate_detail["p1_region_rule"] == "2_경기도_사회적경제"
    assert candidate_detail["p1_region_detail"] == "경기"
    assert candidate_detail["p1_purpose_match"] == "확인필요"
    assert candidate_detail["investment_round"] == "Pre-IPO"
    assert candidate_detail["investment_amount"] == "로그인 필요"
    assert candidate_detail["investor"] == "비엔더블유인베스트먼트"
    assert candidate_detail["contact_email"] == "hello@the-aio.com"
    [sminfo_task] = structured_store.tables["sminfo_enrichment_queue"]
    assert sminfo_task["company"] == "에이아이오"
    assert sminfo_task["representative"] == "권진형"
    assert sminfo_task["homepage"] == "https://the-aio.com/"
    assert sminfo_task["source_channel"] == "thevc_investment_ma"
    assert sminfo_task["source_url"] == "https://thevc.kr/aio"
    assert sminfo_task["status"] == "pending"
    assert sminfo_task["next_run_at"].endswith("+09:00")
    assert sminfo_task["created_at"].endswith("+09:00")
    assert sminfo_task["updated_at"].endswith("+09:00")
    [queue_projection] = review_queue.published["SMINFO Queue"]
    assert queue_projection["task_id"] == sminfo_task["task_id"]
    assert queue_projection["company"] == "에이아이오"
    assert queue_projection["status"] == "pending"
    assert queue_projection["next_run_at"].endswith("+09:00")
    assert queue_projection["updated_at"].endswith("+09:00")
    assert any(row["job_name"] == "crawl-sources" for row in structured_store.tables["agent_runs"])
    assert (tmp_path / "wiki" / "entities").exists()


def test_crawl_sources_uses_thevc_playwright_fetcher_when_requested(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()
    seen_targets: list[dict[str, object]] = []

    def static_fetch_url(url: str) -> str:
        raise AssertionError(f"static fetch_url should not be used for Playwright The VC target: {url}")

    def thevc_fetcher(target: dict[str, object]) -> list[dict[str, str]]:
        seen_targets.append(target)
        return [
            {
                "channel": "thevc_investment_ma",
                "payload": "\n".join(
                    [
                        "Title: THE VC Investment/M&A - 로민 텍스트스코프",
                        "URL: https://thevc.kr/",
                        "Source URI: https://thevc.kr/lomin",
                        "Company: 로민",
                        "Product: 텍스트스코프",
                        "Business Model: 텍스트스코프 - AI 문서 인식 솔루션",
                        "Industry: 엔터프라이즈",
                        "Representative: 강지홍",
                        "Homepage: https://www.lomin.ai/",
                        "Region: 한국, 서울특별시",
                        "Contact Email: ",
                        "Published: 2026-05-20",
                        "Signal: investment",
                        "Confidence: 0.65",
                        "Tags: thevc_investment_ma, public_cold_lead, investment, fresh, detail_enriched, industry:엔터프라이즈, round:series-a",
                        "Investment Round: Series A",
                        "Investment Amount: 로그인 필요",
                        "Investor: 네이버클라우드",
                        "Evidence: THE VC 투자/M&A 공개 카드: 로민 / 텍스트스코프.",
                    ]
                ),
            }
        ]

    result = crawl_sources(
        targets=[
            {
                "url": "https://thevc.kr/",
                "source_kind": "thevc_investment_ma",
                "thevc_backend": "playwright",
                "max_cards": "15",
                "max_pages": "3",
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        wiki_store=SQLiteWikiStore(root=tmp_path),
        fetch_url=static_fetch_url,
        thevc_source_fetcher=thevc_fetcher,
        run_id="run_thevc_playwright",
    )

    assert result.crawled_source_count == 1
    assert seen_targets == [
        {
            "url": "https://thevc.kr/",
            "source_kind": "thevc_investment_ma",
            "thevc_backend": "playwright",
            "max_cards": "15",
            "max_pages": "3",
        }
    ]
    assert structured_store.tables["mother_entities"][0]["name"] == "로민"


def test_crawl_sources_records_thevc_playwright_warning_from_fetch_result(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()

    def thevc_fetcher(target: dict[str, object]) -> TheVCFetchResult:
        return TheVCFetchResult(
            sources=[
                {
                    "channel": "thevc_investment_ma",
                    "payload": "\n".join(
                        [
                            "Title: THE VC Investment/M&A - 로민 텍스트스코프",
                            "URL: https://thevc.kr/",
                            "Source URI: https://thevc.kr/lomin",
                            "Company: 로민",
                            "Product: 텍스트스코프",
                            "Business Model: 텍스트스코프 - AI 문서 인식 솔루션",
                            "Industry: 엔터프라이즈",
                            "Representative: 강지홍",
                            "Homepage: https://www.lomin.ai/",
                            "Region: 한국, 서울특별시",
                            "Contact Email: ",
                            "Published: 2026-05-20",
                            "Signal: investment",
                            "Confidence: 0.65",
                            "Tags: thevc_investment_ma, public_cold_lead, investment, fresh, detail_enriched, industry:엔터프라이즈, round:series-a",
                            "Investment Round: Series A",
                            "Investment Amount: 로그인 필요",
                            "Investor: 네이버클라우드",
                            "Evidence: THE VC 투자/M&A 공개 카드: 로민 / 텍스트스코프.",
                        ]
                    ),
                }
            ],
            login_status="failed",
            warning_message="THE VC login failed; public crawl fallback used",
        )

    result = crawl_sources(
        targets=[
            {
                "url": "https://thevc.kr/",
                "source_kind": "thevc_investment_ma",
                "thevc_backend": "playwright",
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        thevc_source_fetcher=thevc_fetcher,
        run_id="run_thevc_warning",
    )

    assert result.crawled_source_count == 1
    assert result.warning_count == 1
    crawl_run = next(row for row in structured_store.tables["agent_runs"] if row["job_name"] == "crawl-sources")
    assert crawl_run["error_message"] == "THE VC login failed; public crawl fallback used"


def test_crawl_sources_records_thevc_human_verification_warning(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()

    def thevc_fetcher(target: dict[str, object]) -> TheVCFetchResult:
        raise TheVCHumanVerificationError("THE VC human verification did not complete")

    result = crawl_sources(
        targets=[
            {
                "url": "https://thevc.kr/",
                "source_kind": "thevc_investment_ma",
                "thevc_backend": "playwright",
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        thevc_source_fetcher=thevc_fetcher,
        run_id="run_thevc_human_verification",
    )

    assert result.crawled_source_count == 0
    assert result.warning_count == 1
    crawl_run = next(row for row in structured_store.tables["agent_runs"] if row["job_name"] == "crawl-sources")
    assert "THE VC human verification blocked crawl" in crawl_run["error_message"]


def test_crawl_sources_marks_sheet_targets_as_crawled(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(crawl_sources_module, "now_kst", lambda: "2026-05-22T11:30:00+09:00")
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()
    review_queue.published["Crawl Sources"] = [
        {
            "url": "https://thevc.kr/",
            "source_kind": "thevc_investment_ma",
            "max_cards": "20",
            "status": "active",
            "last_crawled_at": "2026-05-20T09:36:52+09:00",
            "error_message": "old error",
        },
        {
            "url": "https://platum.kr/archives/category/investment",
            "source_kind": "platum_investment_news",
            "max_articles": "24",
            "status": "inactive",
            "last_crawled_at": "",
            "error_message": "",
        },
    ]

    result = crawl_sources(
        targets=[
            {
                "url": "https://thevc.kr/",
                "source_kind": "thevc_investment_ma",
                "max_cards": "20",
                "status": "active",
                "last_crawled_at": "2026-05-20T09:36:52+09:00",
                "error_message": "old error",
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        wiki_store=SQLiteWikiStore(root=tmp_path),
        fetch_url=lambda url: """
            <script type="application/ld+json">
            {"@type": "Organization", "sameAs": ["https://the-aio.com/"]}
            </script>
        """
        if url == "https://thevc.kr/aio"
        else """
            <tr>
              <td><time datetime="2026-05-15T05:14:25.919Z">2026-05-15</time></td>
              <td><span>에이아이오</span><span>낸드컨트롤러</span><div>낸드플래시 시스템 반도체</div></td>
              <td><div>투자대상분야</div><div>반도체/디스플레이</div></td>
              <td><div>투자단계</div><div>Pre-IPO</div></td>
              <td><div>투자금액</div><button>로그인 필요</button></td>
              <td><div>투자자</div><span>비엔더블유인베스트먼트</span></td>
              <td><a href="/aio">프로필 확인</a></td>
            </tr>
        """,
        publish_crawl_status=True,
        run_id="run_sheet_status",
    )

    assert result.crawled_source_count == 1
    crawl_rows = review_queue.published["Crawl Sources"]
    assert crawl_rows[0]["last_crawled_at"] == "2026-05-22T11:30:00+09:00"
    assert crawl_rows[0]["error_message"] == ""
    assert crawl_rows[1]["last_crawled_at"] == ""


def test_crawl_sources_generates_distinct_run_ids_for_repeated_target_sets(monkeypatch, tmp_path) -> None:
    timestamps = iter(
        [
            "2026-05-22T11:30:00+09:00",
            "2026-05-22T11:30:01+09:00",
            "2026-05-22T11:31:00+09:00",
            "2026-05-22T11:31:01+09:00",
        ]
    )
    monkeypatch.setattr(crawl_sources_module, "now_kst", lambda: next(timestamps))
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()

    def fetch_url(url: str) -> str:
        if url == "https://thevc.kr/aio":
            return """
                <script type="application/ld+json">
                {"@type": "Organization", "sameAs": ["https://the-aio.com/"]}
                </script>
            """
        return """
            <tr>
              <td><time datetime="2026-05-15T05:14:25.919Z">2026-05-15</time></td>
              <td><span>에이아이오</span><span>낸드컨트롤러</span><div>낸드플래시 시스템 반도체</div></td>
              <td><div>투자대상분야</div><div>반도체/디스플레이</div></td>
              <td><div>투자단계</div><div>Pre-IPO</div></td>
              <td><div>투자금액</div><button>로그인 필요</button></td>
              <td><div>투자자</div><span>비엔더블유인베스트먼트</span></td>
              <td><a href="/aio">프로필 확인</a></td>
            </tr>
        """

    targets = [{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}]
    first = crawl_sources(
        targets=targets,
        object_store=object_store,
        structured_store=structured_store,
        wiki_store=SQLiteWikiStore(root=tmp_path),
        fetch_url=fetch_url,
    )
    second = crawl_sources(
        targets=targets,
        object_store=object_store,
        structured_store=structured_store,
        wiki_store=SQLiteWikiStore(root=tmp_path),
        fetch_url=fetch_url,
    )

    assert first.run_id != second.run_id
    crawl_run_ids = [
        row["run_id"] for row in structured_store.tables["agent_runs"] if row["job_name"] == "crawl-sources"
    ]
    assert crawl_run_ids == [first.run_id, second.run_id]


def test_crawl_sources_does_not_republish_existing_sheet_projection_rows(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()

    def fetch_url(url: str) -> str:
        if url == "https://thevc.kr/aio":
            return """
                <script type="application/ld+json">
                {
                  "@type": "Organization",
                  "sameAs": ["https://the-aio.com/"],
                  "email": "hello@the-aio.com",
                  "employee": [
                    {"@type": "Person", "name": "권진형", "jobTitle": "대표이사"}
                  ]
                }
                </script>
            """
        return """
            <tr>
              <td><time datetime="2026-05-15T05:14:25.919Z">2026-05-15</time><button>보도자료</button></td>
              <td><span>에이아이오</span><span>낸드컨트롤러</span><div>낸드플래시 시스템 반도체</div></td>
              <td><div>투자대상분야</div><div>반도체/디스플레이</div></td>
              <td><div>투자단계</div><div>Pre-IPO</div></td>
              <td><div>투자금액</div><button>로그인 필요</button></td>
              <td><div>투자자</div><span>비엔더블유인베스트먼트</span></td>
              <td><a href="/aio">프로필 확인</a></td>
            </tr>
        """

    for run_id in ("run_first", "run_second"):
        crawl_sources(
            targets=[{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}],
            object_store=object_store,
            structured_store=structured_store,
            review_queue=review_queue,
            fetch_url=fetch_url,
            run_id=run_id,
        )

    assert len(review_queue.published["Evidence"]) == 1
    assert len(review_queue.published["Candidate Detail"]) == 1
    assert len(structured_store.tables["sminfo_enrichment_queue"]) == 1


def test_crawl_sources_enriches_candidate_detail_with_kvic_investor_profile(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    structured_store.upsert_rows(
        table="kvic_investor_managers",
        rows=[
            {
                "manager_id": "kvic_mgr_d3",
                "manager_name": "디쓰리쥬빌리파트너스",
                "active_fund_count": 3,
                "total_fund_count": 3,
                "active_amount_eok": 743.5,
                "active_commitment_eok": 480.0,
                "fund_fields": ["미래환경산업", "소셜임팩트"],
                "representative_funds": ["디쓰리 미래환경 ECO 벤처투자조합", "디쓰리 임팩트 벤처투자조합 제2호"],
                "profile_tags": ["climate_environment", "impact"],
                "next_expiry_at": "2026-08-16",
                "latest_expiry_at": "2029-08-25",
                "collected_at": "2026-05-19T16:00:00+09:00",
            }
        ],
        key_fields=("manager_id",),
    )
    review_queue = FakeReviewQueue()

    result = crawl_sources(
        targets=[{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        fetch_url=lambda url: """
            <tr>
              <td><time datetime="2026-05-15T05:14:25.919Z">2026-05-15</time><button>보도자료</button></td>
              <td><span>그린테크</span><span>탄소저감</span><div>농업 탄소 데이터 플랫폼</div></td>
              <td><div>투자대상분야</div><div>클린테크</div></td>
              <td><div>투자단계</div><div>Seed</div></td>
              <td><div>투자금액</div><button>로그인 필요</button></td>
              <td><div>투자자</div><span>디쓰리쥬빌리파트너스</span></td>
              <td><a href="/green-tech">프로필 확인</a></td>
            </tr>
        """,
    )

    assert result.crawled_source_count == 1
    [candidate_detail] = review_queue.published["Candidate Detail"]
    assert candidate_detail["investor"] == "디쓰리쥬빌리파트너스"
    assert candidate_detail["kvic_matched_investors"] == "디쓰리쥬빌리파트너스"
    assert candidate_detail["kvic_active_fund_count"] == 3
    assert candidate_detail["kvic_active_amount_eok"] == 743.5
    assert candidate_detail["kvic_fund_fields"] == "미래환경산업, 소셜임팩트"
    assert candidate_detail["kvic_representative_funds"] == "디쓰리 미래환경 ECO 벤처투자조합, 디쓰리 임팩트 벤처투자조합 제2호"
    assert candidate_detail["kvic_profile_tags"] == "climate_environment, impact"


def test_crawl_sources_enqueues_thevc_sminfo_tasks_without_sheet_projection(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()

    def fetch_url(url: str) -> str:
        if url == "https://thevc.kr/aio":
            return """
                <script type="application/ld+json">
                {
                  "@type": "Organization",
                  "sameAs": ["https://the-aio.com/"],
                  "employee": [
                    {"@type": "Person", "name": "권진형", "jobTitle": "대표이사"}
                  ]
                }
                </script>
            """
        return """
            <tr>
              <td><time datetime="2026-05-15T05:14:25.919Z">2026-05-15</time><button>보도자료</button></td>
              <td><span>에이아이오</span><span>낸드컨트롤러</span><div>낸드플래시 시스템 반도체</div></td>
              <td><div>투자대상분야</div><div>반도체/디스플레이</div></td>
              <td><div>투자단계</div><div>Pre-IPO</div></td>
              <td><div>투자금액</div><button>로그인 필요</button></td>
              <td><div>투자자</div><span>비엔더블유인베스트먼트</span></td>
              <td><a href="/aio">프로필 확인</a></td>
            </tr>
        """

    result = crawl_sources(
        targets=[{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=None,
        fetch_url=fetch_url,
        run_id="run_no_sheet",
    )

    assert result.enqueued_sminfo_task_count == 1
    [task] = structured_store.tables["sminfo_enrichment_queue"]
    assert task["company"] == "에이아이오"


def test_crawl_sources_does_not_reset_fresh_terminal_sminfo_queue_tasks(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()

    existing_task = build_sminfo_task(
        {
            "company": "에이아이오",
            "normalized_name": "에이아이오",
            "representative": "권진형",
            "homepage": "https://the-aio.com/",
            "source_url": "https://thevc.kr/aio",
        },
        source_channel="thevc_investment_ma",
        now="2026-05-19T00:00:00+00:00",
    )
    existing_task.update(
        {
            "status": "matched",
            "attempt_count": 1,
            "last_profile_id": "sminfo_profile_existing",
            "updated_at": datetime.now(UTC).isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
        }
    )
    structured_store.upsert_rows(
        table="sminfo_enrichment_queue",
        rows=[existing_task],
        key_fields=("task_id",),
    )

    def fetch_url(url: str) -> str:
        if url == "https://thevc.kr/aio":
            return """
                <script type="application/ld+json">
                {
                  "@type": "Organization",
                  "sameAs": ["https://the-aio.com/"],
                  "employee": [
                    {"@type": "Person", "name": "권진형", "jobTitle": "대표이사"}
                  ]
                }
                </script>
            """
        return """
            <tr>
              <td><time datetime="2026-05-15T05:14:25.919Z">2026-05-15</time><button>보도자료</button></td>
              <td><span>에이아이오</span><span>낸드컨트롤러</span><div>낸드플래시 시스템 반도체</div></td>
              <td><div>투자대상분야</div><div>반도체/디스플레이</div></td>
              <td><div>투자단계</div><div>Pre-IPO</div></td>
              <td><div>투자금액</div><button>로그인 필요</button></td>
              <td><div>투자자</div><span>비엔더블유인베스트먼트</span></td>
              <td><a href="/aio">프로필 확인</a></td>
            </tr>
        """

    result = crawl_sources(
        targets=[{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        fetch_url=fetch_url,
        run_id="run_terminal_sminfo_task",
    )

    assert result.enqueued_sminfo_task_count == 0
    [task] = structured_store.tables["sminfo_enrichment_queue"]
    assert task == existing_task


def test_crawl_sources_preserves_retry_sminfo_queue_backoff(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()
    existing_task = build_sminfo_task(
        {
            "company": "에이아이오",
            "normalized_name": "에이아이오",
            "representative": "권진형",
            "homepage": "https://the-aio.com/",
            "source_url": "https://thevc.kr/aio",
        },
        source_channel="thevc_investment_ma",
        now="2026-05-19T00:00:00+00:00",
    )
    existing_task.update(
        {
            "status": "retry",
            "attempt_count": 2,
            "next_run_at": "2026-05-20T00:00:00+00:00",
            "last_error": "RuntimeError: connection reset",
        }
    )
    structured_store.upsert_rows(
        table="sminfo_enrichment_queue",
        rows=[existing_task],
        key_fields=("task_id",),
    )

    def fetch_url(url: str) -> str:
        if url == "https://thevc.kr/aio":
            return """
                <script type="application/ld+json">
                {
                  "@type": "Organization",
                  "sameAs": ["https://the-aio.com/"],
                  "employee": [
                    {"@type": "Person", "name": "권진형", "jobTitle": "대표이사"}
                  ]
                }
                </script>
            """
        return """
            <tr>
              <td><time datetime="2026-05-15T05:14:25.919Z">2026-05-15</time><button>보도자료</button></td>
              <td><span>에이아이오</span><span>낸드컨트롤러</span><div>낸드플래시 시스템 반도체</div></td>
              <td><div>투자대상분야</div><div>반도체/디스플레이</div></td>
              <td><div>투자단계</div><div>Pre-IPO</div></td>
              <td><div>투자금액</div><button>로그인 필요</button></td>
              <td><div>투자자</div><span>비엔더블유인베스트먼트</span></td>
              <td><a href="/aio">프로필 확인</a></td>
            </tr>
        """

    result = crawl_sources(
        targets=[{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        fetch_url=fetch_url,
        run_id="run_retry_preserved",
    )

    assert result.enqueued_sminfo_task_count == 0
    [task] = structured_store.tables["sminfo_enrichment_queue"]
    assert task == existing_task


def test_crawl_sources_does_not_duplicate_retry_task_when_detail_hints_appear_later(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()

    listing_html = """
        <tr>
          <td><time datetime="2026-05-15T05:14:25.919Z">2026-05-15</time><button>보도자료</button></td>
          <td><span>에이아이오</span><span>낸드컨트롤러</span><div>낸드플래시 시스템 반도체</div></td>
          <td><div>투자대상분야</div><div>반도체/디스플레이</div></td>
          <td><div>투자단계</div><div>Pre-IPO</div></td>
          <td><div>투자금액</div><button>로그인 필요</button></td>
          <td><div>투자자</div><span>비엔더블유인베스트먼트</span></td>
          <td><a href="/aio">프로필 확인</a></td>
        </tr>
    """

    crawl_sources(
        targets=[
            {
                "url": "https://thevc.kr/",
                "source_kind": "thevc_investment_ma",
                "detail_enrichment": "false",
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        fetch_url=lambda url: listing_html,
        run_id="run_without_detail",
    )
    [existing_task] = structured_store.tables["sminfo_enrichment_queue"]
    existing_task.update(
        {
            "status": "retry",
            "attempt_count": 2,
            "next_run_at": "2026-05-20T00:00:00+00:00",
            "last_error": "RuntimeError: connection reset",
        }
    )
    structured_store.upsert_rows(
        table="sminfo_enrichment_queue",
        rows=[existing_task],
        key_fields=("task_id",),
    )

    def fetch_url(url: str) -> str:
        if url == "https://thevc.kr/aio":
            return """
                <script type="application/ld+json">
                {
                  "@type": "Organization",
                  "sameAs": ["https://the-aio.com/"],
                  "employee": [
                    {"@type": "Person", "name": "권진형", "jobTitle": "대표이사"}
                  ]
                }
                </script>
            """
        return listing_html

    result = crawl_sources(
        targets=[{"url": "https://thevc.kr/", "source_kind": "thevc_investment_ma"}],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        fetch_url=fetch_url,
        run_id="run_with_detail",
    )

    assert result.enqueued_sminfo_task_count == 0
    assert structured_store.tables["sminfo_enrichment_queue"] == [existing_task]


def test_crawl_sources_sends_slack_for_new_platum_portfolio_news_only(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()
    notifier = FakeNotifier()
    html = """
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/286764"></a>
          <h3 class="gb-headline">비저너리, 카이스트청년창업투자지주로부터 시드 투자 유치</h3>
          <p class="gb-headline excerpt">공간 지능 데이터 소프트웨어 스타트업 비저너리가 총 8억 원 규모의 시드 투자를 유치했다.</p>
          <time class="entry-date published" datetime="2026-05-13T12:39:15+09:00">2026.05.13</time>
        </div>
    """

    results = []
    for run_id in ("run_first", "run_second"):
        results.append(crawl_sources(
            targets=[
                {
                    "url": "https://platum.kr/archives/category/investment",
                    "source_kind": "platum_investment_news",
                    "portfolio_companies": ["(주)비저너리"],
                }
            ],
            object_store=object_store,
            structured_store=structured_store,
            review_queue=review_queue,
            notifier=notifier,
            slack_channel="C123",
            fetch_url=lambda url: html,
            run_id=run_id,
        ))

    result = results[-1]
    assert results[0].notified_count == 1
    assert result.crawled_source_count == 0
    assert result.notified_count == 0
    assert len(structured_store.tables["raw_sources"]) == 1
    assert structured_store.tables["raw_sources"][0]["channel"] == "platum_investment_news"
    assert structured_store.tables["mother_entities"][0]["name"] == "비저너리"
    assert structured_store.tables["signals"][0]["signal_type"] == "portfolio_news"
    assert len(review_queue.published["Evidence"]) == 1
    assert len(review_queue.published["Portfolio News"]) == 1
    assert len(structured_store.tables["sminfo_enrichment_queue"]) == 0
    portfolio_news = review_queue.published["Portfolio News"][0]
    assert portfolio_news["company"] == "비저너리"
    assert portfolio_news["title"] == "비저너리, 카이스트청년창업투자지주로부터 시드 투자 유치"
    assert portfolio_news["summary"] == "공간 지능 데이터 소프트웨어 스타트업 비저너리가 총 8억 원 규모의 시드 투자를 유치했다."
    assert portfolio_news["url"] == "https://platum.kr/archives/286764"
    assert portfolio_news["published_at"] == "2026-05-13T12:39:15+09:00"
    assert portfolio_news["source"] == "Platum"
    assert portfolio_news["channel"] == "platum_investment_news"
    assert portfolio_news["matched_companies"] == "비저너리"
    assert portfolio_news["notified_at"].endswith("+09:00")
    assert portfolio_news["status"] == "new"
    assert len(notifier.messages) == 1
    assert notifier.messages[0]["channel"] == "C123"
    assert "비저너리" in notifier.messages[0]["text"]
    assert "https://platum.kr/archives/286764" in notifier.messages[0]["text"]


def test_crawl_sources_does_not_slack_platum_news_already_in_sheet_when_db_is_empty(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()
    review_queue.seed_reviews(
        "Portfolio News",
        [
            {
                "company": "비저너리",
                "url": "https://platum.kr/archives/286764",
                "title": "비저너리, 카이스트청년창업투자지주로부터 시드 투자 유치",
            }
        ],
    )
    notifier = FakeNotifier()
    html = """
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/286764"></a>
          <h3 class="gb-headline">비저너리, 카이스트청년창업투자지주로부터 시드 투자 유치</h3>
          <p class="gb-headline excerpt">공간 지능 데이터 소프트웨어 스타트업 비저너리가 총 8억 원 규모의 시드 투자를 유치했다.</p>
          <time class="entry-date published" datetime="2026-05-13T12:39:15+09:00">2026.05.13</time>
        </div>
    """

    result = crawl_sources(
        targets=[
            {
                "url": "https://platum.kr/archives/category/investment",
                "source_kind": "platum_investment_news",
                "portfolio_companies": ["(주)비저너리"],
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        notifier=notifier,
        slack_channel="C123",
        fetch_url=lambda url: html,
        run_id="run_existing_sheet_news_empty_db",
    )

    assert result.crawled_source_count == 1
    assert result.notified_count == 0
    assert len(notifier.messages) == 0
    assert len(structured_store.tables["raw_sources"]) == 1
    assert structured_store.tables["raw_sources"][0]["channel"] == "platum_investment_news"
    assert review_queue.published["Portfolio News"] == []


def test_crawl_sources_uses_accelerator_watchlist_sheet_tab_and_recent_slack(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        crawl_sources_module,
        "now_kst_datetime",
        lambda: datetime(2026, 5, 21, 12, 0, 0, tzinfo=KST),
    )
    monkeypatch.setattr(crawl_sources_module, "now_kst", lambda: "2026-05-21T12:00:00+09:00")
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()
    review_queue.seed_reviews(
        "Accelerator Watchlist",
        [
            {"company": "(주)공감만세", "aliases": "", "status": "active"},
            {"company": "(주)제로원", "aliases": "", "status": "active"},
            {"company": "숨은회사", "aliases": "", "status": "inactive"},
        ],
    )
    notifier = FakeNotifier()
    html = """
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/300001"></a>
          <h3 class="gb-headline">공감만세, 지역 관광 프로그램 확장</h3>
          <p class="gb-headline excerpt">공감만세가 지역 기반 프로그램을 확대했다.</p>
          <time class="entry-date published" datetime="2026-05-20T09:00:00+09:00">2026.05.20</time>
        </div>
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/300002"></a>
          <h3 class="gb-headline">제로원, 창업 교육 플랫폼 출시</h3>
          <p class="gb-headline excerpt">제로원이 신규 플랫폼을 공개했다.</p>
          <time class="entry-date published" datetime="2026-03-01T09:00:00+09:00">2026.03.01</time>
        </div>
    """

    result = crawl_sources(
        targets=[
            {
                "url": "https://platum.kr/archives/category/investment",
                "source_kind": "platum_investment_news",
                "portfolio_watchlist_sheet_tab": "Accelerator Watchlist",
                "portfolio_news_sheet_tab": "Accelerator News",
                "portfolio_news_slack_heading": "Hermes 육성기업 뉴스 감지",
                "portfolio_notify_recent_days": "2",
                "max_pages": 1,
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        notifier=notifier,
        slack_channel="C123",
        fetch_url=lambda url: html,
        run_id="run_accelerator_news",
    )

    assert result.crawled_source_count == 2
    assert result.notified_count == 1
    assert review_queue.published["Portfolio News"] == []
    news_by_company = {str(row["company"]): row for row in review_queue.published["Accelerator News"]}
    assert set(news_by_company) == {"공감만세", "제로원"}
    assert news_by_company["공감만세"]["notified_at"] == "2026-05-21T12:00:00+09:00"
    assert news_by_company["제로원"]["notified_at"] == ""
    assert len(notifier.messages) == 1
    assert "Hermes 육성기업 뉴스 감지" in notifier.messages[0]["text"]
    assert "https://platum.kr/archives/300001" in notifier.messages[0]["text"]
    assert "https://platum.kr/archives/300002" not in notifier.messages[0]["text"]


def test_crawl_sources_publishes_existing_db_platum_source_to_new_news_tab(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()
    html = """
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/300003"></a>
          <h3 class="gb-headline">공감만세, 임팩트 프로그램 확장</h3>
          <p class="gb-headline excerpt">공감만세가 임팩트 프로그램을 확대했다.</p>
          <time class="entry-date published" datetime="2026-05-20T09:00:00+09:00">2026.05.20</time>
        </div>
    """
    crawl_sources(
        targets=[
            {
                "url": "https://platum.kr/archives/category/investment",
                "source_kind": "platum_investment_news",
                "portfolio_companies": ["공감만세(주)"],
                "max_pages": 1,
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        fetch_url=lambda url: html,
        run_id="run_portfolio_first",
    )
    review_queue.seed_reviews(
        "Accelerator Watchlist",
        [{"company": "(주)공감만세", "aliases": "", "status": "active"}],
    )

    result = crawl_sources(
        targets=[
            {
                "url": "https://platum.kr/archives/category/investment",
                "source_kind": "platum_investment_news",
                "portfolio_watchlist_sheet_tab": "Accelerator Watchlist",
                "portfolio_news_sheet_tab": "Accelerator News",
                "max_pages": 1,
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        fetch_url=lambda url: html,
        run_id="run_accelerator_existing_db_source",
    )

    assert result.crawled_source_count == 0
    assert len(structured_store.tables["raw_sources"]) == 1
    assert [row["company"] for row in review_queue.published["Portfolio News"]] == ["공감만세"]
    assert [row["company"] for row in review_queue.published["Accelerator News"]] == ["공감만세"]


def test_crawl_sources_publishes_same_platum_url_for_new_company(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()
    review_queue.seed_reviews(
        "Portfolio News",
        [
            {
                "company": "공감만세",
                "url": "https://platum.kr/archives/286555",
                "title": "공감만세와 리소리우스, 임팩트 투자 유치",
            }
        ],
    )
    html = """
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/286555"></a>
          <h3 class="gb-headline">공감만세와 리소리우스, 임팩트 투자 유치</h3>
          <p class="gb-headline excerpt">공감만세와 리소리우스가 후속 투자를 유치했다.</p>
        </div>
    """

    result = crawl_sources(
        targets=[
            {
                "url": "https://platum.kr/archives/category/investment",
                "source_kind": "platum_investment_news",
                "portfolio_companies": ["공감만세(주)", "(주)리소리우스"],
                "max_pages": 1,
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        fetch_url=lambda url: html,
        run_id="run_platum_existing_url_new_company",
    )

    assert result.crawled_source_count == 2
    assert [row["company"] for row in review_queue.published["Portfolio News"]] == ["리소리우스"]


def test_crawl_sources_does_not_drop_new_company_when_platum_url_exists_in_db(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    structured_store.upsert_rows(
        table="raw_sources",
        rows=[
            {
                "source_id": "src_existing",
                "channel": "platum_investment_news",
                "url": "https://platum.kr/archives/286555",
            }
        ],
        key_fields=("source_id",),
    )
    structured_store.upsert_rows(
        table="signals",
        rows=[
            {
                "signal_id": "sig_existing",
                "source_id": "src_existing",
                "entity_id": "ent_gong",
            }
        ],
        key_fields=("signal_id",),
    )
    structured_store.upsert_rows(
        table="mother_entities",
        rows=[
            {
                "entity_id": "ent_gong",
                "name": "공감만세",
                "normalized_name": "공감만세",
            }
        ],
        key_fields=("entity_id",),
    )
    review_queue = FakeReviewQueue()
    html = """
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/286555"></a>
          <h3 class="gb-headline">공감만세와 리소리우스, 임팩트 투자 유치</h3>
          <p class="gb-headline excerpt">공감만세와 리소리우스가 후속 투자를 유치했다.</p>
        </div>
    """

    result = crawl_sources(
        targets=[
            {
                "url": "https://platum.kr/archives/category/investment",
                "source_kind": "platum_investment_news",
                "portfolio_companies": ["공감만세(주)", "(주)리소리우스"],
                "max_pages": 1,
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        fetch_url=lambda url: html,
        run_id="run_platum_existing_db_url_new_company",
    )

    assert result.crawled_source_count == 1
    assert review_queue.published["Portfolio News"][0]["company"] == "리소리우스"


def test_crawl_sources_fetches_platum_facetwp_pages_when_configured(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()
    notifier = FakeNotifier()
    first_page_html = """
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/286770"></a>
          <h3 class="gb-headline">삶 클리닉, AI엔젤클럽으로부터 시드 투자 유치</h3>
          <p class="gb-headline excerpt">AI 기반 정신건강 데이터 플랫폼 삶 클리닉이 투자를 유치했다.</p>
        </div>
    """
    second_page_html = """
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/286100"></a>
          <h3 class="gb-headline">공감만세, 지역 관광 투자 유치</h3>
          <p class="gb-headline excerpt">공정여행 스타트업 공감만세가 신규 투자를 유치했다.</p>
          <time class="entry-date published" datetime="2026-05-01T09:00:00+09:00">2026.05.01</time>
        </div>
    """

    result = crawl_sources(
        targets=[
            {
                "url": "https://platum.kr/archives/category/investment",
                "source_kind": "platum_investment_news",
                "portfolio_companies": ["공감만세(주)"],
                "max_pages": 2,
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        notifier=notifier,
        slack_channel="C123",
        fetch_url=lambda url: first_page_html,
        fetch_platum_page=lambda url, page: second_page_html,
        run_id="run_platum_facetwp_pages",
    )

    assert result.crawled_source_count == 1
    assert result.notified_count == 1
    assert review_queue.published["Portfolio News"][0]["company"] == "공감만세"
    assert review_queue.published["Portfolio News"][0]["url"] == "https://platum.kr/archives/286100"
    assert "공감만세" in notifier.messages[0]["text"]


def test_crawl_sources_uses_platum_pagination_by_default(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()
    first_page_html = """
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/286770"></a>
          <h3 class="gb-headline">삶 클리닉, AI엔젤클럽으로부터 시드 투자 유치</h3>
          <p class="gb-headline excerpt">AI 기반 정신건강 데이터 플랫폼 삶 클리닉이 투자를 유치했다.</p>
        </div>
    """
    second_page_html = """
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/286100"></a>
          <h3 class="gb-headline">공감만세, 지역 관광 투자 유치</h3>
          <p class="gb-headline excerpt">공정여행 스타트업 공감만세가 신규 투자를 유치했다.</p>
        </div>
    """

    result = crawl_sources(
        targets=[
            {
                "url": "https://platum.kr/archives/category/investment",
                "source_kind": "platum_investment_news",
                "portfolio_companies": ["공감만세(주)"],
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        fetch_url=lambda url: first_page_html,
        fetch_platum_page=lambda url, page: second_page_html,
        run_id="run_platum_default_pages",
    )

    assert result.crawled_source_count == 1
    assert review_queue.published["Portfolio News"][0]["company"] == "공감만세"


def test_crawl_sources_clamps_platum_max_pages_from_sheet(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    page_calls: list[int] = []

    def fetch_platum_page(url: str, page: int) -> str:
        page_calls.append(page)
        return ""

    crawl_sources(
        targets=[
            {
                "url": "https://platum.kr/archives/category/investment",
                "source_kind": "platum_investment_news",
                "portfolio_companies": ["공감만세(주)"],
                "max_pages": 5000,
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        fetch_url=lambda url: "",
        fetch_platum_page=fetch_platum_page,
        run_id="run_platum_clamped_pages",
    )

    assert page_calls == list(range(2, 51))


def test_crawl_sources_preserves_multiple_portfolio_matches_for_same_platum_url(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()
    html = """
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/286555"></a>
          <h3 class="gb-headline">공감만세와 리소리우스, 임팩트 투자 유치</h3>
          <p class="gb-headline excerpt">공감만세와 리소리우스가 후속 투자를 유치했다.</p>
        </div>
    """

    result = crawl_sources(
        targets=[
            {
                "url": "https://platum.kr/archives/category/investment",
                "source_kind": "platum_investment_news",
                "portfolio_companies": ["공감만세(주)", "(주)리소리우스"],
                "max_pages": 1,
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        fetch_url=lambda url: html,
        run_id="run_platum_multi_company",
    )

    assert result.crawled_source_count == 2
    assert [row["company"] for row in review_queue.published["Portfolio News"]] == ["공감만세", "리소리우스"]


def test_crawl_sources_records_platum_pagination_fetch_warnings(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()

    def fetch_platum_page(url: str, page: int) -> str:
        raise CrawlFetchError("blocked")

    result = crawl_sources(
        targets=[
            {
                "url": "https://platum.kr/archives/category/investment",
                "source_kind": "platum_investment_news",
                "portfolio_companies": ["공감만세(주)"],
                "max_pages": 2,
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        fetch_url=lambda url: "",
        fetch_platum_page=fetch_platum_page,
        run_id="run_platum_page_warning",
    )

    assert result.warning_count == 1
    assert "Platum pagination failed" in structured_store.tables["agent_runs"][0]["error_message"]


def test_crawl_sources_accepts_platum_investment_alias_from_runtime_env(tmp_path) -> None:
    object_store = FakeObjectStore(bucket="raw-bucket")
    structured_store = FakeStructuredStore()
    review_queue = FakeReviewQueue()
    html = """
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/286764"></a>
          <h3 class="gb-headline">비저너리, 카이스트청년창업투자지주로부터 시드 투자 유치</h3>
          <p class="gb-headline excerpt">공간 지능 데이터 소프트웨어 스타트업 비저너리가 총 8억 원 규모의 시드 투자를 유치했다.</p>
          <time class="entry-date published" datetime="2026-05-13T12:39:15+09:00">2026.05.13</time>
        </div>
    """

    result = crawl_sources(
        targets=[
            {
                "url": "https://platum.kr/archives/category/investment",
                "source_kind": "platum_investment",
                "portfolio_companies": ["(주)비저너리"],
            }
        ],
        object_store=object_store,
        structured_store=structured_store,
        review_queue=review_queue,
        fetch_url=lambda url: html,
        run_id="run_platum_alias",
    )

    assert result.crawled_source_count == 1
    assert structured_store.tables["raw_sources"][0]["channel"] == "platum_investment_news"
