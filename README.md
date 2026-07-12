English | [中文](./README.zh-CN.md)

# Chat Session Managers (Codex / Claude Code / Grok)

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![Network](https://img.shields.io/badge/network-100%25%20offline%20at%20runtime-success.svg)

Three small local tools for browsing the conversation history that **Codex**, **Claude Code**, and **Grok** leave on your own machine, with archive / unarchive / delete actions built right into the UI. Everything runs locally — no network access at runtime, no conversation content ever leaves your computer.

> The first time you run `build.sh` on any Mac, it installs its dependencies fresh **using that machine's own Python**. The resulting App belongs only to that machine — you're not downloading someone else's prebuilt binary, and nothing from the original author's computer (paths, architecture, anything) is baked in.

## Screenshots

*(All content shown below is fictional demo data generated for these screenshots — not anyone's real conversations.)*

| Codex | Claude Code | Grok |
|---|---|---|
| ![Codex screenshot](./docs/screenshots/en/codex.png) | ![Claude Code screenshot](./docs/screenshots/en/claude-code.png) | ![Grok screenshot](./docs/screenshots/en/grok.png) |

> The UI itself is bilingual too — it follows your system/browser language automatically (English shown above; see the [Chinese README](./README.zh-CN.md) for a 中文 screenshot). Force a language with `?lang=en` or `?lang=zh` in the address bar if you ever need to override the auto-detection.

## Quickstart

```bash
git clone <this repo's URL>
cd chat-session-managers
bash build.sh
```

When it finishes, three Apps appear on your Desktop:

- **Codex 对话管理器.app**
- **Claude Code 对话管理器.app**
- **Grok 对话管理器.app**

Just double-click to open. If macOS says "cannot verify developer" the first time: right-click the App → Open → click "Open" again to confirm. That's the normal message for a locally ad-hoc-signed app that hasn't been notarized by Apple (a personal tool like this doesn't have an Apple Developer account) — after confirming once, double-clicking works normally from then on.

Only want one or two of them:

```bash
bash build.sh codex              # only build the Codex manager
bash build.sh claude-code grok   # only build these two
```

### Requirements

- **macOS 11 or later** (uses macOS-only `pywebview` + `pyobjc` for the native window; won't run on Windows/Linux)
- **Python 3.9+** (`brew install python@3.14` recommended; the system's built-in `python3` also works)
- The first build needs internet access (to install `pywebview` + `pyobjc`, roughly 1-2 minutes); later rebuilds reuse the `.build/` cache and skip re-downloading

## What each App looks at

| App | Data source | How archive/delete is implemented |
|---|---|---|
| **Codex** | `~/.codex/sessions`, `~/.codex/archived_sessions` | Calls the official `codex archive / unarchive / delete` commands, so internal indexes never get out of sync |
| **Claude Code** | `~/.claude/projects/**/*.jsonl` | No corresponding CLI command exists, so this tool moves files directly: archive = move to `~/.claude/projects_archived/`; delete auto-backs-up to `~/.claude/deleted_sessions/` first |
| **Grok** | `~/.grok` | Same approach as Claude Code — file-level operations with automatic backup |

Shared features across all three: browse (title/updated time/directory/source/preview), search by title or content, filter by status, archive/unarchive/delete (deletes always back up first — nothing is ever hard-deleted).

## Project layout

```
chat-session-managers/
├── build.sh                Generates the Apps (run this on your own machine)
├── common/
│   └── launcher.template   Template for each App's launcher script; build.sh fills in the local Python path
└── apps/
    ├── codex/
    │   ├── app.py          Desktop window entry point (pywebview)
    │   ├── server.py       Local HTTP server + read/action logic
    │   ├── index.html      Frontend UI (single file)
    │   ├── Info.plist      App metadata (name/icon/bundle ID)
    │   └── icon.icns
    ├── claude-code/  (same layout as above)
    └── grok/         (same layout as above)
```

What `build.sh` does: finds a usable system Python → creates an isolated environment with `pywebview`+`pyobjc` installed → assembles each `apps/<name>/`'s code + that isolated environment + icon into a standard `.app` bundle → signs it locally (ad-hoc). At no point does it write any absolute path into git, and build output isn't committed either (see `.gitignore`).

## Security notes

- **Fully local, zero outbound network calls at runtime.** None of the three Apps' `server.py` / `app.py` / `index.html` contain any `http(s)://` call pointing outside localhost, no CDN/external-font/third-party-script references, and no analytics or error-reporting SDK of any kind. You can verify this yourself with `grep -rE "https?://" apps/` — the only matches are local addresses (`127.0.0.1:<port>`) and XML namespace strings, nothing else.
- The backend only listens on `127.0.0.1` — never exposed to your LAN or the public internet.
- The only moment that needs internet access is **the first run of `build.sh`**, which downloads the two public packages `pywebview`/`pyobjc` from PyPI. That's a build-time action, separate from the App actually reading/displaying your conversation data — the App itself makes no network calls while running.
- Every data source each app reads is consistently overridable via its own env var (`CODEX_HOME`, `CLAUDE_CONFIG_DIR` + `CLAUDE_DESKTOP_SESSIONS_DIR`, `GROK_HOME`) — useful for testing with isolated/fake data instead of your real history. This was tightened after an internal review found the Claude Code app had one hardcoded path that didn't respect the override; it's now fixed and consistent with the other two apps.
- Every delete backs up first, then acts — an accidental delete can always be recovered by hand.
- Session IDs are strictly validated before being passed to subprocesses (as an argument array, never a shell string), so there's no command-injection risk.

## Known limitation

**Codex: cloud sync can "undo" a delete.** If the Codex/ChatGPT Desktop client is running and a session has already synced to the cloud, a local delete/archive may get pulled back down by cloud sync — it'll look like "the delete failed / it came back." To make a delete on a cloud-synced session permanent: quit the Desktop client before deleting with this tool, and/or delete the session on the cloud side (there's no CLI command for that). This tool's write operations always back up first, so even if sync restores a file, no data is lost.

## License

MIT — see [LICENSE](./LICENSE).
