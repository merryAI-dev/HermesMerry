from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from merry_mcp.registry import allowed_tool_names
from merry_runtime.hermes_profile import validate_tool_lockdown
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
        print(f"Job '{args.job_name}' is scaffolded; connect provider adapters before production use.")
        return 0

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
