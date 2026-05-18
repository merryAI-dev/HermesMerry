#!/usr/bin/env bash
set -euo pipefail

: "${GHCR_OWNER:?Set GHCR_OWNER to the GitHub user or org that owns the package.}"

IMAGE_TAG="${IMAGE_TAG:-staging}"
GHCR_OWNER_NORMALIZED="$(printf '%s' "$GHCR_OWNER" | tr '[:upper:]' '[:lower:]')"
IMAGE_URI="ghcr.io/${GHCR_OWNER_NORMALIZED}/hermes-merry:${IMAGE_TAG}"

docker buildx inspect >/dev/null

if [ "${PUSH_IMAGE:-0}" = "1" ]; then
  docker buildx build --platform linux/amd64 -t "$IMAGE_URI" --push .
else
  docker buildx build --platform linux/amd64 -t "$IMAGE_URI" --load .
fi

printf '%s\n' "$IMAGE_URI"
