from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_DESIGNATOR_PATTERNS = (
    r"\(주\)",
    r"㈜",
    r"주식회사",
    r"농업회사법인",
    r"유한회사",
    r"회사법인",
    r"\binc\.?\b",
    r"\bjoint\s+stock\s+company\b",
    r"\bcompany\s+limited\b",
    r"\bpte\.?\s*ltd\.?\b",
    r"\bgmbh\b",
    r"\bl\.?p\.?\b",
)
_DESIGNATOR_RE = re.compile("|".join(_DESIGNATOR_PATTERNS), re.IGNORECASE)
_TOKEN_BOUNDARY_CHARS = r"0-9A-Za-z가-힣"
_KOREAN_PARTICLES = "이가은는을를의와과도"


@dataclass(frozen=True, slots=True)
class PortfolioKeyword:
    display_name: str
    normalized_name: str


def load_portfolio_watchlist(path: str | Path) -> tuple[PortfolioKeyword, ...]:
    raw_names = Path(path).read_text(encoding="utf-8").splitlines()
    return build_portfolio_watchlist(raw_names)


def build_portfolio_watchlist(raw_names: list[str] | tuple[str, ...]) -> tuple[PortfolioKeyword, ...]:
    seen: set[str] = set()
    keywords: list[PortfolioKeyword] = []
    for raw_name in raw_names:
        for alias in _aliases(raw_name):
            display_name = _clean_display_name(alias)
            normalized_name = _normalize_for_substring_match(display_name)
            if len(normalized_name) < 2 or normalized_name in seen:
                continue
            seen.add(normalized_name)
            keywords.append(PortfolioKeyword(display_name=display_name, normalized_name=normalized_name))
    return tuple(keywords)


def matched_portfolio_names(text: str, watchlist: tuple[PortfolioKeyword, ...]) -> list[str]:
    normalized_text = _normalize_for_substring_match(text)
    boundary_text = _clean_boundary_text(text)
    matches: list[str] = []
    for keyword in watchlist:
        if _matches_keyword(keyword=keyword, normalized_text=normalized_text, boundary_text=boundary_text):
            matches.append(keyword.display_name)
    return matches


def _matches_keyword(*, keyword: PortfolioKeyword, normalized_text: str, boundary_text: str) -> bool:
    if _needs_token_boundary(keyword.normalized_name):
        pattern = (
            rf"(?<![{_TOKEN_BOUNDARY_CHARS}]){re.escape(keyword.display_name.casefold())}"
            rf"(?:(?![{_TOKEN_BOUNDARY_CHARS}])|(?=[{_KOREAN_PARTICLES}](?![가-힣])))"
        )
        return re.search(pattern, boundary_text) is not None
    return keyword.normalized_name in normalized_text


def _needs_token_boundary(normalized_name: str) -> bool:
    return len(normalized_name) < 3 and bool(re.fullmatch(r"[가-힣]+", normalized_name))


def _aliases(raw_name: str) -> tuple[str, ...]:
    value = raw_name.strip().strip('"').strip()
    if not value:
        return ()
    outside, parentheticals = _split_parentheticals(value)
    aliases = [outside]
    for parenthetical in parentheticals:
        aliases.append(parenthetical)
        if "구." in parenthetical:
            aliases.append(parenthetical.split("구.", 1)[1])
    return tuple(alias for alias in aliases if alias.strip())


def _split_parentheticals(value: str) -> tuple[str, list[str]]:
    outside: list[str] = []
    parentheticals: list[str] = []
    stack: list[str] = []
    depth = 0
    current: list[str] = []
    for character in value:
        if character == "(":
            if depth == 0:
                outside.extend(current)
                current = []
            else:
                stack.append(character)
            depth += 1
            continue
        if character == ")" and depth > 0:
            depth -= 1
            if depth == 0:
                parentheticals.append("".join(stack).strip())
                stack = []
            else:
                stack.append(character)
            continue
        if depth:
            stack.append(character)
        else:
            current.append(character)
    outside.extend(current)
    return "".join(outside), parentheticals


def _clean_display_name(value: str) -> str:
    cleaned = value.strip().strip('"').strip()
    cleaned = cleaned.replace("구.", "")
    cleaned = _DESIGNATOR_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[ㆍ·∙]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" ,./-_")
    return cleaned


def _normalize_for_substring_match(value: str) -> str:
    cleaned = _clean_display_name(value).casefold()
    return re.sub(r"[^0-9a-z가-힣]+", "", cleaned)


def _clean_boundary_text(value: str) -> str:
    cleaned = _clean_display_name(value).casefold()
    return re.sub(r"\s+", " ", cleaned)
