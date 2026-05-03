---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
---

# MODE: Paradigm Suspension

```yaml
# 0. IDENTITY
mode_id: paradigm-suspension
canonical_name: Paradigm Suspension
suffix_rule: analysis
educational_name: paradigm suspension and assumption surfacing

# 1. TERRITORY AND POSITION
territory: T9-paradigm-and-assumption-examination
gradation_position:
  axis: stance
  value: suspending
adjacent_modes_in_territory:
  - mode_id: frame-comparison
    relationship: stance counterpart (comparing rather than suspending)
  - mode_id: worldview-cartography
    relationship: depth-molecular sibling (deeper synthesis across paradigms)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "what if X is wrong"
    - "evidence contradicts the accepted explanation"
    - "I want to question the standard view"
    - "why does this consensus exist"
  prompt_shape_signals:
    - "suspend the paradigm"
    - "question the frame"
    - "what if the consensus is wrong"
    - "heterodox exploration"
disambiguation_routing:
  routes_to_this_mode_when:
    - "challenge the foundational assumptions a single consensus depends on"
    - "evaluate evidence without the interpretive overlay of the dominant frame"
  routes_away_when:
    - "compare two or more paradigms side by side" → frame-comparison
    - "build a synthesis across worldviews" → worldview-cartography
    - "challenge a single argument's coherence within its own frame" → coherence-audit (T1)
    - "trace institutional interests behind the position" → cui-bono (T2)
when_not_to_invoke:
  - "User accepts the consensus and wants to work within it" → Project Mode or Constraint Mapping
  - "Question targets a specific claim's truth, not the framework that gives it sense" → Deep Clarification
  - "User wants to push back against observation rather than against authority — Einstein guard rail violation"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: suspending

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [paradigm_or_consensus_position, contesting_evidence_or_alternative]
    optional: [historical_paradigm_revision_analogue, foundational_papers_of_consensus]
    notes: "Applies when user explicitly names the paradigm and supplies the contesting evidence or alternative."
  accessible_mode:
    required: [situation_or_claim_under_question]
    optional: [hint_at_user_unease_or_anomaly]
    notes: "Default. Mode infers the load-bearing consensus and surfaces alternatives."
  detection:
    expert_signals: ["Lakatosian", "Kuhnian", "hard core", "protective belt", "paradigm shift", "anomaly"]
    accessible_signals: ["what if X is wrong", "the standard view", "this can't be the whole story"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the consensus position or accepted explanation you want to question?'"
    on_underspecified: "Ask: 'Are you challenging the evidence behind a position, or the interests pushing it? If interests, route to Cui Bono.'"
output_contract:
  artifact_type: audit
  required_sections:
    - foundational_assumptions
    - evidence_audit_observational_vs_interpretive
    - load_bearing_assessment
    - alternative_interpretations
    - evaluation
  format: prose

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have foundational assumptions been stated as testable propositions, or are they smuggled in as conclusions?"
    failure_mode_if_unmet: assumption-as-conclusion
  - cq_id: CQ2
    question: "Is observational evidence cleanly separated from interpretive evidence, with the same standard applied to consensus and alternatives?"
    failure_mode_if_unmet: asymmetric-evidence-standard
  - cq_id: CQ3
    question: "Is the Einstein guard rail honoured — push back against authority, never against observation?"
    failure_mode_if_unmet: einstein-guard-rail-violation
  - cq_id: CQ4
    question: "Are alternatives genuinely distinct from the consensus and grounded in observational evidence, not strawmen?"
    failure_mode_if_unmet: false-equivalence

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: contrarianism-trap
    detection_signal: "Mode concludes the consensus is wrong without evidential grounding for the rejection."
    correction_protocol: flag
  - name: false-equivalence
    detection_signal: "Fringe alternative treated as equally supported by the same kind of evidence the consensus rests on."
    correction_protocol: flag
  - name: interpretive-evidence-trap
    detection_signal: "Alternative's evidence accepted uncritically while consensus evidence is held to a higher standard (or vice versa)."
    correction_protocol: re-dispatch (apply observational/interpretive distinction symmetrically)
  - name: einstein-guard-rail-violation
    detection_signal: "An observation is dismissed in order to favour a preferred alternative."
    correction_protocol: flag
  - name: assumption-as-conclusion
    detection_signal: "A foundational assumption is stated in conclusion form ('therefore X') rather than testable form ('it is claimed that X')."
    correction_protocol: re-dispatch (rewrite as testable proposition)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - lakatos-hard-core-protective-belt
  optional:
    - kuhn-anomaly-and-paradigm-revision
    - hermeneutic-circle
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: worldview-cartography
    when: "Suspension reveals multiple paradigms in genuine tension that warrant integrative synthesis."
  sideways:
    target_mode_id: frame-comparison
    when: "Suspension surfaces two or more paradigms; user wants comparative reading rather than single-frame suspension."
  downward:
    target_mode_id: null
    when: "Paradigm Suspension is the lightest stance position in T9."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Paradigm Suspension is the degree to which foundational assumptions are surfaced as testable propositions and traced through the framework's logical scaffolding. A thin pass names assumptions; a substantive pass identifies which assumptions are load-bearing (the framework collapses if suspended) versus peripheral (the framework adapts), and tests each assumption against observational rather than interpretive evidence. Test depth by asking: would the analysis predict which observations would falsify each load-bearing assumption?

## BREADTH ANALYSIS GUIDANCE

Breadth in Paradigm Suspension is the catalog of alternative interpretations consistent with the same observational evidence. Widen the lens by generating ≥2 alternatives per load-bearing assumption, looking for structural similarities to historical paradigm revisions (Copernican, plate tectonics, prion theory), and surveying what the domain looks like under each alternative. Breadth markers: alternatives are genuinely distinct (not paraphrases of consensus), each grounded in observation, with at least one historical analogue noted.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing Paradigm Suspension output: states ≥3 foundational assumptions as testable propositions; tags each evidence item as observational or interpretive; assesses load-bearing vs peripheral status; supplies ≥2 genuinely distinct alternatives grounded in observation; honours the Einstein guard rail (observation wins over preferred alternative). Specifically check for the contrarianism trap (rejecting consensus without evidence) and false equivalence (treating fringe positions as equally supported).

## REVISION GUIDANCE

Revise to convert assumptions stated as conclusions into testable propositions. Revise to add load-bearing assessment where missing. Revise to apply observational/interpretive labelling symmetrically. Resist revising toward neutrality if the analysis surfaces a genuinely weakened paradigm — the mode is suspending, not endorsing. Resist revising toward contrarian conclusions if observation supports the consensus — observation wins. Never collapse the suspension into a verdict the evidence does not warrant.

## CONSOLIDATION GUIDANCE

Consolidate as prose in the five required sections (foundational assumptions / evidence audit / load-bearing assessment / alternative interpretations / evaluation). Format: prose only — no diagram. A diagram would freeze the paradigm's structure, contradicting the mode's commitment to holding interpretive frames provisional. If visualisation is essential, transition to Synthesis (for bilateral mapping) or Dialectical Analysis (for adversarial sublation). Each foundational assumption uses the literal prefix "Assumption N (testable):"; each evidence item is tagged "[observational]" or "[interpretive]"; load-bearing assessment uses the literal label "load-bearing:" or "peripheral:".

## VERIFICATION CRITERIA

Verified means: ≥3 foundational assumptions stated as testable propositions (not conclusions); every evidence item carries an observational/interpretive tag; load-bearing assessment present for ≥3 assumptions; ≥2 genuinely distinct alternatives with observational grounding; Einstein guard rail honoured throughout (no observation dismissed to favour an alternative); evaluation states honestly whether the paradigm is supported, weakened, or indeterminate. The four critical questions are addressed in the output.
