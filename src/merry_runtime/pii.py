from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PIIFinding:
    kind: str
    value: str
    start: int
    end: int


_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"\b(?:\+82[-.\s]?)?0?1[016789][-.\s]?\d{3,4}[-.\s]?\d{4}\b")


def detect_pii(text: str) -> list[PIIFinding]:
    findings: list[PIIFinding] = []
    for match in _EMAIL_PATTERN.finditer(text):
        findings.append(PIIFinding("email", match.group(0), match.start(), match.end()))
    for match in _PHONE_PATTERN.finditer(text):
        findings.append(PIIFinding("phone", match.group(0), match.start(), match.end()))
    return sorted(findings, key=lambda finding: finding.start)


def redact_pii(text: str) -> str:
    redacted = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    redacted = _PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)
    return redacted
