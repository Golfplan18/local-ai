---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Probabilistic Forecasting

```yaml
# 0. IDENTITY
mode_id: probabilistic-forecasting
canonical_name: Probabilistic Forecasting
suffix_rule: analysis
educational_name: probabilistic forecasting (Tetlock superforecasting)

# 1. TERRITORY AND POSITION
territory: T6-future-exploration
gradation_position:
  axis: depth
  value: thorough
  secondary_axis: stance
  secondary_value: probability-output
adjacent_modes_in_territory:
  - mode_id: consequences-and-sequel
    relationship: depth-lighter sibling (forward causal cascade, no probability output)
  - mode_id: scenario-planning
    relationship: depth-counterpart (thorough but narrative-output rather than probability-output)
  - mode_id: pre-mortem-action
    relationship: stance-counterpart (adversarial-future on the action plan)
  - mode_id: wicked-future
    relationship: depth-molecular sibling (built Wave 4)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want a probability on this happening"
    - "what are the odds"
    - "give me a calibrated estimate"
    - "I want a forecast I could bet on"
    - "what's the base rate for something like this"
  prompt_shape_signals:
    - "probability of"
    - "what are the chances"
    - "forecast"
    - "superforecasting"
    - "Tetlock"
    - "calibrated probability"
    - "base rate for"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants a numeric probability or probability range as the primary output"
    - "user wants explicit base-rate reasoning, reference-class selection, and inside-vs-outside-view comparison"
    - "the question has a resolvable outcome (something that will be observably true or false by some date)"
  routes_away_when:
    - "user wants narrative scenarios rather than a probability number" → scenario-planning
    - "user wants light forward causal cascade with no probability commitment" → consequences-and-sequel
    - "user wants adversarial failure-mode walk on a plan" → pre-mortem-action
    - "user wants integrated multi-perspective forward analysis" → wicked-future
when_not_to_invoke:
  - "Question has no resolvable outcome (vague, contested definition of success) — clarify first via deep-clarification (T10) or escalate to scenario-planning"
  - "User is choosing among options now rather than estimating future state" → T3 modes
  - "User is examining historical causes of an outcome already observed" → T4 modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [forecast_question, resolution_criteria, time_horizon]
    optional: [reference_class_candidates, prior_probability, named_hypothesis_drivers, evidence_inventory]
    notes: "Applies when user supplies a structured question with explicit resolution criteria and named drivers."
  accessible_mode:
    required: [forward_question]
    optional: [time_horizon_estimate, why_user_wants_forecast]
    notes: "Default. Mode elicits resolution criteria and time horizon during execution if missing."
  detection:
    expert_signals: ["resolution criteria are", "time horizon is", "reference class", "base rate", "prior probability"]
    accessible_signals: ["what are the odds", "probability of", "give me a forecast", "chances of"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What event are you forecasting, and by when would we know whether it happened?'"
    on_underspecified: "Ask: 'How would we know, in concrete observable terms, whether the forecast resolved yes or no?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Is the forecast question operationally resolvable, or has it been left vague enough to escape evaluation?"
    failure_mode_if_unmet: unresolvable-question
  - cq_id: CQ2
    question: "Has an explicit reference class been selected and its base rate stated, or has the analysis jumped to inside-view reasoning without an outside-view anchor?"
    failure_mode_if_unmet: base-rate-neglect
  - cq_id: CQ3
    question: "Has the analysis distinguished inside-view drivers (what's specific to this case) from outside-view adjustment (how this case compares to the reference class), and shown the math of the adjustment?"
    failure_mode_if_unmet: view-collapse
  - cq_id: CQ4
    question: "Has the probability been stated as a range (with explicit confidence interval or fermization) rather than a false-precision point estimate?"
    failure_mode_if_unmet: false-precision

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: unresolvable-question
    detection_signal: "Resolution criteria section is empty or contains hedged language ('roughly', 'meaningfully', 'in the ballpark') without operational definition."
    correction_protocol: re-dispatch
  - name: base-rate-neglect
    detection_signal: "No reference class named, or reference class named without a base-rate number."
    correction_protocol: re-dispatch
  - name: view-collapse
    detection_signal: "Inside-view drivers and outside-view base rate not separately stated; final estimate not derivable from the two views' combination."
    correction_protocol: re-dispatch
  - name: false-precision
    detection_signal: "Probability stated as a single point (e.g., '37%') without range, or with range narrower than the evidence supports."
    correction_protocol: flag
  - name: anchor-bias
    detection_signal: "Final estimate suspiciously close to the first-mentioned base rate or to a salient round number."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - tetlock-superforecasting
  optional:
    - kahneman-tversky-bias-catalog (when bias-corrections are central)
    - knightian-risk-uncertainty-ambiguity (when the question crosses risk/uncertainty boundary)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: wicked-future
    when: "Question depends on multiple interacting feedback loops or stakeholder conflicts that single-question forecasting cannot decompose."
  sideways:
    target_mode_id: scenario-planning
    when: "User wants narrative scenarios with named pathways rather than a single probability number."
  downward:
    target_mode_id: consequences-and-sequel
    when: "User wants light forward causal cascade with no probability commitment."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Probabilistic Forecasting is the explicitness of base-rate reasoning, reference-class construction, and inside-vs-outside-view adjustment. A thin pass produces a number with intuitive justification; a substantive pass selects a reference class, states its base rate with citation or reasoning, names the inside-view drivers that distinguish this case from the reference class, shows the math of the adjustment, and produces a probability range whose width reflects the analyst's actual confidence rather than a default fermization. Test depth by asking: could a reader reproduce the estimate from the artifact, including the directional and magnitude adjustments from base rate?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means surveying multiple candidate reference classes before locking one (or explicitly weighting across several), scanning for inside-view drivers in multiple categories (mechanism, motivation, capacity, environment, base-rate-defying factors), and surfacing leading indicators that would update the estimate. A breadth-passing analysis names at least two candidate reference classes and explains the choice, even if only one is used for the final estimate.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Probabilistic Forecasting is the Tetlock-style superforecasting method applied to a resolvable future question — producing a calibrated probability range anchored in an explicit reference-class base rate, adjusted by transparent inside-view drivers, with leading indicators that would trigger updates. The mode is depth-thorough in T6's forward-exploration territory with probability-as-output stance, distinct from consequences-and-sequel (depth-lighter; forward causal cascade with no probability commitment), scenario-planning (depth-counterpart; narrative scenarios rather than a probability number), and pre-mortem-action (stance-counterpart; adversarial-future failure walk on a plan). The Tetlock commandments are held lightly as heuristics, not applied mechanically; the disposition (operational resolvability, base-rate anchoring, view-separation, range-not-point) is what matters.

**Procedure.**

1. Lock operational resolution criteria — what observable fact, by what date, would resolve the forecast yes or no. Hedged language disqualifies; route to deep-clarification if criteria can't be operationalized.
2. Survey candidate reference classes — at least two before locking the primary; name the alternative considered and the reason for not using it as primary.
3. State the base rate for the chosen reference class with citation or structural reasoning.
4. Identify inside-view drivers individually — case-specific factors by category (mechanism / motivation / capacity / environment / base-rate-defying), each with direction (raises or lowers probability from base rate) and magnitude estimate (percentage points or qualitative band).
5. Show the math of the outside-view adjustment transparently — `base rate [X%] + drivers shifting [+/−Y pp range] = final estimate [Z% ± width]`. A reader could reproduce the estimate from the components.
6. Produce a probability range whose width reflects actual confidence, not default fermization or false precision.
7. Identify leading indicators and update triggers — observable signals, thresholds, the directional adjustment each implies.
8. Hold two confidence kinds distinct — calibration confidence (am I right about the range) and point confidence (where in the range is most likely).
9. Flag anchor-bias where the final estimate sits suspiciously close to the first-mentioned base rate or a salient round number.

**Goal.** Produce a calibrated probabilistic forecast where the resolution criteria are operational, the reference-class base rate is explicit, inside-view drivers are individuated and combined transparently with the base rate, and the final probability is a range whose width reflects the analyst's actual confidence — with leading indicators that would trigger updates.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — operational resolvability.** Is the forecast question operationally resolvable, or has it been left vague enough to escape evaluation? Failure mode if unmet: `unresolvable-question`.
- **CQ2 — reference class and base rate.** Has an explicit reference class been selected and its base rate stated, or has the analysis jumped to inside-view reasoning without an outside-view anchor? Failure mode if unmet: `base-rate-neglect`.
- **CQ3 — view separation.** Has the analysis distinguished inside-view drivers (what's specific to this case) from outside-view adjustment (how this case compares to the reference class), and shown the math of the adjustment? Failure mode if unmet: `view-collapse`.
- **CQ4 — range not point.** Has the probability been stated as a range (with explicit confidence interval or fermization) rather than a false-precision point estimate? Failure mode if unmet: `false-precision`.

A passing output states resolution criteria operationally, names at least two candidate reference classes (with one chosen and the alternative noted), states the base rate as a number, lists inside-view drivers individually with direction and magnitude, shows the outside-view adjustment math transparently, produces a probability range with width reflecting confidence, names leading indicators with thresholds, and keeps calibration and point confidence distinct.

**Named failure modes.**

- *unresolvable-question* — resolution-criteria section empty or contains hedged language ("roughly", "meaningfully", "in the ballpark") without operational definition.
- *base-rate-neglect* — no reference class named, or reference class named without a base-rate number.
- *view-collapse* — inside-view drivers and outside-view base rate not separately stated; final estimate not derivable from the two views' combination.
- *false-precision* — probability stated as a single point (e.g., "37%") without range, or with range narrower than the evidence supports.
- *anchor-bias* — final estimate suspiciously close to the first-mentioned base rate or to a salient round number.

## REVISION GUIDANCE

Revise to add explicit base-rate citation where the draft asserts "common" or "rare" without a number. Revise to widen the probability range where the draft has anchored on false precision. Revise to surface inside-view drivers individually rather than aggregating them into a vague "case-specific factors" mention. Resist revising toward narrative — the mode's analytical character is probability-output. If the user wants narrative, escalate sideways to scenario-planning rather than diluting this mode's contract.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Tetlock-style probabilistic forecast atom set: operational resolution criteria, reference-class atoms with base-rate numbers, inside-view driver atoms (separate from base rate), outside-view-adjustment atoms showing the math, probability-range atom with width matching evidence, leading-indicator update-trigger atoms, and two-kind confidence (calibration vs. point)**. The atoms are:

1. **Resolution-criteria atom.** The forecast question stated with operational resolution criteria: what observable fact, by what date, would resolve the forecast yes or no. Unresolvable-question is the named failure mode the consolidator watches for; hedged language ("roughly", "meaningfully", "in the ballpark") without operational definition gets reshaped to operationally-resolvable criteria, or the corpus surfaces the under-specification as a sideways-route to deep-clarification.

2. **Reference-class atoms.** Each candidate reference class carries: the class definition, the base-rate number (with citation or structural reasoning), and the rationale for its applicability to this case. Base-rate-neglect is the named failure mode; reference classes named without base-rate numbers get reshaped, and analyses that jumped to inside-view without an outside-view anchor get reshaped to surface the base rate.

3. **Inside-view driver atoms.** Each atom names: one case-specific driver (mechanism / motivation / capacity / environment / base-rate-defying factor), its direction (raises or lowers probability from base rate), and its magnitude estimate (in percentage points or qualitative band). Drivers appear as a list, not aggregated into "case-specific factors" — view-collapse is the named failure mode.

4. **Outside-view adjustment atom.** The math of the adjustment, made transparent: `base rate [X%] + drivers shifting [+/−Y pp range] = final estimate [Z% ± width]`. A reader could reproduce the estimate from the components.

5. **Probability-range atom.** The forecast as a *range* (e.g., `25–35%`, or `high / medium / low / negligible` band) whose width reflects the analyst's actual confidence. False-precision is the named failure mode; point estimates without range, or ranges narrower than the evidence supports, get reshaped to wider intervals or qualitative bands.

6. **Leading-indicator and update-trigger atoms.** Each atom names: an observable signal that would prompt forecast revision, the threshold that triggers the update, and the directional adjustment the signal implies (`if signal X exceeds Y, raise forecast by Z pp`).

7. **Anchor-bias flag — when applicable.** Where streams produced a final estimate suspiciously close to the first-mentioned base rate or to a salient round number, the flag is preserved with reasoning.

8. **Two-kind confidence atom.** Calibration confidence (`am I right about the range`) and point confidence (`where in the range is most likely`), kept distinct. Tetlock's heuristics-held-lightly stance is preserved — the dispositional commitments matter more than rote commandment-by-commandment execution.

**Mode-specific bloat patterns to cut:**

- **Unresolvable question** — hedged resolution language; if it can't resolve yes/no by a date, it isn't a forecast.
- **Base-rate neglect** — reference classes named without numbers, or analyses that skip to inside view.
- **View-collapse** — inside-view drivers aggregated into "case-specific factors" without individual directional and magnitude estimates.
- **False precision** — point estimates without range; ranges narrower than the evidence supports.
- **Anchor bias** — final estimate suspiciously close to first-mentioned number or round figure.
- **Tetlock-commandment rigidity** — applying the ten commandments mechanically rather than holding them lightly as heuristics.
- **Narrative drift** — story-style outputs without probability commitment; if narrative is what's wanted, scenario-planning is the right sideways-route.
- **Single-reference-class lock-in** — locking the reference class without surveying alternatives.

**What NOT to collapse:**

- **Competing reference classes** — when streams selected different reference classes with different base rates, both survive with their respective base rates; the choice between them is the analyst's, with reasoning preserved.
- **Range width** — wide ranges that reflect genuine uncertainty are not narrowed for the sake of false precision. The width is information.
- **Inside-view driver disagreement** — when streams assigned different magnitudes or directions to the same driver, both estimates survive; the disagreement bounds the uncertainty.
- **Resolution-criteria ambiguity** — when the question cannot be operationally resolved without arbitrary choice, the corpus surfaces this rather than smoothing.

## VERIFICATION CRITERIA

Verified means: resolution criteria are operational and locked; reference class is named with base-rate number; inside-view drivers and outside-view base rate are separately stated; the final probability is a range whose construction can be reproduced from the artifact; leading indicators are named with thresholds; the four critical questions are addressable from the output. Confidence-in-estimate accompanies the probability range.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **probabilistic forecast** — a structured estimate that locks operational resolution criteria, anchors in an explicit base rate from a named reference class, adjusts via transparent inside-view reasoning, produces a probability range whose width reflects confidence, and names leading indicators for update. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Resolution criteria locked.** One paragraph. `**Forecast question:** [stated precisely]. **Resolution criteria:** [the observable fact that resolves the forecast]. **Resolution date:** [by when]. **What "yes" looks like:** [...]. **What "no" looks like:** [...].`

2. **Reference class and base rate.** A labelled block. `**Primary reference class:** [definition]. **Base rate:** [number with citation or structural reasoning]. **Applicability rationale:** [...]. **Alternative reference classes considered:** [list with brief base rates and reason for not using as primary].`

3. **Inside view drivers.** Bulleted list. Each: `**[Driver]** — category: [mechanism / motivation / capacity / environment / base-rate-defying]. Direction: [raises / lowers probability]. Magnitude: [percentage points or qualitative band]. Reasoning: [...].`

4. **Outside view adjustment.** One labelled block showing the math. `Base rate: [X%]. Inside-view drivers shift estimate: [+/− Y pp range, with directional summary]. Final estimate: [Z% ± width]. A reader can reproduce this from the components above.`

5. **Probability estimate with range.** One labelled line. `**Forecast: [range, e.g., 25–35%]** — width reflects [calibration uncertainty / fermization / structural unknowns].` When the question warrants qualitative band, use `high / medium / low / negligible` with explicit threshold definitions.

6. **Leading indicators and update triggers.** Bulleted list. Each: `**[Observable signal]** — threshold that triggers update: [...]. Directional adjustment if observed: [+/− Y pp]. Where to look for the signal: [...].`

7. **Confidence in estimate.** Two labelled assessments, kept distinct:
   - `**Calibration confidence:** [confidence that the range contains the true probability]. Basis: [...].`
   - `**Point confidence within range:** [where in the range is most likely, and how strongly]. Basis: [...].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- Tetlock vocabulary stays operative: `base rate`, `reference class`, `inside view`, `outside view`, `calibration`, `update trigger`. The vocabulary appears verbatim; paraphrasing into generic forecast-language is reshaped.
- Probability appears as a *range*, not a point. Point estimates are reshaped to ranges whose width reflects evidence; fake precision is reshaped at this layer.
- The outside-view-adjustment math (section 4) is *transparent*. A reader can reproduce the estimate from base rate + drivers. Opaque adjustments are reshaped.
- When the anchor-bias flag survived consolidation, section 4 carries a labelled `**Anchor-bias caveat:** the estimate sits suspiciously close to [the first-mentioned base rate / a salient round number]. Re-examining the inside-view-driver adjustments may reveal whether the math actually supports this estimate.`
- The two-kind confidence (section 7) stays separated — calibration and point confidence are distinct quantities.
- When the question is not operationally resolvable (resolution-criteria atom flagged degradation), the deliverable opens with: `**Note: this question is not yet operationally resolvable. The forecast below is provisional; clarifying the resolution criteria (e.g., what observable fact, by what date) is the first move before locking in the estimate. Sideways-route to deep-clarification if the operational definition is itself contested.**`

## CAVEATS AND OPEN DEBATES

**Debate D8 — Tetlock's commandments as binding rules vs. heuristics held lightly.** Tetlock's *Superforecasting* (2015) closes with "ten commandments" for would-be forecasters (triage, break problems into components, balance inside and outside views, etc.). A persistent failure mode in popular Tetlock readings is treating these commandments as binding rules — applied mechanically regardless of question shape. Tetlock himself has been explicit, in interviews and follow-up writing, that the commandments are heuristics that must be held lightly: superforecasters do not follow them mechanically; they cultivate the underlying disposition (probabilistic thinking, bias awareness, willingness to update) and apply the commandments where they help. This mode operates with the heuristics-held-lightly stance: the seven required output sections encode the disposition (operational resolvability, base-rate anchoring, view-separation, range-not-point) without prescribing rote commandment-by-commandment execution. Citations: Tetlock & Gardner 2015 *Superforecasting*; Tetlock subsequent interview and methodological clarifications.

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

**Prioritize:** `supports`, `contradicts`, `qualifies`, `produces`, `precedes`
**Deprioritize:** `parent`, `analogous-to`

*Family: hypothesis-future. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
