from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse


_LEGAL_SUFFIX_PATTERN = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|labs?|gmbh|plc)\b\.?",
    re.IGNORECASE,
)
_KOREAN_LEGAL_PATTERN = re.compile(r"\(주\)|㈜|주식회사")
_PUNCTUATION_PATTERN = re.compile(r"[,/&+._()\-]+")
_SPACE_PATTERN = re.compile(r"\s+")


def normalize_company_name(name: str | None) -> str:
    if not name:
        return ""

    value = unicodedata.normalize("NFKC", name).casefold().strip()
    value = _KOREAN_LEGAL_PATTERN.sub(" ", value)
    value = _PUNCTUATION_PATTERN.sub(" ", value)
    value = _LEGAL_SUFFIX_PATTERN.sub(" ", value)
    value = _SPACE_PATTERN.sub(" ", value).strip()
    return value


def normalize_domain(homepage: str | None) -> str:
    if not homepage:
        return ""

    value = homepage.strip()
    parsed = urlparse(value if "://" in value else f"//{value}")
    host = parsed.netloc or parsed.path.split("/", 1)[0]
    host = host.split("@")[-1].split(":", 1)[0].casefold().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def normalized_region(region: str | None) -> str:
    return _SPACE_PATTERN.sub(" ", unicodedata.normalize("NFKC", region or "").casefold()).strip()
