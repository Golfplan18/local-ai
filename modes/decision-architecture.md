---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-01

---

# MODE: Decision Architecture

```yaml
# 0. IDENTITY
mode_id: decision-architecture
canonical_name: Decision Architecture
suffix_rule: analysis
educational_name: decision architecture (integrated decision analysis with stakeholders + risk + alternatives)

# 1. TERRITORY AND POSITION
territory: T3-decision-making-under-uncertainty
gradation_position:
  axis: depth
  value: molecular
adjacent_modes_in_territory:
  - mode_id: constraint-mapping
    relationship: depth-light sibling (deterministic constraint pass)
  - mode_id: decision-under-uncertainty
    relationship: depth-thorough sibling (probability-and-time-weighted)
  - mode_id: multi-criteria-decision
    relationship: complexity sibling (multi-criteria weighting)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "this is a big decision and I want the full treatment"
    - "I need to think through this with stakeholders, constraints, and what could go wrong"
    - "the decision is real and I want a structured architecture, not just a recommendation"
    - "willing to spend the time to do this properly"
  prompt_shape_signals:
    - "decision architecture"
    - "full decision analysis"
    - "should I do X or Y, taking everything into account"
    - "structured decision document"
disambiguation_routing:
  routes_to_this_mode_when:
    - "decision is high-stakes; user wants integrated architecture spanning constraints + uncertainty + stakeholders + failure modes"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "decision is constraint-bounded only (no uncertainty)" → constraint-mapping
    - "decision is probability-weighted but stakeholder-light" → decision-under-uncertainty
    - "decision is multi-criteria with clean criteria weights" → multi-criteria-decision
    - "the decision is really stakeholder-conflict at heart, not your-decision-with-inputs" → stakeholder-mapping or T8 modes
when_not_to_invoke:
  - "User has time pressure (Decision Architecture is Tier-3 ~10+ min)" → decision-under-uncertainty or constraint-mapping
  - "Decision is genuinely simple (one constraint dominates)" → constraint-mapping
  - "User is producing a decision document for a third-party decision-maker, not making a decision themselves" → decision-clarity

# 3. EXECUTION STRUCTURE
composition: molecular
molecular_spec:
  components:
    - mode_id: decision-under-uncertainty
      runs: full
    - mode_id: constraint-mapping
      runs: full
    - mode_id: stakeholder-mapping
      runs: full
    - mode_id: pre-mortem-action
      runs: full
  synthesis_stages:
    - name: decision-frame-integration
      type: parallel-merge
      input: [decision-under-uncertainty, constraint-mapping]
      output: "integrated decision frame: alternatives × probability-weighted outcomes × binding constraints"
    - name: stakeholder-impact-overlay
      type: sequenced-build
      input: [decision-frame-integration, stakeholder-mapping]
      output: "decision frame with per-alternative stakeholder-impact mapping and identified power-asymmetries"
    - name: failure-mode-stress-test
      type: contradiction-surfacing
      input: [stakeholder-impact-overlay, pre-mortem-action]
      output: "leading alternatives stress-tested against pre-mortem failure pathways; revised alternative ranking"
    - name: integrated-decision-architecture
      type: dialectical-resolution
      input: [decision-frame-integration, stakeholder-impact-overlay, failure-mode-stress-test]
      output: "single integrated decision architecture document with recommendation, residual risks, and decision-conditions-to-monitor"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; do not aggregate over low-confidence stakeholder or pre-mortem findings

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [decision_statement, alternatives, criteria, stakeholder_inventory]
    optional: [constraint_inventory, prior_decisions, risk_history]
    notes: "Applies when user supplies alternatives plus stakeholder inventory."
  accessible_mode:
    required: [decision_description]
    optional: [contextual_background, time_pressure_indicator]
    notes: "Default. Mode elicits alternatives, criteria, and stakeholder inventory during execution."
  detection:
    expert_signals: ["alternatives are A, B, C", "stakeholders include", "constraints are", "criteria"]
    accessible_signals: ["big decision", "should I do X", "thinking through this"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the decision, and what are the alternatives you're choosing among?'"
    on_underspecified: "Ask the user whether they want the full Decision Architecture pass or a lighter Decision Under Uncertainty / Constraint Mapping read."
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have the alternatives been generated broadly enough, or is the analysis evaluating an artificially narrow option set?"
    failure_mode_if_unmet: option-set-poverty
  - cq_id: CQ2
    question: "Do the constraint findings actually bound the alternatives, or do they sit in a separate silo from the probability-weighted outcomes?"
    failure_mode_if_unmet: silo-aggregation
  - cq_id: CQ3
    question: "Are the stakeholder impacts surfaced per alternative, or aggregated into a generic stakeholder list disconnected from choice?"
    failure_mode_if_unmet: stakeholder-disconnection
  - cq_id: CQ4
    question: "Has the leading alternative been pre-mortem-stress-tested, or has the synthesis presented a recommendation without naming failure pathways?"
    failure_mode_if_unmet: pre-mortem-omission
  - cq_id: CQ5
    question: "Are the decision-conditions-to-monitor concrete enough to detect drift, or vague enough to be unfalsifiable?"
    failure_mode_if_unmet: monitoring-vagueness

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: option-set-poverty
    detection_signal: "Alternatives enumerated are fewer than three or are obvious binary; no creative or boundary alternative considered."
    correction_protocol: re-dispatch (with explicit alternative-generation prompt)
  - name: silo-aggregation
    detection_signal: "Synthesis stages concatenate constraint, decision-under-uncertainty, stakeholder, and pre-mortem outputs without integration."
    correction_protocol: re-dispatch (synthesis stage with explicit integration prompt)
  - name: stakeholder-disconnection
    detection_signal: "Stakeholder impacts are listed once for the situation generally rather than mapped per alternative."
    correction_protocol: re-dispatch
  - name: pre-mortem-omission
    detection_signal: "pre-mortem-action did not run against the leading alternative."
    correction_protocol: flag and re-dispatch
  - name: monitoring-vagueness
    detection_signal: "Decision-conditions-to-monitor are stated as 'watch how things develop' or similar without concrete signals."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - kahneman-tversky-bias-catalog (when decision is intuition-heavy)
    - knightian-risk-uncertainty-ambiguity (when uncertainty regime is ambiguous)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Decision Architecture is the heaviest mode in T3."
  sideways:
    target_mode_id: decision-clarity
    when: "Output should be a decision-clarity document for a third-party decision-maker rather than your own integrated decision."
  downward:
    target_mode_id: decision-under-uncertainty
    when: "User has time pressure or scope is narrower than initially estimated."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Decision Architecture is the degree to which the four synthesis stages actually integrate component outputs rather than concatenating them. A thin molecular pass runs decision-under-uncertainty, constraint-mapping, stakeholder-mapping, and pre-mortem-action and stitches their outputs together; a substantive pass surfaces tensions among them — for instance, a constraint that invalidates the probability-weighted leading option, or a stakeholder impact that flips the pre-mortem failure scenario. Test depth by asking: does the integrated architecture contain a recommendation that no single component could have produced?

## BREADTH ANALYSIS GUIDANCE

Breadth in Decision Architecture is the catalog of alternatives considered before the architecture narrows to a recommendation. Widen the lens to scan: status-quo alternative; obvious binary; creative third option; do-nothing; reverse-the-question; defer-and-monitor. Even when the recommendation lands on one alternative, breadth is documented in the alternatives section. Breadth also covers stakeholder enumeration: ensure the stakeholder-mapping fragment surveys absent voices, not just visible parties.

## EVALUATION CRITERIA

Decision Architecture is read as a Howard-Raiffa-tradition decision analysis with Kahneman-Tversky bias hygiene, Klein prospective-hindsight stress-testing, and Mitchell-Agle-Wood stakeholder-salience overlay. Because the mode is molecular — four components run in parallel (decision-under-uncertainty, constraint-mapping, stakeholder-mapping, pre-mortem-action) and pass through four sequenced synthesis stages — the evaluator's primary axis is whether the synthesis stages produce an integrated architecture or a stapling of four sub-passes. CQ2 (silo-aggregation) and CQ4 (pre-mortem-omission) are load-bearing: they protect against the two failures that most directly invalidate the deliverable — a non-integrated recommendation, and a recommendation unprotected by a failure-pathway stress test. CQ1 (option set), CQ3 (stakeholder-disconnection), and CQ5 (monitoring vagueness) act as quality gates on inputs and outputs.

Evaluator checks:

1. **Integration vs concatenation (CQ2, load-bearing).** For each synthesis-stage output, ask: could decision-under-uncertainty alone have produced this? Could constraint-mapping alone? Genuine integration names interactions — a constraint that invalidates the probability-weighted leading option, a stakeholder impact that flips the pre-mortem failure scenario, a failure pathway that defeats the constraint-favoured alternative. A document of four parallel sub-pass sections in sequence is silo-aggregation.

2. **Pre-mortem stress test on the leading alternative (CQ4, load-bearing).** The leading alternative must carry an attached failure-pathway atom from pre-mortem-action — past-tense prospective-hindsight narrative, leading indicators, recoverability assessment. A recommendation without pre-mortem coverage is decision architecture without stress test; pre-mortem-omission is the failure mode and the recommendation does not pass.

3. **Option-set breadth (CQ1).** At minimum three alternatives must survive, and at least one must be analyst-generated (creative-third / do-nothing / reverse-the-question / defer-and-monitor). Binary framings with no analyst expansion are option-set-poverty — the architecture is evaluating a pre-narrowed choice set, not a decision space.

4. **Per-alternative stakeholder impact (CQ3).** Stakeholder impacts must attach to specific alternatives, not to the situation generally. A single flat stakeholder enumeration is stakeholder-disconnection; the test is whether the same stakeholder appears under multiple alternatives with different impact directions and magnitudes. The Mitchell-Agle-Wood power-legitimacy-urgency triad is the reading vocabulary; power-asymmetry (a stakeholder bears the impact but cannot influence the decision) is surfaced explicitly.

5. **Monitoring concreteness (CQ5).** Decision-conditions-to-monitor must name observable signals with thresholds and signal latency (how long after the underlying shift the signal appears). "Monitor the situation," "watch for developments," "track relevant signals" are monitoring-vagueness — they look like monitoring but carry no falsifiable trigger.

6. **Residual-risk honesty.** The recommendation atom must carry residual risks the recommendation does NOT eliminate. A clean recommendation without named residual risks is hedging disguised as rigor — the residual-risk surfacing protects against the post-hoc "we considered everything" narrative that flattens decision quality. Kahneman-Tversky overconfidence is the underlying bias.

Confidence is calibrated separately: synthesis-stage atoms inherit lower confidence than component-stage atoms; uniform confidence across both surfaces is miscalibrated. Where the four components disagreed on the leading alternative, the evaluator confirms the disagreement is preserved as a recommendation-tension atom rather than silently reconciled.

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates. Revise to surface tensions where the draft has resolved them prematurely (e.g., stakeholder impacts that quietly contradict the recommendation should be named, not smoothed over). Revise to add concrete monitoring conditions where the draft is vague. Resist revising toward clean-recommendation framing that omits residual risks — Decision Architecture honors residual uncertainty.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **alternative atoms with attached per-alternative attributes (probability-weighted outcomes, binding constraints, stakeholder impacts, failure pathways)**, integrated via the four synthesis stages rather than concatenated. Each atom carries component-provenance tags so the integration is auditable. The atoms are:

1. **Decision-statement atom.** The decision being architected, stated once at the corpus head. Cross-stream paraphrase collapses to one canonical statement.

2. **Alternative atoms.** Each carries: alternative statement, probability-weighted outcomes (provenance: decision-under-uncertainty), binding constraints (provenance: constraint-mapping), stakeholder impacts per stakeholder (provenance: stakeholder-mapping + decision-architecture synthesis), and failure pathways from pre-mortem stress test (provenance: pre-mortem-action). At least three alternatives must survive cross-stream dedup or option-set-poverty fires; at least one must be analyst-generated (creative-third / do-nothing / reverse-the-question / defer-and-monitor).

3. **Per-alternative stakeholder-impact atoms.** Stakeholder impacts attach to specific alternatives, not to the situation generally. Stakeholder-disconnection is the named failure mode; a corpus carrying a single "stakeholder list" rather than per-alternative impact maps is its signature. Each atom names: stakeholder, alternative under consideration, impact direction (positive / negative / neutral), magnitude, and power-asymmetry note where the stakeholder cannot influence the decision but bears the impact.

4. **Constraint-binding atoms.** Each binding constraint atom carries: constraint statement, which alternatives it eliminates or qualifies, and the mechanism of binding (hard / soft / contingent-on-other-decision). Silo-aggregation is the failure mode here: constraints listed once without binding-to-alternatives are concatenation, not integration.

5. **Failure-pathway atoms per leading alternative.** Pre-mortem stress test outputs attach to the leading alternative(s) — failure narratives, leading indicators, and recoverability assessment per pathway. Pre-mortem-omission is the named failure mode; a leading alternative without attached failure pathways does not survive corpus assembly.

6. **Recommendation atom with residual risks.** A single corpus-level recommendation atom carries: recommended alternative, integrated rationale (synthesizing all four component findings, not a single component's verdict), and residual risks that survive the synthesis (the risks the recommendation does NOT eliminate). Residual-risk atoms are load-bearing — a clean-recommendation atom without residual risks is the polished-recommendation failure pattern revision-guidance flags.

7. **Decision-conditions-to-monitor atoms.** Each names: observable signal, alternative or risk it monitors, threshold or pattern that would trigger reassessment, and signal latency (how long after the underlying condition shifts does the signal appear). Monitoring-vagueness is the named failure mode; conditions like "watch how things develop" do not survive — either an observable signal with threshold survives or the atom is dropped.

8. **Confidence map.** Confidence markers attach to individual atoms (probability weights, stakeholder-impact assessments, failure-pathway likelihoods). When the two streams assigned different confidences to the same atom, audit conservatism applies (the lower confidence survives).

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Component-output concatenation residue** — when prose simply transcribes a component's output verbatim ("Constraint mapping identified X, Y, Z" / "Stakeholder mapping found A, B, C") without integrating it into the decision architecture. Silo-aggregation residue; the corpus carries integrated atoms, not concatenated component sections.
- **Stakeholder-list-without-per-alternative-impact** — a single flat stakeholder enumeration not mapped to alternatives. Stakeholder-disconnection residue; either the stakeholders attach to per-alternative-impact atoms or they do not survive.
- **Alternative-paraphrase loops** — same alternative under different framings. Single canonical statement survives.
- **Constraint-restatement** — same binding constraint named multiple times. Single atom survives with the most precise binding mechanism.
- **Vague-monitoring-conditions** — "monitor the situation", "watch for developments", "track relevant signals". Monitoring-vagueness residue; either replaced with concrete observable + threshold or dropped.
- **Recommendation-hedging-without-residual-risk** — soft recommendation language ("on balance perhaps", "it might be worth considering") that elides residual risks rather than naming them. The recommendation atom is allowed to be qualified, but qualification without residual-risk-atoms is hedging-as-substitute-for-rigor.

**What NOT to collapse:**

- **Cross-stream leading-alternative disagreement** — when one stream's integration produced alternative A as the leading recommendation and the other produced alternative B, preserve as a recommendation-tension atom. The disagreement is itself a finding about which integration weights (uncertainty / constraints / stakeholders / failure modes) carry more in this decision; the consolidator must not silently pick.
- **Stakeholder-impact disagreement per alternative** — when streams disagreed on whether a stakeholder is helped or hurt by alternative X, preserve both impact-directions as parallel atoms. The disagreement may reveal that the stakeholder's interest is itself contested or that the alternative's stakeholder-effect depends on implementation choices not yet specified.
- **Constraint-binding disagreement** — when one stream judged constraint C binding on alternative A and the other did not, preserve both judgments. Whether a constraint binds is consequential; silent reconciliation is silo-aggregation residue.
- **Failure-pathway-completeness disagreement** — when streams identified different failure pathways for the same leading alternative, preserve all surviving pathways. Pre-mortem-action's value is breadth of failure-narrative generation; merging non-overlapping pathways is bloat-cutting, but losing distinct pathways is content loss.

## VERIFICATION CRITERIA

Verified means: every component ran (or was flagged as proceeded-with-gap); the four synthesis stages integrated rather than concatenated; the leading alternative carries a pre-mortem stress test; decision-conditions-to-monitor are concrete; confidence map is populated. The five critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structured integrated decision architecture: alternatives with attached attributes (probability-weighted outcomes, binding constraints, stakeholder impacts, failure pathways), single recommendation with residual risks, and concrete monitoring conditions**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Decision frame.** One paragraph stating the decision, its scope, and its time horizon. Frame as "Decision being architected:"

2. **Alternatives with probability-weighted outcomes.** For each alternative A1, A2, A3, …, render a block:
   - **Alternative:** one-line statement
   - **Probability-weighted outcomes:** named outcomes with probability bands (when uncertain) or point estimates (when well-anchored); provenance tag `[from decision-under-uncertainty]`
   - **Origin:** user-supplied / analyst-generated / hybrid

   At minimum three alternatives; at least one analyst-generated.

3. **Binding constraints per alternative.** For each constraint, render: `**[Constraint]** — applies to alternatives: [A_n list]. Mechanism of binding: [hard / soft / contingent-on-other-decision]. Eliminates: [which alternatives the constraint rules out].` Provenance tag `[from constraint-mapping]`. The constraints must attach to alternatives explicitly — silo-aggregation is the named failure mode.

4. **Stakeholder impact per alternative.** A table or per-stakeholder block. For each (stakeholder, alternative) pair, render: stakeholder, alternative, impact direction (positive / negative / neutral), magnitude (high / moderate / low), power-asymmetry note (when the stakeholder cannot influence the decision but bears the impact). Provenance tag `[from stakeholder-mapping]`. The per-alternative attachment is load-bearing — stakeholder-disconnection is the named failure mode.

5. **Failure pathways for the leading alternative(s).** For the leading alternative (and any close runners-up), bulleted list of failure pathways. Each bullet: `**[Failure narrative in past-tense prospective-hindsight]** — causal pathway: [current state → failure]. Leading indicators: [what would reveal the pathway taking]. Recoverability: [recoverable / unrecoverable] — reason: [...].` Provenance tag `[from pre-mortem-action]`. At minimum one failure pathway per leading alternative.

6. **Recommended alternative with residual risks.** A single block: `**Recommended: A_n** — integrated rationale: [synthesis across all four components, not single-component verdict]. Residual risks that survive the recommendation: [list]. What this recommendation does NOT eliminate: [the risks that persist regardless of choice].` The residual-risk content is load-bearing; a clean recommendation without residual risks is hedging-disguised-as-rigor.

7. **Decision conditions to monitor.** Numbered list. Each item: `**[Condition name]** — observable signal: [specific signal with threshold]. Monitors: [which alternative or risk]. Trigger: [pattern that would prompt reassessment]. Signal latency: [how long after underlying shift before signal appears].` Vague conditions ("monitor the situation") do not appear — monitoring-vagueness is the named failure mode.

8. **Confidence map.** Bulleted list of confidence markers attached to probability weights, stakeholder-impact assessments, failure-pathway likelihoods, and the overall recommendation. Per-finding confidence with reason.

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- Provenance tags (`[from decision-under-uncertainty]`, `[from constraint-mapping]`, `[from stakeholder-mapping]`, `[from pre-mortem-action]`) appear inline where atoms originate from specific components — they make integration auditable and silo-aggregation visible.
- Alternative IDs (A1, A2, …) are referenced consistently throughout once introduced.
- Section 4's stakeholder-impact rendering: table form when ≤4 stakeholders × ≤4 alternatives; per-stakeholder blocks when complexity exceeds table-readability.
- The single recommendation in section 6 is integrated, not a single component's verdict. If the recommendation matches one component's leading choice exactly, name what the other three components contributed to the rationale.


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

**Prioritize:** `requires`, `enables`, `qualifies`, `supports`, `contradicts`
**Deprioritize:** `analogous-to`, `parent`

*Family: decision-risk. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
