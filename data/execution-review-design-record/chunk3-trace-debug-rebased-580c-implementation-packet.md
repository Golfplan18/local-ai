# Chunk 3 Trace Debug Corrected Implementation Packet, Block 2

## Outcome

Corrected the second Codex review block for Chunk 3. The active review target is now rebased onto current `origin/main` `580c39e1628d3d77acb2ad1f47a2e1c594468add`.

No vault files were touched. No commit, merge, or PR was made.

## Worktree and artifacts

- Implementation worktree: `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c`
- Baseline worktree: `/Users/oracle/ora-worktrees/chunk3-baseline-580c39e1`
- Base commit: `580c39e1628d3d77acb2ad1f47a2e1c594468add`
- Corrected packet: `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c-implementation-packet.md`
- Corrected diff: `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c-implementation-diff.patch`

## Block findings addressed

1. Conversation purge deadlock fixed.

`trace_debug` now has `purge_conversation_unlocked()` for callers that already hold the lifecycle lock, and the public `purge_conversation()` remains the locked wrapper. `conversation_closeout.py` now calls the unlocked helper from inside its existing closeout lock.

2. Debug contexts are bounded.

Trace debug context loading now applies a deterministic whole-package budget with explicit `evidence_budget` markers. Oversized strings and aggregate contexts are truncated or omitted with visible unavailable/truncated markers instead of silently producing multi-million-character prompts.

3. Framework-parent investigations load child evidence.

The trace walker now recursively loads child trace manifests, steps, step-health, model-call configs, contracts, and boundary tables up to a bounded depth/child limit. Framework parents now carry the milestone evidence needed for localization.

4. Replay selection is mechanically faithful.

Probe preparation no longer falls back to the last call in the whole trace. It requires exactly one matching physical model-call config for the selected step, rejects ambiguous multi-call mappings, and rejects incomplete message envelopes such as system-only captures.

5. Counterfactual, cost, and production probe paths are live.

`prompt_delta` is applied as an explicit counterfactual message. `cost_ceiling` is compared with the estimated token budget and can return `COST_EXCEEDED`. Server endpoints now exist for probe prepare/approve/execute, and CLI has deterministic `/trace-probe prepare|approve|execute` handling. Execute uses the approved server-side envelope and records a `trace-probe` trace.

6. Binding P-Debug discipline is present.

The runtime PIF now includes the P-Debug Trace-Backed Verdict Discipline section with allowed verdicts, seven-class root-cause taxonomy, PEF Lock inheritance, Silent Non-Solution Substitution guard, P-Debug No-Punt escalation, and fabricated-finding failure mode.

7. Learning records are version/verdict safe.

Learning schema now includes contract/framework fingerprints, failing step, and verification probe. `record_diagnosis_learning()` accepts only one unambiguous line-anchored `VERDICT:` field and refuses reports that merely mention verdict words in prose or contain multiple verdict lines.

8. Boundary summary no longer contradicts first failure.

`last_known_good` is now calculated as the last passing boundary before the first failure, not the final passing step anywhere in the trace.

## Adversarial self-review

I rechecked the eight blocked areas against source after fixing them:

- Closeout uses `purge_conversation_unlocked()` under its existing lock.
- `build_debug_prompt()` uses the locked trace walker as the existence/read authority and applies `_apply_debug_budget()` before serialization.
- Child traces are recursively walked with bounded depth and child count.
- Replay rejects no-match, multi-match, and incomplete-message cases.
- Cost ceiling and prompt delta are active in `prepare_probe()`.
- Server and CLI probe callers exist and use the same approval state as tests.
- PIF binding text is present in the runtime `frameworks/book/process-inference.md` file.
- Learning requires a single `VERDICT:` line and stores fingerprints/probe fields.

No remaining blocking self-review findings were found.

## Validation

Rebased validation on `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c`:

- Python compile: passed for touched Python files.
- JavaScript syntax: passed for touched browser files.
- `git diff --check HEAD`: passed.
- Focused tests: `112` passed.

Full-suite parity with `ORA_HOME` exported on both sides:

- Baseline: `Ran 4856 tests in 184.449s`, `FAILED (failures=34, errors=6, skipped=19)`, `40` sorted `FAIL`/`ERROR` signatures.
- Implementation: `Ran 4876 tests in 269.093s`, `FAILED (failures=34, errors=6, skipped=19)`, `40` sorted `FAIL`/`ERROR` signatures.
- Signature comparison: byte-identical.

Signature files:

- `/tmp/chunk3-parity-580c/baseline.signatures`
- `/tmp/chunk3-parity-580c/impl.signatures`

## Notes

- The corrected review target is `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c`.
- The prior corrected worktree `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased` remains older, based on `d822d9a8`.
- Runtime lock files under `data/*.lock` are untracked and excluded from the implementation.
- Per protocol, this stops here for the Codex code-review gate.
