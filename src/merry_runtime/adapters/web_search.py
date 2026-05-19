from __future__ import annotations

import html
import base64
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen as default_urlopen


_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Chrome/125.0 Safari/537.36"
)
_RESULT_BLOCK = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r"(?P<tail>.*?)(?=<a[^>]+class=\"[^\"]*result__a|</body>|</html>)",
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET = re.compile(r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</a>', re.IGNORECASE | re.DOTALL)
_BING_BLOCK = re.compile(r'<li[^>]+class="[^"]*b_algo[^"]*"[^>]*>(?P<block>.*?)(?=<li[^>]+class="[^"]*b_algo|</ol>|</body>|</html>)', re.IGNORECASE | re.DOTALL)
_BING_TITLE = re.compile(r'<h2[^>]*>\s*<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.IGNORECASE | re.DOTALL)
_BING_SNIPPET = re.compile(r"<p[^>]*>(?P<snippet>.*?)</p>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class DuckDuckGoSearchClient:
    timeout_seconds: int = 15
    user_agent: str = _DEFAULT_USER_AGENT
    urlopen: Callable[..., Any] = field(default=default_urlopen, repr=False)

    def search(self, query: str, *, max_results: int) -> list[dict[str, str]]:
        if not query.strip() or max_results <= 0:
            return []
        request_url = f"https://html.duckduckgo.com/html/?{urlencode({'q': query})}"
        request = Request(request_url, headers={"User-Agent": self.user_agent, "Accept": "text/html,*/*"})
        with self.urlopen(request, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
        return _parse_duckduckgo_results(body, max_results=max_results)


@dataclass(frozen=True, slots=True)
class PublicWebSearchClient:
    timeout_seconds: int = 15
    user_agent: str = _DEFAULT_USER_AGENT
    urlopen: Callable[..., Any] = field(default=default_urlopen, repr=False)

    def search(self, query: str, *, max_results: int) -> list[dict[str, str]]:
        if not query.strip() or max_results <= 0:
            return []
        duckduckgo = DuckDuckGoSearchClient(
            timeout_seconds=self.timeout_seconds,
            user_agent=self.user_agent,
            urlopen=self.urlopen,
        )
        results = duckduckgo.search(query, max_results=max_results)
        if results:
            return results
        return _fetch_bing_results(
            query=query,
            max_results=max_results,
            timeout_seconds=self.timeout_seconds,
            user_agent=self.user_agent,
            urlopen=self.urlopen,
        )


def _parse_duckduckgo_results(body: str, *, max_results: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for match in _RESULT_BLOCK.finditer(body):
        title = _clean_html(match.group("title"))
        url = _decode_duckduckgo_url(html.unescape(match.group("href")))
        snippet_match = _SNIPPET.search(match.group("tail"))
        snippet = _clean_html(snippet_match.group("snippet")) if snippet_match else ""
        if title and url:
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


def _fetch_bing_results(
    *,
    query: str,
    max_results: int,
    timeout_seconds: int,
    user_agent: str,
    urlopen: Callable[..., Any],
) -> list[dict[str, str]]:
    request_url = f"https://www.bing.com/search?{urlencode({'q': query, 'setlang': 'ko-KR'})}"
    request = Request(
        request_url,
        headers={"User-Agent": user_agent, "Accept": "text/html,*/*", "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8", errors="replace")
    return _parse_bing_results(body, max_results=max_results)


def _parse_bing_results(body: str, *, max_results: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for block_match in _BING_BLOCK.finditer(body):
        block = block_match.group("block")
        title_match = _BING_TITLE.search(block)
        if title_match is None:
            continue
        title = _clean_html(title_match.group("title"))
        url = _decode_bing_url(html.unescape(title_match.group("href")))
        snippet_match = _BING_SNIPPET.search(block)
        snippet = _clean_html(snippet_match.group("snippet")) if snippet_match else ""
        if title and url:
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


def _decode_duckduckgo_url(value: str) -> str:
    if value.startswith("//"):
        value = f"https:{value}"
    parsed = urlparse(value)
    params = parse_qs(parsed.query)
    uddg = params.get("uddg", [])
    if uddg:
        return unquote(uddg[0])
    return value


def _decode_bing_url(value: str) -> str:
    parsed = urlparse(value)
    params = parse_qs(parsed.query)
    encoded = params.get("u", [])
    if encoded:
        payload = encoded[0]
        if payload.startswith("a1"):
            payload = payload[2:]
        try:
            padded = payload + "=" * (-len(payload) % 4)
            return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        except Exception:
            return value
    return value


def _clean_html(value: str) -> str:
    without_tags = _TAG.sub(" ", value)
    return " ".join(html.unescape(without_tags).split())
