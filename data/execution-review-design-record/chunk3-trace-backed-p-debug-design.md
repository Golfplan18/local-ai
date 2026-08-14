# Chunk 3 Design: Trace-backed P-Debug and Recommend-only Correction

Status: design gate draft  
Ora base verified: `0ee92d64edf9`  
Vault state checked: pulled before reading; already up to date  
Implementation status: not started

## Scope

Chunk 3 makes Ora able to investigate a failed or suspicious turn from its captured trace instead of relying on the user to narrate what happened.

In scope:

- Extend the existing Process Inference Framework P-Debug profile so its evidence source is an exact `trace_ref` and its contract source is the executed framework or mode contract.
- Capture the execution-time contract excerpt and fingerprint needed to diagnose future traces without reinterpreting them through edited framework or mode files.
- Add a trace-backed diagnosis path that can walk from the last-known-good step to the first-bad step and classify the result into the approved finite verdict vocabulary.
- Add explicit entry points for investigation from natural language, the Trace Walk modal, and Paused-card trace links.
- Add a single-step re-execution primitive for bounded probes, but only behind risk/side-effect gating and recommend-only behavior.
- Add a recommend-only learning library for recurring trace-debug lessons, with no automatic framework edits or autonomy promotion.

Out of scope:

- Automatic framework-contract edits.
- Automatic content retrieval repair, config mutation, or ledger-based autonomy promotion.
- Chunk 4 resume UX or “continue from failing step” as a user-facing recovery path.
- Any vault edit before explicit user authorization.

## Verified ground truth

All anchors below were re-derived against Ora `0ee92d64edf9`; no old line numbers from earlier prompts were trusted.

### Trace capture and safe read surface

- `orchestrator/pipeline_trace.py` already exposes safe read helpers for browser-grade trace inspection:
  - `_trace_ref_parts()` accepts only two-part relative refs.
  - `resolve_trace_ref()` is used by projection helpers to resolve only manifest-bearing trace directories.
  - `trace_manifest_projection()` holds `_rp.conversation_lifecycle_lock(conversation_id)` while resolving and projecting the manifest.
  - `trace_step_projection()` validates a safe `step*` name, checks membership in `expected_steps ∪ actual_steps`, allows `step-health`, and holds the lifecycle lock through read.
  - `trace_export_html()` holds one lifecycle lock for the whole export snapshot.
  - `list_trace_refs()` now owns the runtime lifecycle lock while discovering and resolving refs.

Design consequence: Chunk 3 must reuse these helpers for UI-facing reads, and any deeper debug read must use the same resolve-first/no-follow/lifecycle-lock pattern rather than inventing a second reader.

### Framework contract source

- `orchestrator/framework_parser.py` parses `## MILESTONES DELIVERED` into structured `Milestone` objects with:
  - `endpoint_produced`
  - `verification_criterion`
  - `drift_check_question`
  - `gear`
  - `mode`
  - `layers_covered`
  - `required_prior`
- `orchestrator/milestone_executor.py` already uses this parser for framework execution, records selected mode, and creates parent/child trace lineage for milestone attempts.

Design consequence: framework debugging cannot safely reload the current framework file unless the executed contract was fingerprinted. Chunk 3 must capture the execution-time contract excerpt and fingerprint in the trace. Current files may be used only when their fingerprints match the recorded fingerprint. It should not ask the user to restate what the framework promised.

### Mode contract source

- Mode files under `modes/` contain `## VERIFICATION CRITERIA` sections; existing prompt-assembly tests already depend on this section shape.
- Non-framework turns record `mode` and `gear` in the trace manifest.

Design consequence: non-framework trace debugging also needs an execution-time mode-contract excerpt and fingerprint. Current mode files may be substituted only when their fingerprints match. If no execution-time contract is available and no fingerprint match can recover it, the debugger must report `CONTRACT_UNAVAILABLE` and withhold the four-way verdict rather than misusing `CONTRACT_MISMATCH`.

### Current PIF profile

- Vault canonical file: `/Users/oracle/Documents/vault/Framework — Process Inference.md`.
- Runtime framework copy: `frameworks/book/process-inference.md`.
- Current P-Debug milestone describes “Identified failure point within a broken process plus corrected path specification,” but it still assumes the user supplies expected-vs-actual process details.

Design consequence: the vault file is the source of truth for the conceptual profile, but Ora’s runtime copy must also be updated when implementation is authorized so the executing system can use the new profile. The current P-Debug contract itself must be rewritten because it assumes a broken process and corrected path; that is incompatible with `BAD_DRAW`, `CONTRACT_MISMATCH`, and `NO_DEFECT`.

### Production entry points and gates

- Server production entry: `server/server.py` `_pipeline_stream_impl` starts a trace, emits the `trace_ref`, binds turn context, and runs risk-gate handling before framework/runtime dispatch.
- CLI production entry: `orchestrator/boot.py` `run_pipeline` starts/finalizes traces and also handles risk-gate commands before runtime/framework/chat dispatch.
- Lesson from prior chunks: both production entry points must be covered wherever behavior applies.

Design consequence: natural-language trace-debug routing and single-step probes must be implemented for both server and CLI paths, or factored below both. Probe execution must pass the existing risk/side-effect gate, not just a cost check.

### Trace Walk and Paused UI anchors

- `server/static/js/trace-walk.js` currently exposes `window.OraTraceWalk.open({ trace_ref, step })` and has Close, Pin trace, and Export HTML actions.
- `server/static/js/export-toolbar.js` opens the current turn’s trace by exact assistant `trace_ref`.
- `server/static/js/review-queue-panel.js` and `server/static/js/sidebar-oversight.js` already open Paused-entry trace refs when present.
- `orchestrator/oversight_queue.py` has `PausedEntry.trace_ref`; `orchestrator/tool_events.py` derives exact refs for execution-gate Paused entries when `ctx.trace_dir` is available.

Design consequence: Chunk 3 should add an Investigate action to the existing trace affordances without weakening exact-ref semantics. Paused entries that lack an exact trace ref still omit investigation rather than guessing.

## Design

### D1. PIF Trace Debug profile

Extend the existing Process Inference Framework, not a new framework file.

The P-Debug profile will be rewritten, not merely extended, so it can honestly diagnose both defects and non-defects.

Profile changes:

- Setup: accept an exact trace investigation target, optional step hint, and optional symptom; do not require the user to assert that the process is broken.
- Endpoint: “Trace-backed diagnostic verdict and recommend-only correction bundle when a defect is localized.”
- Verification criterion: the report identifies the execution-time contract, separates structural from semantic evidence, returns one allowed verdict or `CONTRACT_UNAVAILABLE`, and applies a correction bundle only when the verdict is `DEFECT_LOCALIZED`.
- Output format: structured diagnostic report with verdict, confidence, contract checked, evidence walked, three-valued boundary table, root cause, probe recommendation, and correction bundle if applicable.
- Drift check: “Did this diagnosis stay inside captured trace evidence and the execution-time contract, without inventing a defect or requiring a correction for non-defect verdicts?”
- Layer instructions: replace “broken process” assumptions with “investigated process”; add explicit NO_DEFECT, BAD_DRAW, and CONTRACT_UNAVAILABLE branches; require PEF Lock inheritance, Silent Non-Solution Substitution guard, No-Punt escalation, and fabricated finding as a named failure mode.

The trace-backed rules:

- Evidence source: exact `trace_ref`, manifest, step projections, step-health, and parent/child lineage when present.
- Contract source for framework traces: execution-time contract excerpt and fingerprint for the recorded `framework_id`, `mode`, and `milestone_id`; current framework file only if its fingerprint matches.
- Contract source for mode traces: execution-time `## VERIFICATION CRITERIA` excerpt and fingerprint plus recorded gear; current mode file only if its fingerprint matches.
- Procedure: symptom intake, contract load, boundary walk, finite cause classification, probe only when reading cannot discriminate, verdict.
- Finite cause taxonomy: `retrieval gap`, `instruction conflict`, `evaluator miss`, `consolidation compression loss`, `model bad-draw`, `config mismatch`, `framework underspecification`.
- Verdicts: `DEFECT_LOCALIZED`, `BAD_DRAW`, `CONTRACT_MISMATCH`, `NO_DEFECT`.
- Contract availability: `CONTRACT_UNAVAILABLE` is a separate non-verdict terminal diagnostic for legacy or incomplete traces where the execution-time contract cannot be recovered. It withholds the four-way verdict.
- Correction bundle lanes: rerun recommendation, framework-file edit proposal, content-retrieval repair recommendation, config-change recommendation.
- Discipline language is copied into the profile: PEF Lock inheritance, Silent Non-Solution Substitution guard, No-Punt escalation, and fabricated finding as a named failure mode.

Vault handling:

- The design gate authorizes the shape only.
- Implementation will not touch `/Users/oracle/Documents/vault` until the user explicitly says to proceed with the vault-side edit.
- When authorized, the vault edit must happen on a vault branch, be committed, pushed, PR’d, squash-merged, and accompanied by registry maintenance if the PIF profile change is considered substantive under vault rules.

Runtime handling:

- The Ora runtime copy `frameworks/book/process-inference.md` must be updated in the implementation worktree so `/framework process-inference` can actually run the new profile.
- The vault and runtime copies must not silently diverge. The implementation packet should state their relationship explicitly.

### D2. Trace-debug context loader

Add a small Ora helper module, tentatively `orchestrator/trace_debug.py`, that prepares a bounded “debug context package” for P-Debug.

Inputs:

- `trace_ref` required.
- Optional `step_hint`, only if it resolves to a safe manifest-listed step or `step-health`.
- Optional user symptom text.

Execution-time contract capture:

- Add a bounded contract snapshot to traces at execution time, not at investigation time.
- Framework traces record complete canonical contract fields: framework id, framework file path or logical id, mode, milestone id, endpoint produced, verification criterion, drift check question, output format, gear, layers covered, required prior milestones, conditional layers, and a canonical fingerprint over the complete preserved fields.
- Mode traces record complete canonical mode-contract fields: mode id, gear, full `## VERIFICATION CRITERIA` section, and a canonical fingerprint over the complete preserved fields.
- Contract snapshots must preserve the complete canonical contract fields exactly after canonicalization. They must not truncate, redact, summarize, or otherwise alter clauses used for diagnosis.
- If a contract exceeds the permitted preservation limit, contains unsupported data, or cannot be preserved exactly, record explicit contract-capture failure metadata and no partial diagnostic contract.
- Later investigation of a trace with capture failure returns `CONTRACT_UNAVAILABLE` unless fingerprint-verified recovery can reconstruct the complete canonical fields exactly.
- Snapshots contain only contract text, not user prompt or answer content.
- Current framework/mode files may be substituted only when their canonical fingerprint equals the recorded fingerprint.
- Legacy traces without a snapshot may attempt fingerprint recovery only if enough recorded metadata exists to verify an exact match; otherwise return `CONTRACT_UNAVAILABLE`.

Behavior:

- Resolve and read through `pipeline_trace` safe primitives wherever browser-safe projection is enough.
- For deeper internal reads, hold `_rp.conversation_lifecycle_lock(conversation_id)` through resolution, manifest revalidation, and all bounded no-follow reads.
- Reject stale, malformed, traversal, symlink, non-manifest, conversation-directory, and root refs cleanly.
- Preserve exact `parent_trace_ref` and `child_trace_refs`; never infer lineage.
- Mark `terminal_status: open` traces as incomplete and diagnose only from available evidence.

Contract loading:

- If `trace_kind` is framework or child framework milestone, prefer the manifest’s execution-time contract snapshot.
- If no snapshot exists, parse the current runtime framework file only if the computed fingerprint matches recorded fingerprint material.
- If neither snapshot nor fingerprint-verified recovery exists, return `CONTRACT_UNAVAILABLE`.
- If non-framework, prefer the manifest’s execution-time mode verification snapshot.
- If no mode snapshot exists, use the current mode file only if its fingerprint matches recorded fingerprint material.
- A faithful execution that disappoints the user because the contract did not promise the expected behavior is `CONTRACT_MISMATCH`; an unavailable contract is `CONTRACT_UNAVAILABLE`.

Boundary walk:

- Compare `expected_steps`, `actual_steps`, missing steps, `step-health`, and the bounded projections for each step.
- Classify each boundary with three-valued semantics: `pass`, `fail`, or `unknown`.
- Separate structural evidence from semantic evidence. A present, healthy step file proves only that the step ran and its artifact was well-formed; it does not prove the step satisfied the contract.
- Treat semantic pass as evaluator-supported only when a captured verifier, drift check, step-health marker, or contract-specific check supports it.
- Locate last-known-good and first-bad step from captured packages and evaluator-supported evidence, not from generated intuition.
- For framework parent traces, inspect child refs as first-class execution units; each milestone child gets its own contract and terminal status.

### D3. Routing and user entry points

Add three entry paths, all converging on the same trace-debug context loader and P-Debug profile.

Natural language:

- Natural-language routing is behavior-altering and must be default-OFF behind an approved runtime flag.
- When enabled, server and CLI turn heads recognize explicit trace-debug intent only when an exact `trace_ref` is present in the user message, or when the current selected turn has an exact trace ref in the server UI path.
- Examples: “investigate trace conv/turn”, “debug why this trace failed”, “why did this run miss the framework contract”.
- Ambiguous “why did that happen?” without an exact current-turn ref remains normal chat or asks for the trace target. No guessing.

Structured payload:

- Trace Walk and Paused-card actions must submit structured data, not rely on natural-language parsing.
- Server field: add a JSON request field such as `trace_debug` with `{ trace_ref, step_hint, symptom, source }`.
- CLI command: add deterministic `/trace-debug <trace_ref> [--step <step>] [--symptom <text>]`.
- The normal turn pipeline converts this structured payload into the P-Debug context and prompt; the raw payload remains visible in trace metadata.
- The submitted conversation id must match the investigated trace ref’s conversation id. Cross-conversation investigation is rejected in Chunk 3.
- This same-conversation requirement applies to server UI, CLI, Paused-card actions, Trace Walk actions, debug turns, probe turns, and learning-library writes.
- Cross-conversation investigation is deferred to a later provenance-aware purge design.

Trace Walk modal:

- Add an “Investigate” action next to Pin trace and Export HTML.
- The action uses the modal’s loaded, generation-checked manifest and selected step.
- The action submits a normal Ora turn carrying the exact trace ref, optional selected step, and optional user symptom.
- If the trace is stale, invalid, or still loading, Investigate is disabled.

Paused-card action:

- For Paused entries with exact `trace_ref`, show “Investigate trace”.
- For Paused entries without exact `trace_ref`, omit the action rather than deriving from conversation or task id.

Implementation preference:

- Use the existing chat submission path rather than a separate debug endpoint wherever possible. The debug action should create a normal, replayable turn so the diagnosis itself gets a trace.
- If a small server route is needed only to construct a prompt payload, it must be read-only and must not bypass the standard pipeline, risk gate, or trace creation.

Trace kinds and relationships:

- Add explicit trace kinds: `trace-debug` for investigation turns and `trace-probe` for approved probe turns.
- Add `investigates_trace_ref` to debug/probe manifests to identify the trace being examined.
- Do not overload framework `parent_trace_ref` / `child_trace_refs` lineage for “investigates” relationships. Parent/child remains execution lineage only.

Trace-kind execution semantics:

- `trace-debug` is the orchestration parent for an investigation turn.
- When the investigation runs through PIF, the PIF milestone attempts remain normal `framework-milestone` child traces linked to the `trace-debug` parent through execution lineage.
- `trace-debug.expected_steps` is the normal parent-orchestration step set for a framework run plus debug-specific derived artifacts, not a replacement for child milestone expected steps.
- `trace-debug.actual_steps` records the parent turn’s actual orchestration artifacts; child milestone work remains in child manifests.
- `trace-debug.terminal_status` is `completed` only if the PIF child milestone completes successfully and its drift check passes.
- `trace-debug.terminal_status` is `error` when contract loading, debug payload validation, PIF execution, child milestone execution, or drift check fails with an error.
- `trace-debug.terminal_status` is `abandoned` if the turn exits before child completion/finalization.
- `trace-debug` manifests include `investigates_trace_ref` and may include `probe_trace_refs`, but investigation relationships are not mixed into `child_trace_refs`.
- `trace-probe` is a model-only probe turn, not a framework child.
- `trace-probe` required artifacts are immutable prepared request summary, approval id/token reference, approval digest, replay eligibility decision, effective provider/model/config, cost ceiling, risk-gate decision reference, probe request envelope digest, bounded probe result, and `investigates_trace_ref`.
- `trace-probe.expected_steps` includes preparation, approval validation, physical model attempt, result capture, and step-health.
- `trace-probe` is created only after replay eligibility and approval are valid. `NOT_REPLAYABLE`, forged, expired, mismatched, or unapproved requests fail before probe-trace creation and are recorded in the parent `trace-debug` trace.
- `trace-probe.terminal_status` is `completed` only after approval validation, physical model attempt, result capture, and inert-output finalization all succeed.
- `trace-probe.terminal_status` is `error` for invalid/expired/replayed approval, provider failure, envelope mismatch, refused replay eligibility, or result capture failure.
- `trace-probe.terminal_status` is `abandoned` if execution exits after trace creation but before a terminal result is finalized.

### D4. Single-step re-execution primitive

Add an internal primitive for probes, tentatively `trace_debug.reexecute_step_probe(...)`.

Purpose:

- Let P-Debug discriminate cases like `model bad-draw` versus `framework underspecification` when trace reading is insufficient.
- Serve as the lower-level atom Chunk 4 can later reuse for resume.

Hard constraints:

- Replay eligibility is mechanical and allowlisted.
- Default flow is prepare -> approve -> execute. No external request before the user sees cost/risk and approves.
- The existing risk/side-effect gate is mandatory. Passing the cost gate alone is not enough.
- Tool calls, filesystem writes, network side effects, and external actions are disabled by default.
- Model-only re-execution is the only automatic probe class in Chunk 3.
- Any tool/external-action step is either refused as “requires explicit re-gated action” or routed through the same execution gate used for normal risky actions.
- The primitive must be reachable from both server and CLI paths, or placed below both so they share behavior.
- Probe output is inert. It is never passed to tool parsing, execution, persistence repair, or downstream pipeline stages.
- Modified prompts are labelled `counterfactual_probe`, not replay.

Replay allowlist:

- The recorded step must contain complete messages or a complete model request envelope.
- The trace must include effective physical provider/model configuration, parameters, and token limits from `model-call-config.jsonl` or equivalent captured metadata.
- The request must be model-only, with no tools, external actions, or callbacks.
- The target provider/model must still be configured and available.
- The step artifact and request envelope must match an immutable digest computed during prepare.
- Unsupported or partial envelopes return `NOT_REPLAYABLE` and recommend whole-turn rerun or framework/content repair instead.

Approval contract:

- Prepare returns an immutable approval digest over trace identity, trace manifest fingerprint, step name, step artifact digest, prompt delta, effective configuration, cost ceiling, risk tier, and expiry.
- The digest is integrity evidence only, not authorization.
- Approval is always represented by server-authoritative pending state. A signed token may carry or identify the prepared request, but it cannot replace server-side one-time nonce/state.
- The approval record is bound to the existing risk-gate decision, conversation id, investigated trace ref, prepared request digest, cost ceiling, expiry, and requesting user/session context available to Ora.
- Execute accepts only an approval reference that resolves to valid server-side pending approval state.
- Execution atomically consumes the approval exactly once before making the physical model request.
- Replays, forged tokens, expired approvals, digest mismatches, conversation mismatches, risk-decision mismatches, and concurrent double-consumption all fail closed without a model request.
- Any mutation to trace, step, prompt delta, config, or cost ceiling invalidates approval.

Inputs:

- Exact `trace_ref`.
- Safe `step_name` from the trace step map.
- Optional bounded prompt modification supplied by the debugger.
- Probe budget/cost ceiling.

Outputs:

- A structured probe result with original step ref, attempted model/config, cost estimate, risk decision, probe status, and bounded result summary.
- No automatic correction applied to framework, retrieval config, vault content, or user files.

Trace behavior:

- A probe run creates a `trace-probe` trace so it can be inspected.
- The probe trace records `investigates_trace_ref` pointing to the investigated trace.
- It does not record the investigated trace as `parent_trace_ref`; parent/child is reserved for execution lineage.
- The probe trace conversation id must equal the investigated trace conversation id.

### D5. Learning library, recommend-only

Add a recommend-only trace-debug learning library as a non-RAG operational store, not a vault note, unless the design gate chooses otherwise.

Recommended storage:

- `data/trace-debug/learning-library.jsonl` under Ora runtime data.
- JSONL append under a shared cross-process file lock, stealth-gated, and conversation-purge aware.
- No prompt body, answer body, or vault content text.

Record shape:

- `schema_version`
- `created_at`
- `conversation_id`
- `trace_ref` and optional `step_name`
- `framework_id` plus version fingerprint when applicable
- `mode` and `gear`
- `symptom_signature`, redacted and bounded
- `root_cause` from the finite taxonomy
- `verdict`
- `correction_lane`
- `correction_summary`, redacted and bounded
- `verification_probe`, if performed
- `recurrence_count`, derived at read time from immutable observations rather than mutated in place
- `escalation_boundary`

Use rules:

- The library may recommend likely root causes or correction lanes.
- It may not auto-edit frameworks, configs, retrieval sources, or ledgers.
- Stale trace refs are allowed as historical refs but must be labelled stale if reopened later.
- NO_DEFECT entries are first-class and must be retained so the system learns not to invent defects.
- Conversation purge atomically rewrites the file under the same shared cross-process lock and removes all records carrying the purged conversation id. Tombstones must not retain private identifiers.
- Debug/probe learning entries may be written only for same-conversation investigations, so conversation purge can completely remove derived debug material in Chunk 3.
- Add an off-switch for all learning-library writes.
- Add gitignore coverage for the store.
- Document the store, purge behavior, and off-switch.

### D6. Diagnosis output contract

P-Debug should produce a compact, reviewable report:

- `Verdict`: one of the approved verdicts.
- `Confidence`: evidence-backed, not numeric theater.
- `Contract checked`: framework milestone or mode verification criteria.
- `Evidence walked`: manifest, step range, child traces if any.
- `Boundary`: last-known-good and first-bad step, or “none found”.
- `Boundary evidence`: structural and semantic state for each relevant step as `pass`, `fail`, or `unknown`.
- `Root cause`: one finite class, or “not discriminated without probe”.
- `Probe recommendation`: cost/risk estimate before any probe.
- `Correction bundle`: recommend-only action lane with concrete next step.
- `No-defect statement`: explicit when the run is faithful to contract.
- `Contract unavailable`: explicit terminal diagnostic when no execution-time contract can be verified; no four-way verdict emitted.

The output must never say a defect exists unless it can point to trace evidence plus the relevant contract clause.

## Trace doc §10 checklist

Chunk 3 adds or extends persistence in three ways: execution-time contract snapshots in trace manifests, optional probe/debug traces using the existing trace store, and a new trace-debug learning library.

### Contract snapshots

- Purpose: preserve the actual contract used at execution time so later diagnostics cannot be distorted by framework or mode edits.
- Content: bounded contract excerpts and canonical fingerprints only; no user prompt, answer body, or retrieved content.
- Preservation: complete canonical contract fields are preserved exactly or capture failure is recorded; no truncated/redacted contract may be used for diagnosis.
- Owner: existing trace manifest store.
- Retention: same as the owning trace.
- Redaction: contract text only, bounded; no private content fields.
- Stealth: follows existing trace policy.
- Purge: removed with the owning trace.
- Failure mode: if contract capture fails for a turn, later diagnosis returns `CONTRACT_UNAVAILABLE` unless fingerprint-verified recovery is possible.

### Probe traces

- Purpose: record bounded probe turns for later inspection.
- Content: normal trace artifacts for the probe run plus required probe artifacts; no parent linkage to the investigated trace.
- Relationship: `trace_kind: trace-probe` and `investigates_trace_ref`; do not use parent/child for investigation relationship.
- Conversation ownership: probe trace conversation id must equal the investigated trace conversation id for Chunk 3.
- Owner: existing trace store and retention sweeper.
- Retention: same trace-retention model as normal traces unless pinned per trace.
- Redaction: inherits trace redaction behavior.
- Stealth: disabled in stealth/private modes consistent with existing trace policy.
- Purge: existing trace purge by conversation must remove probe traces owned by that conversation.
- Failure mode: if probe trace creation fails, the probe must fail closed or run without persistence only if the user explicitly approved that behavior.

### Learning library

- Purpose: recommend-only recurrence memory for trace debugging.
- Content: bounded metadata and redacted summaries only; no raw user/model content.
- Owner: Ora runtime data, not vault RAG.
- Retention: conversation purge physically removes matching conversation records, including `NO_DEFECT` entries. Only unlinkable aggregate counts may survive if implemented explicitly.
- Redaction: write path must scrub free text and cap lengths.
- Stealth: no writes in stealth/private mode.
- Concurrency: append under a shared cross-process file lock, one JSON object per line.
- Purge mechanics: atomically rewrite under the same lock; no tombstones retaining conversation identifiers.
- Conversation ownership: debug/probe learning entries must be written only for same-conversation investigations, so conversation purge can completely remove derived debug material in Chunk 3.
- Corruption handling: malformed lines are skipped with visible diagnostic counters, never silently treated as evidence.
- User visibility: reports can cite that a similar pattern exists, but must show the current trace evidence independently.
- Migration: schema version on every line; unknown future versions ignored.

## Tests

Focused tests should cover:

- Trace-debug loader rejects malformed, traversal, stale, symlink, root, conversation-directory, and non-manifest refs.
- Contract capture records execution-time framework milestone snapshots and mode verification snapshots with fingerprints.
- Contract capture preserves complete canonical fields exactly; oversize or unpreservable contracts record capture failure and later produce `CONTRACT_UNAVAILABLE`.
- Mutation-after-run tests prove diagnostics use the snapshot, not an edited current framework/mode file.
- Legacy traces without recoverable contract snapshots return `CONTRACT_UNAVAILABLE` and emit no four-way verdict.
- Loader accepts only safe `step*` stems and `step-health` from the exact trace step map.
- Framework contract loader selects the exact `framework_id`, mode, and milestone from the manifest.
- Mode contract loader extracts `## VERIFICATION CRITERIA` and fails cleanly when absent.
- Boundary walker distinguishes structural pass/fail/unknown from semantic pass/fail/unknown and does not infer last-known-good from mere execution success.
- Framework parent debugging includes child trace terminal status and reciprocal lineage.
- Seeded broken-framework instruction returns `DEFECT_LOCALIZED` or `CONTRACT_MISMATCH` as appropriate, with concrete edit proposal and no auto-apply.
- Seeded thin retrieval returns `retrieval gap` and content-retrieval repair recommendation.
- Seeded forced bad draw returns `BAD_DRAW` and rerun recommendation.
- Clean-run control returns `NO_DEFECT`.
- Probe primitive emits cost/risk estimate before request and refuses model execution without approval.
- Probe prepare/approve/execute binds approval to immutable digest, cost ceiling, and expiry.
- Probe approval is server-authoritative, bound to the risk-gate decision, and atomically consumed once.
- Probe tests cover forged-token/reference, expired approval, replayed approval, trace/config mutation, and concurrent double-execution attempts.
- Probe replay allowlist rejects incomplete envelopes, unsupported engines, missing effective config, missing token limits, and any tool/external-action request.
- Counterfactual prompt modifications are labelled counterfactual probes, not replay.
- Probe output remains inert and never enters tool parsing or downstream execution.
- Probe primitive refuses tool/external-action replay by default.
- Probe path is available through both server and CLI entry seams.
- Learning library writes are stealth-gated, redacted, bounded, locked, and purge-aware.
- Learning library purge atomically rewrites under lock and leaves no tombstone/private identifier behind.
- Natural-language routing flag defaults OFF.
- UI tests cover Trace Walk Investigate enable/disable, exact trace payload, selected-step payload, stale manifest behavior, Paused-card action only when exact ref exists, and no out-of-order trace join.
- Same-conversation tests reject cross-conversation debug/probe requests and prove purging the investigated conversation removes debug response traces, probe traces, and learning-library entries.

Full validation after implementation must follow the kickoff protocol: focused tests, adversarial self-review, baseline-vs-implementation full-suite parity with `ORA_HOME` exported on both runs, implementation packet, and code-review gate before any landing.

## Acceptance criteria

Chunk 3 is acceptable when:

- A user can investigate an exact trace from Trace Walk or a Paused card without manually narrating the full expected/actual process.
- Natural-language investigation works only with an exact target trace and never guesses from nearby conversation state.
- Framework traces are checked against parsed milestone contracts; mode traces are checked against mode verification criteria.
- Reports can honestly produce all four verdicts, including `NO_DEFECT`.
- Legacy or incomplete traces without a verified execution-time contract produce `CONTRACT_UNAVAILABLE` instead of a four-way verdict.
- Probes never bypass risk/side-effect gating and never execute external/tool side effects by default.
- Probe approvals are mechanically bound to immutable prepared requests and expire.
- Probe approvals cannot be forged, replayed, or double-consumed.
- Correction bundles are concrete and reviewable, but nothing is auto-applied.
- Learning-library entries are recommend-only and contain no raw content.
- Learning-library recurrence counts are derived from immutable observations.
- Server and CLI production entry points both behave consistently.
- The implementation packet includes the vault/runtime PIF relationship and any vault work waits for explicit user authorization.

## Open questions for design gate

Q1. Resolved by design gate: use the non-RAG Ora store `data/trace-debug/learning-library.jsonl`, rather than vault notes.

Q2. Resolved by design gate: Chunk 3 executes model-only probes; tool and external-action replay are refused and require a later design gate.

Q3. Resolved by design gate with condition: Trace Walk “Investigate” submits a structured exact-reference payload through the normal Ora turn pipeline.

Q4. Resolved by design gate: explicit vault authorization is required. Runtime work may be prepared in isolation, but it must not land while the canonical vault PIF and runtime copy diverge.
