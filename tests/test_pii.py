from merry_runtime.pii import detect_pii, redact_pii


def test_detects_email_and_korean_phone_number() -> None:
    findings = detect_pii("Founder: min@example.com / 010-1234-5678")

    assert {finding.kind for finding in findings} == {"email", "phone"}


def test_redacts_pii_before_llm_summary_payloads() -> None:
    redacted = redact_pii("Founder: min@example.com / 010-1234-5678")

    assert "min@example.com" not in redacted
    assert "010-1234-5678" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
