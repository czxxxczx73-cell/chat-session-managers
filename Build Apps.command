#!/bin/bash
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || exit 1

LANGUAGE="$(defaults read -g AppleLanguages 2>/dev/null | head -2 | tail -1 || true)"
if [[ "$LANGUAGE" == *zh* ]]; then
  echo "对话管理器 · 本机构建器"
  echo "这一步只在你的 Mac 上生成 App，不会上传任何对话或本机数据。"
  echo "首次构建需要联网安装公开的 Python 依赖。"
else
  echo "Chat Session Managers · Local Builder"
  echo "This creates the Apps on your Mac. It does not upload conversations or local data."
  echo "The first build needs internet access to install public Python dependencies."
fi
echo ""

/bin/bash "$ROOT/build.sh"
STATUS=$?

echo ""
if [[ $STATUS -eq 0 ]]; then
  if [[ "$LANGUAGE" == *zh* ]]; then
    echo "完成：三个 App 已生成到桌面。按任意键关闭窗口。"
  else
    echo "Done: all three Apps were created on your Desktop. Press any key to close."
  fi
else
  if [[ "$LANGUAGE" == *zh* ]]; then
    echo "构建失败（状态 $STATUS）。请保留上方错误信息。按任意键关闭窗口。"
  else
    echo "Build failed (status $STATUS). Keep the error above for troubleshooting. Press any key to close."
  fi
fi
read -n 1 -s
exit $STATUS
