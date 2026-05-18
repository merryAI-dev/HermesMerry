from merry_runtime.ingestion.platum import extract_platum_portfolio_news_sources
from merry_runtime.portfolio_watchlist import build_portfolio_watchlist


def test_extract_platum_portfolio_news_sources_matches_watchlist_companies_only() -> None:
    html = """
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/286764"></a>
          <h3 class="gb-headline">비저너리, 카이스트청년창업투자지주로부터 시드 투자 유치</h3>
          <p class="gb-headline excerpt">공간 지능 데이터 소프트웨어 스타트업 비저너리가 총 8억 원 규모의 시드 투자를 유치했다.</p>
          <time class="entry-date published" datetime="2026-05-13T12:39:15+09:00">2026.05.13</time>
        </div>
        <div class="gb-grid-column gb-query-loop-item">
          <a class="gb-container-link" href="https://platum.kr/archives/286770"></a>
          <h3 class="gb-headline">삶 클리닉, AI엔젤클럽으로부터 시드 투자 유치</h3>
          <p class="gb-headline excerpt">AI 기반 정신건강 데이터 플랫폼 삶 클리닉이 투자를 유치했다.</p>
          <time class="entry-date published" datetime="2026-05-13T12:56:24+09:00">2026.05.13</time>
        </div>
    """
    watchlist = build_portfolio_watchlist(["(주)비저너리", "클리(주)"])

    sources = extract_platum_portfolio_news_sources(
        html,
        source_url="https://platum.kr/archives/category/investment",
        watchlist=watchlist,
        max_articles=10,
    )

    assert len(sources) == 1
    assert sources[0]["channel"] == "platum_investment_news"
    payload = sources[0]["payload"]
    assert "Company: 비저너리" in payload
    assert "Title: 비저너리, 카이스트청년창업투자지주로부터 시드 투자 유치" in payload
    assert "URL: https://platum.kr/archives/286764" in payload
    assert "Published: 2026-05-13T12:39:15+09:00" in payload
    assert "삶 클리닉" not in payload
