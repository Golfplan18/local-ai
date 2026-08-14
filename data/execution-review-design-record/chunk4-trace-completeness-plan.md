# Chunk 4 Replacement Plan — Gear 1–4 Trace Completeness

Status: Approved scope reset for fresh execution and independent code review.

Planning reference: `origin/main` at `7f0c80457d6d7880413e21e7c987002d6f16a088` on 2026-07-15. The execution thread must fetch `origin/main` again and record the actual base SHA before creating its worktree.

This plan replaces the resume-from-step implementation scope. The prior Revision 8 resume design is retained only as a historical rejected design; it is not an implementation source for this plan.

## 1. Objective

Ensure that every logical pipeline stage that actually executes in Gear 1, Gear 2, Gear 3, and Gear 4 produces an accurate, inspectable trace through Ora's existing trace system.

Tracing must remain observational. It must not change prompts, model calls, provider selection, retries, fallbacks, tools, pipeline output, persistence behavior, or user-visible control flow.

The smallest acceptable outcome is a verified coverage matrix showing that current `origin/main` is already complete. If the audit finds no material gaps, implementation stops with no runtime changes.

## 2. Explicit exclusions

The following are out of scope and must not be implemented, copied, or revived:

- Resume or replay from an intermediate stage
- Checkpoint capture or state reconstruction
- Corrected or counterfactual reruns
- Resume approvals, risk clearance, operation authority, or replay protection
- Resume-specific route plans, retry policies, budgets, or cancellation tokens
- Fatal resume-control exceptions or propagation guards
- Resume CLI commands, server endpoints, or `/chat` payloads
- Trace Walk rerun/resume controls
- A shared Gear stage-runner refactor undertaken to support resume
- New generic telemetry, policy, or execution frameworks
- Refactors unrelated to a demonstrated trace-coverage gap

No code is to be salvaged or cherry-picked from `chunk4-resume-from-step`. Knowledge from that review may inform the audit, but the new implementation starts from current `origin/main`.

## 3. Definitions

### Logical pipeline stage

A named production phase that the pipeline executes as part of a Gear path. A retry, provider attempt, or worker future is not automatically a separate logical stage; it remains an event or attempt within its owning stage unless current production behavior already treats it as a first-class step.

### Trace complete

A production path is trace complete when:

1. Every logical stage that actually ran has an inspectable trace artifact or existing structured event.
2. The manifest distinguishes expected, actual, missing, derived, skipped/replaced, and contingency stages honestly.
3. Effective Gear and terminal status are accurate after degradation, fallback, pause, error, abandonment, or short circuit.
4. Trace write failure cannot change pipeline behavior.
5. Existing privacy, private-conversation, and stealth suppression rules remain intact.

### Scope boundary

This plan covers trace production, safe projection, Trace Walk read-only rendering, and export only where necessary to expose an already-recorded pipeline stage. It does not authorize new execution controls.

## 4. Worktree and baseline

The execution thread must:

1. Fetch current `origin/main`.
2. Record the fetched base SHA.
3. Create a fresh worktree and local branch, recommended as:
   - Worktree: `/Users/oracle/ora-worktrees/chunk4-trace-completeness`
   - Branch: `chunk4-trace-completeness`
4. Confirm the new worktree is clean before editing.
5. Run the relevant baseline tests and the full suite before editing.
6. Save the exact sorted baseline `FAIL`/`ERROR` signatures for parity comparison.

Do not commit, push, create a pull request, or modify the vault. After the authorized acceptance-criterion-12 amendment is complete, do not modify this plan document again.

## 5. Phase A — Read-only production audit

Before editing runtime code, re-derive every code anchor from the fetched base. Do not rely on prior design anchors or the rejected worktree.

Build a consolidated trace-coverage matrix with one row for every actual Gear path and logical stage. At minimum, each row records:

| Field | Required content |
|---|---|
| Gear | 1, 2, 3, or 4 |
| Production path | normal, retry, degradation, fallback, paused, error, abandoned, or short circuit |
| Logical stage | exact production name and code anchor |
| Execution condition | when the stage runs |
| Trace artifact/event | exact filename or event channel currently written |
| Manifest treatment | expected, actual, derived, replaced, or intentionally absent |
| Safe projection | whether Trace Walk can inspect it without raw unsafe data |
| Test evidence | existing production-path test, if any |
| Gap | none, missing trace, inaccurate manifest, inaccessible projection, or missing test |

The audit must cover:

- Gear 1 normal and bypass/direct behavior
- Gear 2 normal and bypass/direct behavior
- Gear 3 analysis, evaluation, claim verification, revision, unflagged scan, verification cycles, quality gate, recovery, and terminal output paths that exist in current production
- Gear 4 paired/parallel analysis, cross-evaluation, claim verification, revision, unflagged scan, verification cycles, consolidation, formatting, quality gate, recovery, and terminal output paths that exist in current production
- Gear degradation and Gear 4-to-lower-Gear fallback behavior
- Provider/model retries and unhealthy-output retries as events within their owning stages
- Supplemental RAG, web verification, and tool activity only to confirm that their existing events remain associated with the correct logical stage
- Server and CLI production entry points
- Completed, error, paused, abandoned, and short-circuit manifest finalization
- Private and stealth behavior

Audit exit rule:

- If no material gap exists, make no code changes. Report the completed matrix and verification evidence, then stop for review.
- If gaps exist, list only those gaps before implementation. Every code change must map to a listed matrix row.
- If closing a gap would require pipeline restructuring or a new architecture, stop and request a scope decision rather than expanding this plan.

## 6. Phase B — Minimal gap closure

Implement only gaps demonstrated by Phase A, in dependency order:

1. Gear 1 and Gear 2 trace gaps
2. Gear 3 trace gaps
3. Gear 4 normal and parallel trace gaps
4. Degradation, fallback, and exceptional terminal-path gaps
5. Manifest, safe projection, Trace Walk, or export gaps that prevent inspection of recorded stages

Implementation rules:

- Add recording at an existing production boundary; do not create a new execution boundary.
- Reuse existing `pipeline_trace` primitives and schemas where possible.
- Trace writes remain fail-open and must not alter returned values or raised exceptions.
- Do not change prompts, context assembly, model parameters, endpoint selection, call order, retries, fallback criteria, tool behavior, or output formatting.
- Do not extract or refactor Gear stage runners unless a separately approved design requires it.
- Do not add a new runtime module unless the execution thread first reports why existing trace infrastructure cannot safely hold the gap closure.
- Do not expose secrets, raw private state, credentials, unsafe attachments, or new raw prompt content through browser projections or exports.
- Keep Trace Walk read-only.
- Any file outside the expected trace surfaces and focused tests requires explicit justification in the execution report.

Expected implementation surface, only if the audit proves changes are needed:

- `orchestrator/boot.py`
- `orchestrator/pipeline_trace.py`
- `server/server.py`
- `server/static/js/trace-walk.js`
- Focused tests under `orchestrator/tests/`

This list is not permission to modify every file. Modify only the files needed for documented matrix gaps.

## 7. Phase C — Verification

Focused verification must prove, as applicable:

- Every matrix row has production-path evidence.
- Gear 1–4 normal paths record all logical stages that execute.
- Parallel Gear 4 stages retain distinct and correctly attributed traces.
- Retries remain attached to the correct logical stage without becoming fake pipeline steps.
- Degradation and fallback manifests report the effective path and do not manufacture missing-stage warnings for legitimately replaced work.
- Errors, pauses, abandonment, and short circuits receive honest terminal statuses.
- A trace-writer failure leaves pipeline calls, outputs, health, retries, and fallback behavior unchanged.
- Tracing unavailable or disabled preserves ordinary behavior.
- Private and stealth rules remain unchanged.
- Trace Walk and export render only safe, recorded information and remain read-only.
- CLI and server production entry points produce equivalent trace semantics.

Testing quality rules:

- Prefer behavioral tests through production entry points over source-text assertions.
- Do not mock the function whose integration is being claimed.
- Source inspection tests may supplement but never replace behavioral coverage.
- Run focused tests together in one process to expose module-state and import-order contamination.
- Run tests in more than one order when server/boot imports are involved.
- Vague existence assertions do not establish trace correctness; tests must read artifacts and assert exact stage identity and manifest treatment.

Parity protocol:

1. Run the same full-suite command used for baseline.
2. Sort and compare every `FAIL`/`ERROR` signature.
3. The post-change signature set must exactly equal the baseline set unless a pre-existing failure was intentionally fixed and independently demonstrated.
4. No new failure, error, hang, import-order dependency, or test-isolation signature is acceptable.
5. Run Python compilation/import checks, JavaScript syntax checks if JavaScript changed, and `git diff --check`.

## 8. Acceptance criteria

The implementation passes only when all of the following are true:

1. A complete Gear 1–4 trace-coverage matrix is delivered and matches current production code.
2. Every runtime change maps to a documented pre-change gap.
3. Every logical stage that actually executes is inspectable through the existing trace system.
4. Manifest expected/actual/missing/derived semantics are honest for normal, fallback, and exceptional paths.
5. Trace recording remains observational and fail-open.
6. Ordinary pipeline behavior and full-suite signatures retain exact parity.
7. Private and stealth behavior retain exact parity.
8. Trace Walk remains read-only.
9. No resume, checkpoint, replay, approval, correction, special budget, special route-policy, or resume cancellation feature is present.
10. No code from the rejected implementation branch was copied or cherry-picked.
11. No runtime module or architectural refactor was introduced without an explicit, approved scope decision.
12. The execution process and all of its descendants must make no writes outside the fresh implementation worktree and its designated isolated runtime root. Before/after changes caused by independent external processes do not fail acceptance when non-attribution is established through the execution process tree, resolved runtime paths, write-containment enforcement, and preserved comparison evidence. Any external write attributable to the execution, or any changed path whose attribution cannot be determined, fails acceptance.

## 9. Execution report requirements

The execution thread must stop before commit and provide:

- Updated plan link
- Fresh base SHA
- Worktree and branch
- Baseline and post-change full-suite counts
- Exact parity/signature comparison
- Completed trace-coverage matrix
- Gaps found and exact changes made for each gap
- Representative on-disk trace and manifest evidence for all four Gears
- Focused and production-entry-point test results
- Files changed
- Explicit confirmation that no rejected-branch code was copied
- Explicit confirmation that no resume-related functionality was introduced
- Any new architectural conflict discovered
- Containment evidence showing whether any outside-worktree changes occurred, their attribution, the execution process tree and resolved runtime paths, and confirmation that no outside write was caused by the execution or its descendants.

The next action after that report is an independent code-review gate, not commit or implementation expansion.

## 10. Independent judge procedure

The judge must not begin reviewing implementation until the user supplies the execution thread's final report.

After receiving the report, the judge must:

1. Read this plan in full.
2. Fetch/read the implementation's recorded base and current `origin/main`; identify any base movement without silently rebasing the reviewed diff.
3. Inspect the complete fresh-worktree diff and untracked files.
4. Re-derive production Gear 1–4 stages and compare them with the delivered matrix.
5. Verify that every changed line maps to a documented trace gap.
6. Search for prohibited resume/checkpoint/replay/approval/correction functionality and unrelated refactors.
7. Verify trace fail-open behavior, privacy behavior, manifest truthfulness, and read-only UI/export behavior against actual code.
8. Inspect tests for mocks, source-only assertions, vacuous assertions, import-order contamination, and untested production paths.
9. Run focused verification and the exact parity protocol independently.
10. Verify process-tree and runtime-path isolation, write-containment enforcement, and attribution for every outside-worktree delta. Independently attributable external activity is non-blocking; execution-attributable or unattributed changes require BLOCK.
11. Return `PASS` or `BLOCK`, with concrete findings ordered by severity.

The judge must not edit files, repair findings, commit, push, create a pull request, or broaden the scope.

## 11. Rejected-worktree cleanup policy

The rejected implementation worktree and local branch may be deleted only after verifying:

- Worktree path is exactly `/Users/oracle/ora-worktrees/chunk4-resume`.
- Branch name is exactly `chunk4-resume-from-step`.
- `git log --oneline origin/main..HEAD` contains no branch-unique commits.
- `git merge-base --is-ancestor HEAD origin/main` succeeds, or another explicit base check proves no unique commit would be lost.

Because `origin/main` may have advanced, equality between the rejected worktree's old HEAD and current `origin/main` is not required.

Cleanup must remove only the rejected local worktree and local branch. It must not push, delete a remote branch, alter the main worktree, modify the vault, or delete the historical design document at `/Users/oracle/ora-worktrees/chunk4-resume-from-step-design.md`.

## 12. Salvage decision

No implementation artifact is approved for salvage.

In particular, do not carry forward:

- `gear_runner.py`
- Resume checkpoint or approval modules
- Resume exception guards or stop-token logic
- Resume server or CLI integration
- Resume Trace Walk controls
- Resume-specific manifest/export fields
- Resume-specific tests
- `.gitignore` entries created solely for resume approval state

The only retained value is the program-level conclusion that trace completeness—not replay—is the objective. Any future reuse of an idea or code pattern requires a separate justification against a concrete gap in this plan.
