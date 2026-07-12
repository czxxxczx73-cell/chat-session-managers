# Version 2.0.1 — conversation-only Codex list

This patch fixes Codex one-shot execution records appearing as conversations.

## Fixed

- Excludes sessions marked `source=exec` or `originator=codex_exec` from the conversation manager.
- Filters injected `AGENTS.md instructions`, permission blocks, environment context, and skill context from user titles, previews, and turn counts.
- Omits records that contain no genuine user conversation turn.
- Adds a regression fixture containing both an injected context block and an `exec` session.
- Makes package and Release versions follow the Git tag instead of being hard-coded to 2.0.0.

The existing card-based UI is unchanged and remains protected by the byte-for-byte UI check.
