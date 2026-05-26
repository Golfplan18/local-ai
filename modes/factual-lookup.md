---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-24
date modified: 2026-05-24

---

# MODE: Factual Lookup

```yaml
# 0. IDENTITY
mode_id: factual-lookup
canonical_name: Factual Lookup
suffix_rule: none
educational_name: factual lookup (retrieval, no judgment)

# 1. TERRITORY AND POSITION
territory: T0-default-judgment
gradation_position:
  axis: specificity
  value: information-only
adjacent_modes_in_territory:
  - mode_id: general-inquiry
    relationship: gear counterpart (general-inquiry handles judgment-required; this handles info-only)
  - mode_id: subjective-inquiry
    relationship: gear counterpart (subjective-inquiry handles subjective questions; this handles objective lookups)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "user wants a specific fact, status, or current value"
    - "answer is a discrete piece of information the model may not carry in training"
    - "retrieval is required, but no judgment or analysis is needed"
  prompt_shape_signals:
    - "what is the current"
    - "what's the latest"
    - "who won"
    - "weather"
    - "what's the score"
    - "is it open"
    - "what happened in <recent year>"
    - "stock price"
    - "remind me of <factual topic>"
disambiguation_routing:
  routes_to_this_mode_when:
    - "Stage 1 GEAR2_RAG_TRIGGERS match present AND no judgment markers"
    - "question is factual, may require retrieval, has no debate or evaluation component"
  routes_away_when:
    - "any judgment marker present" → general-inquiry or specific analytical mode
    - "question is subjective" → subjective-inquiry
    - "question is system-meta or no-retrieval-needed" → Stage 0 bypass
when_not_to_invoke:
  - "Question requires judgment or evaluation"
  - "Question is conversational meta (Stage 0 bypass instead)"
  - "Question fits a specific analytical mode"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: retrieval-only

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [factual_question]
    optional: [recency_constraint, source_preference]
    notes: "Applies when the user specifies how recent the answer must be or which sources are preferred."
  accessible_mode:
    required: [factual_question]
    optional: []
    notes: "Default. Mode performs retrieval against trusted sources."
  detection:
    expert_signals: ["as of", "from <source>", "per BLS", "per the latest"]
    accessible_signals: ["what's the", "what is the current", "who won"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What specifically would you like to know?'"
    on_underspecified: "Proceed with reasonable interpretation; surface the interpretation alongside the answer."

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Was the answer retrieved or model-asserted? Retrieved answers cite the source; model-asserted answers tag the recency limitation."
    failure_mode_if_unmet: silent-confabulation
  - cq_id: CQ2
    question: "If the question is time-sensitive, has the answer's freshness been stated?"
    failure_mode_if_unmet: stale-answer
  - cq_id: CQ3
    question: "If retrieval failed or returned conflicting results, has that been surfaced rather than papered over?"
    failure_mode_if_unmet: retrieval-failure-masked

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: silent-confabulation
    detection_signal: "Specific quantitative or named-entity claim presented without provenance, where training-knowledge may be stale."
    correction_protocol: flag
  - name: stale-answer
    detection_signal: "Time-sensitive answer provided without dating the source or noting training-data recency."
    correction_protocol: flag
  - name: retrieval-failure-masked
    detection_signal: "Retrieval returned nothing useful and the response substituted a plausible-sounding answer rather than acknowledging the gap."
    correction_protocol: re-frame
  - name: judgment-creep
    detection_signal: "Response begins offering recommendations or evaluations the question didn't ask for."
    correction_protocol: re-dispatch (to general-inquiry or specific analytical mode)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional: []
  foundational: []

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~10sec
escalation_signals:
  upward:
    target_mode_id: general-inquiry
    when: "If the question turns out to require judgment, escalate to general-inquiry."
  sideways:
    target_mode_id: null
    when: "Information lookups don't typically have sideways modes."
  downward:
    target_mode_id: null
    when: "Already the lightest analytical pathway."
```

## DEPTH ANALYSIS GUIDANCE

There is no depth analysis in this mode — it's single-pass retrieval. Depth instead means provenance: the response names the source, dates the information, and tags any claim that couldn't be retrieved.

## BREADTH ANALYSIS GUIDANCE

Breadth means catching the edges where the question could mean something different. If "the weather" is ambiguous about location, name the assumed location and offer alternatives. If "who won" is ambiguous about which event, name the event clearly. Otherwise the mode does not survey perspectives — that's not what factual lookup is for.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Factual Lookup is a single-pass retrieval mode — a discrete factual question, a sourced answer, no judgment or analysis. It is the T0 information-only sibling of general-inquiry (which handles questions requiring judgment) and subjective-inquiry (which handles subjective questions). The mode actively uses web search and trusted-source retrieval; depth here means provenance, not multi-perspective surveying. Length is calibrated to the question — a factual-lookup response that fills the screen has drifted into the wrong mode.

**Procedure.**

1. Interpret the question — if ambiguous (e.g., "the weather" without location), name the assumed interpretation and offer the alternatives concisely.
2. Retrieve against trusted sources when retrieval is available; otherwise reason from training knowledge.
3. Answer directly in one or two sentences — no preamble, no restating the question.
4. Tag provenance — cite the retrieved source with date, or note "from training knowledge (cutoff: <date>); verify if freshness matters."
5. State freshness for time-sensitive answers — when the answer was last updated, or the training-data cutoff.
6. Surface retrieval failures directly when retrieval returned nothing useful — "I couldn't retrieve this; here's what I can say from training: [...] but verify."
7. Stay in retrieval mode — if the question turns out to require judgment, signal re-dispatch to general-inquiry rather than offering evaluation.

**Goal.** Produce a direct factual answer with light provenance — sourced where retrieved, tagged where reasoning from training, freshness noted where time-sensitive.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — provenance present.** Was the answer retrieved or model-asserted? Retrieved answers cite the source; model-asserted answers tag the recency limitation. Failure mode if unmet: `silent-confabulation`.
- **CQ2 — freshness stated.** If the question is time-sensitive, has the answer's freshness been stated? Failure mode if unmet: `stale-answer`.
- **CQ3 — retrieval failures surfaced.** If retrieval failed or returned conflicting results, has that been surfaced rather than papered over? Failure mode if unmet: `retrieval-failure-masked`.

A passing output answers directly, names provenance (source or training-knowledge tagged), states freshness for time-sensitive answers, surfaces retrieval failures when they happen, and stays in retrieval mode rather than drifting into judgment or evaluation.

**Named failure modes.**

- *silent-confabulation* — specific quantitative or named-entity claim presented without provenance, where training-knowledge may be stale.
- *stale-answer* — time-sensitive answer provided without dating the source or noting training-data recency.
- *retrieval-failure-masked* — retrieval returned nothing useful and the response substituted a plausible-sounding answer rather than acknowledging the gap.
- *judgment-creep* — response begins offering recommendations or evaluations the question didn't ask for.

## REVISION GUIDANCE

Revise to add provenance where the draft asserts a fact without it. Revise to add a freshness note where the answer is time-sensitive. Revise to surface retrieval failure where the draft papered over a missing answer. If revision discovers the question required judgment, re-dispatch to general-inquiry rather than continuing in factual-lookup.

## CONSOLIDATION GUIDANCE

For Gear 2 single-pass operation, formal consolidation does not apply — the corpus IS the answer. The atoms are:

1. **Answer atom.** The retrieved or asserted answer to the question.
2. **Provenance atom.** Where the answer came from — retrieved source, training-knowledge, or "not found."
3. **Freshness atom — when applicable.** When the answer was last updated, or the training-knowledge cutoff.
4. **Interpretation atom — when applicable.** When the question was ambiguous, what interpretation the mode applied.

**What NOT to do:**

- Add framing the question didn't request.
- Offer evaluation or recommendation — that's judgment-creep.
- Pad the answer to feel substantial — keep responses scaled to the question.

## VERIFICATION CRITERIA

Verified means: the answer is given; provenance is named (source or training-knowledge tagged); freshness is stated for time-sensitive questions; if retrieval failed, the failure is acknowledged rather than masked. The mode does not require multi-perspective surveying, structural completeness, or analytical depth — just clean, sourced retrieval.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **direct factual answer** with light provenance. Structure:

1. **Answer.** One or two sentences carrying the answer directly. No preamble.

2. **Source / freshness note.** A brief tag — either citing the retrieved source with its date, or noting "from training knowledge (cutoff: <date>); verify if freshness matters." Inline at the end of the answer paragraph is fine.

3. **Interpretation note — when applicable.** If the question was ambiguous, one sentence stating what was assumed.

4. **Retrieval-failure note — when applicable.** If retrieval failed, state it directly: "I couldn't retrieve this; here's what I can say from training: [brief context], but verify."

**Per-section conventions:**

- Brevity is the format. A factual-lookup response that fills the screen is wrong; the mode is for direct answers.
- No conversational filler ("Great question!"). No restating the question. No section headers — the answer is short enough not to need them.
- Where the answer is genuinely complex (multiple parts, multiple options), use a compact list rather than prose. Still no preamble.

---

## DEFAULT GEAR

Gear 2

- **Expected Runtime:** ~10sec
- **Context Budget:** light

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[resource, engram]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `qualifies`, `requires`
**Deprioritize:** `analogous-to`, `parent`

*Family: retrieval. The mode actively uses web search and trusted-source retrieval — RAG is the primary content source, not a supplement.*
