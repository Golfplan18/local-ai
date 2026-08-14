# Chunk 3 Trace-Backed P-Debug Implementation Packet v5

## Status

Ready for the user's Codex code-review gate. This revision remains based on `f2a7385beb9391050adebc1333af7d160c930cf2`, the review base used for the preceding packet.

`origin/main` has since advanced to `525d3075`. Per the approved protocol, rebase onto that current origin after review approval and before landing; no rebase, commit, merge, branch publication, live smoke, or vault edit has been performed in this packet.

## Latest review fixes

1. Restored `conversation_tag_for_trace_ref()` redaction lookup. The server prepare/approve/execute path now carries a private source trace's private tag into the probe, and the probe manifest is verified as private.
2. Probe manifest metadata updates are now checked immediately. Missing or mismatched `trace_kind` or `investigates_trace_ref` fails the probe before model execution.
3. Probe finalization is now checked by reading the manifest after `finalize_manifest()`. A successful response is converted to an error unless the durable manifest contains the probe kind, exact investigated reference, and `terminal_status: completed`.
4. Added server-path private-probe coverage and persistence failure/read-back coverage.

## Earlier retained fixes

The packet retains the preceding fixes for immutable framework-source fingerprints, same-conversation reciprocal probe origins, fail-closed required artifacts, server-authoritative one-shot approvals with rejection events, bounded/redacted finite-taxonomy learning records, corruption reporting, seeded verdict paths, trace walking, three-valued boundary evidence, bounded debug prompts, framework-parent child evidence, exact replay eligibility, inert model-only probes, cost ceilings, private handling, physical-call context, probe lineage, default-OFF natural-language routing, P-Debug instruction changes, and locked trace reads.

## Validation

Focused tests:

- `133` tests passed in `orchestrator.tests.test_trace_manifest` and `orchestrator.tests.test_trace_walk_ui`.

Full-suite parity on a fresh baseline and implementation worktree, with `ORA_HOME` exported separately:

- Fresh baseline: `4992` tests, `34` failures, `6` errors, `19` skipped.
- Implementation: `5033` tests, `34` failures, `6` errors, `19` skipped.
- Sorted `FAIL`/`ERROR` signatures: `40` baseline and `40` implementation; byte-identical.

Other checks:

- Python compilation passed for all changed Python entry points.
- JavaScript syntax checks passed for all changed browser files.
- `git diff --check HEAD` passed.

Full-suite logs used for parity:

- `/tmp/ora-chunk3-base-f5.full.log`
- `/tmp/ora-chunk3-impl-f5.full.log`
- `/tmp/ora-chunk3-base-f5.signatures`
- `/tmp/ora-chunk3-impl-f5.signatures`

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

`/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c-implementation-diff-v5.patch`
