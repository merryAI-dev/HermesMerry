from merry_runtime.adapters.sminfo_playwright import SminfoPlaywrightClient


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
