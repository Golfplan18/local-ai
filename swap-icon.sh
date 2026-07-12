#!/usr/bin/env bash
# Usage: ./swap-icon.sh [dark|light|amber|teal|blue|warm]

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
WORKSPACE="${ORA_HOME:-$SCRIPT_DIR}"
if [[ ! -d "$WORKSPACE" ]]; then
  echo "ERROR: ORA_HOME is not a directory: $WORKSPACE" >&2
  exit 1
fi
WORKSPACE="$(cd -- "$WORKSPACE" && pwd -P)"

VARIANT="${1:-dark}"
case "$VARIANT" in
  dark|light|amber|teal|blue|warm) ;;
  *)
    echo "Unknown variant '$VARIANT'. Choose: dark light amber teal blue warm" >&2
    exit 2
    ;;
esac

ICON="$WORKSPACE/config/icons/ora-${VARIANT}.icns"
BUNDLE="$WORKSPACE/Ora.app"
RESOURCE_DIR="$BUNDLE/Contents/Resources"
TARGET_ICON="$RESOURCE_DIR/ai.icns"

if [[ ! -d "$RESOURCE_DIR" ]]; then
  echo "ERROR: Ora.app resource directory is missing: $RESOURCE_DIR" >&2
  exit 1
fi
if [[ ! -f "$ICON" ]]; then
  echo "ERROR: Generated icon is missing: $ICON" >&2
  echo "Run: $WORKSPACE/make_icons.py" >&2
  exit 1
fi

cp "$ICON" "$TARGET_ICON"
touch "$BUNDLE"

LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"
if [[ -x "$LSREGISTER" ]]; then
  "$LSREGISTER" -f "$BUNDLE" >/dev/null 2>&1 || true
fi
echo "Ora.app icon set to ora-${VARIANT}"
