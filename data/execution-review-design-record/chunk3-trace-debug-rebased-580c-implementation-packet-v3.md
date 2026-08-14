# Ora Trace Walk Chunk 3 implementation packet v3

## Scope

This packet implements the latest reviewed corrections for Chunk 3 trace-backed P-Debug and model-only probes. It is based on current `origin/main` `f2a7385beb9391050adebc1333af7d160c930cf2`, rebased from the previously reviewed implementation.

## Latest block findings addressed

1. Aggregate trace-debug contraction now marks omitted child execution-time contracts unavailable instead of silently dropping them.
2. Mode contract capture is refreshed from the final `step-health.json` gear in both CLI and server pipeline completion paths, using the already loaded mode text.
3. Probe execution binds the probe trace directory, current step, call metadata, privacy tag, and tool-event context around the model executor, then restores the caller context.
4. Server probe preparation and execution carry the source trace privacy tag; probe traces inherit private redaction policy.
5. Direct P-Debug prompt wording and the runtime PIF agree that the four verdicts are `DEFECT_LOCALIZED`, `BAD_DRAW`, `CONTRACT_MISMATCH`, and `NO_DEFECT`; `CONTRACT_UNAVAILABLE` is a terminal diagnostic only, and prior learning is advisory.
6. Probe relationships use `probe_trace_refs`, not framework child lineage. Probe event records preserve prepare rejection, approval rejection, approval, and preparation outcomes, and the trace walker includes successful probe traces and probe events.
7. Framework fingerprints include an execution-time source digest. Prior learning is filtered by compatible framework and contract fingerprints.
8. CLI probe parsing stops `--delta` before `--cost-ceiling`; prompt deltas are bounded and rejected when oversized.

## Tests and validation

- Focused suite: `125` passed.
- Full baseline at `f2a7385b`: `4,992` tests, `34` failures, `6` errors, `19` skips.
- Full implementation: `5,025` tests, `34` failures, `6` errors, `19` skips.
- Sorted `FAIL`/`ERROR` signatures: `40` versus `40`, byte-identical.
- Python compilation: passed for touched Python modules.
- JavaScript syntax checks: passed for touched browser modules.
- `git diff --check`: passed.

The implementation test count is higher because the packet adds permanent regression tests for the reviewed cases. The two runtime `data/*.lock` files remain untracked and are excluded from the supplied diff.

## Landing state

- Work remains in the isolated worktree `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c`.
- No commit, branch publication, pull request, merge, live smoke, or vault edit was performed.
- The packet is ready for the user-run Codex code-review gate.
