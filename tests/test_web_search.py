from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError

from merry_runtime.adapters.web_search import DuckDuckGoSearchClient, PublicWebSearchClient


class FakeResponse(BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


class CapturingUrlopen:
    def __init__(self, html: str) -> None:
        self.html = html
        self.request = None
        self.timeout = None

    def __call__(self, request, *, timeout: int):
        self.request = request
        self.timeout = timeout
        return FakeResponse(self.html.encode("utf-8"))


def test_duckduckgo_search_client_extracts_result_title_url_and_snippet() -> None:
    urlopen = CapturingUrlopen(
        """
        <html><body>
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ffund&amp;rut=abc">
            디쓰리 미래환경 ECO 벤처투자조합 결성
          </a>
          <a class="result__snippet">디쓰리쥬빌리파트너스가 운용하는 미래환경산업 펀드다.</a>
        </body></html>
        """
    )
    client = DuckDuckGoSearchClient(urlopen=urlopen, timeout_seconds=9)

    results = client.search('"디쓰리 미래환경 ECO 벤처투자조합"', max_results=3)

    assert results == [
        {
            "title": "디쓰리 미래환경 ECO 벤처투자조합 결성",
            "url": "https://example.com/fund",
            "snippet": "디쓰리쥬빌리파트너스가 운용하는 미래환경산업 펀드다.",
        }
    ]
    assert urlopen.timeout == 9
    assert "duckduckgo.com/html/" in urlopen.request.full_url


def test_public_web_search_client_falls_back_to_bing_when_duckduckgo_has_no_results() -> None:
    class RoutingUrlopen:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def __call__(self, request, *, timeout: int):
            self.urls.append(request.full_url)
            if "duckduckgo" in request.full_url:
                return FakeResponse(b"<html><body>Unfortunately, bots use DuckDuckGo too.</body></html>")
            return FakeResponse(
                b"""
                <html><body><ol id="b_results">
                  <li class="b_algo">
                    <h2><a href="https://www.bing.com/ck/a?u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9teXNjLWF1bQ">MYSC AUM report</a></h2>
                    <div class="b_caption"><p>MYSC AUM 1,107 eok and 20 funds.</p></div>
                  </li>
                </ol></body></html>
                """
            )

    urlopen = RoutingUrlopen()
    client = PublicWebSearchClient(urlopen=urlopen, timeout_seconds=9)

    results = client.search("MYSC AUM", max_results=3)

    assert results == [
        {
            "title": "MYSC AUM report",
            "url": "https://example.com/mysc-aum",
            "snippet": "MYSC AUM 1,107 eok and 20 funds.",
        }
    ]
    assert any("duckduckgo" in url for url in urlopen.urls)
    assert any("bing.com/search" in url for url in urlopen.urls)


def test_public_web_search_client_falls_back_to_bing_when_duckduckgo_is_forbidden() -> None:
    class RoutingUrlopen:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def __call__(self, request, *, timeout: int):
            self.urls.append(request.full_url)
            if "duckduckgo" in request.full_url:
                raise HTTPError(request.full_url, 403, "Forbidden", hdrs=None, fp=None)
            return FakeResponse(
                b"""
                <html><body><ol id="b_results">
                  <li class="b_algo">
                    <h2><a href="https://example.com/fallback">Fallback investor profile</a></h2>
                    <div class="b_caption"><p>Fallback search evidence.</p></div>
                  </li>
                </ol></body></html>
                """
            )

    urlopen = RoutingUrlopen()
    client = PublicWebSearchClient(urlopen=urlopen, timeout_seconds=9)

    results = client.search("MYSC AUM", max_results=3)

    assert results == [
        {
            "title": "Fallback investor profile",
            "url": "https://example.com/fallback",
            "snippet": "Fallback search evidence.",
        }
    ]
    assert any("duckduckgo" in url for url in urlopen.urls)
    assert any("bing.com/search" in url for url in urlopen.urls)
