---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-24

---

# MODE: Scenario Planning

```yaml
# 0. IDENTITY
mode_id: scenario-planning
canonical_name: Scenario Planning
suffix_rule: analysis
educational_name: alternative-future scenario planning (Wack/Schwartz lineage)

# 1. TERRITORY AND POSITION
territory: T6-future-exploration
gradation_position:
  axis: depth
  value: thorough
  secondary_axis: stance
  secondary_value: narrative-output
adjacent_modes_in_territory:
  - mode_id: consequences-and-sequel
    relationship: depth-lighter sibling (light forward projection)
  - mode_id: probabilistic-forecasting
    relationship: depth-thorough sibling (probability-output instead of narrative-output)
  - mode_id: pre-mortem-action
    relationship: stance-counterpart (adversarial-future-on-plan; shares klein-pre-mortem lens with T7's pre-mortem-fragility)
  - mode_id: wicked-future
    relationship: depth-molecular sibling (integrates multiple T6 modes)
  - mode_id: backcasting
    relationship: stance-counterpart (constructive-future — gap-deferred)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "a decision depends on future conditions that are genuinely uncertain"
    - "I'm doing strategic planning over a horizon longer than a year"
    - "everyone is assuming one default future and I want to challenge that"
    - "what if the environment changes"
    - "how should we prepare for different futures"
  prompt_shape_signals:
    - "scenarios"
    - "2x2 scenario matrix"
    - "scenario planning"
    - "possible futures"
    - "what-if matrix"
    - "alternative futures"
disambiguation_routing:
  routes_to_this_mode_when:
    - "multiple plausible futures to prepare for, narrative form"
    - "2x2 matrix with axes from critical uncertainties"
    - "5–20 year strategic horizon under genuine uncertainty"
  routes_away_when:
    - "one decision under uncertainty now (probability + payoff)" → decision-under-uncertainty (T3)
    - "want probability distributions instead of narrative scenarios" → probabilistic-forecasting
    - "questioning the foundational frame" → paradigm-suspension (T9)
    - "trace a failure backward" → root-cause-analysis (T4)
    - "stress-test a specific plan adversarially" → pre-mortem-action
    - "want lighter forward consequence cascade" → consequences-and-sequel
when_not_to_invoke:
  - "Horizon is short (under one year) and uncertainty is bounded" → consequences-and-sequel or constraint-mapping
  - "User wants to choose among present-state options, not prepare for futures" → T3
  - "Forces in play are feedback-structured and require systems-dynamics treatment" → systems-dynamics-causal (T4)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: generative

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [focal_question, planning_horizon, driving_force_inventory]
    optional: [predetermined_vs_uncertain_classification, prior_scenario_sets, STEEP_categorization]
    notes: "Applies when user supplies driving forces classified or partially classified, or names the Shell/Schwartz method explicitly."
  accessible_mode:
    required: [focal_question_or_strategic_concern]
    optional: [planning_horizon, contextual_background]
    notes: "Default. Mode infers driving forces, classifies them, selects axes, and constructs scenarios."
  detection:
    expert_signals: ["driving forces", "predetermined elements", "critical uncertainties", "STEEP", "Shell scenarios", "wild card"]
    accessible_signals: ["scenarios", "possible futures", "what could happen", "how should we prepare"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the strategic decision or focal question, and roughly what time horizon are you planning over?'"
    on_underspecified: "Ask: 'What's the focal question for these scenarios, and over what horizon?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the four scenarios structurally distinct (different causal logic), or merely magnitude variants (good/bad/medium)?"
    failure_mode_if_unmet: good-bad-medium-trap
  - cq_id: CQ2
    question: "Are the two axes genuinely independent, or do they correlate so the scenarios cluster on a diagonal?"
    failure_mode_if_unmet: correlated-axes-trap
  - cq_id: CQ3
    question: "Has any scenario been designated 'most likely' or 'official', undermining the mode's anti-prediction stance?"
    failure_mode_if_unmet: official-future-trap
  - cq_id: CQ4
    question: "Have driving forces been honestly classified as predetermined vs critical uncertainty, or has a genuine uncertainty been treated as predetermined?"
    failure_mode_if_unmet: certainty-masquerade-trap
  - cq_id: CQ5
    question: "Does each scenario translate into actionable strategic guidance (leading indicators, robust vs scenario-dependent strategies, contingent actions), or does it remain a story without strategy?"
    failure_mode_if_unmet: story-without-strategy-trap

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: good-bad-medium-trap
    detection_signal: "Scenarios labelled by magnitude (optimistic/pessimistic/baseline) rather than distinct causal logic."
    correction_protocol: re-dispatch
  - name: official-future-trap
    detection_signal: "One scenario labelled 'most likely' or designated as the planning baseline."
    correction_protocol: re-dispatch
  - name: story-without-strategy-trap
    detection_signal: "Scenario narratives lack leading indicators or actionable strategy translations."
    correction_protocol: flag
  - name: certainty-masquerade-trap
    detection_signal: "Driving force classified as predetermined that could plausibly go either way; classification not defended."
    correction_protocol: flag
  - name: correlated-axes-trap
    detection_signal: "Items cluster on a diagonal (axes covary); axes-independence rationale missing or trivial (< 40 chars)."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - shell-scenario-method
  optional:
    - tetlock-superforecasting
    - schwartz-art-of-the-long-view
    - steep-framework
    - klein-pre-mortem
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: wicked-future
    when: "Scenarios reveal multiple stakeholder values irreducibly conflict; futures need integrated analysis."
  sideways:
    target_mode_id: probabilistic-forecasting
    when: "User wants probability distributions over outcomes rather than narrative futures."
  downward:
    target_mode_id: consequences-and-sequel
    when: "Horizon is short or uncertainty is mild; light forward projection suffices."
```

## DEPTH ANALYSIS GUIDANCE

Going deeper in Scenario Planning means tracing each scenario's causal logic — what specific sequence of events makes this future coherent, which driving forces dominate, which actors respond how. A thin pass names scenarios; a substantive pass identifies the predetermined elements (forces that will happen regardless of axis position) separately from the critical uncertainties (forces that could go either way), constructs each quadrant from genuine independent uncertainty, and articulates leading indicators that would let an observer recognize early which scenario is materializing. Test depth by asking: could a strategist build contingent plans from each scenario's leading indicators alone?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning STEEP driving forces (Social, Technological, Economic, Environmental, Political) before narrowing to the two axes. Generate at least one wild-card scenario outside the 2×2 — a low-probability/high-impact future that would invalidate the matrix. Identify robust strategies (work across scenarios) vs scenario-dependent strategies (require correctly identifying which scenario is unfolding) vs contingent actions (tied to specific leading indicators). Breadth markers: every quadrant carries leading indicators; strategies are tagged robust or scenario-dependent; the wild card sits in prose, not in the matrix; the two axes' independence is argued non-trivially.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Scenario Planning is Wack/Schwartz-lineage 2×2 alternative-future construction: driving forces are classified predetermined-vs-critical-uncertainty, two independent critical uncertainties form the axes, and four causally-distinct scenarios populate the quadrants with leading indicators, strategic translation, and at least one wild card sitting outside the matrix. It is distinct from consequences-and-sequel (depth-lighter sibling — light forward projection), from probabilistic-forecasting (depth-thorough sibling — probability distributions instead of narrative), from pre-mortem-action (stance-counterpart — adversarial-future-on-plan), and from decision-under-uncertainty (T3 — one decision now with probability + payoff rather than preparation for multiple futures).

**Procedure.**

1. Lock the focal question and planning horizon (5–20 years typical for strategic scenarios).
2. Catalogue driving forces across STEEP (Social / Technological / Economic / Environmental / Political).
3. Classify each force honestly — `predetermined` (will happen regardless of axis position) vs. `critical-uncertainty` (could go either way); resist certainty-masquerade (treating uncertainty as fixed).
4. Select two critical uncertainties as axes; argue their independence substantively (>40 chars) — distinct drivers, historical decorrelation, orthogonal dependencies. Correlated axes collapse the 2×2 to a 1×4.
5. Construct four scenarios with distinct *causal logic* (not magnitude variants like optimistic / pessimistic / baseline) — coherent sequences of what unfolds in each quadrant.
6. Name each scenario by causal-logic shorthand (e.g., `Constrained Boom`, `Wild West`, `Soft Landing`, `Stall`).
7. Generate leading indicators per scenario — observable signals that, if seen early, mark this scenario as materialising.
8. Translate to strategic implications tagged `robust` (works across all four), `scenario-dependent` (requires correctly identifying which is unfolding), or `contingent` (tied to a specific leading indicator).
9. Generate at least one wild card — a low-probability/high-impact future outside the 2×2 that would invalidate the matrix.
10. Preserve equal standing for all four scenarios — no "most likely" designation; the mode does not predict.

**Goal.** Produce a 2×2 scenario set with strategic translation where four causally-distinct scenarios are populated, axes are genuinely independent, leading indicators per scenario surface, strategic implications distinguish robust / scenario-dependent / contingent, and at least one wild card sits outside the matrix.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — structural distinctiveness.** Are the four scenarios structurally distinct (different causal logic), or merely magnitude variants (good/bad/medium)? Failure mode if unmet: `good-bad-medium-trap`.
- **CQ2 — axes independence.** Are the two axes genuinely independent, or do they correlate so the scenarios cluster on a diagonal? Failure mode if unmet: `correlated-axes-trap`.
- **CQ3 — no most-likely designation.** Has any scenario been designated "most likely" or "official," undermining the mode's anti-prediction stance? Failure mode if unmet: `official-future-trap`.
- **CQ4 — honest predetermined-vs-uncertain.** Have driving forces been honestly classified as predetermined vs critical uncertainty, or has a genuine uncertainty been treated as predetermined? Failure mode if unmet: `certainty-masquerade-trap`.
- **CQ5 — strategic actionability.** Does each scenario translate into actionable strategic guidance (leading indicators, robust vs scenario-dependent strategies, contingent actions), or does it remain a story without strategy? Failure mode if unmet: `story-without-strategy-trap`.

A passing output has four scenarios with distinct causal logic, axes whose independence is argued in ≥40 chars of rationale, leading indicators per quadrant, robust vs scenario-dependent strategies distinguished, a wild card in prose, and no scenario marked "most likely."

**Named failure modes.**

- *good-bad-medium-trap* — scenarios labelled by magnitude (optimistic/pessimistic/baseline) rather than distinct causal logic.
- *official-future-trap* — one scenario labelled "most likely" or designated as the planning baseline.
- *story-without-strategy-trap* — scenario narratives lack leading indicators or actionable strategy translations.
- *certainty-masquerade-trap* — driving force classified as predetermined that could plausibly go either way; classification not defended.
- *correlated-axes-trap* — items cluster on a diagonal (axes covary); axes-independence rationale missing or trivial (< 40 chars).

## REVISION GUIDANCE

Revise to rewrite scenario names that use magnitude labels (optimistic/pessimistic/baseline) into names that capture distinct causal logic (Constrained boom, Wild west, Soft landing, Stall). Revise to remove any "most likely" designation — SP does not predict; each scenario receives equal standing. Revise to add leading indicators where quadrants lack them. Revise to expand the axes-independence rationale where it is asserted rather than argued (must reference distinct drivers, historical decorrelation, or orthogonal dependencies). Resist revising scenarios toward what the user "expects" — the mode's purpose is to challenge the official future, including the user's. Resist collapsing the wild card back into the matrix; the wild card is structurally outside the 2×2.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Schwartz/Wack scenario-set atom set: focal-question lock, driving-force atoms classified predetermined vs. critical-uncertainty, critical-uncertainty-axis atoms with independence rationale, four scenario atoms with distinct causal logic (not magnitude variants), leading-indicator atoms per scenario, strategic-implication atoms distinguishing robust from scenario-dependent strategies, and at least one wild-card atom outside the 2×2**. The atoms are:

1. **Focal-question atom.** The strategic question the scenarios serve, plus planning horizon (5–20 years typical). Subsequent atoms reference this lock; out-of-horizon material is reshaped.

2. **Driving-force atoms — classified.** Each atom names: one driving force, its STEEP category (Social / Technological / Economic / Environmental / Political), and its classification — `predetermined` (will happen regardless of axis position) or `critical-uncertainty` (could go either way). Certainty-masquerade-trap is the named failure mode the consolidator watches for; genuine uncertainties classified as predetermined get reshaped to critical-uncertainty with reasoning.

3. **Critical-uncertainty-axis atoms.** Two axes selected from the critical-uncertainty inventory. Each axis carries: low-label, high-label, the driving forces it represents, and an independence-rationale atom of substantive length. Correlated-axes-trap is the named failure mode; axes that co-vary (scenarios cluster on a diagonal) get reshaped, with axis-independence argued through distinct drivers / historical decorrelation / orthogonal dependencies.

4. **Scenario atoms — four quadrants with distinct causal logic.** Each atom carries: a *name* (causal-logic shorthand, not magnitude — e.g., `Constrained Boom`, `Wild West`, `Soft Landing`, `Stall`, not `Optimistic` / `Pessimistic`), a *narrative* (coherent causal sequence making this future internally consistent), and the axis-position. Good-bad-medium-trap is the named failure mode; scenarios labelled by magnitude get reshaped to distinct-causal-logic naming.

5. **Leading-indicator atoms per scenario.** Each atom names: an observable signal that, if seen early, would mark this scenario as materialising. Each quadrant carries at least one leading indicator. Story-without-strategy-trap is the named failure mode; scenario narratives without leading indicators get reshaped.

6. **Strategic-implication atoms — robust / scenario-dependent / contingent.** Each strategy atom carries a tag: `robust` (works across all four scenarios), `scenario-dependent` (requires correctly identifying which scenario is unfolding), or `contingent` (tied to a specific leading indicator). The three tags do not blur.

7. **Wild-card atoms.** Each wild-card atom names a low-probability / high-impact future *outside* the 2×2 that would invalidate the matrix. At least one wild card sits in prose, never inside the matrix.

8. **No-official-future check.** A standing atom: has any scenario been designated `most likely` or `official`? Official-future-trap is the named failure mode; the mode does not predict, and one-scenario-promotion erodes the anti-prediction stance. All four scenarios carry equal standing.

9. **Confidence per finding.** Confidence accompanies axis-selection, predetermined-vs-uncertainty classifications, and leading-indicator selections.

**Mode-specific bloat patterns to cut:**

- **Good-bad-medium scenarios** — magnitude labels (`Optimistic` / `Pessimistic` / `Baseline`) instead of distinct causal logic.
- **Correlated axes** — scenarios clustering on a diagonal; the 2×2 collapses to a 1×4.
- **Official future** — any scenario designated `most likely`. The mode does not predict.
- **Certainty masquerade** — genuine uncertainties hidden as predetermined elements.
- **Story without strategy** — scenarios with narrative but no leading indicators or strategic translation.
- **Wild card inside the matrix** — wild cards sit *outside* the 2×2 by construction; pulling them inside collapses their function.
- **Trivial axis-independence rationale** — under 40 characters of argument; the axes' independence has to be earned.
- **Strategy tags blurred** — robust / scenario-dependent / contingent collapsed into generic recommendations.

**What NOT to collapse:**

- **All four scenarios** — equal standing throughout. Any designation of one as "most likely" is reshaped at this layer.
- **Stream disagreement about which uncertainties are critical** — when streams selected different axis-pairs, both pairs survive; the choice surfaces with reasoning.
- **Predetermined-vs-uncertainty disagreement per driver** — when streams classified the same driver differently, the disagreement is itself a finding about what's contested.
- **Wild cards** — never reabsorbed into the matrix; they exist to mark its limits.

## VERIFICATION CRITERIA

Verified means: all four quadrants populated with name and non-empty narrative; each quadrant has at least one leading indicator; axes-independence rationale present and non-trivial (≥40 chars); driving forces classified predetermined vs critical-uncertainty in prose; scenarios are structurally distinct (not magnitude variants); no scenario labelled "most likely"; at least one wild card present in prose; at least one robust strategy distinguished from at least one scenario-dependent strategy. The five critical questions are addressable from the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **2×2 scenario set with strategic translation** — a Schwartz/Wack-tradition narrative output where four causally-distinct scenarios are populated, axes are genuinely independent, leading indicators per scenario surface, strategic implications distinguish robust / scenario-dependent / contingent, and at least one wild card sits in prose outside the matrix. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Focal question.** One short paragraph stating the strategic question and the planning horizon.

2. **Driving forces classified.** A two-column block:
   - `**Predetermined elements (will happen regardless of axis position):** [list with STEEP category per item].`
   - `**Critical uncertainties (could go either way):** [list with STEEP category per item].`

3. **Critical uncertainties as axes.** One labelled block. `**Axis X:** [label]. Low-label: [...]. High-label: [...]. Drivers represented: [...]. **Axis Y:** [label]. Low-label: [...]. High-label: [...]. Drivers represented: [...]. **Independence rationale:** [substantive argument that these axes do not covary, referencing distinct drivers / historical decorrelation / orthogonal dependencies].`

4. **Scenario matrix (2×2).** Four labelled quadrants. Each: `**[Quadrant TL/TR/BL/BR] — [Scenario name in distinct-causal-logic shorthand]:** Axis-X position / Axis-Y position. **Narrative:** [coherent causal sequence — what unfolds and why]. **Strategic translation:** [what this future means for the focal question].`

5. **Leading indicators per scenario.** Per scenario, one labelled sub-block: `**[Scenario name] — Leading indicators:** [observable signal 1] / [observable signal 2] / [observable signal 3]. **Where to look:** [...]. **Threshold for declaring this scenario unfolding:** [...].`

6. **Strategic implications.** Three labelled sub-blocks:
   - `**Robust strategies (work across all four scenarios):** [list].`
   - `**Scenario-dependent strategies (require correctly identifying which scenario):** [list with scenario-tags].`
   - `**Contingent actions (tied to specific leading indicators):** [list with trigger-indicators].`

7. **Wild card.** One labelled block. `**Wild card:** [low-probability / high-impact future outside the 2×2 that would invalidate the matrix]. **Why it sits outside the matrix:** [...]. **Indicator that it may be unfolding:** [...].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- Schwartz/Wack vocabulary stays operative: `driving forces`, `predetermined elements`, `critical uncertainties`, `2×2`, `leading indicators`, `robust strategies`, `wild card`. The vocabulary appears verbatim.
- Scenario names (section 4) use distinct-causal-logic shorthand, not magnitude labels. `Optimistic` / `Pessimistic` / `Baseline` get reshaped at this layer.
- All four scenarios receive equal standing. Designations of `most likely` or `official` are reshaped to equal-standing language.
- Axis-independence (section 3) is *argued*, not asserted. A rationale of fewer than 40 characters is reshaped to substantive argument.
- Strategy tags (section 6) — `robust` / `scenario-dependent` / `contingent` — appear verbatim with distinguishing meanings preserved.
- Wild cards (section 7) sit in prose, *outside* the matrix. Wild cards pulled into the matrix get reshaped — their structural function is to mark what the matrix doesn't capture.
- When streams diverged on axis-pair selection, the deliverable carries a labelled note in section 3: `**Alternative axes considered:** stream A selected [pair X] for [reason]; stream B selected [pair Y]. The deliverable uses [chosen] because [...]; the alternative axes would have produced [different scenario logic].`

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~10min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- Concept Fan
- APC
- CAF
- C&S
- OPV
- PMI

Mental models (always loaded):
- tetlock-superforecasting
- klein-pre-mortem
- taleb-fragility-antifragility
- narrative-instinct
- second-order-thinking
- sensemaking
- cynefin-framework

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `contradicts`, `qualifies`, `produces`, `precedes`
**Deprioritize:** `parent`, `analogous-to`

*Family: hypothesis-future. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
