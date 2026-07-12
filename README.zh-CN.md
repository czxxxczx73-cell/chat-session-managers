[English](./README.md) | [中文](./README.zh-CN.md)

# macOS 对话管理器

[![CI](https://github.com/czxxxczx73-cell/chat-session-managers/actions/workflows/ci.yml/badge.svg)](https://github.com/czxxxczx73-cell/chat-session-managers/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/czxxxczx73-cell/chat-session-managers)](https://github.com/czxxxczx73-cell/chat-session-managers/releases/latest)
[![macOS](https://img.shields.io/badge/macOS-13%2B-111111?logo=apple)](https://github.com/czxxxczx73-cell/chat-session-managers/releases/latest)
[![Universal](https://img.shields.io/badge/Universal-Apple%20Silicon%20%2B%20Intel-3a7bd5)](https://github.com/czxxxczx73-cell/chat-session-managers/releases/latest)
[![Local only](https://img.shields.io/badge/privacy-local%20only-2ea44f)](./PRIVACY.md)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

三款专门管理本地对话历史的 macOS App，分别支持 **Codex、Claude Code、Grok**。发布版换成了轻量 Universal 2 原生宿主，但完整保留原来的卡片式界面和排版。

| Codex | Claude Code | Grok |
|---|---|---|
| ![Codex 对话管理器](./docs/screenshots/zh/codex.png) | ![Claude Code 对话管理器](./docs/screenshots/zh/claude-code.png) | ![Grok 对话管理器](./docs/screenshots/zh/grok.png) |

所有截图均为虚构演示数据。界面会自动跟随 macOS / 浏览器语言，完整支持简体中文和英文。

## 直接下载

1. 打开 [最新 Release](https://github.com/czxxxczx73-cell/chat-session-managers/releases/latest)。
2. 下载 `Chat-Session-Managers-v<版本号>-universal.zip`。
3. 解压后，把需要的 App 拖入"应用程序"。
4. 当前为本地签名、未做 Apple 公证，因此首次启动可能需要 **右键 App → 打开**。

同一个发布包原生支持 Apple 芯片和 Intel Mac。轻量宿主不再打包 pywebview/pyobjc，但本机需要有 **Python 3.9 或更高版本**；程序会自动查找 Homebrew、python.org 和系统常见安装位置。

## 本地与隐私

- 没有分析、遥测、账户系统、云端数据库、CDN 或外部网络请求
- WebKit 宿主禁止跳转到 `127.0.0.1` / `localhost` 以外的地址
- Python 服务只监听随机的本机回环端口，并跟随父 App 退出
- 搜索、筛选和刷新全部只读
- 归档、恢复和删除必须显式点击按钮
- 删除前会先创建可恢复的本地备份
- Claude 刷新不会再根据 Desktop 登记区的临时差异自动删除 transcript

详见 [PRIVACY.md](./PRIVACY.md) 和 [SECURITY.md](./SECURITY.md)。

## 功能

- 按标题、目录和预览内容搜索
- 按工程、归档状态和来源筛选
- 查看标题、时间、路径、轮数、模型、版本和预览
- 支持批量选择（对应 App 支持时）
- 归档、恢复和先备份后删除
- 检测正在运行的 Codex / Claude Code 会话并显示冲突提示
- 完整中英文界面

| App | 本地数据来源 | 操作方式 |
|---|---|---|
| Codex | `~/.codex/sessions`、`~/.codex/archived_sessions` | 调用官方 `codex` 命令归档、恢复和删除 |
| Claude Code | `~/.claude/projects/**/*.jsonl`，以及可选的 Claude Desktop 登记信息 | 在活动/归档目录之间移动所选 transcript；仅 Desktop 记录保持只读 |
| Grok | `~/.grok/sessions` | 在活动/归档目录之间移动所选会话目录 |

删除前的备份保存在每个工具本地的 `deleted_sessions` 目录。

## UI 排版被严格锁定

三份 `index.html` 与 Claude 发布的卡片式排版逐字节一致。CI 会校验 SHA-1，只要内部视觉结构发生变化就直接失败。2.0 版改变的是宿主、打包、安全检查、语言元数据和 GitHub 发布体验，不是 App 里面的排版。

## 构建与验证

需要 macOS 13+、Xcode Command Line Tools 和 Python 3.9+。

```bash
git clone https://github.com/czxxxczx73-cell/chat-session-managers.git
cd chat-session-managers
make check test package installer
```

- `make check`：锁定 UI，并检查本机路径、遥测和外部运行时 URL。
- `make test`：使用隔离的虚构数据验证刷新只读。
- `make package`：生成直接下载的 Universal 2 发布包。
- `make installer`：生成“在自己的 Mac 上构建”的备用安装包。

欢迎贡献，参见 [CONTRIBUTING.md](./CONTRIBUTING.md)。项目采用 [MIT](./LICENSE) 许可证。
