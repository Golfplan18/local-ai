---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
---

# MODE: Cui Bono

```yaml
# 0. IDENTITY
mode_id: cui-bono
canonical_name: Cui Bono
suffix_rule: analysis
educational_name: who-benefits analysis (cui bono)

# 1. TERRITORY AND POSITION
territory: T2-interest-and-power
gradation_position:
  axis: complexity
  value: simple
adjacent_modes_in_territory:
  - mode_id: stakeholder-mapping
    relationship: complexity-heavier sibling (multi-party-descriptive — lives in T8)
  - mode_id: boundary-critique
    relationship: stance-critical counterpart (Ulrich CSH)
  - mode_id: wicked-problems
    relationship: complexity-molecular sibling
  - mode_id: decision-clarity
    relationship: depth-molecular sibling (decision-maker-output)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "trying to understand who's behind this"
    - "want to know who benefits from"
    - "feels like someone's pushing this for a reason"
    - "this policy or standard sounds objective but I suspect it isn't"
  prompt_shape_signals:
    - "who benefits"
    - "cui bono"
    - "whose interests"
    - "who's pushing this"
    - "trace the interests"
    - "who gains from X"
disambiguation_routing:
  routes_to_this_mode_when:
    - "this one situation, single set of beneficiaries"
    - "quick read on who gains from this state of affairs"
    - "policy or institutional position with distributional consequences"
  routes_away_when:
    - "landscape of multiple parties with different stakes" → stakeholder-mapping
    - "tangled / wicked / many systems interacting" → wicked-problems
    - "voices being left out of the picture entirely" → boundary-critique
    - "produce a decision document for a decision-maker" → decision-clarity
    - "questioning the empirical foundations of a position" → paradigm-suspension
when_not_to_invoke:
  - "User is evaluating an argument's soundness, not its sponsoring interests" → T1
  - "User is asking about active negotiation strategy" → T13
  - "Multiple competing explanations for the same evidence — adjudicate via diagnosticity" → T5 competing-hypotheses

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [situation_or_artifact, optional_actor_inventory]
    optional: [historical_context, prior_interest_analyses, distributional_parameters]
    notes: "Applies when user explicitly references actors by name or supplies an actor inventory or named institutional parameters."
  accessible_mode:
    required: [situation_or_artifact]
    optional: [related_context]
    notes: "Default. Mode infers actor inventory and parameters from the situation."
  detection:
    expert_signals: ["actor inventory", "stakeholders are X, Y, Z", "interest groups include", "policy text", "regulatory framework"]
    accessible_signals: ["who benefits", "whose interests", "who's behind this", "trace the interests"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe the situation, decision, or paste the article/document you want me to look at?'"
    on_underspecified: "Ask: 'What's the situation, decision, or text you want a who-benefits read on?'"
output_contract:
  artifact_type: mapping
  required_sections:
    - institutional_authorship
    - stated_rationale
    - distributional_impact
    - alternative_design_from_opposite_constituency
    - motivational_analysis_fgl
    - legitimate_value
    - confidence_per_finding
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the identified beneficiaries actually positioned to benefit, or is the inference symbolic?"
    failure_mode_if_unmet: symbolic-inference (mistaking narrative resonance for actual benefit)
  - cq_id: CQ2
    question: "Are there beneficiaries the analysis is missing because they are not visible from the artifact's frame?"
    failure_mode_if_unmet: frame-bounded-blindness
  - cq_id: CQ3
    question: "Are the costs identified actually borne by the parties named, or is incidence misattributed?"
    failure_mode_if_unmet: cost-incidence-error
  - cq_id: CQ4
    question: "Has FGL (Fear, Greed, Laziness) been applied symmetrically across constituencies, or only against the disfavoured side?"
    failure_mode_if_unmet: asymmetric-fgl

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: symbolic-inference
    detection_signal: "Beneficiary identified by ideological alignment rather than concrete benefit pathway."
    correction_protocol: flag
  - name: frame-bounded-blindness
    detection_signal: "All identified parties share the artifact's frame; no parties from outside the frame appear."
    correction_protocol: escalate
  - name: cost-incidence-error
    detection_signal: "Costs are attributed to a party without a concrete payment, time, or freedom-loss pathway."
    correction_protocol: flag
  - name: conspiracy-trap
    detection_signal: "Distributional outcomes attributed to deliberate coordination without explicit evidence; intent assumed where structural incentives suffice."
    correction_protocol: flag
  - name: cynicism-trap
    detection_signal: "Position concluded to have no legitimate basis; legitimate value collapsed into distributional overlay."
    correction_protocol: flag
  - name: mirror-trap
    detection_signal: "Alternative design reflects analyst's preference rather than the disadvantaged constituency's interests."
    correction_protocol: re-dispatch
  - name: asymmetric-fgl
    detection_signal: "FGL applied to only one constituency; opposing party's motives uninspected."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - rumelt-strategy-kernel
    - ulrich-csh-boundary-categories
    - public-choice-theory
    - fgl-fear-greed-laziness
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: stakeholder-mapping
    when: "Beneficiary inventory exceeds 5 parties or interest structure is multi-layered."
  sideways:
    target_mode_id: boundary-critique
    when: "Most identified parties are inside one frame; boundary-critique surfaces parties outside it."
  downward:
    target_mode_id: null
    when: "Cui Bono is already the lightest mode in T2."
```

## DEPTH ANALYSIS GUIDANCE

Going deeper in Cui Bono means tracing concrete benefit pathways (money flows, power-position changes, time-and-attention captures, narrative-control gains) rather than asserting alignment-based benefit. A thin pass names parties; a substantive pass names the institutional author, the specific parameters or definitional choices that drive distribution, and the counterparty's loss-pathway. Apply FGL (Fear, Greed, Laziness) explicitly per constituency. Test depth by asking: could the analysis predict how each beneficiary would behave if the situation changed, and could it name the parameter whose alteration would shift the distribution?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for parties not visible from the artifact's own frame: parties who would benefit if the situation were framed differently; parties who pay costs the artifact treats as natural; parties absent from the discussion whose voices would change the analysis. Construct the alternative design that would emerge from the opposite constituency's interests, with equal technical sophistication. Identify the legitimate value the current position serves, separate from its distributional overlay. Breadth markers: the analysis surveys the boundary of who is and isn't being asked, and offers an alternative as well-formed as the original.

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) symbolic vs. concrete benefit; (CQ2) frame-bounded blindness; (CQ3) cost-incidence accuracy; (CQ4) FGL symmetry. The named failure modes (symbolic-inference, frame-bounded-blindness, cost-incidence-error, conspiracy-trap, cynicism-trap, mirror-trap, asymmetric-fgl) are the evaluation checklist. A passing Cui Bono output names institutional author, names benefit pathways concretely with specific parameters, surfaces an alternative design from the disadvantaged constituency, applies FGL symmetrically across constituencies, separates legitimate value from distributional overlay, and assigns confidence per finding.

## REVISION GUIDANCE

Revise to add concrete pathways where the draft asserts benefit without mechanism. Revise to add specific parameters where vague "incentive structure" language sits unanchored. Revise to add boundary-cases (parties absent or marginalized). Revise to make the alternative design technically sophisticated rather than cosmetic, and to ground it in the disadvantaged constituency's interests rather than the analyst's preferences. Resist revising toward neutrality if the analysis surfaces real power-asymmetries — the mode is descriptive of interest structure, not neutralizing of it. Silent upgrade from structural incentive attribution to intent-attribution during revision is a failure unless new evidence is explicitly cited.

## CONSOLIDATION GUIDANCE

Consolidate as a structured mapping with the seven required sections. The institutional author appears as the source node in any structural representation; the parameters driving distribution are named explicitly; beneficiaries and cost-bearers are separable. The alternative-constituency design is emitted as its own section, not as a competing primary analysis. FGL attributions accompany each named constituency. Each finding carries a confidence rating. The structured format permits row-level audit of which party benefits how, by what mechanism, with what cost-incidence.

## VERIFICATION CRITERIA

Verified means: the institutional author is named explicitly; at least two specific parameters driving distribution are stated; the alternative design is constructed with equal technical rigor and from the disadvantaged constituency's interests; FGL is applied to at least two constituencies; legitimate value is separated from distributional overlay; every named beneficiary has a concrete benefit pathway; every named cost has a concrete bearer; the analysis has surfaced absent voices or explicitly noted that boundary-critique was deferred. Confidence per finding accompanies every claim. The four critical questions are addressable from the output.
