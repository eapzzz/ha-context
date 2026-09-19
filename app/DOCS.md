# ha-context

Start the app, then **Open web UI**. The first screen is onboarding. The connection
and read-only configuration mount are detected; no personal token is required.

The **Files** link opens downloads in a separate browser tab. Keep the terminal
tab open during exports. **Documentation** is available in the interface and in
the web header. Only one terminal session is active at a time.

No port is published. Do not disable protection mode. The configuration mount is
read-only. Exports and preferences live under the app's private `/data/local`.

Reset is inside Maintenance. Uninstall/update is handled by Home Assistant's app
management, not a privileged shell. Removing this app does not remove HA config.

This initial HA OS package is **experimental**: its gateway, authorization guards
and downloads have local automated tests, but it has not yet been run on a real
Supervisor instance. Report deployment issues without tokens or raw exports.
