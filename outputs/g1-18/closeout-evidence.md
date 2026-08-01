# G1.18 Gate Submission — Reusable Process Authoring and Execution

Status: correction implementation complete; independent Gate G1.18 re-judgment pending. G1.19 and G1.20 remain unauthorized.

## Scope and baseline

- Runtime baseline: `b0c9edaff62b490287ec03818857edf99a7364c4` (accepted G1.16).
- Vault baseline: `5c20bfa1a2bf2ce957dc96cdfbeea3532aa51431` (G1.17 bounded deferral).
- First rejected G1.18 submission: runtime `4551e171011990c9581a0466e36d31c6d7f6d2aa`; vault `87ebca7671e7d81f07777292e7b71cbaed4a7d14`.
- Second rejected correction: runtime `5e8e09c11318416e94085546283302d8ebc99752`; vault `c11e743223397ea4f9ed051a049e5b3cc9311464`.
- Third rejected correction: runtime `f19472fb600fee60ab6100e25e17209596923890`; vault `fea7104d02c5af3af17a3f1f4d296c251415941f`.
- G1.17 remains user-deferred. No Persona architecture, Persona registry/binding, MindSpec selection, relationship-blurb injection, or Persona precedence was added.
- The existing `interaction_style`/`output_style` split and honne/tatemae behavior are unchanged.
- G1.18 adds no Trigger, scheduler, outbound channel, sending, publication, activation, external-effect executor, or expanded G1.20 telemetry UI.
- The pre-existing untracked `data/conversation-manifest.jsonl.lock` remains untouched.

## 2026-07-24 gate correction

The three independent findings reproduced against `4551e171` before correction:

1. A nonempty `{"result":"WRONG"}` received worker `PASS` against “must exactly equal EXPECTED.” The corrected blueprint contract rejects free-text criteria as unassessable. Each admitted structured criterion now produces an ID/kind/result/reason/observation-digest assessment; the controller independently recomputes the supported predicate, and runtime final review authenticates the complete assessment/start/attempt/result/evidence lineage. Wrong, partial, contradictory, or fabricated success cannot authorize `ACCEPT`.
2. An exception from the verification worker left the Run `running` at `final-review`. Verification now creates a pre-attempt checkpoint, consumes a bounded attempt, persists `isolated_process_verification_started`, records typed failure and a recovery checkpoint, and leaves the Run `pending`. Restart resumes only verification. Every retry is persisted; exhaustion records the final failure and routes to `BLOCKED`.
3. `enum` and other property constraints survived authoring but were not evaluated. The admitted recursive subset is now explicit and complete: object/array structure, required/no-additional fields, `enum`, `const`, string length, numeric bounds and `multipleOf`, array length/uniqueness, and object-size constraints. The same validator enforces inputs before Run creation and complete outputs before verification. Unsupported keywords fail during authoring.
4. The first correction budgeted declared action baselines plus the correction allowance but omitted the baseline final-verification attempt. The compiled total now includes every declared action baseline, one final-verification baseline, and the correction allowance. Runtime counts first attempts per segment separately from later corrections, so action retries cannot consume an unstarted action or verification baseline. Admission at either the correction allowance or total ceiling routes mechanically to `BLOCKED`; verification admission also persists a typed failure record. The exact three-action-failure sequence reaches final review with the baseline verifier still available, survives a crash/restart at that boundary, and completes on the reserved seventh attempt.
5. Generic `begin_attempt()` and `complete_attempt()` remained capable of appending G1.18 attempt records outside the segment-aware path. Both now authenticate the stored definition and reject G1.18 before mutation. G1.18 uses only paired specialized start/completion methods, each bound to the exact current action or verification node. Four generic wrong/future-node starts and generic completion of an active specialized attempt preserve the attempt counter, state digest, and record log exactly; the same attacked Run then reaches authenticated `ACCEPT`.

## G1.1 reconciliation

| Legacy G1.18 statement | Implemented disposition |
|---|---|
| Compile to executable PFF/Operations Manifest and run with `milestone_executor.py` | Compile to the strict G1.1 Process Definition schema, register by exact ID/version/content digest, and execute with `GovernedProcessRuntime`; the worker is only an actuator |
| Store Trigger on each Process Definition | Definition explicitly excludes triggers; G1.19 owns Trigger binding and scheduling |
| Store Model Profile and Style on the definition | Resolve existing Project → Process → Step → one-run Model Profile precedence and output Style into an immutable Run execution-context binding |
| Build execution and full telemetry together | Reuse existing Run records/Inspector; G1.20 retains expanded tracking/telemetry ownership |

No other conflict was found. Definition registry, Library promotion, management interview, authority grants, Artifact scope, evidence, bounded attempts, checkpoints, recovery, independent review, final transition, and Inspector compatibility all reuse the accepted G1.1 objects.

## Implemented path

1. A completed real management interview offers reusable Process authoring in the existing plan-review browser surface.
2. A strict blueprint is validated against non-effectful action and human-checkpoint grammar, the complete admitted JSON Schema subset, and a closed machine-assessable criterion grammar. Trigger, runtime-engine, Persona, MindSpec, effectful fields, unsupported schema keywords, and unassessable criteria are rejected.
3. Proposal and revision records are runtime-reserved and retry-safe. Concurrent delivery of one authoring identity persists one authoritative record; an unchanged proposal cannot satisfy a requested revision.
4. Principal approval binds the exact proposal ID/digest, creates a G1.1 child construction Run, constructs the definition Artifact, invokes the runtime registration bridge, independently reviews the registration receipt, applies `ACCEPT`, and explicitly promotes the exact capability.
5. Process Library exposes only the exact promoted G1.18 definition plus its input schema. The browser requires explicit current-Project confirmation before starting.
6. The public API fixes the Principal to `principal:user`, validates exact definition/project/input/profile/style bindings, and returns one deterministic restart-safe Run identity.
7. Each action persists a current-node checkpoint and bounded attempt, invokes a separate no-tools worker, stores a file-backed Artifact, and binds completion to a reserved execution record containing exact Run/definition/node/operation/attempt/context/request/response/Artifact identities.
8. A human checkpoint can be resolved only by the exact Run Principal. Denial blocks without producing the draft; failed authority changes no state.
9. Action or verification-worker failure completes its attempt, persists a typed failure record and recovery checkpoint, and pauses. The total attempt budget consists of all action baselines, one final-verification baseline, and the shared correction allowance; per-segment admission prevents retries from stealing later baselines. Generic attempt APIs reject G1.18 before mutation, and only the current-node-bound specialized pair may create or complete these attempt records. Retry preserves completed steps and reauthenticates Project/Model/Style, Artifact content, and verification lineage. Correction or total admission exhaustion blocks mechanically.
10. Independent isolated verification assesses every structured criterion, while the controller mechanically recomputes each result. Exact evidence and reserved start/completion records bind the criterion set, assessment set, attempt, Run, definition, result, evidence, request/response, and execution context. Artifact-only, evidence-only, generic-event, false/partial assessment, stale-context, and direct-completion paths cannot authorize `ACCEPT`.

## Email-processing proof

`user/email-processing@1.0.0` accepts exact message ID, sender, subject, and body fields. It classifies and summarizes the email, stops at the Principal checkpoint, prepares an `UNSENT DRAFT` only after approval, and independently verifies three structured criteria: deterministic input grounding, the exact unsent prefix, and authenticated absence of external effects. The full positive proof uses four real separate-process worker invocations (three actions plus verification). The worker contains no sending, dispatcher, tool, shell, browser, file-write, messaging, or Process Runtime API. A denied checkpoint produces no draft and no acceptance.

## Adversarial coverage

The focused suite proves:

- strict G1.1 definition validation and normalized content identity;
- rejection of parallel-engine, Trigger, Persona, MindSpec, external-operation, duplicate-operation/output, unproduced-required-output, unsupported-schema, and unassessable-criterion blueprints;
- input and output enforcement for the admitted recursive schema subset, including public-API `enum` and length refusal;
- completed real management interview binding;
- exact, concurrent-idempotent proposal records, changed revision identity, Principal approval, construction, registration receipt, independent review, and Library promotion;
- unpromoted, wrong-project, stale-definition, bad-input, and caller-selected-Principal refusal;
- existing Model Profile precedence and output Style as exact Run context, with no Persona or Trigger binding;
- Project confirmation in the browser;
- real separate-process action and full email execution;
- reserved-event, Artifact-only completion, evidence-only acceptance, and non-Principal checkpoint attacks;
- human approval and denial paths;
- wrong nonempty output, partially satisfied criteria, fabricated worker `PASS`, and exact criterion/result evidence binding;
- action and verification failure records, recovery checkpoints, successful restart retry without action replay, bounded verifier exhaustion, output drift refusal, completed-Run retry idempotency, and authenticated result identity;
- three failed action attempts followed by successful recovery through all baseline actions, crash/restart immediately before final verification, use of the reserved verifier baseline, and deterministic correction-admission blocking with idempotent terminal replay;
- generic wrong-node and future-node attempt starts plus generic completion of an active specialized attempt, with exact no-mutation assertions and subsequent legitimate `ACCEPT` on the same Run;
- exact public authoring/run/checkpoint endpoints and unknown-field refusal;
- canonical/mirror body parity and tracker/Registry scope boundaries.

## Reproducible verification

All commands run from the corrected checkout on 2026-07-24 with:

```bash
cd /Users/oracle/ora-msi-central-routing
export ORA_HOME=/Users/oracle/ora-msi-central-routing
export ORA_VAULT=/Users/oracle/Documents/vault
```

Focused G1.18:

```bash
python3 -m pytest -q orchestrator/tests/test_g1_18_process_automation.py
# 36 passed, 12 subtests passed; exit 0
```

Original finding and adjacent bypass closure:

```bash
python3 -m pytest -q orchestrator/tests/test_g1_18_process_automation.py \
  -k 'schema_constraints or verifier_fails or wrong_or_partially or verification_failure_restart or verification_failure_can_resume or output_schema_constraint or public_run_enforces'
# 7 passed, 29 deselected, 2 subtests passed; exit 0
```

Attempt-reservation and exact-boundary recovery closure:

```bash
python3 -m pytest -q orchestrator/tests/test_g1_18_process_automation.py \
  -k 'action_retry_allowance_reserves_verification or correction_attempt_ceiling_blocks'
# 2 passed, 34 deselected; exit 0
```

Generic attempt-API isolation and legitimate-control closure:

```bash
python3 -m pytest -q orchestrator/tests/test_g1_18_process_automation.py \
  -k 'generic_attempt_start or generic_attempt_completion'
# 2 passed, 34 deselected; exit 0
```

Accepted G1.1 kernel and Phase 1/2 adjacency plus G1.18:

```bash
python3 -m pytest -q \
  orchestrator/tests/test_process_contracts.py \
  orchestrator/tests/test_governed_process_runtime.py \
  orchestrator/tests/test_phase_1_5_governed_sources.py \
  orchestrator/tests/test_phase_1_6_programming_definition.py \
  orchestrator/tests/test_phase_1_7_kernel_trials.py \
  orchestrator/tests/test_phase_2_1_entry_routing.py \
  orchestrator/tests/test_phase_2_2_management_interview.py \
  orchestrator/tests/test_phase_2_3_plan_approval.py \
  orchestrator/tests/test_phase_2_4_delegation_attention.py \
  orchestrator/tests/test_phase_2_5_run_inspector.py \
  orchestrator/tests/test_phase_2_6_process_library_lifecycle.py \
  orchestrator/tests/test_phase_2_7_surface_boundaries.py \
  orchestrator/tests/test_phase_2_8_experience_validation.py \
  orchestrator/tests/test_g1_18_process_automation.py
# 378 passed, 201 subtests passed; exit 0
```

Model Profile/dispatcher adjacency:

```bash
python3 -m pytest -q \
  orchestrator/tests/test_g1_16_model_profiles.py \
  orchestrator/tests/test_g1_16_model_profile_api.py \
  orchestrator/tests/test_model_dispatch.py \
  orchestrator/tests/test_chunk3_per_process_config.py \
  orchestrator/tests/test_framework_elicitation.py
# 89 passed, 8 subtests passed; exit 0
```

Documentation and retained Phase 3 semantics:

```bash
python3 -m pytest -q \
  orchestrator/tests/test_phase_3_3_user_guidance.py \
  orchestrator/tests/test_phase_3_4_maintainer_reference.py \
  orchestrator/tests/test_phase_3_5_closeout.py
# 30 passed, 192 subtests passed; exit 0
```

Browser integration:

```bash
node server/static/tests/test-process-entry.js
# 26 / 26 passed; exit 0
node server/static/tests/test-process-plan-review.js
# 19 / 19 passed; exit 0
```

Compilation, JavaScript syntax, and established DCP mirror drift:

```bash
python3 -m py_compile \
  orchestrator/process_automation.py \
  orchestrator/process_automation_worker.py \
  orchestrator/governed_process_runtime.py \
  orchestrator/model_dispatch.py \
  orchestrator/process_library_lifecycle.py \
  server/app.py
node --check server/static/js/process-entry.js
node --check server/static/js/process-plan-review.js
python3 scripts/verify-implementation.py --check drift
# drift PASS; all commands exit 0
```

Diff and repository integrity after the submitted commits:

```bash
cd /Users/oracle/ora-msi-central-routing
git diff b0c9edaff62b490287ec03818857edf99a7364c4..HEAD --check
git rev-list --left-right --count '@{upstream}...HEAD'
cd /Users/oracle/Documents/vault
git diff 5c20bfa1a2bf2ce957dc96cdfbeea3532aa51431..HEAD --check
git rev-list --left-right --count '@{upstream}...HEAD'
# both diff checks exit 0; both synchronization checks print 0 0 and exit 0
```

The runtime worktree contains only the accepted pre-existing
`data/conversation-manifest.jsonl.lock`. The shared vault worktree also contains
unrelated, unstaged Engram, We Too, cleaning-log, and Daily Note changes. They are
outside G1.18, were preserved without modification or staging, and are absent from
the submitted commit ranges. This packet therefore certifies the exact committed
range, diff integrity, parity, and upstream synchronization; it does not claim
ownership or cleanliness of those user-held vault changes.

The default all-category `verify-implementation.py` command is not a G1.18 acceptance command: by design it still reports G1.14's seven missing twins and fourteen unreconciled framework-pair drifts, plus separately owned historical corpus checks. The bounded `--check drift` parity check passes, and this gate changes no framework pair or G1.14 queue receipt.
