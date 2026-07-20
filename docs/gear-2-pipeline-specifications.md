# Framework — Gear 2 Pipeline Specifications

## Status and authority

This is the candidate as-built specification for Ora's Gear 2 single-pass path. It is not issued as the frozen G1.2 specification until the remaining premium campaign row is rerun under its exact authenticated subscription path and the final campaign audit passes. Executable truth remains in `orchestrator/boot.py`, `orchestrator/router.py`, the selected named configuration, and the selected mode file. The paired runtime reference is `docs/gear-2-pipeline-specifications.md`; its body must remain identical to this canonical body.

Gear 2 remains separate from Gear 1 because retrieval, consultation, and transformation context are load-bearing here. It remains separate from Gear 3 because it performs one response-producing pass without an adversarial review cascade. No new medium-fast global slot was needed: the installed Fast-1 selector already populates `utility.gear2_rag_lookup`, while Gear 3 owns separate depth and breadth cells.

## Purpose

Gear 2 handles bounded work whose answer or transformation can be completed in one model pass once the necessary context is assembled. It is the retrieval and structured-rendering path, not a low-quality substitute for judgment.

## Entry contract

Two installed modes declare Gear 2:

| Mode | Entry condition | Governing boundary |
|---|---|---|
| `factual-lookup` | The prompt requests information that needs retrieval and contains no judgment marker. | Retrieve and answer concisely; do not advise, rank, or infer beyond the evidence. |
| `structured-output` | The user supplies source content and asks for a faithful format, template, table, schema, or presentation transformation. | Preserve source meaning and provenance; structure rather than originate analysis. |

The raw-prompt Stage 0 detector recognizes retrieval-without-judgment before Phase A and emits `gear2_rag_dispatch` to `factual-lookup`. That result is not a direct-response bypass. A lookup that also asks what should be done, which option is better, why an outcome occurred, or how competing evidence should be weighed proceeds to analytical routing instead.

`structured-output` may be selected by the ordinary mode router or an authenticated manual mode selection. If the requested output requires new judgment not supported by the supplied source, the mode surfaces the boundary instead of silently performing the analysis.

## Context assembly contract

Gear 2 may assemble all of the following before the single model pass:

- universal behavior and anti-confabulation instructions;
- the selected mode brief, output contract, analytical perspectives, and verification criteria;
- relevant conversation RAG;
- ranked concept RAG from the vault;
- relationship-graph context derived from retrieved concepts;
- F-Consult web consultation when the consultation contract determines it is useful;
- deterministic results for tools explicitly declared by the selected mode; and
- attached-file, image, annotation, project, style, and output-destination context supplied by the caller.

F-Consult is advisory retrieval, not an authority grant. Its physical calls are bound to the named configuration's `utility.gear2_rag_lookup` cell. Deterministic tools execute only when declared by the mode and remain subject to the tool dispatcher. Model-requested tools run through the same dispatcher and typed outcome protocol.

Campaign `rag_isolation: web_only` is a measurement control, not the normal interactive contract: it deliberately suppresses local conversation, concept, and relationship RAG for comparable public captures.

## Endpoint contract

1. `extract_default_gear()` reads Gear 2 from the selected mode.
2. `resolve_single_pass_endpoint(..., gear=2)` first resolves `utility.gear2_rag_lookup` through the `fast` alias.
3. If that cell is absent, it may use `utility.step1_cleanup` only inside the same configuration as a backward-compatible cell fallback.
4. An unnamed/default turn may finally use the active endpoint. A named configuration must fail closed and may not fall through to the active profile.
5. Every response-producing call records `slot=gear2_rag_lookup`, `gear=2`, and the exact configuration identity. Supporting Phase A, F-Consult, claim scan, and visual-synthesis calls likewise carry their exact cell metadata.

## Execution contract

1. Assemble the complete context package before the response-producing call.
2. Build one model message sequence from the universal preamble, selected mode contract, assembled context, relevant history, and cleaned user request.
3. Execute `run_single_pass_with_tools()` on the exact Gear 2 endpoint.
4. Continue only through the bounded agentic tool loop when the model emits a valid tool request.
5. Return the response through visual validation, risk/output routing, trace completion, and any independently triggered Execution Review logic.

Gear 2 does not run the Gear 3 analyst, evaluator, reviser, verifier, or F-Quality cascade. The selected mode's source-fidelity and anti-confabulation rules therefore carry more weight: missing evidence must remain visible rather than being patched by unsupported prose.

## Output contract

`factual-lookup` returns a direct, sourced answer proportionate to the question and distinguishes retrieved fact from uncertainty. `structured-output` returns the requested structure, preserves substantive source atoms and visual envelopes, declares material compression or adaptation, and refuses to masquerade original analysis as formatting.

Neither output exposes pipeline labels, endpoint identities, raw tool syntax, or trace internals.

## Failure and recovery contract

- If no exact Gear 2 endpoint resolves, return a configuration failure; do not borrow a model from another named profile.
- If retrieval or consultation fails, the absence is recorded. The model must state the evidence gap or complete only the supported portion.
- A provider-error string is never accepted as cleaned user input or source content.
- A failed or denied tool call remains a typed failure, not evidence.
- If judgment becomes necessary, reroute to Gear 3 or the appropriate Gear 4 mode rather than deepening Gear 2 in place.
- If source material is incomplete for the requested transformation, request the missing source or return a bounded partial result with the gap named.

## Required evidence

With tracing enabled, Ora records routing, mode/gear identity, RAG retrieval paths and emptiness diagnoses, relationship traversal, F-Consult decisions and calls, deterministic and model-requested tool outcomes, exact physical-call configuration/cell identities, visual processing, and terminal status. Campaign fidelity accepts only path-legal primaries from the declared named configuration.

## G1.2 evaluation disposition

The accepted rerun evidence and campaign scoring to date did not justify edits to Gear 2 mode text, `## ANALYTICAL PERSPECTIVES`, or `## TOOLS`. The observed weak structured-output scores were tied to universal visual/corpus fidelity conditions or endpoint-contract defects, which were corrected in shared plumbing. No capture demonstrated that adding a deterministic tool to another mode causally improved its answer, so `argument-audit` remains the only existing tool-declaration exemplar and no speculative tool seeding was performed. This disposition remains a freeze candidate until the blocked premium row completes and the final G1.2 audit passes.
