import json
from pathlib import Path

from merry_runtime.ingestion.parsers import (
    parse_article,
    parse_email,
    parse_internal_memo,
    parse_referral_row,
    parse_thevc_investment_card,
)


FIXTURES = Path("tests/fixtures")


def test_article_parser_extracts_company_and_evidence() -> None:
    parsed = parse_article(FIXTURES.joinpath("hankyung_article.txt").read_text())

    assert parsed.entity.name == "CareFarm Carbon"
    assert parsed.entity.region == "Jeonbuk"
    assert parsed.raw_source.channel == "hankyung_ceo_interview"
    assert any(signal.signal_type == "impact" for signal in parsed.signals)
    assert parsed.signals[0].source_id == parsed.raw_source.source_id


def test_email_parser_redacts_pii_from_evidence() -> None:
    parsed = parse_email(FIXTURES.joinpath("info_mail.txt").read_text())

    assert parsed.raw_source.channel == "info_mail"
    assert parsed.raw_source.contains_pii is True
    assert "[REDACTED_EMAIL]" in parsed.signals[0].evidence_text
    assert "[REDACTED_PHONE]" in parsed.signals[0].evidence_text


def test_referral_parser_preserves_channel_meaning() -> None:
    parsed = parse_referral_row(json.loads(FIXTURES.joinpath("referral_row.json").read_text()))

    assert parsed.raw_source.channel == "external_referral"
    assert parsed.entity.name == "Merry AI"
    assert parsed.signals[0].tags == ("ai", "impact", "automation")


def test_internal_memo_parser_extracts_impact_signal() -> None:
    parsed = parse_internal_memo(FIXTURES.joinpath("internal_memo.txt").read_text())

    assert parsed.raw_source.channel == "internal_screening_memo"
    assert parsed.entity.name == "Local Care Grid"
    assert parsed.signals[0].signal_type == "impact"


def test_thevc_investment_parser_preserves_public_investment_signal() -> None:
    parsed = parse_thevc_investment_card(
        "\n".join(
            [
                "Title: THE VC Investment/M&A - 에이아이오 낸드컨트롤러",
                "URL: https://thevc.kr/",
                "Source URI: https://thevc.kr/aio",
                "Company: 에이아이오",
                "Industry: 반도체/디스플레이",
                "Published: 2026-05-15",
                "Signal: investment",
                "Confidence: 0.65",
                "Tags: thevc_investment_ma, public_cold_lead, investment, fresh",
                "Evidence: THE VC 투자/M&A 공개 카드",
            ]
        )
    )

    assert parsed.raw_source.channel == "thevc_investment_ma"
    assert parsed.raw_source.source_type == "web_listing"
    assert parsed.raw_source.uri == "https://thevc.kr/aio"
    assert parsed.entity.name == "에이아이오"
    assert parsed.signals[0].signal_type == "investment"
