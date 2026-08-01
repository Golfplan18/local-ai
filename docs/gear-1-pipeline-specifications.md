# Framework — Gear 1 Pipeline Specifications

## Status and authority

This is the active as-built specification for Ora's frozen Gear 1 response path after the complete G1.2 campaign audit passed 198/198 in every lane. It describes the installed behavior; it does not replace the executable source. `orchestrator/boot.py`, `orchestrator/router.py`, the active named configuration, and `modes/simple.md` remain mechanically authoritative. The paired runtime reference is `docs/gear-1-pipeline-specifications.md`; its body must remain identical to this canonical body.

Gear 1 remains separate from Gear 2. The evaluation did not support compression: Gear 1 is a direct conversational path, while Gear 2 deliberately assembles retrieval and tool context. No new medium-fast global slot was added. The existing `utility.classification` and `utility.gear2_rag_lookup` cells already express the needed separation.

## Purpose

Gear 1 answers prompts that do not need retrieval, analytical judgment, or adversarial review. It minimizes delay and machinery while preserving the universal safety, authority, and observability boundaries.

## Entry contract

The only installed Gear 1 mode is `simple` (`modes/simple.md`, `## DEFAULT GEAR: Gear 1`). Pre-routing selects it for:

- greetings and short acknowledgements that contain no analytical signal;
- system-meta requests such as repeating the immediately prior answer;
- simple facts available without retrieval, such as local runtime facts exposed by an authorized tool;
- mechanical translation, spelling, or formatting requests; and
- explicit requests to skip analysis.

Strong direct-response triggers and tightly constrained weak triggers run on the raw prompt before Phase A. When one fires, Phase A and later mode disambiguation are skipped so prompt expansion cannot create or erase a bypass match. Stage 1 repeats the strong-trigger check as a defensive backup. A greeting plus analytical work, a retrieval-dependent current fact, or any judgment marker is not Gear 1 merely because it contains a bypass word.

Retrieval-without-judgment requests are not direct bypasses. They must retain the `gear2_rag_dispatch` identity and route to `factual-lookup` in Gear 2.

## Context contract

Gear 1 receives:

- the universal behavioral preamble and anti-confabulation discipline;
- the raw user request, or the cleaned request when the defensive Stage 1 route was used;
- relevant conversation history when supplied by the caller; and
- the `simple` routing identity, without analytical role guidance.

Concept RAG, relationship traversal, F-Consult web consultation, and deterministic per-mode tools are skipped below Gear 2. Conversation context may still be assembled because a direct response can depend on the current Dialogue. This is not permission to invent unavailable current facts: when no authorized source exists, the correct result is an explicit knowledge boundary.

## Endpoint and execution contract

1. `extract_default_gear()` reads Gear 1 from the selected mode.
2. `resolve_single_pass_endpoint(..., gear=1)` resolves the exact `utility.classification` cell.
3. A named configuration may use only that named configuration. It must not fall through to the active profile or an arbitrary registered endpoint.
4. Ora builds one message sequence from the behavioral preamble, permitted context, and user request, then calls `run_single_pass_with_tools()` with authenticated metadata: `slot=classification`, `gear=1`, and the exact configuration name. The `simple` file supplies routing identity but declares no analytical brief or role guidance.
5. The model may complete through the bounded agentic tool loop. Every requested tool still passes through the dispatcher, permission gate, scope checks, and tool-event record.
6. There is no analyst/evaluator/reviser/verifier cascade and no F-Quality final-output review in Gear 1.

The risk gate, output routing, visual validation hook, trace completion record, and Execution Review terminal logic remain applicable where their independent conditions fire. “Direct” means a single response-producing model path, not an exemption from system authority.

## Output contract

The output is a concise answer to the user's immediate request. It should not expose mode labels, gear labels, routing rationale, model identities, trace paths, or tool-call syntax. It should avoid analytical scaffolding and should state missing knowledge or unavailable system state plainly.

## Failure and recovery contract

- If the exact classification endpoint cannot resolve, the request fails closed with a configuration error; Ora does not borrow another profile's model.
- A provider failure or unhealthy response remains observable and must not be converted into a fabricated answer.
- Tool denial, error, or empty output is presented to the model as a typed outcome, not as successful evidence.
- A request discovered to require retrieval or judgment is rerouted to Gear 2, Gear 3, or a specific Gear 4 mode; Gear 1 does not simulate those paths.

## Required evidence

When tracing is enabled, the turn records pre-routing, selected mode and gear, exact configuration/cell metadata for every physical model call, tool events, visual-hook results when applicable, and terminal trace state. Campaign fidelity accepts the turn only when each recorded model call matches the primary of the exact declared cell.

## G1.2 evaluation disposition

The complete campaign evidence supports retaining the existing `simple` contract. It did not show a mode-specific defect that justified editing `## ANALYTICAL PERSPECTIVES` or adding `## TOOLS`. Preloading the final mode before Phase A was rejected because the mode is not yet known at that boundary and the first response-producing call already receives the routed mode contract. Gear 1 is frozen in this shape until new trace evidence demonstrates a concrete defect.
