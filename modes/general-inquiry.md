---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-24
date modified: 2026-05-24

---

# MODE: General Inquiry

```yaml
# 0. IDENTITY
mode_id: general-inquiry
canonical_name: General Inquiry
suffix_rule: none
educational_name: general analytical inquiry (universal pipeline)

# 1. TERRITORY AND POSITION
territory: T0-default-judgment
gradation_position:
  axis: specificity
  value: catch-all
adjacent_modes_in_territory:
  - mode_id: subjective-inquiry
    relationship: specificity counterpart (this handles judgment-with-objective-criteria; subjective-inquiry handles judgment-without-objective-criteria)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "user is asking a question requiring judgment but the topic does not fit any specific analytical mode"
    - "ad-hoc reasoning task that needs the universal pipeline discipline but no bespoke methodology"
  prompt_shape_signals:
    - "should I"
    - "what should"
    - "is it worth"
    - "tradeoff"
    - "comparison" (without analytical-mode-specific vocabulary)
    - "help me think about" (when not curiosity-driven exploration)
disambiguation_routing:
  routes_to_this_mode_when:
    - "Stage 2 detected judgment markers but no specific analytical mode dispatched cleanly"
    - "default catch-all for judgment-required prompts"
  routes_away_when:
    - "any specific analytical mode (T1–T21) dispatches" → that mode
    - "no judgment markers, just retrieval needed" → Gear 2 RAG path
    - "purely subjective question (aesthetic, preference, taste)" → subjective-inquiry
when_not_to_invoke:
  - "A more specific analytical mode fits the prompt — prefer the specific mode"
  - "Prompt is information-only with no judgment required" → Gear 2 RAG lookup
  - "Prompt is greeting / system command / mechanical request" → Stage 0 bypass

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive-analytical

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [question_or_topic]
    optional: [context, constraints, prior_thinking, stakes]
    notes: "Applies when the prompt names constraints, stakes, or a specific decision context."
  accessible_mode:
    required: [question_or_topic]
    optional: [context]
    notes: "Default. Mode infers structure from the question itself."
  detection:
    expert_signals: ["constraints are", "the decision is between", "stakes include", "context:"]
    accessible_signals: ["should I", "what should", "help me think about", "is it worth"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the question or topic you'd like to think through?'"
    on_underspecified: "Proceed — universal scaffolding handles ambiguity."

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Is a more specific analytical mode actually appropriate here, and should this analysis recommend the user re-dispatch?"
    failure_mode_if_unmet: catch-all-overuse (analyzing in general-inquiry what should have routed to a specific mode)
  - cq_id: CQ2
    question: "Has the universal f-evaluate / f-revise / f-verify discipline been applied, or has the response leaned only on the model's freeform judgment?"
    failure_mode_if_unmet: scaffolding-bypass

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: catch-all-overuse
    detection_signal: "Prompt actually matches a specific analytical mode (cui-bono, ACH, root-cause-analysis, etc.) but routed here because Stage 2 missed the signal."
    correction_protocol: re-dispatch
  - name: scaffolding-bypass
    detection_signal: "Analysis lacks confidence-per-finding, coverage-gap acknowledgment, or methodological framing — the universal f-* discipline was not applied."
    correction_protocol: flag
  - name: false-objectivity-on-subjective
    detection_signal: "Prompt was actually a subjective question (taste, preference, aesthetic) and the analysis treated subjective claims as objective."
    correction_protocol: re-dispatch (to subjective-inquiry)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional: []
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~1min
escalation_signals:
  upward:
    target_mode_id: null
    when: "If analysis surfaces a specific analytical territory, re-dispatch to that territory's mode rather than escalating in place."
  sideways:
    target_mode_id: subjective-inquiry
    when: "Analysis discovers the question was actually subjective and false objectivity was applied."
  downward:
    target_mode_id: null
    when: "If the question is purely informational, it should have been routed to Gear 2 RAG; not a re-dispatch from inside the pipeline."
```

## DEPTH ANALYSIS GUIDANCE

Going deeper in General Inquiry means applying the universal analytical discipline — claim anchoring, coverage gap identification, confidence calibration — without bespoke methodology overhead. The depth marker is whether the analysis would survive scrutiny on the question's own terms: are claims sourced, are gaps acknowledged, is the conclusion confidence-calibrated? Resist importing methodologies (cui-bono framings, decision-theoretic structure, etc.) that don't naturally fit the question — those belong to their specific modes. The depth here is rigor at the universal level, not depth at a specific level.

## BREADTH ANALYSIS GUIDANCE

Widening the lens in General Inquiry means surfacing perspectives, constraints, or constituencies the question itself doesn't make explicit. Ask what the questioner might be missing, what's outside their stated frame, what alternative framings of the question would produce different conclusions. Breadth markers: the analysis names at least one perspective the question's framing excludes; it identifies at least one assumption the question takes for granted; it offers at least one alternative framing the questioner could choose. If breadth analysis reveals the question is actually a specific analytical type (cui-bono, frame audit, decision under uncertainty, etc.), flag the re-dispatch.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** General Inquiry is the catch-all T0 mode for judgment-required prompts that don't fit any specific analytical territory — applying the universal f-evaluate / f-revise / f-verify discipline without bespoke methodology overhead. It is distinct from factual-lookup (which handles information-only retrieval without judgment), from subjective-inquiry (which handles aesthetic / preference / taste questions without objective criteria), and from any specific analytical mode (cui-bono, ACH, root-cause-analysis, etc. — when those fit, route there). The mode's depth is universal rigor (claim anchoring, gap acknowledgment, confidence calibration), not depth at a specific methodological layer. A re-dispatch suggestion to a more specific mode is a feature, not a failure — it surfaces routing improvements.

**Procedure.**

1. Read the question and check whether a more specific analytical mode actually fits — if it does, the analysis closes with a re-dispatch suggestion to that mode.
2. Check whether the question is actually subjective (aesthetic, taste, preference) — if so, signal re-dispatch to subjective-inquiry rather than treating subjective claims as objective.
3. Frame what the question is asking — reframings or assumption checks if needed; one sentence when the question is clean.
4. Make substantive claims with provenance — anchor quantitative claims to sources or tag for external verification.
5. Surface relevant perspectives — what constituencies, frames, or assumptions the question's framing excludes.
6. Calibrate confidence per finding — naming what would change the conclusion.
7. Acknowledge coverage gaps — what the analysis couldn't resolve and why.
8. Resist importing methodology from other modes — cui-bono-flavored language, decision-theoretic scaffolding, ACH structure don't belong here; they bloat without value.
9. Where the question called for a recommendation, state it with confidence and the conditions under which it changes; otherwise omit the synthesis step.

**Goal.** Produce a structured analytical response that fits the shape of the question rather than imposing fixed sections — applying universal scaffolding discipline to anchor claims, surface perspectives, calibrate confidence, and either confirm the mode-fit or re-dispatch.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — mode fit.** Is a more specific analytical mode actually appropriate, and should this analysis recommend re-dispatch? Failure mode if unmet: `catch-all-overuse`.
- **CQ2 — universal scaffolding applied.** Has the f-evaluate / f-revise / f-verify discipline been applied, or has the response leaned only on the model's freeform judgment? Failure mode if unmet: `scaffolding-bypass`.

A passing output applies universal scaffolding discipline (claim anchoring, coverage-gap acknowledgment, confidence per finding), anchors quantitative claims to sources or tags them for external verification, surfaces perspectives the question's framing excludes, acknowledges what it couldn't cover, and either confirms general-inquiry was the right mode or surfaces a re-dispatch note to a more specific one. The re-dispatch suggestion is always a passing condition — it surfaces a routing failure rather than masking it.

**Named failure modes.**

- *catch-all-overuse* — prompt actually matches a specific analytical mode (cui-bono, ACH, root-cause-analysis, etc.) but routed here because Stage 2 missed the signal.
- *scaffolding-bypass* — analysis lacks confidence-per-finding, coverage-gap acknowledgment, or methodological framing.
- *false-objectivity-on-subjective* — prompt was actually a subjective question (taste, preference, aesthetic) and the analysis treated subjective claims as objective.

## REVISION GUIDANCE

Revise to add provenance where claims sit unanchored. Revise to add coverage acknowledgment where the analysis goes quiet on what it left out. Revise to add confidence labels where conclusions read as more certain than they are. If revision discovers the prompt should have routed elsewhere (specific analytical mode or subjective-inquiry), the revised draft surfaces this as a re-dispatch suggestion rather than continuing to analyze in general-inquiry.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a structured analytical response to the question** — claims, evidence, perspectives, and uncertainty atoms. The atoms are:

1. **Question-framing atom.** What the question is actually asking, including any reframings or assumption checks. One short atom — collapse only if the question was clean as-asked.

2. **Claim atoms.** Each substantive claim the analysis makes, with: the claim itself, the evidence or reasoning supporting it, and the confidence with explicit basis. Unanchored claims get flagged here.

3. **Perspective atoms.** Per perspective or constituency relevant to the question — what they would say or care about. Surface absent perspectives the question's framing excludes.

4. **Uncertainty atoms.** What the analysis couldn't resolve and why — missing data, irreducible value disagreement, dependence on facts outside the analyst's reach.

5. **Re-dispatch flag — when applicable.** If the analysis surfaces that the question was actually a specific analytical type (cui-bono, decision-architecture, etc.) or was actually subjective (aesthetic, taste, preference), this atom flags the better mode.

6. **Recommendation or synthesis atom.** Where the question called for a recommendation, the synthesis atom carries the recommendation with its confidence and the conditions under which it changes.

**Mode-specific bloat patterns to cut:**

- **Methodology framings borrowed from other modes** — cui-bono-flavored language, decision-theoretic scaffolding, ACH structure — these belong in their own modes; here they bloat without value.
- **False structure** — imposed sections, frameworks, or templates the question didn't call for.
- **Confidence overclaiming** — language that asserts certainty where the analysis is reasoning from priors.

**What NOT to collapse:**

- **Genuine multi-perspective tensions** — when streams surface different relevant perspectives, preserve both rather than synthesising to a single voice.
- **The re-dispatch suggestion** — if either stream noticed the question was a specific analytical type, the flag survives consolidation.

## VERIFICATION CRITERIA

Verified means: claims are anchored or tagged for external verification; coverage gaps are acknowledged; confidence is calibrated and per-finding; methodological framing is stated where the analysis takes a stance; if the question was actually subjective or actually a specific analytical type, that recognition appears in the output. A re-dispatch suggestion is always a passing condition — it surfaces a routing failure rather than masking it.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structured analytical response** that fits the shape of the question rather than imposing fixed sections. Place the consolidated-corpus atoms into prose with light structural scaffolding:

1. **Brief framing.** One short paragraph naming what the question is asking and any reframings the analysis applies. When the original question is clean, this is one sentence.

2. **Substantive analysis.** Prose body organized in whatever sections best serve the question — could be one continuous argument, could be three sections, could be a comparison table. Universal discipline applies: claims have provenance, coverage gaps are named, confidence is per-finding.

3. **Perspectives or alternative framings.** Brief section — one paragraph or a bulleted list — surfacing perspectives or framings the question's framing excludes.

4. **Recommendation or synthesis (when applicable).** When the question called for a recommendation, a brief paragraph stating the recommendation with its confidence and the conditions under which it changes. Otherwise omitted.

5. **Confidence and gaps.** A brief closing section naming the analysis's main uncertainties and what would change them.

6. **Re-dispatch note — when applicable.** If the analysis discovered the question fits a specific analytical mode better, a closing note: `**Note:** This question is well-served by [mode-id]. Re-running through that mode would surface [specific analytical depth this mode couldn't provide].` This is a feature, not a failure — it surfaces routing improvements.

**Per-section conventions:**

- The deliverable should not feel templated. The universal pipeline produces structure; the mode-specific layer here is intentionally light because the questions vary too much for fixed sections.
- Length scales with the question. Trivial judgment questions get short responses; complex ones get longer. The mode does not impose a length target.

---

## DEFAULT GEAR

Gear 3

- **Expected Runtime:** ~1min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- AGO
- CAF
- OPV
- FIP

Mental models (always loaded):
- bayesian-reasoning
- base-rate-neglect
- confirmation-bias
- bounded-rationality

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `qualifies`, `contradicts`
**Deprioritize:** `parent`, `analogous-to`

*Family: general. The mode is intentionally broad — RAG retrieval should follow the question's shape rather than mode-specific weighting.*
