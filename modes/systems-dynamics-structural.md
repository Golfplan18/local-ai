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
output_contract:
  artifact_type: mapping
  required_sections:
    - system_boundary
    - variables_and_stocks
    - feedback_loops_with_polarity
    - delays
    - system_archetypes_present
    - structural_observations
    - confidence_and_boundary_caveats
  format: diagram-friendly

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

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) loop genuineness with closing edge; (CQ2) polarity parity matches declared type; (CQ3) boundary stated explicitly; (CQ4) descriptive (not prescriptive) posture maintained; (CQ5) archetype-loop fit when archetype named. The named failure modes are the evaluation checklist. A passing Systems Dynamics Structural output declares its boundary, names every loop with id pattern R<n>/B<n>, verifies polarity parity, describes the structure without recommending interventions, and grounds any named archetype in matching loop topology.

## REVISION GUIDANCE

Revise to add the closing edge (or remove the declaration) for any loop that fails the genuineness check. Revise to fix polarity-parity mismatches before any semantic refinement. Revise to strip prescriptive language that drifted into the map; if the user wants intervention recommendations, route them to `systems-dynamics-causal` rather than retro-fitting them here. Resist the pull toward "what should be done" — the structural map's value is its descriptive fidelity, and prescriptive contamination undermines that.

## CONSOLIDATION GUIDANCE

Consolidate as a structured mapping with the seven required sections in order: system boundary; variables and stocks (named with short labels and roles); feedback loops with polarity (each with id, type, members in order, behaviour-grounded label); delays; system archetypes present (with matching loop topology); structural observations (descriptive, not prescriptive); confidence and boundary caveats. Format: diagram-friendly. The visual is the structural argument, not a summary of it.

## VERIFICATION CRITERIA

Verified means: system boundary is stated; every loop's members close back to start along declared edges; every loop's declared type matches negative-edge parity; at least one delay is marked (when present); archetype names (if any) correspond to matching loop topology; structural observations describe what is without recommending what should be. Confidence is stated for each major loop (high if both depth and breadth analyses converged on type and polarity; lower otherwise).

## CAVEATS AND OPEN DEBATES

This mode is one of two parsed from the legacy Systems Dynamics mode per Decision D (parsing principle, 2026-05-01 architecture lock). The legacy mode conflated two distinct operations: causal investigation ("why does this keep happening, given the feedback dynamics?") and structural mapping ("how does this system currently work, including its feedback dynamics?"). Both share the same feedback-loop lenses and the same diagrammatic vocabulary, but they differ in posture (causal-investigation vs structural-descriptive), output contract (counterintuitive-behaviour prediction vs current-state mapping), and disambiguation question (why vs how). This mode is the T17 structural variant; its causal counterpart `systems-dynamics-causal` lives in T4 and shares the foundational feedback lenses including `feedback-loops`. Routing between the two is determined by the user's actual question — current-state mapping (how) routes here; diagnostic recurrence (why) routes to the causal variant. The maintenance of strict descriptive posture in this mode (no prescriptive drift) is what preserves the parse: it is what makes structural mapping a distinct operation from causal investigation, even when the diagrammatic output looks superficially similar.
