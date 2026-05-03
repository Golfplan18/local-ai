---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Pre-Mortem (Action)

```yaml
# 0. IDENTITY
mode_id: pre-mortem-action
canonical_name: Pre-Mortem (Action)
suffix_rule: analysis
educational_name: pre-mortem on the action plan (Klein, Tetlock lineage)

# 1. TERRITORY AND POSITION
territory: T6-future-exploration
gradation_position:
  axis: stance
  value: adversarial-future
adjacent_modes_in_territory:
  - mode_id: pre-mortem-fragility
    relationship: parsed-sibling (stance-counterpart on system rather than plan; lives in T7; shares klein-pre-mortem lens)
  - mode_id: consequences-and-sequel
    relationship: stance-counterpart (neutral-forward depth-light)
  - mode_id: probabilistic-forecasting
    relationship: stance-counterpart (neutral-forward depth-thorough; built Wave 2)
  - mode_id: scenario-planning
    relationship: stance-counterpart (neutral-future narrative-output)
  - mode_id: wicked-future
    relationship: depth-molecular sibling (built Wave 4)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "we're about to launch / commit to this plan"
    - "imagine it's six months from now and this failed"
    - "before we sign off, what would have to go wrong"
    - "looking ahead to roll-out, where would I bet this trips"
    - "team is over-confident and I want a sober failure-walk"
  prompt_shape_signals:
    - "pre-mortem"
    - "pre-mortem this plan"
    - "imagine this failed"
    - "Klein pre-mortem"
    - "prospective hindsight"
    - "what would the post-mortem say"
disambiguation_routing:
  routes_to_this_mode_when:
    - "the artifact under analysis is an action plan, decision, launch, or course-of-action"
    - "user wants prospective-hindsight failure narration of that plan"
    - "user is pre-commitment and wants to surface failure modes before locking in"
  routes_away_when:
    - "the artifact is a system, design, or structure rather than a plan to execute" → pre-mortem-fragility (T7)
    - "user wants neutral forecast or scenarios rather than failure-mode walk" → probabilistic-forecasting / scenario-planning
    - "user wants light forward causal cascade without adversarial framing" → consequences-and-sequel
    - "user wants adversarial-actor stress test (someone is trying to defeat this)" → red-team-assessment / red-team-advocate (T15)
when_not_to_invoke:
  - "User is post-failure and wants backward causal trace" → root-cause-analysis (T4)
  - "User wants to evaluate the plan's argumentative structure rather than its execution" → T1 modes
  - "Plan is so under-specified that no failure narrative is possible — degrade to elicitation"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: adversarial

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [action_plan, decision_horizon, success_criteria]
    optional: [stakeholder_inventory, prior_attempts_history, known_assumptions]
    notes: "Applies when user supplies a structured plan with named milestones, decision points, or success criteria."
  accessible_mode:
    required: [plan_description]
    optional: [why_user_wants_pre_mortem, decision_horizon_estimate]
    notes: "Default. Mode infers success criteria and decision horizon from the plan description and elicits during execution if missing."
  detection:
    expert_signals: ["the plan is", "milestones include", "success criteria are", "decision horizon", "rollout plan"]
    accessible_signals: ["pre-mortem this", "imagine it failed", "we're about to launch", "before we commit"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe the plan you want to pre-mortem and roughly when you expect to know whether it worked?'"
    on_underspecified: "Ask: 'What does success look like for this plan, so I can imagine its absence?'"
output_contract:
  artifact_type: scenarios
  required_sections:
    - imagined_failure_narrative
    - failure_mode_inventory
    - causal_pathways_to_failure
    - leading_indicators_per_failure_mode
    - precommitment_mitigations
    - residual_unmitigated_risks
    - confidence_per_finding
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the analysis genuinely adopted prospective-hindsight stance (writing as though the failure has already occurred), or has it slipped into hedged forward-projection?"
    failure_mode_if_unmet: stance-slippage
  - cq_id: CQ2
    question: "Are the named failure modes specific to this plan's mechanism, or are they generic project-failure tropes (scope creep, communication breakdown) that would apply to any plan?"
    failure_mode_if_unmet: generic-failure-trope
  - cq_id: CQ3
    question: "Have failure pathways been traced to leading indicators the team could observe pre-failure, or do the failures only become visible at the post-mortem?"
    failure_mode_if_unmet: lagging-indicator-only
  - cq_id: CQ4
    question: "Have pre-commitment mitigations been distinguished from post-hoc remediations, given that pre-mortem's value is in the pre-commitment window?"
    failure_mode_if_unmet: post-hoc-conflation

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: stance-slippage
    detection_signal: "Output uses forward conditional language ('this might fail if...') rather than retrospective ('the plan failed because...')."
    correction_protocol: re-dispatch
  - name: generic-failure-trope
    detection_signal: "Failure modes named are domain-agnostic clichés (scope creep, communication breakdown, stakeholder misalignment) without plan-specific mechanism."
    correction_protocol: re-dispatch
  - name: lagging-indicator-only
    detection_signal: "Leading-indicators section is empty, or all indicators are post-failure observations."
    correction_protocol: flag
  - name: post-hoc-conflation
    detection_signal: "Mitigations include actions that can only be taken after the failure has begun."
    correction_protocol: flag
  - name: optimism-residue
    detection_signal: "Failure-mode inventory is shorter than success-pathway language elsewhere in the analysis suggests; analyst's prior on success bleeds through."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - klein-pre-mortem
  optional:
    - tetlock-superforecasting (when failure pathways involve probabilistic estimation)
    - kahneman-planning-fallacy (when plan timelines are central to the analysis)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~1min
escalation_signals:
  upward:
    target_mode_id: wicked-future
    when: "Plan is entangled with multiple stakeholder conflicts and feedback loops; failure modes interact across systems."
  sideways:
    target_mode_id: pre-mortem-fragility
    when: "On reflection the artifact is a system or design rather than a plan to execute; the relevant failures are structural rather than action-execution."
  downward:
    target_mode_id: consequences-and-sequel
    when: "User wants neutral forward cascade rather than adversarial failure walk."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Pre-Mortem (Action) is the specificity with which the failure narrative is bound to *this plan's mechanism*. A thin pass produces a generic failure list; a substantive pass writes the post-mortem as though the failure happened, names the specific decision point or assumption that broke, traces the causal pathway from that breakage to the visible failure, and identifies the leading indicator that would have shown the breakage as it began. Test depth by asking: could this pre-mortem narrative only be written about this plan, or would it read identically for any project of comparable shape?

## BREADTH ANALYSIS GUIDANCE

Widening the lens in Pre-Mortem (Action) means scanning the failure-mode landscape: execution failures (the team didn't do what the plan called for), assumption failures (a load-bearing premise was wrong), context-shift failures (the world changed during execution), interaction failures (the plan succeeded narrowly but produced consequences that defeated the larger purpose), and motivational failures (the team disengaged before completion). A breadth-passing analysis surveys all five classes before narrowing to the two-or-three most plausible failure narratives for the prospective-hindsight pass.

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) stance integrity (prospective hindsight, not hedged projection); (CQ2) plan-specific vs. generic failures; (CQ3) leading indicators present; (CQ4) pre-commitment mitigations distinguished. The named failure modes (stance-slippage, generic-failure-trope, lagging-indicator-only, post-hoc-conflation, optimism-residue) are the evaluation checklist. A passing Pre-Mortem (Action) output names plan-specific failure mechanisms in past-tense narrative, cites observable leading indicators per failure mode, and offers mitigations the team can lock in *before* commitment.

## REVISION GUIDANCE

Revise to restore prospective-hindsight stance where the draft has slipped into hedged forward-projection. Revise to replace generic failure tropes with plan-specific mechanisms tied to named decision points or assumptions. Revise to add leading indicators where the failure only becomes visible at post-mortem. Resist revising toward optimism — the mode's analytical character is adversarial-future on the action plan; softening the failure narratives toward "manageable risks" is a failure mode, not a polish.

## CONSOLIDATION GUIDANCE

Consolidate as a structured scenarios artifact with the seven required sections. The imagined failure narrative is written in past tense as the post-mortem the team would have produced after the failure. Failure-mode inventory is organized by class (execution / assumption / context-shift / interaction / motivational). Causal pathways link each failure mode to the decision point or assumption that broke. Leading indicators are observable signals the team can monitor; mitigations are pre-commitment actions only. Residual unmitigated risks are named explicitly.

## VERIFICATION CRITERIA

Verified means: the failure narrative is in past-tense prospective-hindsight stance throughout; every named failure mode has plan-specific mechanism (no generic tropes); every failure mode has at least one leading indicator the team could observe pre-failure; every mitigation is a pre-commitment action (not a post-hoc remediation); the four critical questions are addressable from the output. Confidence per finding accompanies each major claim.

## CAVEATS AND OPEN DEBATES

**Parsing rationale (Decision D).** This mode is one of two parsed from the historical "Pre-Mortem" candidate that appeared to fit two territories. Per the parsing principle, dual-citizenship is rejected: the operation on an action plan (T6, future exploration with adversarial-future stance) and the operation on a system/design (T7, risk and failure analysis) are different operations sharing a name. Both modes share the `klein-pre-mortem` lens (Klein 2007 *HBR*; Mitchell, Russo & Pennington 1989 on prospective hindsight), but their input contracts, output contracts, and critical questions diverge. When in doubt about whether the artifact is plan-shaped or system-shaped, route via the disambiguating question: "Is this about an action plan that could fail, or about a system or design with structural fragilities?" Sibling: `pre-mortem-fragility` (T7).
