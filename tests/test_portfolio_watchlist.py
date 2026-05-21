from merry_runtime.portfolio_watchlist import (
    build_portfolio_watchlist,
    build_portfolio_watchlist_from_rows,
    matched_portfolio_names,
)


def test_portfolio_watchlist_strips_corporate_designators_and_keeps_old_name_aliases() -> None:
    watchlist = build_portfolio_watchlist(["(주)테사(구.아트블록코리아)", "농업회사법인(주)시그널케어"])

    assert matched_portfolio_names("테사가 신규 투자를 유치했다.", watchlist) == ["테사"]
    assert matched_portfolio_names("아트블록코리아 시절부터 미술품 조각투자를 운영했다.", watchlist) == ["아트블록코리아"]
    assert matched_portfolio_names("시그널케어가 농식품 데이터 사업을 확장했다.", watchlist) == ["시그널케어"]


def test_portfolio_watchlist_does_not_match_short_keyword_inside_longer_word() -> None:
    watchlist = build_portfolio_watchlist(["클리(주)"])

    assert matched_portfolio_names("삶 클리닉이 시드 투자를 유치했다.", watchlist) == []
    assert matched_portfolio_names("클리, 신규 서비스 출시", watchlist) == ["클리"]


def test_portfolio_watchlist_builds_active_sheet_rows_with_aliases_and_dedupes() -> None:
    watchlist = build_portfolio_watchlist_from_rows(
        [
            {
                "company": "에이아이박스 주식회사",
                "aliases": "AI Box\n에이아이박스(주)",
                "status": "active",
            },
            {"company": "에이아이박스(주)", "status": "active"},
            {"company": "에코 테스트", "status": "inactive"},
            {
                "company": "또리노리/공공주택알리미",
                "aliases": "공공주택알리미",
                "status": "",
            },
        ]
    )

    assert [keyword.display_name for keyword in watchlist] == [
        "에이아이박스",
        "AI Box",
        "또리노리/공공주택알리미",
        "공공주택알리미",
    ]
    assert matched_portfolio_names("AI Box와 공공주택알리미의 신규 소식", watchlist) == [
        "AI Box",
        "공공주택알리미",
    ]
    assert matched_portfolio_names("에코 테스트가 서비스를 출시했다.", watchlist) == []


def test_sheet_watchlist_does_not_infer_parenthetical_aliases() -> None:
    watchlist = build_portfolio_watchlist_from_rows(
        [
            {"company": "두이(DOOY)", "aliases": "", "status": "active"},
            {"company": "한이음(HANEUM)", "aliases": "한이음", "status": "active"},
        ]
    )

    assert [keyword.display_name for keyword in watchlist] == ["두이", "한이음"]
    assert matched_portfolio_names("DOOY가 신규 서비스를 출시했다.", watchlist) == []
    assert matched_portfolio_names("두이가 신규 서비스를 출시했다.", watchlist) == ["두이"]
