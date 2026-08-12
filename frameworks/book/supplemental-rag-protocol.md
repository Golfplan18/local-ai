# Specification — Supplemental RAG Protocol

*Standing instruction for analytical consumers that need a truthful way to report an evidence gap. A supplemental request promotes eligible material that the current turn already retrieved and validated but could not initially fit. It never starts a fresh query or appends an unbudgeted result.*

## Why this exists

An answer can be fluent and internally coherent while depending on a fact that the supplied package does not establish. Later evaluation cannot reliably recover evidence that was never available to the source step.

The protocol therefore gives a model one explicit non-confabulation path. It can identify the unresolved claim and its consequence. The orchestrator then considers only unseen, already-validated whole units in the turn's private deferred inventory, repacks the context within the same endpoint-safe budget, and calls the step again statelessly. If nothing eligible can improve coverage, the gap remains explicit.

## When to use it

Use the `SUPPLEMENTAL RAG REQUEST` block when all of these are true:

- A specific factual claim matters to the requested output.
- The supplied context does not establish it.
- The turn's private coverage state says relevant validated contributor or global units were deferred.
- Continuing without the evidence would require a guess or a materially qualified answer.

**Do NOT use it for:**

- Reasoning, judgment, opinion, or speculation.
- Material already present in the package.
- A new vault, web, or provider search.
- A question that actually requires the user's intent or decision.
- A request to enlarge the model endpoint's safe context budget.

## Request format

Emit the block in your response in this exact format:

```
## SUPPLEMENTAL RAG REQUEST
gap_statement: <one sentence: what claim or fact you cannot verify>
query_terms: <short relevance terms for ranking the deferred inventory>
why_it_matters: <one sentence: how the gap affects your output if unfilled>
```

Place the block at the top. `query_terms` are relevance terms used only to rank unseen, already-retrieved and already-validated units in the current private deferred inventory. They never launch a semantic, lexical, vault, web, or provider search. Do not include source identifiers or a provisional fact. The request is a control signal tied to the current inventory, not permission to expand the retrieval universe.

## Resubmission behaviour

When the orchestrator detects the block, it:

1. Uses `query_terms` to rank the current turn's private inventory of deferred, already-retrieved and already-validated units. The normalized `gap_statement` is used separately for repeat-gap detection.
2. Promotes relevant unseen contributor units first, then relevant unseen global units. Promotion preserves the original validation, privacy, ancestry, archive, and source-wide exclusion decisions.
3. Rebuilds the complete package within the **same** endpoint-safe budget. Promoted units are whole context units; nothing is truncated mid-unit.
4. Re-submits the original step as a fresh stateless call. The prior model response is not appended as evidence.

There is no fresh semantic or lexical query in this loop. Supplementation changes selection among known eligible units; it does not expand the retrieval universe.

## Caps and degradation

There is no numeric request cap. Progress and fit determine termination. The loop stops when any of these is true:

- The normalized gap repeats.
- No relevant unseen eligible unit remains.
- Eligible units exist but no whole unit fits after the ordinary packing priorities are reapplied.
- The repacked call resolves the gap and returns a normal answer.

On the first three stop conditions, the step returns a local `COVERAGE GAP` instead of requesting again:

```
## COVERAGE GAP
unresolved: <one sentence: the claim that remains unverifiable>
impact: <how this affects the analysis you are producing>
status: <repeated | no-new | no-fit>
```

The gap belongs to that call's output. It does not create a durable decision, change conversation state, or authorize a larger request. Endpoint budgeting still starts from the 200,000-token Dialogue maximum and may be smaller after required request payload, output allowance, retry, image, provider, and safety reserves.

## Anti-patterns

- **Fresh-query regression** — running another semantic, lexical, web, or provider query.
- **Append-only growth** — adding a result after packing instead of rebuilding within the same safe budget.
- **Partial-unit fitting** — clipping a turn or indexed atomic chunk to force it into the package.
- **Eligibility bypass** — promoting withheld, missing, privacy- or ancestry-incompatible, unvalidated, or otherwise excluded material. Archive bypass means promoting an archived atomic/global unit; an explicitly contributed archived Dialogue remains eligible read-only context when its ancestry and privacy permit it.
- **Identity disclosure** — exposing deferred unit IDs, titles, paths, conversation IDs, or source names in public output or ordinary trace fields.
- **Confabulation or silent omission** — guessing at the unresolved fact or dropping the affected part of the task without a named gap.
- **Unbounded repetition** — accepting a repeated request when selection did not materially change.

## Trace and observability

Public responses and the ordinary `context_coverage` projection expose only numeric coverage. The projection contains numeric entries from `budget`, each `lanes` member, and `source_counts`, plus optional integer `physical_calls`, `deferred_unit_count`, and `deduplicated_unit_count`. It has no promotion-count or terminal-status field.

Those fields must not contain unit IDs, source IDs, titles, paths, snippets, contributor identities, conversation identities, or a reconstructable ordering of private candidates. The sensitive `supplemental-rag.jsonl` forensic record retains the bounded request text and numeric outcome needed for diagnosis, under trace privacy and retention controls. Private runtime mechanics retain candidate identities for deduplication and promotion; those identities are not copied into reader-facing output or ordinary `context_coverage`.

## Where this protocol is injected

The instruction and handler are enabled only for G3/G4 analyst, evaluator, reviser, verifier, and consolidator roles. Server-authoritative history and ordinary packed context still reach Phase A, Direct, G1–G4, and special consumers, but that broader continuity contract does not enable supplementation.

| Step | Role | Injected |
|---|---|---|
| Phase A, deterministic routing, Direct, G1, and G2 | Cleanup, dispatch, and lower-gear response | No |
| G3/G4 analyst, evaluator, reviser, verifier, and consolidator | Analysis and review roles using the shared wrapper | Yes |
| Other special consumers and placement-only formatting | Consumer-specific work or presentation | No |

## Failure modes named

**The Confident Confabulator.** The model makes a specific unsupported claim instead of requesting supplementation or naming a coverage gap.

**The Fresh-Query Regression.** The orchestrator treats the request as permission to retrieve again, which changes the candidate universe and defeats bounded, auditable packing.

**The Append Overflow.** A result is tacked onto an already packed request, bypassing endpoint reserves or displacing higher-priority context implicitly.

**The Repeated-Request Loop.** The same normalized gap returns after no material coverage change. Repetition must terminate locally.

**The Identity Leak.** Public coverage or ordinary trace projections reveal which private units, sources, or conversations were considered. Numeric aggregate reporting is their boundary; the sensitive forensic request record remains private.

**The Whole-Unit Dead End.** Relevant deferred material exists but no complete unit fits. The correct result is `no-fit` plus a `COVERAGE GAP`, not truncation.

## Relationship to other frameworks

- **Phase A Prompt Cleanup** handles ambiguity in the user's prompt. Supplemental RAG handles an evidence gap inside an already packed turn.
- **Reference — Conversational RAG for Persistent AI Memory** defines eligible conversation and atomic-note candidates, privacy, ancestry, exclusions, stored documents, and vector orientation.
- **Framework — Conversation Processing Pipeline** defines the consumers and the shared endpoint-budget boundary.
- **Reference — Pipeline Trace System** defines the numeric public `context_coverage` representation.
- **Paper — Subtle-Calculation Errors in LLM Pipelines** explains why an explicit evidence-gap path is necessary.

## Status

Current protocol. The vault document is canonical; `~/ora/frameworks/book/supplemental-rag-protocol.md` is its exact body mirror.
