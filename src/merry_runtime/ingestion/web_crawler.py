from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


USER_AGENT = "HermesMerryDiscoveryBot/0.1"


@dataclass(frozen=True, slots=True)
class CrawledPage:
    url: str
    content: str
    backend: str


class CrawlFetchError(RuntimeError):
    pass


def fetch_url(url: str, *, backend: str = "auto", timeout_seconds: int = 20) -> str:
    page = crawl_url(url, backend=backend, timeout_seconds=timeout_seconds)
    return page.content


def crawl_url(url: str, *, backend: str = "auto", timeout_seconds: int = 20) -> CrawledPage:
    _validate_url(url)
    selected_backend = backend.strip().casefold() or "auto"
    if selected_backend not in {"auto", "crawl4ai", "urllib"}:
        raise CrawlFetchError(f"Unsupported crawler backend: {backend}")

    if selected_backend in {"auto", "crawl4ai"}:
        try:
            return asyncio.run(_crawl_with_crawl4ai(url, timeout_seconds=timeout_seconds))
        except ModuleNotFoundError:
            if selected_backend == "crawl4ai":
                raise CrawlFetchError("crawl4ai is not installed") from None
        except Exception as exc:
            if selected_backend == "crawl4ai":
                raise CrawlFetchError(f"crawl4ai crawl failed: {exc}") from exc

    return CrawledPage(url=url, content=_fetch_with_urllib(url, timeout_seconds=timeout_seconds), backend="urllib")


async def _crawl_with_crawl4ai(url: str, *, timeout_seconds: int) -> CrawledPage:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    browser_config = BrowserConfig(headless=True, user_agent=USER_AGENT)
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=timeout_seconds * 1000)
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=run_config)
    if not getattr(result, "success", True):
        error_message = getattr(result, "error_message", "unknown crawl4ai error")
        raise CrawlFetchError(str(error_message))
    content = getattr(result, "html", "") or getattr(result, "cleaned_html", "") or str(getattr(result, "markdown", ""))
    return CrawledPage(url=url, content=str(content), backend="crawl4ai")


def _fetch_with_urllib(url: str, *, timeout_seconds: int) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8", errors="replace")
    except URLError as exc:
        raise CrawlFetchError(f"urllib crawl failed: {exc}") from exc


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CrawlFetchError(f"Only absolute http(s) URLs are supported: {url}")
    if parsed.path.startswith("/api"):
        raise CrawlFetchError("API paths are not allowed for web crawling")
