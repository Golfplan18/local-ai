# Chunk 3 Implementation Packet: Trace-backed P-Debug

Status: ready for Codex code-review gate  
Implementation worktree: `/Users/oracle/ora-worktrees/chunk3-trace-debug`  
Base: `0a96f4d7`  
Vault: untouched  
Landing status: not committed, not merged

## Outcome

Chunk 3 runtime implementation is prepared in an isolated worktree. It adds trace-backed P-Debug investigation, execution-time contract capture, same-conversation investigation enforcement, a conservative model-only probe primitive with server-authoritative one-shot approval, Trace Walk / Paused-card investigation entry points, and a non-RAG trace-debug learning store with physical purge.

Important landing constraint: the runtime PIF copy is changed in this worktree, but the canonical vault PIF was not touched because no vault authorization was granted. This packet must not land until the vault/runtime PIF synchronization question is resolved.

## Files changed

- `.gitignore`
- `frameworks/book/process-inference.md`
- `orchestrator/boot.py`
- `orchestrator/conversation_closeout.py`
- `orchestrator/milestone_executor.py`
- `orchestrator/pipeline_trace.py`
- `orchestrator/trace_debug.py` (new)
- `orchestrator/tests/test_trace_manifest.py`
- `orchestrator/tests/test_trace_walk_ui.py`
- `server/server.py`
- `server/static/js/review-queue-panel.js`
- `server/static/js/sidebar-oversight.js`
- `server/static/js/trace-walk.js`

## Implementation summary

- Execution-time contracts:
  - Mode traces capture full `## VERIFICATION CRITERIA` contract snapshots during Step 2.
  - Framework parent and milestone child traces capture framework/milestone contract snapshots with canonical fingerprints.
  - Oversize/unavailable contracts record capture failure; later debug reports `CONTRACT_UNAVAILABLE` rather than guessing.

- Trace-debug routing:
  - Server accepts structured `trace_debug` JSON through `/chat` and routes it through the normal turn pipeline.
  - CLI supports deterministic `/trace-debug <trace_ref> [--step <step>] [--symptom <text>]`.
  - Natural-language routing remains default-off; no broad implicit routing was added.
  - Debug turns stamp `trace_kind: trace-debug` and `investigates_trace_ref`.

- Probe primitive:
  - Requires mechanical replay eligibility: complete model-only request envelope, effective provider/model/parameters/token limit, no tools/external actions.
  - Uses prepare -> approve -> execute.
  - Approval is server-authoritative and one-shot; digest is integrity evidence only.
  - Invalid, forged, expired, replayed, mutated, or not-replayable requests fail before `trace-probe` creation.
  - Successful approved execution creates `trace-probe`, records inert output, and finalizes completed/error/abandoned honestly.

- UI:
  - Trace Walk adds an Investigate button that submits structured exact-reference payload through `/chat`.
  - Paused-card surfaces add “Investigate trace” only when an exact `trace_ref` exists.
  - Same-conversation requirement is enforced.

- Learning library:
  - Adds non-RAG store `data/trace-debug/learning-library.jsonl`.
  - Store is gitignored, stealth/off-switch gated, and physically purged by conversation.
  - Recurrence count is derived from immutable observations, not mutated in place.

## Adversarial self-review

Findings checked against source:

1. Child framework traces could have been left `open` if contract capture broke `_finalize_child_trace`.
   - Verified against `orchestrator/milestone_executor.py` after implementation.
   - Found and fixed a bad scoped reference in `_finalize_child_trace` that swallowed finalization through fail-open handling.
   - Regression covered by existing and focused tests.

2. Contract capture could become false integrity if current contracts were reloaded after edits.
   - Verified that `trace_debug.framework_contract_snapshot()` fingerprints complete canonical fields.
   - Verified that debug prompt uses manifest snapshot or returns `CONTRACT_UNAVAILABLE` when absent.
   - Added mutation and oversize tests.

3. Probe approval could be forgeable/replayable if digest alone authorized execution.
   - Verified `trace_debug.consume_probe_approval()` requires server-side pending state, approval, expiry, conversation match, manifest digest, step digest, and one-shot consumption.
   - Added forged/replay tests and execution test.

4. Cross-conversation investigation could break purge completeness.
   - Verified `trace_debug.validate_same_conversation()` is used by debug prompt and probe prepare.
   - UI sends `panel_id` equal to the trace conversation; server validates through the debug builder.
   - Added cross-conversation rejection test.

5. Probe traces could be created for refused requests.
   - Verified `execute_probe()` consumes valid approval before `start_trace()`.
   - `NOT_REPLAYABLE` remains a prepare result and creates no probe trace.
   - Added not-replayable no-trace test.

6. UI could submit stale or wrong-conversation investigation payloads.
   - Verified Trace Walk action uses loaded modal state and active conversation id check.
   - Existing generation/abort guards remain intact.
   - Added jsdom payload coverage.

Residual risk:

- The runtime PIF file is updated, but the canonical vault PIF is intentionally untouched. This implementation should not land until vault authorization allows synchronized canonical/runtime PIF updates.
- Natural-language trace-debug routing remains unimplemented/default-off. Deterministic structured UI and CLI routes are implemented.
- Probe execution currently exposes the safe primitive and executor hook; production UI/API for model probe approval/execution is not surfaced beyond the internal primitive.

## Validation

Focused tests:

- `ORA_HOME=/Users/oracle/ora-worktrees/chunk3-trace-debug python3 -m unittest orchestrator.tests.test_trace_manifest orchestrator.tests.test_trace_walk_ui -v`
- Result: `Ran 99 tests ... OK`

Static checks:

- Python compile: passed for touched Python runtime files.
- Browser syntax: `node --check` passed for touched JS files.
- `git diff --check`: passed.

Full-suite parity:

- Baseline worktree: `/Users/oracle/ora-worktrees/chunk3-baseline-0a96f4d7`
- Implementation worktree: `/Users/oracle/ora-worktrees/chunk3-trace-debug`
- Both runs exported `ORA_HOME` to their respective worktrees.
- Baseline: `Ran 4850 tests in 244.129s`; `FAILED (failures=43, errors=6, skipped=17)`
- Implementation: `Ran 4857 tests in 265.717s`; `FAILED (failures=43, errors=6, skipped=17)`
- Sorted FAIL/ERROR signatures: `49` vs `49`, byte-identical.
- Signature files:
  - `/tmp/chunk3-parity/baseline.signatures`
  - `/tmp/chunk3-parity/impl.signatures`

## Review artifacts

- Packet: `/Users/oracle/ora-worktrees/chunk3-trace-debug-implementation-packet.md`
- Diff: `/Users/oracle/ora-worktrees/chunk3-trace-debug-implementation-diff.patch`
