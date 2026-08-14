# Chunk 3 Trace-Backed P-Debug Implementation Packet v6

## Status

Ready for the user's Codex code-review gate. This revision remains based on `f2a7385beb9391050adebc1333af7d160c930cf2`.

`origin/main` is `525d3075`. Rebase onto that commit remains a landing-time prerequisite after review approval. No rebase, commit, merge, branch publication, live smoke, or vault edit has been performed.

## Latest review fix

Probe finalization is now verified for every terminal outcome, not only successful probes:

- `completed` probes require durable `trace_kind`, exact `investigates_trace_ref`, and `terminal_status: completed`.
- Provider failures require durable `terminal_status: error`.
- Interrupt/system-exit paths require durable `terminal_status: abandoned` before the interruption continues propagating.
- If the normal finalizer is silent or fails to persist, the probe uses the existing atomic manifest updater as a fallback and reads the manifest back again before returning.
- Added a regression test that suppresses finalization during a provider failure and verifies the persisted terminal error.
- Updated the prior completion persistence test to verify that suppressed finalization is repaired into a durable completed probe rather than incorrectly reported as a failure.

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

- `/tmp/ora-chunk3-base-f6.full.log`
- `/tmp/ora-chunk3-impl-f6.full.log`
- `/tmp/ora-chunk3-base-f6.signatures`
- `/tmp/ora-chunk3-impl-f6.signatures`

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

`/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c-implementation-diff-v6.patch`
