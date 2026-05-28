from __future__ import annotations

import json
import os
import re
from pathlib import Path


def load_requester_map(*, map_json: str = "", map_path: str = "") -> dict[str, str]:
    """Load explicit requester-to-Slack-user-id mappings.

    Slack display-name search is intentionally not used here. Mentioning the
    wrong person is worse than skipping a notification, so mappings must be
    explicit through JSON or a JSON file.
    """
    merged: dict[str, str] = {}
    path_value = map_path or os.getenv("SLACK_REQUESTER_MAP_PATH", "")
    json_value = map_json or os.getenv("SLACK_REQUESTER_MAP_JSON", "")

    if path_value.strip():
        payload = json.loads(Path(path_value).read_text(encoding="utf-8"))
        merged.update(_normalize_mapping(payload))

    if json_value.strip():
        payload = json.loads(json_value)
        merged.update(_normalize_mapping(payload))

    return merged


def resolve_requester_user_id(requester: str, requester_map: dict[str, str]) -> str | None:
    for alias in requester_aliases(requester):
        user_id = requester_map.get(alias)
        if user_id:
            return user_id
    return None


def requester_aliases(requester: str) -> tuple[str, ...]:
    value = " ".join(str(requester or "").split())
    if not value:
        return ()

    aliases: list[str] = [value]
    Korean = r"[가-힣]{2,5}"
    nickname_matches = re.findall(r"\(([^)]+)\)", value)
    aliases.extend(nickname.strip() for nickname in nickname_matches if nickname.strip())

    korean_names = re.findall(Korean, value)
    aliases.extend(korean_names)

    if nickname_matches and korean_names:
        aliases.append(f"{korean_names[0]}({nickname_matches[0].strip()})")
        aliases.append(f"{korean_names[0]} ({nickname_matches[0].strip()})")

    deduped: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        normalized = alias.strip()
        if normalized and normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return tuple(deduped)


def _normalize_mapping(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("Slack requester map must be a JSON object")

    normalized: dict[str, str] = {}
    for key, value in payload.items():
        alias = str(key).strip()
        user_id = str(value).strip()
        if alias and user_id:
            normalized[alias] = user_id
    return normalized
