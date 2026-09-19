#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
chmod u+x "$ROOT/ha-context"
exec "$ROOT/ha-context" "$@"
