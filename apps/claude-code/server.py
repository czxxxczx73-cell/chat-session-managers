#!/usr/bin/env python3
"""Claude Code 对话管理器 — 本地网页版后端。

读取 ~/.claude/projects/<工程目录>/<session>.jsonl 下的本地会话，
提供列表 / 搜索 / 按工程筛选，以及归档、取消归档、删除操作。

与 Codex 不同，Claude Code 没有 `archive/unarchive/delete` 子命令，
会话就是一个个 .jsonl 文件。因此本工具直接对文件系统操作：

  · 归档   = 把 .jsonl 移到 ~/.claude/projects_archived/（镜像原目录结构）
             —— 移出 projects/ 后 `claude --resume` 就看不到它了，等于归档，
                想恢复随时移回。
  · 取消归档 = 从 projects_archived/ 移回 projects/。
  · 删除   = 先备份到 ~/.claude/deleted_sessions/，再删除原文件（可手动找回）。

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

HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8765"))

# Claude Code 支持用 CLAUDE_CONFIG_DIR 覆盖 ~/.claude
CLAUDE_HOME = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
PROJECTS_DIR = CLAUDE_HOME / "projects"
ARCHIVED_DIR = CLAUDE_HOME / "projects_archived"   # 本工具自建的归档区
DELETED_DIR = CLAUDE_HOME / "deleted_sessions"     # 本工具自建的删除备份区

# Claude 桌面端 App 的会话登记区（macOS）。每个会话一个 local_*.json，
# 其中 cliSessionId 对应 projects/ 下 .jsonl 的文件名（会话 id），
# 据此可判断一条会话是「仅本地 / 仅桌面端 / 都有」。
DESKTOP_SESSIONS_DIR = (
    Path.home() / "Library" / "Application Support" / "Claude" / "claude-code-sessions"
)

HERE = Path(__file__).resolve().parent
INDEX_HTML = HERE / "index.html"

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def decode_project_dir(name):
    """把 projects/ 下的目录名还原成大致的工程路径。

    Claude Code 把 cwd 里的分隔符替换成 '-'（如 /Users/alice → -Users-alice）。
    因为路径里本身可能含 '-'，还原是有损的，仅作兜底；真正的 cwd 以
    transcript 内的 cwd 字段为准。
    """
    if name.startswith("-"):
        return "/" + name[1:].replace("-", "/")
    return name.replace("-", "/")


def extract_text(content):
    """从一条 message 的 content 里抽取纯文本。

    content 可能是字符串，或 [{"type":"text","text":...}, ...] 这样的块数组。
    工具调用 / 工具结果 / 图片块都忽略。
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text" and "text" in item:
            parts.append(str(item["text"]))
    return "\n".join(parts)


def is_real_user_text(text):
    """判断是否是「真实用户输入」，过滤命令注入 / 系统上下文等。"""
    if not text:
        return False
    t = text.lstrip()
    if t.startswith("<"):  # <command-name> / <local-command-*> / <environment_context>...
        return False
    return True


# 解析结果缓存：{文件路径: (mtime_ns, size, 解析结果)}。
# 会话文件只增不改（追加写），(mtime, size) 不变即可复用，刷新时无需重读全部文件。
_PARSE_CACHE = {}


def parse_transcript(path):
    """解析一个 .jsonl 会话文件，返回汇总字典（带 mtime+size 缓存）。"""
    try:
        st = path.stat()
        cache_key = str(path)
        cached = _PARSE_CACHE.get(cache_key)
        if cached and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
            return dict(cached[2])
    except OSError:
        st = None
        cache_key = None

    sid = path.stem
    custom_title = ai_title = ""
    preview = ""
    user_turns = assistant_turns = 0
    cwd = git_branch = version = entrypoint = ""
    first_ts = last_ts = ""

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
                if typ == "custom-title":
                    custom_title = o.get("customTitle") or custom_title
                    continue
                if typ == "ai-title":
                    ai_title = o.get("aiTitle") or ai_title
                    continue

                ts = o.get("timestamp")
                if ts:
                    if not first_ts:
                        first_ts = ts
                    last_ts = ts
                if not cwd and o.get("cwd"):
                    cwd = o["cwd"]
                if not git_branch and o.get("gitBranch"):
                    git_branch = o["gitBranch"]
                if not version and o.get("version"):
                    version = o["version"]
                if not entrypoint and o.get("entrypoint"):
                    entrypoint = o["entrypoint"]  # 如 claude-desktop / cli

                if typ not in ("user", "assistant"):
                    continue
                if o.get("isMeta") or o.get("isSidechain"):
                    continue
                msg = o.get("message") or {}
                role = msg.get("role")
                text = extract_text(msg.get("content"))
                if role == "user":
                    if is_real_user_text(text):
                        user_turns += 1
                        if not preview:
                            preview = text.strip()
                elif role == "assistant":
                    if text.strip():
                        assistant_turns += 1
    except OSError:
        pass

    title = custom_title or ai_title or (preview[:40] if preview else "(未命名会话)")
    mtime, size = (st.st_mtime, st.st_size) if st else (0, 0)

    info = {
        "id": sid,
        "title": title,
        "custom_title": custom_title,
        "ai_title": ai_title,
        "updated_at": last_ts,
        "created_at": first_ts,
        "mtime": mtime,
        "cwd": cwd,
        "git_branch": git_branch,
        "version": version,
        "entrypoint": entrypoint,
        "preview": preview[:240],
        "user_turns": user_turns,
        "assistant_turns": assistant_turns,
        # 空会话：整个文件里没有任何真实对话内容（只有 ai-title / mode /
        # last-prompt 等元数据行）。删除后 Claude Code 进程会立刻重建 stub，
        # 无法真正删掉，因此 collect() 直接不把它们列出来。
        "empty": user_turns == 0 and assistant_turns == 0,
        "size": size,
        "file": str(path),
    }
    if cache_key and st:
        _PARSE_CACHE[cache_key] = (st.st_mtime_ns, st.st_size, dict(info))
    return info


# 自动同步：最近这段时间内写入过的本地会话不参与删除，
# 防止误删「刚创建、桌面端登记尚未落盘」的新会话。
SYNC_ACTIVE_GRACE_SEC = 300


def sync_extras(desktop):
    """让本地 projects/ 与桌面端 App 保持一致：未在桌面端登记的会话自动删除。

    · 有内容的先备份到 ~/.claude/deleted_sessions/ 再删（可手动找回）
    · 空 stub（0 轮对话）直接删，不产生备份垃圾
      —— Claude 进程可能重建 stub，但列表里始终不显示，下次同步再清
    · 最近 SYNC_ACTIVE_GRACE_SEC 秒内写入过的跳过（保护活跃/新建会话）
    · 归档区 projects_archived/ 是用户手动归档的，永不自动删除
    """
    result = {"deleted": 0, "backed_up": 0}
    if not PROJECTS_DIR.exists():
        return result
    now = time.time()
    touched_dirs = []
    for proj in PROJECTS_DIR.iterdir():
        if not proj.is_dir():
            continue
        for p in proj.glob("*.jsonl"):
            sid = p.stem
            if not UUID_RE.match(sid) or sid in desktop:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            if now - st.st_mtime < SYNC_ACTIVE_GRACE_SEC:
                continue
            info = parse_transcript(p)
            try:
                if not info["empty"]:
                    DELETED_DIR.mkdir(parents=True, exist_ok=True)
                    dt = datetime.now(timezone.utc)
                    ts = dt.strftime("%Y-%m-%dT%H-%M-%S-") + f"{dt.microsecond // 1000:03d}Z"
                    shutil.copy2(p, DELETED_DIR / f"{ts}-{p.name}")
                    result["backed_up"] += 1
                p.unlink()
                _PARSE_CACHE.pop(str(p), None)
                result["deleted"] += 1
                touched_dirs.append(proj)
            except OSError:
                pass
    for d in touched_dirs:
        rmdir_if_empty(d)
    return result


def load_desktop_sessions():
    """读取桌面端 App 的会话登记，返回 {cliSessionId: 登记信息}。

    目录结构：claude-code-sessions/<账户>/<工作区>/local_<桌面会话id>.json。
    读不到（目录不存在 / 非 macOS / 文件损坏）就当没有，不影响其余功能。
    """
    index = {}
    if not DESKTOP_SESSIONS_DIR.exists():
        return index
    try:
        entries = sorted(DESKTOP_SESSIONS_DIR.rglob("local_*.json"))
    except OSError:
        return index
    for p in entries:
        try:
            o = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cid = o.get("cliSessionId")
        if not isinstance(cid, str) or not cid:
            continue
        index[cid] = {
            "title": o.get("title") or "",
            "cwd": o.get("cwd") or "",
            "created_ms": o.get("createdAt") or 0,
            "activity_ms": o.get("lastActivityAt") or 0,
            "turns": o.get("completedTurns") or 0,
            "model": o.get("model") or "",
            "desktop_archived": bool(o.get("isArchived")),
            "registry": str(p),
        }
    return index


def _ms_to_iso(ms):
    """毫秒时间戳 → 与 transcript 一致的 ISO-8601 UTC 字符串（可字符串排序）。"""
    if not ms:
        return ""
    try:
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
    except (OverflowError, OSError, ValueError):
        return ""


def collect(desktop=None):
    """汇总本地 + 归档 + 桌面端会话，按更新时间倒序。

    每条会话带 source 字段：
      · both    —— 本地有 .jsonl，桌面端也登记了（桌面端打开过/正在管理）
      · local   —— 只有本地 .jsonl（同步宽限期内的新会话，或归档区的）
      · desktop —— 只在桌面端登记，本地文件已不存在（只读展示，不可操作）
    """
    if desktop is None:
        desktop = load_desktop_sessions()
    sessions = []
    seen = set()

    def handle(path, archived, project):
        if path.stem in seen:
            return
        seen.add(path.stem)
        info = parse_transcript(path)
        if info["empty"]:
            return  # 空会话残留不列出（删了也会被 Claude 进程重建，见 parse_transcript）
        if not info["cwd"]:
            info["cwd"] = decode_project_dir(project)
        info["archived"] = archived
        info["project"] = project
        d = desktop.get(info["id"])
        info["source"] = "both" if d else "local"
        if d and info["title"] == "(未命名会话)" and d["title"]:
            info["title"] = d["title"]  # 本地没标题时借用桌面端标题
        sessions.append(info)

    if ARCHIVED_DIR.exists():
        for proj in sorted(ARCHIVED_DIR.iterdir()):
            if proj.is_dir():
                for p in sorted(proj.glob("*.jsonl")):
                    handle(p, True, proj.name)
    if PROJECTS_DIR.exists():
        for proj in sorted(PROJECTS_DIR.iterdir()):
            if proj.is_dir():
                for p in sorted(proj.glob("*.jsonl")):
                    handle(p, False, proj.name)

    # 桌面端登记了、但本地已无对应文件的会话：只读列出（0 轮的同样视为空，不列）
    for cid, d in desktop.items():
        if cid in seen or not d["turns"]:
            continue
        sessions.append({
            "id": cid,
            "title": d["title"] or "(未命名会话)",
            "custom_title": "",
            "ai_title": d["title"],
            "updated_at": _ms_to_iso(d["activity_ms"]),
            "created_at": _ms_to_iso(d["created_ms"]),
            "mtime": (d["activity_ms"] or 0) / 1000,
            "cwd": d["cwd"],
            "git_branch": "",
            "version": "",
            "entrypoint": "claude-desktop",
            "preview": "",
            "user_turns": d["turns"],
            "assistant_turns": 0,
            "size": 0,
            "file": d["registry"],
            "empty": False,
            "archived": False,
            "project": "",
            "source": "desktop",
        })

    sessions.sort(
        key=lambda s: (s.get("updated_at") or "", s.get("mtime") or 0), reverse=True
    )
    return sessions


_RUNNING_CACHE = [0.0, False]  # [上次检测时间, 结果]


def claude_running():
    """检测 Claude Code 是否在运行——对一个仍活跃的会话动文件可能产生冲突，
    据此在前端给个温和提示。单次 pgrep（ERE 合并三种形态）+ 5 秒缓存。"""
    now = time.monotonic()
    if now - _RUNNING_CACHE[0] < 5.0:
        return _RUNNING_CACHE[1]
    result = False
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "claude --resume|/claude |bin/claude"],
            capture_output=True, text=True, timeout=5,
        )
        result = proc.returncode == 0 and bool(proc.stdout.strip())
    except Exception:  # noqa: BLE001
        pass
    _RUNNING_CACHE[0], _RUNNING_CACHE[1] = now, result
    return result


def find_file(sid):
    """返回 (path, archived, project)，找不到返回 (None, None, None)。"""
    for base, archived in ((PROJECTS_DIR, False), (ARCHIVED_DIR, True)):
        if not base.exists():
            continue
        for proj in base.iterdir():
            if not proj.is_dir():
                continue
            cand = proj / f"{sid}.jsonl"
            if cand.exists():
                return cand, archived, proj.name
    return None, None, None


def rmdir_if_empty(d):
    """归档/取消归档后，若来源工程目录已空则删掉，保持目录整洁。"""
    try:
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    except OSError:
        pass


def perform_action(action, sid):
    src, archived, project = find_file(sid)
    if not src:
        return {"ok": False, "action": action, "id": sid, "error": "找不到该会话文件"}

    try:
        if action == "delete":
            DELETED_DIR.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc)
            ts = now.strftime("%Y-%m-%dT%H-%M-%S-") + f"{now.microsecond // 1000:03d}Z"
            backup = DELETED_DIR / f"{ts}-{src.name}"
            shutil.copy2(src, backup)
            src.unlink()
            return {"ok": True, "action": action, "id": sid, "backup": str(backup)}

        if action == "archive":
            if archived:
                return {"ok": True, "action": action, "id": sid, "noop": True}
            dst_dir = ARCHIVED_DIR / project
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst_dir / src.name))
            rmdir_if_empty(src.parent)
            return {"ok": True, "action": action, "id": sid}

        if action == "unarchive":
            if not archived:
                return {"ok": True, "action": action, "id": sid, "noop": True}
            dst_dir = PROJECTS_DIR / project
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst_dir / src.name))
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
                desktop = load_desktop_sessions()
                sync = sync_extras(desktop)  # 自动对齐：本地多余的会话删掉
                self._json(
                    200,
                    {
                        "ok": True,
                        "claude_home": str(CLAUDE_HOME),
                        "claude_running": claude_running(),
                        "sync": sync,
                        "sessions": collect(desktop),
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

        # 兼容两种入参：单条 id，或批量 ids=[...]
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
                # 单条：保持原有返回结构不变
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
        pass  # 静音访问日志


def create_server(port):
    """构建一个监听指定端口的服务实例（供原生 app 入口复用）。"""
    return ThreadingHTTPServer((HOST, port), Handler)


def main():
    if not INDEX_HTML.exists():
        print("警告：缺少 index.html，页面无法显示。", file=sys.stderr)
    if not PROJECTS_DIR.exists():
        print(f"警告：未找到会话目录：{PROJECTS_DIR}", file=sys.stderr)
    server = create_server(PORT)
    url = f"http://{HOST}:{PORT}/"
    print("=" * 48)
    print(" Claude Code 对话管理器 已启动")
    print(f"   地址       : {url}")
    print(f"   CLAUDE_HOME: {CLAUDE_HOME}")
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
