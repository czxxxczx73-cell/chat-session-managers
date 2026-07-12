#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED="$ROOT/scripts/app-format.sha1"
ACTUAL="$(mktemp)"
trap 'rm -f "$ACTUAL"' EXIT

cd "$ROOT"
for file in apps/*/index.html; do
  shasum "$file"
done | sort > "$ACTUAL"

if ! diff -u "$EXPECTED" "$ACTUAL"; then
  echo "An App UI file changed. The existing card layout and visual design must remain untouched." >&2
  exit 1
fi
echo "App UI check passed: all three index.html files match the Claude-published version byte for byte."
