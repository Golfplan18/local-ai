#!/bin/bash
# Start the Local AI chat server

WORKSPACE="$HOME/local-ai"

# Kill any existing server
pkill -f "server.py" 2>/dev/null
sleep 1

# Start server in background
python3 "$WORKSPACE/server/server.py" &
SERVER_PID=$!

# Wait for server to be ready (up to 30s)
for i in $(seq 1 30); do
  if curl -sf http://localhost:5000/health >/dev/null 2>&1; then
    echo "Server ready at http://localhost:5000"
    open http://localhost:5000
    exit 0
  fi
  sleep 1
done

echo "ERROR: Server did not start within 30 seconds."
echo "Check for errors: python3 $WORKSPACE/server/server.py"
exit 1
