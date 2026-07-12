#!/usr/bin/env python3
"""Codex 对话管理器 — 本地网页版后端。

读取 ~/.codex 下的本地会话（sessions/）与归档会话（archived_sessions/），
提供列表 / 搜索 / 筛选，以及归档、取消归档、删除操作。

写操作一律调用官方命令 `codex archive|unarchive|delete <id>`，
以保证 session_index.jsonl、state_5.sqlite 等内部状态保持一致，
避免手动搬文件导致索引错乱。

零第三方依赖，仅用 Python 标准库。运行：python3 server.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8765"))

CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
SESSIONS_DIR = CODEX_HOME / "sessions"
ARCHIVED_DIR = CODEX_HOME / "archived_sessions"
DELETED_DIR = CODEX_HOME / "deleted_sessions"
INDEX_FILE = CODEX_HOME / "session_index.jsonl"

HERE = Path(__file__).resolve().parent
INDEX_HTML = HERE / "index.html"

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
UUID_SEARCH = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def find_codex_bin():
    p = shutil.which("codex")
    if p:
        return p
    for cand in (
        Path.home() / ".local/bin/codex",
        Path("/opt/homebrew/bin/codex"),
        Path("/usr/local/bin/codex"),
    ):
        if cand.exists():
            return str(cand)
    return None


CODEX_BIN = find_codex_bin()


def load_index():
    """返回 id -> {thread_name, updated_at} 映射。"""
    idx = {}
    if not INDEX_FILE.exists():
        return idx
    with INDEX_FILE.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = o.get("id")
            if sid:
                idx[sid] = o
    return idx


def extract_text(content):
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, dict) and "text" in item:
            parts.append(str(item["text"]))
    return "\n".join(parts)


def parse_rollout(path):
    """读取一个 rollout 文件，返回 (meta, preview, user_turns, assistant_turns)。

    preview 取第一条「真实」用户消息（跳过 <environment_context> /
    <permissions instructions> 等以 '<' 开头的系统注入消息）。
    """
    meta = {}
    preview = ""
    user_turns = 0
    assistant_turns = 0
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                typ = o.get("type")
                payload = o.get("payload") or {}
                if typ == "session_meta" and not meta:
                    meta = payload
                elif typ == "response_item" and payload.get("type") == "message":
                    role = payload.get("role")
                    text = extract_text(payload.get("content"))
                    if role == "user":
                        if text and not text.lstrip().startswith("<"):
                            user_turns += 1
                            if not preview:
                                preview = text.strip()
                    elif role == "assistant":
                        assistant_turns += 1
    except OSError:
        pass
    return meta, preview, user_turns, assistant_turns


def id_from_name(name):
    m = UUID_SEARCH.search(name)
    return m.group(0) if m else None


def collect():
    """汇总本地 + 归档会话，按更新时间倒序。"""
    idx = load_index()
    sessions = []
    seen = set()

    def handle(path, archived):
        meta, preview, ut, at = parse_rollout(path)
        sid = meta.get("id") or id_from_name(path.name)
        if not sid or sid in seen:
            return
        seen.add(sid)
        info = idx.get(sid, {})
        try:
            st = path.stat()
            mtime, size = st.st_mtime, st.st_size
        except OSError:
            mtime, size = 0, 0
        sessions.append(
            {
                "id": sid,
                "title": info.get("thread_name")
                or (preview[:40] if preview else "(未命名会话)"),
                "updated_at": info.get("updated_at") or meta.get("timestamp") or "",
                "created_at": meta.get("timestamp") or "",
                "mtime": mtime,
                "cwd": meta.get("cwd", ""),
                "source": meta.get("source") or meta.get("originator") or "",
                "originator": meta.get("originator", ""),
                "archived": archived,
                "preview": preview[:240],
                "user_turns": ut,
                "assistant_turns": at,
                "file": str(path),
                "size": size,
            }
        )

    if ARCHIVED_DIR.exists():
        for p in sorted(ARCHIVED_DIR.glob("rollout-*.jsonl")):
            handle(p, True)
    if SESSIONS_DIR.exists():
        for p in sorted(SESSIONS_DIR.rglob("rollout-*.jsonl")):
            handle(p, False)

    sessions.sort(
        key=lambda s: (s.get("updated_at") or "", s.get("mtime") or 0), reverse=True
    )
    return sessions


def desktop_running():
    """检测 Codex Desktop / app-server 是否在运行。

    它在运行时会从云端实时回灌会话，导致本地删除/归档被「还原」，
    前端据此提示用户先退出 Desktop。
    """
    for pat in ("codex app-server", "Codex.app/Contents/MacOS"):
        try:
            proc = subprocess.run(
                ["pgrep", "-f", pat], capture_output=True, text=True, timeout=5
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def run_codex(action, sid):
    cmd = [CODEX_BIN, action]
    # `codex delete` 在非交互终端下会拒绝，需 --force 跳过 TTY 确认。
    if action == "delete":
        cmd.append("--force")
    cmd.append(sid)
    return subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )


def find_rollout(sid):
    """返回该会话 rollout 文件的路径，找不到返回 None。"""
    for base in (SESSIONS_DIR, ARCHIVED_DIR):
        if base.exists():
            for p in base.rglob(f"rollout-*{sid}*.jsonl"):
                return p
    return None


def location_of(sid):
    """会话当前位置：'local' / 'archived' / None。"""
    if SESSIONS_DIR.exists():
        for _ in SESSIONS_DIR.rglob(f"rollout-*{sid}*.jsonl"):
            return "local"
    if ARCHIVED_DIR.exists():
        for _ in ARCHIVED_DIR.rglob(f"rollout-*{sid}*.jsonl"):
            return "archived"
    return None


def backup_before_delete(sid):
    """删除前把文件复制到 deleted_sessions/，模仿 Desktop 的命名，保证可找回。"""
    src = find_rollout(sid)
    if not src or not src.exists():
        return None
    try:
        DELETED_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y-%m-%dT%H-%M-%S-") + f"{now.microsecond // 1000:03d}Z"
        dst = DELETED_DIR / f"{ts}-{src.name}"
        shutil.copy2(src, dst)
        return dst
    except OSError:
        return None


def perform_action(action, sid):
    """执行操作并按「操作后真实文件位置」判定成败。

    codex 在 Desktop app-server 运行时退出码不可信（删除可能 rc=1 却已删成功），
    因此一律以文件系统最终状态为准。删除前自动备份到 deleted_sessions/。
    """
    backup = backup_before_delete(sid) if action == "delete" else None
    proc = run_codex(action, sid)
    loc = location_of(sid)

    if action == "delete":
        ok = loc is None
        if not ok and backup and backup.exists():
            backup.unlink(missing_ok=True)  # 实际没删成，清理多余备份
    elif action == "archive":
        ok = loc == "archived"
    else:  # unarchive
        ok = loc == "local"

    return {
        "ok": ok,
        "action": action,
        "id": sid,
        "verified_location": loc,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-2000:],
        "stderr": (proc.stderr or "")[-2000:],
        "backup": str(backup) if (action == "delete" and ok and backup) else None,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                self._send(200, INDEX_HTML.read_text(encoding="utf-8"), "text/html")
            except OSError:
                self._send(500, "index.html 缺失", "text/plain")
        elif path == "/api/sessions":
            try:
                self._json(
                    200,
                    {
                        "ok": True,
                        "codex_home": str(CODEX_HOME),
                        "codex_bin": CODEX_BIN,
                        "desktop_running": desktop_running(),
                        "sessions": collect(),
                    },
                )
            except Exception as e:  # noqa: BLE001
                self._json(500, {"ok": False, "error": str(e)})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/action":
            self._json(404, {"ok": False, "error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json(400, {"ok": False, "error": "请求体解析失败", "error_code": "bad_request"})
            return

        action = body.get("action")
        sid = body.get("id", "") or ""
        if action not in ("archive", "unarchive", "delete"):
            self._json(400, {"ok": False, "error": "未知操作", "error_code": "unknown_action"})
            return
        if not UUID_RE.match(sid):
            self._json(400, {"ok": False, "error": "非法会话 id", "error_code": "invalid_id"})
            return
        if not CODEX_BIN:
            self._json(500, {"ok": False, "error": "找不到 codex 命令", "error_code": "codex_bin_missing"})
            return
        try:
            result = perform_action(action, sid)
            if not result["ok"] and not result.get("error"):
                result["error"] = (result.get("stderr") or "").strip() or "操作未生效"
                if not (result.get("stderr") or "").strip():
                    result["error_code"] = "action_no_effect"
            self._json(200 if result["ok"] else 500, result)
        except subprocess.TimeoutExpired:
            self._json(500, {"ok": False, "error": "命令执行超时", "error_code": "timeout"})
        except Exception as e:  # noqa: BLE001
            self._json(500, {"ok": False, "error": str(e)})

    def log_message(self, *args):
        pass  # 静音访问日志


def create_server(port):
    """构建一个监听指定端口的服务实例（供原生 app 入口复用）。"""
    return ThreadingHTTPServer((HOST, port), Handler)


def main():
    if not INDEX_HTML.exists():
        print("警告：缺少 index.html，页面无法显示。", file=sys.stderr)
    if not CODEX_HOME.exists():
        print(f"警告：未找到 CODEX_HOME 目录：{CODEX_HOME}", file=sys.stderr)
    server = create_server(PORT)
    url = f"http://{HOST}:{PORT}/"
    print("=" * 48)
    print(" Codex 对话管理器 已启动")
    print(f"   地址      : {url}")
    print(f"   CODEX_HOME: {CODEX_HOME}")
    print(f"   codex 命令: {CODEX_BIN or '未找到（归档/删除将不可用）'}")
    print("   按 Ctrl+C 退出")
    print("=" * 48)
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
        server.shutdown()


if __name__ == "__main__":
    main()
