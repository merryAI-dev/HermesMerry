from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from merry_mcp.registry import allowed_tool_names
from merry_runtime.agent_loop import run_agent_loop
from merry_runtime.hermes_profile import validate_tool_lockdown
from merry_runtime.job_runner import JobRunError, run_job
from merry_runtime.runtime_config import RuntimeConfig, RuntimeConfigError
from merry_runtime.runtime_factory import build_runtime
from merry_runtime.schema import BIGQUERY_TABLES


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes x Merry runtime jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile_parser = subparsers.add_parser("validate-hermes-profile")
    profile_parser.add_argument(
        "--profile",
        default="configs/hermes-production-profile.json",
        help="Path to a Hermes production profile JSON file.",
    )

    subparsers.add_parser("print-schema")
    subparsers.add_parser("list-mcp-tools")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument(
        "job_name",
        choices=[
            "ingest-sources",
            "ingest-ac-profiles",
            "resolve-entities",
            "score-candidates",
            "sync-review-sheet",
            "calibrate-scores",
            "weekly-summary",
        ],
    )
    run_parser.add_argument("--sources-json", default="", help="Inline JSON source list for ingestion jobs.")
    run_parser.add_argument("--sources-file", default="", help="Path to JSON source list for ingestion jobs.")
    run_parser.add_argument("--ac-id", default="", help="AC profile ID for score/review jobs. Defaults to AC_ID env.")

    loop_parser = subparsers.add_parser("loop")
    loop_parser.add_argument("--max-cycles", type=int, default=None, help="Override AGENT_LOOP_MAX_CYCLES.")
    loop_parser.add_argument("--interval-seconds", type=int, default=None, help="Override AGENT_LOOP_INTERVAL_SECONDS.")

    args = parser.parse_args(argv)

    if args.command == "validate-hermes-profile":
        profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
        validate_tool_lockdown(profile)
        print("Hermes profile lockdown: OK")
        return 0

    if args.command == "print-schema":
        print(json.dumps(BIGQUERY_TABLES, indent=2, sort_keys=True))
        return 0

    if args.command == "list-mcp-tools":
        print("\n".join(allowed_tool_names()))
        return 0

    if args.command == "run":
        sources_json = args.sources_json
        if args.sources_file:
            sources_json = Path(args.sources_file).read_text(encoding="utf-8")

        runtime = None
        started_at = _now()
        config = RuntimeConfig.from_env()
        try:
            config.validate_for_job(args.job_name, has_inline_sources=bool(sources_json))
            runtime = build_runtime(config)
            result = run_job(
                args.job_name,
                runtime=runtime,
                config=config,
                sources_json=sources_json,
                ac_id=args.ac_id,
            )
        except (RuntimeConfigError, JobRunError) as exc:
            print(f"Job failed: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:
            try:
                _record_failed_agent_run(runtime=runtime, job_name=args.job_name, started_at=started_at, exc=exc)
            except Exception:
                pass
            print(f"Job failed: {_bounded_error_message(exc)}", file=sys.stderr)
            return 1

        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "loop":
        config = RuntimeConfig.from_env()
        max_cycles = args.max_cycles if args.max_cycles is not None else config.agent_loop_max_cycles
        try:
            config.validate_for_loop(max_cycles=max_cycles)
            for job_name in config.agent_loop_jobs:
                config.validate_for_job(job_name, has_inline_sources=False)
            runtime = build_runtime(config)
            result = run_agent_loop(
                runtime=runtime,
                config=config,
                jobs=config.agent_loop_jobs,
                interval_seconds=args.interval_seconds
                if args.interval_seconds is not None
                else config.agent_loop_interval_seconds,
                max_cycles=max_cycles,
                sleep_fn=time.sleep,
            )
        except RuntimeConfigError as exc:
            print(f"Job failed: {exc}", file=sys.stderr)
            return 2

        print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
        return 0 if result.failure_count == 0 else 1

    parser.error(f"Unknown command: {args.command}")


def _record_failed_agent_run(*, runtime: object, job_name: str, started_at: str, exc: Exception) -> None:
    structured_store = getattr(runtime, "structured_store", None)
    if structured_store is None:
        return

    finished_at = _now()
    run_id = f"run_failed_{_safe_job_name(job_name)}_{_short_digest(started_at, finished_at, type(exc).__name__)}"
    structured_store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": run_id,
                "job_name": job_name,
                "status": "failed",
                "started_at": started_at,
                "finished_at": finished_at,
                "input_count": 0,
                "output_count": 0,
                "error_message": _bounded_error_message(exc),
            }
        ],
        key_fields=("run_id",),
    )


def _bounded_error_message(exc: Exception, max_length: int = 1000) -> str:
    return f"{type(exc).__name__}: {exc}"[:max_length]


def _safe_job_name(job_name: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in job_name)


def _short_digest(*parts: str) -> str:
    payload = "\n".join(parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
