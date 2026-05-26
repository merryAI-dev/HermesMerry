#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
local_env="${HERMES_LOCAL_ENV:-$repo_root/.env.local}"

if [ -z "${THEVC_USER_EMAIL:-}" ]; then
  read -r -p "THE VC email: " THEVC_USER_EMAIL
fi

if [ -z "${THEVC_PASSWORD:-}" ]; then
  read -r -s -p "THE VC password: " THEVC_PASSWORD
  echo
fi

if [ -z "${THEVC_USER_EMAIL:-}" ] || [ -z "${THEVC_PASSWORD:-}" ]; then
  echo "THEVC_USER_EMAIL and THEVC_PASSWORD are required." >&2
  exit 1
fi

touch "$local_env"
chmod 600 "$local_env"

LOCAL_ENV="$local_env" THEVC_USER_EMAIL="$THEVC_USER_EMAIL" THEVC_PASSWORD="$THEVC_PASSWORD" python3 - <<'PY'
from __future__ import annotations

import os
import shlex
from pathlib import Path

path = Path(os.environ["LOCAL_ENV"])
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
updates = {
    "THEVC_USER_EMAIL": os.environ["THEVC_USER_EMAIL"],
    "THEVC_PASSWORD": os.environ["THEVC_PASSWORD"],
    "THEVC_BROWSER_STATE_PATH": "/tmp/hermes-merry-local/thevc-state.json",
    "THEVC_BROWSER_HEADLESS": "0",
    "THEVC_BROWSER_CHANNEL": "chrome",
    "THEVC_TIMEOUT_SECONDS": "30",
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

echo "Saved THE VC credentials to $local_env."
