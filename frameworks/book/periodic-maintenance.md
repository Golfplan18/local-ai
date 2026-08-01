# Framework — Periodic Maintenance

## Display Name
Periodic Maintenance

## Display Description
Four explicit historical-audit commands retained after production maintenance moved to exact events and deadlines. None runs on a clock.


## Purpose

Four corpus-scale diagnostics remain callable as explicit campaigns. G1.10 established that new orphan, metadata, graph, and lifecycle work has runtime triggers; a full-vault pass is therefore a historical-debt or reporting campaign, not scheduled maintenance.

## What runs at runtime (not here)

These all execute in `runtime_pipeline.py` after every session or at server startup:

| Task | Where | Why runtime is possible |
|------|-------|------------------------|
| Pass 2 relationships | runtime_pipeline.py step 12 | Query new note against ChromaDB — O(1) per note, not O(n²) |
| Convergence analysis | deduplication.py | Check arrival_history count at merge time — one integer comparison |
| Index regeneration | server.py startup | One directory listing comparison at boot |
| RAG manifest freshness | server.py startup | One mtime comparison + conditional recompile at boot |

## What runs only as an explicit campaign (this framework)

### Task 1 — Orphan Relationship Cleanup

**Current trigger:** OS file events now observe Obsidian deletions and renames. The full scan exists only to reconcile historical debt or verify event coverage.

**What:** Scan all relationship targets across all notes. Remove references to deleted or consolidated notes. Rebuild graph index.

**Steps:**
1. `RelationshipGraph.find_orphan_targets()` — identify targets pointing to non-existent files
2. For each orphan: check if the target was renamed (fuzzy match against current vault titles)
3. If renamed: update reference. If deleted: remove relationship entry.
4. `RelationshipGraph.remove_orphans()` for remaining
5. Rebuild graph with `RelationshipGraph.build_from_vault()`

**Alert condition:** More than 10 orphans found (may indicate bulk vault reorganization).

### Task 2 — Vault Health Audit (includes Provenance Audit)

**Current trigger:** note-write validation prevents new property debt. The complete-vault picture is an explicitly requested report.

**What:** Comprehensive vault scan producing a health report with action items. Provenance audit (previously separate) is folded in — stale incubators are found during the same scan.

**Checks:**
- Notes with empty `relationships` arrays
- Notes with `status: incubator` or `provenance: incubator` older than 30 days (provenance audit)
- Notes with unfilled `definitions_required`
- Orphaned extractions in staging whose source sessions can't be found
- Notes missing required YAML properties (`type`, `tags`)

**Actions:**
- Queue stale incubators for review (copy to `~/ora/data/review-queue/`)
- Generate health report at `~/ora/data/vault-health-YYYY-MM.md`

**Alert conditions:**
- Any check finds issues requiring attention
- More than 20 stale incubators (review queue growing)

### Task 3 — Relationship Graph Density

**Current trigger:** graph mutations provide incremental signals; exact aggregate reporting is on demand.

**Metrics:**
- Average relationships per note
- Percentage of notes with zero relationships
- Percentage of notes with 10+ relationships
- Total unique relationship types in use
- Most connected notes (top 10)
- Month-over-month comparison from `~/ora/data/graph-density-YYYY-MM.json`

**Alert condition:** Density declined compared to previous month.

### Task 4 — Archive and Cleanup

**Current trigger:** output creation binds lifecycle and any expiration deadline; append events enforce size thresholds. This command is recovery/audit-only.

**Actions:**
- Review queue entries older than 90 days → move to `~/ora/data/archive/`
- Compress log files older than 30 days (gzip)
- Remove empty directories in data/

## Execution Model

- Each task runs independently. A task failure is logged but does not halt subsequent tasks.
- All tasks log to `~/ora/logs/maintenance-YYYY-MM-DD.log`.
- Alert summary generated at end of each run.
- Callable from Python (`orchestrator/tools/periodic_maintenance.py`) only through an explicit campaign.

## Scheduling

Production scheduling is retired. Defaults for all four tasks are `off` in
`Reference — Ora Periodic Maintenance.md`. `daily_note` uses one persisted
calendar deadline; News and Engram work uses exact artifact-write events. The
legacy scheduler can report or run a deliberately enabled campaign when called
directly, but the oversight daemon never starts it and errors never arm a clock
fallback.

## Dependencies

- Phase 7 (Relationship Architecture) — for orphan cleanup
- ChromaDB must be populated (for graph density reporting)
