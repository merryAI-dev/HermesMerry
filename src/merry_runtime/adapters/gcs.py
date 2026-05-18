from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from google.api_core import exceptions as google_exceptions
except ImportError:  # pragma: no cover - exercised only when google deps are unavailable
    _CREATE_ONLY_UPLOAD_EXISTS_EXCEPTIONS: tuple[type[Exception], ...] = ()
else:
    _CREATE_ONLY_UPLOAD_EXISTS_EXCEPTIONS = (
        google_exceptions.AlreadyExists,
        google_exceptions.PreconditionFailed,
    )


@dataclass(slots=True)
class GCSObjectStore:
    client: Any
    bucket: str

    def write_raw_text(self, *, path: str, text: str, content_type: str) -> str:
        normalized_path = path.lstrip("/")
        blob = self.client.bucket(self.bucket).blob(normalized_path)
        uri = f"gs://{self.bucket}/{normalized_path}"
        try:
            blob.upload_from_string(text, content_type=content_type, if_generation_match=0)
        except _CREATE_ONLY_UPLOAD_EXISTS_EXCEPTIONS:
            return uri
        return uri
