# Implementation plan

1. Pin regression behavior: credential masking, volume values, registry envelope keys,
   read-only endpoint guard, one WS failure, selected sources, source/target separation.
2. Adapt collector into app/hacontext/engine.py; add state.py for installation ownership,
   private settings, discovery, archive management and identity-based legacy cleanup.
3. Add worker.py: serialized progress, cancelable exports, provenance, report consistency,
   stable entity comparison, companion inventory, retention, source-only sharing archive.
4. Add ui.py: full-screen first-run wizard, export/inventory/history/preview/docs/settings,
   reset/uninstall confirmations and conditional old-install cleanup. Test via pipe input.
5. Add Linux bootstrap/launcher and HA OS Dockerfile/ingress terminal/file downloads with
   ingress-peer verification, no external port and no shell access. Validate configs.
6. Run regression + end-to-end + real terminal rendering tests; audit distribution for
   private user values; package source ZIP/tar plus portable first-command installer.

Execution: local isolated build branch, no remote changes. Existing collector is a starting
point, not proof of compatibility. No access to a real user's HA or Docker daemon here.
Tests use a synthetic HTTP/WebSocket server and temporary filesystem. HA OS integration
must be explicitly marked untested on a running Supervisor until such a test is available.
