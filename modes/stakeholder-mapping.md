---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Stakeholder Mapping

```yaml
# 0. IDENTITY
mode_id: stakeholder-mapping
canonical_name: Stakeholder Mapping
suffix_rule: analysis
educational_name: multi-party stakeholder mapping (Bryson, Mitchell-Agle-Wood salience)

# 1. TERRITORY AND POSITION
territory: T8-stakeholder-conflict
gradation_position:
  axis: complexity
  value: multi-party-descriptive
adjacent_modes_in_territory:
  - mode_id: conflict-structure
    relationship: complexity-heavier sibling (systemic; gap-deferred per CR-6)
  - mode_id: cui-bono
    relationship: complexity-lighter sibling (single-situation interest; lives in T2)
  - mode_id: interest-mapping
    relationship: cross-territory follow-on (Fisher/Ury; lives in T13; foundational input)
  - mode_id: principled-negotiation
    relationship: cross-territory follow-on (lives in T13; receives stakeholder map as input)
  - mode_id: third-side
    relationship: cross-territory follow-on (Ury mediator-stance; lives in T13)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I need to map out who's involved here"
    - "there are multiple parties with different stakes"
    - "before we move, we need to understand the parties"
    - "we keep getting blindsided by people we forgot to consider"
    - "who has standing in this and how much"
  prompt_shape_signals:
    - "stakeholder map"
    - "stakeholder mapping"
    - "stakeholder analysis"
    - "Bryson power-interest grid"
    - "Mitchell Agle Wood salience"
    - "who needs to be at the table"
    - "RACI"
disambiguation_routing:
  routes_to_this_mode_when:
    - "multiple identifiable parties with divergent stakes; user wants the landscape descriptively"
    - "input feeds a downstream negotiation, decision, or wicked-problems analysis"
    - "user is trying to surface absent or marginalized parties before action"
  routes_away_when:
    - "single situation, single set of beneficiaries — interest read" → cui-bono (T2)
    - "active negotiation requiring guidance now" → interest-mapping or principled-negotiation (T13)
    - "tangled wicked problem with feedback loops and irreducible value conflict" → wicked-problems (T2)
    - "decision among parties where the user is the decider" → decision-clarity or decision-architecture
when_not_to_invoke:
  - "User has only one party of interest; mapping is overkill" → cui-bono
  - "User has the parties already mapped and wants negotiation strategy" → T13
  - "User wants to evaluate an argument's soundness rather than its sponsoring constituencies" → T1

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [situation_or_decision, candidate_stakeholder_inventory, salience_dimensions]
    optional: [historical_relationships, prior_engagement_record, formal_authority_structure]
    notes: "Applies when user supplies a candidate party list or names salience dimensions (power, legitimacy, urgency)."
  accessible_mode:
    required: [situation_description]
    optional: [parties_user_already_thought_of]
    notes: "Default. Mode infers stakeholder inventory from the situation and elicits parties the user has not yet named."
  detection:
    expert_signals: ["stakeholder inventory", "salience dimensions", "RACI", "power-interest grid", "Mitchell Agle Wood"]
    accessible_signals: ["who's involved", "who has a stake", "who needs to be at the table", "stakeholder map"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe the situation or decision and any parties you've already identified?'"
    on_underspecified: "Ask: 'What's the situation, and which parties have you already considered?'"
output_contract:
  artifact_type: mapping
  required_sections:
    - stakeholder_inventory
    - power_interest_positioning
    - mitchell_agle_wood_salience_classification
    - stake_per_party
    - relationships_among_parties
    - absent_or_marginalized_parties
    - confidence_per_finding
  format: matrix

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the inventory identified parties from outside the user's initial frame, or has the analysis stayed inside the user's pre-existing mental model of who counts?"
    failure_mode_if_unmet: frame-bounded-inventory
  - cq_id: CQ2
    question: "Are stakes named at the level of concrete interests (what the party wants and could lose), rather than at the level of role-labels alone?"
    failure_mode_if_unmet: role-as-stake
  - cq_id: CQ3
    question: "Has salience been assessed using more than one dimension (power AND legitimacy AND urgency, per Mitchell-Agle-Wood), so a high-power-low-legitimacy party isn't conflated with a high-legitimacy-low-power party?"
    failure_mode_if_unmet: single-axis-salience
  - cq_id: CQ4
    question: "Have absent or marginalized parties been explicitly named, or has the map silently mirrored existing power asymmetries?"
    failure_mode_if_unmet: silent-power-mirroring

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: frame-bounded-inventory
    detection_signal: "Every party in the inventory shares the user's frame; no parties from outside the frame appear."
    correction_protocol: re-dispatch
  - name: role-as-stake
    detection_signal: "Stakes are named as role-labels (regulator, investor, end-user) without articulating what the party concretely wants and could lose."
    correction_protocol: flag
  - name: single-axis-salience
    detection_signal: "Salience is plotted on one dimension (usually power) only; legitimacy and urgency are absent or collapsed."
    correction_protocol: re-dispatch
  - name: silent-power-mirroring
    detection_signal: "The salience map ranks parties in proportion to their existing power; no marginalized-but-legitimate party appears."
    correction_protocol: re-dispatch
  - name: laundry-list-flatness
    detection_signal: "Stakeholders are listed without relationships among them or differential stakes; the map is a list, not a map."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - stakeholder-analysis-frameworks
  optional:
    - ulrich-csh-boundary-categories (when boundary critique cross-cuts to surface absent parties)
    - public-choice-theory (when parties are organized constituencies)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: conflict-structure
    when: "Inventory is multi-party AND parties exhibit systemic conflict structure (when conflict-structure is built)."
  sideways:
    target_mode_id: interest-mapping
    when: "User is moving from descriptive mapping into active negotiation; route to T13."
  downward:
    target_mode_id: cui-bono
    when: "Inventory collapses to a single party of interest; lighter mode is appropriate."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Stakeholder Mapping is the granularity with which each party's stake is articulated as concrete interests rather than role-labels. A thin pass names parties by role; a substantive pass names what each party concretely wants, what they could concretely lose, what their best alternative is if this situation goes against them, and what their internal heterogeneity looks like (large stakeholder groups are rarely monolithic). Test depth by asking: could the analysis predict how each party would behave when offered specific concessions, or when faced with specific threats?

## BREADTH ANALYSIS GUIDANCE

Widening the lens in Stakeholder Mapping means deliberate scanning for parties outside the user's initial frame: parties affected but not represented, parties with informal influence not visible on org charts, parties whose voices are filtered through intermediaries, parties from adjacent domains who become stakeholders if the situation shifts, future parties whose interests will be created by the action under consideration, and silent parties whose absence is itself a stake. Apply Mitchell-Agle-Wood salience (power × legitimacy × urgency) on each candidate party rather than collapsing to power alone.

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) frame-bounded inventory; (CQ2) role-as-stake; (CQ3) single-axis salience; (CQ4) silent power mirroring. The named failure modes (frame-bounded-inventory, role-as-stake, single-axis-salience, silent-power-mirroring, laundry-list-flatness) are the evaluation checklist. A passing Stakeholder Mapping output names parties from outside the user's initial frame, articulates stakes as concrete interests, classifies salience along all three Mitchell-Agle-Wood dimensions, surfaces relationships among parties, and explicitly names absent or marginalized parties.

## REVISION GUIDANCE

Revise to expand the inventory where the draft has stayed inside the user's frame. Revise to articulate stakes as concrete interests where the draft has named only roles. Revise to populate Mitchell-Agle-Wood salience on all three dimensions where only power is plotted. Revise to surface absent parties where the map has silently mirrored existing power asymmetries. Resist revising toward a tidier diagram if tidiness comes at the cost of dropping low-salience-but-legitimate parties — the mode's analytical value is in the long tail of the inventory, not the short head.

## CONSOLIDATION GUIDANCE

Consolidate as a structured matrix with the seven required sections. Stakeholder inventory is row-organized by party. Power-interest positioning emits a 2×2 grid (Bryson) with each party plotted; Mitchell-Agle-Wood salience is a separate three-dimensional classification (definitive / dominant / dangerous / dependent / dormant / discretionary / demanding / non-stakeholder). Stake-per-party is a column on the inventory. Relationships among parties are emitted as a relationship list (allies / opposition / dependencies / brokers). Absent or marginalized parties have their own section with reason-for-absence. Confidence per finding accompanies each row.

## VERIFICATION CRITERIA

Verified means: the inventory contains at least one party from outside the user's initial frame, or the analysis explicitly notes that no such party was identifiable; every party has a stake articulated as concrete interest, not just role-label; Mitchell-Agle-Wood salience is populated on all three dimensions for every party (or explicitly marked as not-applicable with reason); at least one absent or marginalized party is named, or the analysis explicitly notes that no such party exists; relationships among parties are stated rather than left implicit; the four critical questions are addressable from the output.
