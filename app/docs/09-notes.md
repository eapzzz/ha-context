# Context notes

Notes add facts that Home Assistant cannot discover: placement, intended use,
room conventions and external programs. They never change HA entities or devices.

## Add context to a lamp or phone

Open Devices & sensors and find the entity. Highlight it with the arrow keys or
click it. Its details appear immediately.

Entity note describes that specific entity or sensor. Device note describes the
physical device linked to the entity. Room note describes its assigned area. A
missing device/area link is reported rather than invented.

Write the description, then choose Save note or press Ctrl-S. For example:
"Behind the television. Use only as background lighting."

## General household context

Open Notes, then General notes. This is the original notes.md text, preserved
from earlier versions. It is useful for household-wide rules and external systems.
Object descriptions belong in the separate attached notes, not in a giant mixed
text document.

Notes also lists all attached notes. Add note lets you choose an entity, device
or area from the latest snapshot. Edit note opens the selected record. An empty
saved note removes that record; Delete note asks for confirmation.

## What the chat receives

Create a NEW export after saving notes. Existing exports are historical snapshots
and are never rewritten by editing a note.

user-notes.md contains general context and sections labeled with exact target IDs.
annotations.json contains typed targets (entity/device/area), IDs, note text and
whether each target was found in this snapshot. Both are included in TXT and ZIP.
Descriptions are user-provided, not automatically verified facts. Missing targets
are kept but clearly marked; the exporter never guesses a replacement.

If you rename an entity, edit its old note and attach it to the new ID yourself.
No automatic reassigning based on a similar name is attempted.

## Saving and privacy

Unsaved text remains in memory when switching pages in this session. The status
bar shows pending note drafts. Quitting asks for confirmation when drafts exist.
Ctrl-S saves the currently open note. Drafts do NOT enter exports and cannot survive
a killed terminal process. Save before closing SSH.

On Linux, global notes are local/notes.md. Attached notes are
local/annotations.json, created only when needed. Both are excluded from Git.
Reset settings keeps both. Uninstall removes them with the other private app data.

Do not put passwords, tokens or sensitive personal information in notes. Known
secrets are masked in exports, but arbitrary notes still need review before sharing.
