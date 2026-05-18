from __future__ import annotations

import json
from dataclasses import dataclass
from html.parser import HTMLParser
import re
from typing import Any, Callable
from urllib.parse import urljoin


THEVC_INVESTMENT_CHANNEL = "thevc_investment_ma"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ROUND_TAG_RE = re.compile(r"[^0-9a-zA-Z가-힣]+")
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
    r"(?![A-Za-z0-9._%+-])"
)
_SOURCE_LABELS = {"보도자료", "기타"}


@dataclass(frozen=True, slots=True)
class TheVCInvestmentCard:
    company: str
    product: str
    description: str
    industry: str
    investment_round: str
    investment_amount: str
    investor: str
    published_at: str
    profile_url: str
    source_url: str
    representative: str = ""
    homepage: str = ""
    region: str = ""
    contact_email: str = ""


@dataclass(frozen=True, slots=True)
class TheVCCompanyDetail:
    representative: str = ""
    homepage: str = ""
    region: str = ""
    contact_email: str = ""


def extract_thevc_investment_sources(
    html: str,
    *,
    source_url: str,
    max_cards: int = 20,
    fetch_detail_url: Callable[[str], str] | None = None,
) -> list[dict[str, str]]:
    cards = extract_thevc_investment_cards(html, source_url=source_url, max_cards=max_cards)
    if fetch_detail_url is not None:
        cards = [_enrich_card(card, fetch_detail_url=fetch_detail_url) for card in cards]
    return [{"channel": THEVC_INVESTMENT_CHANNEL, "payload": _card_payload(card)} for card in cards]


def extract_thevc_investment_cards(
    html: str,
    *,
    source_url: str,
    max_cards: int = 20,
) -> list[TheVCInvestmentCard]:
    parser = _InvestmentRowParser()
    parser.feed(html)

    cards: list[TheVCInvestmentCard] = []
    for row in parser.rows:
        card = _card_from_row(row, source_url=source_url)
        if card is None:
            continue
        cards.append(card)
        if len(cards) >= max_cards:
            break
    return cards


def extract_thevc_company_detail(html: str) -> TheVCCompanyDetail:
    parser = _CompanyDetailParser()
    parser.feed(html)
    structured_detail = _detail_from_json_ld(parser.json_ld_blocks)
    text_detail = _detail_from_text(parser.visible_text, parser.meta_descriptions)
    contact_text = "\n".join([*parser.mailtos, *parser.visible_text, *parser.meta_descriptions])
    contact_email = structured_detail.contact_email or _extract_public_email(contact_text)
    return TheVCCompanyDetail(
        representative=structured_detail.representative or text_detail.representative,
        homepage=structured_detail.homepage or text_detail.homepage,
        region=structured_detail.region or text_detail.region,
        contact_email=contact_email or text_detail.contact_email,
    )


class _InvestmentRowParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, list[str]]] = []
        self._skip_depth = 0
        self._in_row = False
        self._current: dict[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "tr":
            self._in_row = True
            self._current = {"texts": [], "hrefs": []}
            return
        if self._in_row and tag == "a" and self._current is not None:
            attrs_by_name = {name: value for name, value in attrs}
            href = attrs_by_name.get("href")
            if href:
                self._current["hrefs"].append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "tr" and self._in_row:
            if self._current is not None:
                self.rows.append(self._current)
            self._current = None
            self._in_row = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not self._in_row or self._current is None:
            return
        text = " ".join(data.split())
        if text:
            self._current["texts"].append(text)


class _CompanyDetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.visible_text: list[str] = []
        self.meta_descriptions: list[str] = []
        self.mailtos: list[str] = []
        self.json_ld_blocks: list[str] = []
        self._skip_depth = 0
        self._in_json_ld = False
        self._json_ld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_by_name = {name.casefold(): value or "" for name, value in attrs}
        if tag == "script":
            if attrs_by_name.get("type", "").casefold() == "application/ld+json":
                self._in_json_ld = True
                self._json_ld_parts = []
            else:
                self._skip_depth += 1
            return
        if tag == "style":
            self._skip_depth += 1
            return
        if tag == "meta":
            name = attrs_by_name.get("name", "").casefold()
            property_name = attrs_by_name.get("property", "").casefold()
            if name == "description" or property_name in {"og:description", "twitter:description"}:
                content = _clean(attrs_by_name.get("content", ""))
                if content:
                    self.meta_descriptions.append(content)
        if tag == "a":
            href = attrs_by_name.get("href", "")
            if href.casefold().startswith("mailto:"):
                self.mailtos.append(href.split(":", 1)[1].split("?", 1)[0])

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            block = _clean("".join(self._json_ld_parts))
            if block:
                self.json_ld_blocks.append(block)
            self._json_ld_parts = []
            self._in_json_ld = False
            return
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._json_ld_parts.append(data)
            return
        if self._skip_depth:
            return
        text = _clean(data)
        if text:
            self.visible_text.append(text)


def _card_from_row(row: dict[str, list[str]], *, source_url: str) -> TheVCInvestmentCard | None:
    texts = row["texts"]
    if not {"투자대상분야", "투자단계", "투자금액", "투자자"} <= set(texts):
        return None
    if "프로필 확인" not in texts:
        return None

    try:
        first_label_index = min(texts.index(label) for label in ("투자대상분야", "투자단계", "투자금액", "투자자"))
    except ValueError:
        return None

    lead_fields = texts[:first_label_index]
    published_at = next((text for text in lead_fields if _DATE_RE.match(text)), "")
    lead_fields = [text for text in lead_fields if not _DATE_RE.match(text) and text not in _SOURCE_LABELS]
    if len(lead_fields) < 3:
        return None

    company, product, description = lead_fields[0], lead_fields[1], lead_fields[2]
    profile_path = row["hrefs"][0] if row["hrefs"] else ""
    profile_url = urljoin(source_url, profile_path)

    return TheVCInvestmentCard(
        company=company,
        product=product,
        description=description,
        industry=_field_after(texts, "투자대상분야"),
        investment_round=_field_after(texts, "투자단계"),
        investment_amount=_field_after(texts, "투자금액"),
        investor=_investor_after(texts),
        published_at=published_at,
        profile_url=profile_url,
        source_url=source_url,
    )


def _enrich_card(card: TheVCInvestmentCard, *, fetch_detail_url: Callable[[str], str]) -> TheVCInvestmentCard:
    detail = TheVCCompanyDetail()
    if card.profile_url:
        detail_html = _safe_fetch(fetch_detail_url, card.profile_url)
        if detail_html:
            detail = extract_thevc_company_detail(detail_html)
    contact_email = detail.contact_email
    if not contact_email and detail.homepage:
        contact_email = _find_homepage_contact_email(detail.homepage, fetch_url=fetch_detail_url)
    return TheVCInvestmentCard(
        company=card.company,
        product=card.product,
        description=card.description,
        industry=card.industry,
        investment_round=card.investment_round,
        investment_amount=card.investment_amount,
        investor=card.investor,
        published_at=card.published_at,
        profile_url=card.profile_url,
        source_url=card.source_url,
        representative=detail.representative,
        homepage=detail.homepage,
        region=detail.region,
        contact_email=contact_email,
    )


def _detail_from_json_ld(blocks: list[str]) -> TheVCCompanyDetail:
    for block in blocks:
        for node in _json_ld_nodes(block):
            detail = _detail_from_json_node(node)
            if detail != TheVCCompanyDetail():
                return detail
    return TheVCCompanyDetail()


def _json_ld_nodes(block: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(block)
    except json.JSONDecodeError:
        return []
    return [node for node in _flatten_json_ld(value) if isinstance(node, dict)]


def _flatten_json_ld(value: Any) -> list[Any]:
    if isinstance(value, list):
        nodes: list[Any] = []
        for item in value:
            nodes.extend(_flatten_json_ld(item))
        return nodes
    if isinstance(value, dict):
        graph = value.get("@graph")
        if isinstance(graph, list):
            return [value, *graph]
        return [value]
    return []


def _detail_from_json_node(node: dict[str, Any]) -> TheVCCompanyDetail:
    homepage = _json_homepage(node)
    address = node.get("address")
    region = _json_region(address) if isinstance(address, dict) else ""
    representative = _json_representatives(node.get("employee")) or _json_representatives(node.get("founder"))
    contact_email = _json_email(node.get("email"))
    return TheVCCompanyDetail(
        representative=representative,
        homepage=homepage,
        region=region,
        contact_email=contact_email,
    )


def _json_homepage(node: dict[str, Any]) -> str:
    same_as = node.get("sameAs")
    candidates = same_as if isinstance(same_as, list) else [same_as]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value and "thevc.kr" not in value:
            return _normalize_url(value)
    return ""


def _json_region(address: dict[str, Any]) -> str:
    parts = [
        str(address.get("addressCountry") or "").strip(),
        str(address.get("addressRegion") or "").strip(),
        str(address.get("addressLocality") or "").strip(),
    ]
    return ", ".join(part for part in parts if part)


def _json_representatives(value: Any) -> str:
    people = value if isinstance(value, list) else [value]
    names: list[str] = []
    for person in people:
        if not isinstance(person, dict):
            continue
        job_title = str(person.get("jobTitle") or person.get("roleName") or "")
        if job_title and "대표" not in job_title and "CEO" not in job_title.upper():
            continue
        name = str(person.get("name") or "").strip()
        if name:
            names.append(name)
    return "∙".join(dict.fromkeys(names))


def _json_email(value: Any) -> str:
    candidates = value if isinstance(value, list) else [value]
    for candidate in candidates:
        email = _extract_public_email(str(candidate or ""))
        if email:
            return email
    return ""


def _detail_from_text(visible_text: list[str], meta_descriptions: list[str]) -> TheVCCompanyDetail:
    text = " ".join([*meta_descriptions, *visible_text])
    representative = _match_first(
        text,
        (r"현재\s*대표자는\s*([^\.]+?)입니다", r"대표자\s*([0-9A-Za-z가-힣∙·,\s]+)"),
    )
    region = _match_first(
        text,
        (r"본사는\s*([^\.]+?)에\s*위치해있습니다", r"본사\s*주소\s*([0-9A-Za-z가-힣∙·,\s]+)"),
    )
    homepage = _match_first(text, (r"홈페이지\s*([^\s]+)", r"(https?://[^\s]+)"))
    return TheVCCompanyDetail(
        representative=_clean(representative),
        homepage=_normalize_url(homepage) if homepage else "",
        region=_normalize_region(region),
        contact_email=_extract_public_email(text),
    )


def _find_homepage_contact_email(homepage: str, *, fetch_url: Callable[[str], str]) -> str:
    for url in _homepage_contact_candidates(homepage):
        html = _safe_fetch(fetch_url, url)
        if not html:
            continue
        email = extract_thevc_company_detail(html).contact_email or _extract_public_email(html)
        if email:
            return email
    return ""


def _homepage_contact_candidates(homepage: str) -> list[str]:
    base = _normalize_url(homepage)
    if not base:
        return []
    paths = ("", "/contact", "/contact-us", "/about", "/company", "/support")
    return list(dict.fromkeys(urljoin(base, path) for path in paths))


def _safe_fetch(fetch_url: Callable[[str], str], url: str) -> str:
    try:
        return fetch_url(url)
    except Exception:
        return ""


def _extract_public_email(text: str) -> str:
    match = _EMAIL_RE.search(text)
    return match.group(1) if match else ""


def _match_first(text: str, patterns: tuple[str, ...]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""


def _normalize_url(value: str) -> str:
    cleaned = _clean(value).rstrip(".,)")
    if not cleaned:
        return ""
    if cleaned.startswith("//"):
        return f"https:{cleaned}"
    if not cleaned.startswith(("http://", "https://")):
        return f"https://{cleaned}"
    return cleaned


def _normalize_region(value: str) -> str:
    cleaned = _clean(value)
    if not cleaned:
        return ""
    parts = [part.strip() for part in re.split(r"[∙·,]", cleaned) if part.strip()]
    return ", ".join(parts) if len(parts) > 1 else cleaned


def _clean(value: str) -> str:
    return " ".join(value.split())


def _field_after(texts: list[str], label: str) -> str:
    try:
        index = texts.index(label)
    except ValueError:
        return ""
    if index + 1 >= len(texts):
        return ""
    return texts[index + 1]


def _investor_after(texts: list[str]) -> str:
    try:
        index = texts.index("투자자") + 1
    except ValueError:
        return ""
    values: list[str] = []
    for text in texts[index:]:
        if text == "프로필 확인":
            break
        values.append(text)
    return " ".join(values)


def _card_payload(card: TheVCInvestmentCard) -> str:
    detail_tags = (
        ["detail_enriched"]
        if any((card.representative, card.homepage, card.region, card.contact_email))
        else ["needs_web_fallback"]
    )
    tags = [
        THEVC_INVESTMENT_CHANNEL,
        "public_cold_lead",
        "investment",
        "fresh",
        *detail_tags,
        f"industry:{card.industry}",
        f"round:{_tag_value(card.investment_round)}",
    ]
    evidence = (
        f"THE VC 투자/M&A 공개 카드: {card.company} / {card.product}. "
        f"{card.description} 투자단계={card.investment_round}; 투자자={card.investor}; "
        f"투자금액={card.investment_amount}."
    )
    return "\n".join(
        [
            f"Title: THE VC Investment/M&A - {card.company} {card.product}",
            f"URL: {card.source_url}",
            f"Source URI: {card.profile_url}",
            f"Company: {card.company}",
            f"Product: {card.product}",
            f"Industry: {card.industry}",
            f"Representative: {card.representative}",
            f"Homepage: {card.homepage}",
            f"Region: {card.region}",
            f"Contact Email: {card.contact_email}",
            f"Published: {card.published_at}",
            "Signal: investment",
            "Confidence: 0.65",
            f"Tags: {', '.join(tags)}",
            f"Investment Round: {card.investment_round}",
            f"Investment Amount: {card.investment_amount}",
            f"Investor: {card.investor}",
            f"Evidence: {evidence}",
        ]
    )


def _tag_value(value: str) -> str:
    normalized = _ROUND_TAG_RE.sub("-", value.casefold()).strip("-")
    return normalized or "unknown"
