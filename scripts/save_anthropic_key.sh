#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
local_env="${HERMES_LOCAL_ENV:-$repo_root/.env.local}"

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  read -r -s -p "Anthropic API key: " ANTHROPIC_API_KEY
  echo
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ANTHROPIC_API_KEY is empty." >&2
  exit 1
fi

touch "$local_env"
chmod 600 "$local_env"

LOCAL_ENV="$local_env" ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" python3 - <<'PY'
from __future__ import annotations

import os
import shlex
from pathlib import Path

path = Path(os.environ["LOCAL_ENV"])
api_key = os.environ["ANTHROPIC_API_KEY"]
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
updates = {
    "ANTHROPIC_API_KEY": api_key,
    "HERMES_LLM_MODEL": "claude-sonnet-4-6",
    "HERMES_LLM_TIMEOUT_SECONDS": "30",
}
existing = {line.split("=", 1)[0]: index for index, line in enumerate(lines) if "=" in line}
for key, value in updates.items():
    replacement = f"{key}={shlex.quote(value)}"
    if key in existing:
        lines[existing[key]] = replacement
    else:
        lines.append(replacement)
path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
PY

echo "Saved Anthropic API key to $local_env."
