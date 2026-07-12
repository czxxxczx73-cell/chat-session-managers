#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT/scripts/verify-app-format.sh"

HOME_PATHS="$(rg -n '(/Users/[^/[:space:]]+|/home/[^/[:space:]]+)' \
  "$ROOT/NativeHost" "$ROOT/apps" \
  | rg -v '/Users/alice|/home/alice' || true)"
if [[ -n "$HOME_PATHS" ]]; then
  echo "$HOME_PATHS" >&2
  echo "Found a hard-coded user home path in the distributable files." >&2
  exit 1
fi

if rg -n '(analytics|telemetry|sentry|segment|mixpanel|google-analytics)' "$ROOT/apps" --glob '*.{py,html}'; then
  echo "Found a possible analytics or telemetry reference." >&2
  exit 1
fi

EXTERNAL_URLS="$(rg -n -o 'https?://[^[:space:]<>]+' "$ROOT/apps" --glob '*.{py,html}' \
  | rg -v '127\.0\.0\.1|localhost|\{HOST\}|www\.w3\.org|schemas\.apple\.com' || true)"
if [[ -n "$EXTERNAL_URLS" ]]; then
  echo "$EXTERNAL_URLS" >&2
  echo "Found an external URL in runtime source." >&2
  exit 1
fi

echo "Release audit passed: no UI drift, user-specific paths, telemetry, or outbound runtime URL."
