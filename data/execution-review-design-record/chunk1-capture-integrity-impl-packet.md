# Chunk 1 Implementation Packet: Capture integrity

## Outcome

Chunk 1 is implemented in the fresh worktree at `/Users/oracle/ora-worktrees/chunk1-capture-integrity`, rebased onto current `origin/main` SHA `60b495d9948b`.

No commits, merges, vault edits, main-worktree changes, PRs, or live-smoke steps were performed.

## Second review-gate block resolution

The second Codex review returned BLOCK with two findings. Each finding was verified against source and fixed:

1. **Physical-call capture completeness**
   - `claude-code` subscription calls now record a physical provider attempt immediately before the actual `subprocess.run` call.
   - Local recording was removed from the high-level `call_model` local branch so unsupported engines are not mislabeled as physical attempts.
   - Ollama now records at the HTTP `urlopen` request seam.
   - MLX now records at the `mlx_generate` request seam with the resolved default `max_tokens=999999999` when no endpoint cap is supplied.
   - Regression tests cover successful mocked `claude-code`, MLX default token-cap capture, and unsupported local engines producing no `model-call-config.jsonl` record.

2. **Successful production lineage tests**
   - Added server `_pipeline_stream` happy-path framework lineage coverage.
   - Added CLI `run_pipeline` happy-path framework lineage coverage.
   - Both tests assert completed parent status, framework id, two distinct child refs for retry attempts, child terminal statuses, child framework/milestone fields, and child `parent_trace_ref` back to the parent.

## Prior block resolution retained

The first Codex review returned five findings. Those repairs remain in place after rebase:

- Child trace skeletons remain `terminal_status: "open"` during execution.
- Child traces finalize `completed` only after the gear pipeline and drift check succeed.
- `KeyboardInterrupt`, `SystemExit`, and other `BaseException` exits finalize child traces as `error` before re-raising.
- `model-call-config.jsonl` records physical provider attempts with invocation identity, attempt index, provider-attempt label, effective endpoint, and effective token cap.
- Malformed/schemeless URL strings such as `user:pass@example.test/v1` persist an empty host rather than credential-bearing path text.
- `resolve_trace_ref` rejects symlink escapes using the current upstream safe trace-directory primitives.
- Same-second trace creation claims each turn directory atomically with `os.mkdir` and retries on `FileExistsError`.

## Rebase resolution

`origin/main` moved through `b281bfe1b421` and then `60b495d9948b` during the second block fix. I rebased the implementation, resolved overlaps against upstream's dialogue lifecycle / safe trace-store work, and preserved both sides:

- Kept upstream lifecycle context scoping in server trace finalization.
- Kept upstream safe owned-directory trace helpers and symlink protections.
- Reapplied Chunk 1 framework/milestone/child manifest fields to server and CLI finalization.
- Reapplied atomic same-timestamp trace creation inside the upstream safe trace root.
- Reapplied pinned-retention behavior inside the upstream conversation lifecycle lock.
- Kept upstream symlink and lifecycle tests while retaining Chunk 1's new tests.

## Files changed

- `orchestrator/pipeline_trace.py`
- `orchestrator/milestone_executor.py`
- `orchestrator/boot.py`
- `server/server.py`
- `orchestrator/retention_sweeper.py`
- `orchestrator/tests/test_trace_manifest.py`
- `orchestrator/tests/test_retention_sweeper.py`

Diff file for Codex review: `/Users/oracle/ora-worktrees/chunk1-capture-integrity.diff`

## Implemented behavior

### D1: Framework runs are first-class trace parents

- CLI `run_pipeline` and server `_pipeline_stream` carry `framework_id`, `milestone_id`, and `child_refs` in turn state.
- Both production framework-command paths copy framework execution status back into turn state before manifest finalization.
- Bracketed framework parse/file/unsupported/unexpected errors finalize as `terminal_status: "error"`.
- Framework parent manifests preserve and dedupe child trace refs at append and finalization.

### D2: Collision-safe trace creation

- `pipeline_trace.start_trace` resolves same-second collisions with suffixes and atomically claims the directory with `os.mkdir`, inside upstream's safe owned trace root.

### D3: Trace pin/unpin/status affordance

- Added strict trace reference resolution in `pipeline_trace.py`.
- Added manifest-preserving helpers for pin/unpin/status.
- Added CLI actions: `pin`, `unpin`, and `status`.
- Resolution accepts only `<conversation_id>/<turn_dir>` refs that contain `trace-manifest.json`; it rejects traversal, root refs, conversation-directory refs, and symlink escapes.

### D4: Retention respects pinned traces

- The trace sweeper skips old trace directories whose manifest says `retention_state: "pinned"`.
- Missing or unreadable manifests are not treated as pinned.
- Sweep summaries include `traces_pinned_skipped`.

### D5: Capture completeness for generated model calls

- Added `model-call-config.jsonl` snapshots at physical provider-attempt boundaries.
- Added per-call metadata context so `_call_with_retry` can pass `step`, `slot`, `gear`, and `config_name` into lower-level capture.
- Snapshots redact/seal endpoint config to operational fields only: model identity, endpoint identity, sampling knobs, timeout-ish fields, reasoning effort, and a credential-safe base URL host.
- Added missing Gear 3 and Gear 4 prompt/payload captures for verifier loops, quality-gate retries, re-revisions, reconsolidations, and reformat passes.

### D6: Child traces for milestone attempts

- Each framework milestone attempt now gets its own child trace.
- Each retry gets a separate child trace.
- Child manifests include parent trace ref, framework id, milestone id, mode, and gear.
- Child attempts explicitly bind trace and tool-event context around the gear run, then restore the parent context.
- Framework-level calls outside child attempts are bound to the parent trace.
- Drift-check calls after a child attempt are bound to that child trace before child finalization.

## Focused validation

Command context: implementation worktree with `ORA_HOME` exported to the worktree root.

- `python3 -m unittest orchestrator.tests.test_trace_manifest orchestrator.tests.test_retention_sweeper`
- Result after rebase to `60b495d9948b`: 104 tests run, OK.

## Full-suite parity validation

Both runs exported `ORA_HOME` to the relevant worktree root before running test discovery.

Baseline worktree:

- Path: `/Users/oracle/ora-worktrees/chunk1-capture-integrity-baseline`
- Base: `origin/main` at `60b495d9948b`
- Full suite: 4555 tests in 296.239s
- Result: `FAILED (failures=43, errors=6, skipped=15)`

Implementation worktree:

- Path: `/Users/oracle/ora-worktrees/chunk1-capture-integrity`
- Base: `origin/main` at `60b495d9948b`
- Full suite: 4575 tests in 201.991s
- Result: `FAILED (failures=43, errors=6, skipped=15)`

Parity comparison:

- Baseline sorted FAIL/ERROR signatures: 49
- Implementation sorted FAIL/ERROR signatures: 49
- Diff result: byte-identical
- Diff artifact: `/tmp/chunk1-failerr-v4.diff` is empty because the signatures match.

## Test log artifacts

- Baseline full-suite log: `/tmp/chunk1-baseline-full-v4.log`
- Implementation full-suite log: `/tmp/chunk1-impl-full-v4.log`
- Baseline FAIL/ERROR signatures: `/tmp/chunk1-baseline-failerr-v4.txt`
- Implementation FAIL/ERROR signatures: `/tmp/chunk1-impl-failerr-v4.txt`
- Signature diff: `/tmp/chunk1-failerr-v4.diff`

## Stop point

Per protocol, this revised packet stops before commit, PR, merge, vault update, worktree pruning, or live smoke. Awaiting the Codex code-review gate verdict.
