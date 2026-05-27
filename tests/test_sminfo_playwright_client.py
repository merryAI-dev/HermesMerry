from merry_runtime.adapters.sminfo_playwright import SminfoPlaywrightClient, _click_search_result


class _FakeLocator:
    def select_option(self, *, label: str) -> None:
        self.label = label

    def fill(self, value: str) -> None:
        self.value = value

    def click(self) -> None:
        self.clicked = True


class _ResetOncePage:
    def __init__(self) -> None:
        self.goto_calls = 0
        self.locator = _FakeLocator()

    def goto(self, *_args: object, **_kwargs: object) -> None:
        self.goto_calls += 1
        if self.goto_calls == 1:
            raise RuntimeError("Page.goto: net::ERR_CONNECTION_RESET at https://sminfo.mss.go.kr/cm/sv/CSV001R0.do")

    def get_by_label(self, _name: str) -> _FakeLocator:
        return self.locator

    def get_by_role(self, _role: str, *, name: str) -> _FakeLocator:
        return self.locator

    def wait_for_load_state(self, *_args: object, **_kwargs: object) -> None:
        return None

    def evaluate(self, *_args: object, **_kwargs: object) -> list[dict[str, object]]:
        return []


class _RetryingClient(SminfoPlaywrightClient):
    def __init__(self, page: _ResetOncePage, slept: list[float]) -> None:
        super().__init__(
            user_id="user",
            password="password",
            retry_backoff_seconds=3,
            sleep_fn=lambda seconds: slept.append(seconds),
        )
        self.fake_page = page

    def _ensure_page(self) -> _ResetOncePage:
        return self.fake_page

    def _ensure_logged_in(self, page: _ResetOncePage) -> None:
        return None


class _SearchResultClickPage:
    def __init__(self) -> None:
        self.evaluated_args: list[object] = []
        self.waited_urls: list[tuple[str, int]] = []
        self.waited_load_states: list[tuple[str, int]] = []

    def evaluate(self, _script: str, arg: object) -> bool:
        self.evaluated_args.append(arg)
        return True

    def wait_for_url(self, pattern: str, *, timeout: int) -> None:
        self.waited_urls.append((pattern, timeout))

    def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        self.waited_load_states.append((state, timeout))


class _AmbiguousSearchPage:
    url = "https://sminfo.mss.go.kr/gc/sf/GSF002R0.print"

    def goto(self, *_args: object, **_kwargs: object) -> None:
        return None

    def get_by_label(self, _name: str) -> _FakeLocator:
        return _FakeLocator()

    def get_by_role(self, _role: str, *, name: str) -> _FakeLocator:
        return _FakeLocator()

    def wait_for_load_state(self, *_args: object, **_kwargs: object) -> None:
        return None

    def evaluate(self, *_args: object, **_kwargs: object) -> list[dict[str, object]]:
        return [
            {"index": 0, "cells": ["(주)씨위드", "대표A", "중소기업", "제조업", "서울"]},
            {"index": 1, "cells": ["씨위드 주식회사", "대표B", "중소기업", "바이오", "부산"]},
        ]


class _AmbiguousSearchClient(SminfoPlaywrightClient):
    def __init__(self) -> None:
        super().__init__(user_id="user", password="password")
        self.fake_page = _AmbiguousSearchPage()

    def _ensure_page(self) -> _AmbiguousSearchPage:
        return self.fake_page

    def _ensure_logged_in(self, page: _AmbiguousSearchPage) -> None:
        return None


def test_sminfo_playwright_client_rate_limits_between_lookup_attempts() -> None:
    slept: list[float] = []
    times = iter([100.0, 110.0])
    client = SminfoPlaywrightClient(
        user_id="user",
        password="password",
        min_interval_seconds=35,
        sleep_fn=lambda seconds: slept.append(seconds),
        monotonic_fn=lambda: next(times),
    )

    client._wait_for_rate_limit()
    client._wait_for_rate_limit()

    assert slept == [25.0]


def test_sminfo_playwright_client_retries_connection_reset_once_before_returning_result() -> None:
    slept: list[float] = []
    page = _ResetOncePage()
    client = _RetryingClient(page=page, slept=slept)

    profile = client.lookup_company(company_name="에이아이오", candidate={})

    assert page.goto_calls == 2
    assert slept == [3.0]
    assert profile.match_status == "not_found"


def test_click_search_result_waits_for_detail_report_navigation() -> None:
    page = _SearchResultClickPage()

    _click_search_result(page, result_index=1, timeout_ms=45000)

    assert page.evaluated_args == [1]
    assert page.waited_urls == [("**/IEI001R0.do**", 45000)]
    assert page.waited_load_states == [("networkidle", 45000)]


def test_sminfo_playwright_client_serializes_ambiguous_search_results() -> None:
    client = _AmbiguousSearchClient()

    profile = client.lookup_company(company_name="씨위드", candidate={})

    assert profile.match_status == "ambiguous"
    assert profile.raw_payload["search_results"][0]["company_name"] == "(주)씨위드"
