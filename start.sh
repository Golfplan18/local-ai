#!/bin/bash
# Local AI — Start Script
WORKSPACE="$HOME/ora"

# Export a robust Ora root for the whole server process tree. Every
# orchestrator module prefers $ORA_HOME over os.path.expanduser("~/ora"),
# so exporting it here guarantees correct path resolution even if HOME (or
# the passwd-db lookup) is transiently unavailable in a child process.
# Root cause of the stray "~/ora/..." directories: a path helper fell back
# to a literal "~" when expanduser could not resolve HOME (fixed 2026-05-30).
export HOME
export ORA_HOME="$WORKSPACE"

# RAG selection layer (Process 13): wider retrieval + similarity floor +
# relevance fit-gate + dedup, applied to every retrieval lane. The pipeline
# behaves as before without this var. See Book — RAG Architecture Report v2.0
# §"Process 13". Enabled 2026-06-04.
export ORA_RAG_SELECTION=1
export ORA_RAG_FIT_GATE_SLOT=sidebar

# Extraction escalation (Process 14): when a high-trust Step-2 web snippet is
# too thin to carry the needed detail, deep-fetch the full page, chunk it,
# fit-gate the passages, and fold survivors into WEB CONTEXT. Bounded
# (<=3 fetches/turn) + fail-closed. See Book — RAG Architecture Report v2.0
# §"Process 14". Enabled 2026-06-05.
export ORA_WEB_EXTRACTION=1

# Conversation→engram loop: after each session, promote the runtime-extracted,
# quality-gated atomic notes from staging into the vault as engrams (the
# previously-missing final step). See engram_promotion.py + Working — RAG
# Sources and Provenance Rework 2026-06-05 §7. Enabled 2026-06-05.
export ORA_RUNTIME_ENGRAM_PROMOTION=1

# Runtime engram persistence: when promotion writes new Engrams into the vault,
# stage exactly those generated files, commit them, and push the vault repo.
# This keeps the conversation→engram loop from leaving approved notes as
# untracked git files. Enabled 2026-06-17.
export ORA_RUNTIME_ENGRAM_AUTOCOMMIT=1

# Deliverable scrub (Step 8.5): after the gear-4 formatter writes the final
# answer, a deterministic zero-model pass strips any leaked internal pipeline
# scaffolding (stray contract headings, VERDICT: lines, provider/truncation
# error markers). High-precision — only removes exact internal jargon, never
# normal answer content; logs anything stripped to the per-turn
# deliverable-scrub.jsonl trace sidecar. See boot.py::_scrub_pipeline_leaks.
# Enabled 2026-06-05.
export ORA_DELIVERABLE_SCRUB=1

# OpenRouter per-provider latency (the Speed preset's primary speed
# signal): the registry sync pulls time-to-first-token + throughput from
# OpenRouter's public frontend stats API (no key, no credit) and writes
# or_ttft_ms / or_throughput_tps per model, with AA median latency as the
# fallback. The layer is a no-op without this flag, so a break in the
# undocumented endpoint can't wedge the sync. Populates on the next
# registry refresh (Models-pane Refresh / scheduled sync) after restart.
# See sync_model_registry.py::layer_openrouter_stats. Enabled 2026-06-29.
export ORA_OR_STATS=1

# Kill any stale server process
pkill -f "server/server.py" 2>/dev/null
sleep 1

# Find Python: Homebrew (macOS), then system python3
if [ -x "/opt/homebrew/bin/python3" ]; then
  PYTHON="/opt/homebrew/bin/python3"
elif command -v python3 &>/dev/null; then
  PYTHON="python3"
else
  echo "ERROR: python3 not found. Install Python 3.10+ first."
  exit 1
fi

# Start server with meta-layer oversight daemon enabled by default.
# The daemon watches PEDs, corpora, and workflow specs; per CLAUDE.md
# Meta-Layer Oversight Subsystem. Pass --no-oversight to disable.
if [[ " $* " == *" --no-oversight "* ]]; then
  CLEAN_ARGS=$(echo " $@ " | sed 's/ --no-oversight / /g' | sed 's/^ *//;s/ *$//')
  "$PYTHON" "$WORKSPACE/server/server.py" $CLEAN_ARGS &
else
  "$PYTHON" "$WORKSPACE/server/server.py" --oversight "$@" &
fi

# Wait up to 30s for server on any port 5000-5010
for i in $(seq 1 30); do
  for port in $(seq 5000 5010); do
    if curl -sf "http://localhost:$port/health" >/dev/null 2>&1; then
      echo "Local AI ready at http://localhost:$port"
      # Open browser (cross-platform)
      if command -v open &>/dev/null; then
        open "http://localhost:$port"
      elif command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:$port"
      elif command -v start &>/dev/null; then
        start "http://localhost:$port"
      fi
      exit 0
    fi
  done
  sleep 1
done

echo "ERROR: Server did not start. Run: $PYTHON $WORKSPACE/server/server.py"
exit 1
