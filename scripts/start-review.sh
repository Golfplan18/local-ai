#!/bin/bash
# start-review.sh — Launch the human review queue interface
# Standalone Flask app on localhost:5005 (Dracula-themed dark UI)
# Reviews extraction pipeline output from ~/ora/data/review-queue/

WORKSPACE="$HOME/ora"

# Find Python: Homebrew (macOS), then system python3
if [ -x "/opt/homebrew/bin/python3" ]; then
    PYTHON="/opt/homebrew/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    echo "ERROR: python3 not found. Install Python 3.10+ first." >&2
    exit 1
fi

# Create review queue directory if needed
mkdir -p "$WORKSPACE/data/review-queue"

echo "Starting Review Queue at http://localhost:5005"
"$PYTHON" "$WORKSPACE/server/review.py" "$@"
