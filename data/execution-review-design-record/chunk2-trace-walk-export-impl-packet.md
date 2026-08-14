# Chunk 2 Trace Walk & Export implementation packet

## Outcome

Chunk 2 is implemented in `/Users/oracle/ora-worktrees/chunk2-trace-walk-export` and rebased onto current `origin/main` `681e9835cc75`.

This packet includes the latest BLOCK fix:

- `pipeline_trace.list_trace_refs()` now acquires the cross-process runtime conversation lifecycle lock around the complete trace-list operation: enumeration, ref derivation, and manifest-bearing resolution.
- `api_trace_list()` no longer wraps trace listing in the Flask-only server `RLock`; it delegates to the shared helper so Flask and non-Flask callers receive the same protection.
- Added a regression test proving both discovery and resolution occur while `_rp.conversation_lifecycle_lock()` is held.

Previously repaired and still covered:

- Stale Trace Walk modal responses are ignored using request generations and abort controllers for manifest, step, pin, and export requests.
- Trace manifest/step/export reads hold the conversation lifecycle lock through resolution, revalidation, bounded reads, and full export snapshot assembly.
- Retention updates are serialized under the same lifecycle lock, preserve unrelated manifest fields, reject open traces, and validate the API schema strictly.
- Export no longer navigates the current page on failure; Pin/Export remain disabled until the matching manifest is loaded.
- Permanent jsdom coverage exercises escaped rendering, current-turn synchronization, exact paused trace links, invalid/stale controls, focus lifecycle, and out-of-order manifest/step/pin responses.

## Files changed

- `orchestrator/pipeline_trace.py`
- `orchestrator/tool_events.py`
- `orchestrator/oversight_queue.py`
- `orchestrator/tests/test_trace_manifest.py`
- `orchestrator/tests/test_trace_walk_ui.py`
- `server/server.py`
- `server/index-v3.html`
- `server/static/js/trace-walk.js`
- `server/static/js/export-toolbar.js`
- `server/static/js/v3-conversation.js`
- `server/static/js/sidebar-oversight.js`
- `server/static/js/review-queue-panel.js`

## Rebase and semantic-overlap check

- Rebased cleanly with autostash onto `origin/main` `681e9835cc75`.
- Upstream files changed since the prior packet include `runtime_paths.py`, but there is no changed-file overlap with this implementation.
- No conflicts required manual resolution.

## Validation run after rebase

Focused tests:

- `orchestrator.tests.test_trace_manifest`: pass
- `orchestrator.tests.test_trace_walk_ui`: pass
- Combined focused result: 92 tests pass

Static/syntax checks:

- Python compile check passed for touched Python files.
- Node syntax checks passed for touched browser JavaScript files.
- `git diff --check` passed.

Full-suite parity:

- Baseline worktree: fresh detached `origin/main`, `ORA_HOME` exported to baseline worktree.
- Implementation worktree: corrected Chunk 2 worktree, `ORA_HOME` exported to implementation worktree.
- Baseline suite exit: 1
- Implementation suite exit: 1
- Baseline failure/error signatures: 49
- Implementation failure/error signatures: 49
- Sorted failure/error signature comparison: byte-identical (`cmp=0`)
- Parity logs: `/tmp/chunk2-parity-1783911019`

## Notes for Codex review

- The latest list-lock fix is intentionally inside `pipeline_trace.list_trace_refs()` so non-Flask callers are protected.
- The Flask route still validates the conversation id before delegating, but it no longer relies on the server-only lock for trace-list integrity.
- The refreshed review diff is at `/Users/oracle/ora-worktrees/chunk2-trace-walk-export.diff` and includes the two new untracked files.

## Stop point

Per protocol, this worktree is not committed, merged, or landed. It is ready for the Codex code-review gate.
