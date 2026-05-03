---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Balanced Critique

```yaml
# 0. IDENTITY
mode_id: balanced-critique
canonical_name: Balanced Critique
suffix_rule: analysis
educational_name: balanced critique (neutral stance, multi-perspective)

# 1. TERRITORY AND POSITION
territory: T15-artifact-evaluation-by-stance
gradation_position:
  axis: stance
  value: neutral
adjacent_modes_in_territory:
  - mode_id: steelman-construction
    relationship: stance-counterpart (constructive-strong; lives primarily in T15 with cross-reference to T1)
  - mode_id: benefits-analysis
    relationship: stance-counterpart (constructive-balanced)
  - mode_id: red-team-assessment
    relationship: stance-counterpart (adversarial-actor-modeling, assessment)
  - mode_id: red-team-advocate
    relationship: stance-counterpart (adversarial-actor-modeling, advocate)
  - mode_id: devils-advocate-lite
    relationship: stance-counterpart (adversarial-light; gap-deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "give me a balanced read on this"
    - "I want both sides — strengths and weaknesses, not advocacy"
    - "what holds up and what doesn't"
    - "neutral assessment of this proposal"
    - "I don't want a steelman or a teardown — I want a fair evaluation"
  prompt_shape_signals:
    - "balanced critique"
    - "balanced assessment"
    - "balanced evaluation"
    - "fair evaluation"
    - "strengths and weaknesses"
    - "what holds up"
    - "what doesn't"
    - "neutral read"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants the artifact (plan, proposal, idea) evaluated with neutral stance"
    - "user explicitly rejects advocacy framing in either direction"
    - "user wants strengths AND weaknesses surfaced with comparable rigor"
  routes_away_when:
    - "user wants the strongest possible case for the artifact" → steelman-construction
    - "user wants advantages and minor risks but not adversarial teardown" → benefits-analysis
    - "user wants adversarial-actor stress test for own decision" → red-team-assessment
    - "user wants adversarial argument brief for external use" → red-team-advocate
    - "user wants light contrarian sanity check" → devils-advocate-lite (when built)
when_not_to_invoke:
  - "User wants soundness audit of an argument-as-argument" → T1 modes (Coherence Audit, Frame Audit, Argument Audit)
  - "User wants structural fragility analysis of a system" → pre-mortem-fragility (T7)
  - "User has not provided an artifact to evaluate" → degrade to elicitation

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: neutral

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [artifact, evaluation_criteria, intended_audience_or_purpose]
    optional: [comparable_alternatives, stakeholder_perspectives, prior_evaluations]
    notes: "Applies when user supplies the artifact along with criteria for evaluation."
  accessible_mode:
    required: [artifact_or_proposal]
    optional: [what_user_cares_about_in_evaluation]
    notes: "Default. Mode infers evaluation criteria from the artifact's stated purpose."
  detection:
    expert_signals: ["evaluation criteria", "intended audience", "compare against alternatives", "prior evaluations"]
    accessible_signals: ["balanced read", "fair evaluation", "strengths and weaknesses", "what holds up"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you share the proposal or plan you want evaluated, and what matters to you about it?'"
    on_underspecified: "Ask: 'Roughly what should this proposal accomplish, so I can weigh strengths and weaknesses against that purpose?'"
output_contract:
  artifact_type: synthesis
  required_sections:
    - artifact_summary_one_paragraph
    - strengths_with_evidence
    - weaknesses_with_evidence
    - assumptions_and_uncertainties
    - perspective_dependent_findings
    - net_assessment_with_residual_tensions_named
    - confidence_per_finding
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have strengths and weaknesses been surfaced with comparable rigor, or has one side been treated more thoroughly than the other?"
    failure_mode_if_unmet: stance-tilt
  - cq_id: CQ2
    question: "Have findings that are perspective-dependent (true from one stakeholder vantage, false from another) been flagged as such, rather than asserted as universal?"
    failure_mode_if_unmet: false-universality
  - cq_id: CQ3
    question: "Have residual tensions been named in the net assessment, or has the synthesis collapsed them into a tidy verdict?"
    failure_mode_if_unmet: premature-resolution
  - cq_id: CQ4
    question: "Are claims of strength and weakness backed by specific evidence from the artifact (or absence thereof), rather than asserted by analyst preference?"
    failure_mode_if_unmet: opinion-as-evaluation

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: stance-tilt
    detection_signal: "Strengths and weaknesses sections are asymmetric in length, specificity, or evidence depth; the analysis has slipped into advocacy or critique."
    correction_protocol: re-dispatch
  - name: false-universality
    detection_signal: "Findings that depend on stakeholder perspective are stated as universal; perspective-dependent section is empty or trivial."
    correction_protocol: re-dispatch
  - name: premature-resolution
    detection_signal: "Net assessment delivers a verdict without naming the residual tensions; the strengths and weaknesses are silently overridden by the synthesis."
    correction_protocol: flag
  - name: opinion-as-evaluation
    detection_signal: "Claims of strength or weakness are unbacked by specific evidence; the analysis reads as the analyst's preferences."
    correction_protocol: re-dispatch
  - name: bothsidesism
    detection_signal: "Strengths and weaknesses are forced into balance even when the artifact is genuinely strong (or weak); the mode's neutrality has become artificial symmetry."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - rumelt-strategy-kernel (when artifact is a strategy document)
    - de-bono-pmi (Plus-Minus-Interesting as light scaffolding)
    - ulrich-csh-boundary-categories (when boundary-critique surfaces in the perspective-dependent section)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Balanced Critique is the heaviest neutral-stance mode in T15; deeper evaluation routes sideways to molecular composites in adjacent territories."
  sideways:
    target_mode_id: steelman-construction
    when: "User shifts to wanting the strongest case for the artifact rather than balanced read."
  downward:
    target_mode_id: benefits-analysis
    when: "User wants lighter constructive-balanced read rather than full strengths-and-weaknesses synthesis."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Balanced Critique is the rigor with which strengths and weaknesses are evidenced from the artifact itself rather than from analyst preference. A thin pass produces a list of pros and cons; a substantive pass cites the specific element of the artifact that constitutes each strength or weakness, names the conditions under which the strength would fail to hold or the weakness would not bite, and surfaces assumptions whose alteration would shift the assessment. Test depth by asking: could the user trace each strength/weakness claim back to a specific feature of the artifact?

## BREADTH ANALYSIS GUIDANCE

Widening the lens in Balanced Critique means deliberate scanning across stakeholder perspectives — what looks like a strength from the user's vantage may be a weakness from another's; what looks settled may be contested. The breadth pass surfaces perspective-dependent findings and flags them as such rather than asserting universal evaluations. Adjacent considerations (comparable alternatives, opportunity costs, downstream consequences) are scanned as inputs to the assessment even when they are not the primary focus.

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) symmetric rigor on strengths and weaknesses; (CQ2) perspective-dependent findings flagged; (CQ3) residual tensions named in net assessment; (CQ4) evidence-backed claims rather than analyst opinion. The named failure modes (stance-tilt, false-universality, premature-resolution, opinion-as-evaluation, bothsidesism) are the evaluation checklist. A passing Balanced Critique output presents strengths and weaknesses with comparable evidence depth, flags perspective-dependence, names residual tensions in the synthesis, and grounds claims in the artifact's specifics.

## REVISION GUIDANCE

Revise to restore symmetric rigor where the draft has tilted toward advocacy or teardown. Revise to flag perspective-dependent findings where universal claims have been made. Revise to surface residual tensions where the net assessment has collapsed them. Resist revising toward an artificial 50/50 balance when the artifact is genuinely strong or genuinely weak — the mode's neutrality is in evaluative method, not in forced symmetry of conclusions. Resist revising toward a single-verdict ending; net assessment is allowed to be qualified.

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the seven required sections. The artifact summary opens (one paragraph, neutral). Strengths-with-evidence and weaknesses-with-evidence are emitted as comparable structures (matching depth, matching evidence-citation conventions). Assumptions and uncertainties are listed. Perspective-dependent findings are emitted as their own section with stakeholder vantage labeled. Net assessment closes with residual tensions named. Confidence per finding accompanies each major claim.

## VERIFICATION CRITERIA

Verified means: strengths and weaknesses sections are comparable in length, specificity, and evidence depth; every strength and weakness is tied to a specific element of the artifact; perspective-dependent findings are flagged with stakeholder vantage; residual tensions are named explicitly in the net assessment; the analysis is not artificially balanced when the artifact is genuinely asymmetric in quality; the four critical questions are addressable from the output. Confidence per finding accompanies each major claim.
