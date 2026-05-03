---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Third Side

```yaml
# 0. IDENTITY
mode_id: third-side
canonical_name: Third Side
suffix_rule: analysis
educational_name: third-side mediation (Ury ten roles)

# 1. TERRITORY AND POSITION
territory: T13-negotiation-and-conflict-resolution
gradation_position:
  axis: stance
  value: mediator
  complexity_axis_value: multi-party
adjacent_modes_in_territory:
  - mode_id: interest-mapping
    relationship: stance-counterpart (party-stance, two-party-default, depth-light; built Wave 2)
  - mode_id: principled-negotiation
    relationship: stance-counterpart (party-stance, two-party-default, depth-thorough; Wave 3)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "the conflict has more than two parties and a single mediator-perspective is needed"
    - "I'm acting as a third party (mediator, facilitator, ombuds, community member) and need a frame for the role"
    - "I'm advising someone who is mediating a conflict"
    - "the surrounding community / network has a role in containing or resolving this conflict"
    - "want to map the third-side roles available in this situation"
    - "want a Ury third-side reading rather than a party-side reading"
  prompt_shape_signals:
    - "third side"
    - "third-side"
    - "Ury third side"
    - "mediation"
    - "mediator perspective"
    - "facilitating a conflict"
    - "containing a conflict"
    - "ombuds"
    - "the community's role"
    - "ten roles"
    - "provider equalizer healer witness referee peacekeeper bridge-builder mediator arbiter teacher"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user is in (or advising) a mediator / facilitator / ombuds / third-party role"
    - "conflict has multiple parties (more than two), a community/network surrounding the parties, or both"
    - "user wants to map which Ury third-side roles are needed and who could fill them"
    - "user wants a containment / prevention / resolution analysis from the surrounding community's vantage"
  routes_away_when:
    - "user is a party to the conflict and wants party-side negotiation guidance" → principled-negotiation (or interest-mapping for lighter)
    - "user wants only quick interest-mapping" → interest-mapping
    - "user wants descriptive multi-party stakeholder mapping without active conflict-resolution framing" → stakeholder-mapping (T8)
    - "user wants strategic-game analysis of multi-party interaction (equilibria, coalitions)" → strategic-interaction (T18)
    - "user wants policy / boundary-critique analysis (whose voices are excluded)" → boundary-critique (T2)
when_not_to_invoke:
  - "User is a direct party with their own interests at stake" → principled-negotiation or interest-mapping
  - "Conflict is straightforwardly two-party with no community/network role" → principled-negotiation or interest-mapping
  - "User wants stakeholder mapping without conflict-resolution framing" → stakeholder-mapping (T8)
  - "User wants game-theoretic equilibrium analysis" → strategic-interaction (T18)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: neutral

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [parties, conflict_description, surrounding_community_or_network, user_third_party_role_or_advisory_relationship]
    optional: [conflict_history, prior_mediation_attempts, escalation_signals, community_resources_or_norms_relevant, cultural_context, time_pressure]
    notes: "Applies when user supplies named parties, identifies their third-party role (or who they are advising), and describes the surrounding community/network."
  accessible_mode:
    required: [conflict_description, user_role_in_situation]
    optional: [who_else_is_around_the_conflict, what_has_been_tried, what_is_escalating]
    notes: "Default. Mode infers parties, third-party roles available, and surrounding community from the description."
  detection:
    expert_signals: ["third side", "Ury", "mediator", "facilitator", "ombuds", "ten roles", "provider equalizer healer witness referee peacekeeper bridge-builder mediator arbiter teacher"]
    accessible_signals: ["mediating a conflict", "the community needs to step in", "I'm not a party but I'm involved", "facilitating between"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Who are the parties to the conflict, what is the conflict, and what is your role — are you mediating, facilitating, advising someone who is, or part of the surrounding community?'"
    on_underspecified: "Ask: 'Who else is around this conflict — colleagues, friends, neighbors, leaders, professionals — who could play a third-side role?'"
output_contract:
  artifact_type: mapping
  required_sections:
    - parties_and_conflict_summary
    - surrounding_community_or_network
    - prevention_roles_active_or_needed
    - resolution_roles_active_or_needed
    - containment_roles_active_or_needed
    - role_assignment_candidates
    - escalation_signals_to_watch
    - candidate_third_side_interventions
    - flagged_unknowns_to_test
    - confidence_per_finding
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the analysis maintained a third-side stance — analyzing what the surrounding community can do — rather than slipping into party-side advocacy for one party's interests?"
    failure_mode_if_unmet: party-stance-creep
  - cq_id: CQ2
    question: "Have the ten Ury roles been considered as a checklist (provider, teacher, bridge-builder, mediator, arbiter, equalizer, healer, witness, referee, peacekeeper) rather than collapsing into a generic mediator role?"
    failure_mode_if_unmet: ten-role-collapse
  - cq_id: CQ3
    question: "Have the three role-clusters (prevention, resolution, containment) all been considered, rather than defaulting to resolution roles only?"
    failure_mode_if_unmet: prevention-or-containment-omission
  - cq_id: CQ4
    question: "Have role assignments been linked to actual people / institutions / norms in the surrounding community, rather than asserting roles in the abstract?"
    failure_mode_if_unmet: roles-without-bearers
  - cq_id: CQ5
    question: "Have the limits of third-side intervention been acknowledged — situations where the parties' agency is primary, where third-side intervention would be intrusive, or where power asymmetry makes neutral mediation untenable — rather than asserting the third side as universally appropriate?"
    failure_mode_if_unmet: third-side-overreach

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: party-stance-creep
    detection_signal: "Analysis recommends moves that favor one party's interests rather than analyzing what the surrounding community can do for the conflict as a whole; output reads as advocacy."
    correction_protocol: re-dispatch
  - name: ten-role-collapse
    detection_signal: "Output names only mediator (or only one or two of the ten roles); the full ten-role checklist is not surveyed."
    correction_protocol: re-dispatch
  - name: prevention-or-containment-omission
    detection_signal: "Output addresses only resolution roles (mediator / arbiter / equalizer); prevention (provider / teacher / bridge-builder) and/or containment (witness / referee / peacekeeper) clusters are not addressed."
    correction_protocol: re-dispatch
  - name: roles-without-bearers
    detection_signal: "Roles are listed without naming actual people / institutions / norms in the surrounding community who could fill them."
    correction_protocol: re-dispatch
  - name: third-side-overreach
    detection_signal: "Analysis asserts third-side intervention as appropriate without considering the limits — power asymmetry that makes mediation paper over coercion, parties' own agency that makes intervention intrusive, situations where the conflict's resolution requires confrontation rather than mediation."
    correction_protocol: flag
  - name: cultural-context-flatness
    detection_signal: "Third-side roles applied without consideration of how the surrounding community's cultural norms, hierarchies, and existing institutions shape which roles are available and who can credibly fill them."
    correction_protocol: flag
  - name: parties-as-passive
    detection_signal: "Output frames parties as objects of third-side intervention rather than as agents whose own moves matter; third-side roles are positioned as solving the conflict rather than as supporting the parties to do so."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - ury-third-side
  optional:
    - fisher-ury-principled-negotiation (when third-side role includes coaching parties on principled-negotiation method)
    - lederach-conflict-transformation (when conflict is deep, identity-based, or community-rooted)
    - kriesberg-constructive-conflicts (when conflict has historical depth and trajectory analysis matters)
    - voss-tactical-empathy (when third-side role includes coaching one party in adversarial-context dynamics)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Third Side is the deepest mediator-stance multi-party mode in T13; further depth comes from iteration with new community-mapping information."
  sideways:
    target_mode_id: principled-negotiation
    when: "On reflection the user is actually a party (or the analysis would better serve as party-side guidance for a primary stakeholder) rather than a third-party role."
  downward:
    target_mode_id: interest-mapping
    when: "User wants only the position-to-interest descent on the parties, without the full third-side role survey."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Third Side is the rigor with which the ten Ury roles are surveyed across the three role-clusters, with each role linked to actual bearers in the surrounding community. A thin pass names "mediator" generically; a substantive pass: (1) maps the surrounding community/network — colleagues, friends, family, neighbors, leaders, professionals, institutions, norms — that constitute the third side as a social fact; (2) surveys the ten roles in their three clusters: **prevention** (provider — addresses frustrated needs that drive conflict; teacher — gives skills for conflict-handling; bridge-builder — develops relationships that pre-empt conflict), **resolution** (mediator — facilitates communication; arbiter — judges when self-resolution fails; equalizer — democratizes power asymmetry; healer — addresses injured emotions and broken relationships), **containment** (witness — pays attention so escalation has consequences; referee — establishes rules for fair fight; peacekeeper — interposes when violence threatens); (3) identifies which roles are *active* (already being filled, well or poorly), which are *needed but unfilled*, and which are *not yet relevant but may become so*; (4) names candidate bearers per role from the surrounding community; (5) recommends specific third-side interventions keyed to role gaps; (6) acknowledges the limits — power asymmetry that makes mediation cover for coercion, parties' agency that makes intervention intrusive, situations requiring confrontation rather than mediation. Test depth by asking: could the analysis tell the user which one or two role gaps, if filled, would change the conflict's trajectory most?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning the surrounding community in three rings (intimate — family / close colleagues; mid — extended network / institutional context; outer — wider community / public / norms); surveying all three role-clusters (prevention / resolution / containment) before narrowing; considering escalation signals (rhetoric hardening, third-party recruitment to one side, breakdown of channels of communication, emergence of public symbolic markers, threats of exit or violence); and considering parallel third-side traditions (Lederach's conflict-transformation lineage on identity-rooted conflict; Kriesberg's constructive-conflicts trajectory analysis; restorative justice; indigenous and traditional dispute-resolution practices that may already exist in the community). Breadth markers: all ten Ury roles considered (even if most are not active); all three role-clusters considered; the surrounding community mapped in at least two rings; escalation signals listed; the limits of third-side intervention acknowledged.

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) third-side stance maintained, not party-stance creep; (CQ2) ten-role checklist surveyed; (CQ3) all three role-clusters (prevention / resolution / containment) considered; (CQ4) roles linked to bearers; (CQ5) limits acknowledged. The named failure modes are the evaluation checklist. A passing Third Side output names parties and conflict, maps surrounding community, surveys the ten roles across three clusters, names role-assignment candidates, surfaces escalation signals, recommends specific interventions keyed to role gaps, flags unknowns testable in practice, and acknowledges intervention limits.

## REVISION GUIDANCE

Revise to restore third-side stance where the draft slipped into party advocacy. Revise to expand the role survey where the draft collapsed to mediator-only. Revise to address prevention and containment where the draft addressed only resolution. Revise to name bearers where the draft asserted roles in the abstract. Revise to acknowledge limits where the draft asserted third-side as universally appropriate. Revise to honor parties' agency where the draft positioned them as passive objects of intervention. Resist revising toward generic mediator-talk — the mode's analytical character is the *ten-role-and-three-cluster* frame, not generic mediation; collapsing back to "mediator" is a failure mode, not a polish. Resist revising toward over-confident community capacity assertions — sometimes the surrounding community lacks the third side the conflict needs, and naming that is part of honest analysis.

## CONSOLIDATION GUIDANCE

Consolidate as a structured mapping with the ten required sections. Parties and conflict summary appear first. Surrounding community/network is mapped before role assignment (the third side is a *social fact* that may or may not contain the roles needed). Prevention / resolution / containment role-clusters appear as separate sections, each with the relevant Ury roles (prevention: provider, teacher, bridge-builder; resolution: mediator, arbiter, equalizer, healer; containment: witness, referee, peacekeeper) and which are active / needed / not-yet-relevant. Role-assignment candidates link each role to actual people / institutions / norms in the surrounding community. Escalation signals are listed as triggers for shifting role-cluster emphasis (e.g., escalation may mean containment becomes primary). Candidate interventions are specific and keyed to role gaps. Flagged unknowns are testable. Confidence per finding distinguishes confidence in role-need (often higher) from confidence in bearer-availability (often lower) from confidence in intervention-effectiveness (depends on context).

## VERIFICATION CRITERIA

Verified means: parties and conflict named; surrounding community/network mapped; all three role-clusters (prevention / resolution / containment) addressed; the ten Ury roles surveyed (active / needed / not-yet-relevant per role); role-assignment candidates link roles to actual bearers; escalation signals listed; at least two specific third-side interventions named with role-gap rationale; flagged unknowns testable in practice; intervention limits acknowledged where context warrants; the five critical questions are addressable from the output. Confidence per major finding accompanies each claim. The third-side stance is maintained throughout (no party advocacy creep).

## CAVEATS AND OPEN DEBATES

This mode does not carry mode-specific debates. The Wave 2 sibling `interest-mapping` and the Wave 3 sibling `principled-negotiation` carry **Debate D6** (Fisher-Ury sufficiency for adversarial contexts; Voss critique), which bears on third-side intervention obliquely: when a third party coaches one of the parties in negotiation method, the choice of method (Fisher-Ury integrative vs. Voss tactical-empathy adversarial) is a third-side decision the analysis may need to address. The `voss-tactical-empathy` lens is carried optionally for that case. The territory-level question of how mediator-stance interacts with deep-identity / community-rooted conflicts (Lederach's transformation lineage) and with conflicts that have historical trajectory (Kriesberg's constructive-conflicts) is treated as breadth scanning rather than as a mode-specific debate; both lenses are carried optionally for context where the Ury ten-role frame benefits from supplementation. Citations: Ury 2000 *The Third Side: Why We Fight and How We Can Stop*; Lederach 2003 *The Little Book of Conflict Transformation*; Kriesberg & Dayton 2017 *Constructive Conflicts*; Fisher, Ury & Patton 1981/2011 *Getting to Yes* for the cross-reference to party-side method.
