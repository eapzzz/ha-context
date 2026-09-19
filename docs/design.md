# ha-context

## Approved brief
A self-contained Home Assistant inventory app. English full-screen terminal onboarding,
mouse/keyboard navigation, an offline help library and one remembered command. Standalone
Linux plus a native HA OS app with the same terminal UI through authenticated ingress.
Only read HA data. No LLM, telemetry, cloud upload, HA changes or persistent Linux service.

## Ownership
Linux: one chosen installation root; local configuration, token, notes, logs, exports,
Python environment stay inside it. One external command symlink. HA OS: immutable app
image, private persistent /data/local and a read-only HA configuration mount. Supervisor
owns installation/removal of the HA OS image; link back to app management for removal.
Detect legacy exporter assets by identity, not just names; show cleanup only when present.
Never remove HA configuration, other apps, unknown directories, mount points or symlink targets.

## Collection and trust
Reuse the existing read-only collector, but remove old scattered-settings entrypoints.
REST GET allowlist and WS read allowlist; validate TLS, no redirect with token. Use one
WS handshake attempt per snapshot, no invented Origin, cancellation via worker process.
Explicitly selected source: local mount, Docker/Podman container, or API only. Discover
addresses without tokens; require a user choice when ambiguous. Never select an arbitrary
container or silently switch an API instance. Record independent coverage per section,
filesystem fallbacks, intentional skips, unknown availability and partial status.

## Interface
A calm navy/lavender instrument panel, sky-blue active controls, warm amber incomplete
states. Default monospace inherited from SSH terminal. A five-step onboarding rail and
source-to-snapshot read-only chain form the visual signature. No animations or dependencies
on special fonts. Tab/Shift-Tab, arrow keys, Enter, mouse; F1 help, Ctrl-Q exit. Long content
scrolls. Failed input and network calls retain form values and offer a retry.

## Privacy
Credential field masking is separate from global known-value replacement. Never seed
numeric readings, ordinary words or service schema descriptions into secret replacements.
Structural IDs preserved; precise locations, credential attributes and email addresses
masked; optional extra masking of network metadata. Synthetic fixtures only in source.
Exports are private snapshots, not backups, and review remains required.

## Non-goals
No automated HA edits, event listening, historic database export, live phone access,
full external app source, password manager or automatic public publication.
