# Maintenance

## Reset settings

Removes the exporter's local connection settings and token. Notes, exports and
program code remain. The next screen is onboarding. This does not revoke a token
at HA, reset your phone, change Home Assistant or delete any automation.

## Previous exporter files

This control appears only when recognized previous exporter files are detected.
A clean installation does not show an empty cleanup panel. Paths are checked by
file identity and expected structure. Select one, review it and type REMOVE.
Unknown files, inaccessible paths, symlink directories and mount points are not
silently removed. Files owned by another account may need that account's help.

## Uninstall

On Linux, review the installation path and type UNINSTALL. The application removes
its own folder (including notes, token, exports, runtime and logs) and only command
symlinks that point to this installation. Removing a system shortcut can require
one system sudo authorization. The deletion guard rejects HA config folders,
protected system folders, your home directory, overlaps and mounted directories.

On HA OS the Supervisor owns the app image and data. Use Settings → Apps →
ha-context → Uninstall. This is deliberately not replaced by a privileged host
shell. The app's UI explains this path. No command needs to be typed.

## Updates

For a Git clone, Update from Git fetches its origin and applies fast-forward-only
changes. Tracked local modifications stop the update. For a package installation,
Install source ZIP accepts a trusted ha-context source archive. File paths and
checksums are validated; a code rollback copy is saved under local/rollback.
Local settings, notes, token and exports are never copied out or overwritten by
source updates. An interrupted update is not equivalent to an atomic filesystem
snapshot, so do not remove power while applying it. Restart after an update.

Runtime dependencies remain in the app folder. If a future version changes the
dependency list, the launcher prepares a new private .venv/ using the network.
Keep rollback copies only while needed; uninstall removes them with local/.
