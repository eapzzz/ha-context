# Changelog

## 2.1.1 — Docker export authorization

- Export workers keep the SSH terminal session and use a separate process group.
  `sudo` authorization is no longer discarded by creating a detached session.
- Safe cancellation and shutdown target only the worker group, including the
  interval before the worker has created its group on Python 3.10+.
- Docker inspection errors are preserved instead of becoming “container gone”.
- Local folder validation distinguishes permission denial, missing configuration
  and unreadable files. It does not change any Home Assistant permissions.
- Export failures show a stopped screen with Retry and Connection settings;
  stderr is drained without displaying or storing raw private data.
- Added real worker, process-group, PTY, cancellation, local-file-access and
  REST/WebSocket regression tests. PTY sudo policy is simulated; no sudoers
  changes, token migration or new dependencies are needed.


## 2.1.0

- Fixed viewport shell and menu, active-page highlighting, F6 navigation, Esc/back
  handling, mouse focus, and wrapping action rows for narrow terminals.
- Immediate list selection for chapters, previews and inventory; documentation
  Previous/Next, reader search and word-based prose wrapping on resize.
- Reactive inventory search, compact status filter, selected-row details and cached
  parsed inventory; preserve filters and selected entity when editing context.
- Private entity/device/area notes, exact-ID export and explicit unmatched targets.
  Existing general notes are preserved. Drafts survive page switches in-session;
  quitting warns before discarding them. Ctrl-S saves the current note.
- Updated in-app help and simpler settings summary. No new dependencies.
- Regression tests drive keyboard/mouse events, viewport resizing, saved notes,
  real local REST/WebSocket export and Git fast-forward with private data retained.

## 2.0.1

- Fix first-run portable ZIP metadata discovery. Dependencies and their metadata
  were bundled, but metadata in `.pyz/.vendor` was not discoverable by Python's
  standard metadata finder. Bootstrap now has archive-root metadata aliases;
  installed files still keep just one copy under `.vendor`.
- Add isolated (`-I -S`) startup and dependency-resolution tests against the built
  archive, including a real pseudo-terminal opening the folder-selection screen.
- Verify the installed offline UI independently of bootstrap aliases.
- Add workspace navigation, phone-filter and conditional-cleanup regression tests.
- Document actual navigation names and limitations instead of implying seven
  identically named, fully equivalent tabs.
- Include Python 3.14 in the proposed CI matrix. This is not a claim that that
  remote workflow ran in the authoring environment.

## 2.0.0

- One-root application with English full-screen onboarding, docs and maintenance.
- Linux portable installation and source launcher; native HA OS ingress package.
- Cancelable export worker, phone-registration inventory, history and file preview.
- Accurate warning grouping, intentional omissions and local registry fallbacks.
- Secret masking no longer learns ordinary numbers, registry envelope keys or service
  parameter schemas. Notification contents are separated from notification telemetry.
- One failed WebSocket handshake per snapshot, with useful status-code diagnostics.
- Read-only source boundaries, conditional identity-based legacy cleanup, typed reset
  and uninstall confirmation, and source-only sharing.

Native HA OS integration remains experimental until tested on a real Supervisor.
