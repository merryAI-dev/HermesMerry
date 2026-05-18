from merry_runtime.adapters.fakes import FakeObjectStore, FakeReviewQueue, FakeStructuredStore
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
    assert result.ingested_entity_count == 1
    assert structured_store.tables["mother_entities"][0]["name"] == "에이아이오"
    assert structured_store.tables["mother_entities"][0]["representative"] == "권진형"
    assert structured_store.tables["mother_entities"][0]["homepage"] == "https://the-aio.com/"
    assert structured_store.tables["mother_entities"][0]["region"] == "한국, 경기도, 용인시"
    assert structured_store.tables["mother_entities"][0]["contact_email"] == "hello@the-aio.com"
    assert structured_store.tables["signals"][0]["signal_type"] == "investment"
    assert structured_store.tables["raw_sources"][0]["channel"] == "thevc_investment_ma"
    assert review_queue.published["Evidence"][0]["channel"] == "thevc_investment_ma"
    assert review_queue.published["Candidate Detail"][0]["company"] == "에이아이오"
    assert review_queue.published["Candidate Detail"][0]["contact_email"] == "hello@the-aio.com"
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
