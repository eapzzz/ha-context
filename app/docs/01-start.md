# Start here

ha-context reads your Home Assistant and creates a context snapshot for a chat.
It does not use an AI model, call MCP tools or send the snapshot anywhere.
It never turns on lights, sends phone commands, executes templates or reloads HA.

## First launch

Run the installer once. The Welcome screen guides you through connection,
configuration source, privacy, notes and a final review. Save & open finishes it.
On Linux the program offers to install the single command: ha-context.
All subsequent configuration, diagnostics and maintenance are in the interface.

Tab and Shift-Tab move between controls. Enter activates buttons. Space chooses
checkboxes and radio options. Arrow keys immediately select list entries. Mouse is supported.
F6 switches between menu and content; Esc returns or cancels. Ctrl-S saves notes.
F1 opens this guide. F2 returns home. Ctrl-Q exits. Ctrl-C cancels an export.
Text panels support search: focus the text, press Ctrl-F, type and press Enter.
Long screens scroll to the focused control. Use a terminal of at least 80 x 24.

## Where the files live

Linux: the folder containing this program, normally ~/ha-context.
Your settings, token, notes, exports and diagnostics live in its local/ subfolder.
There is only one external command shortcut. No shell configuration is rewritten.
A portable release includes Python libraries in .vendor/; a source install uses
.venv/. These folders belong to this installation and are not your HA environment.

HA OS: code is in the app image, persistent private data is in /data/local.
The Supervisor manages the image and its data. The HA config mount is read-only.

## Daily use

Open ha-context, choose Create export and then Create snapshot. Review coverage
and the privacy report. Upload ha-context.txt to your chat. ZIP contains the
same sections, but some chat modes do not accept ZIP archives. Large TXT files
also receive numbered parts that concatenate to the same full text.

A chat sees a snapshot, not a live connection. Export again after changing devices,
phone sensors, entity names or automations. A snapshot cannot prove future behavior.
