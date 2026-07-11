#!/bin/zsh
# Backlog ingest supervisor — runs the unified ingest repeatedly until the
# input directory drains, sleeping between cycles so subscription
# rate-window resets are absorbed (every stage resumes from its manifest).
#
# Usage: scripts/backlog_ingest_supervisor.sh <input_dir> [max_cycles] [sleep_secs] [--no-chunks]
#
# Pass --no-chunks only for local-Ora session logs whose chunks already
# exist via inline mode (batch emission would double-index them); those
# sessions additionally get marked completed-without-emission in the
# path2 manifest so future full ingests don't sweep them in. Commercial
# exports run the full pipeline.

set -u
cd "$(dirname "$0")/.." || exit 1
PY=/opt/homebrew/bin/python3
LOG=~/ora/data/backlog-ingest.log

INPUT_DIR=${1:?usage: backlog_ingest_supervisor.sh <input_dir> [max_cycles] [sleep_secs] [--no-chunks]}
MAX_CYCLES=${2:-12}
SLEEP_SECS=${3:-1800}
CHUNK_FLAG=""
if [ "${4:-}" = "--no-chunks" ]; then
  CHUNK_FLAG="--no-chunks"
fi

echo "[supervisor] start $(date '+%F %T') input=$INPUT_DIR max_cycles=$MAX_CYCLES chunks=${CHUNK_FLAG:-on}" >> "$LOG"

for i in $(seq 1 "$MAX_CYCLES"); do
  echo "[supervisor] cycle $i $(date '+%F %T')" >> "$LOG"
  "$PY" -m orchestrator.historical.ingest \
      --backend claude-cli --input-dir "$INPUT_DIR" $CHUNK_FLAG >> "$LOG" 2>&1

  PENDING=$(ORA_SUP_INPUT_DIR="$INPUT_DIR" "$PY" - <<'PYEOF'
import os
from orchestrator.historical.cli import (
    DEFAULT_MANIFEST_PATH, enumerate_input_files, load_manifest,
)
input_dir = os.environ["ORA_SUP_INPUT_DIR"]
m = load_manifest(DEFAULT_MANIFEST_PATH)
done = set(m.get("completed_files", {}))
print(sum(1 for f in enumerate_input_files(input_dir) if f not in done))
PYEOF
)
  echo "[supervisor] cycle $i done — cleanup pending: $PENDING" >> "$LOG"
  if [ "$PENDING" -eq 0 ]; then
    break
  fi
  sleep "$SLEEP_SECS"
done

if [ -n "$CHUNK_FLAG" ]; then
  # Mark local-Ora sessions completed-without-emission in the path2
  # manifest (their chunks exist via inline mode).
  "$PY" - <<'PYEOF' >> "$LOG" 2>&1
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
fi

echo "[supervisor] finished $(date '+%F %T')" >> "$LOG"
