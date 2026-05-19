from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.request import Request, urlopen as default_urlopen


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True, slots=True)
class AnthropicMessagesClient:
    api_key: str
    model: str = "claude-sonnet-4-6"
    timeout_seconds: int = 30
    anthropic_version: str = "2023-06-01"
    urlopen: Callable[..., Any] = field(default=default_urlopen, repr=False)

    def complete_json(self, *, system_prompt: str, user_prompt: str, max_tokens: int) -> dict[str, object]:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        request = Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self.anthropic_version,
                "content-type": "application/json",
                "accept": "application/json",
            },
            method="POST",
        )
        with self.urlopen(request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        return _extract_json(_message_text(body))


def _message_text(body: dict[str, Any]) -> str:
    chunks: list[str] = []
    for block in body.get("content", []) or []:
        if isinstance(block, dict) and block.get("type") == "text":
            chunks.append(str(block.get("text") or ""))
    return "\n".join(chunks)


def _extract_json(text: str) -> dict[str, object]:
    match = _JSON_OBJECT.search(text)
    if not match:
        raise ValueError("Anthropic response did not contain a JSON object")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Anthropic response JSON must be an object")
    return parsed
