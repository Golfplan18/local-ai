---
nexus: obsidian
type: mode
date created: 2026/04/24
date modified: 2026/04/24
rebuild_phase: catch-all
meta_mode: true
---

# MODE: Standard

## TRIGGER CONDITIONS

Positive:
1. The prompt requires some reasoning to answer — not just a lookup — but no conflicting frames, hidden assumptions, or real-stakes tradeoffs that warrant adversarial review.
2. Short-answer questions with a defensible single answer ("explain how X works", "walk me through Y in two paragraphs").
3. Moderate-complexity explanations, summaries, or clarifications that a single mid-tier model can produce well.
4. Any prompt the classifier cannot confidently slot into a specific analytical mode AND is not trivially simple — Standard is the catch-all.

Negative:
- IF the answer is trivially retrievable from general knowledge with no reasoning → **Simple**.
- IF the prompt requires cross-examination, commitment-revision cycles, or contradiction-detection → **Adversarial** or a specific analytical mode.
- IF the prompt names a specific analytical task (root-cause, comparison between options, forward cascade, paradigm challenge) → route to the specific mode.

## EPISTEMOLOGICAL POSTURE

Reason carefully but don't manufacture complexity. Standard answers are defensible one-shots: one model, one primary pass, RAG-supported, no adversarial review. If the question opens genuine uncertainty, say so plainly — don't hedge reflexively, but don't assert beyond what the reasoning supports.

## DEFAULT GEAR

Gear 2. Single primary model with RAG. Standard is the Gear 2 catch-all: when in doubt between Simple (Gear 1) and Standard, pick Standard; when in doubt between Standard and a specific analytical mode, pick the specific mode.

## RAG PROFILE

**Retrieve (prioritise):** sources that directly inform the question; reference material, authoritative explanations, relevant prior-conversation context.

**Deprioritise:** adversarial source pairs (dialectical material, opposing camps) — that complexity is for modes that explicitly need it.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `explains`, `defines`, `exemplifies`, `precedes`
**Deprioritise:** `contradicts`, `supersedes`, `inverts`
**Rationale:** Standard answers are expository. The relationships that matter are the ones that build up the answer, not the ones that interrogate it.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The user's question. |
| `conversation_rag` | Prior turns that frame the current question. |
| `concept_rag` | Mental models or definitions relevant to the domain. |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: moderate
analytical_floor_tokens: moderate
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

Not applicable at Gear 2. If promoted to Gear 3:

White Hat:
1. State the answer clearly and cite the reasoning.
2. Identify any assumption the answer depends on.

Black Hat:
1. Note assumptions the answer would fail under.
2. Flag any claim that went beyond what the evidence supports.

### Cascade — what to leave for the evaluator

Not the primary posture at Gear 2. If promoted:
- Make the answer's load-bearing assumption explicit in prose so the evaluator can check it.
- Name the reasoning step that is most likely to be wrong so the evaluator can scrutinize it.

### Consolidator guidance

Not applicable at Gear 2. If promoted to Gear 4, merge both streams' answers, preserving any reasoning-step disagreement as a named tension rather than averaging it away.

## BREADTH MODEL INSTRUCTIONS

Produce a clear, reasoned answer. Organize the response so the reasoning is visible but not overbuilt — the user asked a question, not for a dissertation.

Green Hat:
1. Offer the answer that best fits the prompt and the retrieved context.
2. If multiple plausible answers exist, pick the most defensible one and name the others briefly.

Yellow Hat:
1. Identify what makes the answer useful to the user.
2. Surface one practical next step if the prompt suggests the user will act on the answer.

### Cascade — what to leave for the evaluator

Not applicable at Gear 2. If promoted, leave one explicit hook for the evaluator: one sentence naming the reasoning step most open to challenge.

## EVALUATION CRITERIA

Not applicable at Gear 2 — no evaluator step. If promoted to Gear 3, universal evaluator contract applies with these additions:

### Focus for this mode

If promoted, a strong Standard evaluator prioritises:
1. **Answer directness (M1).** Did the response answer the prompt, or did it pivot to a related question?
2. **Assumption transparency (M2).** Are the answer's load-bearing assumptions named?
3. **Proportionality (C1).** Is the response length proportional to the question? Over-length is a failure in Standard.

### Suggestion templates per criterion

- **M1 (indirect answer):** `suggested_change`: "Restate the answer as the first sentence; move context to follow."
- **M2 (hidden assumption):** `suggested_change`: "Name the load-bearing assumption explicitly in a sentence beginning 'This assumes…'."
- **C1 (over-length):** `suggested_change`: "Cut by one-third; keep the claim, the reasoning, and one example. Drop restatements and hedges."

### Known failure modes to call out

- **The Padding Trap** → open: "Response restates the question, lists generalities, then answers. Cut the padding."
- **The Hidden Assumption Trap** → open: "Answer depends on an unstated premise. Name it."
- **The Essay Trap** → open: "Response is too long for the question. Match the response shape to the prompt shape."

### Verifier checks for this mode

Universal V1-V8 apply. No Standard-specific checks are required — the catch-all posture means the universal floor is the full contract.

## CONTENT CONTRACT

Prose response. Sections or headings only if the question explicitly asks for them ("give me three reasons", "compare A and B point by point"). No envelope by default.

### Reviser guidance per criterion

If promoted to Gear 3:
- **M1 (indirect answer):** lead with the direct answer; move framing after.
- **M2 (hidden assumption):** insert a one-sentence "This assumes…" clause.
- **C1 (over-length):** cut restatements and hedges; keep claim + reasoning + example.

## EMISSION CONTRACT

No envelope by default. Standard is a prose-first mode. An envelope may be emitted only if the user explicitly asks for a visual artifact (diagram, table, chart) — and in that case, route emission through the shape that fits the request.

### Envelope type

None by default. If user explicitly requests a visual, the closest-matching type from the compiler's registry.

### Emission rules

1. No `ora-visual` fence unless the user explicitly asks for a visual.
2. Prose response that directly answers the prompt.
3. Structure (lists, subheadings) only when the prompt calls for structure.

### What NOT to emit

- Unrequested envelopes.
- Unrequested subheadings or numbered lists.
- Unprompted caveats ("it's complicated", "many experts debate this").
- Restating the question before answering.

## GUARD RAILS

**Catch-all guard rail.** Standard is the fallback for prompts that don't fit a specific mode. Do not try to retrofit a specific analytical framework (root-cause, decision-under-uncertainty, etc.) onto a prompt that did not ask for one.

**No-adversarial guard rail.** Standard runs at Gear 2 — no adversarial review by default. If the prompt genuinely needs adversarial review, classification should have routed it to Adversarial or a specific mode; treating Standard as a cheaper replacement for Gear 3 is a failure of classification, not a license for Standard to skip review.

**Proportionality guard rail.** Response length tracks prompt complexity. A one-paragraph question gets a one-paragraph answer.

## SUCCESS CRITERIA

Structural (machine):
- S1: no `ora-visual` fence unless explicitly requested by user.
- S2: response is prose (no spurious `##` headings).

Semantic (LLM-reviewer, only if promoted to Gear 3):
- M1: direct answer — the prompt is addressed in the first or second sentence.
- M2: load-bearing assumptions are named when present.
- M3: no unrequested hedging or caveats.

Composite:
- C1: response length is proportional to prompt length and complexity.

```yaml
success_criteria:
  mode: standard
  version: 1
  envelope_optional: true
  no_envelope: true
  structural:
    - { id: S1, check: no_envelope_unless_requested }
    - { id: S2, check: headings_only_when_requested }
  semantic:
    - { id: M1, check: direct_answer }
    - { id: M2, check: assumptions_named }
    - { id: M3, check: no_unrequested_hedging }
  composite:
    - { id: C1, check: length_proportional_to_prompt }
  acceptance: { tier_a_threshold: 0.85,
                structural_must_all_pass: true,
                semantic_min_pass: 0.75, composite_min_pass: 0.75 }
```

## KNOWN FAILURE MODES

**The Padding Trap.** Filling the response with restatements and generalities before getting to the answer.

**The Specific-Mode Retrofit Trap.** Treating the prompt as if it were root-cause-analysis or decision-under-uncertainty when it wasn't asked for. Standard does not manufacture analytical frameworks.

**The Over-Hedge Trap.** Manufacturing uncertainty that the question did not contain.

**The Essay Trap.** Producing a five-paragraph response to a one-sentence question.

**The Gear-3-Replacement Trap.** Using Standard when the prompt genuinely needs adversarial review. This is a classification failure, not a feature.
