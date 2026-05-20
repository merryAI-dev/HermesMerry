from __future__ import annotations

import re
from dataclasses import dataclass


_PROVINCE_ALIASES = {
    "서울특별시": "서울",
    "부산광역시": "부산",
    "대구광역시": "대구",
    "인천광역시": "인천",
    "광주광역시": "광주",
    "대전광역시": "대전",
    "울산광역시": "울산",
    "세종특별자치시": "세종",
    "경기도": "경기",
    "강원특별자치도": "강원",
    "강원도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "전북특별자치도": "전북",
    "전라북도": "전북",
    "전라남도": "전남",
    "경상북도": "경북",
    "경상남도": "경남",
    "제주특별자치도": "제주",
}

_LOCATION_ONLY_RULE_1 = ("전주시", "경북", "청도군", "남해군", "영암군")
_AMBIGUOUS_LOCALITIES = {"동구", "서구", "남구", "고성군"}
_SOCIAL_ECONOMY_KEYWORDS = (
    "사회적경제",
    "사회적기업",
    "예비사회적기업",
    "협동조합",
    "사회적협동조합",
    "마을기업",
    "자활기업",
    "소셜벤처",
)

_POPULATION_DECLINE_AREAS = {
    "부산": ("동구", "서구", "영도구"),
    "대구": ("남구", "서구", "군위군"),
    "인천": ("강화군", "옹진군"),
    "경기": ("가평군", "연천군"),
    "강원": (
        "고성군",
        "삼척시",
        "양구군",
        "양양군",
        "영월군",
        "정선군",
        "철원군",
        "태백시",
        "평창군",
        "홍천군",
        "화천군",
        "횡성군",
    ),
    "충북": ("괴산군", "단양군", "보은군", "영동군", "옥천군", "제천시"),
    "충남": ("공주시", "금산군", "논산시", "보령시", "부여군", "서천군", "예산군", "청양군", "태안군"),
    "전북": ("고창군", "김제시", "남원시", "무주군", "부안군", "순창군", "임실군", "장수군", "정읍시", "진안군"),
    "전남": (
        "강진군",
        "고흥군",
        "곡성군",
        "구례군",
        "담양군",
        "보성군",
        "신안군",
        "영광군",
        "영암군",
        "완도군",
        "장성군",
        "장흥군",
        "진도군",
        "함평군",
        "해남군",
        "화순군",
    ),
    "경북": (
        "고령군",
        "문경시",
        "봉화군",
        "상주시",
        "성주군",
        "안동시",
        "영덕군",
        "영양군",
        "영주시",
        "영천시",
        "울릉군",
        "울진군",
        "의성군",
        "청도군",
        "청송군",
    ),
    "경남": ("거창군", "고성군", "남해군", "밀양시", "산청군", "의령군", "창녕군", "하동군", "함안군", "함양군", "합천군"),
}


@dataclass(frozen=True, slots=True)
class _RuleMatch:
    rule: str
    detail: str
    requires_social_economy: bool = False


def evaluate_p1_regional_priority(
    *,
    region: str = "",
    road_address: str = "",
    business_model: str = "",
    industry: str = "",
    company_type: str = "",
    main_products: str = "",
    standard_industry: str = "",
) -> dict[str, str]:
    """Evaluate P1 regional markings for the operator Candidate Detail sheet."""
    location_text = _normalize_region_text(region, road_address)
    purpose_text = _normalize_spacing(" ".join((business_model, industry, company_type, main_products, standard_industry)))
    matches = _location_matches(location_text)

    social_keywords = [keyword for keyword in _SOCIAL_ECONOMY_KEYWORDS if keyword in purpose_text]
    has_location_only_match = any(not match.requires_social_economy for match in matches)
    has_social_rule = any(match.requires_social_economy for match in matches)

    if social_keywords:
        purpose_match = "Y" if matches else "N"
        purpose_detail = "사회적경제 키워드: " + ", ".join(dict.fromkeys(social_keywords))
    elif has_location_only_match:
        purpose_match = "Y"
        purpose_detail = "소재지 단독 기준 해당"
        if has_social_rule:
            purpose_detail += "; 경기도 사회적경제조직 여부 확인필요"
    elif has_social_rule:
        purpose_match = "확인필요"
        purpose_detail = "경기도 소재 확인, 사회적경제조직 여부 확인필요"
    else:
        purpose_match = "N"
        purpose_detail = ""

    return {
        "p1_region_match": "Y" if matches else "N",
        "p1_region_rule": "; ".join(dict.fromkeys(match.rule for match in matches)),
        "p1_region_detail": "; ".join(dict.fromkeys(match.detail for match in matches)),
        "p1_purpose_match": purpose_match,
        "p1_purpose_detail": purpose_detail,
    }


def _location_matches(location_text: str) -> list[_RuleMatch]:
    matches: list[_RuleMatch] = []

    rule_1_details = _specific_region_rule_details(location_text)
    if rule_1_details:
        matches.append(_RuleMatch(rule="1_특정지역_4000백만원이상", detail=", ".join(rule_1_details)))

    if "경기" in location_text:
        matches.append(_RuleMatch(rule="2_경기도_사회적경제", detail="경기", requires_social_economy=True))

    if "과천시" in location_text:
        matches.append(_RuleMatch(rule="3_과천시", detail="과천시"))

    if "제주" in location_text:
        matches.append(_RuleMatch(rule="4_제주", detail="제주"))

    population_decline_details = _population_decline_details(location_text)
    if population_decline_details:
        matches.append(_RuleMatch(rule="5_인구감소지역", detail=", ".join(population_decline_details)))

    return matches


def _specific_region_rule_details(location_text: str) -> list[str]:
    details: list[str] = []
    for token in _LOCATION_ONLY_RULE_1:
        if token == "경북" and "경북" in location_text:
            details.append("경북")
        elif token != "경북" and token in location_text:
            details.append(token)
    return list(dict.fromkeys(details))


def _population_decline_details(location_text: str) -> list[str]:
    details: list[str] = []
    for province, localities in _POPULATION_DECLINE_AREAS.items():
        province_present = province in location_text
        for locality in localities:
            if locality not in location_text:
                continue
            if province_present:
                details.append(f"{province} {locality}")
            elif locality not in _AMBIGUOUS_LOCALITIES:
                details.append(locality)
    return list(dict.fromkeys(details))


def _normalize_region_text(*values: str) -> str:
    text = _normalize_spacing(" ".join(value for value in values if value))
    for full_name, short_name in _PROVINCE_ALIASES.items():
        text = text.replace(full_name, short_name)
    return text


def _normalize_spacing(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace(",", " ")).strip()
