---
nexus:
  - ora
type: mode
tags:
  - framework/instruction
  - architecture
date created: 2026-04-17
date modified: 2026-05-01
---

# MODE: Consequences and Sequel

```yaml
# 0. IDENTITY
mode_id: consequences-and-sequel
canonical_name: Consequences and Sequel
suffix_rule: analysis
educational_name: forward causal-cascade tracing (de Bono C&S, second-and-third-order effects)

# 1. TERRITORY AND POSITION
territory: T6-future-exploration
gradation_position:
  axis: depth
  value: light
  stance_axis_value: forward
adjacent_modes_in_territory:
  - mode_id: probabilistic-forecasting
    relationship: depth-thorough sibling (probability-output)
  - mode_id: scenario-planning
    relationship: depth-thorough sibling (narrative-output)
  - mode_id: pre-mortem-action
    relationship: stance-adversarial sibling (forward-on-plan)
  - mode_id: wicked-future
    relationship: depth-molecular sibling
  - mode_id: backcasting
    relationship: stance-constructive counterpart (gap-deferred)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "what would happen if we did X"
    - "what are the downstream effects"
    - "what are the second-order consequences"
    - "if we ship this, what does it lead to"
  prompt_shape_signals:
    - "consequences"
    - "sequel"
    - "second-order"
    - "third-order"
    - "cascade forward"
    - "what does this lead to"
disambiguation_routing:
  routes_to_this_mode_when:
    - "forward-from-action question, light pass to map immediate-through-third-order effects"
    - "linear cascade (may fork but not loop) — want a quick look at what propagates from a decision"
    - "willing to spend ~5 minutes for a focused cascade rather than a full scenario set"
  routes_away_when:
    - "circular feedback is the defining structure" → systems-dynamics-causal
    - "want probability-weighted forecasts" → probabilistic-forecasting
    - "want narrative scenario explorations" → scenario-planning
    - "specifically asking what could go wrong with this plan" → pre-mortem-action
    - "tracing backward from a symptom" → root-cause-analysis (T4)
when_not_to_invoke:
  - "User is choosing among options with risk as one input among several" → T3 (decision-under-uncertainty)
  - "User is evaluating a single proposal's benefit/risk envelope" → benefits-analysis (T15)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: generative

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [proposed_action, time_horizon_of_interest, domain_context]
    optional: [historical_analogues, prior_cascade_attempts]
    notes: "Applies when user supplies a clearly stated action with relevant time horizon and domain context."
  accessible_mode:
    required: [proposed_action_or_event]
    optional: [related_context, what_user_cares_about]
    notes: "Default. Mode infers time horizon from the action's nature."
  detection:
    expert_signals: ["second-order effects", "downstream cascade", "sequel analysis", "policy impact"]
    accessible_signals: ["what would happen if", "what does this lead to", "if we do X then what"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the action or event you want me to trace forward consequences for?'"
    on_underspecified: "Ask: 'How far forward do you want to look — immediate effects only, or out to second and third order?'"
output_contract:
  artifact_type: mapping
  required_sections:
    - action_or_event
    - first_order_consequences
    - second_order_consequences
    - third_order_consequences_where_tractable
    - time_horizon_classification
    - reinforcing_and_counteracting_branches
    - cross_domain_effects
    - unintended_consequences
    - leading_indicators
    - feedback_loop_flag_if_present
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the cascade reached at least third order on at least one branch, or has it stopped at first-order effects?"
    failure_mode_if_unmet: first-order-stop
  - cq_id: CQ2
    question: "Does every causal link state a mechanism, or are some links assertions of association without explanation?"
    failure_mode_if_unmet: association-without-mechanism
  - cq_id: CQ3
    question: "Are effects distributed across time horizons (immediate / short / medium / long), or are they all at one horizon?"
    failure_mode_if_unmet: single-horizon
  - cq_id: CQ4
    question: "Are unintended consequences — effects outside the proposer's stated goal — surfaced and distinguished from intended effects?"
    failure_mode_if_unmet: intended-effects-only
  - cq_id: CQ5
    question: "If any link returns influence to an earlier node, has the analysis flagged the feedback loop and proposed handoff to systems-dynamics-causal (T4) or systems-dynamics-structural (T17) per parse, rather than masquerading the cycle as a DAG?"
    failure_mode_if_unmet: feedback-collapse

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: first-order-stop
    detection_signal: "Cascade names immediate effects only; no second- or third-order branch is traced."
    correction_protocol: re-dispatch (extend at least one branch to third order)
  - name: association-without-mechanism
    detection_signal: "Causal links assert X → Y without naming the mechanism by which X produces Y."
    correction_protocol: flag (request mechanism per link)
  - name: single-horizon
    detection_signal: "All effects sit at one time horizon (e.g., everything is immediate or everything is long-term)."
    correction_protocol: re-dispatch (redistribute across at least three horizons)
  - name: intended-effects-only
    detection_signal: "Cascade traces only the proposer's stated goals; no effect outside the goal frame is named."
    correction_protocol: re-dispatch (add at least one unintended consequence)
  - name: feedback-collapse
    detection_signal: "Cycle present in the cascade but emitted as if linear; no SD handoff proposed."
    correction_protocol: escalate (suppress envelope, route to systems-dynamics-causal)
  - name: reinforcing-counteracting-collapse
    detection_signal: "All branches are amplifying or all dampening; no distinction drawn between the two."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - de-bono-consequence-and-sequel
  optional:
    - reinforcing-counteracting-distinction
    - cross-domain-cascade-patterns (when the cascade traverses multiple domains)
    - leading-indicators-methodology (when distant effects need near-term proxies)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: probabilistic-forecasting
    when: "Cascade reveals enough structure that probability weights would clarify which paths matter."
  sideways:
    target_mode_id: scenario-planning
    when: "Cascade branches diverge enough that narrative scenarios would carry the analysis better than a DAG."
  downward:
    target_mode_id: null
    when: "Consequences and Sequel is already the lightest forward-exploration mode in T6."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Consequences and Sequel is the cascade's depth in causal levels — first-order, second-order, third-order — and the rigour of mechanism statement at each link. A thin pass names immediate effects of the action; a substantive pass continues each first-order effect into its second-order consequences and at least one third-order consequence on a leading branch, with the mechanism for each link stated explicitly. Each effect is tagged with a time horizon (immediate / short / medium / long), and reinforcing branches (amplification) are distinguished from counteracting branches (dampening). Test depth by asking: could the analysis predict which specific signal would appear first if the cascade is unfolding as projected?

## BREADTH ANALYSIS GUIDANCE

Breadth in Consequences and Sequel is the catalog of branches considered — including branches the proposer would not name. Widen the lens by scanning: which domains the cascade crosses (an action in one domain often produces effects in others); which constituencies experience effects the proposer has not framed as effects; which feedback loops appear (and trigger SD handoff); which unintended consequences emerge from the structure rather than from the action's intent. Breadth markers: at least one cross-domain effect is named, at least one unintended consequence is surfaced, and time horizons span at least three of the four bands.

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) third-order reached on at least one branch; (CQ2) mechanism stated per link; (CQ3) time horizons distributed; (CQ4) unintended consequences surfaced; (CQ5) feedback loops flagged for SD handoff rather than emitted as DAG. The named failure modes are the evaluation checklist. A passing Consequences and Sequel output reaches third order on at least one branch, states a mechanism for every link, distributes effects across at least three time horizons, names at least one unintended consequence, and either contains no cycles or has flagged the cycle and proposed handoff.

## REVISION GUIDANCE

Revise to extend any branch that stops at first-order by asking: each effect becomes a cause — what does this then produce? Revise to add a mechanism sentence to any link that asserts X → Y without explaining how. Revise to redistribute effects across time horizons when one horizon dominates. If a cycle is discovered during revision, suppress the envelope entirely and propose handoff to `systems-dynamics-causal` — Consequences and Sequel cannot emit cycles, and forcing a cycle into a DAG misrepresents the structure.

## CONSOLIDATION GUIDANCE

Consolidate as a structured mapping with the ten required sections in order: action or event; first-order consequences; second-order consequences; third-order consequences where tractable; time-horizon classification; reinforcing and counteracting branches; cross-domain effects; unintended consequences; leading indicators; feedback-loop flag if present. Format: structured. Each effect carries a time-horizon tag and a mechanism for the link from its parent.

## VERIFICATION CRITERIA

Verified means: at least one path reaches length 3 (third order); every link in the cascade has a stated mechanism; effects span at least three of the four time-horizon bands; at least one unintended consequence is named; at least one reinforcing branch and at least one counteracting branch are distinguished; if any cycle appears, it is flagged and SD handoff is proposed. Confidence per major branch is stated (high for well-precedented cascades; lower for novel territory).

## CAVEATS AND OPEN DEBATES

Consequences and Sequel operates as the Tier-1 light variant in the T6 future-exploration ladder; it complements but does not substitute for the heavier modes — `probabilistic-forecasting` (when probability weights matter), `scenario-planning` (when divergent narratives carry the analysis better than a single cascade), `wicked-future` (the molecular variant for tangled forward problems). The mode's load-bearing constraint is acyclicity: when a cycle appears in the cascade, the right move is handoff to `systems-dynamics-causal`, not forcing the cycle into a DAG that misrepresents the structure. The third-order discipline (extend at least one branch to depth 3) is the discipline that distinguishes a real cascade from an enumeration of immediate effects.
