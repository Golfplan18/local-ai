---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Pre-Mortem (Fragility)

```yaml
# 0. IDENTITY
mode_id: pre-mortem-fragility
canonical_name: Pre-Mortem (Fragility)
suffix_rule: analysis
educational_name: pre-mortem on structural fragilities (Klein, Taleb adjacent)

# 1. TERRITORY AND POSITION
territory: T7-risk-and-failure
gradation_position:
  axis: stance
  value: adversarial-future
adjacent_modes_in_territory:
  - mode_id: pre-mortem-action
    relationship: parsed-sibling (stance-counterpart on plan rather than system; lives in T6; shares klein-pre-mortem lens)
  - mode_id: fragility-antifragility-audit
    relationship: depth-heavier sibling (Talebian asymmetry-focused; built Wave 3)
  - mode_id: failure-mode-scan
    relationship: depth-light sibling (gap-deferred per CR-6)
  - mode_id: fault-tree
    relationship: depth-thorough sibling (gap-deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "where could this design break"
    - "what failure modes does this system exhibit"
    - "which parts of this structure are load-bearing single points"
    - "if I were stress-testing this architecture, where would I look"
    - "before we ship this design, what fragilities exist"
  prompt_shape_signals:
    - "pre-mortem this design"
    - "pre-mortem this system"
    - "structural fragilities"
    - "where will this break"
    - "single points of failure"
    - "Klein pre-mortem on this architecture"
disambiguation_routing:
  routes_to_this_mode_when:
    - "the artifact under analysis is a system, design, structure, architecture, or institution"
    - "user wants prospective-hindsight failure narration of structural breakage"
    - "the relevant failures are about how the structure responds to stress, not about how a team executes"
  routes_away_when:
    - "the artifact is an action plan or course of action rather than a structure" → pre-mortem-action (T6)
    - "user wants Talebian asymmetry analysis (fragile / robust / antifragile)" → fragility-antifragility-audit
    - "user wants adversarial-actor stress test (someone is trying to defeat this)" → red-team-assessment / red-team-advocate (T15)
    - "user wants exhaustive structured fault decomposition" → fault-tree (when built)
when_not_to_invoke:
  - "User is post-failure and wants backward causal trace" → root-cause-analysis (T4)
  - "User wants to evaluate the design as an argument or proposal" → balanced-critique or steelman-construction (T15)
  - "Design is so under-specified that no failure narrative is possible — degrade to elicitation"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: adversarial

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [system_or_design, structural_components, intended_function]
    optional: [stress_envelope, known_load_assumptions, prior_failures_in_class]
    notes: "Applies when user supplies a structured design with named components, dependencies, or operating envelope."
  accessible_mode:
    required: [system_description]
    optional: [why_user_wants_fragility_check, intended_use_context]
    notes: "Default. Mode infers components and intended function from the description and elicits stress envelope during execution if absent."
  detection:
    expert_signals: ["the architecture", "the design", "the system has", "components include", "dependencies are", "operating envelope"]
    accessible_signals: ["where will this break", "structural fragilities", "pre-mortem this design", "what's the weak point"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe the system or design and what it's meant to do under what conditions?'"
    on_underspecified: "Ask: 'What range of conditions is this meant to operate within, so I can imagine the conditions in which it breaks?'"
output_contract:
  artifact_type: scenarios
  required_sections:
    - imagined_breakage_narrative
    - structural_fragility_inventory
    - load_pathways_to_breakage
    - leading_indicators_per_fragility
    - structural_mitigations
    - residual_unmitigated_fragilities
    - confidence_per_finding
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the analysis genuinely adopted prospective-hindsight stance on the system (writing as though the breakage has already occurred), or has it slipped into hedged forward-projection?"
    failure_mode_if_unmet: stance-slippage
  - cq_id: CQ2
    question: "Are the named fragilities specific to this structure's components and dependencies, or are they generic system-failure tropes (single point of failure, cascading failure) without structural specificity?"
    failure_mode_if_unmet: generic-fragility-trope
  - cq_id: CQ3
    question: "Have load pathways been traced from operating-envelope stresses to specific structural elements that yield, or do the breakages appear without mechanism?"
    failure_mode_if_unmet: mechanism-gap
  - cq_id: CQ4
    question: "Have structural mitigations been distinguished from operational workarounds, given that fragility is a property of the structure rather than its operation?"
    failure_mode_if_unmet: structure-operation-conflation

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: stance-slippage
    detection_signal: "Output uses forward conditional language ('this might fail under load') rather than retrospective ('the system broke when load exceeded X because component Y could not...')."
    correction_protocol: re-dispatch
  - name: generic-fragility-trope
    detection_signal: "Fragilities named are pattern-matched abstractions (single point of failure, cascading failure, brittle dependency) without naming the specific component, link, or interface."
    correction_protocol: re-dispatch
  - name: mechanism-gap
    detection_signal: "A fragility is asserted without naming the load condition that triggers it or the structural property that yields under that load."
    correction_protocol: flag
  - name: structure-operation-conflation
    detection_signal: "Mitigations include operational practices (better monitoring, more careful operators) rather than structural changes."
    correction_protocol: flag
  - name: actor-modeling-drift
    detection_signal: "Failure narratives invoke an adversarial actor trying to defeat the system; this is Red Team's territory, not structural fragility."
    correction_protocol: re-dispatch (or escalate to red-team-assessment / red-team-advocate)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - klein-pre-mortem
  optional:
    - taleb-fragile-robust-antifragile (when Talebian framing fits)
    - perrow-normal-accidents (when system is tightly coupled)
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~1min
escalation_signals:
  upward:
    target_mode_id: fragility-antifragility-audit
    when: "Analysis needs Talebian asymmetry framing (fragile vs. robust vs. antifragile) or formal stress-envelope decomposition."
  sideways:
    target_mode_id: pre-mortem-action
    when: "On reflection the artifact is a plan to execute rather than a structure; the relevant failures are about action execution rather than structural breakage."
  downward:
    target_mode_id: null
    when: "Pre-Mortem (Fragility) is the lightest stance-adversarial-future entry in T7; downward routing is to a lighter-depth mode within T7 once Failure Mode Scan is built."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Pre-Mortem (Fragility) is the specificity with which the breakage narrative is bound to *this structure's components and load pathways*. A thin pass names abstract fragility patterns; a substantive pass writes the post-incident report as though the breakage happened, names the specific component or interface that yielded, traces the load condition that exceeded the structural property, and identifies leading indicators (drift, saturation, latency increase, error rate climb) that would have shown the structure approaching failure. Test depth by asking: could this fragility narrative only be written about this design, or would it read identically for any system of comparable architecture?

## BREADTH ANALYSIS GUIDANCE

Widening the lens in Pre-Mortem (Fragility) means scanning the structural-fragility landscape: load fragilities (the structure breaks under unusual but specifiable load), dependency fragilities (a component depends on a fragile-or-absent counterpart), interface fragilities (the joint between components is the failure surface), state fragilities (the structure breaks when accumulated state crosses a threshold), and emergent fragilities (the structure exhibits a failure mode that no single component shows). A breadth-passing analysis surveys all five classes before narrowing to the two-or-three most plausible breakage narratives for the prospective-hindsight pass.

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) stance integrity (prospective hindsight on the structure); (CQ2) structure-specific vs. generic fragility tropes; (CQ3) load pathway with mechanism present; (CQ4) structural vs. operational mitigations distinguished. The named failure modes (stance-slippage, generic-fragility-trope, mechanism-gap, structure-operation-conflation, actor-modeling-drift) are the evaluation checklist. A passing Pre-Mortem (Fragility) output names structure-specific yield mechanisms in past-tense narrative, cites observable leading indicators per fragility, and offers structural mitigations rather than operational workarounds.

## REVISION GUIDANCE

Revise to restore prospective-hindsight stance where the draft has slipped into hedged forward-projection. Revise to replace generic fragility tropes with structure-specific mechanisms tied to named components, interfaces, or dependencies. Revise to add load pathways where the breakage appears without mechanism. Resist revising toward operational fixes — the mode's analytical character is adversarial-future on the structure; recommending "more careful monitoring" instead of structural change collapses fragility into operation. Resist drift into adversarial-actor framing; if the analysis is really about an attacker, escalate to the red-team modes rather than revise.

## CONSOLIDATION GUIDANCE

Consolidate as a structured scenarios artifact with the seven required sections. The imagined breakage narrative is written in past tense as the post-incident report the team would produce after the structural failure. Structural fragility inventory is organized by class (load / dependency / interface / state / emergent). Load pathways link each fragility to the operating-envelope condition that triggers it and the structural property that yields. Leading indicators are observable pre-failure signals; mitigations are structural changes only (component replacement, interface hardening, dependency removal, state-bound enforcement). Residual unmitigated fragilities are named explicitly.

## VERIFICATION CRITERIA

Verified means: the breakage narrative is in past-tense prospective-hindsight stance throughout; every named fragility has a structure-specific mechanism (no generic tropes); every fragility has at least one leading indicator observable pre-failure; every mitigation is a structural change (not an operational workaround); no narrative is actually about an adversarial actor; the four critical questions are addressable from the output. Confidence per finding accompanies each major claim.

## CAVEATS AND OPEN DEBATES

**Parsing rationale (Decision D).** This mode is one of two parsed from the historical "Pre-Mortem" candidate that appeared to fit two territories. Per the parsing principle, dual-citizenship is rejected: the operation on an action plan (T6, future exploration with adversarial-future stance) and the operation on a system/design (T7, risk and failure analysis) are different operations sharing a name. Both modes share the `klein-pre-mortem` lens (Klein 2007 *HBR*; Mitchell, Russo & Pennington 1989 on prospective hindsight), but their input contracts, output contracts, and critical questions diverge. When in doubt about whether the artifact is plan-shaped or system-shaped, route via the disambiguating question: "Is this about an action plan that could fail, or about a system or design with structural fragilities?" Sibling: `pre-mortem-action` (T6).
