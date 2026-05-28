#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from merry_runtime.github_qa_context import collect_repo_evidence
from merry_runtime.github_qa_issue import (
    build_qa_issue_body,
    build_qa_issue_title,
    build_slack_issue_reply,
    create_github_issue,
)
from merry_runtime.hermes_qa_delegation import build_hermes_qa_prompt, run_hermes_qa_handoff
from merry_runtime.slack_qa_triage import build_github_search_terms, build_qa_draft, extract_qa_event


DEFAULT_QA_CHANNEL = "C0AH3LQ00AD"
DEFAULT_STATE_FILE = "tmp/hermes/slack-qa-realtime-state.json"
DEFAULT_GITHUB_REPO = "merryAI-dev/startup-diagnostic-platform"
DEFAULT_BORAM_SLACK_USER_ID = "U099F3KA1CL"


def main(argv: Sequence[str] | None = None) -> int:
    _load_local_env_files()

    parser = argparse.ArgumentParser(description="Watch Slack QA messages and draft GitHub-grounded replies.")
    parser.add_argument("--channel", default=os.getenv("SLACK_QA_CHANNEL", DEFAULT_QA_CHANNEL))
    parser.add_argument("--repo", action="append", default=[], help="Repository path to search. May be repeated.")
    parser.add_argument("--limit", type=int, default=30, help="Slack history limit for --once.")
    parser.add_argument("--state-file", default=os.getenv("SLACK_QA_STATE_FILE", DEFAULT_STATE_FILE))
    parser.add_argument("--send", action="store_true", help="Post drafts to Slack. Default prints JSON only.")
    parser.add_argument("--once", action="store_true", help="Process recent history once instead of listening.")
    parser.add_argument("--poll-interval", type=int, default=20, help="Polling interval in seconds for live mode.")
    parser.add_argument("--socket-mode", action="store_true", help="Use Slack Socket Mode instead of history polling.")
    parser.add_argument(
        "--delegate",
        choices=("hermes", "local"),
        default=os.getenv("SLACK_QA_DELEGATE", "hermes"),
        help="Draft generator. hermes uses Hermes Agent CLI; local uses deterministic fallback.",
    )
    parser.add_argument("--github-repo", default=os.getenv("SLACK_QA_GITHUB_REPO", DEFAULT_GITHUB_REPO))
    parser.add_argument(
        "--github-assignee",
        action="append",
        default=_env_list("SLACK_QA_GITHUB_ASSIGNEES", default="merryAI-dev"),
        help="GitHub issue assignee. May be repeated.",
    )
    parser.add_argument(
        "--github-label",
        action="append",
        default=_env_list("SLACK_QA_GITHUB_LABELS"),
        help="GitHub issue label. May be repeated; label must already exist.",
    )
    parser.add_argument(
        "--reviewer-slack-user",
        default=os.getenv("SLACK_QA_REVIEWER_SLACK_USER_ID", DEFAULT_BORAM_SLACK_USER_ID),
        help="Slack user ID to mention after creating the issue.",
    )
    parser.add_argument(
        "--create-github-issue",
        action=argparse.BooleanOptionalAction,
        default=_env_bool("SLACK_QA_CREATE_GITHUB_ISSUE", True),
        help="Create a GitHub issue when --send is active.",
    )
    parser.add_argument(
        "--ignore-existing-on-start",
        action="store_true",
        help="Mark recent history as seen before entering live polling.",
    )
    args = parser.parse_args(argv)

    repo_paths = _repo_paths(args.repo)
    state_path = Path(args.state_file)
    processed_keys = _load_processed_keys(state_path)

    if args.once:
        result = _process_recent_history(
            channel=args.channel,
            limit=args.limit,
            repo_paths=repo_paths,
            processed_keys=processed_keys,
            send=args.send,
            delegate=args.delegate,
            github_issue_enabled=args.create_github_issue and args.send,
            github_repo=args.github_repo,
            github_assignees=args.github_assignee,
            github_labels=args.github_label,
            reviewer_slack_user_id=args.reviewer_slack_user,
        )
        if args.send:
            _save_processed_keys(state_path, processed_keys | set(result["processed_keys"]))
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.socket_mode:
        _listen_socket_mode(
            channel=args.channel,
            repo_paths=repo_paths,
            state_path=state_path,
            processed_keys=processed_keys,
            send=args.send,
            delegate=args.delegate,
            github_issue_enabled=args.create_github_issue and args.send,
            github_repo=args.github_repo,
            github_assignees=args.github_assignee,
            github_labels=args.github_label,
            reviewer_slack_user_id=args.reviewer_slack_user,
        )
    else:
        _poll_history(
            channel=args.channel,
            limit=args.limit,
            repo_paths=repo_paths,
            state_path=state_path,
            processed_keys=processed_keys,
            send=args.send,
            poll_interval=args.poll_interval,
            ignore_existing_on_start=args.ignore_existing_on_start,
            delegate=args.delegate,
            github_issue_enabled=args.create_github_issue,
            github_repo=args.github_repo,
            github_assignees=args.github_assignee,
            github_labels=args.github_label,
            reviewer_slack_user_id=args.reviewer_slack_user,
        )
    return 0


def _process_recent_history(
    *,
    channel: str,
    limit: int,
    repo_paths: list[Path],
    processed_keys: set[str],
    send: bool,
    delegate: str,
    github_issue_enabled: bool,
    github_repo: str,
    github_assignees: list[str],
    github_labels: list[str],
    reviewer_slack_user_id: str,
) -> dict[str, Any]:
    from slack_sdk import WebClient

    client = _web_client()
    response = client.conversations_history(channel=channel, limit=limit)
    planned: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    newly_processed: set[str] = set()

    for message in reversed(response.get("messages", []) or []):
        plan = _plan_message(
            message=message,
            channel=channel,
            repo_paths=repo_paths,
            processed_keys=processed_keys | newly_processed,
            delegate=delegate,
            create_issue=github_issue_enabled,
            github_repo=github_repo,
            github_assignees=github_assignees,
            github_labels=github_labels,
            reviewer_slack_user_id=reviewer_slack_user_id,
        )
        if plan is None:
            skipped.append({"ts": str(message.get("ts") or ""), "reason": "not_qa_or_duplicate"})
            continue
        planned.append(plan)
        newly_processed.add(plan["dedupe_key"])
        if send:
            _post_draft(client, channel=channel, thread_ts=plan["thread_ts"], text=plan["draft"])

    return {
        "dry_run": not send,
        "planned_count": len(planned),
        "skipped_count": len(skipped),
        "processed_keys": sorted(newly_processed),
        "planned": planned,
        "skipped": skipped,
    }


def _poll_history(
    *,
    channel: str,
    limit: int,
    repo_paths: list[Path],
    state_path: Path,
    processed_keys: set[str],
    send: bool,
    poll_interval: int,
    ignore_existing_on_start: bool,
    delegate: str,
    github_issue_enabled: bool,
    github_repo: str,
    github_assignees: list[str],
    github_labels: list[str],
    reviewer_slack_user_id: str,
) -> None:
    print(
        json.dumps(
            {
                "status": "polling",
                "channel": channel,
                "send": send,
                "poll_interval": poll_interval,
                "delegate": delegate,
                "github_issue_enabled": github_issue_enabled and send,
                "github_repo": github_repo,
                "repo_paths": [str(path) for path in repo_paths],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    if ignore_existing_on_start:
        result = _process_recent_history(
            channel=channel,
            limit=limit,
            repo_paths=repo_paths,
            processed_keys=processed_keys,
            send=False,
            delegate=delegate,
            github_issue_enabled=False,
            github_repo=github_repo,
            github_assignees=github_assignees,
            github_labels=github_labels,
            reviewer_slack_user_id=reviewer_slack_user_id,
        )
        seen_keys = set(result["processed_keys"])
        if seen_keys:
            processed_keys.update(seen_keys)
            _save_processed_keys(state_path, processed_keys)
            print(
                json.dumps(
                    {"status": "marked_existing_history", "count": len(seen_keys)},
                    ensure_ascii=False,
                ),
                flush=True,
            )
    while True:
        result = _process_recent_history(
            channel=channel,
            limit=limit,
            repo_paths=repo_paths,
            processed_keys=processed_keys,
            send=send,
            delegate=delegate,
            github_issue_enabled=github_issue_enabled and send,
            github_repo=github_repo,
            github_assignees=github_assignees,
            github_labels=github_labels,
            reviewer_slack_user_id=reviewer_slack_user_id,
        )
        new_keys = set(result["processed_keys"])
        if new_keys:
            processed_keys.update(new_keys)
            _save_processed_keys(state_path, processed_keys)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        time.sleep(max(poll_interval, 5))


def _listen_socket_mode(
    *,
    channel: str,
    repo_paths: list[Path],
    state_path: Path,
    processed_keys: set[str],
    send: bool,
    delegate: str,
    github_issue_enabled: bool,
    github_repo: str,
    github_assignees: list[str],
    github_labels: list[str],
    reviewer_slack_user_id: str,
) -> None:
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.response import SocketModeResponse

    app_token = os.getenv("SLACK_APP_TOKEN", "")
    if not app_token:
        raise SystemExit("Missing SLACK_APP_TOKEN")

    web_client = _web_client()
    auth = web_client.auth_test()
    self_bot_user_id = str(auth.get("user_id") or "")
    socket_client = SocketModeClient(app_token=app_token, web_client=web_client)

    def handle_socket_mode_request(client: SocketModeClient, request: Any) -> None:
        if request.type != "events_api":
            return
        client.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id))

        event = (request.payload or {}).get("event", {})
        if event.get("type") != "message" or event.get("channel") != channel:
            return
        if event.get("user") == self_bot_user_id:
            return

        plan = _plan_message(
            message=event,
            channel=channel,
            repo_paths=repo_paths,
            processed_keys=processed_keys,
            delegate=delegate,
            create_issue=github_issue_enabled and send,
            github_repo=github_repo,
            github_assignees=github_assignees,
            github_labels=github_labels,
            reviewer_slack_user_id=reviewer_slack_user_id,
        )
        if plan is None:
            return

        processed_keys.add(plan["dedupe_key"])
        _save_processed_keys(state_path, processed_keys)
        if send:
            _post_draft(web_client, channel=channel, thread_ts=plan["thread_ts"], text=plan["draft"])
        else:
            print(json.dumps(plan, ensure_ascii=False), flush=True)

    socket_client.socket_mode_request_listeners.append(handle_socket_mode_request)
    socket_client.connect()
    print(
        json.dumps(
            {
                "status": "listening",
                "channel": channel,
                "send": send,
                "delegate": delegate,
                "github_issue_enabled": github_issue_enabled and send,
                "github_repo": github_repo,
                "repo_paths": [str(path) for path in repo_paths],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    while True:
        time.sleep(1)


def _plan_message(
    *,
    message: dict[str, Any],
    channel: str,
    repo_paths: list[Path],
    processed_keys: set[str],
    delegate: str,
    create_issue: bool,
    github_repo: str,
    github_assignees: list[str],
    github_labels: list[str],
    reviewer_slack_user_id: str,
) -> dict[str, Any] | None:
    ts = str(message.get("ts") or "")
    thread_ts = str(message.get("thread_ts") or ts)
    text = _message_text_for_parsing(message)
    event = extract_qa_event(text, channel=channel, message_ts=ts, thread_ts=thread_ts)
    if event is None or event.dedupe_key in processed_keys:
        return None

    terms = build_github_search_terms(event)
    evidence = collect_repo_evidence(terms, repo_paths=repo_paths, limit=8)
    draft_source = delegate
    handoff_error = ""
    if delegate == "hermes":
        try:
            prompt = build_hermes_qa_prompt(event, evidence, repo_paths=repo_paths)
            draft = run_hermes_qa_handoff(prompt, repo_cwd=repo_paths[0] if repo_paths else Path.cwd())
        except Exception as exc:
            draft_source = "local-fallback"
            handoff_error = str(exc)
            draft = build_qa_draft(event, evidence)
    else:
        draft = build_qa_draft(event, evidence)

    issue_url = ""
    issue_error = ""
    if create_issue:
        try:
            issue_title = build_qa_issue_title(event)
            issue_body = build_qa_issue_body(event, hermes_diagnosis=draft, evidence=evidence)
            issue_url = create_github_issue(
                repo_full_name=github_repo,
                title=issue_title,
                body=issue_body,
                assignees=github_assignees,
                labels=github_labels,
            )
            draft = build_slack_issue_reply(
                issue_url=issue_url,
                reviewer_slack_user_id=reviewer_slack_user_id,
            )
        except Exception as exc:
            issue_error = str(exc)
            draft = "\n".join(
                [
                    draft,
                    "",
                    f"GitHub 이슈 생성은 실패했습니다. 보람님 확인이 필요합니다. ({issue_error})",
                ]
            )
    return {
        "dedupe_key": event.dedupe_key,
        "channel": channel,
        "message_ts": ts,
        "thread_ts": thread_ts,
        "summary": event.summary,
        "requester_name": event.requester_name,
        "terms": terms,
        "evidence": [item.to_dict() for item in evidence],
        "draft_source": draft_source,
        "handoff_error": handoff_error,
        "issue_url": issue_url,
        "issue_error": issue_error,
        "draft": draft,
    }


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


def _post_draft(client: Any, *, channel: str, thread_ts: str, text: str) -> None:
    client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=text)


def _web_client() -> Any:
    from slack_sdk import WebClient

    token = os.getenv("SLACK_BOT_TOKEN", "")
    if not token:
        raise SystemExit("Missing SLACK_BOT_TOKEN")
    return WebClient(token=token)


def _repo_paths(values: list[str]) -> list[Path]:
    configured = values or [item for item in os.getenv("SLACK_QA_REPO_PATHS", "").split(":") if item]
    if not configured:
        configured = [str(Path.cwd())]
    return [Path(value).expanduser().resolve() for value in configured]


def _env_list(name: str, *, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _load_processed_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {str(item) for item in payload}
    if isinstance(payload, dict):
        return {str(item) for item in payload.get("processed_keys", [])}
    return set()


def _save_processed_keys(path: Path, processed_keys: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"processed_keys": sorted(processed_keys)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_local_env_files() -> None:
    candidates = [
        Path(os.getenv("HERMES_ENV_FILE", ".env.local")),
        Path.home() / ".hermes" / ".env",
    ]
    for path in candidates:
        if path.exists():
            _load_env_file(path)


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
