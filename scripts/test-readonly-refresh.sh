#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
PIDS=""
cleanup() {
  for pid in $PIDS; do kill "$pid" 2>/dev/null || true; done
  rm -rf "$WORK"
}
trap cleanup EXIT

snapshot() { find "$1" -type f -print0 | sort -z | xargs -0 shasum; }
free_port() { python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()"; }

check_provider() {
  local key="$1" home="$2" port before after pid
  port="$(free_port)"
  before="$(snapshot "$home")"
  case "$key" in
    codex)
      env CODEX_HOME="$home" PORT="$port" SESSION_MANAGER_EMBEDDED=1 python3 "$ROOT/apps/codex/server.py" >"$WORK/$key.log" 2>&1 &
      ;;
    claude-code)
      env CLAUDE_CONFIG_DIR="$home" CLAUDE_DESKTOP_SESSIONS_DIR="$WORK/desktop-none" PORT="$port" SESSION_MANAGER_EMBEDDED=1 python3 "$ROOT/apps/claude-code/server.py" >"$WORK/$key.log" 2>&1 &
      ;;
    grok)
      env GROK_HOME="$home" PORT="$port" SESSION_MANAGER_EMBEDDED=1 python3 "$ROOT/apps/grok/server.py" >"$WORK/$key.log" 2>&1 &
      ;;
  esac
  pid=$!
  PIDS="$PIDS $pid"
  for _ in $(seq 1 80); do
    if curl -fsS "http://127.0.0.1:$port/api/sessions" >"$WORK/$key.json" 2>/dev/null; then break; fi
    sleep 0.05
  done
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["ok"] and len(d["sessions"]) == 1; s=d["sessions"][0]; key=sys.argv[2]; assert key != "codex" or (s["title"] == "Fixture Codex session" and s["preview"] == "Test the Codex fixture safely." and s["user_turns"] == 1)' "$WORK/$key.json" "$key"
  after="$(snapshot "$home")"
  [[ "$before" == "$after" ]] || { echo "$key refresh modified fixture data" >&2; exit 1; }
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}

cp -R "$ROOT/Tests/Fixtures/codex" "$WORK/codex"
cp -R "$ROOT/Tests/Fixtures/claude" "$WORK/claude"
cp -R "$ROOT/Tests/Fixtures/grok" "$WORK/grok"
check_provider codex "$WORK/codex"
check_provider claude-code "$WORK/claude"
check_provider grok "$WORK/grok"

echo "Read-only refresh tests passed for Codex, Claude Code, and Grok."
