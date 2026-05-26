from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from merry_runtime.ingestion.thevc import extract_thevc_investment_sources


_DEFAULT_STATE_PATH = Path("/workspace/hermes/thevc-state.json")
_NEXT_PAGE_RE = re.compile(r"다음 페이지 보기")
_LOGIN_BUTTON_NAME = "가입 / 로그인"
_INVESTMENT_MORE_NAME = "투자/M&A 더 보기"


class TheVCHumanVerificationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TheVCFetchResult:
    sources: list[dict[str, str]]
    login_status: str = "not_attempted"
    warning_message: str = ""


@dataclass(frozen=True, slots=True)
class _TheVCLoginResult:
    status: str
    warning_message: str = ""


@dataclass(slots=True)
class TheVCPlaywrightClient:
    user_email: str = ""
    password: str = ""
    storage_state_path: Path = _DEFAULT_STATE_PATH
    headless: bool = True
    browser_channel: str = ""
    timeout_ms: int = 30000
    _playwright: Any = field(default=None, init=False, repr=False)
    _browser: Any = field(default=None, init=False, repr=False)
    _context: Any = field(default=None, init=False, repr=False)
    _page: Any = field(default=None, init=False, repr=False)
    _logged_in: bool = field(default=False, init=False, repr=False)
    _login_attempted: bool = field(default=False, init=False, repr=False)
    _login_status: str = field(default="not_attempted", init=False, repr=False)
    _login_warning_message: str = field(default="", init=False, repr=False)

    @classmethod
    def from_env(cls) -> TheVCPlaywrightClient:
        return cls(
            user_email=os.getenv("THEVC_USER_EMAIL", ""),
            password=os.getenv("THEVC_PASSWORD", ""),
            storage_state_path=Path(os.getenv("THEVC_BROWSER_STATE_PATH", str(_DEFAULT_STATE_PATH))),
            headless=_parse_bool(os.getenv("THEVC_BROWSER_HEADLESS", ""), default=True),
            browser_channel=os.getenv("THEVC_BROWSER_CHANNEL", ""),
            timeout_ms=max(1, _parse_int(os.getenv("THEVC_TIMEOUT_SECONDS", ""), default=30)) * 1000,
        )

    def fetch_investment_sources(self, target: dict[str, Any]) -> list[dict[str, str]]:
        return self.fetch_investment_result(target).sources

    def fetch_investment_result(self, target: dict[str, Any]) -> TheVCFetchResult:
        source_url = str(target.get("url") or "https://thevc.kr/").strip()
        max_cards = _positive_int(target.get("max_cards"), default=20)
        max_pages = _positive_int(target.get("max_pages"), default=1, maximum=10)
        detail_enrichment = _truthy(target.get("detail_enrichment"), default=True)
        login_required = _truthy(target.get("thevc_login_required"), default=False)

        page = self._ensure_page()
        page.goto(source_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        _wait_for_thevc_app(page, timeout_ms=self.timeout_ms)
        login_result = self._ensure_logged_in(page, required=login_required)
        _safe_wait_for_network_idle(page, timeout_ms=self.timeout_ms)
        _open_investment_pages(page, timeout_ms=self.timeout_ms)

        rendered_pages: list[str] = []
        for _page_number in range(max_pages):
            rendered_pages.append(page.content())
            if _count_sources(rendered_pages, source_url=source_url, max_cards=max_cards) >= max_cards:
                break
            if not _click_next_investment_page(page, timeout_ms=self.timeout_ms):
                break

        return TheVCFetchResult(
            sources=extract_thevc_sources_from_rendered_pages(
                rendered_pages,
                source_url=source_url,
                max_cards=max_cards,
                fetch_detail_url=self._fetch_detail_html if detail_enrichment else None,
            ),
            login_status=login_result.status,
            warning_message=login_result.warning_message,
        )

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._logged_in = False
        self._login_attempted = False
        self._login_status = "not_attempted"
        self._login_warning_message = ""

    def _ensure_page(self) -> Any:
        if self._page is not None:
            return self._page
        context = self._ensure_context()
        self._page = context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        return self._page

    def _ensure_context(self) -> Any:
        if self._context is not None:
            return self._context
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        launch_options: dict[str, object] = {"headless": self.headless}
        if self.browser_channel:
            launch_options["channel"] = self.browser_channel
        self._browser = self._playwright.chromium.launch(**launch_options)
        storage_state = str(self.storage_state_path) if self.storage_state_path.exists() else None
        self._context = self._browser.new_context(storage_state=storage_state)
        return self._context

    def _ensure_logged_in(self, page: Any, *, required: bool = False) -> _TheVCLoginResult:
        if self._login_attempted:
            if required and self._login_status == "failed":
                raise RuntimeError(self._login_warning_message or "THE VC login failed")
            return _TheVCLoginResult(status=self._login_status, warning_message=self._login_warning_message)
        self._login_attempted = True
        if not self.user_email or not self.password:
            if not _has_login_button(page) and not _has_login_required_fields(page):
                self._logged_in = True
                self._login_status = "succeeded"
                self._login_warning_message = ""
                return _TheVCLoginResult(status="succeeded")
            if required:
                raise RuntimeError("THE VC login required but credentials are not configured")
            self._login_status = "not_attempted"
            self._login_warning_message = ""
            return _TheVCLoginResult(status=self._login_status)

        if not _has_login_button(page):
            if _has_login_required_fields(page):
                warning = "THE VC login failed: login button unavailable while gated fields remain"
                if required:
                    raise RuntimeError(warning)
                self._login_status = "failed"
                self._login_warning_message = warning
                return _TheVCLoginResult(status=self._login_status, warning_message=self._login_warning_message)
            self._logged_in = True
            self._login_status = "succeeded"
            self._login_warning_message = ""
            return _TheVCLoginResult(status="succeeded")
        try:
            _click_login_button(page)
            page.get_by_role("textbox", name="이메일").fill(self.user_email)
            page.get_by_role("textbox", name="패스워드").fill(self.password)
            page.get_by_role("button", name=re.compile(r"^로그인$")).click()
            page.wait_for_function(
                """
                () => !Array.from(document.querySelectorAll('button')).some(
                  (button) => button.innerText.trim() === '가입 / 로그인'
                )
                """,
                timeout=min(self.timeout_ms, 10000),
            )
        except Exception as exc:
            _dismiss_login_modal(page)
            if required:
                error_message = _login_error_message(page) or str(exc)
                raise RuntimeError(f"THE VC login failed: {error_message}") from exc
            error_message = _login_error_message(page) or str(exc)
            self._login_status = "failed"
            self._login_warning_message = f"THE VC login failed: {error_message}"
            return _TheVCLoginResult(status=self._login_status, warning_message=self._login_warning_message)
        self._logged_in = True
        self._login_status = "succeeded"
        self._login_warning_message = ""
        self._save_storage_state()
        return _TheVCLoginResult(status="succeeded")

    def _save_storage_state(self) -> None:
        if self._context is None:
            return
        self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        self._context.storage_state(path=str(self.storage_state_path))
        try:
            self.storage_state_path.chmod(0o600)
        except OSError:
            pass

    def _fetch_detail_html(self, url: str) -> str:
        page = self._ensure_context().new_page()
        page.set_default_timeout(self.timeout_ms)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            _wait_for_thevc_app(page, timeout_ms=self.timeout_ms)
            self._ensure_logged_in(page)
            _safe_wait_for_network_idle(page, timeout_ms=self.timeout_ms)
            return page.content()
        finally:
            page.close()


def extract_thevc_sources_from_rendered_pages(
    page_htmls: list[str],
    *,
    source_url: str,
    max_cards: int = 20,
    fetch_detail_url: Callable[[str], str] | None = None,
) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen_profile_urls: set[str] = set()
    for html in page_htmls:
        page_sources = extract_thevc_investment_sources(
            html,
            source_url=source_url,
            max_cards=max_cards,
            fetch_detail_url=fetch_detail_url,
        )
        for source in page_sources:
            profile_url = _payload_field(source.get("payload", ""), "Source URI")
            if profile_url and profile_url in seen_profile_urls:
                continue
            if profile_url:
                seen_profile_urls.add(profile_url)
            sources.append(source)
            if len(sources) >= max_cards:
                return sources
    return sources


def _open_investment_pages(page: Any, *, timeout_ms: int) -> None:
    button = page.get_by_role("button", name=_INVESTMENT_MORE_NAME)
    if button.count() == 0:
        return
    button.first.click(force=True)
    _safe_wait_for_network_idle(page, timeout_ms=timeout_ms)


def _click_next_investment_page(page: Any, *, timeout_ms: int) -> bool:
    button = page.get_by_role("button", name=_NEXT_PAGE_RE)
    if button.count() == 0:
        return False
    text = button.first.inner_text(timeout=timeout_ms)
    match = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if match and int(match.group(1)) >= int(match.group(2)):
        return False
    before = _investment_table_text(page)
    button.first.click(force=True)
    try:
        page.wait_for_function(
            """
            (before) => Array.from(document.querySelectorAll('tr'))
              .map((row) => row.innerText.trim())
              .filter(Boolean)
              .join('\\n---\\n') !== before
            """,
            before,
            timeout=timeout_ms,
        )
    except Exception:
        page.wait_for_timeout(500)
    return True


def _has_login_button(page: Any) -> bool:
    return bool(
        page.evaluate(
            """
            (name) => Array.from(document.querySelectorAll('button')).some(
              (button) => button.innerText.trim().replace(/\\s+/g, ' ') === name
            )
            """,
            _LOGIN_BUTTON_NAME,
        )
    )


def _has_login_required_fields(page: Any) -> bool:
    try:
        return "로그인 필요" in page.locator("body").inner_text(timeout=1000)
    except Exception:
        return False


def _click_login_button(page: Any) -> None:
    clicked = page.evaluate(
        """
        (name) => {
          const button = Array.from(document.querySelectorAll('button')).find(
            (item) => item.innerText.trim().replace(/\\s+/g, ' ') === name
          );
          if (!button) return false;
          button.click();
          return true;
        }
        """,
        _LOGIN_BUTTON_NAME,
    )
    if not clicked:
        raise RuntimeError("THE VC login button is not available")


def _dismiss_login_modal(page: Any) -> None:
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass


def _login_error_message(page: Any) -> str:
    try:
        return page.evaluate(
            """
            () => Array.from(document.querySelectorAll('*'))
              .map((item) => item.innerText && item.innerText.trim().replace(/\\s+/g, ' '))
              .filter(Boolean)
              .find((text) => text.includes('에러') || text.includes('실패') || text.includes('어려움')) || ''
            """
        )
    except Exception:
        return ""


def _safe_wait_for_network_idle(page: Any, *, timeout_ms: int) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass


def _wait_for_thevc_app(page: Any, *, timeout_ms: int) -> None:
    try:
        page.wait_for_function(
            """
            () => document.title.includes('더브이씨')
              || document.body.innerText.includes('투자/M&A')
              || Array.from(document.querySelectorAll('button')).some(
                (button) => button.innerText.trim().replace(/\\s+/g, ' ') === '가입 / 로그인'
              )
            """,
            timeout=timeout_ms,
        )
    except Exception:
        if _is_human_verification_page(page):
            raise TheVCHumanVerificationError("THE VC human verification did not complete")


def _is_human_verification_page(page: Any) -> bool:
    try:
        title = page.title()
        body_text = page.locator("body").inner_text(timeout=1000)
    except Exception:
        return False
    return "Human Verification" in title or "confirm you are human" in body_text


def _investment_table_text(page: Any) -> str:
    return page.evaluate(
        """
        () => Array.from(document.querySelectorAll('tr'))
          .map((row) => row.innerText.trim())
          .filter(Boolean)
          .join('\\n---\\n')
        """
    )


def _count_sources(page_htmls: list[str], *, source_url: str, max_cards: int) -> int:
    return len(extract_thevc_sources_from_rendered_pages(page_htmls, source_url=source_url, max_cards=max_cards))


def _payload_field(payload: str, label: str) -> str:
    prefix = f"{label}:"
    for line in payload.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _positive_int(value: Any, *, default: int, maximum: int | None = None) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    if maximum is not None:
        return min(parsed, maximum)
    return parsed


def _parse_int(value: str, *, default: int) -> int:
    if not value.strip():
        return default
    return int(value)


def _parse_bool(value: str, *, default: bool) -> bool:
    if not value.strip():
        return default
    return value.strip().casefold() in {"1", "true", "yes", "y", "on"}


def _truthy(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().casefold() not in {"0", "false", "no", "n", "off", "disabled"}
