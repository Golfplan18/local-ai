---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
no_visual: true
---

# MODE: Steelman Construction

```yaml
# 0. IDENTITY
mode_id: steelman-construction
canonical_name: Steelman Construction
suffix_rule: analysis
educational_name: strongest-case construction (steelman)

# 1. TERRITORY AND POSITION
territory: T15-artifact-evaluation-by-stance
gradation_position:
  axis: stance
  value: constructive-strong
adjacent_modes_in_territory:
  - mode_id: benefits-analysis
    relationship: stance-counterpart (constructive-balanced — Plus/Minus/Interesting)
  - mode_id: balanced-critique
    relationship: stance-counterpart (neutral)
  - mode_id: red-team-assessment
    relationship: stance-counterpart (adversarial-actor-modeling, assessment — direct opposite)
  - mode_id: red-team-advocate
    relationship: stance-counterpart (adversarial-actor-modeling, advocate)
  - mode_id: devils-advocate-lite
    relationship: stance-counterpart (adversarial-light — gap-deferred)
cross_territory_reference:
  - territory: T1-argumentative-artifact-examination
    note: "When the artifact under steelmanning is itself an argument, T1 cross-reference activates. The home territory remains T15; T1 informs lens selection (e.g., argument-coherence considerations) without re-homing the mode."

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "a position is about to be critiqued or dismissed"
    - "I want to understand the opposing argument at its strongest before evaluating"
    - "the debate involves caricature of one side"
    - "I want to give this idea its fairest hearing"
  prompt_shape_signals:
    - "steelman"
    - "best case for"
    - "strongest version of"
    - "what's the best argument for X"
    - "give me the strongest formulation"
disambiguation_routing:
  routes_to_this_mode_when:
    - "you want a single artifact reconstructed at its logical best, then critiqued only at that strength"
    - "the input is one position or proposal you want strengthened"
    - "self-directed epistemic hygiene — strengthen-then-critique workflow"
  routes_away_when:
    - "balanced evaluation across positive, negative, and interesting" → benefits-analysis
    - "neutral examination weighing both sides equally" → balanced-critique
    - "tear it down adversarially for own decision" → red-team-assessment
    - "build the case against for external use" → red-team-advocate
    - "drive thesis through antithesis to synthesis" → dialectical-analysis (T12)
    - "trace whose interests the position serves" → cui-bono (T2)
    - "question the foundational frame the position rests on" → paradigm-suspension (T9)
when_not_to_invoke:
  - "User wants a balanced evaluation, not a constructive-strong stance" → benefits-analysis or balanced-critique
  - "User wants the artifact attacked for own fix-prioritisation" → red-team-assessment
  - "User wants an argument brief against the artifact for external use" → red-team-advocate
  - "User is auditing the argument's soundness as an argument, not building its best version" → T1 (argument-audit / coherence-audit / frame-audit)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: constructive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [position_or_proposal, position_proponents_or_canonical_sources]
    optional: [user_position_for_agreement_mapping, prior_critiques_to_avoid_recapitulating]
    notes: "Applies when user supplies the position with explicit attribution to proponents or canonical formulations."
  accessible_mode:
    required: [position_or_proposal_to_steelman]
    optional: [user_position_or_critique_context]
    notes: "Default. Mode infers proponents and canonical formulations from the position."
  detection:
    expert_signals: ["canonical formulation", "the proponents' best argument", "Rawls argues", "academic literature on"]
    accessible_signals: ["steelman", "best case for", "strongest version", "give it the fairest hearing"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What position or argument do you want me to construct the strongest case for?'"
    on_underspecified: "Ask: 'Could you state the position you want steelmanned, and whether you'd like me to identify points of agreement with your own view?'"
output_contract:
  artifact_type: synthesis
  required_sections:
    - original_position
    - steelmanned_reconstruction
    - strength_identification
    - points_of_agreement
    - critique_of_the_steelman
    - survival_assessment
  format: prose

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Would a thoughtful proponent of this position endorse the reconstruction (mirror test), or would they recognize their argument weakened?"
    failure_mode_if_unmet: tinman-trap
  - cq_id: CQ2
    question: "Is the steelman recognizably the same argument strengthened, or has it drifted into a different argument the analyst prefers?"
    failure_mode_if_unmet: identity-loss
  - cq_id: CQ3
    question: "Does the critique address only the steelmanned version, or does it retreat to the weaker original at any point?"
    failure_mode_if_unmet: retreat-to-original
  - cq_id: CQ4
    question: "Was the steelman built fully before critique began, or were construction and critique entangled?"
    failure_mode_if_unmet: entangled-construction

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: tinman-trap
    detection_signal: "Reconstruction appears strong but is designed to be defeated; mirror test fails (proponent would not endorse)."
    correction_protocol: re-dispatch
  - name: identity-loss
    detection_signal: "Reconstruction has drifted into a different argument; core claim of original position no longer present."
    correction_protocol: re-dispatch
  - name: retreat-to-original
    detection_signal: "Critique paragraph addresses the weaker original formulation at one or more passages."
    correction_protocol: re-dispatch
  - name: steel-strawman
    detection_signal: "Steelman appears generally strong but a specific point is engineered for defeat by the subsequent critique."
    correction_protocol: re-dispatch
  - name: projection-trap
    detection_signal: "Reconstruction filtered through analyst's worldview rather than the proponent's values; charitable inferences favour analyst's frame."
    correction_protocol: flag
  - name: entangled-construction
    detection_signal: "Construction and critique appear interleaved; steelman was not built fully before critique began."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - rapoport-rules-of-engagement
    - dennett-charitable-interpretation
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Steelman Construction is the canonical constructive-strong mode in T15; no heavier sibling along the stance axis."
  sideways:
    target_mode_id: benefits-analysis
    when: "User wants balanced evaluation rather than asymmetric strengthening; switch to constructive-balanced."
  downward:
    target_mode_id: null
    when: "No lighter constructive-strong sibling; if user wants a quick endorsement rather than a strengthened reconstruction, route out of T15 entirely."
```

## DEPTH ANALYSIS GUIDANCE

Going deeper in Steelman Construction means reconstructing the position at its logical best — surfacing hidden premises that would make the argument stronger, filling logical gaps with the most charitable inferences, and marshalling the best available evidence. Depth shows itself in the mirror test: would a thoughtful proponent say "I wish I'd thought of putting it that way"? A thin pass paraphrases; a substantive pass formulates more precisely than proponents have, identifies the strongest premises, and marshalls evidence that would be most difficult for a critic to dismiss. Construction completes fully before critique begins — entangled construction-and-critique is a structural failure mode.

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for the proponent's full philosophical or strategic context, not just the immediate claim. Identify hidden premises, fill gaps, and look for the strongest available support across the position's intellectual lineage. Identify at least two points of agreement between the steelmanned position and the user's own — these are not concessions but genuine common ground that often opens unexpected analytical leverage. Identify what is genuinely valuable in the position, separate from its rhetorical packaging. Breadth markers: hidden premises are explicitly surfaced, points of agreement are numbered and grounded in the user's stated view, and the steelman's intellectual lineage is acknowledged.

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) mirror test pass; (CQ2) identity preservation; (CQ3) critique-targets-steelman-only; (CQ4) construction-before-critique. The named failure modes (tinman-trap, identity-loss, retreat-to-original, steel-strawman, projection-trap, entangled-construction) are the evaluation checklist. A passing Steelman output has all six required sections, the steelmanned reconstruction is recognizably the same argument strengthened, at least two points of agreement are explicit, the critique addresses only the strongest version, and the survival assessment names what remains compelling after critique. Mode is prose-only — any visual emission is an evaluation failure.

## REVISION GUIDANCE

Revise to strengthen the reconstruction wherever a thoughtful proponent would recognize weakness — apply the mirror test until it passes. Revise to re-anchor to the original claim wherever the steelman has drifted into a different argument. Revise to rewrite critique passages that retreat to the weaker original; if a critique doesn't apply to the steelmanned version, drop it rather than weakening the steelman to make the critique fit. Revise to rebuild from the proponent's values where the reconstruction has filtered through the analyst's worldview. Resist revising toward "balanced" presentation — the mode is asymmetric by design; the constructive-strong stance is the deliverable. If multiple positions need steelmanning, apply identical rigor to each (symmetry guard rail).

## CONSOLIDATION GUIDANCE

Consolidate as prose with the six required sections in order: original position (faithful re-expression including weaknesses), steelmanned reconstruction (the strongest possible version), strength identification (most defensible premises, hardest-to-dismiss evidence), points of agreement (≥2 explicit), critique of the steelman (addressing only the strongest version), survival assessment (what remains compelling after critique). The original-position paragraph stays bounded (≤ ⅓ of total steelman section length) so construction dominates rather than repetition of the weak formulation. Mode is prose-only — no envelope, no diagram, no visual summary; if user requests visual rendering, propose dialectical-analysis (which emits IBIS) as transition.

## VERIFICATION CRITERIA

Verified means: all six required sections present in order or clearly demarcated; original-position paragraph bounded (≤ ⅓ of steelman section length); mirror test passes (a thoughtful proponent would endorse the reconstruction); steelman is recognizably the same argument strengthened (not replaced); at least two points of agreement explicit; critique addresses only the steelmanned version with no retreat to the original; survival assessment present; no visual envelope emitted. The four critical questions are addressable from the output.
