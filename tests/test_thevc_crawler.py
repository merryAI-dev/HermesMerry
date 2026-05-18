from merry_runtime.ingestion.thevc import extract_thevc_investment_sources


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
    sources = extract_thevc_investment_sources(THEVC_HOME_HTML, source_url="https://thevc.kr/")

    assert len(sources) == 2
    assert sources[0]["channel"] == "thevc_investment_ma"
    assert "Company: 에이아이오" in sources[0]["payload"]
    assert "Product: 낸드컨트롤러" in sources[0]["payload"]
    assert "Industry: 반도체/디스플레이" in sources[0]["payload"]
    assert "Investment Round: Pre-IPO" in sources[0]["payload"]
    assert "Investor: 비엔더블유인베스트먼트" in sources[0]["payload"]
    assert "Source URI: https://thevc.kr/aio" in sources[0]["payload"]
    assert "Tags: thevc_investment_ma, public_cold_lead, investment, fresh, industry:반도체/디스플레이, round:pre-ipo" in sources[0]["payload"]


def test_extract_thevc_investment_sources_ignores_non_investment_rows() -> None:
    html = "<tr><td>지원사업</td><td>인천상공회의소</td></tr>"

    sources = extract_thevc_investment_sources(html, source_url="https://thevc.kr/")

    assert sources == []
