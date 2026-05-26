#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
local_env="${HERMES_LOCAL_ENV:-$repo_root/.env.local}"
runpodctl_bin="${RUNPODCTL_BIN:-/Users/boram/bin/runpodctl}"
days="${RUNPOD_AUDIT_DAYS:-3}"

usage() {
  cat <<'EOF'
Usage: scripts/runpod_cost_audit.sh [--days N]

Print a read-only Runpod cost snapshot:
  - account balance
  - running/stopped Pods
  - Serverless endpoints and workers
  - network volumes
  - daily Pod, Serverless, and network-volume billing buckets

The script loads .env.local when present, so RUNPOD_API_KEY can stay out of the shell history.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --days)
      days="${2:?--days requires a number}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -f "$local_env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$local_env"
  set +a
fi

if ! command -v "$runpodctl_bin" >/dev/null 2>&1; then
  echo "runpodctl not found at $runpodctl_bin. Set RUNPODCTL_BIN to override." >&2
  exit 2
fi

if ! [[ "$days" =~ ^[0-9]+$ ]] || [ "$days" -lt 1 ]; then
  echo "--days must be a positive integer." >&2
  exit 2
fi

read -r start_time end_time < <(
  AUDIT_DAYS="$days" python3 - <<'PY'
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

days = int(os.environ["AUDIT_DAYS"])
end = datetime.now(UTC).replace(microsecond=0)
start = end - timedelta(days=days)
print(start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z"))
PY
)

run_section() {
  title="$1"
  shift
  printf '\n## %s\n' "$title"
  if ! "$@"; then
    echo "(failed: $*)" >&2
    return 1
  fi
}

echo "# Runpod Cost Audit"
echo "Window: $start_time to $end_time UTC"
echo "Local env: $local_env"

failures=0

run_section "Account" "$runpodctl_bin" user || failures=$((failures + 1))
run_section "Pods" "$runpodctl_bin" pod list --all || failures=$((failures + 1))
run_section "Serverless endpoints" "$runpodctl_bin" serverless list --include-workers --include-template || failures=$((failures + 1))
run_section "Network volumes" "$runpodctl_bin" network-volume list || failures=$((failures + 1))
run_section "Pod billing by day/pod" \
  "$runpodctl_bin" billing pods --bucket-size day --grouping podId --start-time "$start_time" --end-time "$end_time" || failures=$((failures + 1))
run_section "Serverless billing by day/endpoint" \
  "$runpodctl_bin" billing serverless --bucket-size day --grouping endpointId --start-time "$start_time" --end-time "$end_time" || failures=$((failures + 1))
run_section "Network-volume billing by day" \
  "$runpodctl_bin" billing network-volume --bucket-size day --start-time "$start_time" --end-time "$end_time" || failures=$((failures + 1))

cat <<'EOF'

## Cost leak checklist
- Serverless endpoints with min/active workers above zero keep billing even without traffic.
- RUNNING Pods accrue compute charges until stopped or deleted.
- Stopped Pods can still accrue volume storage charges.
- One-cycle canary Pods that end with `sleep infinity` must be deleted after evidence capture.
- Hermes control-plane crawl/sheet jobs should run on CPU or finite batch Pods; Gemma/Qwen serving should be a separate scale-to-zero endpoint unless low latency requires active workers.
EOF

if [ "$failures" -gt 0 ]; then
  echo
  echo "Audit incomplete: $failures Runpod query section(s) failed." >&2
  exit 1
fi
