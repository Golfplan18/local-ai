#!/bin/bash
# Usage: ./swap-icon.sh [dark|light|amber|teal|blue]
VARIANT="${1:-dark}"
ICON="$HOME/local-ai/config/icons/ai-${VARIANT}.icns"
BUNDLE="$HOME/local-ai/ai.app/Contents/Resources/ai.icns"

if [ ! -f "$ICON" ]; then
  echo "Unknown variant '$VARIANT'. Choose: dark light amber teal blue"
  exit 1
fi

cp "$ICON" "$BUNDLE"
touch "$HOME/local-ai/ai.app"
/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister -f "$HOME/local-ai/ai.app" 2>/dev/null
echo "Icon set to ai-${VARIANT}"
