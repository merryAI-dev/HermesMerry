from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from merry_runtime.ingestion.sminfo import (
    SminfoProfile,
    SminfoSearchResult,
    choose_sminfo_search_result,
    parse_sminfo_profile_tables,
)


LOGIN_URL = "https://sminfo.mss.go.kr/cm/sv/CSV001R0.do"
DETAIL_SEARCH_URL = "https://sminfo.mss.go.kr/gc/sf/GSF002R0.print"


@dataclass(slots=True)
class SminfoPlaywrightClient:
    user_id: str
    password: str
    headless: bool = True
    timeout_ms: int = 30000
    min_interval_seconds: int = 35
    max_lookup_attempts: int = 3
    retry_backoff_seconds: float = 10.0
    sleep_fn: Callable[[float], None] = time.sleep
    monotonic_fn: Callable[[], float] = time.monotonic
    _playwright: Any = field(default=None, init=False, repr=False)
    _browser: Any = field(default=None, init=False, repr=False)
    _page: Any = field(default=None, init=False, repr=False)
    _logged_in: bool = field(default=False, init=False, repr=False)
    _last_lookup_monotonic: float | None = field(default=None, init=False, repr=False)

    def lookup_company(self, *, company_name: str, candidate: dict[str, str]) -> SminfoProfile:
        self._wait_for_rate_limit()
        last_error: Exception | None = None
        for attempt in range(max(self.max_lookup_attempts, 1)):
            try:
                return self._lookup_company_once(company_name=company_name, candidate=candidate)
            except Exception as exc:
                last_error = exc
                if attempt >= max(self.max_lookup_attempts, 1) - 1 or not _is_transient_browser_error(exc):
                    raise
                self.sleep_fn(self.retry_backoff_seconds)
        raise RuntimeError(f"SMINFO lookup failed: {last_error}")

    def _lookup_company_once(self, *, company_name: str, candidate: dict[str, str]) -> SminfoProfile:
        page = self._ensure_page()
        self._ensure_logged_in(page)
        page.goto(DETAIL_SEARCH_URL, wait_until="domcontentloaded", timeout=self.timeout_ms)
        page.get_by_label("검색어 선택").select_option(label="업체명")
        page.get_by_role("textbox", name="검색어 입력").fill(company_name)
        page.get_by_role("button", name="검색").click()
        page.wait_for_load_state("networkidle", timeout=self.timeout_ms)

        results = _extract_search_results(page)
        decision = choose_sminfo_search_result(requested_company=company_name, candidate=candidate, results=results)
        if decision.status != "matched" or decision.result is None:
            return SminfoProfile(
                requested_company=company_name,
                match_status=decision.status,
                error_message=decision.rationale,
                raw_payload={"search_results": [result.__dict__ for result in results]},
            )

        _click_search_result(page, decision.result.result_index, timeout_ms=self.timeout_ms)
        tables = _extract_tables(page)
        return parse_sminfo_profile_tables(requested_company=company_name, sminfo_url=page.url, tables=tables)

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._browser = None
        self._playwright = None
        self._page = None
        self._logged_in = False
        self._last_lookup_monotonic = None

    def _wait_for_rate_limit(self) -> None:
        now = self.monotonic_fn()
        if self._last_lookup_monotonic is not None:
            elapsed = now - self._last_lookup_monotonic
            remaining = self.min_interval_seconds - elapsed
            if remaining > 0:
                self.sleep_fn(remaining)
                now += remaining
        self._last_lookup_monotonic = now

    def _ensure_page(self) -> Any:
        if self._page is not None:
            return self._page
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        return self._page

    def _ensure_logged_in(self, page: Any) -> None:
        if self._logged_in:
            return
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=self.timeout_ms)
        if page.get_by_role("link", name="로그아웃").count() == 0:
            page.get_by_role("textbox", name="아이디").fill(self.user_id)
            page.get_by_role("textbox", name="비밀번호").fill(self.password)
            page.get_by_role("button", name="로그인").click()
            page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
        if page.get_by_role("link", name="로그아웃").count() == 0:
            raise RuntimeError("SMINFO login failed")
        self._logged_in = True


def _extract_search_results(page: Any) -> list[SminfoSearchResult]:
    rows = page.evaluate(
        """
        () => {
          const table = Array.from(document.querySelectorAll('table')).find(
            (item) => (item.querySelector('caption')?.innerText || '').trim() === '기업 상세검색 목록'
          );
          if (!table) return [];
          return Array.from(table.querySelectorAll('tbody tr')).map((row, index) => {
            const cells = Array.from(row.querySelectorAll('td')).map((cell) => cell.innerText.trim().replace(/\\s+/g, ' '));
            return { index, cells };
          }).filter((row) => row.cells.length >= 5);
        }
        """
    )
    return [
        SminfoSearchResult(
            company_name=row["cells"][0],
            representative=row["cells"][1],
            company_type=row["cells"][2],
            industry=row["cells"][3],
            road_address=row["cells"][4],
            result_index=int(row["index"]),
        )
        for row in rows
    ]


def _click_search_result(page: Any, result_index: int, *, timeout_ms: int) -> None:
    clicked = page.evaluate(
        """
        (resultIndex) => {
          const table = Array.from(document.querySelectorAll('table')).find(
            (item) => (item.querySelector('caption')?.innerText || '').trim() === '기업 상세검색 목록'
          );
          if (!table) return false;
          const rows = Array.from(table.querySelectorAll('tbody tr'));
          const link = rows[resultIndex]?.querySelector('a');
          if (!link) return false;
          link.click();
          return true;
        }
        """,
        result_index,
    )
    if not clicked:
        raise RuntimeError(f"SMINFO search result row {result_index} is not clickable")
    page.wait_for_url("**/IEI001R0.do**", timeout=timeout_ms)
    page.wait_for_load_state("networkidle", timeout=timeout_ms)


def _extract_tables(page: Any) -> list[dict[str, object]]:
    return page.evaluate(
        """
        () => Array.from(document.querySelectorAll('table')).map((table) => ({
          caption: (table.querySelector('caption')?.innerText || '').trim(),
          rows: Array.from(table.querySelectorAll('tr')).map((row) =>
            Array.from(row.querySelectorAll('th,td')).map((cell) => cell.innerText.trim().replace(/\\s+/g, ' '))
          ).filter((cells) => cells.length > 0)
        }))
        """
    )


def _is_transient_browser_error(exc: Exception) -> bool:
    message = str(exc)
    return any(
        marker in message
        for marker in (
            "ERR_CONNECTION_RESET",
            "ERR_TIMED_OUT",
            "ERR_CONNECTION_CLOSED",
            "Timeout",
            "net::ERR",
        )
    )
