#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
local_env="${HERMES_LOCAL_ENV:-$repo_root/.env.local}"
runpodctl_bin="${RUNPODCTL_BIN:-/Users/boram/bin/runpodctl}"

if [ -z "${RUNPOD_API_KEY:-}" ]; then
  read -r -s -p "Runpod API key: " RUNPOD_API_KEY
  echo
fi

if [ -z "${RUNPOD_API_KEY:-}" ]; then
  echo "RUNPOD_API_KEY is empty." >&2
  exit 1
fi

touch "$local_env"
chmod 600 "$local_env"

LOCAL_ENV="$local_env" RUNPOD_API_KEY="$RUNPOD_API_KEY" python3 - <<'PY'
from __future__ import annotations

import os
import shlex
from pathlib import Path

path = Path(os.environ["LOCAL_ENV"])
api_key = os.environ["RUNPOD_API_KEY"]
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
replacement = f"RUNPOD_API_KEY={shlex.quote(api_key)}"
for index, line in enumerate(lines):
    if line.startswith("RUNPOD_API_KEY="):
        lines[index] = replacement
        break
else:
    lines.append(replacement)
path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
PY

"$runpodctl_bin" config --apiKey "$RUNPOD_API_KEY" >/dev/null
chmod 600 "$HOME/.runpod/config.toml"

echo "Saved Runpod API key to $local_env and runpodctl config."
