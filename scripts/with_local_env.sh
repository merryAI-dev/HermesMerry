#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
local_env="${HERMES_LOCAL_ENV:-$repo_root/.env.local}"

if [ -f "$local_env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$local_env"
  set +a
fi

exec "$@"
