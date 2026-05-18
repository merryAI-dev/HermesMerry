from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SlackNotifier:
    client: Any

    def send_message(self, *, channel: str, text: str) -> str:
        response = self.client.chat_postMessage(channel=channel, text=text)
        return str(response["ts"])
