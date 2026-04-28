#!/bin/bash
# run-maintenance.sh — Periodic maintenance runner (Phase 12)
# Accepts frequency argument: "weekly" or "monthly"
# Run via cron or manually.
#
# Cron schedule:
#   Weekly: Sunday 2 AM
#   0 2 * * 0 /Users/oracle/ora/scripts/run-maintenance.sh weekly
#
#   Monthly: 1st of month 3 AM
#   0 3 1 * * /Users/oracle/ora/scripts/run-maintenance.sh monthly

set -uo pipefail

ORA_DIR="${HOME}/ora"
LOG_DIR="${ORA_DIR}/logs"

# Find Python: Homebrew (macOS), then system python3
if [ -x "/opt/homebrew/bin/python3" ]; then
    PYTHON="/opt/homebrew/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    echo "ERROR: python3 not found. Install Python 3.10+ first." >&2
    exit 1
fi

FREQUENCY="${1:-weekly}"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
LOG_FILE="${LOG_DIR}/maintenance-$(date '+%Y-%m-%d').log"

mkdir -p "$LOG_DIR"

log() {
    echo "[${TIMESTAMP}] $1" | tee -a "$LOG_FILE"
}

log "=== Periodic Maintenance Start (${FREQUENCY}) ==="

# Validate frequency argument
if [[ "$FREQUENCY" != "weekly" && "$FREQUENCY" != "monthly" ]]; then
    log "ERROR: Invalid frequency '${FREQUENCY}'. Use 'weekly' or 'monthly'."
    exit 1
fi

# Verify Python is callable
if ! "$PYTHON" --version >/dev/null 2>&1; then
    log "ERROR: Python not callable: ${PYTHON}"
    exit 1
fi

# Check Ollama (needed for Pass 2 relationship discovery)
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    log "Ollama: responding"
else
    log "WARNING: Ollama not responding — Pass 2 model calls will use heuristic fallback"
fi

# Run the maintenance module
log "Running ${FREQUENCY} maintenance tasks..."
cd "$ORA_DIR"

$PYTHON -m orchestrator.tools.periodic_maintenance "$FREQUENCY" 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

if [ $EXIT_CODE -eq 0 ]; then
    log "=== Maintenance Complete (success) ==="
else
    log "=== Maintenance Complete (with failures — exit code ${EXIT_CODE}) ==="
fi

# Also run the existing RAG manifest maintenance
log "Running RAG manifest maintenance..."
if [ -f "${ORA_DIR}/scripts/maintain-rag-manifest.sh" ]; then
    bash "${ORA_DIR}/scripts/maintain-rag-manifest.sh" >> "$LOG_FILE" 2>&1
    log "RAG manifest maintenance complete"
else
    log "WARNING: maintain-rag-manifest.sh not found"
fi

log "=== All Maintenance Complete ==="
exit $EXIT_CODE
