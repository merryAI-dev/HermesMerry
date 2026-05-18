from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GCSObjectStore:
    client: Any
    bucket: str

    def write_raw_text(self, *, path: str, text: str, content_type: str) -> str:
        normalized_path = path.lstrip("/")
        blob = self.client.bucket(self.bucket).blob(normalized_path)
        blob.upload_from_string(text, content_type=content_type)
        return f"gs://{self.bucket}/{normalized_path}"
