# Version 2.0 — same interface, complete release

This release preserves the original card-based Codex, Claude Code, and Grok interfaces while rebuilding everything around them for a smaller and more complete GitHub distribution.

## Highlights

- Direct 4.2 MB Universal 2 package for Apple Silicon and Intel Macs
- Original App UI files preserved byte for byte
- Native WebKit host replaces the bundled pywebview/pyobjc runtime
- Full English / Simplified Chinese interface and localized App names
- Loopback-only local service with external WebKit navigation blocked
- Claude refresh no longer auto-deletes local transcripts
- Parent-process cleanup prevents orphaned local services
- Fictional fixture tests verify read-only refresh for all three providers
- Optional build-on-your-own-Mac installer remains available

## Downloads

- `Chat-Session-Managers-v2.0.0-universal.zip` — recommended direct download
- `Chat-Session-Managers-Local-Installer-v2.0.0.zip` — locally builds the original pywebview package

The direct package requires Python 3.9+ installed locally. The Apps are ad-hoc signed, so macOS may require right-clicking and choosing **Open** once.
