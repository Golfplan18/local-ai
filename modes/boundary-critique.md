---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Boundary Critique

```yaml
# 0. IDENTITY
mode_id: boundary-critique
canonical_name: Boundary Critique
suffix_rule: analysis
educational_name: "boundary critique (Ulrich CSH: critical systems heuristics)"

# 1. TERRITORY AND POSITION
territory: T2-interest-and-power
gradation_position:
  axis: stance
  value: critical
adjacent_modes_in_territory:
  - mode_id: cui-bono
    relationship: stance-counterpart (descriptive who-benefits within the artifact's own frame)
  - mode_id: stakeholder-mapping
    relationship: complexity-counterpart (multi-party-descriptive — lives in T8)
  - mode_id: wicked-problems
    relationship: complexity-molecular sibling
  - mode_id: decision-clarity
    relationship: depth-molecular sibling

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I think the framing of this leaves people out"
    - "who isn't being asked"
    - "whose perspective is being treated as natural or inevitable"
    - "the boundary of who counts as a stakeholder feels too narrow"
    - "there's an 'us' implied here that needs surfacing"
  prompt_shape_signals:
    - "boundary critique"
    - "Ulrich"
    - "CSH"
    - "critical systems heuristics"
    - "who is excluded"
    - "boundary judgments"
    - "whose voice is missing"
    - "what's outside the system being analyzed"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants explicit critique of the boundary judgments embedded in a system, decision, or design"
    - "user suspects the framing has naturalized exclusions that should be surfaced and questioned"
    - "user wants to apply Ulrich's twelve boundary categories (sources of motivation, control, knowledge, legitimacy)"
  routes_away_when:
    - "user wants descriptive who-benefits within the artifact's frame" → cui-bono
    - "user wants multi-party stakeholder landscape without critical stance" → stakeholder-mapping
    - "user wants integrated multi-perspective analysis of a wicked problem" → wicked-problems
    - "user wants to negotiate boundary across affected parties" → T13 modes
when_not_to_invoke:
  - "User wants neutral or descriptive analysis without critical-stance framing" → cui-bono or stakeholder-mapping
  - "Boundary in question is technical and uncontested (e.g., a defined system spec)" → T17 process modes
  - "Affected parties are clearly identified and not in dispute" → cui-bono or T13 modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: critical

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [system_or_design_or_decision, named_boundary_in_question]
    optional: [stakeholder_inventory_provisional, ulrich_categories_of_focus, normative_position]
    notes: "Applies when user supplies the system/design/decision, names the boundary at issue, and may identify which of Ulrich's twelve categories are most in play."
  accessible_mode:
    required: [system_or_situation, what_feels_excluded_or_naturalized]
    optional: [why_user_wants_boundary_critique, suspected_voices_left_out]
    notes: "Default. Mode applies Ulrich's twelve categories during execution as the structuring framework."
  detection:
    expert_signals: ["Ulrich", "CSH", "boundary judgments", "critical systems heuristics", "sources of motivation", "sources of control", "sources of knowledge", "sources of legitimacy"]
    accessible_signals: ["who is excluded", "who isn't asked", "the framing leaves out", "what's outside"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the system, decision, or design we're examining, and what about its boundary feels off?'"
    on_underspecified: "Ask: 'Whose voice or interest do you suspect is being treated as outside the scope of this analysis?'"
output_contract:
  artifact_type: audit
  required_sections:
    - system_under_critique
    - boundary_judgments_currently_embedded
    - sources_of_motivation_audit
    - sources_of_control_audit
    - sources_of_knowledge_audit
    - sources_of_legitimacy_audit
    - affected_but_not_involved_parties
    - is_vs_ought_boundary_comparison
    - confidence_per_finding
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have boundary judgments been surfaced as judgments (contestable, made by someone for some purpose), or are they treated as natural givens of the system?"
    failure_mode_if_unmet: boundary-naturalization
  - cq_id: CQ2
    question: "Has the analysis distinguished those involved in the system's design and benefit from those affected by but not involved in the system, per Ulrich's core asymmetry?"
    failure_mode_if_unmet: involved-affected-collapse
  - cq_id: CQ3
    question: "Have all four of Ulrich's category-clusters (motivation, control, knowledge, legitimacy) been audited, or has the analysis selected only the categories that confirm an initial suspicion?"
    failure_mode_if_unmet: selective-categories
  - cq_id: CQ4
    question: "Has the *is* vs. *ought* boundary comparison been performed — i.e., what the boundary currently is vs. what it would be if affected-but-not-involved parties were included — rather than only diagnosing the current boundary?"
    failure_mode_if_unmet: ought-omission

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: boundary-naturalization
    detection_signal: "Boundary judgments described in system-spec language (definitional, technical) rather than as contestable choices made by someone for some purpose."
    correction_protocol: re-dispatch
  - name: involved-affected-collapse
    detection_signal: "Affected-but-not-involved parties section is absent or merged into the involved-stakeholder list."
    correction_protocol: re-dispatch
  - name: selective-categories
    detection_signal: "Only one or two of Ulrich's four category-clusters are audited; others are skipped or noted as 'not applicable' without justification."
    correction_protocol: re-dispatch
  - name: ought-omission
    detection_signal: "Output diagnoses the current boundary without articulating what an inclusive-of-affected-parties boundary would look like."
    correction_protocol: flag
  - name: critique-without-purpose
    detection_signal: "Boundary critique surfaced without articulating what the user could do with the surfaced judgments (no implication for the system, decision, or design)."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - ulrich-csh-boundary-categories
  optional:
    - habermas-discourse-ethics (when legitimacy category is foregrounded)
    - midgley-systemic-intervention (when intervention is in scope)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: wicked-problems
    when: "Boundary critique surfaces a problem with multiple interacting stakeholder conflicts and feedback loops that exceed atomic critique."
  sideways:
    target_mode_id: cui-bono
    when: "On reflection user wanted descriptive who-benefits within the existing frame rather than critical surfacing of the frame's boundary."
  downward:
    target_mode_id: cui-bono
    when: "User wants lighter descriptive read; critical-stance was not the right pitch."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Boundary Critique is the rigor with which Ulrich's twelve boundary categories are applied — four category-clusters (motivation, control, knowledge, legitimacy), each audited along the *is* / *ought* axis, distinguishing those involved from those affected-but-not-involved. A thin pass names some excluded parties; a substantive pass works through the four category-clusters systematically, surfaces who currently provides the source of motivation/control/knowledge/legitimacy and on whose behalf, identifies affected-but-not-involved parties per category, and constructs the *ought* counterpart that would obtain if those parties were included. Test depth by asking: could the critique tell the system's designer which specific boundary judgment, if revised, would change the system's relation to its affected parties?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means surveying the full Ulrich category-cluster space (motivation: client/purpose/measure-of-improvement; control: decision-maker/resources/decision-environment; knowledge: expert/expertise/guarantor; legitimacy: witness/emancipation/worldview) and considering boundary frames from adjacent traditions (Habermasian discourse-ethics, Midgley's systemic intervention, Mackenzie's situated knowledges) where they bear. Breadth markers: all four category-clusters are visited; affected-but-not-involved parties are sought across all four (not only the obvious ones); the worldview category is treated with care because it surfaces the deepest boundary judgments.

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) boundaries surfaced as judgments not naturalized; (CQ2) involved/affected distinction maintained; (CQ3) all four category-clusters audited; (CQ4) is-vs-ought comparison performed. The named failure modes (boundary-naturalization, involved-affected-collapse, selective-categories, ought-omission, critique-without-purpose) are the evaluation checklist. A passing Boundary Critique output names the system, surfaces current boundary judgments per Ulrich's four clusters, identifies affected-but-not-involved parties, and constructs the *ought* counterpart.

## REVISION GUIDANCE

Revise to denaturalize boundary judgments where the draft treated them as system-given. Revise to maintain the involved/affected distinction where the draft collapsed it. Revise to complete the four category-clusters where the draft selected only some. Revise to add the *ought* counterpart where the draft only diagnosed the *is*. Resist revising toward neutrality — the mode's analytical character is critical, and a passing artifact retains the critical edge. If the user wanted neutral analysis, escalate sideways to cui-bono.

## CONSOLIDATION GUIDANCE

Consolidate as a structured audit with the nine required sections. The system under critique is named first. Boundary judgments currently embedded appear as their own section. Each of Ulrich's four category-clusters appears as a numbered audit section (motivation, control, knowledge, legitimacy). Affected-but-not-involved parties appear as their own section, organized by category. The is-vs-ought boundary comparison is the final analytical section before confidence-per-finding. The structured format permits row-level audit of which boundary judgment, in which category, currently obtains and what its inclusive counterpart would be.

## VERIFICATION CRITERIA

Verified means: the system under critique is named; boundary judgments currently embedded are surfaced as judgments (not as system-givens); all four of Ulrich's category-clusters are audited; affected-but-not-involved parties are identified per category; the is-vs-ought boundary comparison is performed; the four critical questions are addressable from the output. Confidence per major finding accompanies each claim.
