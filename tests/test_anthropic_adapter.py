from __future__ import annotations

import json
from io import BytesIO

from merry_runtime.adapters.anthropic import AnthropicMessagesClient


class FakeResponse(BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


class CapturingUrlopen:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.request = None
        self.timeout = None

    def __call__(self, request, *, timeout: int):
        self.request = request
        self.timeout = timeout
        return FakeResponse(json.dumps(self.payload).encode("utf-8"))


def test_anthropic_messages_client_extracts_first_json_object_from_text_response() -> None:
    urlopen = CapturingUrlopen(
        {
            "content": [
                {
                    "type": "text",
                    "text": '근거만 추출했습니다. {"status":"success","external_aum_eok":1107,"confidence":0.86}',
                }
            ]
        }
    )
    client = AnthropicMessagesClient(
        api_key="test-key",
        model="claude-sonnet-4-6",
        timeout_seconds=9,
        urlopen=urlopen,
    )

    result = client.complete_json(system_prompt="system", user_prompt="user", max_tokens=512)

    assert result == {"status": "success", "external_aum_eok": 1107, "confidence": 0.86}
    assert urlopen.timeout == 9
    assert urlopen.request.full_url == "https://api.anthropic.com/v1/messages"
    assert urlopen.request.headers["X-api-key"] == "test-key"
    assert urlopen.request.headers["Anthropic-version"] == "2023-06-01"
    body = json.loads(urlopen.request.data.decode("utf-8"))
    assert body["model"] == "claude-sonnet-4-6"
    assert body["system"] == "system"
    assert body["messages"] == [{"role": "user", "content": "user"}]
