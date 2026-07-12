# Privacy

Chat Session Managers works on local conversation files and is designed not to transmit them.

- The native host allows WebKit navigation only to `127.0.0.1`, `localhost`, or local files.
- Each standard-library Python service binds only to `127.0.0.1` on a random port.
- There is no analytics, telemetry, crash reporting, account system, CDN, external font, or cloud database.
- Search, filtering, and refresh are read-only.
- Archive, restore, and delete require an explicit user action.
- Delete creates a local backup before removing the selected original.
- Claude refresh does not automatically delete local transcripts.
- A parent-process monitor stops the loopback service if the native host exits unexpectedly.

The release needs a local Python interpreter, but it does not download any dependency at runtime.

Automated checks lock the existing UI files, reject user-specific absolute paths and external runtime URLs, and verify read-only refresh with fictional fixtures.
