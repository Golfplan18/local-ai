#!/bin/bash
pkill -f "server/server.py" 2>/dev/null && echo "Server stopped." || echo "Server was not running."
