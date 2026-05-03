---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Causal DAG

```yaml
# 0. IDENTITY
mode_id: causal-dag
canonical_name: Causal DAG
suffix_rule: analysis
educational_name: causal directed acyclic graph analysis (Pearl do-calculus)

# 1. TERRITORY AND POSITION
territory: T4-causal-investigation
gradation_position:
  axis: depth
  value: thorough
  secondary_axis: specificity
  secondary_value: formalism-explicit
adjacent_modes_in_territory:
  - mode_id: root-cause-analysis
    relationship: complexity-lighter sibling (single cause-chain, no formal graph)
  - mode_id: systems-dynamics-causal
    relationship: complexity-counterpart (feedback structure, cyclic — DAG is acyclic by definition)
  - mode_id: process-tracing
    relationship: specificity-counterpart (historical-event-specific, evidence-test-driven)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want to know what would happen if we intervened"
    - "I need to separate correlation from causation"
    - "we have observational data and need to reason about counterfactuals"
    - "I want to identify confounders before drawing a causal conclusion"
  prompt_shape_signals:
    - "causal graph"
    - "DAG"
    - "do-calculus"
    - "Pearl"
    - "confounder"
    - "back-door"
    - "front-door"
    - "intervention vs observation"
    - "counterfactual"
    - "what would happen if we did X"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants explicit graphical representation of causal structure"
    - "user wants to distinguish observation, intervention, and counterfactual reasoning"
    - "user wants to identify confounders, mediators, and colliders before estimating effects"
    - "user wants formal reasoning about identifiability of a causal effect"
  routes_away_when:
    - "single cause-chain on a defined symptom (no graph needed)" → root-cause-analysis
    - "system has feedback loops that violate acyclicity" → systems-dynamics-causal
    - "specific historical event where evidence-tests on competing causal hypotheses are central" → process-tracing
    - "evaluating multiple competing hypotheses against evidence (Bayesian)" → competing-hypotheses (T5)
when_not_to_invoke:
  - "User wants to map how a system works rather than why an outcome occurred" → T17
  - "User wants to explain how parts produce the whole's behavior" → T16
  - "Frame itself may be generating the problem" → T9 paradigm modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [outcome_or_effect_of_interest, candidate_causal_variables, intervention_question]
    optional: [observational_data_summary, prior_dag_sketch, identifiability_concern, suspected_confounders]
    notes: "Applies when user supplies a structured causal question, named variables, and an explicit intervention or counterfactual query."
  accessible_mode:
    required: [causal_question]
    optional: [context_about_variables, why_user_wants_causal_read]
    notes: "Default. Mode elicits variables, intervention question, and known confounders during execution."
  detection:
    expert_signals: ["DAG", "do-calculus", "back-door", "front-door", "confounder", "instrumental variable", "Pearl"]
    accessible_signals: ["what would happen if", "is X causing Y", "correlation vs causation", "intervention"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What outcome are you trying to explain or change, and what are the candidate causes you have in mind?'"
    on_underspecified: "Ask: 'Are you asking what would happen if you intervened on X (do-operator), or asking what caused the observed Y (counterfactual)?'"
output_contract:
  artifact_type: mapping
  required_sections:
    - causal_question_locked
    - variable_inventory_with_roles
    - dag_specification
    - confounder_mediator_collider_classification
    - identifiability_verdict
    - intervention_or_counterfactual_answer
    - assumption_inventory
    - confidence_per_finding
  format: diagram-friendly

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the causal question been locked at a specific rung of Pearl's ladder (observation, intervention, or counterfactual), and is the analysis using the operators appropriate to that rung?"
    failure_mode_if_unmet: rung-confusion
  - cq_id: CQ2
    question: "Have all plausible confounders been named and either included in the DAG or explicitly assumed away with justification?"
    failure_mode_if_unmet: hidden-confounder
  - cq_id: CQ3
    question: "Has the back-door (or front-door) criterion been checked, and is the causal effect identifiable from the assumed graph?"
    failure_mode_if_unmet: non-identifiability-elision
  - cq_id: CQ4
    question: "Have collider variables been correctly classified, with the analysis avoiding conditioning on them (which would induce spurious dependence)?"
    failure_mode_if_unmet: collider-conditioning
  - cq_id: CQ5
    question: "Are the structural assumptions encoded in the DAG (which arrows present, which absent) made explicit, with the most fragile assumptions flagged?"
    failure_mode_if_unmet: implicit-assumption

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: rung-confusion
    detection_signal: "Analysis uses observational language ('we observe X correlated with Y') to answer an interventional question ('what if we did X')."
    correction_protocol: re-dispatch
  - name: hidden-confounder
    detection_signal: "DAG omits a plausible common cause without an explicit no-confounding assumption."
    correction_protocol: flag
  - name: non-identifiability-elision
    detection_signal: "Final causal claim made without checking back-door or front-door criterion."
    correction_protocol: re-dispatch
  - name: collider-conditioning
    detection_signal: "Analysis conditions on a variable that is a common effect of two other variables in the graph (collider), inducing spurious association."
    correction_protocol: re-dispatch
  - name: implicit-assumption
    detection_signal: "DAG presented without enumerating which arrows were excluded and why (no-direct-effect assumptions invisible)."
    correction_protocol: flag
  - name: cycle-violation
    detection_signal: "Causal structure exhibits feedback (X → Y → X) — DAG cannot represent this; mode boundary violation."
    correction_protocol: escalate

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - pearl-causal-graphs
    - pearl-do-calculus
  optional:
    - bennett-checkel-process-tracing-tests (when historical-event-specific evidence-tests are also relevant)
    - knightian-risk-uncertainty-ambiguity (when assumption fragility crosses into deep uncertainty)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Causal DAG is the most formal mode in T4's depth axis at thorough tier; molecular escalation deferred."
  sideways:
    target_mode_id: systems-dynamics-causal
    when: "Causal structure exhibits feedback loops that violate acyclicity; switch to feedback-structure analysis."
  downward:
    target_mode_id: root-cause-analysis
    when: "Single cause-chain suffices; formal graph adds overhead without analytical gain."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Causal DAG analysis is the explicitness of (a) Pearl-ladder rung selection — observation, intervention, or counterfactual — and (b) graphical representation of the assumed causal structure with all variables classified by role. A thin pass produces a sketch and an intuitive causal claim; a substantive pass locks the question at a rung, enumerates variables, classifies each as cause / effect / confounder / mediator / collider / instrument, draws the DAG with explicit absent-arrow assumptions, applies the back-door (or front-door) criterion to check identifiability, and answers the intervention or counterfactual query in the language proper to its rung. Test depth by asking: could a reader reproduce the identifiability verdict from the artifact, including which arrows were assumed absent and why?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for plausible confounders the analyst might miss (selection effects, reverse causation candidates, time-varying confounders, latent variables), considering alternative DAG structures consistent with the same observations, and surfacing the identifiability boundary — under which assumption violations would the conclusion fail. Breadth markers: the analysis names at least one alternative DAG that observational data could not distinguish from the chosen one, and notes which intervention or natural experiment would discriminate.

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) rung specification; (CQ2) confounder enumeration; (CQ3) identifiability verdict; (CQ4) collider handling; (CQ5) assumption explicitness. The named failure modes (rung-confusion, hidden-confounder, non-identifiability-elision, collider-conditioning, implicit-assumption, cycle-violation) are the evaluation checklist. A passing Causal DAG output locks the question at a Pearl rung, presents the DAG with all variables classified, applies the appropriate identifiability criterion, answers the intervention or counterfactual query, and surfaces the most fragile structural assumptions.

## REVISION GUIDANCE

Revise to add omitted confounders where the draft assumes no-confounding without justification. Revise to make absent-arrow assumptions explicit where the DAG presents a structure without saying what was excluded. Revise to demote a causal claim to an associational claim when identifiability fails. Resist revising toward stronger conclusions than the graph supports — the mode's analytical character is rigorous identifiability discipline, not maximal causal commitment. If the user pushes for an interventional answer that the graph cannot identify, surface the assumption that would be required to answer it rather than answering it anyway.

## CONSOLIDATION GUIDANCE

Consolidate as a diagram-friendly mapping with the eight required sections. The DAG specification appears as a node-and-arrow listing (suitable for rendering) plus an explicit absent-arrow inventory. Variables are classified per role in a structured table. The identifiability verdict appears as a yes/no with the criterion applied (back-door, front-door, do-calculus rule). The intervention or counterfactual answer is stated in the language of its rung. The assumption inventory orders assumptions by fragility (most fragile first). Confidence per finding accompanies each major claim.

## VERIFICATION CRITERIA

Verified means: the causal question is locked at a Pearl rung; all variables are classified by role; the DAG is specified with absent-arrow assumptions enumerated; the back-door or front-door criterion has been applied with verdict stated; collider variables are correctly handled; the intervention or counterfactual answer matches the rung; the assumption inventory is ordered by fragility. The five critical questions are addressable from the output. Confidence per finding accompanies every causal claim.

## CAVEATS AND OPEN DEBATES

**Debate D4 — Are Pearl's ladder levels 2 (intervention) and 3 (counterfactual) genuinely distinct rungs, or is intervention a special case of counterfactual reasoning?** Pearl (2009, *Causality*; 2018, *Book of Why*) argues for a strict three-rung hierarchy: observation (seeing), intervention (doing, via the do-operator), and counterfactuals (imagining what would have been). Each rung requires strictly more structural commitment than the one below; effects identifiable at level 3 are not generally identifiable from level 2 information alone. Maudlin and other philosophers of causation have argued the distinction is blurrier — interventions are themselves a kind of counterfactual ("what if we set X to x"), and the three-rung architecture is more pedagogical than ontological. The Pearl-Maudlin exchange surfaces this debate without resolving it. This mode operates with Pearl's strict hierarchy as the operational stance: critical question CQ1 requires explicit rung selection, and the intervention-or-counterfactual-answer section is rung-tagged. The debate is surfaced for users whose causal question sits at the level-2/level-3 boundary and who want to know whether the distinction matters for their application. Citations: Pearl 2009 *Causality*; Pearl 2018 *Book of Why*; Maudlin and related counterfactual-theoretic critiques.
