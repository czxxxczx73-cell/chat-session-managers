# Chat Session Managers

Three focused, local-first macOS Apps for browsing and managing conversation history from **Codex**, **Claude Code**, and **Grok**. Install only the Apps you use; no account, cloud database, analytics, or telemetry is involved.

## Watch the functional demo

[**Watch the 20-second 1080p live UI demo →**](https://github.com/czxxxczx73-cell/chat-session-managers/releases/download/v2.0.1/chat-session-managers-demo-v2.mp4)

The video shows real search, source and status filters, multi-select batch archive, restore, and the recoverable backup warning shown before delete. It uses isolated fictional data. A lightweight animated preview is embedded directly in the README, and the full experience is available on the [bilingual product page](https://czxxxczx73-cell.github.io/chat-session-managers/).

## Current highlights

- Direct ~4.2 MB Universal 2 package for Apple Silicon and Intel Macs
- Native WebKit host — no bundled pywebview/pyobjc runtime
- Full English / Simplified Chinese interface and localized App names
- Loopback-only local service with external WebKit navigation blocked
- Claude refresh no longer auto-deletes local transcripts
- Parent-process cleanup prevents orphaned local services
- Fictional fixture tests verify read-only refresh for all three providers
- Codex one-shot `exec` tasks and injected AGENTS context are excluded from the conversation list
- GitHub Social Preview and sharper bilingual project positioning

## Download

- `Chat-Session-Managers-v<version>-universal.zip` — the Universal 2 App package
- `chat-session-managers-demo-v2.mp4` — the 20-second 1080p live UI walkthrough

Requires Python 3.9+ installed locally (used only for the standard-library session service, not for the window itself). The Apps are ad-hoc signed, so macOS may require right-clicking and choosing **Open** once.

Questions, ideas, and showcases are welcome in [GitHub Discussions](https://github.com/czxxxczx73-cell/chat-session-managers/discussions). Bug reports belong in [GitHub Issues](https://github.com/czxxxczx73-cell/chat-session-managers/issues).
