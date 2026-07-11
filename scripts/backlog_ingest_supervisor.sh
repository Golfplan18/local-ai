#!/bin/zsh
# Backlog ingest supervisor — runs the unified ingest repeatedly until the
# input directory drains, sleeping between cycles so subscription
# rate-window resets are absorbed (every stage resumes from its manifest).
#
# Usage: scripts/backlog_ingest_supervisor.sh [max_cycles] [sleep_secs]
#
# The run uses --no-chunks: the current backlog is local-Ora session logs
# whose chunks already exist via inline mode — batch chunk emission would
# double-index them. After the cleanup stage converges, the new sessions
# are marked completed-without-emission in the path2 manifest so future
# full ingests don't sweep them in either.

set -u
cd "$(dirname "$0")/.." || exit 1
PY=/opt/homebrew/bin/python3
LOG=~/ora/data/backlog-ingest.log
MAX_CYCLES=${1:-12}
SLEEP_SECS=${2:-1800}

echo "[supervisor] start $(date '+%F %T') max_cycles=$MAX_CYCLES" >> "$LOG"

for i in $(seq 1 "$MAX_CYCLES"); do
  echo "[supervisor] cycle $i $(date '+%F %T')" >> "$LOG"
  "$PY" -m orchestrator.historical.ingest \
      --backend claude-cli --no-chunks >> "$LOG" 2>&1

  PENDING=$("$PY" - <<'PYEOF'
from orchestrator.historical.cli import (
    DEFAULT_INPUT_DIR, DEFAULT_MANIFEST_PATH,
    enumerate_input_files, load_manifest,
)
m = load_manifest(DEFAULT_MANIFEST_PATH)
done = set(m.get("completed_files", {}))
print(sum(1 for f in enumerate_input_files(DEFAULT_INPUT_DIR) if f not in done))
PYEOF
)
  echo "[supervisor] cycle $i done — cleanup pending: $PENDING" >> "$LOG"
  if [ "$PENDING" -eq 0 ]; then
    break
  fi
  sleep "$SLEEP_SECS"
done

# Mark the newly ingested local-Ora sessions completed-without-emission in
# the path2 manifest (their chunks exist via inline mode).
"$PY" - <<'PYEOF' >> "$LOG" 2>&1
import json
from datetime import datetime
from pathlib import Path
from orchestrator.historical.chain_detector import derive_session_id
from orchestrator.historical.cleaned_pair_reader import load_cleaned_pair
from orchestrator.historical.path2_cli import (
    DEFAULT_MANIFEST_PATH, load_manifest, save_manifest,
)

archive = Path("/Users/oracle/Documents/Commercial AI archives")
manifest = load_manifest(DEFAULT_MANIFEST_PATH)
completed = manifest.setdefault("completed_sessions", {})
stamp = datetime.now().isoformat(timespec="seconds")
added = 0
for p in archive.glob("*.md"):
    try:
        cp = load_cleaned_pair(str(p))
    except Exception:
        continue
    platform = (cp.source_platform or "").lower()
    if platform not in ("ora-local", "local", "local-ora"):
        continue
    if cp.source_chat in completed:
        continue
    completed[cp.source_chat] = {
        "completed_at": stamp,
        "session_id": derive_session_id(cp.source_chat),
        "suppressed": "inline-mode chunks already exist",
    }
    added += 1
save_manifest(manifest, DEFAULT_MANIFEST_PATH)
print(f"[supervisor] suppressed chunk emission for {added} local-Ora sessions")
PYEOF

echo "[supervisor] finished $(date '+%F %T')" >> "$LOG"
