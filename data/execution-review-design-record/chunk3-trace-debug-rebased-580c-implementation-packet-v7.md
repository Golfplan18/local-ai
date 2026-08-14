# Chunk 3 Trace-Backed P-Debug Implementation Packet v7

## Status

Ready for the user's Codex code-review gate. This revision remains based on `f2a7385beb9391050adebc1333af7d160c930cf2`.

`origin/main` is now `c5ecd95`. Rebase onto the actual current origin remains a landing-time prerequisite after review approval. No rebase, commit, merge, branch publication, live smoke, or vault edit has been performed.

## Latest review fix

The probe finalization fallback now performs full manifest derivation before accepting durability:

- It scans the trace directory with the same `_scan_turn_dir()` helper used by the normal finalizer.
- It applies the same trace-probe expected-step table, including `step-health`.
- It persists `expected_steps`, `actual_steps`, `derived_artifacts`, `trace_kind`, `investigates_trace_ref`, `terminal_status`, schema version, and finalization time atomically.
- It reads the complete manifest back before returning success or accepting a terminal outcome.
- The completion regression now verifies four actual probe step files, one derived `step-health` artifact, and the complete expected-step table.

The earlier terminal-status read-back and atomic fallback repair remain active for completed, error, and abandoned outcomes.

## Earlier retained fixes

The packet retains the preceding fixes for immutable framework-source fingerprints, same-conversation reciprocal probe origins, fail-closed required artifacts, server-authoritative one-shot approvals with rejection events, bounded/redacted finite-taxonomy learning records, corruption reporting, seeded verdict paths, trace walking, three-valued boundary evidence, bounded debug prompts, framework-parent child evidence, exact replay eligibility, inert model-only probes, cost ceilings, private handling, physical-call context, probe lineage, default-OFF natural-language routing, P-Debug instruction changes, locked trace reads, private server probe redaction, and successful manifest read-back verification.

## Validation

Focused tests:

- `134` tests passed in `orchestrator.tests.test_trace_manifest` and `orchestrator.tests.test_trace_walk_ui`.

Full-suite parity on a fresh baseline and implementation worktree, with `ORA_HOME` exported separately:

- Fresh baseline: `4992` tests, `34` failures, `6` errors, `19` skipped.
- Implementation: `5034` tests, `34` failures, `6` errors, `19` skipped.
- Sorted `FAIL`/`ERROR` signatures: `40` baseline and `40` implementation; byte-identical.

Other checks:

- Python compilation passed for all changed Python entry points.
- JavaScript syntax checks passed for all changed browser files.
- `git diff --check HEAD` passed.

Full-suite logs used for parity:

- `/tmp/ora-chunk3-base-f7.full.log`
- `/tmp/ora-chunk3-impl-f7.full.log`
- `/tmp/ora-chunk3-base-f7.signatures`
- `/tmp/ora-chunk3-impl-f7.signatures`

## Changed files

- `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c/.gitignore`
- `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c/frameworks/book/process-inference.md`
- `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c/orchestrator/boot.py`
- `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c/orchestrator/conversation_closeout.py`
- `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c/orchestrator/milestone_executor.py`
- `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c/orchestrator/pipeline_trace.py`
- `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c/orchestrator/tests/test_trace_manifest.py`
- `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c/orchestrator/tests/test_trace_walk_ui.py`
- `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c/orchestrator/trace_debug.py`
- `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c/server/server.py`
- `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c/server/static/js/review-queue-panel.js`
- `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c/server/static/js/sidebar-oversight.js`
- `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c/server/static/js/trace-walk.js`

The untracked runtime lock files `data/conversation-indexing-failures.jsonl.lock` and `data/conversation-manifest.jsonl.lock` remain excluded from the diff.

## Diff

Binary-capable implementation diff:

`/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c-implementation-diff-v7.patch`
