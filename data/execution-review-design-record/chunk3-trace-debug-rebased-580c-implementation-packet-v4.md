# Chunk 3 Trace-Backed P-Debug Implementation Packet v4

## Status

Ready for the user's Codex code-review gate. This packet is based on `f2a7385beb9391050adebc1333af7d160c930cf2`, which was current at `origin/main` for this validation pass.

No commit, merge, branch publication, live smoke, or vault edit has been performed.

## Scope

This revision addresses the six findings in the latest BLOCK review:

1. Framework contract fingerprints now use the parsed immutable framework source (`raw_markdown`) and one digest is computed and reused for every contract snapshot in a bundle. Runtime file rereads are not used as a substitute source.
2. Explicit probe origins are restricted to the same conversation, a manifest-bearing `trace-debug` parent, and a reciprocal `investigates_trace_ref` relationship.
3. Probe execution fails closed when required artifacts cannot be written. Successful probes verify the result artifact and step-health artifact before finalizing `completed`.
4. Forged, missing, expired, consumed, mutated, and conversation-mismatched approvals are recorded as rejection events in the originating debug trace when an origin can be identified. Approval remains server-authoritative and one-shot.
5. Learning records use schema version 1, a finite root-cause taxonomy, bounded and secret-redacted text fields, an allowlisted shape, same-conversation ownership checks, and visible malformed/unsupported-schema counters.
6. Permanent tests cover the seeded four-verdict paths, approval expiry, request/config mutation, concurrent double execution, cross-conversation origins, probe artifact failure, framework-source mutation, learning corruption boundaries, and conversation purge behavior.

## Additional retained behavior

The packet retains the earlier Chunk 3 work for trace walking, three-valued boundary evidence, bounded debug prompts with explicit unavailable/truncated markers, framework-parent child evidence, exact replay eligibility, inert model-only probes, cost ceilings, private-conversation handling, probe physical-call context, probe lineage, natural-language routing default-OFF, P-Debug instruction changes, and locked trace reads.

## Validation

Focused tests:

- `131` tests passed in `orchestrator.tests.test_trace_manifest` and `orchestrator.tests.test_trace_walk_ui`.

Full-suite parity, with `ORA_HOME` exported separately for each worktree:

- Fresh baseline: `4992` tests, `34` failures, `6` errors, `19` skipped.
- Implementation: `5031` tests, `34` failures, `6` errors, `19` skipped.
- Sorted `FAIL`/`ERROR` signatures: `40` baseline and `40` implementation; byte-identical.

Other checks:

- Python compilation passed for all changed Python entry points.
- JavaScript syntax checks passed for all changed browser files.
- `git diff --check HEAD` passed.

Full-suite logs used for parity:

- `/tmp/ora-chunk3-base-f4.full.log`
- `/tmp/ora-chunk3-impl-f4.full.log`
- `/tmp/ora-chunk3-base-f4.signatures`
- `/tmp/ora-chunk3-impl-f4.signatures`

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

The untracked runtime lock files `data/conversation-indexing-failures.jsonl.lock` and `data/conversation-manifest.jsonl.lock` were not included in the diff.

## Diff

Binary-capable implementation diff:

`/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c-implementation-diff-v4.patch`
