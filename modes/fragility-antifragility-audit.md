---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Fragility Antifragility Audit

```yaml
# 0. IDENTITY
mode_id: fragility-antifragility-audit
canonical_name: Fragility Antifragility Audit
suffix_rule: analysis
educational_name: fragility / antifragility audit (Taleb convex-response-to-stressor)

# 1. TERRITORY AND POSITION
territory: T7-risk-and-failure-analysis
gradation_position:
  axis: stance
  value: Talebian-asymmetry-focused
  secondary_axis: depth
  secondary_value: thorough
adjacent_modes_in_territory:
  - mode_id: pre-mortem-fragility
    relationship: stance-counterpart (adversarial-future on system; shares concern with structural fragility but uses pre-mortem heuristic rather than convex-response framework)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want to know how this responds to volatility, not just whether it survives normal conditions"
    - "I need to distinguish things that break under stress from things that get stronger"
    - "I'm worried about tail risks and asymmetric exposures"
    - "I want to know whether this is fragile, robust, or antifragile"
    - "I need to find hidden convex or concave exposures"
  prompt_shape_signals:
    - "fragility"
    - "antifragile"
    - "Taleb"
    - "convex response"
    - "concave exposure"
    - "tail risk"
    - "Black Swan"
    - "barbell strategy"
    - "Lindy effect"
    - "asymmetric payoff"
    - "via negativa"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants explicit fragility-robustness-antifragility classification"
    - "user wants to identify convex (gains-from-volatility) and concave (losses-from-volatility) exposures"
    - "user wants tail-risk and asymmetric-payoff analysis"
    - "user wants Talebian heuristics (barbell, via negativa, skin in the game) applied"
  routes_away_when:
    - "user wants general adversarial walk-through of an action plan" → pre-mortem-action (T6)
    - "user wants pre-mortem-style failure imagination on a system without Talebian framework" → pre-mortem-fragility
    - "user wants adversarial-actor red team" → red-team-assessment / red-team-advocate (T15)
    - "user wants formal failure-mode-and-effects (FMEA-style) decomposition" → failure-mode-scan (gap-deferred)
when_not_to_invoke:
  - "User wants forward exploration without failure focus" → T6 modes
  - "User wants to choose among options where risk is one input among several" → T3 modes
  - "User wants causal investigation of a past failure" → T4 modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: adversarial

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [system_or_design_or_strategy, stressor_inventory, current_exposure_profile]
    optional: [historical_stress_events, named_tail_risks, prior_fragility_assessments]
    notes: "Applies when user supplies a defined system or strategy, an enumerated stressor inventory, and a current exposure profile."
  accessible_mode:
    required: [system_or_strategy_description]
    optional: [known_concerns, recent_close_calls]
    notes: "Default. Mode elicits stressor inventory and exposure profile during execution."
  detection:
    expert_signals: ["fragility", "antifragile", "convex", "concave", "tail risk", "Taleb", "barbell", "via negativa"]
    accessible_signals: ["how could this break", "what makes this brittle", "where are the hidden risks", "stress test"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What system, plan, or strategy do you want audited, and what kinds of stress or volatility are you worried about?'"
    on_underspecified: "Ask: 'Are you most worried about how this responds to small frequent shocks, or to rare large shocks (tail events)?'"
output_contract:
  artifact_type: audit
  required_sections:
    - system_or_strategy_locked
    - stressor_inventory
    - convex_exposures_identified
    - concave_exposures_identified
    - fragility_robustness_antifragility_classification
    - tail_risk_assessment
    - asymmetric_payoff_findings
    - via_negativa_recommendations
    - confidence_per_finding
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the analysis classified the system per fragility / robustness / antifragility, or has it collapsed antifragility into mere robustness?"
    failure_mode_if_unmet: antifragility-collapse
  - cq_id: CQ2
    question: "Have concave exposures (where small frequent gains hide rare catastrophic losses) been surfaced explicitly, or has the analysis focused only on visible volatility?"
    failure_mode_if_unmet: hidden-concavity
  - cq_id: CQ3
    question: "Has the analysis distinguished between (a) variance under normal conditions and (b) tail-event response, or has it conflated them?"
    failure_mode_if_unmet: variance-tail-conflation
  - cq_id: CQ4
    question: "Has via negativa been considered (subtraction of fragility-creating elements rather than addition of robustness-creating elements)?"
    failure_mode_if_unmet: addition-bias
  - cq_id: CQ5
    question: "Have the analyst's own Talebian assumptions (markets-are-fat-tailed, expert-prediction-is-poor, optionality-is-undervalued) been held lightly rather than mechanically applied?"
    failure_mode_if_unmet: Talebian-orthodoxy

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: antifragility-collapse
    detection_signal: "Output uses 'robust' and 'antifragile' interchangeably; antifragile system not distinguished from one that merely survives stress."
    correction_protocol: re-dispatch
  - name: hidden-concavity
    detection_signal: "Analysis identifies only visible volatility exposures; no hidden concave exposure (small frequent gains masking rare large losses) surfaced."
    correction_protocol: flag
  - name: variance-tail-conflation
    detection_signal: "Analysis treats high variance and high tail risk as the same property."
    correction_protocol: flag
  - name: addition-bias
    detection_signal: "All recommendations involve adding elements (controls, hedges, redundancy); no subtraction-of-fragility-source recommendations."
    correction_protocol: flag
  - name: Talebian-orthodoxy
    detection_signal: "Conclusions drawn from Talebian aphorisms without case-specific reasoning; barbell-strategy recommended without checking whether barbell suits the actual exposure profile."
    correction_protocol: flag
  - name: false-antifragility
    detection_signal: "System claimed antifragile based on past benefit from volatility, without checking whether the same mechanism applies to the volatility ahead."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - taleb-fragility-antifragility
  optional:
    - knightian-risk-uncertainty-ambiguity (when distinction between risk and deep uncertainty matters)
    - klein-pre-mortem (when adversarial-imagination heuristic complements convex-response framing)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Fragility Antifragility Audit is the heaviest stance-Talebian mode in T7 at thorough tier; molecular escalation deferred."
  sideways:
    target_mode_id: pre-mortem-fragility
    when: "User wants pre-mortem-style failure imagination without Talebian convex-response framework."
  downward:
    target_mode_id: null
    when: "Lighter T7 mode (failure-mode-scan) deferred per CR-6; no current downward sibling."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Fragility Antifragility Audit is the explicitness of (a) the convex/concave exposure classification per element of the system, (b) the distinction between normal-condition variance and tail-event response, and (c) the via-negativa recommendations alongside addition-of-robustness recommendations. A thin pass labels the system fragile or robust intuitively; a substantive pass enumerates stressors by frequency-and-magnitude profile, identifies which elements gain from volatility (convex), which lose disproportionately (concave), classifies the system overall, surfaces hidden concave exposures (small frequent gains masking rare large losses), and recommends both subtraction (via negativa) and addition. Test depth by asking: could a reader identify, from the artifact, which specific element of the system would do most damage if removed and which is doing the most damage by being present?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for stressors outside the analyst's normal frame (regulatory shocks, supply-chain disruption, key-person dependency, reputational tail events, technological obsolescence), surfacing hidden concavities the system's stakeholders have learned not to see (insurance-style payoff structures, tax-loss harvesting profiles, leveraged exposures), and considering Lindy-effect adjustments where applicable (durability of older elements vs. fragility of newer elements). Breadth markers: the analysis names at least one stressor-type the user did not initially mention, and surfaces at least one hidden concavity in the existing exposure profile.

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) fragility/robustness/antifragility classification; (CQ2) hidden concavities; (CQ3) variance vs. tail distinction; (CQ4) via negativa recommendations; (CQ5) Talebian assumptions held lightly. The named failure modes (antifragility-collapse, hidden-concavity, variance-tail-conflation, addition-bias, Talebian-orthodoxy, false-antifragility) are the evaluation checklist. A passing audit classifies the system per the three-way distinction, surfaces hidden concavities, distinguishes normal-condition variance from tail-event response, and recommends both subtraction and addition.

## REVISION GUIDANCE

Revise to disentangle robustness from antifragility where the draft conflates them. Revise to surface hidden concavities where the draft focuses only on visible volatility. Revise to add via negativa recommendations where all recommendations involve addition. Revise to qualify Talebian aphorisms with case-specific reasoning. Resist revising toward reassurance — the mode's analytical character is adversarial-Talebian, and a fragility audit that finds nothing fragile has likely missed hidden concavities. If the user pushes for a clean bill of health, surface the assumptions that would have to hold for that conclusion to be safe.

## CONSOLIDATION GUIDANCE

Consolidate as a structured audit with the nine required sections. The stressor inventory is presented as a table with frequency-and-magnitude estimates. Convex and concave exposures appear in separate sections per element, with magnitude estimates. The fragility/robustness/antifragility classification is stated overall and per major subsystem. Tail risk is assessed with named tail events and exposure magnitudes. Asymmetric payoff findings highlight where small inputs produce disproportionate outputs in either direction. Via negativa recommendations are listed separately from addition-recommendations. Confidence per finding accompanies each major claim.

## VERIFICATION CRITERIA

Verified means: convex and concave exposures are enumerated per element; the system is classified per fragility/robustness/antifragility distinction; hidden concavities are surfaced; normal-condition variance is distinguished from tail-event response; via negativa recommendations appear alongside addition-recommendations; Talebian assumptions are held lightly with case-specific reasoning. The five critical questions are addressable from the output. Confidence per finding accompanies every classification and recommendation.
