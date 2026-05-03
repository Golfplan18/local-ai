---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Multi-Criteria Decision

```yaml
# 0. IDENTITY
mode_id: multi-criteria-decision
canonical_name: Multi-Criteria Decision
suffix_rule: analysis
educational_name: "multi-criteria decision analysis (MCDM: AHP, SMART, ELECTRE, etc.)"

# 1. TERRITORY AND POSITION
territory: T3-decision-making-under-uncertainty
gradation_position:
  axis: complexity
  value: multi-criteria
adjacent_modes_in_territory:
  - mode_id: constraint-mapping
    relationship: depth-lighter sibling (environment-known)
  - mode_id: decision-under-uncertainty
    relationship: depth-thorough sibling (probability-and-time-weighted single-criterion)
  - mode_id: decision-architecture
    relationship: depth-molecular sibling (built Wave 4)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I'm choosing among options and they trade off across multiple things I care about"
    - "no single criterion can settle this"
    - "I want to see how the options stack up across all the dimensions"
    - "weighting matters here and I want to make my weights explicit"
  prompt_shape_signals:
    - "multi-criteria"
    - "MCDA"
    - "MCDM"
    - "weighted criteria"
    - "AHP"
    - "SMART analysis"
    - "criteria matrix"
    - "rank options across"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user has named (or implies) ≥3 criteria that matter to the decision"
    - "user wants explicit weights and a structured cross-criterion comparison"
    - "options are discrete and enumerable; criteria can be operationalized into scores"
  routes_away_when:
    - "decision turns on probability and time-weighting under a single dominant criterion" → decision-under-uncertainty
    - "decision is about mapping environmental constraints rather than choosing among options" → constraint-mapping
    - "decision requires molecular orchestration across stakeholders, scenarios, and criteria" → decision-architecture
when_not_to_invoke:
  - "Decision has only one or two criteria — overhead of MCDM exceeds value" → decision-under-uncertainty or constraint-mapping
  - "User is exploring the future or projecting consequences rather than choosing" → T6 modes
  - "Decision is among parties whose conflict is the analytical object" → T8 stakeholder-mapping or T13 modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [option_set, criteria_list, weighting_preferences]
    optional: [scoring_data, mcdm_method_preference, sensitivity_threshold, tradeoff_tolerances]
    notes: "Applies when user supplies enumerated options, named criteria, and at least preliminary weights."
  accessible_mode:
    required: [decision_description, options_being_considered]
    optional: [what_matters_most, dealbreakers]
    notes: "Default. Mode elicits criteria and weights during execution; criteria surfaced from 'what matters' phrasing."
  detection:
    expert_signals: ["criteria are", "weights are", "AHP", "SMART", "ELECTRE", "TOPSIS", "pairwise comparison"]
    accessible_signals: ["choosing between", "weighing", "tradeoff", "what matters most", "stack up"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What are the options you're choosing among, and what dimensions matter to the choice?'"
    on_underspecified: "Ask: 'Of those criteria, which carry more weight for you, and roughly by how much?'"
output_contract:
  artifact_type: ranked_options
  required_sections:
    - options_inventory
    - criteria_definitions
    - weights_with_rationale
    - scoring_matrix
    - aggregated_ranking
    - sensitivity_analysis
    - dominant_and_dominated_options
    - confidence_per_finding
  format: matrix

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the criteria genuinely independent of one another, or do they double-count by measuring the same underlying attribute under different names?"
    failure_mode_if_unmet: criterion-redundancy
  - cq_id: CQ2
    question: "Are the weights elicited from the decision-maker's actual preferences, or imposed by the analyst's choice of MCDM method without preference elicitation?"
    failure_mode_if_unmet: weight-imposition
  - cq_id: CQ3
    question: "Has sensitivity analysis surfaced how robust the ranking is to weight perturbations and scoring uncertainty, or is the top-ranked option presented as if the ranking were stable?"
    failure_mode_if_unmet: false-stability
  - cq_id: CQ4
    question: "Have dominated options (those beaten by another option on every criterion) been identified and pruned, and have dominant options (beating others on every criterion) been flagged as no-brainer choices?"
    failure_mode_if_unmet: dominance-blindness

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: criterion-redundancy
    detection_signal: "Two or more criteria score highly correlated across options without explicit acknowledgment that they capture related aspects."
    correction_protocol: flag
  - name: weight-imposition
    detection_signal: "Weights stated without rationale or elicitation history; equal weights used as a 'neutral' default without surfacing that equal weighting is itself a preference choice."
    correction_protocol: re-dispatch
  - name: false-stability
    detection_signal: "Sensitivity analysis section is empty, or perturbation tested only one weight at a time when joint perturbation would change the ranking."
    correction_protocol: re-dispatch
  - name: dominance-blindness
    detection_signal: "Output presents a full ranking when dominance relations would have pruned the option set or made the top choice obvious."
    correction_protocol: flag
  - name: aggregation-method-opacity
    detection_signal: "Aggregation method (additive, multiplicative, ELECTRE-style outranking, etc.) not named, or named without explanation of why this method fits the decision shape."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - mcdm-methods
  optional:
    - kahneman-tversky-bias-catalog (when weight elicitation is anchored or framed)
    - rumelt-strategy-kernel (when criteria are strategic and the choice is strategy-shaped)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: decision-architecture
    when: "Decision involves multiple stakeholders with diverging weights, requires scenario integration, or carries sequential-decision structure (real options)."
  sideways:
    target_mode_id: decision-under-uncertainty
    when: "On reflection a single criterion dominates; multi-criteria framing was overhead."
  downward:
    target_mode_id: constraint-mapping
    when: "Choice resolves once constraints are mapped; no genuine multi-criteria tradeoff remains."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Multi-Criteria Decision is the explicitness of method choice, weight elicitation, and sensitivity testing. A thin pass produces a weighted-sum ranking with implicit method assumptions; a substantive pass names the MCDM method (additive SMART, AHP pairwise, ELECTRE outranking, TOPSIS distance-from-ideal, etc.), explains why it fits the decision shape, surfaces weights with elicited rationale, identifies dominance relations to prune the option set, runs sensitivity analysis on both weights and scores, and flags where the ranking is robust vs. fragile. Test depth by asking: could the analysis tell the decision-maker which weight or score perturbation would flip the top choice?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means surveying the criteria space for under-named dimensions (the criterion the decision-maker would notice they cared about only if it were missing), scanning for criterion redundancy (two criteria measuring the same underlying attribute), and considering whether the option set itself is complete (would option-set expansion change the analysis?). Breadth markers: criteria are surveyed across at least three categories (e.g., outcome-quality, cost, risk, fit, reversibility); option set is sanity-checked for completeness before scoring.

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) criterion independence; (CQ2) weight elicitation rather than imposition; (CQ3) sensitivity analysis surfacing robustness; (CQ4) dominance pruning. The named failure modes (criterion-redundancy, weight-imposition, false-stability, dominance-blindness, aggregation-method-opacity) are the evaluation checklist. A passing MCDM output names method with rationale, surfaces weights with elicitation, scores explicitly, runs sensitivity analysis, and flags dominance relations.

## REVISION GUIDANCE

Revise to add weight rationale where the draft presents weights without elicitation. Revise to add sensitivity analysis where the draft presents the ranking as stable. Revise to prune dominated options and flag dominant ones rather than presenting a flat ranking. Resist revising toward false consensus — if criteria genuinely conflict, the artifact's job is to surface the tradeoff, not to manufacture a clear winner. If the ranking is method-fragile (small perturbations flip the top choice), say so explicitly.

## CONSOLIDATION GUIDANCE

Consolidate as a matrix artifact with the eight required sections. The scoring matrix is the central artifact: rows are options, columns are criteria, cells are scores. Weights appear as a row beneath the criteria. Aggregated ranking appears with method-name. Sensitivity analysis is a separate section showing how the ranking shifts under weight or score perturbation. Dominated options are flagged or struck through. Confidence-per-finding distinguishes scoring uncertainty from weight uncertainty from method-fit uncertainty.

## VERIFICATION CRITERIA

Verified means: criteria are named and defined operationally; weights are elicited or explicitly noted as analyst-imposed (with reason); aggregation method is named and explained; scoring is explicit per option per criterion; sensitivity analysis runs at least one joint weight-score perturbation; dominance relations are surfaced; the four critical questions are addressable from the output. Confidence accompanies each major finding.
