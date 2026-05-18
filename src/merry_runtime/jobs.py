from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from merry_mcp.registry import allowed_tool_names
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
        choices=["ingest-sources", "resolve-entities", "score-candidates", "sync-review-sheet", "weekly-summary"],
    )
    run_parser.add_argument("--sources-json", default="", help="Inline JSON source list for ingest-sources.")
    run_parser.add_argument("--sources-file", default="", help="Path to JSON source list for ingest-sources.")
    run_parser.add_argument("--ac-id", default="", help="AC profile ID for score/review jobs. Defaults to AC_ID env.")

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

        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
