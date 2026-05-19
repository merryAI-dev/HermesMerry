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
    slack_channel: str = ""

    def list_tools(self) -> tuple[str, ...]:
        return allowed_tool_names()

    def call_tool(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if name not in TOOL_REGISTRY:
            raise UnknownMCPToolError(f"Tool is not allowed: {name}")
        self._validate_payload_size(payload)
        self._validate_payload_schema(name, payload)

        sanitized_payload = self._sanitize_payload(name, payload)
        if name not in self.handlers:
            raise UnknownMCPToolError(f"No handler registered for allowed tool: {name}")
        return self.handlers[name](sanitized_payload)

    def _validate_payload_size(self, payload: dict[str, Any]) -> None:
        payload_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if payload_size > self.max_payload_bytes:
            raise MCPPayloadError(f"Payload exceeds max size: {payload_size} > {self.max_payload_bytes}")

    @classmethod
    def _validate_payload_schema(cls, name: str, payload: dict[str, Any]) -> None:
        schema = TOOL_REGISTRY[name].input_schema
        missing = [field for field in schema.get("required", []) if field not in payload]
        if missing:
            raise MCPPayloadError(f"Missing required fields for {name}: {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra_fields = sorted(set(payload) - set(properties))
            if extra_fields:
                raise MCPPayloadError(f"Payload contains additional fields for {name}: {extra_fields}")
        for field, value in payload.items():
            cls._validate_field(name, field, value, properties[field])

    @staticmethod
    def _validate_field(name: str, field: str, value: Any, field_schema: dict[str, Any]) -> None:
        field_type = field_schema.get("type")
        if field_type == "string" and not isinstance(value, str):
            raise MCPPayloadError(f"{name}.{field} must be string")
        if field_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise MCPPayloadError(f"{name}.{field} must be integer")
        if field_type == "object" and not isinstance(value, dict):
            raise MCPPayloadError(f"{name}.{field} must be object")
        if field_type == "array" and not isinstance(value, list):
            raise MCPPayloadError(f"{name}.{field} must be array")
        minimum = field_schema.get("minimum")
        if minimum is not None and isinstance(value, int) and not isinstance(value, bool) and value < int(minimum):
            raise MCPPayloadError(f"{name}.{field} is too small: {value} < {minimum}")
        maximum = field_schema.get("maximum")
        if maximum is not None and isinstance(value, int) and not isinstance(value, bool) and value > int(maximum):
            raise MCPPayloadError(f"{name}.{field} is too large: {value} > {maximum}")
        max_items = field_schema.get("maxItems")
        if max_items is not None and isinstance(value, list) and len(value) > int(max_items):
            raise MCPPayloadError(f"{name}.{field} has too many items: {len(value)} > {max_items}")
        allowed_values = field_schema.get("enum")
        if allowed_values and value not in allowed_values:
            raise MCPPayloadError(f"{name}.{field} value is not allowed: {value}")
        max_length = field_schema.get("maxLength")
        if max_length is not None and isinstance(value, str) and len(value) > int(max_length):
            raise MCPPayloadError(f"{name}.{field} is too long: {len(value)} > {max_length}")

    def _sanitize_payload(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        sanitized = dict(payload)
        if name == "send_slack_summary":
            if not self.slack_channel:
                raise MCPPayloadError("send_slack_summary requires a configured Slack channel")
            sanitized["channel"] = self.slack_channel
            sanitized["summary"] = redact_pii(str(sanitized["summary"]))
        return sanitized
