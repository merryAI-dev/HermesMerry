from merry_runtime.adapters.sminfo_playwright import SminfoPlaywrightClient


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
