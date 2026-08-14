# Chunk 0 Design Addendum — Trace Manifest

*Design-gate packet for Codex. Parent plan: `~/Documents/vault/Working — Trace Walk and Earned Autonomy Build Plan.md` (approved 2026-07-09, three conditions). This addendum covers Chunk 0 only. Code anchors verified against ora HEAD `a0c7e0be` on 2026-07-09 by a read-only scout; the concurrent-session caveat applies (re-verify anchors at implementation worktree creation).*

## Scope

One new file per turn (`trace-manifest.json` in the turn directory), the conversation-side `trace_ref` join, and honest finalization for every turn path — including short-circuits (Codex condition 1). **Out of scope, deferred to Chunk 1:** sweeper pin *enforcement* (the schema carries `retention_state` now; the sweeper change lands with Chunk 1), framework child traces (schema reserves `parent_trace_ref`/`child_trace_refs` now), any viewer.

## Verified ground truth the design rests on

- `start_trace` (pipeline_trace.py:75-147) writes exactly one file, `metadata.json`, and is the only guaranteed write. `write_step_health` (:292-317) fires only inside run_gear3/run_gear4. **The turn directory is never explicitly closed on any path.**
- `_pipeline_stream` (server.py, start_trace hoisted to :3078-3088) has **~19 distinct return sites and no common exit point**. Path groups by what the turn dir contains at return:
  - **metadata.json only:** risk-gate sticky reply (:3134), risk continuation (:3141), runtime slash-command (:3164), no-endpoint error (:3171), resolution-chain continuation (:3191/:3193), framework-elicitation continuation (:3215/:3217), framework command (:3297/:3323/:3332), framework elicitation start (:3338/:3349).
  - **metadata + step1 files, no step2/step-health:** manual-override pending-clarification (:3529), gear-1/2 bypass via `_direct_stream` (:3565 — `_direct_stream` is not passed trace_dir and sets `tool_events.set_turn_context(trace_dir=None)` at :3738), pre-routing question gate (:3606), legacy clarification gate (:3638).
  - **Finalized (step-health + cost-summary):** full pipeline (:3666, `finally` at :3656-3666) and manual-clarification continuation (:3267, `finally` at :3259-3266 — note this path has **no step1 files**: it reuses a stored step1 dict).
- Clarification resume/skip endpoints (server.py:10761-10773, :10846-10858) open a **fresh** trace and reach a gear (step-health written, cost-summary not), while the original paused turn's partial trace is abandoned — a built-in lineage case.
- **In-place-update precedents** for an idempotent finalizer: `compute_cost_summary` (boot.py:13413-13423, "safe to call repeatedly — overwrites") and `_log_visual_emissions_for_turn` (boot.py:1184-1257, globs `step*.json` then writes a derived summary). Atomic writes via `_atomic_write_json` (tmp + os.replace).
- Conversation side: `save_turn_spatial_state` (conversation_memory.py:169-181) → `_do_write` (:227-238) builds the assistant turn dict at :338-345, which already carries reserved-`None` fields — the precedent slot for `trace_ref`. The chunk/manifest layer is separate: `_save_conversation` (server.py:5650) appends conversation-manifest.jsonl lines at :5809-5817 (fields: timestamp_utc, conversation_id, chunk_id, chunk_path, raw_path, tag) and runs on a **daemon thread** (:10803-10807, :10881-10885), so `trace_ref` must be threaded through the `threading.Thread(args=…)` call sites.
- Retention sweeper deletes on **mtime** (`retention_sweeper.py:142`, cutoff from `ORA_RETENTION_TRACES_DAYS` at :276, rmtree at :144, empty-conv-dir rmdir at :148-152) — it never parses the dirname timestamp.

## Design

### D1 — Manifest lifecycle: skeleton at start, one idempotent finalizer in a single `try/finally`

`start_trace` writes `trace-manifest.json` (schema below) alongside `metadata.json` with `terminal_status: "open"`. Finalization: wrap the body of `_pipeline_stream` (from immediately after start_trace to the end) in one `try/finally`; the `finally` calls a new `pipeline_trace.finalize_manifest(trace_dir, kind, status_hint)` — the **only single-point option** given 19 return sites, and it also fires on `GeneratorExit` (client disconnect) and exceptions, which no per-site approach would. The generator body maintains a local `turn_kind` (default `"unknown"`), assigned one line at each branch entry (14 assignments, mechanical). `finalize_manifest` is idempotent (atomic overwrite; `compute_cost_summary` precedent), derives `actual_steps` by globbing `step*.json` in the turn dir (`_log_visual_emissions_for_turn` precedent), and derives `terminal_status`:

- `completed` — step-health.json exists;
- `short_circuit` — `turn_kind` in the short-circuit set;
- `error` — exception recorded on the way out;
- `abandoned` — none of the above (e.g. GeneratorExit mid-pipeline).

The two clarification-resume endpoints get the same wrap (they already open their own traces). Their manifests set `parent_trace_ref` to the abandoned paused turn's dir — lineage exercised from day one.

### D2 — Trace kinds (Codex condition 1 satisfied)

`chat-gear1 | chat-gear2 | chat-gear3 | chat-gear4 | direct` (gear-1/2 bypass) `| runtime_command | risk_hold | resolution_continuation | framework_elicitation | framework_command | clarification_pending | clarification_resume | no_endpoint_error | framework-run | framework-milestone | debug-run | resume` (last four reserved; populated in Chunks 1/3/4). Every one of the 14 observed path groups maps to exactly one kind; nothing metadata-only can masquerade as an abandoned pipeline run.

### D3 — Schema v1

```json
{
  "schema_version": 1,
  "conversation_id": "…",
  "turn_timestamp_utc": "20260709T…Z",
  "trace_kind": "chat-gear4",
  "terminal_status": "completed",
  "gear": 4,
  "mode": "root-cause-analysis",
  "framework_id": null,
  "milestone_id": null,
  "expected_steps": ["step1-phase-a", "step1-pre-routing", "step2-context", "step3-depth", "…"],
  "actual_steps": ["…globbed at finalize…"],
  "redaction_level": "private",
  "retention_state": "default",
  "parent_trace_ref": null,
  "child_trace_refs": [],
  "finalized_at": "2026-07-09T…Z"
}
```

`expected_steps` derivation: static per-gear step lists (the §2 layout table in the Trace doc), refined by mode only where the mode changes shape (verifier cycles are recorded as observed, not expected-counted). Open Question Q3 offers the alternative.

### D4 — Conversation-side join

`trace_ref` = `"<conversation_id>/<turn_timestamp>"` (relative to the pipeline-traces root — machine-resolvable, no absolute paths). Added: (a) keyword-only param through `save_turn_spatial_state` → `_do_write`, stamped on the assistant turn dict (:338-345 slot); (b) field on the conversation-manifest.jsonl line (:5809-5817), with `trace_dir` threaded through the daemon-thread `args`. Stealth turns: `trace_ref: null` (no trace exists to reference). A `trace_status` mirror field on the message is deliberately omitted — status lives in one place (the manifest); the viewer joins on demand.

### D5 — Trace doc §10 checklist (new persistence surface)

1. **Off-switch:** inherits `ORA_PIPELINE_TRACE` (no trace dir → no manifest). 2. **Stealth:** inherits Layer-1 no-creation. 3. **Purge:** lives inside the turn dir → `purge_conversation_traces` rmtree covers it; conversation.json `trace_ref` for stealth is null by construction. 4. **Gitignore:** covered by existing `data/pipeline-traces/` exclusion (verify with `git check-ignore` in tests). 5. **Documentation:** new subsection in `Reference — Pipeline Trace System` §2 + a §9-series entry, in the landing PR.

## Tests

Unit: manifest skeleton written by start_trace; finalizer stamps correct kind+status for each path class (simulate the four groups); idempotent double-finalize; stealth → zero files; `git check-ignore` on the manifest path; atomicity (tmp+replace). Integration: one real bypass turn and one real gear-3 turn through the server harness produce honestly-classified manifests; clarification-pause→resume produces linked parent/child. Parity: full suite, sorted FAIL/ERROR byte-identical to a fresh baseline at the implementation SHA, zero new.

## Open questions for the judge

- **Q1:** Kind stamping — local `turn_kind` + single `finally` (recommended; one hook, disconnect-safe) vs explicit `finalize_manifest` calls at each of the 19 return sites (no "unknown" window, but 19 chances to miss one and no GeneratorExit coverage).
- **Q2:** The clarification-resume endpoints' missing `cost-summary.json` is a pre-existing inconsistency the new `finally` could trivially fix in passing. Recommend: note it, defer the fix (scope discipline) unless the judge prefers folding it.
- **Q3:** `expected_steps` from static per-gear tables (recommended: simple, honest, verifier cycles observed-only) vs derived from mode files (more precise, more coupling).

## Design-gate verdict (Codex, 2026-07-11): APPROVE WITH MODIFICATIONS

**Q1:** single generator-level `try/finally` finalizer (as recommended); branch-local `turn_kind`/`status_hint` assignments; `finalize_manifest` fail-open + idempotent.
**Q2:** fix in passing — the wrapped `clarification_resume`/`clarification_skip` endpoints get the same best-effort `compute_cost_summary(trace_dir)` behavior as `_pipeline_stream`.
**Q3:** static per-gear required-step tables (as recommended), but split required vs optional/observed-only semantics: verifier cycles, web consultation, visual hook, and derived summaries must not create false "missing step" warnings.

Added conditions (binding):

1. **Status-hint-aware terminal status.** Server paths that catch errors, yield `error`, and return (no endpoint, runtime command failure, resolution failure, framework elicitation failure, framework command failure — server.py:~3156 vicinity) must finalize as `terminal_status: "error"`, not `short_circuit`.
2. **`clarification_pending` finalizes as `terminal_status: "paused"`** (explicit status), never `abandoned` — the parent of a resume is intentionally paused.
3. **Explicit trace-ref propagation channel.** `_pipeline_stream` owns `trace_dir` but `_invoke_pipeline` performs the main `_save_conversation`/`_persist_turn_spatial_state` calls outside the generator (server.py:6115, :6208, :6246). Add a non-inferential channel from generator to saver, then thread `trace_ref` through `_save_conversation`, `_persist_turn_spatial_state`, `save_turn_spatial_state`, and clarification endpoint save paths.
4. **Persist paused parent trace refs.** Pause sites (server.py:3514, :3586, :3623) must store the paused trace ref in `_pending_clarification` so resume/skip can set `parent_trace_ref`.
5. **Filter `actual_steps`.** No raw `step*.json` glob as the final list — it catches `step-health.json` and `step-visual-hook.json`; exclude or separately classify summaries/derived artifacts so missing-step rendering stays clean.

## Acceptance (from the approved plan, restated)

Any conversation.json turn resolves mechanically to its trace dir with zero inference; step completeness computable from the manifest alone; short-circuit/metadata-only turns honestly classified (Codex condition 1); stealth turns produce nothing; §10 checklist satisfied and documented; parity zero-new.
