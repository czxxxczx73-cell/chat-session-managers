#!/usr/bin/env python3
"""Claude Code 对话管理器 — 原生桌面 App 入口。

用 pywebview 在 macOS 原生 WebView 窗口中加载界面，后台线程跑内置 HTTP 服务。
关闭窗口即退出进程并停止服务——表现为一个普通可开关的桌面应用。
"""
import os
import socket
import sys
import threading
import time

# 让本文件无论从哪里被调用都能找到同目录的 server.py / index.html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import webview  # noqa: E402

import server as srv  # noqa: E402


def pick_port(preferred=8765):
    """优先用 8765，被占用则让系统分配一个空闲端口。"""
    for p in (preferred, 0):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", p))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            continue
    return preferred


def wait_until_up(port, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return True
        except OSError:
            time.sleep(0.05)
    return False


APP_NAME = "Claude Code 对话管理器"


def set_app_identity():
    """修正 macOS 进程身份：菜单栏名称 + Dock 图标 + 在 Dock 中显示。

    因为入口是直接运行 python，进程默认被识别为 “Python”。这里用 pyobjc
    在 NSApplication 启动前覆盖 bundle 名称并设置图标，让它表现得像普通应用。
    """
    try:
        from Foundation import NSBundle

        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info is not None:
            info["CFBundleName"] = APP_NAME
            info["CFBundleDisplayName"] = APP_NAME
    except Exception:
        pass
    try:
        from AppKit import NSApplication, NSImage

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(0)  # NSApplicationActivationPolicyRegular
        icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.icns")
        if os.path.exists(icon):
            image = NSImage.alloc().initWithContentsOfFile_(icon)
            if image is not None:
                app.setApplicationIconImage_(image)
    except Exception:
        pass


def main():
    port = pick_port()
    httpd = srv.create_server(port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    wait_until_up(port)

    set_app_identity()

    webview.create_window(
        APP_NAME,
        f"http://127.0.0.1:{port}/",
        width=1180,
        height=800,
        min_size=(820, 560),
    )
    webview.start()  # 阻塞，直到窗口被关闭

    try:
        httpd.shutdown()
    except Exception:
        pass


if __name__ == "__main__":
    main()
