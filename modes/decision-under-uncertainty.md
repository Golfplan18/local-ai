---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-24

---

# MODE: Decision Under Uncertainty

```yaml
# 0. IDENTITY
mode_id: decision-under-uncertainty
canonical_name: Decision Under Uncertainty
suffix_rule: analysis
educational_name: decision analysis under uncertainty (probability and time-weighted)

# 1. TERRITORY AND POSITION
territory: T3-decision-making-under-uncertainty
gradation_position:
  axis: depth
  value: thorough
adjacent_modes_in_territory:
  - mode_id: constraint-mapping
    relationship: depth-light sibling (deterministic tradeoffs)
  - mode_id: multi-criteria-decision
    relationship: complexity sibling (multi-criteria weighting)
  - mode_id: decision-architecture
    relationship: depth-molecular sibling (full molecular orchestration)
  - mode_id: real-options-decision
    relationship: specificity counterpart (staged investment) — gap-deferred
  - mode_id: ethical-tradeoff
    relationship: stance counterpart (normative + values-laden) — gap-deferred

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "a choice must be made between alternatives with uncertain outcomes"
    - "probabilities matter but are not precisely known"
    - "the cost of being wrong is high"
    - "should we act now or wait"
    - "is it worth waiting for more information"
  prompt_shape_signals:
    - "expected value"
    - "decision tree"
    - "should we wait"
    - "value of information"
    - "downside of each option"
disambiguation_routing:
  routes_to_this_mode_when:
    - "probabilities and time-value are central to the choice"
    - "the option to defer or buy information has value worth assessing"
  routes_away_when:
    - "tradeoffs are deterministic; no probability arithmetic needed" → constraint-mapping
    - "user wants to compare multiple weighted criteria" → multi-criteria-decision
    - "decision is a molecular orchestration with stakeholders + risk + future" → decision-architecture
    - "user wants to explore multiple possible futures rather than make one decision now" → scenario-planning (T6)
    - "user wants to understand which explanation fits the evidence" → competing-hypotheses (T5)
when_not_to_invoke:
  - "User has already chosen and wants execution" → Project Mode
  - "Decision involves active negotiation between parties" → T13 negotiation
  - "Question is 'what could go wrong' along a causal cascade" → consequences-and-sequel (T6)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [decision_context, candidate_alternatives_named, probability_estimates_or_ranges, utility_units]
    optional: [base_rate_data, prior_decisions_in_similar_contexts, value_of_information_estimates]
    notes: "Applies when user explicitly carries probabilities, payoffs, and decision theory vocabulary."
  accessible_mode:
    required: [decision_or_choice_situation, sense_of_what_is_uncertain]
    optional: [hint_at_some_alternatives, time_pressure_or_deadline]
    notes: "Default. Mode elicits probabilities (or ranges or qualitative bands), surfaces defer/sequence/hedge alternatives, and supplies utility units."
  detection:
    expert_signals: ["expected value", "EV", "decision tree", "real options", "minimax regret", "value of information", "VOI", "tornado chart", "influence diagram", "Bayesian"]
    accessible_signals: ["should we wait", "is it worth the risk", "what's the downside", "what if we're wrong"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the decision you're facing, what alternatives are you weighing, and what's uncertain about each one?'"
    on_underspecified: "Ask: 'Are probabilities and time-value central (route here), or are the tradeoffs deterministic (Constraint Mapping)?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Is each critical variable classified as risk (assignable probability), uncertainty (estimable range), or deep uncertainty (no meaningful probability)?"
    failure_mode_if_unmet: false-precision
  - cq_id: CQ2
    question: "Have defer / sequence / hedge / buy-information alternatives been considered alongside direct choices?"
    failure_mode_if_unmet: missing-defer
  - cq_id: CQ3
    question: "Have non-quantifiable factors (ethics, relationships, identity, reputation) been presented alongside the quantitative framework, not as footnotes?"
    failure_mode_if_unmet: quantification-trap
  - cq_id: CQ4
    question: "Does the recommendation name what would change it — the conditions under which it should be revisited?"
    failure_mode_if_unmet: unconditional-recommendation
  - cq_id: CQ5
    question: "Are probabilities grounded in base rates or qualitative bands, not anchored to initial guesses presented as point estimates?"
    failure_mode_if_unmet: anchoring-trap

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: false-precision
    detection_signal: "Specific point probability (e.g. '17%') assigned without base-rate grounding."
    correction_protocol: flag (replace with range or qualitative band)
  - name: analysis-paralysis
    detection_signal: "Real options framing rationalises indefinite delay; cost of delay not assessed against value of information."
    correction_protocol: re-dispatch (assess cost-of-delay vs VOI explicitly)
  - name: quantification-trap
    detection_signal: "All factors reduced to utility numbers when some (ethics, identity, morale) resist meaningful quantification."
    correction_protocol: re-dispatch (add non-quantifiable factors section)
  - name: missing-defer
    detection_signal: "Decision framed as binary (A or B) when 'wait and learn' or 'buy information' is feasible."
    correction_protocol: re-dispatch (add defer/pilot/hedge alternative)
  - name: anchoring-trap
    detection_signal: "Initial probability estimates anchor subsequent analysis regardless of evidence."
    correction_protocol: re-dispatch (generate estimates independently before comparison)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - expected-utility-theory
  optional:
    - real-options-methodology (when financial/staged-investment)
    - minimax-regret-and-robust-decision-making (under deep uncertainty)
    - tetlock-superforecasting (when probabilities can be calibrated)
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: decision-architecture
    when: "Decision requires molecular orchestration: stakeholders + risk + future + multi-criteria all interact."
  sideways:
    target_mode_id: scenario-planning
    when: "Multiple plausible futures need to be explored before a choice is made."
  downward:
    target_mode_id: constraint-mapping
    when: "Probabilities are not material; deterministic tradeoff mapping suffices."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Decision Under Uncertainty is the rigour with which uncertainty is classified, probabilities are grounded, and consequences are characterised. A thin pass attaches numbers to outcomes; a substantive pass classifies each variable (risk / uncertainty / deep uncertainty), grounds each probability in a base rate or qualitative band, traces consequences under each plausible state, and assesses the value of additional information against the cost of delay. Test depth by asking: could the recommendation predict how it would shift if a specific input changed? Each critical variable carries the literal label `risk` / `uncertainty` / `deep uncertainty`.

## BREADTH ANALYSIS GUIDANCE

Breadth in Decision Under Uncertainty is the catalog of alternatives the framing might exclude. Widen the lens to surface defer, sequence, hedge, and buy-information options alongside direct choices. Identify robust alternatives (perform acceptably across multiple states) versus optimal alternatives (best in one state). Surface non-quantifiable factors. Breadth markers: at least one defer/pilot/hedge alternative; explicit assessment of which alternatives are robust vs optimal; reversibility cost named per alternative.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Decision Under Uncertainty is a probability-and-time-weighted decision analysis built on expected-utility theory with Knightian risk-vs-uncertainty-vs-deep-uncertainty classification as the operative reading vocabulary. It is distinct from constraint-mapping (which handles deterministic tradeoffs without probability arithmetic), from multi-criteria-decision (which weighs many criteria deterministically), from decision-architecture (the full molecular sibling with stakeholders + risk + future composed), and from scenario-planning (which explores multiple plausible futures rather than converging on one decision). The mode's analytical character is to honor what it knows about its own uncertainty — classifying probabilities, grounding them in base rates, and treating each as the kind of thing it actually is.

**Procedure.**

1. Frame the decision — name the alternatives, the decision-maker, the time-window, and the reversibility of each alternative.
2. Classify each critical variable per Knightian distinction — `risk` (assignable probability), `uncertainty` (estimable range), or `deep uncertainty` (no meaningful probability). Apply labels verbatim, not decoratively.
3. Ground probabilities in base rates or qualitative bands — replace point estimates lacking base-rate justification with ranges or qualitative bands (high / medium / low / negligible).
4. Trace consequences per (alternative × state) — name the consequence and a utility unit (or qualitative magnitude); align units across cells.
5. Surface defer / sequence / hedge / buy-information alternatives alongside direct A-vs-B framing; when no defer-class alternative is feasible, state so with reason.
6. Assess value-of-information against cost-of-delay — each VOI lever names what information would resolve which uncertainty, what it costs to obtain, and whether VOI exceeds cost-of-delay.
7. Surface non-quantifiable factors (ethics, identity, relationships, morale, reputation, dignity) as their own atoms alongside the quantitative framework — never as footnotes.
8. Recommend with conditions — state the recommended alternative (or staged sequence) plus an explicit `Revisit if:` block naming what change in inputs would warrant rerunning.
9. Distinguish robust alternatives (perform acceptably across states) from optimal alternatives (best in one state) when streams identified both.
10. Calibrate confidence per finding, distinguishing structural confidence (decision frame, classification) from substantive confidence (probability estimates, consequence projections).

**Goal.** Produce a decision-analysis recommendation under uncertainty — classifying each variable, tracing consequences across plausible states, assessing information vs delay, and converging on a conditional recommendation with non-quantifiable factors preserved alongside the quantitative framework.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — Knightian classification (load-bearing).** Is each critical variable classified as risk, uncertainty, or deep uncertainty, with labels appearing verbatim? Failure mode if unmet: `false-precision`.
- **CQ2 — defer / sequence / hedge / buy-information (load-bearing).** Have non-binary alternatives been considered alongside direct choices, or has the framing been binary? Failure mode if unmet: `missing-defer`.
- **CQ3 — non-quantifiable factors.** Are ethics, identity, relationships, and other non-quantifiable factors presented alongside the quantitative framework as their own atoms (not footnotes, not compressed into utility numbers)? Failure mode if unmet: `quantification-trap`.
- **CQ4 — conditional recommendation.** Does the recommendation name what would change it — the `Revisit if:` conditions? Failure mode if unmet: `unconditional-recommendation`.
- **CQ5 — anchoring discipline.** Are probabilities grounded in base rates or qualitative bands, not anchored to initial guesses presented as point estimates? Failure mode if unmet: `anchoring-trap`.

A passing output classifies each variable per Knightian distinction with labels verbatim, considers defer/sequence/hedge alternatives, traces consequences with aligned utility units, assesses VOI against cost-of-delay, surfaces non-quantifiable factors at full salience, produces a recommendation with explicit revision-conditions, distinguishes robust from optimal alternatives when both are in play, and carries per-finding confidence.

**Named failure modes.**

- *false-precision* — specific point probability assigned without base-rate grounding.
- *analysis-paralysis* — real-options framing rationalises indefinite delay without cost-of-delay vs VOI comparison.
- *quantification-trap* — all factors reduced to utility numbers when some (ethics, identity, morale) resist meaningful quantification.
- *missing-defer* — decision framed as binary when wait-and-learn or buy-information was feasible.
- *anchoring-trap* — initial probability estimates anchor subsequent analysis regardless of evidence.

## REVISION GUIDANCE

Revise to convert point probabilities into ranges when no base rate grounds the precision. Revise to add defer/pilot/hedge alternatives when binary framing has masked them. Revise to add non-quantifiable factors when only utility numbers appear. Revise to add recommendation conditions ("this would change if X"). Resist revising toward over-confident point estimates — humility about probability is part of the output. Resist revising toward exhaustive enumeration when robustness analysis suffices.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Knightian-classified decision-analysis atom set: decision framing, per-variable uncertainty classification, consequence atoms under each plausible state, alternatives including defer/sequence/hedge/buy-information, value-of-information atoms, recommendation with revision-conditions, and non-quantifiable atoms preserved alongside the quantitative framework**. The atoms are:

1. **Decision-framing atom.** The choice on the table — alternatives named, decision-maker named, time-window named, reversibility of each alternative noted. One short paragraph plus an alternatives list.

2. **Uncertainty-classification atoms per variable.** Each critical variable carries an explicit Knightian label: `risk` (assignable probability), `uncertainty` (estimable range), `deep uncertainty` (no meaningful probability). False-precision is the named failure mode the consolidator watches for; point probabilities without base-rate grounding get reshaped to ranges or qualitative bands.

3. **Probability/range atoms.** Each probability carries: its value (point, range, or qualitative band — high/medium/low/negligible), the basis (named base rate, structural inference, qualitative estimate), and the variable it applies to. Anchoring-trap is the named failure mode; estimates that anchor to initial guesses presented as point estimates get reshaped.

4. **Consequence atoms per (alternative × state).** Each atom carries: the alternative, the state, the consequence under that combination, and a utility unit (or qualitative magnitude) stated verbatim. Utility units are aligned across atoms — comparing apples-and-apples is the corpus standard.

5. **Defer / sequence / hedge / buy-information atoms.** Each atom that surfaces a non-binary alternative carries: the alternative shape (wait-and-learn, pilot, hedge, partial commitment), the cost of taking it (delay, opportunity, fixed cost), the information it produces, and the reversibility profile. Missing-defer is the named failure mode; binary framings where wait-and-learn was feasible get reshaped.

6. **Value-of-information atoms.** Each VOI atom carries: what information would resolve which uncertainty, the cost of obtaining it (time, money, effort), the value of obtaining it (expected utility shift), and whether VOI exceeds cost-of-delay. Analysis-paralysis is the named failure mode; rationalised indefinite delay without VOI-vs-cost-of-delay assessment gets reshaped.

7. **Recommendation atom.** The recommended alternative (or staged sequence), the conditions under which the recommendation holds, and a revision-trigger atom: what change in inputs would warrant revisiting. Unconditional-recommendation is the named failure mode.

8. **Non-quantifiable-factor atoms.** Each atom carries one factor that resists meaningful quantification — ethics, identity, relationships, morale, reputation, dignity — and the consideration it raises for the decision. Quantification-trap is the named failure mode; non-quantifiable factors collapsed into utility numbers get reshaped back to their own atoms. These atoms ride alongside the quantitative atoms; they are not footnotes.

9. **Robust-vs-optimal flag atoms.** Where streams identified robust alternatives (perform acceptably across multiple states) versus optimal alternatives (best in one state), the flag is preserved as a separate consideration.

10. **Confidence per finding** distinguishing structural confidence (the decision frame and uncertainty classification) from substantive confidence (the probabilities and the consequence estimates).

**Mode-specific bloat patterns to cut:**

- **Point probabilities without base-rate grounding** — false-precision. Specific percentages presented as if grounded in calibration when no base rate or qualitative band justifies the precision.
- **Anchored estimates** — probability estimates that visibly anchor to initial guesses across the analysis.
- **Binary framings hiding defer/sequence/hedge** — A-vs-B presentations where wait-and-learn or partial commitment was a feasible third option.
- **Real-options framing rationalising indefinite delay** — analysis-paralysis. Delay framed as VOI-seeking when cost-of-delay was not assessed against information gain.
- **Quantification of non-quantifiable factors** — utility numbers attached to ethics, identity, or dignity claims that resist meaningful numerical reduction.
- **Unconditional recommendations** — recommendations stated without revision-conditions.
- **Exhaustive consequence enumeration** — listing every (alternative × state) combination when a robust-vs-optimal assessment would have answered the decision-maker's question with less surface area.

**What NOT to collapse:**

- **Risk-vs-uncertainty-vs-deep-uncertainty disagreements** — when streams classified the same variable differently (one as risk with a probability estimate, another as deep uncertainty), the disagreement is the finding. Knightian classification is itself contested for some variables and the corpus preserves the contest.
- **Robust vs optimal alternatives** — when one alternative is robust across states and another is optimal in one state, both survive; the choice between them is the decision-maker's, not the consolidator's.
- **Quantitative vs non-quantifiable framings** — when streams gave the quantitative case for one alternative and the non-quantifiable case for another, both survive in their own atoms and are not blended into a single utility number.
- **Stream disagreement about whether a defer/buy-information option is feasible** — when one stream surfaced wait-and-learn and another judged it infeasible, both readings are preserved with the feasibility considerations attached.

## VERIFICATION CRITERIA

Verified means: each critical variable classified as risk/uncertainty/deep uncertainty with reasoning; defer/sequence/hedge alternatives considered alongside direct choices; value-of-information assessed against cost of delay; recommendation states what would change it; non-quantifiable factors present alongside quantitative framework; probabilities grounded in base rates or qualitative bands. The five critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **decision-analysis recommendation under uncertainty** — a structured artifact that classifies each variable, traces consequences across plausible states, assesses information versus delay, and converges on a conditional recommendation with non-quantifiable factors preserved alongside the quantitative framework. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Decision framing.** One paragraph stating the decision, the alternatives named, the decision-maker named, the time-window, and the reversibility profile of each alternative.

2. **Uncertainty identification.** A table. Each row: `**[Variable]** — class: [risk / uncertainty / deep uncertainty]. Probability or range: [value or band]. Basis: [base rate / structural inference / qualitative].` The Knightian class label appears verbatim — `risk`, `uncertainty`, `deep uncertainty` — not paraphrased.

3. **Consequence analysis.** A matrix or per-alternative block. For each (alternative × state) pair: `**[Alternative] under [state]:** [consequence]. Utility: [value with units stated verbatim].` Utility units are consistent across cells. When the matrix is too sparse to be informative (deep uncertainty dominates), this section renders a robust-vs-optimal narrative instead of a populated matrix.

4. **Defer, sequence, hedge, buy-information alternatives.** Bulleted list of non-binary alternatives. Each: `**[Alternative shape]** — cost of taking it: [delay / opportunity / fixed]. Information produced: [...]. Reversibility: [...].` When no defer-class alternative is feasible, this section says so explicitly with the reason.

5. **Value of information analysis.** One paragraph or short bulleted block. For each candidate VOI lever: `**[Information that would resolve uncertainty]** — cost of obtaining: [...]. Value of obtaining: [expected utility shift]. VOI vs cost-of-delay: [favorable / unfavorable / break-even].` When indefinite delay is being rationalised as VOI-seeking, the deliverable surfaces the analysis-paralysis flag explicitly.

6. **Recommendation.** One paragraph stating the recommended alternative (or staged sequence), followed by an explicit revision-condition block: `**Revisit if:** [list of input changes that would warrant rerunning the analysis].` Unconditional recommendations are reshaped at this layer.

7. **Non-quantifiable factors.** Bulleted list of factors that resist meaningful quantification. Each: `**[Factor — ethics / identity / relationship / morale / reputation / dignity]** — consideration: [...]. How it bears on the decision: [...].` This section appears alongside the quantitative analysis, not as a footnote.

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- The Knightian vocabulary (risk / uncertainty / deep uncertainty) is operative — labels appear verbatim with their distinguishing meanings preserved.
- Probability values appear with units or qualitative bands appropriate to their class: assignable probabilities as percentages, estimable ranges as intervals (`30–50%`), deep uncertainty as qualitative bands (`high / medium / low / negligible`).
- Utility units stay consistent across the consequence matrix; mixed units get reshaped at this layer.
- When an envelope-bearing visualisation is appropriate, render it inline: `decision_tree` for sequential choices under assignable probabilities (chance-node children sum to 1.0; decision-node children carry no probability); `influence_diagram` when dependency structure dominates; `tornado` for parameter-sensitivity. Utility units in the envelope match the prose.
- Recommendation revision-conditions (section 6) appear as a labelled `**Revisit if:**` block — visually distinct so the decision-maker can see at a glance what would change the recommendation.
- Non-quantifiable factors (section 7) are listed at full salience; collapsing them into utility numbers is reshaped at this layer.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `requires`, `enables`, `qualifies`, `supports`, `contradicts`
**Deprioritize:** `analogous-to`, `parent`

*Family: decision-risk. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
