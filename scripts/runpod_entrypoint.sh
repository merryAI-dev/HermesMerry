#!/usr/bin/env bash
set -euo pipefail

credential_file=""

cleanup() {
  if [ -n "$credential_file" ] && [ -f "$credential_file" ]; then
    rm -f "$credential_file"
  fi
}
trap cleanup EXIT

if [ -n "${GOOGLE_APPLICATION_CREDENTIALS_JSON:-}" ]; then
  credential_file="$(mktemp /tmp/hermes-gcp-XXXXXX.json)"
  chmod 600 "$credential_file"
  printf '%s' "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > "$credential_file"
  export GOOGLE_APPLICATION_CREDENTIALS="$credential_file"
fi

exec "$@"
