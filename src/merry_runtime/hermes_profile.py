from __future__ import annotations

from copy import deepcopy
from typing import Any


DANGEROUS_TOOLSETS = {
    "terminal",
    "file",
    "code_execution",
    "computer_use",
    "delegation",
    "cronjob",
}


class HermesProfileError(ValueError):
    pass


def build_production_profile() -> dict[str, Any]:
    return {
        "toolsets": {**{tool: False for tool in DANGEROUS_TOOLSETS}, "merry_ac": True},
        "terminal": {"backend": "docker"},
        "tool_loop_guardrails": {"hard_stop_enabled": True},
        "agent": {"max_turns": 20},
        "yolo": False,
    }


def validate_tool_lockdown(profile: dict[str, Any]) -> dict[str, Any]:
    inspected = deepcopy(profile)
    toolsets = inspected.get("toolsets", {})

    missing = sorted(tool for tool in DANGEROUS_TOOLSETS if tool not in toolsets)
    enabled = sorted(tool for tool in DANGEROUS_TOOLSETS if toolsets.get(tool) is not False)
    if missing or enabled:
        raise HermesProfileError(f"Dangerous toolsets must be explicitly disabled. missing={missing}, enabled={enabled}")

    if inspected.get("terminal", {}).get("backend") != "docker":
        raise HermesProfileError("terminal.backend must be docker even when terminal is disabled")

    if inspected.get("agent", {}).get("max_turns", 999) > 20:
        raise HermesProfileError("agent.max_turns must be 20 or lower")

    if inspected.get("tool_loop_guardrails", {}).get("hard_stop_enabled") is not True:
        raise HermesProfileError("tool_loop_guardrails.hard_stop_enabled must be true")

    if inspected.get("yolo") is not False:
        raise HermesProfileError("yolo mode must be false")

    return inspected
