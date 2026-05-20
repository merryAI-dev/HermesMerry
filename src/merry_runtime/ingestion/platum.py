from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from merry_runtime.ingestion.web_crawler import CrawlFetchError, USER_AGENT
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


def fetch_platum_facetwp_page(source_url: str, page: int, *, timeout_seconds: int = 20) -> str:
    if page <= 1:
        raise CrawlFetchError(f"FacetWP page must be greater than 1: {page}")
    payload = _facetwp_payload(source_url=source_url, page=page)
    request = Request(
        f"{source_url.rstrip('/')}?_paged={page}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json",
            "Referer": source_url,
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return template_from_facetwp_response(response.read().decode("utf-8-sig", errors="replace"))
    except URLError as exc:
        raise CrawlFetchError(f"Platum FacetWP page fetch failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CrawlFetchError(f"Platum FacetWP page returned invalid JSON: {exc}") from exc


def template_from_facetwp_response(response_text: str) -> str:
    data = json.loads(response_text.lstrip("\ufeff"))
    template = data.get("template")
    return str(template or "")


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


def _facetwp_payload(*, source_url: str, page: int) -> dict[str, object]:
    parsed = urlparse(source_url)
    return {
        "action": "facetwp_refresh",
        "data": {
            "facets": {"pagination": []},
            "frozen_facets": {},
            "http_params": {
                "get": {"_paged": str(page)},
                "uri": parsed.path.strip("/"),
                "url_vars": [],
            },
            "template": "wp",
            "extras": {"sort": "default"},
            "soft_refresh": 1,
            "is_bfcache": 1,
            "first_load": 0,
            "paged": str(page),
        },
    }


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
