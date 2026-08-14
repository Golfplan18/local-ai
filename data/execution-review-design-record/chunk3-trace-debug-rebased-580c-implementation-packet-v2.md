# Chunk 3 Corrected Implementation Packet

Status: implementation complete; stopped before commit, merge, PR, landing, live smoke, or vault edit.

## Review target

- Worktree: `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c`
- Base: `580c39e1628d3d77acb2ad1f47a2e1c594468add`
- Runtime profile changed only in the isolated worktree. The canonical vault remains untouched.
- Refreshed diff: `/Users/oracle/ora-worktrees/chunk3-trace-debug-rebased-580c-implementation-diff.patch`

## Corrections to the eight blocked findings

1. Child evidence is now accepted only when the child ref stays in the investigated conversation and the child manifest reciprocally names the investigated parent. Foreign, stale, non-reciprocal, and over-limit children produce visible unavailable markers instead of silently disappearing.

2. Probe envelopes now retain the physical `endpoint_id` and redacted base-URL host captured at the provider seam. Execution resolves that ID from current configuration and refuses missing, mutated, or unavailable provider/model/base-url configurations; it no longer overlays recorded identity onto an unrelated fallback endpoint.

3. Empty provider results and Ora error strings beginning with `[Error` are failed probe executions. They write an inert error result, write failed step health, return `error`, and finalize the probe manifest as `error`. Only a non-empty successful model string can finalize `completed`.

4. Contract snapshots are fingerprint-verified against their complete canonical fields before diagnosis. The debug budgeter never truncates contract fields. Invalid, oversized, or fingerprint-mismatched captures become `CONTRACT_UNAVAILABLE`. Mode contracts are captured from the execution-time text after runtime degradation resolves the effective gear, for both CLI and server execution paths.

5. Boundary construction now joins `step-health.json` to each manifest-listed step and honors boolean `ok` values from both step payloads and health records. Structural presence remains separate from evaluator-supported semantic pass/fail/unknown evidence.

6. Trace kinds now have explicit ownership semantics. `trace-debug` owns only `step-debug-request` and `step-debug-result`; framework milestone pipeline steps remain in milestone children. `trace-probe` requires its four probe steps plus `step-health`. CLI prepare/approve/execute turns are `trace-probe-control`; an executed probe records `investigates_trace_ref` without becoming a parent/child lineage ref.

7. The runtime P-Debug profile now uses the approved seven root-cause classes: retrieval gap, instruction conflict, evaluator miss, consolidation compression loss, model bad-draw, config mismatch, and framework underspecification. It requires exactly one four-way `VERDICT:` line when the contract is available. `CONTRACT_UNAVAILABLE` is a separate diagnostic with no four-way verdict, and prior learning is advisory only.

8. Learning validation and append now occur under one conversation lifecycle lock, so purge cannot be interleaved between validation and write. Private traces are refused, framework snapshots carry a framework fingerprint, and learning accepts only the exact four-way verdict field. Existing physical purge uses the unlocked helper while holding its outer lifecycle lock.

## Adversarial self-review

- Verified foreign-child rejection against the same-conversation and reciprocal-parent checks in the recursive trace walker.
- Verified child-count and recursion-limit paths emit explicit evidence-unavailable markers.
- Verified endpoint identity is resolved from the recorded ID and compared against current type, provider, model, and safe base-url host.
- Verified provider error and empty-result branches set probe status to `error` before finalization; interruption remains `abandoned`.
- Verified contract fingerprint and preservation-limit checks run before prompt budgeting, and contract strings are protected from generic truncation.
- Verified step-health booleans drive semantic boundary state without collapsing structural evidence into semantic proof.
- Verified parent debug artifacts and probe health artifacts are represented in the manifest expected-step table.
- Verified learning writes are lock-ordered with purge and private manifests are rejected before append.

## Tests added or updated

The focused suite includes regression coverage for foreign and non-reciprocal child refs, omitted-child markers, provider failure lifecycle, exact contract preservation, boolean health failures, trace-kind expected artifacts, private learning suppression, exact endpoint metadata, probe counterfactuals, and verdict-safe learning.

## Validation

- Focused trace/debug suite: `119` tests passed.
- Python compilation: passed for all touched Python files.
- JavaScript syntax checks: passed for all touched JavaScript files.
- `git diff --check`: passed.
- Fresh baseline full suite with `ORA_HOME` exported: `4856` tests, `34` failures, `6` errors, `19` skipped.
- Fresh implementation full suite with `ORA_HOME` exported: `4883` tests, `34` failures, `6` errors, `19` skipped.
- Sorted `FAIL`/`ERROR` signatures: `40` versus `40`, byte-identical.
- Runtime lock files under `data/` are untracked and excluded from the refreshed diff.

## Handoff boundary

This packet is ready for the next Codex code-review gate. No commit, branch publication, PR, merge, rebase, live smoke, kickoff-ledger update, or vault modification was performed.
