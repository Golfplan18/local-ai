#!/bin/bash
# Local AI — Start Script
WORKSPACE="$HOME/local-ai"

# Kill any stale server process
pkill -f "server/server.py" 2>/dev/null
sleep 1

# Use Homebrew Python (has Flask, mlx-lm, chromadb, etc.)
PYTHON="/opt/homebrew/bin/python3"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi

# Start server
"$PYTHON" "$WORKSPACE/server/server.py" &

# Wait up to 30s for server to respond
for i in $(seq 1 30); do
  if curl -sf http://localhost:5000/health >/dev/null 2>&1; then
    echo "Local AI ready at http://localhost:5000"
    open http://localhost:5000
    exit 0
  fi
  sleep 1
done

echo "ERROR: Server did not start. Run: python3 ~/local-ai/server/server.py"
exit 1
