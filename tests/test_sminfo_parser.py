from merry_runtime.ingestion.sminfo import (
    SminfoSearchResult,
    choose_sminfo_search_result,
    parse_sminfo_profile_tables,
)


def test_choose_sminfo_search_result_uses_representative_to_break_same_name_ties() -> None:
    result = choose_sminfo_search_result(
        requested_company="에이아이오",
        candidate={"representative": "권진형∙백상열", "region": "경기"},
        results=[
            SminfoSearchResult(
                company_name="(주)에이아이오",
                representative="권진형",
                company_type="외감",
                industry="전기용 기계·장비 및 관련 기자재 도매업",
                road_address="경기 용인시 수지구 신수로",
                result_index=0,
            ),
            SminfoSearchResult(
                company_name="(주)에이아이오",
                representative="안태원",
                company_type="일반법인",
                industry="응용 소프트웨어 개발 및 공급업",
                road_address="울산 중구 도화골4길",
                result_index=1,
            ),
        ],
    )

    assert result.status == "matched"
    assert result.result is not None
    assert result.result.representative == "권진형"


def test_choose_sminfo_search_result_marks_unresolved_duplicate_names_as_ambiguous() -> None:
    result = choose_sminfo_search_result(
        requested_company="에이아이오",
        candidate={},
        results=[
            SminfoSearchResult(
                company_name="(주)에이아이오",
                representative="권진형",
                company_type="외감",
                industry="전기용 기계·장비 및 관련 기자재 도매업",
                road_address="경기 용인시 수지구 신수로",
                result_index=0,
            ),
            SminfoSearchResult(
                company_name="(주)에이아이오",
                representative="안태원",
                company_type="일반법인",
                industry="응용 소프트웨어 개발 및 공급업",
                road_address="울산 중구 도화골4길",
                result_index=1,
            ),
        ],
    )

    assert result.status == "ambiguous"
    assert result.result is None


def test_parse_sminfo_profile_tables_extracts_basic_profile_and_latest_financials() -> None:
    profile = parse_sminfo_profile_tables(
        requested_company="에이아이오",
        sminfo_url="https://sminfo.mss.go.kr/si/ei/IEI001R0.do?cmd=com&kcd=0007451769",
        tables=[
            {
                "caption": "기업프로필정보",
                "rows": [
                    ["기업명", "(주)에이아이오", "대표자명", "권진형"],
                    ["기업형태", "법인 또는 기타사업자", "설립일", "2011-05-13"],
                    ["주소(도로명)", "경기 용인시 수지구 신수로 767"],
                    ["홈페이지", "www.the-aio.com", "주생산품", "낸드 플래시 컨트롤러 F/W 설계 등"],
                    ["표준산업", "전기용 기계·장비 및 관련 기자재 도매업", "정보수정일자", "2026-05-18"],
                    ["미수집필드", "저장하면 안 되는 값"],
                ],
            },
            {
                "caption": "매출현황",
                "rows": [
                    ["결산년도", "총자산", "자본금", "자본총계", "매출액", "영업이익", "당기순이익"],
                    ["2025-12-31", "27,096,382", "32,342,619", "-55,546,710", "17,851,006", "-13,097,004", "-19,903,884"],
                ],
            },
        ],
    )

    assert profile.match_status == "matched"
    assert profile.matched_company == "(주)에이아이오"
    assert profile.representative == "권진형"
    assert profile.company_type == "법인 또는 기타사업자"
    assert profile.established_at == "2011-05-13"
    assert profile.road_address == "경기 용인시 수지구 신수로 767"
    assert profile.homepage == "www.the-aio.com"
    assert profile.main_products == "낸드 플래시 컨트롤러 F/W 설계 등"
    assert profile.standard_industry == "전기용 기계·장비 및 관련 기자재 도매업"
    assert profile.info_updated_at == "2026-05-18"
    assert profile.latest_financial_year == "2025-12-31"
    assert profile.revenue_krw_thousand == "17851006"
    assert profile.operating_income_krw_thousand == "-13097004"
    assert profile.net_income_krw_thousand == "-19903884"
    assert profile.total_assets_krw_thousand == "27096382"
    assert "저장하면 안 되는 값" not in str(profile.raw_payload)
