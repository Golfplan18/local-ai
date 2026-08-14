# Chunk 3 Trace Debug Corrected Implementation Packet

## Outcome

Corrected Chunk 3 after the Codex review block. The implementation is rebased onto current `origin/main` `d822d9a8610e4bcad9438499e54fb49c92054ae4` in `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased`.

No vault files were touched. The unrelated runtime lock files remain excluded from the implementation.

## Worktree and base

- Implementation worktree: `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased`
- Baseline worktree: `/Users/oracle/ora-worktrees/chunk3-baseline-d822d9a8`
- Base commit: `d822d9a8610e4bcad9438499e54fb49c92054ae4`
- Corrected diff: `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-implementation-diff.patch`

## Block findings addressed

1. Debugger now walks the trace.

`trace_debug.build_debug_prompt()` now loads a single lifecycle-locked trace snapshot containing the manifest projection, all manifest-listed step projections, `step-health`, `model-call-config.jsonl`, child trace manifests, and a three-valued boundary table. The prompt explicitly instructs P-Debug to classify structural and semantic evidence separately and not infer semantic success from mere execution.

2. Probe replay now uses production trace evidence.

`prepare_probe()` no longer depends on a synthetic `payload.model_request`. It can derive a model-only replay envelope from production step payload fields plus the effective `model-call-config.jsonl` record. The envelope is retained in server-side approval state and `execute_probe()` passes the actual envelope to the model executor.

3. Probe cost and risk approval now fail closed.

`prepare_probe()` computes a bounded cost estimate and derives the risk decision server-side through the existing risk gate. The old caller-supplied `risk_decision` affordance was removed. `execute_probe()` consumes one-time server-side approval before creating a probe trace, and if trace creation fails it refuses to call the model executor.

4. Learning library is constrained and integrated.

Learning writes now use an allowlisted schema, same-conversation trace validation, secret redaction, recurrence derived at read time, and physical purge under the shared lifecycle lock. Trace-debug server and CLI paths call `record_diagnosis_learning()` after P-Debug returns a recognizable verdict. Prior related entries are included in the debug prompt as non-authoritative context.

5. P-Debug no longer structurally assumes a defect.

The runtime PIF copy now includes trace-backed verdict discipline, PEF Lock, substitution guard, fabricated-finding guard, and first-class handling for `DEFECT_LOCALIZED`, `BAD_DRAW`, `CONTRACT_MISMATCH`, `NO_DEFECT`, and `CONTRACT_UNAVAILABLE`. The prior defect-assuming P-Debug instructions in Layers 1, 3, and 5 were rewritten.

6. Framework bundle capture now fails honestly.

`framework_contract_bundle()` now marks the parent bundle unavailable if any milestone contract snapshot fails. It no longer substitutes `{}` and reports the parent as captured.

7. Default-off natural-language routing is implemented.

`trace_debug_nl_enabled()` is now used. Server and CLI paths can route exact-reference natural-language investigation requests only when `ORA_TRACE_DEBUG_NL` is enabled; default remains off and ambiguous/multiple refs are ignored.

8. Read locking and UI failure reporting are tightened.

Trace debug loading now holds the lifecycle lock across resolution and all trace reads. Trace Walk investigation fetches check `response.ok`; Paused-card investigation callers now surface failures instead of suppressing them.

## Adversarial self-review

I specifically re-checked the previous block seams against source after the fixes:

- Verified `build_debug_prompt()` no longer calls separate unlocked projection helpers and instead uses `_load_trace_walk_locked()` for the whole trace snapshot.
- Verified `prepare_probe()` has no caller-supplied risk decision parameter and derives replay eligibility from step payload plus `model-call-config.jsonl`.
- Verified `execute_probe()` returns before model execution if `start_trace()` fails.
- Verified `append_learning_entry()` only persists allowlisted fields and rejects cross-conversation trace refs.
- Verified the PIF still contains generic phrase “failure points” for normal path planning, but the active P-Debug branches no longer require user-narrated expected/actual behavior, first observed failure, or failure-isolating probes.
- Verified server and CLI both wire structured trace-debug and default-off natural-language routing through normal turn execution.
- Verified browser investigation paths check failed `/chat` responses and report them visibly.

No remaining blocking self-review findings were found.

## Tests and validation

Mechanical validation on `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased`:

- Python compile: passed for touched Python files.
- JavaScript syntax: passed for `trace-walk.js`, `review-queue-panel.js`, and `sidebar-oversight.js`.
- `git diff --check HEAD`: passed.
- Focused tests: `105` passed.

Full-suite parity with `ORA_HOME` exported on both sides:

- Baseline: `Ran 4853 tests in 141.659s`, `FAILED (failures=43, errors=6, skipped=17)`, `49` sorted `FAIL`/`ERROR` signatures.
- Implementation: `Ran 4866 tests in 146.705s`, `FAILED (failures=43, errors=6, skipped=17)`, `49` sorted `FAIL`/`ERROR` signatures.
- Signature comparison: byte-identical.

Signature files:

- `/tmp/chunk3-parity-d822/baseline.signatures`
- `/tmp/chunk3-parity-d822/impl.signatures`

## Notes for review

- The prior worktree `/Users/oracle/ora-worktrees/chunk3-trace-debug` remains present with runtime `data/*.lock` files. The corrected review target is `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased`.
- The implementation changes are currently staged in the rebased worktree because the patch was applied with index preservation. No commit has been made.
- Per protocol, this stops here for the Codex code-review gate.
