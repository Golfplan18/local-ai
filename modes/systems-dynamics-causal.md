---
nexus:
  - ora
type: mode
tags:
  - framework/instruction
  - architecture
date created: 2026-05-01
date modified: 2026-05-01

---

# MODE: Systems Dynamics Causal

```yaml
# 0. IDENTITY
mode_id: systems-dynamics-causal
canonical_name: Systems Dynamics Causal
suffix_rule: analysis
educational_name: feedback-system causal analysis (Forrester/Senge lineage)

# 1. TERRITORY AND POSITION
territory: T4-causal-investigation
gradation_position:
  axis: complexity
  value: feedback-structure
adjacent_modes_in_territory:
  - mode_id: root-cause-analysis
    relationship: complexity-lighter sibling (single-cause-chain)
  - mode_id: causal-dag
    relationship: depth-thorough sibling (formalism-explicit, Pearl)
  - mode_id: process-tracing
    relationship: specificity-historical-event sibling (Bennett/Checkel)
  - mode_id: systems-dynamics-structural
    relationship: operation-counterpart (T17 home; structural-descriptive posture; same feedback lenses, different operation)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "this keeps happening despite our attempts to fix it"
    - "fixing X seems to make Y worse"
    - "interventions produce counterintuitive results"
    - "delays between action and effect are confusing the picture"
  prompt_shape_signals:
    - "why does this keep happening with feedback dynamics"
    - "what are the leverage points"
    - "fixes that fail"
    - "draw the feedback structure (causal)"
    - "diagnose the recurring behaviour"
disambiguation_routing:
  routes_to_this_mode_when:
    - "ongoing counterintuitive behaviour driven by loops — user wants causal diagnosis"
    - "the question is why this keeps happening (causal investigation), not how the system currently works (structural mapping)"
    - "want feedback dynamics analysis specifically, not a single-chain trace"
  routes_away_when:
    - "single failure event, no declared feedback loops" → root-cause-analysis
    - "the question is how the system currently works, not why a problem recurs" → systems-dynamics-structural
    - "static structural relations without temporal dynamics" → relationship-mapping (T11)
    - "want formal DAG with conditional-independence reasoning" → causal-dag
    - "specific historical event needing trace evidence" → process-tracing
when_not_to_invoke:
  - "User is mapping a workflow's current operation rather than diagnosing recurring symptoms" → T17 (systems-dynamics-structural or process-mapping)
  - "User has a one-off failure with no recurrence pattern" → root-cause-analysis

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [recurring_symptom, attempted_interventions, system_boundary_hypothesis]
    optional: [prior_loop_articulations, archetype_hypothesis, stock_inventory]
    notes: "Applies when user supplies recurring-symptom history with intervention attempts and may name a candidate archetype or boundary."
  accessible_mode:
    required: [recurring_symptom_description]
    optional: [intervention_history, related_context]
    notes: "Default. Mode elicits boundary and intervention history during execution."
  detection:
    expert_signals: ["fixes that fail", "shifting the burden", "limits to growth", "system archetype", "Meadows leverage", "stock and flow"]
    accessible_signals: ["this keeps happening", "fixing X makes Y worse", "delayed effect", "counterintuitive"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What pattern do you keep seeing recur, and what have you tried that didn't fix it (or made it worse)?'"
    on_underspecified: "Ask: 'Are you trying to diagnose why this keeps happening (causal), or to map how the system currently works (structural)? The first invokes Systems Dynamics Causal; the second invokes Systems Dynamics Structural.'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the declared loops genuine cycles in the graph (closing edge present), or are they linear chains mis-labelled as loops?"
    failure_mode_if_unmet: linear-masquerading-as-loop
  - cq_id: CQ2
    question: "Does each loop's declared type (R or B) match its polarity parity (even number of negative edges → R; odd → B)?"
    failure_mode_if_unmet: polarity-parity-mismatch
  - cq_id: CQ3
    question: "Has the system boundary been stated explicitly, or has the analysis silently expanded to absorb every adjacent variable?"
    failure_mode_if_unmet: boundary-dishonesty
  - cq_id: CQ4
    question: "If a system archetype is named, does its characteristic loop topology actually appear in the declared loops, or is it a name-drop?"
    failure_mode_if_unmet: archetype-name-drop
  - cq_id: CQ5
    question: "Are leverage points ranked by Meadows depth with reasoning, or is the recommendation a parameter tweak presented as systemic intervention?"
    failure_mode_if_unmet: deep-leverage-omission

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: linear-masquerading-as-loop
    detection_signal: "A declared loop's members do not return influence to the start variable along an edge in the graph."
    correction_protocol: re-dispatch (verify closing edge or remove the loop from declarations)
  - name: polarity-parity-mismatch
    detection_signal: "Loop declared as R has odd negative-edge count, or B has even — declared type contradicts parity."
    correction_protocol: flag (mandatory; validator rejects)
  - name: boundary-dishonesty
    detection_signal: "Analysis omits explicit boundary statement; variables outside the relevant scope are absorbed silently."
    correction_protocol: flag
  - name: archetype-name-drop
    detection_signal: "Archetype named in prose without a matching loop topology in the declared loops."
    correction_protocol: re-dispatch (either remove the archetype or add the matching loop)
  - name: deep-leverage-omission
    detection_signal: "Leverage recommendations sit only at parameter-adjustment depth (Meadows 1-3) when structural depth is available."
    correction_protocol: flag
  - name: everything-connects-holism
    detection_signal: "Unfalsifiable claim that 'everything connects' without specific mechanism per link."
    correction_protocol: re-dispatch (add boundary statement and per-link mechanisms)
  - name: observer-blindness
    detection_signal: "Analyst and user are positioned outside the system being analysed when they are part of it."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - feedback-loops
    - meadows-twelve-leverage-points
  optional:
    - senge-system-archetypes (when archetype identification clarifies behaviour)
    - sterman-system-dynamics-modelling (when quantitative stock-and-flow modelling is in play)
    - forrester-industrial-dynamics (foundational source-tradition lens)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: causal-dag
    when: "Causal structure is sufficiently formalisable that conditional-independence reasoning would clarify; user wants a Pearl-style DAG."
  sideways:
    target_mode_id: systems-dynamics-structural
    when: "User's actual question is how the system currently operates rather than why a recurring symptom persists — switch from causal to structural posture."
  downward:
    target_mode_id: root-cause-analysis
    when: "Recurring symptom turns out to be a single-event failure with a tractable backward chain rather than a feedback-driven pattern."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Systems Dynamics Causal is the rigour of feedback-structure articulation: every loop named with its members in order, polarity declared per edge, type (R or B) verified against parity, delays marked explicitly, and at least one counterintuitive behaviour predicted from the structure. A thin pass names variables and asserts loops without verifying closure; a substantive pass walks each loop from start to closing edge, counts negative edges to confirm type, distinguishes the dominant loop driving the recurring symptom from secondary loops, and grounds at least one Senge archetype in matching loop topology. Test depth by asking: does the analysis predict the system's response to a specific intervention before that intervention is tried?

## BREADTH ANALYSIS GUIDANCE

Breadth in Systems Dynamics Causal is the catalog of loops considered before the dominant loop is committed and the leverage-point candidates considered before the recommendation is committed. Widen the lens by scanning: which Senge archetypes might fit (Fixes That Fail, Shifting the Burden, Limits to Growth, Eroding Goals, Escalation, Success to the Successful, Tragedy of the Commons, Growth and Underinvestment); which delays may be hiding causal links across timescales; which variables outside the current boundary would change the dominant-loop story if included. Breadth markers: at least one explicit "outside the boundary" exclusion is named, and leverage points span multiple Meadows depths (not all depth 1-3 parameter tweaks).

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) loop genuineness with closing edge; (CQ2) polarity parity matches declared type; (CQ3) boundary stated explicitly; (CQ4) archetype-loop fit when archetype named; (CQ5) Meadows-ranked leverage points. The named failure modes are the evaluation checklist. A passing Systems Dynamics Causal output declares its boundary, names every loop with id pattern R<n>/B<n>, verifies polarity parity, predicts at least one counterintuitive behaviour, and ranks leverage points by Meadows depth with reasoning.

## REVISION GUIDANCE

Revise to add the closing edge (or remove the declaration) for any loop that fails the genuineness check. Revise to fix polarity-parity mismatches before any semantic refinement — these are validator-rejected. Revise to add the boundary statement when missing; silent boundary expansion produces false leverage. Resist revising toward a "complete" map by adding every adjacent variable — the boundary is the analytical contract, and dishonesty about it is a structural failure, not a polish opportunity.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Forrester/Senge causal feedback-system atom set: system-boundary lock, variable atoms with short labels, feedback-loop atoms with polarity-parity verified (R/B), delay atoms, Senge archetype atoms grounded in matching loop topology, Meadows-depth-ranked leverage-point atoms, counterintuitive-behaviour-prediction atoms, and confidence with boundary caveats**. The atoms are:

1. **System-boundary atom.** What's inside the system, what's outside. The boundary is stated *explicitly*. Boundary-dishonesty is the named failure mode the consolidator watches for; analyses that silently absorb every adjacent variable get reshaped to explicit boundary declaration. Everything-connects-holism is the named failure mode for the opposite drift; "everything connects" without specific mechanism per link gets reshaped.

2. **Variable atoms.** Each atom names: one variable with a short label, its kind (stock / flow / auxiliary), and unit of change. Variables outside the declared boundary are excluded with explicit rationale.

3. **Feedback-loop atoms with polarity-parity verification.** Each atom carries: a loop id (`R1`, `R2`, `B1`, `B2` …), a type (`R` — reinforcing / `B` — balancing), the loop's members in order, the polarity of each edge (`+` / `−`), and a polarity-parity check (even number of `−` edges → R; odd → B). Linear-masquerading-as-loop is the named failure mode; declared loops where the closing edge is missing get reshaped (verify or remove). Polarity-parity-mismatch is the named failure mode; loop declared R with odd `−` count, or B with even, gets reshaped — the validator rejects mismatches.

4. **Delay atoms.** Each atom marks an edge or loop where delay between cause and effect is operative. At least one delay surfaces (delays are pervasive in feedback systems; absence is suspicious).

5. **Senge-archetype atoms — when applicable.** Each atom names: an archetype (`Fixes That Fail` / `Shifting the Burden` / `Limits to Growth` / `Eroding Goals` / `Escalation` / `Success to the Successful` / `Tragedy of the Commons` / `Growth and Underinvestment`) and the matching loop topology in the declared loops. Archetype-name-drop is the named failure mode; archetypes named without matching topology get reshaped or removed.

6. **Meadows-depth leverage-point atoms.** Each atom names: a leverage point with explicit Meadows depth (12: constants / parameters / numbers; 11: buffer sizes; 10: stock-and-flow structures; 9: delays; 8: balancing-loop strength; 7: reinforcing-loop gain; 6: information flows; 5: rules; 4: self-organisation; 3: goals; 2: paradigm; 1: power to transcend paradigms). Deep-leverage-omission is the named failure mode; recommendations limited to depths 12–10 (parameter tweaks) when deeper leverage is available get reshaped.

7. **Counterintuitive-behaviour atoms.** Each atom predicts: a non-obvious behaviour of the system (fixes that fail; intervention worsens symptom; delayed feedback masks cause), grounded in the declared loop structure. At least one counterintuitive behaviour appears.

8. **Observer-position atom — when applicable.** When the analyst or user is part of the system being analysed (a workplace, an interpersonal pattern, a research community), the observer-position is stated. Observer-blindness is the named failure mode.

9. **Confidence and boundary-caveat atoms.** Confidence per major loop (high if depth and breadth converged on type and polarity; lower otherwise); boundary caveats name what was deliberately excluded.

**Mode-specific bloat patterns to cut:**

- **Linear-masquerading-as-loop** — declared loop without a closing edge in the graph.
- **Polarity-parity mismatch** — declared type contradicts negative-edge count.
- **Boundary dishonesty** — silent absorption of adjacent variables.
- **Everything-connects holism** — unfalsifiable "everything is connected" without per-link mechanism.
- **Archetype name-drop** — Senge archetype invoked without matching loop topology.
- **Deep-leverage omission** — leverage points only at parameter-tweak depth when structural depth is available.
- **Observer blindness** — analyst/user positioned outside a system they're part of.
- **Map-as-summary drift** — the visual treated as decoration rather than as the structural argument.

**What NOT to collapse:**

- **Closing edges** — verified explicitly per declared loop; never elided.
- **Polarity per edge** — every edge carries `+` or `−`; unmarked edges get reshaped.
- **Stream disagreement about archetype** — when streams identified different archetypes in the same structure, both survive with their respective topology-matches.
- **Boundary exclusions** — what was kept outside is part of the analytical contract.
- **Loops at the same level** — multiple loops can be operative simultaneously (the dominant loop plus secondary loops); the corpus does not collapse to one.

## VERIFICATION CRITERIA

Verified means: system boundary is stated; every loop's members close back to start along declared edges; every loop's declared type matches negative-edge parity; at least one delay is marked; archetype names (if any) correspond to matching loop topology; leverage points carry Meadows depth labels; at least one counterintuitive behaviour is predicted from the structure. Confidence is stated for each major loop (high if both depth and breadth analyses converged on type and polarity; lower otherwise).

## OUTPUT FORMAT GUIDANCE

The deliverable is a **causal feedback-system mapping** — a Forrester/Senge structured analysis where every loop is closed and polarity-parity-verified, archetype names match loop topology, leverage points are ranked by Meadows depth, and at least one counterintuitive behaviour is predicted from the structure. Place the consolidated-corpus atoms into the following sections, in this order:

1. **System boundary.** One paragraph stating what's inside and what's outside. `**Inside:** [the variables in scope]. **Outside (deliberately excluded):** [variables whose inclusion would change the dominant-loop story, with reason for exclusion].`

2. **Variables.** Bulleted list. Each: `**[Variable]** — kind: [stock / flow / auxiliary]. Unit: [...]. Short label: [...].`

3. **Feedback loops with polarity.** A labelled block per loop. Each: `**Loop [R1 / R2 / B1 / B2 ...]:** Type: [R / B]. Members in order: [V1 → V2 → ... → V1]. Edge polarities: [+/− per edge]. Polarity-parity check: [even − count → R; odd → B; matches/mismatches declared type]. Behaviour-grounded label: [what this loop produces in observable terms].`

4. **Delays.** Bulleted list. Each: `**[Edge or loop]** — delay magnitude: [seconds / hours / days / quarters / years / generations]. Implication: [how the delay produces counterintuitive behaviour].`

5. **System archetypes.** Bulleted list. Each: `**[Archetype name — Fixes That Fail / Shifting the Burden / Limits to Growth / Eroding Goals / Escalation / Success to the Successful / Tragedy of the Commons / Growth and Underinvestment]** — matching loop topology: [which declared loops instantiate the archetype]. Behaviour predicted: [...].` Archetype name-drops without matching topology are reshaped at this layer.

6. **Leverage points — Meadows-ranked.** Numbered list, **deepest first**. Each: `[N]. **[Leverage point]** — Meadows depth: [12 / 11 / 10 / 9 / 8 / 7 / 6 / 5 / 4 / 3 / 2 / 1]. Description: [...]. Why this depth: [...]. Expected effect on the dominant loop: [...].`

7. **Counterintuitive behaviours.** Bulleted list. Each: `**[Predicted counterintuitive behaviour]** — grounded in loops: [which loops produce this]. Observable signal: [what the user would see if this prediction holds].`

8. **Confidence and boundary caveats.** Bulleted list. Each: `**[Loop / leverage point / archetype]** — confidence: [high / medium / low]. Basis: [convergence across analyses / single-stream / contested]. Boundary caveat: [variables outside the declared boundary whose inclusion would change this finding].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- Loop ids follow the `R<n>` / `B<n>` pattern verbatim.
- Polarity-parity verification is *explicit* per loop — the count of `−` edges and the implied type appear in the loop's labelled block.
- Senge archetype vocabulary appears verbatim with matching loop topology required. Name-drops without topology are reshaped.
- Meadows depth labels (1–12) appear verbatim per leverage point; the depth distinction is operative, not decorative.
- Format is *diagram-friendly* — the visual is the structural argument. When a CLD or stock-and-flow envelope is appropriate, it is rendered as the centrepiece of section 3, not as a summary of the prose.
- When the observer-blindness flag survived consolidation, section 1 closes with: `**Observer-position note:** the analyst / user is part of this system; their behaviour is itself a variable in [Loop X]. The analysis below accounts for this rather than positioning the observer outside.`
- When the question is actually "how does this system currently work" (not "why does it keep happening"), the deliverable opens with a sideways-route note: `**Note: if the question is how the system currently operates rather than why a recurring symptom persists, systems-dynamics-structural (T17) is the appropriate sideways-route. The current deliverable carries causal-investigation posture.**`

## CAVEATS AND OPEN DEBATES

This mode is one of two parsed from the legacy Systems Dynamics mode per Decision D (parsing principle, 2026-05-01 architecture lock). The legacy mode conflated two distinct operations: causal investigation ("why does this keep happening, given the feedback dynamics?") and structural mapping ("how does this system currently work, including its feedback dynamics?"). Both share the same feedback-loop lenses and the same diagrammatic vocabulary, but they differ in posture (causal-investigation vs structural-descriptive), output contract (counterintuitive-behaviour prediction vs current-state mapping), and disambiguation question (why vs how). This mode is the T4 causal variant; its structural counterpart `systems-dynamics-structural` lives in T17 and shares the foundational feedback lenses including `feedback-loops`. Routing between the two is determined by the user's actual question — diagnostic recurrence (why) routes here; current-state mapping (how) routes to the structural variant.


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

**Prioritize:** `precedes`, `enables`, `requires`, `produces`, `derived-from`
**Deprioritize:** `analogous-to`, `parent`

*Family: causal. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
