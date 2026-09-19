# ha-context

A read-only Home Assistant inventory app. Guided setup, phone sensors, configuration,
privacy review and a reusable TXT/ZIP snapshot — in one English terminal workspace.
No model, MCP server, telemetry or automatic upload is used.

## Workspace 2.1

The workspace keeps one full-screen background, fixed navigation and a stable footer.
F6 focuses the menu, arrows choose a page, Enter opens it. Tab cycles controls;
Esc returns/cancels and Ctrl-S saves the open note. Mouse controls follow the same
selection as the keyboard. Long action rows wrap rather than overflowing a small terminal.

Documentation chapters and file previews open on selection. Documentation also has
Previous/Next and Ctrl-F search. Entity search filters while typing, and selecting
an entity shows its details. Reopening the inventory reuses its parsed snapshot.

Attach descriptions directly with **Entity note**, **Device note**, or **Room note**.
**Notes → General notes** keeps the existing household-wide text. Notes are private,
never written into HA, and included in new exports as `annotations.json` and
`user-notes.md`. IDs are exact; unmatched targets are explicitly marked. Notes saved
before this release are preserved, and reset does not remove either type.

### Updating an existing Git-connected installation

Overlay the source archive contents into your LOCAL source checkout (the folder
containing `.git`). Review the diff, stage new and modified files, commit, and push.
On the server, choose **Maintenance → Update from Git**, confirm, then restart
`ha-context`. Do not reinstall or repeat onboarding. This version adds no dependencies
and leaves `.git`, `.vendor`, `.venv`, tokens, settings and existing exports alone.
Source files only are packaged. Do not publish the server's `local/` folder.

## Start on Linux

**Recommended: use the portable release `ha-context.pyz`.** Copy it to the Linux server
where you want the app installed and run:

```sh
python3 "$HOME/ha-context.pyz"
```

Choose a dedicated folder (default `~/ha-context`). Included pure-Python dependencies
make the portable release usable without contacting a package server. Python 3.10+
and an interactive terminal are still required. No existing folder is overwritten.

Onboarding configures the connection, optional local files, privacy and export retention.
It installs one `ha-context` command shortcut. Subsequent runs need only:

```sh
ha-context
```

The shortcut is placed in `~/.local/bin` when that folder is already in PATH, otherwise
`/usr/local/bin` with a standard system `sudo` prompt. Shell startup files are not edited.
The program does not save your sudo password or add you to the Docker group.
The downloaded installer is not part of the installation and may be removed afterward.

### From a Git clone or source ZIP

Clone/copy this whole project to a dedicated folder, then run `bash install.sh` from that
folder. The launcher creates its private `.venv` and installs pinned requirements.
This source-only method needs working Internet/PyPI access and Python's `venv` module.
The installer remains interactive; it does not copy your own HA token to friends.

## Home Assistant OS

This repository includes a native HA OS **app** definition (formerly called add-on) in
`app/`. It uses the same terminal workspace inside authenticated HA ingress, with file
download links above the terminal.

Once this source is in a GitHub repository, add that repository URL in Home Assistant's
**Settings → Apps → App store → menu → Repositories**, install **ha-context**, start it,
and select **Open Web UI**. Older HA versions may call these screens Add-ons.
No GitHub repository URL is hardcoded here because the destination repo is user-owned.

The Supervisor provides authentication; no personal HA token is needed in the native app.
The HA configuration is mounted **read-only** at `/homeassistant_config`. Private data
uses `/data/local`, managed by HA OS. No Docker socket or host network access is requested.
The terminal command is fixed to this app; it is not an arbitrary shell. Exports can be
downloaded from **Files**. Keep the terminal tab open while exporting.

**HA OS support is experimental:** the gateway, authentication checks and download routes
have automated local tests, but this release has not been installed on a real Supervisor
or built with Docker in the authoring environment. CI includes an image-build job; it has
not been run remotely here. Do not equate these tests with a real-device validation.

A Linux installation can also connect to a remote HA OS instance through its HA URL and
a personal token. Select **API only** when no configuration folder is available. Such
an export cannot include arbitrary local YAML/includes; the coverage report says so.

## What is included

- Five-step onboarding and remembered settings; Docker/Podman discovery with a manual
  source selector. Direct container addresses can be refreshed by the selected name.
- Full TXT + ZIP export, progress and cancellation. Both contain the same sanitized
  sections, with file sizes and SHA-256 checksums. Large text exports have split parts.
- Entity/device/area registries, disabled entries, live states and attributes, available
  actions, local configuration/includes/blueprints/templates, helper metadata, dashboards
  and read-only device automation descriptions where supported by that HA version.
- Companion App inventory grouped by **device registration ID**, not by duplicate names.
  Enabled, disabled and unavailable are separate. Notification service names are retained.
- Entity search, phone-only view, filtered entity selection export, coverage/issue browser,
  export history, stable inventory/configuration comparison, notes and retention.
- Private-value redaction with structural IDs preserved, plus optional network masking.
- Built-in documentation, independent connection diagnostics, reset, source-package
  creation, Git/source-ZIP update, conditional old-install cleanup and uninstall.

## Navigation and current limits

The left menu contains **Overview**, **Create export**, **Devices & sensors**,
**Export history**, **Diagnostics**, **Notes**, **Documentation**, **Settings**,
and **Maintenance**. Privacy preferences are under **Settings → Privacy & retention**;
file preview is under **Export history → Review** or **Overview → Review latest**.

These are not seven identically named tabs. Overview is a snapshot summary, not a
live connection monitor. A saved filtered entity view is not a full room-scoped
configuration export. The privacy preview displays reports and exported sections,
not an interactive per-value redaction editor. The included Workspace navigation
chapter describes these limits and the exact paths.

## One installation root

```text
ha-context/
  app/                   application and built-in docs
  .vendor/ or .venv/      isolated dependencies
  local/                 private, never included in source sharing
    config.json          preferences and selected HA source
    token                personal HA token, mode 600
    notes.md             general context for future chats
    annotations.json     private notes tied to entities, devices and areas
    exports/             completed snapshots
    logs/                tool diagnostics, not HA history
  ha-context             launcher
  install.sh
```

Only the command symlink lives outside this root. HA OS necessarily separates immutable
image files from Supervisor-managed `/data`; uninstall/update there use HA's own controls.

## Maintenance and old versions

A new install displays **no legacy cleanup option**. The option appears only after
positively recognizing files from the earlier exporter. Removal shows the exact selected
path and requires typing `REMOVE`. Unknown directories, HA configuration and other apps
are never selected by a broad name-only search.

**Reset settings** removes the saved connection/token and restarts onboarding, preserving
notes and exports. It does not revoke the token at the HA server; revoke it in your HA
profile separately when appropriate. **Uninstall ha-context** on Linux requires typing
`UNINSTALL`, removes the identified installation root and its matching command shortcut,
and leaves Home Assistant unchanged. HA OS uses **Settings → Apps → ha-context → Uninstall**
to remove its image and private data; this is documented inside the interface.

Updates are explicit: a clean Git checkout can fast-forward from its configured upstream;
a package installation can accept a trusted source ZIP. Code rollback files stay inside
`local/rollback`. Private settings are preserved. Exit and reopen after an update.
Checksums detect corruption, not a malicious publisher; only install trusted code.

## What this is not

This is not a backup, live AI connection, event recorder or automation executor. No
history database, raw logs, camera recordings or external application source are exported.
A snapshot may be partial, stale or incomplete for the automation you have in mind.
Unloaded integration/device capabilities may be absent. The program reports unsupported
or failed reads instead of interpreting them as zero devices.

Redaction is best effort, not a guarantee for arbitrary custom YAML, free-form messages,
new integration attributes or obfuscated credentials. Names, room structure, presence,
entity IDs, schedules, SSIDs and IP addresses can be private even when not passwords.
Review the output before sharing. Never publish a running installation or private exports
as repository contents. Use **Maintenance → Create shareable source** instead.

## Export instead of MCP?

A fixed local exporter performs the repeatable collection without calling an LLM. You
review and reuse one snapshot in your chosen chat without providing it a token or direct
write access. An MCP-capable agent is useful for adaptive live queries and authorized
changes, but has a different interaction/permissions model. A file still consumes the
chat's context/usage, and a full snapshot is not necessarily cheaper than a few narrow
MCP reads. This tool makes no quota, unlimited-usage or cost-saving guarantee.

## Development and verification

```sh
python3 -m pip install -r app/requirements.txt -r app/requirements-haos.txt pytest
python3 -m pytest -q
```

Tests use synthetic data, temporary folders, a local REST/WebSocket server, the real TUI
event loop and local ingress HTTP clients. No user's server data is included in fixtures.
See `docs/design.md`, `docs/implementation-plan.md`, `SECURITY.md` and the in-app library.

## References

- https://developers.home-assistant.io/docs/api/rest/
- https://developers.home-assistant.io/docs/api/websocket/
- https://developers.home-assistant.io/docs/apps/configuration/
- https://developers.home-assistant.io/docs/apps/communication/
- https://developers.home-assistant.io/docs/apps/presentation/
- https://developers.openai.com/codex/mcp/

MIT-licensed application. Portable distributions retain third-party dependency licenses.


### Docker authorization correction (2.1.1)

Export and Diagnostics keep the same SSH terminal authorization context. The
worker creates a separate process group (not a new session) for targeted Cancel
and shutdown. Local-folder permission errors are not mislabeled as missing YAML.
Update normally from Git; no reinstall, new libraries, sudoers change, filesystem
permission change, or configuration/token migration is needed.
