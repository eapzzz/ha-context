# Connection and deployment

## Linux / Docker / Podman

Detect local HA inspects running containers by name and image. It does not scan
your LAN or send a token to guessed servers. Multiple containers require a choice.
The exporter remembers that choice, not a hardcoded Cosmos or Docker network name.
If local-address refresh is enabled, the chosen container's current published
port or single bridge address is inspected before every export. Multiple bridge
addresses require an explicit URL rather than an arbitrary choice.

Authorize Docker invokes the system sudo prompt. Your password is not saved by
ha-context. Only container inspection and read-only commands inside the selected
container use sudo. The application and its files remain on your normal account.
A system-wide command shortcut may also request authorization once.

## Token

HA → User profile → Security → Long-Lived Access Tokens → Create token.
Use a dedicated token for this exporter. Some registry/configuration reads need
an administrator account. The tool only implements reads, but the token itself
may have broader privileges. Do not paste it into a chat or source repository.
The saved token has mode 600 inside a mode-700 local folder; it is not encrypted.

## Home Assistant OS

Install ha-context as an HA app (formerly called an add-on) from its repository.
Open its web interface. Onboarding detects the managed environment and uses the
Supervisor's internal HA API proxy. No personal token is saved. Configuration
is mounted at /homeassistant_config read-only. Ingress performs authentication.
The app exposes no public port and does not require protection mode to be disabled.

You can also run ha-context on another Linux computer and connect to HA OS by URL
and token. Select API only unless a readable configuration folder is available.
That mode cannot magically read HA OS files across the network. Missing local
configuration is explicitly recorded, never represented as a complete backup.

## Direct address and Cloudflare

A reverse proxy can accept ordinary REST calls while rejecting a WebSocket
handshake. Diagnostics reports the HTTP status without response bodies or cookies.
The client does not add a browser Origin header and does not follow redirects
with your token. TLS verification stays enabled. A proxy error is not proof that
the HA token or physical devices are broken. Choose a trusted reachable local
address when appropriate; the app never changes your tunnel configuration.

Always verify that the selected folder/container and API URL describe the SAME
Home Assistant instance. The paths and selected source are included in the report.

References:
https://developers.home-assistant.io/docs/api/rest/
https://developers.home-assistant.io/docs/api/websocket/
https://developers.home-assistant.io/docs/apps/communication/


## Docker works in checks, but export asks for authentication

In 2.1.0 the export worker created a new terminal session. That discarded the
per-terminal sudo authentication used by Diagnostics. Version 2.1.1 keeps the
same terminal session and uses a separate process group only for cancellation.

Run ha-context as your usual SSH user. Choose **Local Docker / Podman container**
and your Home Assistant container. **Authorize Docker** uses the system's sudo
prompt when required. Finish the settings flow with **Save & open**, then export.
Do not use a protected host folder as a workaround. The app neither stores your
sudo password nor changes sudoers, Docker permissions or Home Assistant files.
Unusual sudo policies (for example per-parent-process timestamps) can still
require different authorization; failures are reported, not silently bypassed.

## Permission denied versus missing configuration

**Readable configuration folder** requires this host user's read and directory
traversal permissions. `/config` inside a container is not `/config` on the host.
The program now checks file metadata and opens configuration.yaml without reading
its contents during validation. Permission denial is reported separately from a
missing file. For a Docker installation, prefer container mode and authorized
Docker commands instead of changing Home Assistant ownership or permissions.
