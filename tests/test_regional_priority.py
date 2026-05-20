from merry_runtime.regional_priority import evaluate_p1_regional_priority


def test_p1_regional_priority_matches_specific_regions_and_population_decline() -> None:
    result = evaluate_p1_regional_priority(region="한국, 경상북도, 청도군")

    assert result["p1_region_match"] == "Y"
    assert "1_특정지역_4000백만원이상" in result["p1_region_rule"]
    assert "5_인구감소지역" in result["p1_region_rule"]
    assert "경북" in result["p1_region_detail"]
    assert "청도군" in result["p1_region_detail"]
    assert result["p1_purpose_match"] == "Y"


def test_p1_regional_priority_marks_gyeonggi_social_economy_as_review_needed() -> None:
    result = evaluate_p1_regional_priority(region="한국, 경기도, 용인시")

    assert result["p1_region_match"] == "Y"
    assert result["p1_region_rule"] == "2_경기도_사회적경제"
    assert result["p1_region_detail"] == "경기"
    assert result["p1_purpose_match"] == "확인필요"
    assert "사회적경제조직 여부 확인필요" in result["p1_purpose_detail"]


def test_p1_regional_priority_confirms_gyeonggi_social_enterprise_keywords() -> None:
    result = evaluate_p1_regional_priority(region="경기도 과천시", company_type="사회적협동조합")

    assert result["p1_region_match"] == "Y"
    assert "2_경기도_사회적경제" in result["p1_region_rule"]
    assert "3_과천시" in result["p1_region_rule"]
    assert result["p1_purpose_match"] == "Y"
    assert "사회적협동조합" in result["p1_purpose_detail"]


def test_p1_regional_priority_avoids_ambiguous_district_without_province() -> None:
    result = evaluate_p1_regional_priority(region="서구")

    assert result["p1_region_match"] == "N"
    assert result["p1_region_rule"] == ""
    assert result["p1_purpose_match"] == "N"


def test_p1_regional_priority_matches_jeju_and_ignores_nonmatching_seoul() -> None:
    jeju = evaluate_p1_regional_priority(region="제주특별자치도 제주시")
    seoul = evaluate_p1_regional_priority(region="서울특별시 강남구")

    assert jeju["p1_region_match"] == "Y"
    assert jeju["p1_region_rule"] == "4_제주"
    assert seoul["p1_region_match"] == "N"
