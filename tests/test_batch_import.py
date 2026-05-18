import pytest

from merry_runtime.ingestion.batch_import import (
    ALLOWED_CHANNELS,
    CandidateBatchValidationError,
    parse_candidate_batch_csv,
)
from merry_runtime.ingestion.parsers import parse_email, parse_referral_row


HEADER = "company,brand,representative,homepage,region,industry,channel,evidence,confidence,tags,source_uri"


def _csv(*rows: str) -> str:
    return "\n".join((HEADER, *rows))


def test_parse_candidate_batch_csv_requires_strict_columns() -> None:
    csv_text = "company,homepage,channel,evidence\nMerry AI,https://merry.ai,external_referral,Referral"

    with pytest.raises(CandidateBatchValidationError, match="missing required columns"):
        parse_candidate_batch_csv(csv_text)


def test_parse_candidate_batch_csv_rejects_unknown_channel() -> None:
    csv_text = _csv(
        "Merry AI,Merry,Kim,https://merry.ai,Seoul,AI,unknown_channel,Referral,0.8,ai,drive://row-1"
    )

    with pytest.raises(CandidateBatchValidationError, match="unknown discovery channel"):
        parse_candidate_batch_csv(csv_text)


def test_parse_candidate_batch_csv_redacts_evidence_before_source_conversion() -> None:
    csv_text = _csv(
        "Merry AI,Merry,Kim,https://merry.ai,Seoul,AI,info_mail,"
        "Contact founder@merry.ai or 010-1234-5678,0.8,ai,gmail://message-1"
    )

    batch = parse_candidate_batch_csv(csv_text)

    source = batch.sources[0]
    assert source["channel"] == "info_mail"
    assert "founder@merry.ai" not in source["payload"]
    assert "010-1234-5678" not in source["payload"]
    assert "[REDACTED_EMAIL]" in source["payload"]
    assert "[REDACTED_PHONE]" in source["payload"]


def test_parse_candidate_batch_csv_preserves_known_channel_and_source_uri() -> None:
    csv_text = _csv(
        "Merry AI,Merry,Kim,https://merry.ai,Seoul,AI,external_referral,Referral,0.8,ai,drive://exports/batch.csv#row=2"
    )

    batch = parse_candidate_batch_csv(csv_text)

    assert ALLOWED_CHANNELS == {
        "hankyung_ceo_interview",
        "info_mail",
        "external_referral",
        "internal_screening_memo",
    }
    assert batch.row_count == 1
    assert batch.sources[0]["channel"] == "external_referral"
    assert batch.sources[0]["payload"]["source_uri"] == "drive://exports/batch.csv#row=2"
    assert batch.quality_report.passed is True


def test_parse_candidate_batch_csv_normalizes_semicolon_tags_for_existing_ingest_parsers() -> None:
    csv_text = _csv(
        "Merry AI,Merry,Kim,https://merry.ai,Seoul,AI,external_referral,Referral,0.8,ai; impact,drive://exports/batch.csv#row=2"
    )

    batch = parse_candidate_batch_csv(csv_text)

    assert batch.sources[0]["payload"]["tags"] == "ai, impact"


def test_parse_candidate_batch_csv_reports_duplicate_homepage_conflict_rate() -> None:
    rows = [
        f"ConflictCo,Conflict,{index},https://conflict-{index % 2}.example,Seoul,AI,external_referral,Evidence,0.7,ai,drive://row-{index}"
        for index in range(6)
    ]
    rows.extend(
        f"Candidate {index},Brand {index},Rep {index},https://candidate-{index}.example,Seoul,AI,external_referral,Evidence,0.7,ai,drive://row-{index}"
        for index in range(6, 100)
    )

    batch = parse_candidate_batch_csv(_csv(*rows))

    assert batch.quality_report.passed is False
    assert batch.quality_report.conflicting_row_count == 6
    assert batch.quality_report.conflict_rate == pytest.approx(0.06)
    assert batch.quality_report.duplicate_conflicts == [
        {
            "normalized_company": "conflictco",
            "row_numbers": [2, 3, 4, 5, 6, 7],
            "homepages": ["https://conflict-0.example", "https://conflict-1.example"],
        }
    ]


def test_source_parsers_preserve_source_uri_and_representative_for_batch_rows() -> None:
    referral = parse_referral_row(
        {
            "company": "Merry AI",
            "representative": "Kim Boram",
            "homepage": "https://merry.ai",
            "region": "Seoul",
            "industry": "AI",
            "evidence": "Curated referral",
            "source_uri": "drive://exports/referrals.csv#row=2",
        }
    )

    email = parse_email(
        "\n".join(
            [
                "Subject: Curated info mail",
                "From: info@merry.ai",
                "Company: Merry AI",
                "Representative: Kim Boram",
                "Homepage: https://merry.ai",
                "Source_URI: gmail://message-1",
                "Evidence: Curated info mail",
            ]
        )
    )

    assert referral.raw_source.uri == "drive://exports/referrals.csv#row=2"
    assert referral.entity.representative == "Kim Boram"
    assert email.raw_source.uri == "gmail://message-1"
    assert email.entity.representative == "Kim Boram"
