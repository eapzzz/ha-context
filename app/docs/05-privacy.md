# Privacy and sharing

The export is private context, not an anonymous dataset. Review before sharing.
Credentials, private location fields/readings, email addresses and password-mode
input values are masked best-effort. Entity IDs, names, area structure, schedules
and presence may remain. No filter can remove every possible secret from
arbitrary custom integrations, scripts, templates, comments or user notes.

Balanced privacy keeps network identifiers useful for Wi-Fi-based conditions.
Additional network masking masks IPv4/MAC patterns, recognized SSID/BSSID/IP
readings and network metadata fields. This is not a complete network-anonymization
guarantee: arbitrary hostnames, URLs, IPv6 addresses and values embedded in custom
text can remain. Review them. Network placeholders must not be pasted into rules.

Short credentials are masked in credential fields. They are NOT learned as global
text substitutions: a PIN of 3 must not erase every sensor value of 3. Known long
literal secret strings can be replaced across files. Storage metadata keys and
service schemas are not treated as passwords. Actual sensor IDs remain usable.

On Linux the token is stored locally with permissions 600, not encrypted at rest.
On HA OS the managed Supervisor token is read from the environment, never written
to the app's settings or exported. Resetting local settings does not revoke a
personal token on the HA server. Revoke an unused token from your HA profile.

Source sharing is separate from context sharing. Create shareable source uses an
explicit code manifest and excludes local/, .git/, .venv/ and bundled runtime
libraries. Never upload your whole configured installation folder to GitHub.

Hashes detect inconsistent/corrupted files, not who created a package. Install
updates only from a trusted source. Git updates preserve local/ but execute code
from your configured repository when you restart the application.
