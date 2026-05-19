from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.request import Request, urlopen as default_urlopen


@dataclass(slots=True)
class AppsScriptDraftClient:
    webhook_url: str
    secret: str
    timeout_seconds: float = 10.0
    clock: Callable[[], int] = lambda: int(time.time())
    nonce_factory: Callable[[], str] = lambda: uuid.uuid4().hex
    urlopen: Callable[..., Any] = field(default=default_urlopen, repr=False)

    def create_draft(self, *, to: str, subject: str, body_text: str) -> str:
        timestamp = str(int(self.clock()))
        nonce = self.nonce_factory()
        body_sha256 = hashlib.sha256(body_text.encode("utf-8")).hexdigest()
        payload = {
            "timestamp": timestamp,
            "nonce": nonce,
            "to": to,
            "subject": subject,
            "body_text": body_text,
            "body_sha256": body_sha256,
            "signature": self._signature(
                timestamp=timestamp,
                nonce=nonce,
                to=to,
                subject=subject,
                body_sha256=body_sha256,
            ),
        }
        request = Request(
            self.webhook_url,
            data=json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response = self.urlopen(request, timeout=self.timeout_seconds)
        try:
            response_payload = json.loads(response.read().decode("utf-8"))
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        if not bool(response_payload.get("ok")):
            raise RuntimeError(str(response_payload.get("error") or "Apps Script draft gateway rejected request"))
        draft_id = str(response_payload.get("draft_id") or response_payload.get("id") or "")
        if not draft_id:
            raise RuntimeError("Apps Script draft gateway response did not include draft_id")
        return draft_id

    def _signature(self, *, timestamp: str, nonce: str, to: str, subject: str, body_sha256: str) -> str:
        signing_payload = f"{timestamp}\n{nonce}\n{to}\n{subject}\n{body_sha256}"
        return hmac.new(self.secret.encode("utf-8"), signing_payload.encode("utf-8"), hashlib.sha256).hexdigest()
