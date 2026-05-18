from merry_runtime.ingestion.thevc import extract_thevc_company_detail, extract_thevc_investment_sources


THEVC_HOME_HTML = """
<section>
  <h2>투자/M&amp;A</h2>
  <table>
    <tbody>
      <tr>
        <td><time datetime="2026-05-15T05:14:25.919Z">2026-05-15</time><button> 보도자료 </button></td>
        <td>
          <span class="text-default text-bold">에이아이오</span>
          <span class="ml-8 text-truncate">낸드컨트롤러</span>
          <div>낸드플래시가 데이터를 읽고 쓰도록 제어하는 시스템 반도체</div>
        </td>
        <td><div>투자대상분야</div><div>반도체/디스플레이</div></td>
        <td><div>투자단계</div><div>Pre-IPO</div></td>
        <td><div>투자금액</div><button>로그인 필요</button></td>
        <td><div>투자자</div><span>비엔더블유인베스트먼트</span></td>
        <td><a href="/aio">프로필 확인</a></td>
      </tr>
      <tr>
        <td><time datetime="2026-05-15T04:22:00.000Z">2026-05-15</time><button> 보도자료 </button></td>
        <td>
          <span class="text-default text-bold">넥스아이</span>
          <span class="ml-8 text-truncate">면역항암제</span>
          <div>불응성 유도 인자를 발굴하여 반응률을 높이는 면역항암제</div>
        </td>
        <td><div>투자대상분야</div><div>바이오/의료</div></td>
        <td><div>투자단계</div><div>Pre-IPO</div></td>
        <td><div>투자금액</div><button>로그인 필요</button></td>
        <td><div>투자자</div><span>디에스씨인베스트먼트</span><span>+13</span></td>
        <td><a href="/nex-i">프로필 확인</a></td>
      </tr>
    </tbody>
  </table>
</section>
"""


def test_extract_thevc_investment_sources_preserves_visible_card_fields() -> None:
    sources = extract_thevc_investment_sources(
        THEVC_HOME_HTML,
        source_url="https://thevc.kr/",
        fetch_detail_url=lambda url: """
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
                {"@type": "Person", "name": "권진형", "jobTitle": "경영 · 대표이사"},
                {"@type": "Person", "name": "백상열", "jobTitle": "경영 · 대표이사"}
              ]
            }
            </script>
        """
        if url == "https://thevc.kr/aio"
        else "",
    )

    assert len(sources) == 2
    assert sources[0]["channel"] == "thevc_investment_ma"
    assert "Company: 에이아이오" in sources[0]["payload"]
    assert "Product: 낸드컨트롤러" in sources[0]["payload"]
    assert "Business Model: 낸드컨트롤러 - 낸드플래시가 데이터를 읽고 쓰도록 제어하는 시스템 반도체" in sources[0]["payload"]
    assert "Industry: 반도체/디스플레이" in sources[0]["payload"]
    assert "Investment Round: Pre-IPO" in sources[0]["payload"]
    assert "Investor: 비엔더블유인베스트먼트" in sources[0]["payload"]
    assert "Source URI: https://thevc.kr/aio" in sources[0]["payload"]
    assert "Representative: 권진형∙백상열" in sources[0]["payload"]
    assert "Homepage: https://the-aio.com/" in sources[0]["payload"]
    assert "Region: 한국, 경기도, 용인시" in sources[0]["payload"]
    assert "Contact Email: hello@the-aio.com" in sources[0]["payload"]
    assert "Tags: thevc_investment_ma, public_cold_lead, investment, fresh, detail_enriched, industry:반도체/디스플레이, round:pre-ipo" in sources[0]["payload"]


def test_extract_thevc_investment_sources_ignores_non_investment_rows() -> None:
    html = "<tr><td>지원사업</td><td>인천상공회의소</td></tr>"

    sources = extract_thevc_investment_sources(html, source_url="https://thevc.kr/")

    assert sources == []


def test_extract_thevc_company_detail_falls_back_to_meta_description() -> None:
    detail = extract_thevc_company_detail(
        """
        <meta name="description" content="본사는 한국∙경기도∙용인시에 위치해있습니다. 현재 대표자는 권진형∙백상열입니다.">
        <div>홈페이지the-aio.com</div>
        <a href="mailto:contact@the-aio.com">문의</a>
        """
    )

    assert detail.representative == "권진형∙백상열"
    assert detail.homepage == "https://the-aio.com"
    assert detail.region == "한국, 경기도, 용인시"
    assert detail.contact_email == "contact@the-aio.com"


def test_extract_thevc_company_detail_reads_homepage_anchor() -> None:
    detail = extract_thevc_company_detail(
        """
        <a href="https://the-aio.com/?ref=thevc">
          <img alt="웹사이트 아이콘"> 홈페이지
        </a>
        <a href="https://www.thebell.co.kr/free/content/ArticleView.asp?key=1">기사</a>
        """
    )

    assert detail.homepage == "https://the-aio.com/"


def test_extract_thevc_investment_sources_uses_homepage_contact_fallback_for_email() -> None:
    def fetch_detail_url(url: str) -> str:
        if url == "https://thevc.kr/aio":
            return """
                <script type="application/ld+json">
                {
                  "@type": "Organization",
                  "sameAs": ["https://the-aio.com/"],
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
        if url == "https://the-aio.com/":
            return "<html><body>Contact us: hello@the-aio.com</body></html>"
        return ""

    sources = extract_thevc_investment_sources(
        THEVC_HOME_HTML,
        source_url="https://thevc.kr/",
        fetch_detail_url=fetch_detail_url,
    )

    assert "Contact Email: hello@the-aio.com" in sources[0]["payload"]


def test_extract_thevc_company_detail_does_not_treat_company_type_as_homepage() -> None:
    detail = extract_thevc_company_detail(
        """
        <div>홈페이지</div>
        <div>주식회사</div>
        <meta name="description" content="본사는 한국∙서울특별시에 위치해있습니다. 현재 대표자는 장영휘입니다.">
        """
    )

    assert detail.homepage == ""
    assert detail.representative == "장영휘"


def test_extract_thevc_company_detail_ignores_thevc_platform_email() -> None:
    detail = extract_thevc_company_detail('<a href="mailto:master@thevc.kr">THE VC</a>')

    assert detail.contact_email == ""


def test_extract_thevc_company_detail_ignores_social_links_before_homepage() -> None:
    detail = extract_thevc_company_detail(
        """
        <script type="application/ld+json">
        {
          "@type": "Organization",
          "sameAs": [
            "https://www.linkedin.com/company/the-aio",
            "https://facebook.com/theaio",
            "https://the-aio.com/"
          ]
        }
        </script>
        """
    )

    assert detail.homepage == "https://the-aio.com/"


def test_extract_thevc_company_detail_prefers_json_ld_url_over_social_same_as() -> None:
    detail = extract_thevc_company_detail(
        """
        <script type="application/ld+json">
        {
          "@type": "Organization",
          "url": "https://the-aio.com/",
          "sameAs": [
            "https://www.linkedin.com/company/the-aio",
            "https://facebook.com/theaio"
          ],
          "email": ["master@thevc.kr", "hello@the-aio.com"]
        }
        </script>
        """
    )

    assert detail.homepage == "https://the-aio.com/"
    assert detail.contact_email == "hello@the-aio.com"
