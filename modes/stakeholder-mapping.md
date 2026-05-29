---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

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

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Stakeholder Mapping is multi-party descriptive landscape work: a Bryson power-interest grid plus Mitchell-Agle-Wood three-dimensional salience (power × legitimacy × urgency) over an inventory that deliberately scans for parties outside the user's initial frame, with concrete interests (Wants / Could-lose / BATNA) articulated per party, relationships among parties surfaced, and absent-or-marginalized parties named explicitly. It is distinct from cui-bono (the lighter T2 sibling — single situation, single set of beneficiaries), from conflict-structure (the heavier sibling — systemic conflict, gap-deferred), from interest-mapping / principled-negotiation / third-side (cross-territory T13 follow-ons — active negotiation), and from wicked-problems (T2 — tangled multi-system feedback rather than descriptive multi-party landscape).

**Procedure.**

1. Lock the situation or decision under analysis.
2. Build the party inventory deliberately scanning beyond the user's initial frame — affected-but-unrepresented parties, informal influencers, intermediary-filtered voices, adjacent-domain parties, future parties, silent parties whose absence is itself a stake.
3. Articulate stakes per party as concrete interests — what they Want, what they could Lose, their BATNA if the situation goes against them, internal heterogeneity (large groups are rarely monolithic).
4. Position each party on the Bryson 2×2 grid — high-power-high-interest (manage closely) / high-power-low-interest (keep satisfied) / low-power-high-interest (keep informed) / low-power-low-interest (monitor).
5. Apply Mitchell-Agle-Wood salience on three dimensions (power, legitimacy, urgency) — produce one of eight classes (definitive / dominant / dangerous / dependent / dormant / discretionary / demanding / non-stakeholder) with per-dimension reasoning.
6. Map relationships among parties — ally / opposition / dependency / broker / coalition — with the basis of the relationship.
7. Name absent or marginalised parties explicitly — kind of absence, reason, what their stake would be if present; or note that none were identifiable in this situation.
8. Resist tidiness — never drop low-salience-but-legitimate parties for a cleaner diagram; the long tail of the inventory is the mode's analytical value.
9. Assign confidence per finding.

**Goal.** Produce a multi-party stakeholder map — Bryson + Mitchell-Agle-Wood structured matrix where each party's concrete interests, two-dimensional power-interest position, three-dimensional salience class, and relationships to other parties are explicit, with absent or marginalised parties surfaced.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — frame-bounded inventory.** Has the inventory identified parties from outside the user's initial frame, or has the analysis stayed inside the user's pre-existing mental model? Failure mode if unmet: `frame-bounded-inventory`.
- **CQ2 — concrete-interest stakes.** Are stakes named at the level of concrete interests (what the party wants and could lose), rather than role-labels alone? Failure mode if unmet: `role-as-stake`.
- **CQ3 — three-dimensional salience.** Has salience been assessed using power AND legitimacy AND urgency (Mitchell-Agle-Wood), so a high-power-low-legitimacy party isn't conflated with a high-legitimacy-low-power party? Failure mode if unmet: `single-axis-salience`.
- **CQ4 — absent parties surfaced.** Have absent or marginalized parties been explicitly named, or has the map silently mirrored existing power asymmetries? Failure mode if unmet: `silent-power-mirroring`.

A passing output names parties from outside the user's initial frame, articulates stakes as concrete interests, classifies salience along all three Mitchell-Agle-Wood dimensions, surfaces relationships among parties, and explicitly names absent or marginalized parties.

**Named failure modes.**

- *frame-bounded-inventory* — every party in the inventory shares the user's frame; no parties from outside the frame appear.
- *role-as-stake* — stakes named as role-labels (regulator, investor, end-user) without articulating what the party concretely wants and could lose.
- *single-axis-salience* — salience plotted on one dimension (usually power) only; legitimacy and urgency are absent or collapsed.
- *silent-power-mirroring* — salience map ranks parties in proportion to their existing power; no marginalized-but-legitimate party appears.
- *laundry-list-flatness* — stakeholders listed without relationships among them or differential stakes; the map is a list, not a map.

## REVISION GUIDANCE

Revise to expand the inventory where the draft has stayed inside the user's frame. Revise to articulate stakes as concrete interests where the draft has named only roles. Revise to populate Mitchell-Agle-Wood salience on all three dimensions where only power is plotted. Revise to surface absent parties where the map has silently mirrored existing power asymmetries. Resist revising toward a tidier diagram if tidiness comes at the cost of dropping low-salience-but-legitimate parties — the mode's analytical value is in the long tail of the inventory, not the short head.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Bryson + Mitchell-Agle-Wood stakeholder atom set: party-inventory atoms (including parties from outside the user's frame), concrete-interest stake atoms per party, Bryson power-interest positioning, Mitchell-Agle-Wood salience classification on three dimensions, relationship atoms among parties, absent-or-marginalized-party atoms, and per-finding confidence**. The atoms are:

1. **Party-inventory atoms.** Each atom names one party with a brief characterisation. The inventory deliberately scans beyond the user's initial frame — parties affected but not represented, parties with informal influence not visible on org charts, parties filtered through intermediaries, parties from adjacent domains, future parties whose interests will be created by the action, silent parties whose absence is itself a stake. Frame-bounded-inventory is the named failure mode the consolidator watches for; inventories where every party shares the user's frame get reshaped to surface at least one outside-frame party (or explicitly note none was identifiable).

2. **Concrete-interest stake atoms per party.** Each atom names: what the party concretely wants, what they could concretely lose, what their best alternative is if this situation goes against them, and internal heterogeneity (large stakeholder groups are rarely monolithic). Role-as-stake is the named failure mode; stakes named at role-label level (`regulator`, `investor`, `end-user`) without concrete interests get reshaped.

3. **Bryson power-interest positioning atoms.** Each atom plots one party on the 2×2 grid: `high-power-high-interest` (manage closely) / `high-power-low-interest` (keep satisfied) / `low-power-high-interest` (keep informed) / `low-power-low-interest` (monitor).

4. **Mitchell-Agle-Wood salience classification atoms.** Each atom classifies one party by the three-dimensional combination of `power`, `legitimacy`, and `urgency`, producing one of the eight classes: `definitive` (all three) / `dominant` / `dangerous` / `dependent` / `dormant` / `discretionary` / `demanding` / `non-stakeholder`. Single-axis-salience is the named failure mode; salience plotted only on power (collapsing legitimacy and urgency) gets reshaped to three-dimensional classification.

5. **Relationship atoms among parties.** Each atom names: a relationship between two parties (`ally` / `opposition` / `dependency` / `broker` / `coalition`) with the basis of the relationship. Laundry-list-flatness is the named failure mode; inventories with no relationship structure get reshaped from "list of parties" to "map of parties".

6. **Absent-or-marginalized-party atoms.** Each atom names: a party that is affected but unrepresented, marginalised, or silent, with the reason-for-absence (no organised constituency, no formal standing, filtered through intermediaries, etc.). Silent-power-mirroring is the named failure mode; salience maps that rank parties in proportion to existing power without surfacing marginalised-but-legitimate parties get reshaped.

7. **Confidence per finding.** Each major claim carries confidence (party inventory; stake characterisation; salience classification; relationship claims).

**Mode-specific bloat patterns to cut:**

- **Frame-bounded inventory** — every party shares the user's vantage; no outside-frame parties.
- **Role-as-stake** — stakes named as roles without concrete interest articulation.
- **Single-axis salience** — power alone plotted; legitimacy and urgency collapsed.
- **Silent power-mirroring** — salience proportional to existing power; marginalised-but-legitimate parties absent.
- **Laundry-list flatness** — parties listed without relationships among them.
- **Salience without grounding** — Mitchell-Agle-Wood class asserted without explicit per-dimension reasoning.
- **Tidy diagram bias** — dropping low-salience-but-legitimate parties for cleaner visualisation. The long tail of the inventory is the mode's analytical value.

**What NOT to collapse:**

- **Outside-frame parties** — they are the load-bearing finding; the user couldn't have generated them without breadth scanning.
- **Stream disagreement about salience class** — when streams classified the same party in different MAW classes, the disagreement is itself a finding about contested legitimacy or urgency.
- **Heterogeneity within large parties** — when a stakeholder group has internal divisions (different factions, different interests), the divisions survive rather than being collapsed.
- **Marginalised-party atoms** — never deleted for diagram cleanliness.

## VERIFICATION CRITERIA

Verified means: the inventory contains at least one party from outside the user's initial frame, or the analysis explicitly notes that no such party was identifiable; every party has a stake articulated as concrete interest, not just role-label; Mitchell-Agle-Wood salience is populated on all three dimensions for every party (or explicitly marked as not-applicable with reason); at least one absent or marginalized party is named, or the analysis explicitly notes that no such party exists; relationships among parties are stated rather than left implicit; the four critical questions are addressable from the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **multi-party stakeholder map** — a Bryson + Mitchell-Agle-Wood structured matrix where each party's concrete interests, two-dimensional power-interest position, three-dimensional salience class, and relationships to other parties are explicit, with absent or marginalised parties surfaced. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Stakeholder inventory.** A table. Each row: `**[Party]** — brief characterisation. Role in situation: [...]. Inside / outside user's initial frame: [...].`

2. **Power-interest positioning (Bryson 2×2).** A labelled block showing each party's quadrant: `**High power / High interest (manage closely):** [parties]. **High power / Low interest (keep satisfied):** [parties]. **Low power / High interest (keep informed):** [parties]. **Low power / Low interest (monitor):** [parties].`

3. **Mitchell-Agle-Wood salience classification.** A table. Each row: `**[Party]** — Power: [yes/no/partial]. Legitimacy: [yes/no/partial]. Urgency: [yes/no/partial]. MAW class: [definitive / dominant / dangerous / dependent / dormant / discretionary / demanding / non-stakeholder]. Reasoning: [...].`

4. **Stake per party.** A table. Each row: `**[Party]** — Wants: [concrete interest]. Could lose: [concrete loss]. BATNA: [best alternative if this goes against them]. Internal heterogeneity: [factions / divisions / monolithic].` Role-labels without concrete content are reshaped at this layer.

5. **Relationships among parties.** Bulleted list. Each: `**[Party A] ↔ [Party B]** — relationship type: [ally / opposition / dependency / broker / coalition]. Basis: [historical / structural / situational]. Implications: [...].`

6. **Absent or marginalized parties.** Bulleted list. Each: `**[Absent party]** — kind of absence: [unrepresented / marginalised / silent / future]. Reason: [no organised constituency / no formal standing / filtered through intermediaries / not yet existent]. Stake-if-present: [what their interest would be].` Where no absent parties exist, this section says so explicitly with reasoning.

7. **Confidence per finding.** Bulleted list of confidence assessments per major claim with grounding.

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- Bryson vocabulary (`manage closely` / `keep satisfied` / `keep informed` / `monitor`) appears verbatim in section 2.
- Mitchell-Agle-Wood eight-class vocabulary (`definitive` / `dominant` / `dangerous` / `dependent` / `dormant` / `discretionary` / `demanding` / `non-stakeholder`) appears verbatim in section 3, with the three-dimensional (power × legitimacy × urgency) reasoning explicit per party.
- Stakes (section 4) are concrete — `Wants`, `Could lose`, `BATNA`. Role-label-only stakes are reshaped here.
- Relationships (section 5) carry a type and a basis. Untyped relationships are reshaped.
- Absent parties (section 6) appear in their own section, not buried in the inventory. The mode's analytical value sits in surfacing what's not yet visible.
- When streams diverged on salience class for the same party, section 3 carries inline disagreement: `**[Party] — contested MAW class:** stream A: [class]; stream B: [class]. Resolution path: [what would decide].`
- When the inventory lacked outside-frame parties despite breadth scanning, section 1 closes with: `**Frame-bounded note:** no parties from outside the user's initial frame were identifiable in this situation. Boundary-critique (Ulrich CSH) is the appropriate sideways-route if frame-completeness is the operative question.`

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `requires`, `enables`, `contradicts`, `supports`, `qualifies`
**Deprioritize:** `parent`, `analogous-to`

*Family: stakeholder-strategy. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
