#!/bin/bash
# 在你自己的 Mac 上，把 apps/ 下的源码生成为桌面 App。
#
# 用法:
#   bash build.sh                       # 生成全部 3 个 App
#   bash build.sh codex                 # 只生成 Codex 对话管理器
#   bash build.sh claude-code grok      # 只生成指定的几个
#
# 生成的 App 出现在你自己的 ~/Desktop 下。每台机器第一次运行都会
# 用【这台机器自己的】Python 现装一份 pywebview + pyobjc ——不依赖
# 任何人预先打包好的依赖，所以在别人电脑上跑出来的 App 只属于那台电脑。
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "❌ 这几个 App 用了 macOS 专属的 pywebview + pyobjc 做原生窗口，只能在 Mac 上构建和运行。" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"
BUILD_VENV="$ROOT/.build/venv"
DESKTOP="$HOME/Desktop"

ALL_APPS=(codex claude-code grok)

# 不用关联数组（declare -A）：macOS 自带的 /bin/bash 是 3.2（苹果因 GPLv3
# 许可问题多年没升级过），不支持关联数组——这里用 case 换取兼容性，
# 保证脚本在"随便一台 Mac、没装过新 bash"的默认环境下也能跑。
app_display_name() {
  case "$1" in
    codex) echo "Codex 对话管理器" ;;
    claude-code) echo "Claude Code 对话管理器" ;;
    grok) echo "Grok 对话管理器" ;;
  esac
}
app_log_name() {
  case "$1" in
    codex) echo "CodexChatManager" ;;
    claude-code) echo "ClaudeCodeChatManager" ;;
    grok) echo "GrokChatManager" ;;
  esac
}
is_valid_app() {
  case "$1" in
    codex|claude-code|grok) return 0 ;;
    *) return 1 ;;
  esac
}

TARGETS=("$@")
if [[ ${#TARGETS[@]} -eq 0 ]]; then
  TARGETS=("${ALL_APPS[@]}")
fi

for t in "${TARGETS[@]}"; do
  if ! is_valid_app "$t"; then
    echo "❌ 不认识的 App 名字: $t" >&2
    echo "   可选: ${ALL_APPS[*]}" >&2
    exit 1
  fi
done

echo "→ 查找系统 Python 3…"
PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "❌ 没找到 python3。请先安装一个（例如 brew install python@3.14，或去 python.org 下载），再重新运行本脚本。" >&2
  exit 1
fi
PYTHON_REAL="$("$PYTHON_BIN" -c 'import sys; print(sys.executable)')"
PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "  使用: $PYTHON_REAL (Python $PY_VERSION)"

if [[ ! -d "$BUILD_VENV" ]]; then
  echo "→ 首次构建：创建隔离环境并安装 pywebview + pyobjc（需要联网，可能要 1-2 分钟）…"
  "$PYTHON_BIN" -m venv "$BUILD_VENV"
  "$BUILD_VENV/bin/python3" -m pip install --upgrade pip -q
  # 只装 pywebview 的 Cocoa 后端实际用到的几个 pyobjc 框架子包，
  # 不装整个 pyobjc（那是 140+ 个 Apple 框架绑定的大杂烩，体积大一个数量级）。
  if ! "$BUILD_VENV/bin/python3" -m pip install -q \
    pywebview \
    pyobjc-core \
    pyobjc-framework-Cocoa \
    pyobjc-framework-Quartz \
    pyobjc-framework-Security \
    pyobjc-framework-UniformTypeIdentifiers \
    pyobjc-framework-WebKit; then
    echo "❌ 依赖安装失败。常见原因：没联网，或缺 Xcode Command Line Tools（运行 xcode-select --install 后重试）。" >&2
    exit 1
  fi
  echo "→ 清理不需要在运行时打包的东西（测试用例/构建工具/调试符号，体积从这一步省下来）"
  SP="$BUILD_VENV/lib/python$PY_VERSION/site-packages"
  rm -rf "$SP/PyObjCTest" "$SP"/pip "$SP"/pip-*.dist-info "$SP/__pycache__"
  find "$SP" -iname "*.dSYM" -type d -prune -exec rm -rf {} +
else
  echo "→ 复用已有构建环境: $BUILD_VENV"
  echo "  （想强制重装依赖，删除 .build/ 目录后重新运行本脚本）"
fi

SITE_PACKAGES="$BUILD_VENV/lib/python$PY_VERSION/site-packages"
if [[ ! -d "$SITE_PACKAGES" ]]; then
  echo "❌ 没找到 $SITE_PACKAGES，构建环境可能已损坏。删除 $ROOT/.build 后重新运行本脚本。" >&2
  exit 1
fi

build_one() {
  local key="$1"
  local name; name="$(app_display_name "$key")"
  local logname; logname="$(app_log_name "$key")"
  local src="$ROOT/apps/$key"
  local app="$DESKTOP/$name.app"
  local res="$app/Contents/Resources"
  local macos="$app/Contents/MacOS"

  echo ""
  echo "=== 构建: $name ==="

  echo "→ 清理旧 App（如果存在）"
  rm -rf "$app"

  echo "→ 建立 App 目录结构"
  mkdir -p "$res" "$macos"

  echo "→ 写入 Info.plist"
  cp "$src/Info.plist" "$app/Contents/Info.plist"

  echo "→ 生成 launcher（写入本机 Python 路径）"
  sed \
    -e "s|__PYTHON_REAL__|$PYTHON_REAL|g" \
    -e "s|__PY_VERSION__|$PY_VERSION|g" \
    -e "s|__LOG_NAME__|$logname|g" \
    "$ROOT/common/launcher.template" > "$macos/launcher"
  chmod +x "$macos/launcher"

  echo "→ 复制程序代码"
  cp "$src/app.py" "$src/server.py" "$src/index.html" "$res/"

  echo "→ 写入依赖（刚才在这台机器上现装的，不是打包带过来的）"
  mkdir -p "$res/venv/site-packages"
  cp -R "$SITE_PACKAGES/." "$res/venv/site-packages/"

  if [[ -f "$src/icon.icns" ]]; then
    echo "→ 复制图标"
    cp "$src/icon.icns" "$res/icon.icns"
  fi

  echo "→ 去除隔离属性 / ad-hoc 签名"
  xattr -dr com.apple.quarantine "$app" 2>/dev/null || true
  codesign --force --deep --sign - "$app" 2>/dev/null || true

  touch "$app"
  echo "✅ 完成: $app"
}

for t in "${TARGETS[@]}"; do
  build_one "$t"
done

echo ""
echo "全部完成，去 ~/Desktop 双击打开就行。"
echo "如果提示「无法验证开发者」：右键点 App → 打开 → 再点一次「打开」确认，"
echo "以后就能正常双击了（这是本地 ad-hoc 签名、没做 Apple 公证的正常提示，不是坏了）。"
