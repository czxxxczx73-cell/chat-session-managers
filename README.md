[English](./README.en.md) | 中文

# 对话管理器（Codex / Claude Code / Grok）

三个本地小工具，分别用来查看 **Codex**、**Claude Code**、**Grok** 这三个 CLI 工具在你电脑上留下的对话历史，并直接在界面里完成归档 / 取消归档 / 删除。全部在本机运行，不联网、不上传任何对话内容。

> 每台电脑第一次运行 `build.sh` 时，会用**这台电脑自己的** Python 现装一份依赖，
> 生成的 App 只属于这台电脑——不是下载别人打包好的东西，也不会残留原作者电脑上的任何路径。

## 快速开始

```bash
git clone <这个仓库的地址>
cd chat-session-managers
bash build.sh
```

跑完之后，桌面上会出现三个 App：

- **Codex 对话管理器.app**
- **Claude Code 对话管理器.app**
- **Grok 对话管理器.app**

双击打开即可。首次打开如果 macOS 提示"无法验证开发者"：右键点 App → 打开 → 再点一次"打开"确认——这是本地 ad-hoc 签名、没做 Apple 公证的正常提示（个人小工具没有 Apple 开发者账号，这一步免不了），确认一次之后就能正常双击了。

只想装其中一个/两个：

```bash
bash build.sh codex              # 只生成 Codex 对话管理器
bash build.sh claude-code grok   # 只生成这两个
```

### 环境要求

- **macOS 11 及以上**（用到了 macOS 专属的 `pywebview` + `pyobjc` 做原生窗口，Windows / Linux 无法运行）
- **Python 3.9+**（推荐 `brew install python@3.14`；用系统自带的 `python3` 也可以）
- 第一次构建需要联网（现装 `pywebview` + `pyobjc`，约 1-2 分钟）；之后重复构建会复用 `.build/` 里的缓存，不用重新下载

## 这三个 App 分别看什么

| App | 数据来源 | 归档/删除的实现方式 |
|---|---|---|
| **Codex** | `~/.codex/sessions`、`~/.codex/archived_sessions` | 调用官方 `codex archive / unarchive / delete` 命令，保证内部索引不错乱 |
| **Claude Code** | `~/.claude/projects/**/*.jsonl` | 无对应 CLI 命令，本工具直接搬文件：归档 = 移到 `~/.claude/projects_archived/`；删除前自动备份到 `~/.claude/deleted_sessions/` |
| **Grok** | `~/.grok` | 同 Claude Code，文件级操作 + 自动备份 |

三个 App 的通用功能：查看（标题/更新时间/目录/来源/预览）、按标题或内容搜索、按状态筛选、归档/取消归档/删除（删除都是先备份再删，从不硬删）。

## 项目结构

```
chat-session-managers/
├── build.sh                生成 App 的脚本（在自己电脑上跑）
├── common/
│   └── launcher.template   App 启动脚本的模板，build.sh 会往里填本机 Python 路径
└── apps/
    ├── codex/
    │   ├── app.py          桌面窗口入口（pywebview）
    │   ├── server.py       本地 HTTP 服务 + 读取/操作逻辑
    │   ├── index.html      前端界面（单文件）
    │   ├── Info.plist      App 的元信息（名称/图标/Bundle ID）
    │   └── icon.icns
    ├── claude-code/  （同上结构）
    └── grok/         （同上结构）
```

`build.sh` 做的事情：找一个能用的系统 Python → 建一个隔离环境装好 `pywebview`+`pyobjc` → 把每个 `apps/<name>/` 的代码 + 这个隔离环境 + 图标，组装成标准 `.app` 结构 → 本地 ad-hoc 签名。全程不写入任何绝对路径到 git 里，构建产物也不提交（见 `.gitignore`）。

## 安全说明

- **完全本地运行，运行期零外部网络请求。** 三个 App 的 `server.py` / `app.py` / `index.html` 里没有任何指向非 localhost 的 `http(s)://` 调用、没有 CDN/外部字体/第三方脚本引用、没有任何埋点或错误上报 SDK——可以自己 `grep -rE "https?://" apps/` 验证，能看到的只有本机地址（`127.0.0.1:端口`）和 XML 命名空间字符串，别无其他。
- 后端只监听 `127.0.0.1`，不对外暴露局域网/公网
- 唯一需要联网的时刻是**首次运行 `build.sh`**，用来从 PyPI 下载 `pywebview`/`pyobjc` 这两个公开依赖包；这是构建期行为，和 App 运行时读取/展示你的对话数据是两回事，App 本身运行时不联网
- 所有删除操作都先备份、再操作，误删可以手动找回
- 会话 id 经过严格校验后才传给子进程（参数数组，非 shell 字符串拼接），不存在命令注入风险

## 已知限制

**Codex：云同步可能"撤销"删除。** 如果 Codex/ChatGPT Desktop 客户端正在运行，且该会话已同步到云端，本地删除/归档可能被云同步重新拉回本地。要让删除永久生效：退出 Desktop 客户端后再删，和/或去云端一侧删除该会话（CLI 无对应命令）。本工具的写操作都会先备份，即使被同步还原也不会丢数据。

## License

MIT，见 [LICENSE](./LICENSE)。
