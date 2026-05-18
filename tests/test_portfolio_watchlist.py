from merry_runtime.portfolio_watchlist import build_portfolio_watchlist, matched_portfolio_names


def test_portfolio_watchlist_strips_corporate_designators_and_keeps_old_name_aliases() -> None:
    watchlist = build_portfolio_watchlist(["(주)테사(구.아트블록코리아)", "농업회사법인(주)시그널케어"])

    assert matched_portfolio_names("테사가 신규 투자를 유치했다.", watchlist) == ["테사"]
    assert matched_portfolio_names("아트블록코리아 시절부터 미술품 조각투자를 운영했다.", watchlist) == ["아트블록코리아"]
    assert matched_portfolio_names("시그널케어가 농식품 데이터 사업을 확장했다.", watchlist) == ["시그널케어"]


def test_portfolio_watchlist_does_not_match_short_keyword_inside_longer_word() -> None:
    watchlist = build_portfolio_watchlist(["클리(주)"])

    assert matched_portfolio_names("삶 클리닉이 시드 투자를 유치했다.", watchlist) == []
    assert matched_portfolio_names("클리, 신규 서비스 출시", watchlist) == ["클리"]
