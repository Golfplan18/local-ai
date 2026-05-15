---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-01

---

# MODE: Decision Clarity

```yaml
# 0. IDENTITY
mode_id: decision-clarity
canonical_name: Decision Clarity
suffix_rule: analysis
educational_name: decision clarity document (for decision-maker; cui-bono + stakeholder + scenario + red-team-assessment composition)

# 1. TERRITORY AND POSITION
territory: T2-interest-and-power
gradation_position:
  axis: depth
  value: molecular
adjacent_modes_in_territory:
  - mode_id: cui-bono
    relationship: complexity-lighter sibling (simple)
  - mode_id: boundary-critique
    relationship: stance counterpart (critical/Ulrich CSH)
  - mode_id: wicked-problems
    relationship: depth-molecular sibling (integrated multi-perspective analysis operation)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I need a decision document for a decision-maker, not an exploratory analysis"
    - "produce something the decision-maker can act on"
    - "give them clarity on who benefits, who's affected, what could happen, and what could go wrong"
    - "the deliverable is a decision-clarity document, not a wicked-problem map"
  prompt_shape_signals:
    - "decision clarity"
    - "decision document for"
    - "brief the decision-maker"
    - "executive decision brief"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user's deliverable is a decision document for a third-party decision-maker"
    - "user wants integrated cui-bono + stakeholder + scenario + adversarial-stress in a decision-shaped output"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "user is making the decision themselves with full alternatives + constraints + uncertainty" → decision-architecture
    - "user wants integrated wicked-problems analysis without decision-shape constraint" → wicked-problems
    - "want quick read on who benefits" → cui-bono
    - "want critical surfacing of marginalized voices" → boundary-critique
when_not_to_invoke:
  - "User has time pressure" → cui-bono or stakeholder-mapping
  - "There is no identified decision-maker; the deliverable is exploratory" → wicked-problems

# 3. EXECUTION STRUCTURE
composition: molecular
# NOTE: Decision H parse — Wicked Problems framework parsed into wicked-problems mode
# (integrated multi-perspective analysis) plus decision-clarity mode (decision-maker-output).
# Paired with restructured Framework — Decision Clarity Analysis.md (Phase 2).
molecular_spec:
  components:
    - mode_id: cui-bono
      runs: full
    - mode_id: stakeholder-mapping
      runs: full
    - mode_id: scenario-planning
      runs: fragment
      fragment_spec: "two-scenario-only — produce two contrasting scenarios (most-likely + most-adverse) sufficient for decision-maker context; do not produce full scenario-planning narrative set"
    - mode_id: red-team-assessment
      runs: fragment
      fragment_spec: "adversarial-stress-test of leading intervention only — adversarial-actor stress test against the leading recommended intervention candidate (assessment stance for the decision-maker's own benefit; advocate stance is not used in this composition because the synthesised document is decision-maker-facing, not external-audience-facing), not full red-team-assessment battery"
  synthesis_stages:
    - name: interest-and-stakeholder-merge
      type: parallel-merge
      input: [cui-bono, stakeholder-mapping]
      output: "merged interest-and-stakeholder picture: who benefits, who pays, who has power, who is absent, with per-stakeholder positions and concerns"
    - name: scenario-overlay
      type: sequenced-build
      input: [interest-and-stakeholder-merge, scenario-planning-fragment]
      output: "interest-and-stakeholder picture overlaid on the two scenarios: how does each scenario shift who benefits, who pays, and where power flows"
    - name: intervention-stress-test
      type: contradiction-surfacing
      input: [scenario-overlay, red-team-fragment]
      output: "leading intervention candidate stress-tested by red-team-fragment; surfaced adversarial dynamics that the cui-bono and scenario passes did not see"
    - name: decision-clarity-document
      type: dialectical-resolution
      input: [interest-and-stakeholder-merge, scenario-overlay, intervention-stress-test]
      output: "Decision Clarity Document for the decision-maker: situation framing, stakeholder map, scenario range, recommended intervention with stress-test findings, residual risks, and decision-maker-actionable recommendations"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; do not aggregate over low-confidence stakeholder or red-team findings; if scenario fragment cannot produce contrasting scenarios, document as one-scenario assumption

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [decision_maker_identity, decision_at_hand, stakeholder_inventory, intervention_candidates]
    optional: [prior_decisions, organizational_context]
    notes: "Applies when user supplies decision-maker identity plus intervention candidates."
  accessible_mode:
    required: [decision_at_hand, decision_maker_identity]
    optional: [contextual_background]
    notes: "Default. Mode elicits stakeholder inventory and intervention candidates during execution."
  detection:
    expert_signals: ["brief the", "decision-maker is", "stakeholders include", "intervention options"]
    accessible_signals: ["decision document", "give them clarity", "for the executive"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Who is the decision-maker, and what's the decision they need clarity on?'"
    on_underspecified: "Ask the user whether they want the full Decision Clarity molecular pass or a lighter Cui Bono / Stakeholder Mapping read."
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Does the document address the actual decision-maker's context (what they can do, what they cannot), or does it present generic analysis?"
    failure_mode_if_unmet: decision-maker-disconnection
  - cq_id: CQ2
    question: "Are stakeholder positions surfaced with concrete interests and concerns, or have they been collapsed into generic categories?"
    failure_mode_if_unmet: stakeholder-collapse
  - cq_id: CQ3
    question: "Has the leading intervention been stress-tested by the red-team fragment, or has the recommendation been presented without adversarial pressure?"
    failure_mode_if_unmet: stress-test-omission
  - cq_id: CQ4
    question: "Are the recommendations actionable by the named decision-maker, or do they exceed the decision-maker's authority or scope?"
    failure_mode_if_unmet: out-of-scope-recommendation
  - cq_id: CQ5
    question: "Are the two scenarios genuinely contrasting (most-likely + most-adverse), or are they variations of the same trajectory?"
    failure_mode_if_unmet: scenario-flattening

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: decision-maker-disconnection
    detection_signal: "Document is generic; no reference to the decision-maker's role, authority, or constraints."
    correction_protocol: re-dispatch (with explicit decision-maker-context prompt)
  - name: stakeholder-collapse
    detection_signal: "Stakeholders are listed in generic categories (e.g., 'employees', 'customers') without concrete interests or positions."
    correction_protocol: re-dispatch
  - name: stress-test-omission
    detection_signal: "red-team-fragment did not run against the leading intervention."
    correction_protocol: flag and re-dispatch
  - name: out-of-scope-recommendation
    detection_signal: "Recommendations require authority or scope the named decision-maker does not have."
    correction_protocol: flag and re-dispatch
  - name: scenario-flattening
    detection_signal: "Two scenarios differ only in degree, not in kind; both privilege the dominant trajectory."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - rumelt-strategy-kernel (when intervention is strategic)
    - ulrich-csh-boundary-categories (when boundary critique cross-cuts)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Decision Clarity is the heaviest mode in T2's depth ladder."
  sideways:
    target_mode_id: wicked-problems
    when: "Output should be integrated multi-perspective analysis rather than decision-clarity document."
  downward:
    target_mode_id: cui-bono
    when: "User has time pressure or scope is narrower than initially estimated."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Decision Clarity is the degree to which the four synthesis stages produce a decision-document that no single component could have produced. A thin molecular pass concatenates cui-bono + stakeholder + scenario + red-team outputs into a document; a substantive pass surfaces tensions — for instance, a stakeholder whose interests flip across scenarios, or a red-team adversarial dynamic that invalidates the leading intervention's interest-rationale. Test depth by asking: does the document contain decision-maker-actionable recommendations that no single component could have produced?

## BREADTH ANALYSIS GUIDANCE

Breadth in Decision Clarity is the catalog of stakeholders and intervention candidates considered before narrowing to the recommendation. Widen the lens to scan: visible stakeholders; absent stakeholders (boundary-critique territory); intervention status quo; intervention reversal; intervention defer-and-monitor. Even when the recommendation lands on one intervention, breadth is documented in the stakeholder-map-with-positions and intervention-recommendation sections. Note: alternative compositions considered included substituting full red-team for the fragment; current composition uses the fragment to keep the document decision-shaped rather than analysis-shaped.

## EVALUATION CRITERIA

Decision Clarity is read as a decision-brief tradition — Rumelt strategy-kernel framing combined with cui-bono interest-pathway analysis, Mitchell-Agle-Wood stakeholder-salience overlay, Schwartz/Wack scenario contrast, and red-team-assessment adversarial stress against the leading intervention. The evaluator's primary axis is decision-maker grounding: this mode exists to produce a document a named third-party decision-maker can act on within their authority, not an exploratory analysis. CQ1 (decision-maker-disconnection) and CQ4 (out-of-scope recommendation) are load-bearing — together they protect the deliverable's reason for existing. CQ2 (stakeholder collapse), CQ3 (stress-test omission), and CQ5 (scenario flattening) act as quality gates on inputs and scenario structure.

Evaluator checks:

1. **Decision-maker grounding (CQ1, load-bearing).** The document must address the named decision-maker's actual context: their authority, their constraints, the audiences they answer to, the time-window they operate within. Generic decision analysis without decision-maker-context anchoring is decision-maker-disconnection — it could be addressed to anyone, which means it is addressed to no one. Test: does the document name the decision-maker, and does the recommendation language presuppose their specific authority and constraints?

2. **Recommendation scope discipline (CQ4, load-bearing).** Recommendations must lie within the named decision-maker's authority. Recommendations that require authority they don't have are out-of-scope-recommendation — they invite the decision-maker to act beyond warrant. When synthesis surfaces a scope-exceeding recommendation, the evaluator confirms the document flags the scope question explicitly rather than burying it.

3. **Stakeholder concreteness (CQ2).** Each stakeholder must carry a concrete position, interest pathway (money / power / time / narrative per cui-bono shape), and concern. Generic categories ("employees," "customers," "the community") without specificity are stakeholder-collapse — the document feels comprehensive but gives the decision-maker no actionable understanding.

4. **Adversarial stress test on the leading intervention (CQ3).** The red-team fragment must run against the *leading* intervention — not a runner-up, and not generally against the situation. The test: does the document name adversarial dynamics, exploit pathways, or failure scenarios that specifically target the recommended intervention? Stress-test-omission is the failure mode and the recommendation does not pass without it. The stance is assessment (red-team-assessment), not advocate — the document is decision-maker-facing, not audience-facing.

5. **Scenario kind-vs-degree (CQ5).** The two scenarios must differ qualitatively, not just in magnitude. Most-likely and most-adverse that both privilege the dominant trajectory are scenario-flattening; the adverse scenario must surface a different causal pathway, not the same pathway worse.

6. **Decision-shape vs analysis-shape.** Decision Clarity is decision-shaped: the document tells the decision-maker what to do, when, and under what conditions. Exploratory framing that maps the territory exhaustively without converging on an actionable recommendation is route-to-wicked-problems residue — the evaluator flags it as mode misfit rather than smoothing it.

Where a stakeholder's position flips across scenarios, the evaluator confirms the flip is surfaced as a named finding rather than buried in a table row — flip-points are load-bearing for the decision-maker's read. Where red-team findings invalidate the cui-bono interest-rationale underlying the recommendation, the contradiction is preserved as a labelled finding rather than silently reconciled.

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates. Revise to ground recommendations more concretely in the decision-maker's authority and constraints. Revise to add adversarial dynamics where the red-team fragment surfaces them. Resist revising toward exploratory framing — Decision Clarity is decision-shaped, not analysis-shaped; the document's purpose is to help the decision-maker act, not to map the territory exhaustively. (When the user wants exhaustive mapping, route to wicked-problems instead.)

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a decision-brief atom set produced by integrating four component-mode outputs (cui-bono, stakeholder-mapping, scenario-planning-fragment, red-team-assessment-fragment) across four synthesis stages**. The atoms are:

1. **Decision-at-hand atom.** The specific decision the named decision-maker faces, stated in the decision-maker's vocabulary, with the time-window and the boundary of what is and isn't theirs to decide. One short paragraph.

2. **Decision-maker-context atom.** Authority, constraints, and accountability of the named decision-maker — what they can do, what they cannot, what audiences they answer to. Decision-maker-disconnection is the named failure mode; generic analysis without context-grounding gets reshaped or flagged.

3. **Interest-and-stakeholder merge atoms (from synthesis-stage 1).** Each atom carries: party, position on the decision, concrete interest pathway (money / power / time / narrative — per cui-bono atom shape), and concrete concern. Stakeholder-collapse is the named failure mode; generic categories (employees, customers) without concrete positions get reshaped.

4. **Scenario-overlay atoms (from synthesis-stage 2).** Two contrasting scenarios — most-likely and most-adverse — with the interest-and-stakeholder picture overlaid on each: how does each scenario shift who benefits, who pays, where power flows. Scenario-flattening is the named failure mode; scenarios that differ only in degree get reshaped.

5. **Intervention-stress-test atoms (from synthesis-stage 3).** The leading intervention candidate, the red-team-fragment's adversarial findings against it (adversarial dynamics, exploit pathways, failure scenarios), and any flip-points where stakeholder positions reverse under stress. Stress-test-omission is the named failure mode.

6. **Recommendation atoms.** Each recommendation carries: the action, the decision-maker's authority to take it (i.e., is it within their scope?), the conditions under which it holds, the residual risk it leaves un-mitigated. Out-of-scope-recommendation is the named failure mode; recommendations exceeding the named decision-maker's authority get reshaped.

7. **Residual-risk and decision-condition atoms.** What remains uncertain after the analysis, what would change the recommendation, what monitoring or trigger would warrant revisiting the decision.

8. **Confidence-map atom.** Per-section confidence: stakeholder map, scenario range, stress-test findings, recommendations. The map distinguishes structural confidence (the analytical frame is sound) from substantive confidence (the inputs to the analysis are reliable).

**Mode-specific bloat patterns to cut:**

- **Concatenation residue** — corpus that reads like four component-mode outputs side-by-side rather than synthesised through the four stages. The four synthesis stages (interest-and-stakeholder merge → scenario overlay → intervention stress-test → decision-clarity document) are what makes this mode molecular rather than additive.
- **Exploratory framing** — language that maps the territory exhaustively without converging on a decision-shaped recommendation. Decision-shaped means: the recommendation tells the decision-maker what to do, when, and under what conditions; it does not invite further exploration. (When exhaustive mapping is what's wanted, the right mode is wicked-problems.)
- **Generic stakeholder categories** — listing "employees" or "customers" without concrete interests, positions, and concerns. The cui-bono and stakeholder-mapping atom shapes require specificity.
- **Recommendations beyond the decision-maker's scope** — recommendations that require authority the named decision-maker does not have. The decision-maker-context atom is load-bearing here.
- **Scenario variations of the same trajectory** — both scenarios privileging the dominant outcome; the most-adverse scenario must be qualitatively different, not just numerically worse.
- **Stress-test against an alternative intervention** — the red-team-fragment was scoped to stress-test the *leading* intervention, not a runner-up. Stress-tests of secondary candidates are bloat unless they invalidated the leading recommendation.

**What NOT to collapse:**

- **Stakeholder-position flips across scenarios** — when streams identified a stakeholder whose position reverses between most-likely and most-adverse scenarios, the flip is itself a finding and survives in the corpus.
- **Red-team findings that invalidate the cui-bono interest-rationale** — when the adversarial pass surfaces an exploit pathway that contradicts the interest-pathway logic from synthesis-stage 1, both readings survive; the tension is the molecular pass's load-bearing finding.
- **Stream disagreement about whether the leading intervention is the right candidate** — when streams converged on different leading interventions, both are preserved with their respective stress-test findings.
- **Disagreement about decision-maker scope** — when streams diverged on whether a recommendation falls inside or outside the named decision-maker's authority, the disagreement gets flagged for the decision-maker rather than smoothed.

## VERIFICATION CRITERIA

Verified means: every component ran (or was flagged as proceeded-with-gap); the four synthesis stages integrated rather than concatenated; leading intervention carries red-team stress-test; recommendations are within the named decision-maker's scope; two scenarios are genuinely contrasting; confidence map is populated. The five critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **Decision Clarity Document** — a decision-brief for the named decision-maker, structured to make the recommendation actionable within their authority. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Decision at hand.** One paragraph stating the decision in the decision-maker's vocabulary, with the time-window and the boundary of what is and isn't theirs to decide.

2. **Decision-maker context.** One paragraph naming the decision-maker explicitly and stating their authority, constraints, and accountability — what they can do, what they cannot, what audiences they answer to. This section is load-bearing for section 9 (recommendations must respect this scope).

3. **Stakeholder map with positions.** A table. Each row: `**[Party]** — position: [for / against / conditional / absent]. Concrete interest: [pathway]. Concern: [specific].` Generic category names ("employees", "customers") are replaced with concrete sub-segments when streams produced them.

4. **Interest and power summary.** One paragraph synthesising who benefits, who pays, where power concentrates, and where boundary-critique flags absent voices. This section is the cui-bono + stakeholder-mapping merge; it does not reproduce them in full.

5. **Scenario range.** Two labelled sub-blocks:
   - `**Most-likely scenario:** [one paragraph trajectory]. Interest shift: [how stakeholders' positions move].`
   - `**Most-adverse scenario:** [one paragraph trajectory, qualitatively different — not just numerically worse]. Interest shift: [...].`

6. **Leading intervention — recommendation.** One paragraph stating the leading intervention candidate, the rationale, and the conditions under which it holds.

7. **Stress-test findings.** Bulleted list of adversarial findings from the red-team-fragment against the leading intervention. Each: `**[Adversarial dynamic / exploit / failure scenario]** — how it stresses the intervention: [...]. Whether it invalidates the recommendation: [yes / no / conditional].`

8. **Residual risks and decision conditions.** Bulleted list. Each: `**[Residual risk]** — what monitoring or trigger would warrant revisiting the decision: [...].`

9. **Decision-maker-actionable recommendations.** A numbered list. Each recommendation: `[N]. **[Action]** — within decision-maker's scope: [yes — by what authority / partially — what extension is needed]. Timeline: [...]. Conditions: [...].` Recommendations exceeding the decision-maker's scope are flagged explicitly, not silently demoted.

10. **Confidence map.** Per-section confidence summary, distinguishing structural confidence (the analytical frame is sound) from substantive confidence (the inputs are reliable).

**Per-section conventions:**

- Use H2 headings for sections 1 through 10.
- Tone is decision-brief, not exploratory essay — the document tells the decision-maker what to do; it does not invite further exploration. Exploratory framing is reshaped at this layer.
- Provenance to component-mode sources stays implicit in the document body — the decision-maker reads a single integrated brief, not four concatenated component outputs. (Provenance per finding remains available in the confidence map.)
- When a stakeholder's position flips across scenarios, the flip is rendered as a labelled finding at the end of section 3 (not buried inside a row): `**Flip-point:** [Stakeholder] — from [position] in most-likely to [position] in most-adverse. Driver: [...].`
- When red-team findings invalidate the cui-bono interest-rationale, the contradiction is rendered as a labelled finding inside section 7: `**Contradiction:** the adversarial dynamic [...] invalidates the interest-rationale that the recommendation rests on. [Implications].`
- When the decision-maker's scope is contested (synthesis disagreed on whether a recommendation falls inside their authority), section 9 carries the disagreement as an explicit flag rather than picking one reading: `**Scope-contested:** [recommendation] — [stream A: in-scope by authority X; stream B: requires extension Y].`


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

**Prioritize:** `requires`, `enables`, `contradicts`, `supports`, `qualifies`
**Deprioritize:** `parent`, `analogous-to`

*Family: stakeholder-strategy. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
