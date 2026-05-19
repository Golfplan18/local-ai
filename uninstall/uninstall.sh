#!/usr/bin/env bash
# Ora uninstall — Mac / Linux entry point.
# Thin wrapper that defers to uninstall.py. Pass through any flags
# (--dry-run, --include-models, --include-conversations).
#
# Lives in ~/ora/uninstall/ (own directory) so accidental tab-completion
# in the wrong terminal doesn't surface it alongside install.py.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-/opt/homebrew/bin/python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    PYTHON="python3"
fi

exec "$PYTHON" "$SCRIPT_DIR/uninstall.py" "$@"
