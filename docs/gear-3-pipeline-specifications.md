# Framework — Gear 3 Pipeline Specifications

## Status and authority

This is the active as-built specification for Ora's frozen Gear 3 sequential adversarial path after the complete G1.2 campaign audit passed 198/198 in every lane. Executable truth remains in `orchestrator/boot.py`, `orchestrator/governed_process_runtime.py`, `orchestrator/router.py`, the selected named configuration, and the selected mode and F-framework files. The paired runtime reference is `docs/gear-3-pipeline-specifications.md`; its body must remain identical to this canonical body.

Gear 3 remains a distinct pipeline. It is not compressed into Gear 2 because it requires sequential independent criticism and correction; it is not Gear 4 because it uses one analyst stream rather than parallel independent analysts and does not consolidate or format two corpora. No new medium-fast global slot was added. The named configuration already exposes exact `analysis.gear3.depth` and `analysis.gear3.breadth` cells.

## Purpose

Gear 3 handles judgment-required prompts for which no specific Gear 4 analytical mode is necessary. It adds independent evaluation, evidence checks, revision, verification, and fail-closed final review while remaining materially lighter than Gear 4's parallel path.

## Entry contract

Three installed modes declare Gear 3:

| Mode | Entry condition | Governing posture |
|---|---|---|
| `general-inquiry` | Judgment is required, no specific deep mode wins, and the prompt is not primarily subjective. | Best-supported practical analysis under the universal sequential cascade. |
| `subjective-inquiry` | The question is primarily taste, preference, or aesthetic judgment and no more specific mode wins. | Make criteria and perspective explicit without pretending subjective preference is objective fact. |
| `passion-exploration` | The user supplies a curiosity seed with no deliverable and no convergence request. | Productive wandering, open questions, frontier honesty, and crystallization monitoring. |

Stage 2 selects a specific mode when the signal registry supports one. If judgment remains but no specific mode or real disambiguation conflict exists, the T0 fallback selects `subjective-inquiry` when subjective markers are present and `general-inquiry` otherwise. `passion-exploration` requires its own positive exploration signals. A prompt that can be completed by retrieval without judgment stays in Gear 2; a prompt selecting a declared deep-analysis mode proceeds to Gear 4.

## Context assembly contract

Before the sequential cascade, Ora assembles the selected mode contract, universal behavioral rules, conversation RAG, ranked concept RAG, relationship context, F-Consult results when useful, deterministic declared-tool results, attachments and annotations, style/output context, and any accepted project or governed-process binding.

The selected mode's analytical brief and verification criteria are loaded into the first analyst call. The mode cannot be preloaded before Phase A because routing has not selected it yet. Phase A failures fall back to the raw user request with an explicit transport-failure trace rather than converting provider-error prose into the prompt.

## Exact endpoint contract

- The analyst and reviser resolve only from `analysis.gear3.depth`.
- The evaluator and verifier resolve only from `analysis.gear3.breadth`.
- The final quality gate resolves the named configuration's `post_analysis.verification` cell, with the already resolved Gear 3 breadth endpoint as the path-local fallback.
- Supporting F-Consult, scan, and visual-synthesis calls resolve their declared utility cells.
- Every physical model request records step, slot, gear, named configuration, attempt, provider, and endpoint identity.
- A named configuration never falls through to the active profile or Gear 4's richer depth/breadth cells.

## Sequential execution contract

| Step | Producer or inspector | Required operation |
|---|---|---|
| 3 | Depth analyst | Produce the first complete mode-conformant analysis using the exact Gear 3 depth cell and supplemental-RAG protocol. |
| 4 | Breadth evaluator | Apply F-Evaluate's seven-section independent critique to the analyst output. A degraded evaluation becomes an explicit no-feedback condition, never fabricated critique. |
| 4.5 | Deterministic claim verification | Parse evaluator-flagged claims and gather source evidence for the reviser and verifier. Persist claim-to-source lineage. |
| 5 | Depth reviser | Apply F-Revise, account for every finding, resolve supported claims, state remaining uncertainty, and emit a `## REVISED DRAFT`. |
| 5.5 | Unflagged-claim scan | Inspect the revised draft for high-risk claims the evaluator missed and gather evidence for them. |
| 6 | Breadth verifier | Apply F-Verify and the mode's verification criteria. Classify the observation as PASS, FAIL, or BROKEN. Supported FAIL results may return to the reviser under the correction policy. |
| 6.5 | Independent final quality gate | Bind the exact candidate artifact and digest, Process Run/definition identity when present, evidence artifact, review boundary, and reviewer. Inspect the user-facing revised-draft body against every mode and universal criterion. |

Gear 3 has no consolidator and no formatter. On release it surfaces only the `## REVISED DRAFT` body, then applies the shared machinery-leak scrub as defense in depth. Analyst/reviser bookkeeping is never the user-facing deliverable.

## Correction and release contract

The domain-general correction policy permits at most three attempts, requires progress evidence, and stops when the same defect reaches the repeated-defect limit. Allowed failure directives are `REVISE`, `REPLAN`, `REDEFINE`, `ESCALATE`, and `BLOCKED`; the local gate does not issue authority by itself.

A Step 6 verifier FAIL may cause another revision only when policy permits it. BROKEN means inspection infrastructure was unavailable; it is not a quality pass. At Step 6.5, a substantive FAIL may trigger one bounded producer correction. The corrected candidate receives a new digest and must pass a fresh independent inspection. Release requires all of the following:

- final observation is PASS;
- the review call is not BROKEN;
- the exact candidate identity matches the reviewed revised-draft body;
- any governed Process Run binding remains valid and Process Coherence supports `ACCEPT`; and
- no governed-runtime integrity fault occurred.

If any condition is absent, Ora returns a typed “Deliverable withheld” result and preserves the candidate and evidence for the governed continuation route. Attempt exhaustion never converts failure to acceptance.

## Degraded operation

If neither Gear 3 endpoint resolves, Ora refuses with exact configuration-chain diagnostics. If exactly one of depth or breadth resolves, Ora may run an observable analyst-only fallback with retry and trace it as `gear3-single-model-analyst-only-fallback`. That result has not passed the sequential adversarial contract and must not be represented as equivalent to a full Gear 3 run.

Provider, evaluator, reviser, verifier, evidence, and extraction failures are recorded in step health and contingency evidence. A broken final quality gate always withholds.

## Required evidence

When tracing is enabled, the turn records raw and cleaned routing input, mode/gear identity, assembled RAG and consultation context, exact model-call cell/configuration identity, every step prompt and output, claim/evidence maps, correction attempts, candidate and review digests, PASS/FAIL/BROKEN observations, release state, contingencies, tool/visual events, cost/usage, and terminal status. Campaign fidelity evaluates only the terminal quality-gate state while preserving earlier failed inspections as the evidence for bounded correction.

## G1.2 evaluation disposition

The complete campaign scores and all targeted reruns support the existing Gear 3 mode contracts. The lowest mode scores reflected prompt/corpus mismatch, missing visual relationships, or one lane failing to execute its declared method—not a common omission in mode instructions. No evidence justified modifying `## ANALYTICAL PERSPECTIVES`, seeding speculative `## TOOLS`, or preloading a mode before routing. The pipeline changes instead bound every physical call to its exact named configuration and cell, made Phase A provider failures non-authoritative, strengthened trace/fidelity verification, and preserved fail-closed final review. Consecutive accepted target runs produced no new mode-specific finding, so Gear 3 is frozen in this shape until new trace evidence demonstrates a concrete defect.
