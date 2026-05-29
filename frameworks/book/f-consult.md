# F-CONSULT — Step 2 Consultation Specification

*Universal scaffolding for step 2. Step 2 produces the **consultation package** — context drawn in parallel from multiple sources before any analyst model runs. Sources include vault knowledge, conversation history, the relationship graph, and the open web. Each chunk in the package is provenanced by source so downstream steps can weight it accordingly.*

*Loaded into: Python orchestration. No model produces the consultation package itself — Step 2 is mechanical assembly. The optional prompt-sanity check (§5) is the one place a fast model touches the package, and it produces a soft warning rather than a gate.*

*Context window relevance: the consultation package is delivered as part of the analyst's system prompt at Step 3. Subsequent steps (evaluator, reviser, verifier, consolidator, formatter) each receive a fresh window with the consultation package re-injected as appropriate; there is no token debt across steps.*

---

## Role

Step 2 is consultation. Before any analytical work begins, the pipeline gathers context from every source that might inform the answer: the vault's stored knowledge, the conversation's prior turns, the relationship graph, and the open web. This is Consultation-Augmented Generation (CAG) — the architectural generalization of RAG to any consultable source, with each chunk provenanced so the model can see where the information came from and weight it accordingly.

Step 2 does not interpret or analyze. Step 2 gathers. The interpretive work happens at Step 3 and beyond, with the consultation package as input.

## The four consultation streams

The four streams run in **parallel**. No stream blocks another; failures in one do not halt the others; partial results are acceptable and logged.

### 1. Vault concept consultation

ChromaDB query against the `knowledge` collection (engrams, resources, mental models). Type-filtered per the active mode's `RAG PROFILE` declarations. Returns ranked chunks with relationship priorities applied. Existing behavior.

### 2. Conversation consultation

ChromaDB query against the `conversations` collection. Returns prior-turn material relevant to the current prompt. Existing behavior.

### 3. Relationship consultation

Graph traversal over the relationship-property index, seeded by the chunks returned in §1. Surfaces atoms reachable by `precedes`, `enables`, `requires`, etc., per the mode's relationship-priority declarations. Existing behavior.

### 4. Web consultation

NEW. Independent web search seeded from the prompt. Returns content the analysis can use both for filling gaps the vault and the model's training do not cover, and for cross-confirming claims the analysis will make. Detailed behavior in §3.

## Web consultation behavior

### When it fires

- Gear ≥ 2 (Gear 1 and bypass paths skip).
- `web_consultation.enabled: true` in routing-config (default true — absent treated as enabled).

When the stream skips, the package's `web_rag` field is empty and the skip reason is recorded in the consultation trace; downstream sees the absence explicitly rather than confusing empty-because-skipped with empty-because-nothing-found.

### Source tiering — a weighting bias, not a filter

Two tiers:

- **Tier 1 — Approved sources.** Domain patterns declared in routing-config (`web_consultation.approved_sources`). Represents outlets the user has vetted as authoritative — government statistical agencies, established journalism, peer-reviewed venues, institutional research, primary sources. Chunks from approved sources land in the package with high weight.
- **Tier 2 — Open web.** Everything else. Chunks land with lower default weight. Open-web results are not excluded — the approved list is a weighting bias, not a gate. Breadth across sources is part of what makes consultation robust.

The model never sees the tier as a "trust this, don't trust that" directive. It sees the provenance and the weight, and reasons about source authority itself.

### Query strategy

The fast model slot (`step1_cleanup` endpoint) reads the raw prompt plus the conversation-RAG result and identifies one or more search intents. Each intent carries a **justification** — a one-line statement of why this intent matters for the analysis to come. Intents that cannot articulate a justification are dropped at the model layer. This justification gate is the anti-nitpicking mechanism: trivial intents fail to articulate why they matter and are dropped, while load-bearing intents pass through with their reasoning attached.

Queries fire in **parallel**. There is no count cap on intents. Per-query timeout (default 15s) provides failure containment; queries that exceed it are abandoned with the failure logged in the consultation trace.

Each intent's query runs through the web-search cascade (Tavily → Brave → DDG by default). When semantic augmentation is enabled (`semantic_augment` in `routing-config.json`) and the semantic provider's key is present, the consultation step also runs an Exa (neural / semantic) search for the same query and merges the results — so each intent draws on both keyword and semantic retrieval rather than keyword alone. This is a no-op when the feature is disabled or the provider is unkeyed, so a clean install consults keyword search only. Note that claim verification (Step 5) deliberately does **not** augment — verifying a specific factual claim wants keyword precision, not semantic similarity.

### Provenance per chunk

Every chunk in the web-RAG portion of the package carries:

- `source: web` (distinguishing it from `vault`, `conversation`, `relationship`)
- `origin_url`
- `source_tier: approved | open`
- `retrieved_at` (ISO timestamp)
- `weight` (numeric; approved sources weight higher by default)
- `intent_justification` (the one-line reason the query was issued)

Downstream steps respect the provenance. Higher-weighted chunks are preferred for primary grounding; lower-weighted chunks are corroborating. Two independent web sources reporting the same fact carry more confidence than one approved source alone.

### Duplication is a feature, not noise

When web consultation returns content that duplicates vault knowledge or what general training would supply, the duplication is signal, not redundancy. Three independent confirmations of the same fact (vault + approved web + training) is exactly what justifies treating the fact as solid. The provenance markers make duplication legible to downstream — the analyst can see "this claim has triple-source coverage" versus "this claim has only one source, weight it accordingly."

### Contradiction surfaces, doesn't resolve

When a web-RAG chunk contradicts a vault-RAG chunk, the conflict is flagged on the web chunk (`consultation_conflict: true`, `conflicts_with: <vault chunk reference>`). Step 2 does not adjudicate the conflict — that's analytical work that belongs at Step 4 (evaluator surfaces the tension as a flagged claim) and Step 5 (reviser resolves it via additional web verification). The flag travels with the chunk to make the conflict visible to every downstream step.

## Prompt-sanity check (light, advisory)

The user's prompt itself can carry factual errors — a typo on a date, a mis-remembered statistic, a wrong attribution. Catching these at Step 2 saves a full pipeline turn of work built on a wrong premise.

### When it fires
- `web_consultation.prompt_sanity.enabled: true` in routing-config (default true).
- Gear ≥ 2.

### What it does
One fast-model call reads the prompt and flags any surface-level factual errors it can identify with high confidence. Output: a list of `prompt_sanity_flags`, each with the suspect claim, the suspected error, and a short reasoning line.

### What it does NOT do
- Does not block the pipeline. Flags are advisory, not gating.
- Does not verify deep claims, contested claims, or anything requiring web search. Those go through Step 5.
- Does not annotate substantive disputed claims as errors. A user prompt asserting the Big Bang theory is wrong is NOT a prompt error; it is a substantive position. The sanity check operates on narrow, checkable surface facts only — the same narrow definition that governs the rest of the fact-verification framework.

### Output
The prompt-sanity flags travel with the consultation package as a small structured block. The analyst sees them; if a flag is correct, the analyst can adjust its interpretation. If incorrect, the analyst can ignore it — the flag is not authoritative.

## The consultation package

The output of Step 2 is a structured assembly with the following components, each provenanced:

- `vault_rag` — vault concept consultation chunks
- `conversation_rag` — conversation consultation chunks
- `relationship_rag` — relationship-graph chunks
- `web_rag` — web consultation chunks with tier, URL, retrieval timestamp, weight, intent justification, and any conflict flags
- `prompt_sanity_flags` — prompt-level error advisories (may be empty)
- `consultation_trace` — operational metadata: which streams ran, latency per stream, failures per stream, query intents issued and their justifications

The full package is injected into the Step 3 analyst's system prompt. Downstream steps receive the package re-injected in their fresh windows — there is no carry-over token debt.

## Named failure modes

**The Single-Source Crutch.** Treating one stream as the authoritative truth. CAG's value is in cross-stream — falling back to vault-only when the web stream is empty re-introduces the rot-perpetuation problem the framework was designed to prevent. When a stream fails, the failure is logged, the analyst sees the gap, and downstream weighting adjusts. The analyst does not pretend the failed stream confirmed.

**The Unprovenanced Smuggle.** A chunk reaches downstream without its source markers. Without provenance, downstream cannot weight, distinguish, or audit. Every chunk in every stream carries provenance — no exceptions.

**The Web-Trust-Override.** Treating web content as authoritative because it is external. The approved-source weighting addresses this for known-good outlets; open-web content carries appropriately lower weight. The analyst is not instructed to trust web content over vault content — it is instructed to read the provenance and weight accordingly.

**The Failed-Search Cover.** A web query times out or returns nothing, and the consultation package proceeds as if no query was issued. This hides the gap from downstream. Failed queries always appear in the consultation trace so downstream can see what was attempted and what failed.

**The Premature Resolution.** Resolving a web-vault contradiction during Step 2 by picking a winner. Step 2 surfaces the conflict; it does not adjudicate. The conflict is data for Step 4 and Step 5.

**The Sanity-Check Overreach.** The prompt-sanity check flagging substantive disputed positions as factual errors. Sanity check operates only on narrow surface-checkable facts. Disputed-theory content, contested interpretations, and contrarian positions pass through untouched; those are substantive material for the analyst to engage with, not error to be corrected.

**The Anti-Nitpicking Bypass.** Web-consultation intents reaching the query layer without an articulated justification. The justification gate is what prevents runaway intent enumeration; bypassing it (e.g. by allowing intents in without the one-line reason attached) reintroduces the failure the cap-based approach was designed against.

## Where mode-specific content lives

This file is universal scaffolding. Modes may declare relevant overrides in their YAML:

- **`web_consultation_priority: high | default | low`** — modes can up- or down-weight the web stream relative to vault. News modes default to `high`; philosophical modes that benefit little from web verification may declare `low` (the web stream still runs by default, but its weight is reduced in the package).
- **`approved_sources_override:`** — modes may declare a mode-specific approved-source list when the global list is wrong-shaped for the mode's domain (e.g., MSI's news modes may declare an approved list of journalism outlets distinct from the global default).

Modes that need neither leave both fields absent and inherit global behavior. There is no per-mode equivalent of `## CONSULTATION GUIDANCE` because Step 2 is mechanical — the consultation behavior does not vary by mode beyond the weighting overrides above.
