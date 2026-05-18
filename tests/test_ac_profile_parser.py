import pytest

from merry_runtime.ingestion.ac_profile_parser import ACProfileParseError, parse_ac_hypothesis_report


def test_parse_ac_hypothesis_report_extracts_structured_profile_fields() -> None:
    report = """
    # AC Hypothesis Report

    AC ID: ac_climate_local
    AC Name: Climate Local Impact AC
    Fund Purpose: climate adaptation and rural resilience fund
    Recruiting Area: Jeonbuk
    Hypothesis Tags: climate, agritech; rural resilience
    Impact Priorities:
    - carbon
    - older farming household income
    Region Preferences: Jeonbuk, Gangwon
    Industry Preferences: AgriTech; ClimateTech
    Tech Preferences:
    - AI
    - remote sensing
    """

    profile = parse_ac_hypothesis_report(report)

    assert profile.ac_id == "ac_climate_local"
    assert profile.ac_name == "Climate Local Impact AC"
    assert profile.fund_purpose == "climate adaptation and rural resilience fund"
    assert profile.recruiting_area == "Jeonbuk"
    assert profile.hypothesis_tags == ("climate", "agritech", "rural resilience")
    assert profile.impact_priority == ("carbon", "older farming household income")
    assert profile.region_preferences == ("Jeonbuk", "Gangwon")
    assert profile.industry_preferences == ("AgriTech", "ClimateTech")
    assert profile.tech_preferences == ("AI", "remote sensing")


@pytest.mark.parametrize(
    ("report", "message"),
    [
        ("AC ID:\nFund Purpose: climate\nHypothesis Tags: climate", "AC ID"),
        ("AC ID: ac_empty\nFund Purpose:\nHypothesis Tags: climate", "Fund Purpose"),
        ("AC ID: ac_empty\nFund Purpose: climate\nImpact Priorities:", "hypothesis or impact"),
    ],
)
def test_parse_ac_hypothesis_report_rejects_useless_reports(report: str, message: str) -> None:
    with pytest.raises(ACProfileParseError, match=message):
        parse_ac_hypothesis_report(report)


def test_parse_ac_hypothesis_report_normalizes_tags_for_scoring_without_losing_readable_values() -> None:
    report = """
    AC ID: ac_health
    AC Name: Health Inclusion AC
    Fund Purpose: digital health equity
    Hypothesis Tags:  Digital Health, digital-health, health equity
    Impact Priorities: Patient Access; health equity
    """

    profile = parse_ac_hypothesis_report(report)

    assert profile.hypothesis_tags == ("digital health", "digital-health", "health equity")
    assert profile.impact_priority == ("Patient Access", "health equity")
