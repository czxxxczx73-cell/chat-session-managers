#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${VERSION:-2.0.0}"
"$ROOT/scripts/audit-release.sh"
"$ROOT/scripts/build-native.sh"

STAGE="$ROOT/.release-stage/Chat Session Managers"
ARCHIVE="$ROOT/dist/Chat-Session-Managers-v$VERSION-universal.zip"
rm -rf "$ROOT/.release-stage" "$ARCHIVE"
mkdir -p "$STAGE"
cp -R "$ROOT/dist/native/"*.app "$STAGE/"
cp "$ROOT/README.md" "$ROOT/README.zh-CN.md" "$ROOT/LICENSE" "$STAGE/"
ditto -c -k --norsrc --keepParent "$STAGE" "$ARCHIVE"
rm -rf "$ROOT/.release-stage"
echo "Packaged direct-download release: $ARCHIVE"
du -h "$ARCHIVE"
