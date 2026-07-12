#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${VERSION:-2.0.1}"
DIST="$ROOT/dist"
STAGE="$ROOT/.release-stage/Chat Session Managers"
ARCHIVE="$DIST/Chat-Session-Managers-Local-Installer-v$VERSION.zip"

"$ROOT/scripts/audit-release.sh"
rm -rf "$ROOT/.release-stage" "$ARCHIVE"
mkdir -p "$STAGE" "$DIST"

cp "$ROOT/Build Apps.command" "$ROOT/build.sh" "$ROOT/LICENSE" "$ROOT/README.md" "$ROOT/README.zh-CN.md" "$STAGE/"
cp -R "$ROOT/apps" "$ROOT/common" "$STAGE/"
chmod +x "$STAGE/Build Apps.command" "$STAGE/build.sh"

ditto -c -k --norsrc --keepParent "$STAGE" "$ARCHIVE"
rm -rf "$ROOT/.release-stage"

echo "Packaged local installer: $ARCHIVE"
du -h "$ARCHIVE"
