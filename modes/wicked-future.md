---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Wicked Future

```yaml
# 0. IDENTITY
mode_id: wicked-future
canonical_name: Wicked Future
suffix_rule: analysis
educational_name: wicked future analysis (scenario + pre-mortem + probabilistic forecast composition)

# 1. TERRITORY AND POSITION
territory: T6-future-exploration
gradation_position:
  axis: depth
  value: molecular
adjacent_modes_in_territory:
  - mode_id: consequences-and-sequel
    relationship: depth-light sibling (forward projection)
  - mode_id: probabilistic-forecasting
    relationship: depth-thorough sibling (probability-output)
  - mode_id: scenario-planning
    relationship: depth-thorough sibling (narrative-output)
  - mode_id: pre-mortem-action
    relationship: stance-adversarial-future sibling

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "the future here is genuinely tangled and I want scenarios + probabilities + failure pathways together"
    - "I need narrative scenarios, calibrated probabilities, and stress tests, not one or the other"
    - "willing to spend the time on a full forward-looking molecular pass"
    - "the question is forward-looking and the standard tools each give partial answers"
  prompt_shape_signals:
    - "wicked future"
    - "long-horizon scenarios with probabilities"
    - "scenarios plus pre-mortem"
    - "what could the future look like and what could go wrong"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants integrated forward analysis with scenarios + probabilities + adversarial-future stress test"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "want quick forward projection from current state" → consequences-and-sequel
    - "want calibrated probability output without narrative" → probabilistic-forecasting
    - "want narrative scenarios without probability formalism or pre-mortem" → scenario-planning
    - "want pre-mortem on a specific plan, not exploration of the future broadly" → pre-mortem-action
when_not_to_invoke:
  - "User has time pressure" → scenario-planning or probabilistic-forecasting
  - "Question is really about a current decision rather than the future broadly" → decision-architecture or decision-under-uncertainty

# 3. EXECUTION STRUCTURE
composition: molecular
# NOTE: Backcasting (constructive-future stance) is deferred per CR-6.
# This mode composes around its absence by anchoring scenario-planning
# (neutral-future), probabilistic-forecasting (probability-output), and
# pre-mortem-action (adversarial-future). The constructive-future stance
# is gap-flagged in partial_composition_handling rather than substituted.
molecular_spec:
  components:
    - mode_id: scenario-planning
      runs: full
    - mode_id: pre-mortem-action
      runs: full
    - mode_id: probabilistic-forecasting
      runs: full
  synthesis_stages:
    - name: scenario-probability-overlay
      type: parallel-merge
      input: [scenario-planning, probabilistic-forecasting]
      output: "scenario set with calibrated probability bands and identified divergence points (where scenarios branch)"
    - name: failure-pathway-stress-test
      type: contradiction-surfacing
      input: [scenario-probability-overlay, pre-mortem-action]
      output: "scenarios stress-tested against pre-mortem failure pathways; identification of which scenarios contain pre-mortem-flagged failure modes"
    - name: integrated-future-architecture
      type: dialectical-resolution
      input: [scenario-probability-overlay, failure-pathway-stress-test]
      output: "integrated forward analysis: probability-weighted scenarios with named failure pathways, divergence-points-to-monitor, and explicit gap-flag for missing constructive-future (Backcasting deferred)"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; do not aggregate over low-confidence forecasting findings
    deferred_components:
      - mode_id: backcasting
        status: deferred (gap-deferred per CR-6)
        compensating_treatment: "Constructive-future stance is not substituted. Output explicitly gap-flags the absence of backward-from-desired-future analysis in the integrated-future-architecture stage. Consumers requiring constructive-future framing should compose Wicked Future with downstream goal-articulation work."

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [forward_question, time_horizon, key_uncertainties]
    optional: [prior_scenarios, prior_forecasts, intervention_candidates]
    notes: "Applies when user supplies key uncertainties or prior scenarios."
  accessible_mode:
    required: [forward_question]
    optional: [contextual_background, time_horizon]
    notes: "Default. Mode elicits time horizon, key uncertainties, and intervention candidates during execution."
  detection:
    expert_signals: ["scenarios", "probability bands", "key uncertainties", "time horizon"]
    accessible_signals: ["what could the future look like", "what could go wrong", "long-horizon"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the forward-looking question, and over what time horizon?'"
    on_underspecified: "Ask the user whether they want the full Wicked Future molecular pass or a lighter scenario-planning / probabilistic-forecasting read."
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have the scenarios been constructed broadly enough, or has the analysis privileged extrapolation of the dominant trend?"
    failure_mode_if_unmet: trend-extrapolation-bias
  - cq_id: CQ2
    question: "Do the probability bands integrate with the scenario narratives, or do they sit in a separate silo from the scenario divergence points?"
    failure_mode_if_unmet: silo-aggregation
  - cq_id: CQ3
    question: "Has pre-mortem-action stress-tested the scenarios for failure pathways, or has the synthesis presented scenarios without naming failure modes?"
    failure_mode_if_unmet: pre-mortem-omission
  - cq_id: CQ4
    question: "Has the absence of constructive-future analysis (Backcasting deferred) been gap-flagged, or has the output silently presented descriptive-future as if complete?"
    failure_mode_if_unmet: silent-gap

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: trend-extrapolation-bias
    detection_signal: "All scenarios are variations of the dominant trend; no orthogonal or discontinuity scenario."
    correction_protocol: re-dispatch (with explicit divergence-scenario prompt)
  - name: silo-aggregation
    detection_signal: "Synthesis stage outputs concatenate scenario, probability, and pre-mortem sections without integration."
    correction_protocol: re-dispatch
  - name: pre-mortem-omission
    detection_signal: "pre-mortem-action did not run against the leading scenario."
    correction_protocol: flag and re-dispatch
  - name: silent-gap
    detection_signal: "Output presents integrated-future-architecture without flagging Backcasting absence."
    correction_protocol: flag and add gap-flag section

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - klein-pre-mortem
  optional:
    - tetlock-superforecasting (when scenarios extend beyond ~5 years)
    - taleb-extremistan-mediocristan (when discontinuity scenarios in play)
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Wicked Future is the heaviest mode in T6."
  sideways:
    target_mode_id: pre-mortem-action
    when: "Question is really about a specific plan's failure pathways rather than open future exploration."
  downward:
    target_mode_id: scenario-planning
    when: "User has time pressure; scenario narratives without probability formalism or pre-mortem suffice."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Wicked Future is the degree to which scenario-probability-overlay and failure-pathway-stress-test stages integrate component outputs rather than concatenating them. A thin molecular pass runs scenario-planning, probabilistic-forecasting, and pre-mortem-action and stitches their outputs; a substantive pass surfaces tensions — for instance, a scenario whose probability band collides with a pre-mortem failure pathway, or a divergence point that the probability formalism cannot price. Test depth by asking: does the integrated forward architecture contain a forecast-claim that no single component could have produced?

## BREADTH ANALYSIS GUIDANCE

Breadth in Wicked Future is the catalog of scenarios considered before narrowing to a probability-weighted set. Widen the lens to scan: trend-extrapolation; orthogonal-driver scenario; discontinuity (extremistan event); reversal; backcasting-from-desired-future (flagged as gap). Even when only 3–5 scenarios are kept, breadth is documented in the scenario-set section. Note: alternative compositions considered included substituting consequences-and-sequel for probabilistic-forecasting in lighter pass; current composition selects the full probabilistic forecasting for calibrated bands.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Wicked Future is a depth-molecular T6 future-exploration mode that composes scenario-planning (narrative scenarios), probabilistic-forecasting (calibrated probability bands), and pre-mortem-action (Klein prospective-hindsight adversarial-future stress test) into an integrated forward analysis. Backcasting (constructive-future stance) is *deferred* per CR-6; the mode covers descriptive-future only and is honest about that gap. It is distinct from consequences-and-sequel (depth-light forward projection), probabilistic-forecasting alone (probability-output only), scenario-planning alone (narrative-output only), and pre-mortem-action (adversarial-future on a specific plan, not future broadly). Read against Schwartz/Wack scenario-planning, Tetlock-Kahneman calibrated forecasting, Klein prospective-hindsight, Taleb extremistan-mediocristan, and Knightian risk-vs-uncertainty in long-horizon territory.

**Procedure.**

1. Lock the forward question and explicit time horizon at the corpus head.
2. Generate a scenario set with type-tag diversity (trend-extrapolation / orthogonal-driver / discontinuity / reversal) — at least one non-trend-extrapolation scenario must survive; otherwise CQ1 fires (trend-extrapolation-bias).
3. Assign probability bands per scenario with explicit bounds (`40%–60%`, not "around 50%"), calibration notes, and the evidence anchoring each bound. Point estimates over long-horizon inputs are false precision.
4. Identify divergence points — the variable or event whose realization splits scenarios — with leading indicators that would reveal which branch is taking.
5. Run pre-mortem stress test on the leading scenarios (top by probability band). Each failure-pathway atom is in past-tense Klein prospective-hindsight form ("the failure has already happened, here's how it played out") with leading indicators and recoverability assessment.
6. Produce the integrated-future-architecture — a forecast-claim no single component could have produced (scenarios + bands + failure pathways together).
7. Surface the constructive-future gap-flag explicitly — its own H2 section, not folded into confidence map or footnotes. Backcasting is deferred per CR-6.
8. Derive the divergence-points-to-monitor forward watchlist from step 4.
9. Surface residual uncertainties that cannot be priced by the probability formalism (Knightian uncertainty, model-misspecification risk, unknown unknowns) — distinct from low-confidence bands.
10. Distinguish priceable risk (probabilities knowable in principle) from Knightian or model-misspecification uncertainty (not priceable); flag outputs that present the latter as the former.

**Goal.** Produce a structured forward analysis — probability-weighted scenarios with divergence points, attached past-tense Klein failure pathways, an integrated forward architecture that requires all three components together, and a mandatory visible constructive-future gap-flag.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — scenario-type breadth.** Have the scenarios been constructed broadly enough, or has the analysis privileged extrapolation of the dominant trend? Failure mode if unmet: `trend-extrapolation-bias`.
- **CQ2 — integration vs concatenation (load-bearing).** Do the probability bands integrate with the scenario narratives, or do they sit in a separate silo from the divergence points? Failure mode if unmet: `silo-aggregation`.
- **CQ3 — pre-mortem stress test (load-bearing).** Has pre-mortem-action stress-tested the leading scenarios for failure pathways, or has the synthesis presented scenarios without naming failure modes? Failure mode if unmet: `pre-mortem-omission`.
- **CQ4 — constructive-future gap visible (load-bearing).** Has the absence of constructive-future analysis (Backcasting deferred) been gap-flagged at its own structurally prominent position, or has the output silently presented descriptive-future as if complete? Failure mode if unmet: `silent-gap`.

A passing output names forward question with time horizon, generates at least three scenarios including at least one non-trend-extrapolation type, assigns probability bands with explicit bounds, identifies divergence points with leading indicators, attaches past-tense Klein failure pathways to leading scenarios, produces an integrated-architecture forecast-claim no single component could have produced, carries the constructive-future gap-flag at its own H2 position, and distinguishes priceable risk from Knightian uncertainty.

**Named failure modes.**

- *trend-extrapolation-bias* — all scenarios are variations of the dominant trend; no orthogonal or discontinuity scenario.
- *silo-aggregation* — synthesis stage outputs concatenate scenario, probability, and pre-mortem sections without integration.
- *pre-mortem-omission* — pre-mortem-action did not run against the leading scenario.
- *silent-gap* — output presents integrated-future-architecture without flagging Backcasting absence.

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates. Revise to add discontinuity scenarios where the draft over-extrapolates dominant trend. Revise to surface divergence points where scenarios are presented as parallel narratives without identifying branching mechanism. Resist revising toward over-confident probability point-estimates — Wicked Future honors uncertainty in long-horizon forecasting; bands and confidence-per-finding are appropriate.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **scenario atoms with attached probability-band, divergence-point, and failure-pathway atoms, plus a load-bearing constructive-future gap-flag**. Three synthesis stages drive the corpus: scenario-probability-overlay, failure-pathway-stress-test, and integrated-future-architecture. Klein prospective-hindsight is the lens that anchors the failure-pathway atoms. The atoms are:

1. **Forward-question-and-horizon atom.** The forward question and explicit time horizon, stated once at the corpus head. Cross-stream paraphrase collapses to one canonical statement.

2. **Scenario atoms.** Each carries: scenario narrative, scenario-type tag (trend-extrapolation / orthogonal-driver / discontinuity / reversal / backcasting-from-desired-future-flagged-as-gap), probability band (with bounds), key uncertainties driving the scenario, and component provenance (scenario-planning produced the narrative; probabilistic-forecasting produced the bands). At least one non-trend-extrapolation scenario must survive cross-stream dedup or CQ1 fails (trend-extrapolation-bias). At minimum 3 scenarios survive.

3. **Probability-band atoms.** Each scenario's band carries: lower bound, upper bound, the evidence anchoring each bound, and a calibration note (when bands are wide, the note explains why — long-horizon, structural-uncertainty, Knightian rather than risk). False-precision in long-horizon forecasting is its own residue; point-estimates without bands do not survive.

4. **Divergence-point atoms.** Each names: the variable or event whose realization splits scenarios into different branches, which scenarios it routes to under which realization, and the leading-indicator that would reveal which branch is taking. Divergence points are corpus-load-bearing because they are what the user actually monitors; silo-aggregation residue lists scenarios in parallel without naming divergence-points.

5. **Failure-pathway atoms per leading scenario.** Pre-mortem stress-test outputs attached to specific scenarios (the leading scenarios by probability band). Each carries: failure-narrative (in past-tense Klein prospective-hindsight form — "the failure has already happened, here's how it played out"), the leading scenario it stress-tests, the causal pathway from current state to failure, and the leading indicators that would reveal the pathway taking. Pre-mortem-omission is the named failure mode; leading scenarios without attached failure-pathway atoms are its corpus signature.

6. **Integrated-future-architecture atom.** The corpus-level synthesis: probability-weighted scenarios with named failure pathways and divergence-points. This atom names what no single component could have produced — typically a forecast-claim that requires scenarios + probabilities + failure pathways together (e.g., "scenario A has 30% band but two of its three failure pathways are detectable via the same leading indicator scenario C would also produce — so the indicator is dual-purpose"). Silo-aggregation is the failure mode; an architecture atom that just re-lists component outputs is its corpus signature.

7. **Constructive-future gap-flag atom — mandatory and visible.** A single corpus-level atom names explicitly: Backcasting (constructive-future stance) is deferred per CR-6; this analysis covers descriptive-future only; users requiring constructive-future framing should compose with downstream goal-articulation work. Silent-gap is the named failure mode; an output that integrates descriptive-future without flagging the constructive-future absence is its corpus signature. The gap-flag is not buried in confidence-map or footnotes — it has its own corpus position.

8. **Divergence-points-to-monitor atoms.** Derived from item 4 — the forward-watchlist items: which divergence-points to monitor, which leading indicators to track, and what each indicator's pattern would signal.

9. **Residual-uncertainties atom.** Names the uncertainties that cannot be priced by the probability formalism (Knightian uncertainty, model-misspecification risk, unknown unknowns). These are distinct from low-confidence bands — they're uncertainties about the analytical frame itself.

10. **Confidence map per finding.** Confidence markers attach to scenarios, probability bands, failure-pathways. When the two streams assigned different confidences, audit conservatism applies.

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Scenario-type homogeneity** — all scenarios carrying trend-extrapolation type tag. Trend-extrapolation-bias residue; the corpus carries scenario-type diversity, or the bloat strip flags the homogeneity as a finding about the analyst's imagination limits.
- **Probability-band paraphrase** — same band stated in different forms (point + uncertainty / interval / log-odds). Single canonical form survives per scenario.
- **Failure-narrative restatement** — pre-mortem outputs restated in non-past-tense or in present-tense future-projection form. Klein discipline is past-tense prospective-hindsight; non-past-tense narratives do not survive as failure-pathway atoms.
- **Component-output concatenation residue** — prose that transcribes scenario-planning's output, then probabilistic-forecasting's output, then pre-mortem-action's output without integration. Silo-aggregation residue; the integrated-future-architecture atom does the integration, and component re-listing is bloat.
- **Buried gap-flag** — the constructive-future absence noted in confidence-map or in a footnote rather than as its own corpus atom. Silent-gap residue; the gap-flag atom is structurally prominent or it is unsurfaced.
- **Point-estimate residue** — long-horizon forecasts stated as single probabilities without bands. False-precision residue; bands replace points, or the atom is downgraded to qualitative-likelihood.

**What NOT to collapse:**

- **Scenario-narrative divergence** — when the two streams produced different scenarios (with overlap but not identity), preserve all surviving scenarios. The breadth value lies in the catalog; merging non-overlapping scenarios is content loss.
- **Probability-band disagreement for the same scenario** — when streams assigned different bands to the same scenario, preserve both bands as a band-disagreement atom. The disagreement is itself a finding about the analysis's robustness to forecasting methodology; the consolidator must not silently pick.
- **Failure-pathway disagreement per leading scenario** — when streams identified different failure pathways for the same scenario, preserve all surviving pathways. Pre-mortem-action's value is breadth of failure narrative; merging non-overlapping pathways is content loss.
- **Divergence-point disagreement** — when streams identified different variables as the divergence-point for the same scenario branching, preserve both as parallel divergence-point atoms. The disagreement reveals that the branching itself may have multiple structural drivers.

## VERIFICATION CRITERIA

Verified means: every component ran (or was flagged as proceeded-with-gap); synthesis stages integrated rather than concatenated; pre-mortem stress-test ran against leading scenarios; constructive-future gap is explicitly flagged; confidence map is populated. The four critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structured forward analysis: probability-weighted scenarios with divergence points, attached failure pathways, integrated forward architecture, and mandatory constructive-future gap-flag**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Forward question and horizon.** Two labelled lines at the top:
   - **Forward question:** [the question being projected]
   - **Time horizon:** [near-term / mid-horizon / long-horizon, with specific date range]

2. **Scenario set with probability bands.** Numbered list of scenarios (S1, S2, S3, …). Each scenario: `**[Scenario name]** — narrative: [one paragraph]. Type: [trend-extrapolation / orthogonal-driver / discontinuity / reversal]. Probability band: [low%–high%]. Key uncertainties driving this scenario: [...]. Provenance: [scenario-planning + probabilistic-forecasting].` At minimum three scenarios; at least one non-trend-extrapolation scenario or trend-extrapolation-bias fires.

3. **Divergence points.** Numbered list. Each divergence point: `**[DP_n]** — variable or event whose realization splits scenarios: [variable]. Routes: [(realization A → S_n), (realization B → S_m)]. Leading indicator: [the signal that would reveal which branch is taking].` Divergence points are corpus-load-bearing; silo-aggregation residue lists scenarios in parallel without naming them.

4. **Failure pathway stress test findings.** For the leading scenario(s) (top by probability band), bulleted list of failure pathways. Each bullet: `**[Failure narrative — past-tense Klein prospective-hindsight: "the failure has already happened, here is how it played out"]** — leading scenario: [S_n]. Causal pathway: [current state → failure]. Leading indicators: [...]. Recoverability: [recoverable / unrecoverable] — reason: [...]. Provenance: [pre-mortem-action].` At minimum one failure pathway per leading scenario.

5. **Integrated forward architecture.** A short prose block (two to four sentences) stating the corpus-level synthesis: probability-weighted scenarios with named failure pathways and divergence-points-to-monitor. The synthesis claim must require all three components together — e.g., "Scenario [N] has [X]% probability but two of its three failure pathways are detectable via the same leading indicator scenario [M] would also produce — so the indicator is dual-purpose." Silo-aggregation is the named failure mode; this section is what no single component could have produced.

6. **Constructive-future gap-flag — mandatory and visible.** A single block in this exact framing: `**Constructive-future gap:** Backcasting (constructive-future stance) is deferred per CR-6. This analysis covers descriptive-future only — probability-weighted scenarios and adversarial-future stress testing. Users requiring constructive-future framing (working backward from a desired future to identify required interventions) should compose Wicked Future with downstream goal-articulation work.` Silent-gap is the named failure mode; this section is structurally prominent (its own H2), not buried in the confidence map or as a footnote.

7. **Divergence-points-to-monitor.** Bulleted list. Each item: `**[Divergence point]** — leading indicator: [observable signal]. Pattern that would signal: [which scenario is taking].` Derived from section 3; this is the forward watchlist.

8. **Residual uncertainties.** Bulleted list of uncertainties that cannot be priced by the probability formalism (Knightian uncertainty, model-misspecification risk, unknown unknowns). Each: `**[Uncertainty]** — why unpriced: [reason — Knightian / structural / no historical base rate / etc.].`

9. **Confidence map.** Bulleted list of confidence markers attached to scenarios (probability bands), failure pathways, and the integrated architecture.

**Per-section conventions:**

- Use H2 headings for sections 1 through 9.
- Scenario IDs (S1, S2, …) and divergence-point IDs (DP_n) are referenced consistently throughout once introduced.
- Probability bands render with explicit bounds: `40%–60%` rather than `around 50%`. False-precision avoided; wide bands explained.
- Section 6's gap-flag is non-negotiable — it appears regardless of whether streams or earlier sections elsewhere implied the gap.
- Failure narratives in section 4 use past-tense Klein prospective-hindsight framing throughout — present-tense or future-tense narratives are bloat per the corpus discipline.


---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~10+min
- **Context Budget:** extended

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `contradicts`, `qualifies`, `produces`, `precedes`
**Deprioritize:** `parent`, `analogous-to`

*Family: hypothesis-future. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
