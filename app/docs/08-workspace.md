# Workspace navigation

The application has a fixed full-screen workspace. The menu, header and footer
remain in the same places. The content changes without resizing the background.
Resize the terminal to change the workspace size; 80 x 24 is the minimum supported.

## Move around

F6 switches focus between the current page and the menu. In the menu, use Up/Down
to choose a page and Enter or Right to open it. Clicking a menu entry opens it.
The active page stays highlighted. Tab and Shift-Tab cycle through controls.

Esc returns to the menu. In a note editor it goes back without losing the in-memory
draft; in a confirmation it cancels that action. F1 opens documentation, F2 opens
Overview, and Ctrl-Q exits. Ctrl-S saves the currently open context note.

Lists have a single selection: moving the highlight selects that item. There is
no separate checked item that can disagree with the highlight. Mouse clicks,
Home/End and Page Up/Down use the same selection.

## Documentation and previews

Click a chapter or move with arrow keys to open it immediately. Previous and Next
are available below the reader. Ctrl-F starts a text search, even from the chapter
list. Enter accepts a search, Esc cancels it. The prose reflows when resized.
Export previews also open their selected section immediately.

## Devices and notes

Search filters as you type. Phone only limits results to Companion App. The
status button cycles All entries, Enabled, Disabled and Unavailable; Left/Right
or Enter changes it. Apply filters is also available. Selecting an entity updates
its details without another button. Filters and selection survive editing a note.

Entity note, Device note and Room note attach private context to exact IDs.
Notes is the central list; General notes contains household-wide context.
See the Context notes chapter for what is included in exports.

## Screen names and limits

Overview is the last snapshot summary, not a continuous connection-health monitor.
Diagnostics runs explicit REST, WebSocket and configuration access checks.

Create export collects the full selected source scope. Save filtered view writes
only a filtered list of entities, not a room/device-scoped configuration export.

Export history lists snapshots. Review displays files. Compare uses the newest
other snapshot; there is no arbitrary pair picker. Preview shows at most 400,000
characters per section. Saved TXT/ZIP are not truncated by this preview limit.

Privacy preferences are under Settings, Privacy & retention. File previews live
under Export history, Review. Settings and Maintenance are separate menu entries.
Known credentials are masked best-effort, not guaranteed for arbitrary content.

Maintenance offers Review old files ONLY when recognized older files exist.
Reset keeps notes and exports. Uninstall is separately confirmed. HA OS still uses
Supervisor to manage image removal and remains experimental in this project.
