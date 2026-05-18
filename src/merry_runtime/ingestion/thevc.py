from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re
from urllib.parse import urljoin


THEVC_INVESTMENT_CHANNEL = "thevc_investment_ma"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ROUND_TAG_RE = re.compile(r"[^0-9a-zA-Z가-힣]+")
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


def extract_thevc_investment_sources(
    html: str,
    *,
    source_url: str,
    max_cards: int = 20,
) -> list[dict[str, str]]:
    cards = extract_thevc_investment_cards(html, source_url=source_url, max_cards=max_cards)
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
    tags = [
        THEVC_INVESTMENT_CHANNEL,
        "public_cold_lead",
        "investment",
        "fresh",
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
