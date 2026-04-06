#!/bin/bash
# Start the Local AI chat server

WORKSPACE="$HOME/local-ai"

# Kill any existing Local AI server (but not other python processes)
pkill -f "server/server.py" 2>/dev/null
sleep 1

# Use Homebrew Python (has Flask, mlx-lm, chromadb, etc.)
PYTHON="/opt/homebrew/bin/python3"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi

# Start server in background (optionally with --scheduler)
"$PYTHON" "$WORKSPACE/server/server.py" "$@" &
SERVER_PID=$!

# Wait for server to be ready on any port 5000-5010 (up to 30s)
for i in $(seq 1 30); do
  for port in $(seq 5000 5010); do
    if curl -sf "http://localhost:$port/health" >/dev/null 2>&1; then
      echo "Server ready at http://localhost:$port (PID: $SERVER_PID)"
      open "http://localhost:$port"
      exit 0
    fi
  done
  sleep 1
done

echo "ERROR: Server did not start within 30 seconds."
echo "Check for errors: $PYTHON $WORKSPACE/server/server.py"
exit 1
