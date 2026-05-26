---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-15
date modified: 2026-05-24
---

# MODE: Simple

```yaml
# 0. IDENTITY
mode_id: simple
canonical_name: Simple
suffix_rule: none
educational_name: direct response (no analytical pipeline)

# 1. TERRITORY AND POSITION
territory: T-bypass
gradation: bypass
neighbors_by_gradation: []
neighbors_by_territory: []
expert_aliases: []

# 2. PIPELINE CONTRACT
pipeline_step: bypass-direct-response
expected_runtime: under-5s
context_budget: low
gear: 1

# 3. CONDITIONS
trigger_conditions:
  - "Stage 0 (pre-Phase-A) bypass check fired on raw prompt"
  - "Stage 1 bypass check fired on operational notation"
  - "user prompt is chitchat, factual lookup, system command, or prior-conversation reference"
not_appropriate_when:
  - "user prompt requests any analytical operation"

# 4. INPUT CONTRACT
input_contract:
  accessible_mode:
    required: []
    detection: "any prompt that reached this mode passed the bypass check"
  expert_mode:
    required: []
    detection: "n/a"
  graceful_degradation:
    on_missing_required: "n/a — no required inputs"
    on_underspecified: "n/a"

# 5. OUTPUT CONTRACT
output_contract:
  shape: "direct conversational response"
  required_sections: []
```

## TRIGGER CONDITIONS

Reached when the **Stage 0 Pre-Phase-A Bypass Check** or the **Stage 1 Pre-Analysis Filter** identifies the prompt as non-analytical: a greeting, a simple factual lookup ("what time is it"), a system-meta reference ("what did you just say", "repeat that"), a mechanical translation / spelling fix, or an explicit user opt-out from analysis ("don't analyze", "skip the analysis").

## EPISTEMOLOGICAL POSTURE

Direct response. The analytical pipeline (Steps 3–8 of any gear) does not run. The model produces a conversational answer using only `boot.md` as system prompt plus the user's raw prompt. No mode-specific guidance is injected because there is no analytical operation to perform.

The **anti-confabulation discipline still applies** even in bypass: if the prompt asks for a fact the model cannot verify (current time, today's date, recent events, system state), the model must say so explicitly rather than confabulating a plausible-looking answer. The Excel-formula failure class (per `Paper — Subtle-Calculation Errors in LLM Pipelines`) is the dominant risk in this mode — bypass responses are short, plausible, and often consumed at face value by the user.

## DEFAULT GEAR

Gear 1

## RAG PROFILE

```yaml
type_filter: []
context_budget: low
retrieval_approach: pre-assembled
analytical_floor_tokens: 256
conversation_history_soft_ceiling: 0.4
```

RAG is optional in bypass mode. Conversation history may be retrieved for context (resolving "that" / "the thing we discussed"); concept-RAG is skipped because no analytical operation needs vault knowledge. When concept-RAG is empty, that is the correct state — not a failure to fall back to confabulation.

## DEPTH ANALYSIS GUIDANCE

Not applicable — this mode does not run depth analysis. Bypass responses are single-pass conversational answers.

## BREADTH ANALYSIS GUIDANCE

Not applicable — this mode does not run breadth analysis.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Simple is the Stage 0 / Stage 1 bypass mode — not an analytical operation but a direct conversational response routed around the analytical pipeline. Reached when the pre-analysis filter identifies the prompt as a greeting, simple factual lookup, system-meta reference, mechanical translation, or explicit user opt-out from analysis. There is no analytical posture, no depth/breadth pass, no consolidation, no verification — the model produces a conversational answer from `boot.md` plus the user's raw prompt.

**Goal.** Produce a direct conversational response appropriate to the bypass class, with the anti-confabulation discipline applied throughout (facts the model cannot verify must be acknowledged as such, not confabulated).

**Evaluation criteria.** Not applicable — this mode does not run cross-evaluation. The only operative discipline is anti-confabulation: if the prompt asks for a fact the model cannot verify (current time, today's date, recent events, system state), the response must say so explicitly rather than fabricating a plausible-looking answer. The Excel-formula failure class is the dominant risk because bypass responses are short, plausible, and often consumed at face value.

**Named failure modes.** None formally declared — bypass is structural, not analytical. The standing risk is *confabulation-by-bypass*: a fabricated factual answer that bypasses the analytical pipeline's verification entirely.

## REVISION GUIDANCE

Not applicable — this mode does not run revision.

## CONSOLIDATION GUIDANCE

Not applicable — this mode does not consolidate.

## VERIFICATION CRITERIA

Not applicable — this mode does not run verifier checks.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **direct conversational response** appropriate to the bypass class:

- **For factual lookups** the model cannot verify (current time, today's date, recent news, user-specific system state): say so explicitly. Do not confabulate a plausible value. The honest "I don't have access to your system clock" is the correct response; a fabricated timestamp is the Excel-formula failure.
- **For greetings**: respond conversationally without forcing analytical structure.
- **For prior-conversation references** ("what did you just say"): if conversation history is available, quote or summarise the referenced exchange. If unavailable, say so.
- **For mechanical translation / spelling fixes**: perform the mechanical operation; do not editorialise.
- **For explicit opt-outs** ("don't analyze"): honour the opt-out; produce the response the user asked for without analytical scaffolding.

No section headers required. No methodology badges. The response ends when the substance ends.
