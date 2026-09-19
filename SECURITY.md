# Security and privacy

The collector only uses allowlisted REST GET and WebSocket read commands. The HA account
behind a token may still have much broader privileges: read-only behavior is a property
of this code, not an enforced read-only HA credential scope. Protect the local token.

TLS certificates are verified. HTTP redirects are not followed with tokens. An explicit
plain-HTTP local URL is allowed; use it only across a trusted host/network. Discovery
inspects selected container metadata without exposing environment variables. It does not
scan the whole LAN or automatically forward a token to every discovered service.

Read-only configuration access is intentionally narrow. Symlinked files/directories,
non-regular files, private authentication storage, databases, logs and backup content are
excluded. Files and responses have size limits; deeply nested exported structures are
bounded. Unknown integration credentials are not part of the metadata projection.

Private files use restrictive Unix modes. Redaction is best effort: unusual key naming,
custom encodings, text instructions and arbitrary secrets cannot be guaranteed safe.
Sensitive exports should not be uploaded to public bug reports. Use synthetic reproductions.

The HA OS gateway trusts only the actual Supervisor ingress peer, not forwarded client
headers. It has no public port mapping. Download names and snapshot identities are
allowlisted; there is no generic file browser, shell prompt, command URL argument or
arbitrary proxy host. Single-session application locking also prevents simultaneous
maintenance and export operations.

Source distribution excludes local state, old snapshots, .git history and dependencies.
A source package is executable code, not harmless configuration. SHA-256 checks prove
integrity only, not authorship. Do not install untrusted ZIP updates.

Uninstall, reset and legacy deletion require explicit UI confirmation. The Linux root is
ownership-marked and checked for Home Assistant configuration overlap/mount points.
Unknown contents placed inside an owned installation folder are still part of a complete
uninstall; keep unrelated documents and services outside the installation root.
