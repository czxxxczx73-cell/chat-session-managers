#!/usr/bin/env python3
"""Grok 对话管理器 — 本地网页版后端。

读取 ~/.grok/sessions/<url-encoded-cwd>/<session-id>/ 下的本地会话，
提供列表 / 搜索 / 按工程筛选，以及归档、取消归档、删除操作。

会话是一个个目录（含 summary.json / chat_history.jsonl 等）。本工具直接对文件系统操作：

  · 归档   = 把会话目录移到 ~/.grok/sessions_archived/（镜像原目录结构）
             —— 移出 sessions/ 后 `grok --resume` 就看不到它了，等于归档，
                想恢复随时移回。
  · 取消归档 = 从 sessions_archived/ 移回 sessions/。
  · 删除   = 先备份到 ~/.grok/deleted_sessions/，再删除原目录（可手动找回）。

零第三方依赖，仅用 Python 标准库。运行：python3 server.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8766"))

# Grok 支持用 GROK_HOME 覆盖 ~/.grok
GROK_HOME = Path(os.environ.get("GROK_HOME", Path.home() / ".grok"))
SESSIONS_DIR = GROK_HOME / "sessions"
ARCHIVED_DIR = GROK_HOME / "sessions_archived"   # 本工具自建的归档区
DELETED_DIR = GROK_HOME / "deleted_sessions"     # 本工具自建的删除备份区
ACTIVE_FILE = GROK_HOME / "active_sessions.json"

HERE = Path(__file__).resolve().parent
INDEX_HTML = HERE / "index.html"

# Grok 默认用 UUIDv7；也允许客户端自定义 UUID
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def decode_cwd_dir(name):
    """把 sessions/ 下的分组目录名还原成 cwd。

    正常情况是 URL 编码（如 %2FUsers%2Falice → /Users/alice）。
    超长路径时 Grok 会用 slug+hash，并在目录内写 .cwd 文件。
    """
    try:
        return unquote(name)
    except Exception:
        return name


def load_group_cwd(group_dir):
    """读取工程分组的真实 cwd。优先 .cwd，其次目录名解码。"""
    cwd_file = group_dir / ".cwd"
    if cwd_file.is_file():
        try:
            text = cwd_file.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                return text
        except OSError:
            pass
    return decode_cwd_dir(group_dir.name)


def extract_text(content):
    """从 message content 里抽取纯文本。"""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text" and "text" in item:
            parts.append(str(item["text"]))
        elif isinstance(item, str):
            parts.append(item)
    return "\n".join(parts)


def is_real_user_text(text):
    """判断是否是「真实用户输入」，过滤 system-reminder / user_info 等。"""
    if not text:
        return False
    t = text.strip()
    if not t:
        return False
    # 抽取 <user_query>…</user_query>
    m = re.search(r"<user_query>\s*([\s\S]*?)\s*</user_query>", t)
    if m:
        return bool(m.group(1).strip())
    if t.startswith("<"):
        return False
    if t.startswith("You are Grok"):
        return False
    return True


def first_user_preview(chat_path, max_chars=240):
    """从 chat_history.jsonl 取第一条真实用户问题作预览。"""
    if not chat_path.is_file():
        return ""
    try:
        with chat_path.open(encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 400:  # 安全上限：别把超大历史全扫一遍
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("type") != "user":
                    continue
                text = extract_text(o.get("content"))
                m = re.search(r"<user_query>\s*([\s\S]*?)\s*</user_query>", text)
                if m:
                    return m.group(1).strip()[:max_chars]
                if is_real_user_text(text):
                    return text.strip()[:max_chars]
    except OSError:
        pass
    return ""


def dir_size(path):
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


# 解析结果缓存：{会话目录: (mtime_ns, size_hint, 解析结果)}
_PARSE_CACHE = {}


def parse_session(session_dir, project_name, group_cwd):
    """解析一个会话目录，返回汇总字典（带缓存）。"""
    summary_path = session_dir / "summary.json"
    try:
        st = summary_path.stat() if summary_path.is_file() else session_dir.stat()
        cache_key = str(session_dir)
        # 用目录 mtime + summary size 粗判变更
        dir_st = session_dir.stat()
        hint = (dir_st.st_mtime_ns, st.st_size if summary_path.is_file() else 0)
        cached = _PARSE_CACHE.get(cache_key)
        if cached and cached[0] == hint[0] and cached[1] == hint[1]:
            return dict(cached[2])
    except OSError:
        st = None
        cache_key = None
        hint = (0, 0)

    sid = session_dir.name
    summary = {}
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary = {}

    info = summary.get("info") if isinstance(summary.get("info"), dict) else {}
    cwd = info.get("cwd") or group_cwd or ""
    title = (
        summary.get("generated_title")
        or summary.get("session_summary")
        or ""
    )
    created_at = summary.get("created_at") or ""
    updated_at = summary.get("updated_at") or summary.get("last_active_at") or ""
    model = summary.get("current_model_id") or ""
    agent = summary.get("agent_name") or ""
    num_messages = int(summary.get("num_messages") or 0)
    num_chat = int(summary.get("num_chat_messages") or 0)

    signals = {}
    signals_path = session_dir / "signals.json"
    if signals_path.is_file():
        try:
            signals = json.loads(signals_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            signals = {}

    user_turns = int(signals.get("userMessageCount") or signals.get("turnCount") or 0)
    assistant_turns = int(signals.get("assistantMessageCount") or 0)
    if not model:
        model = signals.get("primaryModelId") or ""

    preview = first_user_preview(session_dir / "chat_history.jsonl")
    if not title:
        title = (preview[:40] if preview else "(未命名会话)")

    # 空会话：几乎没有任何对话内容
    empty = (
        user_turns == 0
        and assistant_turns == 0
        and num_chat == 0
        and not preview
        and title == "(未命名会话)"
    )

    size = dir_size(session_dir)
    mtime = 0.0
    try:
        mtime = session_dir.stat().st_mtime
    except OSError:
        pass

    result = {
        "id": sid,
        "title": title,
        "custom_title": "",
        "ai_title": summary.get("generated_title") or summary.get("session_summary") or "",
        "updated_at": updated_at,
        "created_at": created_at,
        "mtime": mtime,
        "cwd": cwd,
        "git_branch": "",
        "version": "",
        "entrypoint": agent or "grok",
        "preview": preview[:240],
        "user_turns": user_turns,
        "assistant_turns": assistant_turns,
        "num_messages": num_messages,
        "model": model,
        "agent_name": agent,
        "empty": empty,
        "size": size,
        "file": str(session_dir),
        "project": project_name,
    }
    if cache_key:
        _PARSE_CACHE[cache_key] = (hint[0], hint[1], dict(result))
    return result


def load_active_sessions():
    """读取 ~/.grok/active_sessions.json → {session_id: info}。"""
    index = {}
    if not ACTIVE_FILE.is_file():
        return index
    try:
        data = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return index
    if not isinstance(data, list):
        return index
    for item in data:
        if not isinstance(item, dict):
            continue
        sid = item.get("session_id")
        if isinstance(sid, str) and sid:
            index[sid] = {
                "pid": item.get("pid"),
                "cwd": item.get("cwd") or "",
                "opened_at": item.get("opened_at") or "",
            }
    return index


def collect(active=None):
    """汇总本地 + 归档会话，按更新时间倒序。

    source 字段：
      · active —— 出现在 active_sessions.json（当前可能正被 Grok 打开）
      · local  —— 磁盘上有会话目录，当前不在活跃列表
    """
    if active is None:
        active = load_active_sessions()
    sessions = []
    seen = set()

    def walk(base, archived):
        if not base.exists():
            return
        try:
            groups = sorted(base.iterdir())
        except OSError:
            return
        for group in groups:
            if not group.is_dir():
                continue
            # 跳过索引文件旁的特殊项
            if group.name.startswith(".") or group.name.endswith(".sqlite"):
                continue
            group_cwd = load_group_cwd(group)
            try:
                children = sorted(group.iterdir())
            except OSError:
                continue
            for child in children:
                if not child.is_dir():
                    continue
                sid = child.name
                if not UUID_RE.match(sid):
                    continue
                if sid in seen:
                    continue
                seen.add(sid)
                info = parse_session(child, group.name, group_cwd)
                if info["empty"]:
                    continue
                info["archived"] = archived
                info["source"] = "active" if (sid in active and not archived) else "local"
                if sid in active and not info["cwd"]:
                    info["cwd"] = active[sid].get("cwd") or info["cwd"]
                sessions.append(info)

    walk(ARCHIVED_DIR, True)
    walk(SESSIONS_DIR, False)

    sessions.sort(
        key=lambda s: (s.get("updated_at") or "", s.get("mtime") or 0), reverse=True
    )
    return sessions


_RUNNING_CACHE = [0.0, False]


def grok_running():
    """检测 Grok Build 是否在运行（active_sessions 或 grok 进程）。"""
    now = time.monotonic()
    if now - _RUNNING_CACHE[0] < 5.0:
        return _RUNNING_CACHE[1]
    result = False
    try:
        if load_active_sessions():
            result = True
        else:
            proc = subprocess.run(
                ["pgrep", "-f", r"\.grok/bin/grok"],
                capture_output=True, text=True, timeout=5,
            )
            result = proc.returncode == 0 and bool(proc.stdout.strip())
    except Exception:  # noqa: BLE001
        pass
    _RUNNING_CACHE[0], _RUNNING_CACHE[1] = now, result
    return result


def find_session(sid):
    """返回 (path, archived, project)，找不到返回 (None, None, None)。"""
    for base, archived in ((SESSIONS_DIR, False), (ARCHIVED_DIR, True)):
        if not base.exists():
            continue
        try:
            groups = base.iterdir()
        except OSError:
            continue
        for group in groups:
            if not group.is_dir():
                continue
            cand = group / sid
            if cand.is_dir():
                return cand, archived, group.name
    return None, None, None


def rmdir_if_empty(d):
    try:
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    except OSError:
        pass


def perform_action(action, sid):
    src, archived, project = find_session(sid)
    if not src:
        return {"ok": False, "action": action, "id": sid, "error": "找不到该会话目录"}

    try:
        if action == "delete":
            DELETED_DIR.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc)
            ts = now.strftime("%Y-%m-%dT%H-%M-%S-") + f"{now.microsecond // 1000:03d}Z"
            backup = DELETED_DIR / f"{ts}-{sid}"
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            shutil.copytree(src, backup)
            shutil.rmtree(src)
            _PARSE_CACHE.pop(str(src), None)
            rmdir_if_empty(src.parent)
            return {"ok": True, "action": action, "id": sid, "backup": str(backup)}

        if action == "archive":
            if archived:
                return {"ok": True, "action": action, "id": sid, "noop": True}
            dst_dir = ARCHIVED_DIR / project
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / sid
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            shutil.move(str(src), str(dst))
            _PARSE_CACHE.pop(str(src), None)
            rmdir_if_empty(src.parent)
            return {"ok": True, "action": action, "id": sid}

        if action == "unarchive":
            if not archived:
                return {"ok": True, "action": action, "id": sid, "noop": True}
            dst_dir = SESSIONS_DIR / project
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / sid
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            shutil.move(str(src), str(dst))
            _PARSE_CACHE.pop(str(src), None)
            rmdir_if_empty(src.parent)
            return {"ok": True, "action": action, "id": sid}

        return {"ok": False, "action": action, "id": sid, "error": "未知操作"}
    except OSError as e:
        return {"ok": False, "action": action, "id": sid, "error": str(e)}


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
                active = load_active_sessions()
                self._json(
                    200,
                    {
                        "ok": True,
                        "grok_home": str(GROK_HOME),
                        "claude_home": str(GROK_HOME),  # 兼容前端字段名
                        "grok_running": grok_running(),
                        "claude_running": grok_running(),  # 兼容前端字段名
                        "sync": {"deleted": 0, "backed_up": 0},
                        "sessions": collect(active),
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
            self._json(400, {"ok": False, "error": "请求体解析失败"})
            return

        action = body.get("action")
        if action not in ("archive", "unarchive", "delete"):
            self._json(400, {"ok": False, "error": "未知操作"})
            return

        ids = body.get("ids")
        if not isinstance(ids, list):
            ids = [body.get("id", "") or ""]
        valid = [i for i in ids if isinstance(i, str) and UUID_RE.match(i)]
        if not valid:
            self._json(400, {"ok": False, "error": "没有合法的会话 id"})
            return

        try:
            results = [perform_action(action, sid) for sid in valid]
            ok_n = sum(1 for r in results if r.get("ok"))
            fail_n = len(results) - ok_n

            if len(valid) == 1:
                self._json(200 if results[0].get("ok") else 500, results[0])
            else:
                self._json(
                    200 if fail_n == 0 else 207,
                    {
                        "ok": fail_n == 0,
                        "action": action,
                        "succeeded": ok_n,
                        "failed": fail_n,
                        "results": results,
                    },
                )
        except Exception as e:  # noqa: BLE001
            self._json(500, {"ok": False, "error": str(e)})

    def log_message(self, *args):
        pass


def create_server(port):
    return ThreadingHTTPServer((HOST, port), Handler)


def main():
    if not INDEX_HTML.exists():
        print("警告：缺少 index.html，页面无法显示。", file=sys.stderr)
    if not SESSIONS_DIR.exists():
        print(f"警告：未找到会话目录：{SESSIONS_DIR}", file=sys.stderr)
    server = create_server(PORT)
    url = f"http://{HOST}:{PORT}/"
    print("=" * 48)
    print(" Grok 对话管理器 已启动")
    print(f"   地址      : {url}")
    print(f"   GROK_HOME : {GROK_HOME}")
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
