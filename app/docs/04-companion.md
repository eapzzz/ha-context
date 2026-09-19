# Companion App and phone automation

The exporter reads the phone entities that Home Assistant knows about. It does
not connect directly to the phone or inspect all its private system settings.

Open Devices & sensors, select Companion App only and Apply filters. Search a
phone name or entity ID. Enabled, Disabled and Unavailable are different views.
Phone registrations opens the device-based summary, including inactive duplicate
registrations that may have the same friendly name. Never choose by name alone.

Disabled entities are kept so a future chat knows they exist but cannot assume
that they are usable. A registry entry can be enabled yet unavailable, missing
from live states or stale. The exported snapshot values are not live telemetry.

The name of a notify action can differ from a notify entity ID. Inspect the
services section instead of constructing a notification service from the phone
name. Capabilities and actions in the export are descriptions, never test calls.

To expose another phone sensor, enable it in the Companion App's Manage Sensors,
allow the phone to send an update, and create a fresh export. Sensor update rates,
permissions and delivery constraints depend on the phone and sensor. An exported
setting cannot establish that a notification or alarm command will be delivered.

Reference:
https://companion.home-assistant.io/docs/core/sensors/
