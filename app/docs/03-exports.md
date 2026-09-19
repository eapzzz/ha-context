# Reading an export

## Result status

Complete means the selected scope was collected without recorded failures.
API only is a deliberately narrower scope; it excludes local YAML files.
Partial means useful data exists, but some requested sections failed or were
omitted because of limits. Failed means no successful snapshot was reported.
Canceled means the worker was stopped. A canceled export is never listed as
complete. Interrupted temporary folders remain hidden rather than masquerading
as valid history; they belong to local/ and are removed on uninstall.

A read is not transactionally atomic: sensors and files can change while it runs.
An empty successfully read list is different from an unavailable list.
Intentional exclusions, such as caches and backups, are not counted as warnings.
Repeated failures with the same cause are grouped in issues.json. Per-section
coverage remains available. A failed WebSocket handshake is attempted once per
export, not once per device. Local registry files can provide a fallback.

## Files

summary.json: scope, timestamp, counts and result.
coverage.json: independent status of each read.
manifest.json: provenance, omissions, warnings, sizes and SHA-256 checksums.
entities.json: joined states and entity/device/area data, including disabled IDs.
companion.json: phone registration groups and enabled/disabled/unavailable sensors.
registries/: device, entity, area, floor and label registries where available.
services.json: action descriptions and parameter schemas, NOT actions that ran.
config/: sanitized local configuration, helpers, blueprints and selected metadata.
include_references.json: local include dependencies, missing and external targets.
user-notes.md: your descriptions, separate from automatically collected facts.

Only allowlisted configuration is read from .storage. Authentication stores,
credential-bearing integration options, private keys, backups, history databases,
logs, camera images and recordings are excluded. secrets.yaml is read in memory
only to recognize literal secrets elsewhere, and is never included in a snapshot.
!include, !env_var and !secret remain symbolic; the collector does not execute
YAML constructors or resolve environment variables. Arbitrary includes outside
the selected config root and symlinks are not followed.

Limits: 8 MiB per config file, 64 MiB total configuration, 64 MiB API response.
Size and parse omissions appear in coverage. No snapshot claims that the export
contains all possible historical, external-app or physical information.

## History and comparisons

A comparison shows added/removed entities and changed registry metadata, ignoring
transient state readings. It also compares sanitized configuration file hashes.
Retention runs after a new snapshot is written; 0 keeps all. Only identified
ha-context snapshot directories are candidates for deletion.

Save filtered view writes selected entity data, not a full configuration export.
It is explicitly labeled with its source snapshot and narrower scope.


## Export stopped

A failed export has a dedicated error screen with **Retry export**,
**Connection settings**, and **Back to export**. It is not a successful snapshot.
Earlier snapshots and saved settings/notes are not reset. Authorization errors
are not evidence that a container was deleted. Cancellation targets the export
worker's own process group, not the terminal application or the HA container.
