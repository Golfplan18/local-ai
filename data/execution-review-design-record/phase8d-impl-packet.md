# Execution Review — Phase 8 · Chunk D (ora-side generic seam) IMPLEMENTATION packet (Rev 0)
## `record_program_run` (the programmatic packet record) + the per-run turn-context primitive

*Thread: Execution Thread. Date: 2026-07-06. Branch `execution-review-phase8d-impl` off origin/main `94547937` (Chunk C landing) in worktree `/Users/oracle/ora-worktrees/phase8d-impl`. Design: `phase8-design.md` §5. Addendum: `phase8-D-addendum.md` **Rev 3 — APPROVED-WITH-CONDITIONS by the judge; both P2/P3 conditions carried into this implementation**. NO commit yet — awaiting the CODE-REVIEW gate. This is the GENERIC ora-side seam ONLY; the MSI recipes + `.ora/` catalog land SEPARATELY in the MSI repo (next phase). Durable: this packet + `phase8d-impl.diff`.*

## 0. What this ships (the design's one new generic seam)

The addendum established that Chunk D's only genuinely-new GENERIC ora seam is `record_program_run` (the `invoke_chat` model-event seam was dropped — `boot.call_model` already records `model_call` for every `invoke_chat` call). This diff ships that seam + the per-run turn-context primitive the MSI recipe needs. **No MSI knowledge** (plugin convention). **Diff:** 3 files, +396/−5, whitespace-clean.

- **NEW `orchestrator/execution_review.py`** — `record_program_run(*, trace_dir, output_text, enforcement_model, repo_root=None, risk_tier=None, output_type="execution", producer_claim=None, stealth=False, runner=None, now_iso=None) -> str|None`. Runs the same packet-build + declared-lane fill + persistence gauntlet the live gear terminal runs, for a programmatic run that never flows through `run_pipeline`/`server`.
- **`orchestrator/tool_events.py`** — `set_turn_context(...)` now RETURNS the ContextVar reset token (was `None`; additive) + new `reset_turn_context(token)`. Lets a programmatic run seed a PER-RUN context and restore the prior exactly (incl. the "unset" state) in a `finally`, so a later run's between-run events can't leak into the prior run's per-run sink (judge P2).
- **NEW `orchestrator/tests/test_execution_review.py`** — 10 tests.

## 1. The `record_program_run` contract (binding ⚖ Rev-3, verified)

- **Signals FOLDED from the run's OWN event log (§16-3), never caller-narrated.** The caller routes the run's events to `<trace_dir>/tool-events.jsonl` (via the per-run turn context); `record_program_run` folds them via the landed `risk_gate.record_route_observed(str(trace_dir))` (whole-file mode — the exact terminal path). The signature carries NO caller-supplied signal/lane-verdict param. An empty log → no-signals + a disclosed `instrumentation: "none"` stamp (blindness, not a caller-suppliable green).
- **Evidence lanes filled ONLY by the registered fillers.** The target repo's `standing:true` deploy_probe/render_inspect recipes are built from `catalog.recipes` directly (judge P3 — `lanes_from_catalog` drops `standing`, so its output can't be filtered), stashed as `context_pkg["evidence_contract"]["lanes"]`, and attached by the landed Chunk-C seam (`build_execution_packet` → `route_lanes(declared=)`); then `execution_loop.fill_declared_lanes` runs the deploy_probe filler against the matching recipe. Never accepts lane verdicts as caller data.
- **`enforcement_model` caller-MANDATORY, validated, no default** — refuses (returns None, writes NOTHING) on a value not in `tool_events.ENFORCEMENT` BEFORE the packet is built, rather than inheriting the hardcoded `in_harness` (the P6 TODO). Correct value set via the whitelisted `populate_loop_fields(execution={"enforcement_model": …})` override seam.
- **Caller free-text → `producer_claim.known_limitations`** (the summary carries the shipped prose) — rendered last, labeled unverified (§12). Never a signal, never a lane.
- **Trace-local packet ALWAYS written on a non-stealth success (judge P2).** `persist_packet` only decides the durable tier + writes the ledger/note WHEN promoted; `record_program_run` then calls `write_packet` so a `git_only` / `instrumentation:none` run STILL leaves `execution-packet.json`.
- **Never raises** (every `except` → `_mark_failure` + safe return); **stealth → no record**; `reset_turn_context` no-ops on a bad/None token.

## 2. Verification

- **Adversarial pre-check (3 lenses × per-finding verify, all Opus): ZERO findings** — correctness (fold/build/attach/override/persist+write chain), contract+fail-closed (signals-from-log, enforcement-mandatory-refuse, never-raises, stealth), parity+portability (the `set_turn_context` return is purely additive; new files import nothing existing; no cycle — `execution_loop` is imported lazily inside the function).
- **Parity:** fresh pre-edit baseline in this worktree **4,035 tests / 27 FAIL/ERROR**; post **4,045 tests (+10), sorted FAIL/ERROR BYTE-IDENTICAL to baseline, ZERO new**. `record_program_run` is a library entrypoint — no ora turn calls it, so live behavior is unchanged.
- **Tests (`test_execution_review.py`, 10):** signals folded from a synthetic per-run log (mutation event → `observed.any_mutation` True, caller passes no booleans); empty log → `instrumentation:none` AND the trace-local packet is still written; `enforcement_model` invalid → refuse + no packet, missing → TypeError; caller free-text → `producer_claim.known_limitations`; stealth → no record; **`standing:true` deploy_probe recipe routes onto the packet AND fills (a REAL end-to-end: a fixture git repo with a standing `git_heartbeat` recipe → the probe PASSes → lane sufficient), `standing:false` does NOT route**; the `set_turn_context` token round-trip restores the prior context (incl. unset).

## 3. Portability + invariants

`runtime_paths`-derived roots (via the reused `persist_packet`/`write_packet`); `encoding="utf-8"` on the test I/O; no user-path literals; never-raises throughout. The reset primitive is idiomatic `contextvars` (`ContextVar.set` returns a Token; `reset(token)`). No plugin-convention violation — `record_program_run` is generic (no MSI knowledge); the MSI recipes that call it live in `ora-project`.

## 4. Landing plan + next phase

ON CODE-REVIEW APPROVAL: re-fetch origin/main → rebase → `git add -A` → commit → push → `gh pr create` → `gh pr merge --squash --delete-branch` → prune worktree → ff `~/ora` main → smoke-import `execution_review` + the context primitive → report PR# + bare SHA. **THEN the MSI-side (the next implementation phase, separate MSI-repo landing):** instrument `backfill_orchestrator._call_openrouter` (guarded boundary `model_call` events); wire `invoke_real_gear4` to seed a per-run turn context at the start (using the new token/reset primitive), call `record_program_run` AFTER final output selection across all four consolidation modes (judge P1), `enforcement_model="boundary_only"`, restore the context in a `finally` (judge P2); the publish boundary event + the `standing:true` deploy_probe recipe; the MSI `.ora/evidence.yaml` (root of the astro repo) + the python frontmatter-gate check; the per-article source manifest. MSI-side tests (incl. the per-consolidation-mode recording tests + the context-restore regression) run in `ora-project/tests/`, staged MSI-side, re-pulling the churning MSI repo first. NO commit until the judge approves this diff.

## 5. Carried gotchas (not re-introduced)

`contextvars` don't cross `executor.submit` — but `record_program_run` runs on the caller's thread (no new executor boundary); the per-run context the MSI caller sets propagates to `run_gear4`'s workers via the existing `boot._submit_with_context` copy_context. A redactor/sanitizer except-fallback fails CLOSED (reused `persist_packet`'s fail-closed redaction is untouched). `reversible:true` at high-risk is the §6 gate (untouched — `build_execution_packet` sets it, unchanged).
