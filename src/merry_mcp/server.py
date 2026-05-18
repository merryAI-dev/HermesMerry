from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from merry_mcp.registry import TOOL_REGISTRY, allowed_tool_names
from merry_runtime.pii import redact_pii


class UnknownMCPToolError(ValueError):
    pass


class MCPPayloadError(ValueError):
    pass


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class MerryMCPServer:
    handlers: dict[str, ToolHandler]
    max_payload_bytes: int = 32_768

    def list_tools(self) -> tuple[str, ...]:
        return allowed_tool_names()

    def call_tool(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if name not in TOOL_REGISTRY:
            raise UnknownMCPToolError(f"Tool is not allowed: {name}")
        self._validate_payload_size(payload)
        self._validate_required_fields(name, payload)

        sanitized_payload = self._sanitize_payload(name, payload)
        if name not in self.handlers:
            raise UnknownMCPToolError(f"No handler registered for allowed tool: {name}")
        return self.handlers[name](sanitized_payload)

    def _validate_payload_size(self, payload: dict[str, Any]) -> None:
        payload_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if payload_size > self.max_payload_bytes:
            raise MCPPayloadError(f"Payload exceeds max size: {payload_size} > {self.max_payload_bytes}")

    @staticmethod
    def _validate_required_fields(name: str, payload: dict[str, Any]) -> None:
        schema = TOOL_REGISTRY[name].input_schema
        missing = [field for field in schema.get("required", []) if field not in payload]
        if missing:
            raise MCPPayloadError(f"Missing required fields for {name}: {missing}")

    @staticmethod
    def _sanitize_payload(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        sanitized = dict(payload)
        if name == "send_slack_summary" and "summary" in sanitized:
            sanitized["summary"] = redact_pii(str(sanitized["summary"]))
        return sanitized
