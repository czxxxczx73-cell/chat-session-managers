# Release notes

This file is the `--notes-file` used by `.github/workflows/release.yml` for whichever tag was just pushed — update it before tagging a new release so it describes what actually changed.

## Current highlights

- Direct ~4.2 MB Universal 2 package for Apple Silicon and Intel Macs
- Native WebKit host — no bundled pywebview/pyobjc runtime
- Full English / Simplified Chinese interface and localized App names
- Loopback-only local service with external WebKit navigation blocked
- Claude refresh no longer auto-deletes local transcripts
- Parent-process cleanup prevents orphaned local services
- Fictional fixture tests verify read-only refresh for all three providers

## Download

- `Chat-Session-Managers-v<version>-universal.zip` — the only distributed package

Requires Python 3.9+ installed locally (used only for the standard-library session service, not for the window itself). The Apps are ad-hoc signed, so macOS may require right-clicking and choosing **Open** once.
