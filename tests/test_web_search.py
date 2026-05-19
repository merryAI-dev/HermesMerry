from __future__ import annotations

from io import BytesIO

from merry_runtime.adapters.web_search import DuckDuckGoSearchClient


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
