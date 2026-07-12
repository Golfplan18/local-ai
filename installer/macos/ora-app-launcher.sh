#!/usr/bin/env bash
# Tracked source for Ora.app/Contents/MacOS/ai (the generated .app is ignored).
# The launchd installer copies this shim into an existing local Ora.app bundle.

set -u
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# Ora.app lives directly under the checkout. Derive that checkout so an app
# installed with `--ora-home /custom/path` does not silently fall back to
# ~/ora when Finder supplies no ORA_HOME environment variable.
WORKSPACE="${ORA_HOME:-$(cd -- "$SCRIPT_DIR/../../.." && pwd -P)}"
exec "$WORKSPACE/start.sh"
