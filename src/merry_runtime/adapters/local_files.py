from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class LocalFileObjectStore:
    root: Path

    def write_raw_text(self, *, path: str, text: str, content_type: str) -> str:
        del content_type
        destination = self._safe_destination(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_text(text, encoding="utf-8")
        return destination.as_uri()

    def _safe_destination(self, path: str) -> Path:
        relative = Path(path.lstrip("/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe raw object path: {path}")
        root = self.root.resolve()
        destination = (root / relative).resolve()
        if root != destination and root not in destination.parents:
            raise ValueError(f"unsafe raw object path: {path}")
        return destination
