---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

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

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Third Side is Ury's third-side mediation analysis — a mediator-stance multi-party reading of a conflict from the surrounding community's vantage. It surveys the ten Ury roles (provider / teacher / bridge-builder / mediator / arbiter / equalizer / healer / witness / referee / peacekeeper) across three clusters (prevention / resolution / containment), linking each active or needed role to actual bearers in the community. It is distinct from interest-mapping (party-stance, two-party-default, depth-light), principled-negotiation (party-stance, two-party-default, depth-thorough), stakeholder-mapping (T8 descriptive multi-party without active conflict-resolution framing), strategic-interaction (T18 game-theoretic equilibria/coalitions), and boundary-critique (T2 policy/excluded-voices analysis).

**Procedure.**

1. Summarise parties and the conflict in neutral third-side stance — not party-stance.
2. Map the surrounding community in three rings — intimate (family / close colleagues), mid (extended network / institutional context), outer (wider community / public / norms). The third side is a *social fact* that may or may not contain the roles needed.
3. Survey the ten Ury roles across three clusters: **prevention** (provider, teacher, bridge-builder), **resolution** (mediator, arbiter, equalizer, healer), **containment** (witness, referee, peacekeeper) — each tagged `active` / `needed but unfilled` / `not yet relevant`.
4. Link each active or needed role to a named bearer in the surrounding community — actual person, institution, or norm. Abstract role assertions without candidates are reshaped.
5. Filter bearer candidates through cultural context — the community's norms, hierarchies, and existing institutions shape who can credibly fill which role.
6. Surface escalation signals (rhetoric hardening, third-party recruitment, channel breakdown, public symbolic markers, threats of exit/violence) and the cluster-shift they imply (typically toward containment).
7. Recommend candidate third-side interventions, each keyed to a specific role gap and a candidate bearer — at least two.
8. Flag unknowns testable in practice — questions whose answers would change the role analysis.
9. Acknowledge intervention limits — where power asymmetry makes mediation cover for coercion, where parties' agency requires confrontation rather than mediation, where third-side intervention would be intrusive.
10. Maintain third-side stance throughout (no party-stance creep) and parties-as-agents discipline (not passive objects of intervention).
11. Provide three-kind confidence per finding: role-need / bearer-availability / intervention-effectiveness, kept distinct.

**Goal.** Produce a Ury third-side mediation analysis that surveys all ten roles across three clusters, links each active or needed role to a named bearer in the surrounding community, surfaces escalation signals and intervention limits, and maintains third-side stance throughout.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — third-side stance maintained.** Has the analysis stayed at "what the surrounding community can do" rather than slipping into party-side advocacy for one party's interests? Failure mode if unmet: `party-stance-creep`.
- **CQ2 — ten-role checklist surveyed.** Have the ten Ury roles been considered as a checklist rather than collapsing into a generic mediator role? Failure mode if unmet: `ten-role-collapse`.
- **CQ3 — three role-clusters considered.** Have prevention, resolution, and containment all been considered, rather than defaulting to resolution roles only? Failure mode if unmet: `prevention-or-containment-omission`.
- **CQ4 — roles linked to bearers.** Have role assignments been linked to actual people / institutions / norms in the surrounding community, rather than asserting roles in the abstract? Failure mode if unmet: `roles-without-bearers`.
- **CQ5 — limits acknowledged.** Have the limits of third-side intervention been acknowledged — power asymmetry, parties' primary agency, situations requiring confrontation — rather than asserting third side as universally appropriate? Failure mode if unmet: `third-side-overreach`.

A passing output names parties and conflict in neutral stance, maps the surrounding community in at least two rings, surveys the ten roles across all three clusters with status per role, names bearer candidates for active or needed roles, surfaces escalation signals, recommends at least two specific interventions keyed to role gaps, flags testable unknowns, acknowledges intervention limits, and keeps three confidence kinds distinct.

**Named failure modes.**

- *party-stance-creep* — analysis recommends moves that favor one party's interests rather than analyzing what the surrounding community can do; output reads as advocacy.
- *ten-role-collapse* — output names only mediator (or only one or two of the ten roles); the full ten-role checklist is not surveyed.
- *prevention-or-containment-omission* — output addresses only resolution roles; prevention and/or containment clusters not addressed.
- *roles-without-bearers* — roles listed without naming actual people / institutions / norms who could fill them.
- *third-side-overreach* — analysis asserts third-side intervention as appropriate without considering its limits (power asymmetry covering coercion, parties' agency, situations requiring confrontation).
- *cultural-context-flatness* — third-side roles applied without considering how surrounding-community cultural norms, hierarchies, and institutions shape availability.
- *parties-as-passive* — parties framed as objects of third-side intervention rather than agents whose own moves matter.

## REVISION GUIDANCE

Revise to restore third-side stance where the draft slipped into party advocacy. Revise to expand the role survey where the draft collapsed to mediator-only. Revise to address prevention and containment where the draft addressed only resolution. Revise to name bearers where the draft asserted roles in the abstract. Revise to acknowledge limits where the draft asserted third-side as universally appropriate. Revise to honor parties' agency where the draft positioned them as passive objects of intervention. Resist revising toward generic mediator-talk — the mode's analytical character is the *ten-role-and-three-cluster* frame, not generic mediation; collapsing back to "mediator" is a failure mode, not a polish. Resist revising toward over-confident community capacity assertions — sometimes the surrounding community lacks the third side the conflict needs, and naming that is part of honest analysis.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Ury third-side atom set: parties-and-conflict summary, surrounding-community mapping, ten-role atoms across three clusters (prevention / resolution / containment), role-assignment atoms linking each role to actual bearers, escalation-signal atoms, candidate intervention atoms keyed to role gaps, flagged-unknown atoms, three-kind confidence (role-need / bearer-availability / intervention-effectiveness), and a standing third-side-stance discipline**. The atoms are:

1. **Parties-and-conflict summary atom.** Each party named and the conflict characterised neutrally (third-side stance, not party-stance).

2. **Surrounding-community-or-network mapping atoms.** Each atom names: an actor / institution / norm in the surrounding community/network — at intimate, mid, and outer rings (family / close colleagues; extended network / institutional context; wider community / public / norms). The third side is a *social fact* that may or may not contain the roles needed.

3. **Prevention-role atoms — Ury cluster 1.** Each atom names one of three prevention roles (`provider` — addresses frustrated needs that drive conflict; `teacher` — gives skills for conflict-handling; `bridge-builder` — develops relationships that pre-empt conflict), plus its status (`active` / `needed but unfilled` / `not yet relevant`).

4. **Resolution-role atoms — Ury cluster 2.** Each atom names one of four resolution roles (`mediator` — facilitates communication; `arbiter` — judges when self-resolution fails; `equalizer` — democratises power asymmetry; `healer` — addresses injured emotions and broken relationships), plus status.

5. **Containment-role atoms — Ury cluster 3.** Each atom names one of three containment roles (`witness` — pays attention so escalation has consequences; `referee` — establishes rules for fair fight; `peacekeeper` — interposes when violence threatens), plus status.

6. **Ten-role checklist completeness check.** Ten-role-collapse is the named failure mode the consolidator watches for; outputs that named only "mediator" generically (or only one or two roles) get reshaped to survey the full checklist. Prevention-or-containment-omission is the named failure mode for cluster-imbalance; analyses addressing only resolution roles get reshaped to address prevention and containment.

7. **Role-assignment candidate atoms — per active or needed role.** Each atom names: an actual person / institution / norm in the surrounding community who could fill the role. Roles-without-bearers is the named failure mode; abstract role assertions without named candidates get reshaped.

8. **Escalation-signal atoms.** Each atom names: a signal that the conflict is escalating (rhetoric hardening, third-party recruitment to one side, breakdown of communication channels, emergence of public symbolic markers, threats of exit or violence) and the role-cluster shift it implies (escalation typically shifts containment toward primary).

9. **Candidate intervention atoms — keyed to role gaps.** Each atom names: a specific third-side intervention, the role gap it addresses, and the candidate bearer.

10. **Flagged-unknown atoms.** Testable in practice — questions the user (or the mediator) can investigate that would change the role analysis.

11. **Intervention-limit atoms.** Where third-side intervention may be inappropriate (power asymmetry that makes mediation cover for coercion; parties' own agency requiring confrontation rather than mediation; situations where third-side intervention is intrusive), the limits surface explicitly. Third-side-overreach is the named failure mode; analyses asserting third-side as universally appropriate get reshaped.

12. **Cultural-context flag — when applicable.** Where surrounding-community cultural norms, hierarchies, and institutions shape which roles are available and who can credibly fill them, the flag surfaces. Cultural-context-flatness is the named failure mode.

13. **Parties-as-agents discipline.** A standing atom: parties are *agents*, not passive objects of third-side intervention. Third-side roles support parties' own moves. Parties-as-passive is the named failure mode.

14. **Third-side-stance discipline.** A standing atom: analysis stays at "what can the surrounding community do" rather than slipping into "what should party X do". Party-stance-creep is the named failure mode.

15. **Three-kind confidence per finding.** Role-need (often higher), bearer-availability (often lower), intervention-effectiveness (depends on context). Kept distinct.

**Mode-specific bloat patterns to cut:**

- **Party-stance creep** — recommendations favoring one party rather than what the third side can do for the conflict as a whole.
- **Ten-role collapse** — generic mediator-talk; the full Ury ten-role checklist absent.
- **Cluster imbalance** — only resolution roles addressed; prevention and containment elided.
- **Roles without bearers** — abstract role assertions without named candidates.
- **Third-side overreach** — third-side framed as universally appropriate; limits unacknowledged.
- **Cultural-context flatness** — roles applied without considering whether the surrounding community's institutions and norms can credibly fill them.
- **Parties-as-passive** — third-side positioned as solving the conflict rather than supporting party agency.
- **Generic mediator-talk** — collapsing back to "mediator" rather than the ten-role-and-three-cluster frame.

**What NOT to collapse:**

- **The ten-role checklist** — full survey required; partial coverage gets reshaped.
- **Three-cluster framing** — prevention / resolution / containment distinctions are operative.
- **Stream disagreement about which roles are needed** — when streams identified different role-need patterns, both survive with their respective reasoning.
- **Intervention-limit atoms** — never deleted for cleanliness; the mode's honesty requires acknowledging where the third side cannot help.
- **Three confidence kinds** — never blended into a single confidence value.

## VERIFICATION CRITERIA

Verified means: parties and conflict named; surrounding community/network mapped; all three role-clusters (prevention / resolution / containment) addressed; the ten Ury roles surveyed (active / needed / not-yet-relevant per role); role-assignment candidates link roles to actual bearers; escalation signals listed; at least two specific third-side interventions named with role-gap rationale; flagged unknowns testable in practice; intervention limits acknowledged where context warrants; the five critical questions are addressable from the output. Confidence per major finding accompanies each claim. The third-side stance is maintained throughout (no party advocacy creep).

## OUTPUT FORMAT GUIDANCE

The deliverable is a **Ury third-side mediation analysis** — a structured mapping that surveys all ten roles across three clusters (prevention / resolution / containment), links each active or needed role to a named bearer in the surrounding community, surfaces escalation signals and intervention limits, and maintains third-side stance throughout. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Parties and conflict summary.** One paragraph naming each party neutrally and characterising the conflict from third-side stance.

2. **Surrounding community or network.** A labelled block mapping the community in three rings. `**Intimate ring (family / close colleagues):** [actors]. **Mid ring (extended network / institutional context):** [actors / institutions]. **Outer ring (wider community / public / norms):** [actors / norms].`

3. **Prevention roles active or needed.** Per role, one labelled block: `**Provider:** status: [active / needed / not yet relevant]. Frustrated needs addressed: [...].` `**Teacher:** status: [...]. Skills given: [...].` `**Bridge-builder:** status: [...]. Relationships developed: [...].`

4. **Resolution roles active or needed.** Per role, one labelled block: `**Mediator:** status: [...]. Communication facilitated: [...].` `**Arbiter:** status: [...]. Judgments rendered: [...].` `**Equalizer:** status: [...]. Power-asymmetry addressed: [...].` `**Healer:** status: [...]. Emotions / relationships addressed: [...].`

5. **Containment roles active or needed.** Per role, one labelled block: `**Witness:** status: [...]. Attention paid: [...].` `**Referee:** status: [...]. Rules established: [...].` `**Peacekeeper:** status: [...]. Interposition: [...].`

6. **Role assignment candidates.** Bulleted list. Each: `**[Role]** — candidate bearer(s): [actual person / institution / norm in the surrounding community]. Credibility for the role: [...]. Cultural-context fit: [...].`

7. **Escalation signals to watch.** Bulleted list. Each: `**[Signal — rhetoric hardening / third-party recruitment / channel breakdown / public symbolic markers / threats of exit or violence]** — what it implies: [shift in role-cluster emphasis, typically toward containment].`

8. **Candidate third-side interventions.** Numbered list. Each: `[N]. **[Intervention]** — role gap addressed: [...]. Candidate bearer: [...]. Expected effect on conflict trajectory: [...].` At least two interventions appear.

9. **Flagged unknowns to test.** Bulleted list. Each: `**[Question]** — what it would test: [...]. How the answer changes the analysis: [...].`

10. **Confidence per finding.** Three labelled confidence assessments, kept distinct:
    - `Role-need: [confidence and basis — typically higher].`
    - `Bearer-availability: [confidence and basis — typically lower].`
    - `Intervention-effectiveness: [confidence and basis — depends on context].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 10.
- Ury ten-role vocabulary (`provider` / `teacher` / `bridge-builder` / `mediator` / `arbiter` / `equalizer` / `healer` / `witness` / `referee` / `peacekeeper`) appears verbatim with operative meanings preserved per role.
- Three-cluster framing (prevention / resolution / containment) appears as the structural backbone of sections 3–5.
- Roles link to *named bearers* in section 6 — abstract role assertions are reshaped at this layer.
- The third-side stance is maintained throughout — party-stance creep gets reshaped to community-stance analysis at every section.
- Limits acknowledgement: when third-side overreach was flagged, the deliverable carries: `**Note on intervention limits:** [where third-side intervention may be inappropriate — power asymmetry that makes mediation cover for coercion / parties' agency requiring confrontation / intrusive intervention]. These limits should be honoured before deploying the interventions in section 8.`
- When cultural-context flatness was flagged, section 6 carries: `**Cultural-context note:** the surrounding community's norms and hierarchies shape which roles can credibly be filled. The bearer candidates above are filtered through this context; in another cultural setting the same roles would require different bearers.`
- Confidence (section 10) stays as three distinct kinds; blending is reshaped.

## CAVEATS AND OPEN DEBATES

This mode does not carry mode-specific debates. The Wave 2 sibling `interest-mapping` and the Wave 3 sibling `principled-negotiation` carry **Debate D6** (Fisher-Ury sufficiency for adversarial contexts; Voss critique), which bears on third-side intervention obliquely: when a third party coaches one of the parties in negotiation method, the choice of method (Fisher-Ury integrative vs. Voss tactical-empathy adversarial) is a third-side decision the analysis may need to address. The `voss-tactical-empathy` lens is carried optionally for that case. The territory-level question of how mediator-stance interacts with deep-identity / community-rooted conflicts (Lederach's transformation lineage) and with conflicts that have historical trajectory (Kriesberg's constructive-conflicts) is treated as breadth scanning rather than as a mode-specific debate; both lenses are carried optionally for context where the Ury ten-role frame benefits from supplementation. Citations: Ury 2000 *The Third Side: Why We Fight and How We Can Stop*; Lederach 2003 *The Little Book of Conflict Transformation*; Kriesberg & Dayton 2017 *Constructive Conflicts*; Fisher, Ury & Patton 1981/2011 *Getting to Yes* for the cross-reference to party-side method.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- OPV
- KVI
- CAF
- FIP
- AGO

Mental models (always loaded):
- ury-third-side
- fisher-ury-principled-negotiation
- cooperation
- procedural-justice
- psychological-safety
- stakeholder-analysis-frameworks
- social-proof

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `requires`, `enables`, `supports`, `qualifies`, `analogous-to`
**Deprioritize:** `parent`, `contradicts`

*Family: stakeholder-strategy (per-mode adjustment). See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
