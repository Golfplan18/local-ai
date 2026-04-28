# Framework — Periodic Maintenance

## Purpose

Four scheduled tasks — only work that genuinely requires full-vault scans or has no runtime trigger. Per the Runtime Principle: if a process can run at runtime, it must run at runtime. Scheduled maintenance exists only for tasks where runtime execution is impossible.

## What runs at runtime (not here)

These all execute in `runtime_pipeline.py` after every session or at server startup:

| Task | Where | Why runtime is possible |
|------|-------|------------------------|
| Pass 2 relationships | runtime_pipeline.py step 12 | Query new note against ChromaDB — O(1) per note, not O(n²) |
| Convergence analysis | deduplication.py | Check arrival_history count at merge time — one integer comparison |
| Index regeneration | server.py startup | One directory listing comparison at boot |
| RAG manifest freshness | server.py startup | One mtime comparison + conditional recompile at boot |

## What runs on schedule (this framework)

### Weekly: Task 1 — Orphan Relationship Cleanup

**Why this can't run at runtime:** Deletions and renames happen in Obsidian, not through the pipeline. There is no runtime hook for external vault edits.

**What:** Scan all relationship targets across all notes. Remove references to deleted or consolidated notes. Rebuild graph index.

**Steps:**
1. `RelationshipGraph.find_orphan_targets()` — identify targets pointing to non-existent files
2. For each orphan: check if the target was renamed (fuzzy match against current vault titles)
3. If renamed: update reference. If deleted: remove relationship entry.
4. `RelationshipGraph.remove_orphans()` for remaining
5. Rebuild graph with `RelationshipGraph.build_from_vault()`

**Alert condition:** More than 10 orphans found (may indicate bulk vault reorganization).

### Monthly: Task 2 — Vault Health Audit (includes Provenance Audit)

**Why this can't run at runtime:** Needs the complete vault picture. No per-session trigger for "scan every note for missing properties."

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

### Monthly: Task 3 — Relationship Graph Density

**Why this can't run at runtime:** Aggregate statistics require the full picture. Could also be triggered on-demand.

**Metrics:**
- Average relationships per note
- Percentage of notes with zero relationships
- Percentage of notes with 10+ relationships
- Total unique relationship types in use
- Most connected notes (top 10)
- Month-over-month comparison from `~/ora/data/graph-density-YYYY-MM.json`

**Alert condition:** Density declined compared to previous month.

### Monthly: Task 4 — Archive and Cleanup

**Why this can't run at runtime:** No runtime trigger for "is this log 30 days old." Classic housekeeping.

**Actions:**
- Review queue entries older than 90 days → move to `~/ora/data/archive/`
- Compress log files older than 30 days (gzip)
- Remove empty directories in data/

## Execution Model

- Each task runs independently. A task failure is logged but does not halt subsequent tasks.
- All tasks log to `~/ora/logs/maintenance-YYYY-MM-DD.log`.
- Alert summary generated at end of each run.
- Callable from shell (`run-maintenance.sh weekly|monthly`) and from Python.

## Cron Schedule

```
# Weekly: Sunday 2 AM
0 2 * * 0 /Users/oracle/ora/scripts/run-maintenance.sh weekly >> /Users/oracle/ora/logs/maintenance-cron.log 2>&1

# Monthly: 1st of month 3 AM
0 3 1 * * /Users/oracle/ora/scripts/run-maintenance.sh monthly >> /Users/oracle/ora/logs/maintenance-cron.log 2>&1
```

## Dependencies

- Phase 7 (Relationship Architecture) — for orphan cleanup
- ChromaDB must be populated (for graph density reporting)
