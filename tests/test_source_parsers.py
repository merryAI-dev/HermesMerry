import json
from pathlib import Path

from merry_runtime.ingestion.parsers import parse_article, parse_email, parse_internal_memo, parse_referral_row


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
