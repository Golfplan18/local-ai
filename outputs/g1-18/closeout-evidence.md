# G1.18 Gate Submission — Reusable Process Authoring and Execution

Status: implementation complete; independent Gate G1.18 judgment pending. G1.20 and G1.19 have not started.

## Scope and baseline

- Runtime baseline: `b0c9edaff62b490287ec03818857edf99a7364c4` (accepted G1.16).
- Vault baseline: `5c20bfa1a2bf2ce957dc96cdfbeea3532aa51431` (G1.17 bounded deferral).
- G1.17 remains user-deferred. No Persona architecture, Persona registry/binding, MindSpec selection, relationship-blurb injection, or Persona precedence was added.
- The existing `interaction_style`/`output_style` split and honne/tatemae behavior are unchanged.
- G1.18 adds no Trigger, scheduler, outbound channel, sending, publication, activation, external-effect executor, or expanded G1.20 telemetry UI.
- The pre-existing untracked `data/conversation-manifest.jsonl.lock` remains untouched.

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
2. A strict blueprint is validated against non-effectful action and human-checkpoint grammar. Trigger, runtime-engine, Persona, MindSpec, and effectful fields are rejected.
3. Proposal and revision records are runtime-reserved and retry-safe. Concurrent delivery of one authoring identity persists one authoritative record; an unchanged proposal cannot satisfy a requested revision.
4. Principal approval binds the exact proposal ID/digest, creates a G1.1 child construction Run, constructs the definition Artifact, invokes the runtime registration bridge, independently reviews the registration receipt, applies `ACCEPT`, and explicitly promotes the exact capability.
5. Process Library exposes only the exact promoted G1.18 definition plus its input schema. The browser requires explicit current-Project confirmation before starting.
6. The public API fixes the Principal to `principal:user`, validates exact definition/project/input/profile/style bindings, and returns one deterministic restart-safe Run identity.
7. Each action persists a current-node checkpoint and bounded attempt, invokes a separate no-tools worker, stores a file-backed Artifact, and binds completion to a reserved execution record containing exact Run/definition/node/operation/attempt/context/request/response/Artifact identities.
8. A human checkpoint can be resolved only by the exact Run Principal. Denial blocks without producing the draft; failed authority changes no state.
9. Worker failure pauses at a persisted recovery point. Retry preserves completed steps, obeys the total initial-plus-correction attempt ceiling, and reauthenticates Project/Model/Style and Artifact content.
10. Independent isolated verification produces exact evidence and a reserved verification record. Artifact-only, evidence-only, generic-event, stale-context, and direct-completion paths cannot authorize `ACCEPT`.

## Email-processing proof

`user/email-processing@1.0.0` accepts exact message ID, sender, subject, and body fields. It classifies and summarizes the email, stops at the Principal checkpoint, prepares an `UNSENT DRAFT` only after approval, and independently verifies the complete result. The full positive proof uses four real separate-process worker invocations (three actions plus verification). The worker contains no sending, dispatcher, tool, shell, browser, file-write, messaging, or Process Runtime API. A denied checkpoint produces no draft and no acceptance.

## Adversarial coverage

The focused suite proves:

- strict G1.1 definition validation and normalized content identity;
- rejection of parallel-engine, Trigger, Persona, MindSpec, external-operation, duplicate-operation/output, and unproduced-required-output blueprints;
- completed real management interview binding;
- exact, concurrent-idempotent proposal records, changed revision identity, Principal approval, construction, registration receipt, independent review, and Library promotion;
- unpromoted, wrong-project, stale-definition, bad-input, and caller-selected-Principal refusal;
- existing Model Profile precedence and output Style as exact Run context, with no Persona or Trigger binding;
- Project confirmation in the browser;
- real separate-process action and full email execution;
- reserved-event, Artifact-only completion, evidence-only acceptance, and non-Principal checkpoint attacks;
- human approval and denial paths;
- checkpoint restart, output drift refusal, injected worker failure, retry without replay, completed-Run retry idempotency, and authenticated result identity;
- exact public authoring/run/checkpoint endpoints and unknown-field refusal;
- canonical/mirror body parity and tracker/Registry scope boundaries.

## Reproducible verification

All commands run from the accepted checkout on 2026-07-23 with:

```bash
cd /Users/oracle/ora-msi-central-routing
export ORA_HOME=/Users/oracle/ora-msi-central-routing
export ORA_VAULT=/Users/oracle/Documents/vault
```

Focused G1.18:

```bash
python3 -m pytest -q orchestrator/tests/test_g1_18_process_automation.py
# 25 passed, 8 subtests passed; exit 0
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
# 367 passed, 195 subtests passed; exit 0
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
  server/server.py
node --check server/static/js/process-entry.js
node --check server/static/js/process-plan-review.js
python3 scripts/verify-implementation.py --check drift
# drift PASS; all commands exit 0
```

Diff and repository integrity after the submitted commits:

```bash
cd /Users/oracle/ora-msi-central-routing
git diff b0c9edaff62b490287ec03818857edf99a7364c4..HEAD --check
test -z "$(git status --porcelain --untracked-files=all | grep -v '^?? data/conversation-manifest.jsonl.lock$')"
cd /Users/oracle/Documents/vault
git diff 5c20bfa1a2bf2ce957dc96cdfbeea3532aa51431..HEAD --check
test -z "$(git status --porcelain --untracked-files=all)"
# all exit 0
```

The default all-category `verify-implementation.py` command is not a G1.18 acceptance command: by design it still reports G1.14's seven missing twins and fourteen unreconciled framework-pair drifts, plus separately owned historical corpus checks. The bounded `--check drift` parity check passes, and this gate changes no framework pair or G1.14 queue receipt.
