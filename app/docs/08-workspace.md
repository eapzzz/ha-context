# Workspace navigation

The workspace uses a scrollable left menu, not a row of seven tabs.

| Planned area | Actual entry / route |
| --- | --- |
| Overview | Overview |
| Export | Create export |
| Devices & sensors | Devices & sensors |
| Diagnostics | Diagnostics |
| Privacy & preview | Settings → Privacy & retention; Export history → Review |
| Exports | Export history |
| Settings & maintenance | Separate Settings and Maintenance entries |

Notes and Documentation are additional entries. Use Tab / Shift-Tab to move,
Enter to choose, and F1 for documentation. On shorter terminals the menu scrolls.
The full workspace is available after completing onboarding.

## What the current screens actually do

Overview shows the saved address/source and the latest snapshot summary. It does
not continuously monitor connection health. Diagnostics → Run checks performs
explicit REST, WebSocket and configuration-access checks.

Create export collects a full snapshot in the configured source scope. Devices &
sensors → Save filtered view writes a selected-entity text view; it is NOT a full
room/device-scoped configuration export. There is no full room-scoped export yet.

Devices & sensors reads the latest snapshot, not live data. Search can match IDs,
platform, area and device fields. Companion App only filters mobile-app entities;
Phone registrations opens the device-registration inventory. Disabled, unavailable
and enabled are different conditions.

Export history lists snapshots. Review opens the sections of a selected snapshot;
Compare compares it with the newest other snapshot (not an arbitrary pair picker).
The text preview is capped at 400,000 characters per section; saved exports are not
truncated by that preview limit. Full TXT + ZIP remains on the server.

Privacy & retention edits masking preferences and retention. The preview can show
privacy.txt and issues.json. There is no separate interactive table of every
masked value. Known credentials are always masked; optional network masking can
also mask SSID/BSSID/IP readings. Redaction remains best effort.

Maintenance shows Reset settings only when settings exist, and Review old files
only after recognized old exporter files are found. Reset preserves notes and
exports. Deletion is a separate confirmed action. HA OS uses Supervisor controls
for installation removal; Linux has an in-app uninstall action.
