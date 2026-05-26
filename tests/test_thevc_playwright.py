import pytest

from merry_runtime.adapters.thevc_playwright import (
    TheVCFetchResult,
    TheVCHumanVerificationError,
    TheVCPlaywrightClient,
    extract_thevc_sources_from_rendered_pages,
)


def test_extract_thevc_sources_from_rendered_pages_deduplicates_profiles() -> None:
    first_page = """
        <tr>
          <td><time>2026-05-22</time><button>보도자료</button></td>
          <td><span>로민</span><span>텍스트스코프</span><div>AI 문서 인식 솔루션</div></td>
          <td><div>투자대상분야</div><div>엔터프라이즈</div></td>
          <td><div>투자단계</div><div>Series A</div></td>
          <td><div>투자금액</div><button>로그인 필요</button></td>
          <td><div>투자자</div><span>네이버클라우드</span></td>
          <td><a href="/lomin">프로필 확인</a></td>
        </tr>
    """
    second_page = """
        <tr>
          <td><time>2026-05-22</time><button>보도자료</button></td>
          <td><span>로민</span><span>텍스트스코프</span><div>AI 문서 인식 솔루션</div></td>
          <td><div>투자대상분야</div><div>엔터프라이즈</div></td>
          <td><div>투자단계</div><div>Series A</div></td>
          <td><div>투자금액</div><button>로그인 필요</button></td>
          <td><div>투자자</div><span>네이버클라우드</span></td>
          <td><a href="/lomin">프로필 확인</a></td>
        </tr>
        <tr>
          <td><time>2026-05-21</time><button>보도자료</button></td>
          <td><span>뉴라텍</span><span>와이파이 칩</span><div>저전력 Wi-Fi SoC</div></td>
          <td><div>투자대상분야</div><div>반도체/디스플레이</div></td>
          <td><div>투자단계</div><div>Pre-IPO</div></td>
          <td><div>투자금액</div><button>로그인 필요</button></td>
          <td><div>투자자</div><span>케이비증권 +5</span></td>
          <td><a href="/newratek">프로필 확인</a></td>
        </tr>
    """

    sources = extract_thevc_sources_from_rendered_pages(
        [first_page, second_page],
        source_url="https://thevc.kr/",
        max_cards=10,
    )

    assert len(sources) == 2
    assert "Company: 로민" in sources[0]["payload"]
    assert "Source URI: https://thevc.kr/lomin" in sources[0]["payload"]
    assert "Company: 뉴라텍" in sources[1]["payload"]


def test_thevc_playwright_result_reports_login_failure_while_returning_public_sources() -> None:
    client = _FakeTheVCClient(
        page=_FakeTheVCPage(
            html="""
                <tr>
                  <td><time>2026-05-22</time><button>보도자료</button></td>
                  <td><span>로민</span><span>텍스트스코프</span><div>AI 문서 인식 솔루션</div></td>
                  <td><div>투자대상분야</div><div>엔터프라이즈</div></td>
                  <td><div>투자단계</div><div>Series A</div></td>
                  <td><div>투자금액</div><button>로그인 필요</button></td>
                  <td><div>투자자</div><span>네이버클라우드</span></td>
                  <td><a href="/lomin">프로필 확인</a></td>
                </tr>
            """,
            has_login_button=True,
            login_succeeds=False,
        )
    )

    result = client.fetch_investment_result(
        {
            "url": "https://thevc.kr/",
            "source_kind": "thevc_investment_ma",
            "max_cards": "5",
            "max_pages": "1",
            "detail_enrichment": "false",
        }
    )

    assert isinstance(result, TheVCFetchResult)
    assert result.login_status == "failed"
    assert "THE VC login failed" in result.warning_message
    assert len(result.sources) == 1
    assert "Company: 로민" in result.sources[0]["payload"]


def test_thevc_playwright_required_login_failure_raises() -> None:
    client = _FakeTheVCClient(
        page=_FakeTheVCPage(
            html="<tr><td><time>2026-05-22</time></td></tr>",
            has_login_button=True,
            login_succeeds=False,
        )
    )

    with pytest.raises(RuntimeError, match="THE VC login failed"):
        client.fetch_investment_result(
            {
                "url": "https://thevc.kr/",
                "source_kind": "thevc_investment_ma",
                "thevc_login_required": "true",
            }
        )


def test_thevc_playwright_required_login_without_credentials_raises() -> None:
    client = _FakeTheVCClient(
        page=_FakeTheVCPage(
            html="<tr><td><time>2026-05-22</time></td></tr>",
            has_login_button=True,
        ),
        user_email="",
        password="",
    )

    with pytest.raises(RuntimeError, match="credentials are not configured"):
        client.fetch_investment_result(
            {
                "url": "https://thevc.kr/",
                "source_kind": "thevc_investment_ma",
                "thevc_login_required": "true",
            }
        )


def test_thevc_playwright_result_raises_for_human_verification_instead_of_empty_sources() -> None:
    client = _FakeTheVCClient(
        page=_FakeTheVCPage(
            html="<html><title>Human Verification</title><body>Let's confirm you are human</body></html>",
            title="Human Verification",
            body_text="Let's confirm you are human",
            app_ready=False,
        )
    )

    with pytest.raises(TheVCHumanVerificationError):
        client.fetch_investment_result(
            {
                "url": "https://thevc.kr/",
                "source_kind": "thevc_investment_ma",
                "max_cards": "5",
                "max_pages": "1",
            }
        )


class _FakeTheVCClient(TheVCPlaywrightClient):
    def __init__(
        self,
        *,
        page: "_FakeTheVCPage",
        user_email: str = "operator@example.com",
        password: str = "password",
    ) -> None:
        super().__init__(user_email=user_email, password=password)
        self._fake_page = page

    def _ensure_page(self) -> "_FakeTheVCPage":
        return self._fake_page


class _FakeTheVCPage:
    def __init__(
        self,
        *,
        html: str,
        title: str = "더브이씨 (THE VC) - 한국 스타트업 투자 데이터베이스",
        body_text: str = "투자/M&A 가입 / 로그인 로그인 필요",
        has_login_button: bool = False,
        login_succeeds: bool = False,
        app_ready: bool = True,
    ) -> None:
        self.html = html
        self._title = title
        self._body_text = body_text
        self.has_login_button = has_login_button
        self.login_succeeds = login_succeeds
        self.app_ready = app_ready
        self.keyboard = _FakeKeyboard()

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        self.url = url

    def content(self) -> str:
        return self.html

    def title(self) -> str:
        return self._title

    def wait_for_function(self, script: str, *args, timeout: int) -> None:
        if "document.title.includes" in script and not self.app_ready:
            raise TimeoutError("app never loaded")
        if "가입 / 로그인" in script and not self.login_succeeds:
            raise TimeoutError("login failed")
        if self.login_succeeds:
            self.has_login_button = False

    def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        return None

    def wait_for_timeout(self, timeout: int) -> None:
        return None

    def evaluate(self, script: str, *args):
        if "가입 / 로그인" in script and "querySelectorAll('button')" in script:
            return self.has_login_button
        if "querySelectorAll('tr')" in script:
            return self.html
        if "에러" in script:
            return "알 수 없는 에러가 발생했습니다."
        return False

    def get_by_role(self, role: str, *, name):
        return _FakeLocator(page=self, role=role, name=name)

    def locator(self, selector: str):
        return _FakeBodyLocator(self._body_text)


class _FakeLocator:
    def __init__(self, *, page: _FakeTheVCPage, role: str, name) -> None:
        self.page = page
        self.role = role
        self.name = name
        self.first = self

    def count(self) -> int:
        if self.role == "button" and str(self.name).startswith("re.compile"):
            return 0
        if self.role == "button" and self.name == "투자/M&A 더 보기":
            return 0
        if self.role == "button" and self.name == "다음 페이지 보기":
            return 0
        return 1

    def fill(self, value: str) -> None:
        return None

    def click(self, *, force: bool = False) -> None:
        return None

    def inner_text(self, *, timeout: int) -> str:
        return ""


class _FakeBodyLocator:
    def __init__(self, text: str) -> None:
        self.text = text

    def inner_text(self, *, timeout: int) -> str:
        return self.text


class _FakeKeyboard:
    def press(self, key: str) -> None:
        return None
