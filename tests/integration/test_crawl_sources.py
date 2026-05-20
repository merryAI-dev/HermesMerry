from datetime import UTC, datetime

from merry_runtime.adapters.fakes import FakeNotifier, FakeObjectStore, FakeReviewQueue, FakeStructuredStore
from merry_runtime.ingestion.sminfo_queue import build_sminfo_task
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

    for run_id in ("run_first", "run_second"):
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
            run_id=run_id,
        )

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
    assert portfolio_news["notified_at"] == ""
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
