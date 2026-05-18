from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GmailLabelSource:
    service: Any
    user_id: str
    label_id: str

    def fetch_labeled_messages(self, *, max_results: int = 50) -> list[dict[str, object]]:
        response = self.service.users().messages().list(
            userId=self.user_id,
            labelIds=[self.label_id],
            maxResults=max_results,
        ).execute()
        messages = response.get("messages", [])
        return [
            self.service.users().messages().get(userId=self.user_id, id=message["id"], format="full").execute()
            for message in messages
        ]
