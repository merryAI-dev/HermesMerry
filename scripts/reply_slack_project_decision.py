#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from merry_runtime.slack_project_decisions import parse_project_decision_events, plan_rejection_notifications
from merry_runtime.slack_requester_resolver import load_requester_map


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Batch-read InnerPlatform review messages and mention requesters for rejection decisions."
    )
    parser.add_argument("--channel", default=os.getenv("SLACK_PROJECT_DECISION_CHANNEL", ""))
    parser.add_argument("--input-file", default="", help="Optional exported Slack text. If omitted, read Slack history.")
    parser.add_argument("--limit", type=int, default=50, help="Slack history read limit.")
    parser.add_argument("--map-json", default="", help="Requester map JSON. Overrides/extends SLACK_REQUESTER_MAP_JSON.")
    parser.add_argument("--map-path", default="", help="Requester map file. Overrides/extends SLACK_REQUESTER_MAP_PATH.")
    parser.add_argument(
        "--state-file",
        default="tmp/hermes/slack-project-decision-notifications.json",
        help="Sent dedupe key state file.",
    )
    parser.add_argument("--send", action="store_true", help="Actually post Slack messages. Default is dry-run.")
    args = parser.parse_args(argv)

    requester_map = load_requester_map(map_json=args.map_json, map_path=args.map_path)
    sent_keys = _load_sent_keys(Path(args.state_file))

    if args.input_file:
        input_text = sys.stdin.read() if args.input_file == "-" else Path(args.input_file).read_text(encoding="utf-8")
        events = parse_project_decision_events(input_text, channel=args.channel)
    else:
        if not args.channel:
            raise SystemExit("Missing --channel or SLACK_PROJECT_DECISION_CHANNEL")
        events = _read_slack_history(channel=args.channel, limit=args.limit)

    notifications, skipped = plan_rejection_notifications(events, requester_map=requester_map, sent_keys=sent_keys)

    result: dict[str, Any] = {
        "dry_run": not args.send,
        "event_count": len(events),
        "notification_count": len(notifications),
        "skipped_count": len(skipped),
        "notifications": [notification.to_dict() for notification in notifications],
        "skipped": skipped,
    }

    if args.send:
        _post_notifications(args.channel, notifications)
        _save_sent_keys(Path(args.state_file), sent_keys | {notification.dedupe_key for notification in notifications})
        result["sent_count"] = len(notifications)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _read_slack_history(*, channel: str, limit: int) -> list[Any]:
    from slack_sdk import WebClient

    token = os.getenv("SLACK_BOT_TOKEN", "")
    if not token:
        raise SystemExit("Missing SLACK_BOT_TOKEN")

    client = WebClient(token=token)
    response = client.conversations_history(channel=channel, limit=limit)
    events = []
    for message in response.get("messages", []):
        text = _message_text_for_parsing(message)
        ts = str(message.get("ts") or "")
        thread_ts = str(message.get("thread_ts") or ts)
        events.extend(parse_project_decision_events(text, channel=channel, message_ts=ts, thread_ts=thread_ts))
    return events


def _message_text_for_parsing(message: dict[str, Any]) -> str:
    parts = [str(message.get("text") or "")]
    for block in message.get("blocks", []) or []:
        if not isinstance(block, dict):
            continue
        text_obj = block.get("text")
        if isinstance(text_obj, dict) and text_obj.get("text"):
            parts.append(str(text_obj["text"]))
        for field in block.get("fields", []) or []:
            if isinstance(field, dict) and field.get("text"):
                parts.append(str(field["text"]))
    return "\n".join(part for part in parts if part)


def _post_notifications(channel: str, notifications: list[Any]) -> None:
    from slack_sdk import WebClient

    token = os.getenv("SLACK_BOT_TOKEN", "")
    if not token:
        raise SystemExit("Missing SLACK_BOT_TOKEN")

    client = WebClient(token=token)
    for notification in notifications:
        event = notification.event
        target_channel = event.channel or channel
        kwargs: dict[str, str] = {"channel": target_channel, "text": notification.text}
        if event.thread_ts or event.message_ts:
            kwargs["thread_ts"] = event.thread_ts or event.message_ts
        client.chat_postMessage(**kwargs)


def _load_sent_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {str(item) for item in payload}
    if isinstance(payload, dict):
        return {str(item) for item in payload.get("sent_keys", [])}
    return set()


def _save_sent_keys(path: Path, sent_keys: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"sent_keys": sorted(sent_keys)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
