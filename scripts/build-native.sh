#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/.build/native"
DIST="$ROOT/dist/native"
SDK="$(xcrun --sdk macosx --show-sdk-path)"
MIN_MACOS="${MACOSX_DEPLOYMENT_TARGET:-13.0}"

name_for() {
  case "$1" in
    codex) echo "Codex Session Manager" ;;
    claude-code) echo "Claude Code Session Manager" ;;
    grok) echo "Grok Session Manager" ;;
  esac
}

bundle_for() {
  case "$1" in
    codex) echo "io.github.czxxxczx73cell.CodexSessionManager" ;;
    claude-code) echo "io.github.czxxxczx73cell.ClaudeCodeSessionManager" ;;
    grok) echo "io.github.czxxxczx73cell.GrokSessionManager" ;;
  esac
}

rm -rf "$BUILD" "$DIST"
mkdir -p "$BUILD" "$DIST"

for arch in arm64 x86_64; do
  xcrun --sdk macosx swiftc -swift-version 5 -O -whole-module-optimization \
    -target "$arch-apple-macosx$MIN_MACOS" -sdk "$SDK" \
    -framework AppKit -framework WebKit \
    "$ROOT/NativeHost/main.swift" -o "$BUILD/SessionManagerHost-$arch"
done
xcrun lipo -create "$BUILD/SessionManagerHost-arm64" "$BUILD/SessionManagerHost-x86_64" \
  -output "$BUILD/SessionManagerHost"

for key in codex claude-code grok; do
  name="$(name_for "$key")"
  app="$DIST/$name.app"
  mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
  cp "$BUILD/SessionManagerHost" "$app/Contents/MacOS/SessionManagerHost"
  cp "$ROOT/apps/$key/Info.plist" "$app/Contents/Info.plist"
  cp "$ROOT/apps/$key/server.py" "$ROOT/apps/$key/index.html" "$ROOT/apps/$key/icon.icns" "$app/Contents/Resources/"
  cp -R "$ROOT/apps/$key/en.lproj" "$ROOT/apps/$key/zh-Hans.lproj" "$app/Contents/Resources/"

  /usr/libexec/PlistBuddy -c "Set :CFBundleExecutable SessionManagerHost" "$app/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $(bundle_for "$key")" "$app/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $name" "$app/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Set :CFBundleName $name" "$app/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 2.0.0" "$app/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion 2" "$app/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion 13.0" "$app/Contents/Info.plist"
  codesign --force --deep --sign - --timestamp=none "$app"
  codesign --verify --deep --strict "$app"
  echo "Built native host with unchanged web UI: $app"
done

echo "Architectures: $(xcrun lipo -archs "$BUILD/SessionManagerHost")"
