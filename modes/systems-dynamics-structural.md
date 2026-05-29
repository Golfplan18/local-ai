---
nexus:
  - ora
type: mode
tags:
  - framework/instruction
  - architecture
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Systems Dynamics Structural

```yaml
# 0. IDENTITY
mode_id: systems-dynamics-structural
canonical_name: Systems Dynamics Structural
suffix_rule: analysis
educational_name: feedback-system structural mapping (Forrester/Senge lineage)

# 1. TERRITORY AND POSITION
territory: T17-process-and-system-analysis
gradation_position:
  axis: complexity
  value: feedback
adjacent_modes_in_territory:
  - mode_id: process-mapping
    relationship: specificity-process-flow sibling (linear/non-feedback workflow)
  - mode_id: systems-dynamics-causal
    relationship: operation-counterpart (T4 home; causal-investigation posture; same feedback lenses, different operation)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want to understand how this system currently works"
    - "map the feedback structure of this organisation/workflow/process"
    - "show me the loops and stocks in this system"
    - "I need a structural picture before deciding what to change"
  prompt_shape_signals:
    - "how does this system work"
    - "draw the feedback structure (structural)"
    - "map the system's loops and flows"
    - "structural diagram with feedback dynamics"
disambiguation_routing:
  routes_to_this_mode_when:
    - "the question is how the system currently operates (descriptive structural mapping with feedback)"
    - "user wants the layout of stocks, flows, and loops without a specific recurring symptom to diagnose"
    - "feedback dynamics matter to the structure, but the operation is mapping, not causal investigation"
  routes_away_when:
    - "the question is why a recurring symptom persists (causal diagnosis)" → systems-dynamics-causal
    - "no feedback dynamics, just a linear workflow" → process-mapping
    - "static structural relations without temporal dynamics" → relationship-mapping (T11)
    - "specific failure event needing backward causal trace" → root-cause-analysis (T4)
when_not_to_invoke:
  - "User is diagnosing a recurring symptom rather than mapping current operation" → systems-dynamics-causal (T4)
  - "User wants the principle-level explanation of how parts produce behaviour rather than the operational map" → mechanism-understanding (T16)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [system_under_study, system_boundary_hypothesis, mapping_purpose]
    optional: [prior_system_diagrams, stock_inventory, archetype_hypothesis]
    notes: "Applies when user supplies a defined system with explicit boundary and may name a candidate archetype or stocks-and-flows inventory."
  accessible_mode:
    required: [system_description]
    optional: [related_context, mapping_purpose]
    notes: "Default. Mode elicits boundary and mapping purpose during execution."
  detection:
    expert_signals: ["map the structure", "stocks and flows", "feedback structure", "system archetype", "structural diagram", "current-state map"]
    accessible_signals: ["how does this work", "show me the loops", "structural picture"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What system do you want mapped, and what is your purpose for the map (orientation, intervention design, communication)?'"
    on_underspecified: "Ask: 'Are you trying to map how the system currently works (structural), or to diagnose why a recurring symptom persists (causal)? The first invokes Systems Dynamics Structural; the second invokes Systems Dynamics Causal.'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the declared loops genuine cycles in the graph (closing edge present), or are they linear chains mis-labelled as loops?"
    failure_mode_if_unmet: linear-masquerading-as-loop
  - cq_id: CQ2
    question: "Does each loop's declared type (R or B) match its polarity parity (even number of negative edges → R; odd → B)?"
    failure_mode_if_unmet: polarity-parity-mismatch
  - cq_id: CQ3
    question: "Has the system boundary been stated explicitly, or has the map silently absorbed every adjacent variable?"
    failure_mode_if_unmet: boundary-dishonesty
  - cq_id: CQ4
    question: "Does the structural map describe the system as it currently is, or has it drifted into prescriptive recommendations that belong in a different mode?"
    failure_mode_if_unmet: prescriptive-drift
  - cq_id: CQ5
    question: "If a system archetype is named, does its characteristic loop topology actually appear in the declared loops, or is it a name-drop?"
    failure_mode_if_unmet: archetype-name-drop

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: linear-masquerading-as-loop
    detection_signal: "A declared loop's members do not return influence to the start variable along an edge in the graph."
    correction_protocol: re-dispatch (verify closing edge or remove the loop from declarations)
  - name: polarity-parity-mismatch
    detection_signal: "Loop declared as R has odd negative-edge count, or B has even — declared type contradicts parity."
    correction_protocol: flag (mandatory; validator rejects)
  - name: boundary-dishonesty
    detection_signal: "Map omits explicit boundary statement; variables outside the relevant scope absorbed silently."
    correction_protocol: flag
  - name: prescriptive-drift
    detection_signal: "Map drifts from describing what is to recommending what should be — leverage-point recommendations or intervention proposals appear in the structural mapping."
    correction_protocol: re-dispatch (strip prescriptions; route to systems-dynamics-causal if recommendations are wanted)
  - name: archetype-name-drop
    detection_signal: "Archetype named in prose without a matching loop topology in the declared loops."
    correction_protocol: re-dispatch
  - name: everything-connects-holism
    detection_signal: "Unfalsifiable claim that 'everything connects' without specific mechanism per link."
    correction_protocol: re-dispatch
  - name: observer-blindness
    detection_signal: "Map positions analyst and user outside the system when they are part of it."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - feedback-loops
    - senge-system-archetypes
  optional:
    - sterman-system-dynamics-modelling (when quantitative stock-and-flow modelling is in play)
    - forrester-industrial-dynamics (foundational source-tradition lens)
    - meadows-twelve-leverage-points (named for transparency; used only if structural map enables intervention discussion)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Systems Dynamics Structural is the heaviest feedback-aware structural mode in T17."
  sideways:
    target_mode_id: systems-dynamics-causal
    when: "User actually wants to diagnose why a recurring symptom persists — switch from structural to causal posture."
  downward:
    target_mode_id: process-mapping
    when: "On inspection the system has no significant feedback dynamics — a linear process map suffices."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Systems Dynamics Structural is the rigour of current-state articulation: every variable named with its role (stock, flow, auxiliary, exogenous), every loop walked from start to closing edge, polarity verified per edge, type verified against parity, delays marked explicitly, and structural observations stated descriptively (not prescriptively). A thin pass lists variables and asserts loops; a substantive pass distinguishes stocks from flows, walks each loop's closure, identifies which loops dominate behaviour at which timescales, and articulates structural features (e.g., "the system has two reinforcing loops in tension with one balancing loop, with a long delay on the balancing channel") without sliding into intervention recommendations. Test depth by asking: would another analyst reading this map be able to predict the system's behaviour over the next year without further information?

## BREADTH ANALYSIS GUIDANCE

Breadth in Systems Dynamics Structural is the catalog of relevant loops, stocks, and boundary candidates considered before the map is committed. Widen the lens by scanning: which Senge archetypes might describe the structure (Fixes That Fail, Shifting the Burden, Limits to Growth, Eroding Goals, Escalation, Success to the Successful, Tragedy of the Commons, Growth and Underinvestment); which timescales matter (some loops dominate short-term, others long-term); which actors or institutions sit at the boundary and might be drawn inside or kept out. Breadth markers: at least one explicit "outside the boundary" exclusion is named with rationale, and structural observations note which loops dominate at which timescales.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Systems Dynamics Structural is a Forrester/Senge-tradition feedback-system *structural mapping* — descriptive of how the system currently operates, including its stocks, flows, and feedback loops. It is the T17 operation-counterpart to systems-dynamics-causal (T4 causal-investigation posture — same feedback lenses, different operation). The parse-preserving discipline is descriptive-only posture: prescriptive drift (intervention recommendations, leverage-point prescriptions) is reshaped out and routed to systems-dynamics-causal. The mode is distinct from process-mapping (linear/non-feedback workflow), relationship-mapping (T11 static structural relations without temporal dynamics), and mechanism-understanding (T16 principle-level rather than operational map).

**Procedure.**

1. State the system boundary explicitly — what's inside, what's outside, and which excluded variables would change the structural picture if included.
2. Name variables with role tags (`stock` / `flow` / `auxiliary` / `exogenous`); distinguish stocks (accumulate) from flows (alter stock levels per time unit) — stock/flow conflation reshapes here.
3. Declare each feedback loop with id (`R<n>` / `B<n>`), members in order, polarity per edge (`+` / `−`), and the closing edge that returns influence to start.
4. Verify polarity parity per loop — even number of `−` edges → R; odd → B. Declared type contradicting parity is validator-rejected.
5. Mark delays — temporal delay between cause and effect, where operative.
6. Identify Senge archetypes (Fixes That Fail, Shifting the Burden, Limits to Growth, Eroding Goals, Escalation, Success to the Successful, Tragedy of the Commons, Growth and Underinvestment) only with matching loop topology.
7. State structural observations descriptively — which loops dominate at which timescales, where stocks accumulate, where flows are throttled, where the system is in tension with itself.
8. Reshape out prescriptive language ("the system should…", "the leverage point is…") and surface as a sideways-route note to systems-dynamics-causal.
9. State observer position when analyst or user is part of the system being mapped.
10. Assign per-loop and per-stock confidence with boundary caveats — what was deliberately excluded.

**Goal.** Produce a Forrester/Senge descriptive-stance current-state diagram with stocks, flows, polarity-parity-verified loops, archetype identification grounded in matching topology, and structural observations that do not slide into prescription.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — loop genuineness.** Are the declared loops genuine cycles in the graph (closing edge present), or linear chains mis-labelled as loops? Failure mode if unmet: `linear-masquerading-as-loop`.
- **CQ2 — polarity parity matches type.** Does each loop's declared type (R or B) match its polarity parity (even number of negative edges → R; odd → B)? Failure mode if unmet: `polarity-parity-mismatch`.
- **CQ3 — boundary stated.** Has the system boundary been stated explicitly, or has the map silently absorbed every adjacent variable? Failure mode if unmet: `boundary-dishonesty`.
- **CQ4 — descriptive posture maintained.** Does the structural map describe the system as it currently is, or has it drifted into prescriptive recommendations that belong in a different mode? Failure mode if unmet: `prescriptive-drift`.
- **CQ5 — archetype-loop fit.** If a system archetype is named, does its characteristic loop topology actually appear in the declared loops? Failure mode if unmet: `archetype-name-drop`.

A passing output declares the system boundary, distinguishes stocks from flows, names every loop with id pattern R<n>/B<n> and verified polarity parity, marks delays where operative, grounds any named archetype in matching loop topology, and describes the structure without recommending interventions.

**Named failure modes.**

- *linear-masquerading-as-loop* — a declared loop's members do not return influence to the start variable along an edge in the graph.
- *polarity-parity-mismatch* — declared type contradicts negative-edge count (validator-rejected).
- *boundary-dishonesty* — map omits explicit boundary statement; variables outside scope absorbed silently.
- *prescriptive-drift* — map drifts from describing what is to recommending what should be — leverage-point recommendations or intervention proposals appear in the structural mapping. Reshape and route to systems-dynamics-causal.
- *archetype-name-drop* — archetype named in prose without a matching loop topology in the declared loops.
- *everything-connects-holism* — unfalsifiable claim that "everything connects" without specific mechanism per link.
- *observer-blindness* — map positions analyst and user outside the system when they are part of it.

## REVISION GUIDANCE

Revise to add the closing edge (or remove the declaration) for any loop that fails the genuineness check. Revise to fix polarity-parity mismatches before any semantic refinement. Revise to strip prescriptive language that drifted into the map; if the user wants intervention recommendations, route them to `systems-dynamics-causal` rather than retro-fitting them here. Resist the pull toward "what should be done" — the structural map's value is its descriptive fidelity, and prescriptive contamination undermines that.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Forrester/Senge structural-mapping atom set: system-boundary lock, variable-and-stock atoms with role tags (stock / flow / auxiliary / exogenous), feedback-loop atoms with polarity-parity verified, delay atoms, Senge-archetype atoms grounded in matching loop topology, descriptive-only structural-observation atoms, and confidence with boundary caveats**. The atoms are:

1. **System-boundary atom.** What's inside the system, what's outside. The boundary is stated *explicitly*. Boundary-dishonesty is the named failure mode the consolidator watches for; silent absorption of adjacent variables gets reshaped. Everything-connects-holism is the mirror failure mode; the corpus surfaces specific mechanisms per link.

2. **Variable-and-stock atoms.** Each atom names: one variable, its role tag (`stock` / `flow` / `auxiliary` / `exogenous`), a short label, and a unit of change. Stocks vs. flows are distinguished — stocks accumulate, flows alter stock levels per time unit.

3. **Feedback-loop atoms with polarity-parity verification.** Each atom carries: loop id (`R<n>` / `B<n>`), type (`R` / `B`), members in order, edge polarities, and the parity check (even `−` count → R; odd → B). Linear-masquerading-as-loop and polarity-parity-mismatch are the named failure modes; declared loops without closing edges or with mismatched type-parity get reshaped.

4. **Delay atoms.** Each atom marks an edge or loop where temporal delay between cause and effect is operative. Delays are surfaced rather than smoothed.

5. **Senge-archetype atoms — when applicable.** Each atom names: an archetype plus the matching loop topology in the declared loops. Archetype-name-drop is the named failure mode.

6. **Structural-observation atoms — descriptive only.** Each atom states a structural feature of the system as-it-is: which loops dominate at which timescales, where stocks accumulate, where flows are throttled, where the system is in tension with itself. Prescriptive-drift is the named failure mode; intervention recommendations or leverage-point prescriptions get reshaped out of the structural mapping (and routed to systems-dynamics-causal if the user wants them).

7. **Observer-position atom — when applicable.** When the analyst or user is part of the system being mapped, the observer-position is stated. Observer-blindness is the named failure mode.

8. **Confidence and boundary-caveat atoms.** Confidence per major loop and per stock identification; boundary caveats name what was deliberately excluded.

**Mode-specific bloat patterns to cut:**

- **Linear-masquerading-as-loop** — declared loop without closing edge.
- **Polarity-parity mismatch** — declared type contradicts negative-edge count.
- **Boundary dishonesty** — silent absorption of adjacent variables.
- **Prescriptive drift** — recommendations or interventions appearing in the structural map (route to systems-dynamics-causal for those).
- **Archetype name-drop** — Senge archetype invoked without matching topology.
- **Everything-connects holism** — unfalsifiable "everything is connected" without per-link mechanism.
- **Observer blindness** — analyst/user positioned outside a system they're part of.
- **Stock/flow conflation** — variables tagged without distinguishing accumulation from rate-of-change.

**What NOT to collapse:**

- **Descriptive posture** — the mode's identity is mapping what is, not recommending what should be. Prescriptive drift is the parse-preserving discipline that distinguishes this mode from systems-dynamics-causal.
- **Closing edges** — verified explicitly per loop.
- **Stock-vs-flow distinction** — preserved; collapsing both into "variables" loses the structural distinction.
- **Multiple operative loops at the same time** — multiple loops can dominate at different timescales; the corpus preserves the timescale-stratified picture.

## VERIFICATION CRITERIA

Verified means: system boundary is stated; every loop's members close back to start along declared edges; every loop's declared type matches negative-edge parity; at least one delay is marked (when present); archetype names (if any) correspond to matching loop topology; structural observations describe what is without recommending what should be. Confidence is stated for each major loop (high if both depth and breadth analyses converged on type and polarity; lower otherwise).

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structural feedback-system mapping** — a Forrester/Senge descriptive-stance current-state diagram with stocks, flows, polarity-parity-verified loops, archetype identification, and structural observations that do not slide into prescription. Place the consolidated-corpus atoms into the following sections, in this order:

1. **System boundary.** One paragraph stating what's inside and what's outside. `**Inside:** [variables in scope]. **Outside (deliberately excluded):** [variables whose inclusion would change the structural picture, with reason for exclusion].`

2. **Variables and stocks.** A table or labelled list. Each: `**[Variable]** — role: [stock / flow / auxiliary / exogenous]. Unit: [...]. Short label: [...]. Note on accumulation (for stocks) or rate (for flows): [...].`

3. **Feedback loops with polarity.** Per loop, a labelled block: `**Loop [R1 / R2 / B1 / B2 ...]:** Type: [R / B]. Members in order: [V1 → V2 → ... → V1]. Edge polarities: [+/− per edge]. Polarity-parity check: [even − count → R; odd → B; matches declared type]. Behaviour-grounded label: [what this loop produces].`

4. **Delays.** Bulleted list. Each: `**[Edge or loop]** — delay magnitude: [...]. Structural implication: [how the delay shapes system behaviour].`

5. **System archetypes present.** Bulleted list. Each: `**[Archetype]** — matching loop topology: [which declared loops instantiate the archetype]. Behaviour pattern: [what the structure typically produces].` Name-drops without topology are reshaped.

6. **Structural observations.** Bulleted list. Each: `**[Observation about the system as-it-is]** — grounded in: [which loops, stocks, delays]. Timescale at which this observation is operative: [...].` This section is *descriptive only*. Intervention recommendations are reshaped out and surfaced as a sideways-route note.

7. **Confidence and boundary caveats.** Bulleted list of per-loop / per-stock confidence with grounding, plus boundary caveats naming what was deliberately excluded.

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- Loop ids follow the `R<n>` / `B<n>` pattern verbatim.
- Stock vs. flow distinction is operative in section 2; collapsed labels are reshaped.
- Polarity-parity verification is *explicit* per loop in section 3.
- Senge archetype vocabulary appears verbatim with matching topology required.
- Structural observations (section 6) are *descriptive*. Prescriptive language ("the system should...", "the leverage point is...") gets reshaped out and surfaced separately: `**Note: prescriptive recommendations are not part of this mode's contract. If intervention design is wanted, systems-dynamics-causal (T4) is the appropriate sideways-route.**`
- When the observer-blindness flag survived consolidation, section 1 closes with: `**Observer-position note:** the analyst / user is part of this system; their position is itself a structural feature.`
- Format is *diagram-friendly* — the visual is the structural argument. When a stock-and-flow envelope or CLD is appropriate, it appears as the centrepiece of section 3.
- The mode's parse-preserving discipline (descriptive, not prescriptive) is enforced throughout. Drift toward causal/recommendation framing is what makes the mode collapse back into systems-dynamics-causal.

## CAVEATS AND OPEN DEBATES

This mode is one of two parsed from the legacy Systems Dynamics mode per Decision D (parsing principle, 2026-05-01 architecture lock). The legacy mode conflated two distinct operations: causal investigation ("why does this keep happening, given the feedback dynamics?") and structural mapping ("how does this system currently work, including its feedback dynamics?"). Both share the same feedback-loop lenses and the same diagrammatic vocabulary, but they differ in posture (causal-investigation vs structural-descriptive), output contract (counterintuitive-behaviour prediction vs current-state mapping), and disambiguation question (why vs how). This mode is the T17 structural variant; its causal counterpart `systems-dynamics-causal` lives in T4 and shares the foundational feedback lenses including `feedback-loops`. Routing between the two is determined by the user's actual question — current-state mapping (how) routes here; diagnostic recurrence (why) routes to the causal variant. The maintenance of strict descriptive posture in this mode (no prescriptive drift) is what preserves the parse: it is what makes structural mapping a distinct operation from causal investigation, even when the diagrammatic output looks superficially similar.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~10min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `parent`, `child`, `produces`, `enables`, `requires`
**Deprioritize:** `contradicts`, `supersedes`

*Family: mechanism-structure. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
