from __future__ import annotations

import base64
from dataclasses import dataclass
from email.message import EmailMessage
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


@dataclass(slots=True)
class GmailDraftClient:
    service: Any
    user_id: str = "me"
    from_name: str = "Merry"

    def create_draft(self, *, to: str, subject: str, body_text: str) -> str:
        message = EmailMessage()
        message["To"] = to
        message["From"] = self.from_name
        message["Subject"] = subject
        message.set_content(body_text)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        response = (
            self.service.users()
            .drafts()
            .create(userId=self.user_id, body={"message": {"raw": raw}})
            .execute()
        )
        return str(response.get("id") or response.get("message", {}).get("id") or "")
