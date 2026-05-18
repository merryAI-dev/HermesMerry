from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urljoin

from merry_runtime.portfolio_watchlist import PortfolioKeyword, matched_portfolio_names


PLATUM_INVESTMENT_CHANNEL = "platum_investment_news"
_ITEM_MARKER = '<div class="gb-grid-column'
_HREF_RE = re.compile(r'<a[^>]+class="[^"]*\bgb-container-link\b[^"]*"[^>]+href="([^"]+)"', re.IGNORECASE)
_TITLE_RE = re.compile(r"<h3\b[^>]*>(.*?)</h3>", re.IGNORECASE | re.DOTALL)
_EXCERPT_RE = re.compile(r'<p\b[^>]*class="[^"]*\bexcerpt\b[^"]*"[^>]*>(.*?)</p>', re.IGNORECASE | re.DOTALL)
_PUBLISHED_RE = re.compile(r'<time\b[^>]*datetime="([^"]+)"', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class PlatumArticle:
    url: str
    title: str
    excerpt: str
    published_at: str


def extract_platum_portfolio_news_sources(
    html_text: str,
    *,
    source_url: str,
    watchlist: tuple[PortfolioKeyword, ...],
    max_articles: int = 20,
) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for article in _extract_listing_articles(html_text=html_text, source_url=source_url)[:max_articles]:
        matches = matched_portfolio_names(f"{article.title}\n{article.excerpt}", watchlist)
        for company in matches:
            sources.append(
                {
                    "channel": PLATUM_INVESTMENT_CHANNEL,
                    "payload": _source_payload(article=article, company=company, matched_companies=matches),
                }
            )
    return sources


def _extract_listing_articles(*, html_text: str, source_url: str) -> list[PlatumArticle]:
    articles: list[PlatumArticle] = []
    for block in html_text.split(_ITEM_MARKER):
        if "gb-query-loop-item" not in block:
            continue
        url = _extract(_HREF_RE, block)
        title = _html_text(_extract(_TITLE_RE, block))
        if not url or not title:
            continue
        articles.append(
            PlatumArticle(
                url=urljoin(source_url, url),
                title=title,
                excerpt=_html_text(_extract(_EXCERPT_RE, block)),
                published_at=_extract(_PUBLISHED_RE, block),
            )
        )
    return articles


def _source_payload(*, article: PlatumArticle, company: str, matched_companies: list[str]) -> str:
    evidence = f"{article.title} — {article.excerpt}" if article.excerpt else article.title
    return "\n".join(
        [
            f"Title: {article.title}",
            f"Company: {company}",
            f"Matched Companies: {', '.join(matched_companies)}",
            f"URL: {article.url}",
            f"Published: {article.published_at}",
            f"Summary: {article.excerpt}",
            "Signal: portfolio_news",
            f"Evidence: {evidence}",
            "Confidence: 0.95",
            "Tags: portfolio, platum, investment_news",
        ]
    )


def _extract(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return html.unescape(match.group(1)).strip() if match else ""


def _html_text(value: str) -> str:
    without_tags = _TAG_RE.sub(" ", value)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()
