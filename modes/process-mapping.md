---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01

---

# MODE: Process Mapping

```yaml
# 0. IDENTITY
mode_id: process-mapping
canonical_name: Process Mapping
suffix_rule: analysis
educational_name: process mapping (workflow / dependency / bottleneck identification)

# 1. TERRITORY AND POSITION
territory: T17-process-and-system-analysis
gradation_position:
  axis: specificity
  value: process-flow
  secondary_axis: complexity
  secondary_value: single-process
adjacent_modes_in_territory:
  - mode_id: systems-dynamics-structural
    relationship: complexity-counterpart (feedback structure rather than linear-process flow)
  - mode_id: organizational-structure
    relationship: specificity-counterpart (organizational rather than process-flow; gap-deferred)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I need to map out how this process actually works step by step"
    - "I want to find the bottlenecks in this workflow"
    - "I need to see the dependencies between steps"
    - "I want to document the current state before changing anything"
    - "I need to identify where things slow down or break"
  prompt_shape_signals:
    - "process map"
    - "workflow"
    - "swim lane"
    - "value stream"
    - "bottleneck"
    - "dependency"
    - "flow chart"
    - "current state"
    - "as-is process"
    - "step by step how does this work"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants step-by-step documentation of how a current process works"
    - "user wants explicit identification of bottlenecks, dependencies, and decision points"
    - "user wants current-state ('as-is') mapping rather than future-state design"
    - "process is largely linear or branching but not characterized by feedback loops"
  routes_away_when:
    - "system has feedback loops where outputs influence inputs cyclically" → systems-dynamics-structural
    - "question is why a particular outcome happened" → T4 causal modes
    - "question is how the parts produce the whole's behavior at the principle level" → mechanism-understanding (T16)
    - "question is about who has what role and authority" → organizational-structure (gap-deferred)
when_not_to_invoke:
  - "User wants to design a future state rather than document the current state" → execution-tier (T21) or future-mode (T6)
  - "User wants to evaluate the process as a proposal" → T15 stance modes
  - "User wants causal-chain analysis of an outcome" → T4 modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [process_name_or_scope, process_boundaries, known_actors_or_roles]
    optional: [existing_documentation, known_pain_points, prior_process_maps]
    notes: "Applies when user supplies a scoped process with explicit start-and-end conditions and named actors."
  accessible_mode:
    required: [process_description]
    optional: [why_user_wants_map, recent_problems_with_process]
    notes: "Default. Mode elicits boundaries, actors, and pain points during execution."
  detection:
    expert_signals: ["swim lane", "value stream", "as-is process", "RACI", "process boundaries"]
    accessible_signals: ["how does this work", "step by step", "where does it slow down", "map out the workflow"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What process are you mapping, where does it start, and where does it end?'"
    on_underspecified: "Ask: 'What triggers the process to begin, and how do you know when it's complete?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have the process boundaries been locked (clear start trigger and end condition), or is the scope ambiguous?"
    failure_mode_if_unmet: scope-creep
  - cq_id: CQ2
    question: "Has the analysis distinguished between the documented (official) process and the actual (lived) process, or has it described only one as if it were both?"
    failure_mode_if_unmet: official-vs-actual-elision
  - cq_id: CQ3
    question: "Have decision points and branching paths been identified with explicit decision criteria, or has the process been flattened into a single happy path?"
    failure_mode_if_unmet: happy-path-flattening
  - cq_id: CQ4
    question: "Have bottlenecks been identified with the constraint that creates them named, rather than just the symptom?"
    failure_mode_if_unmet: bottleneck-symptom-only
  - cq_id: CQ5
    question: "Have handoffs between actors been examined for friction and information loss, or treated as frictionless?"
    failure_mode_if_unmet: handoff-blindness

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: scope-creep
    detection_signal: "Process boundaries shifted during execution; map covers more than the locked scope."
    correction_protocol: re-dispatch
  - name: official-vs-actual-elision
    detection_signal: "Map describes the process as documented in policy without acknowledging known deviations or workarounds."
    correction_protocol: flag
  - name: happy-path-flattening
    detection_signal: "All branching paths collapsed to one main flow; exception paths absent."
    correction_protocol: re-dispatch
  - name: bottleneck-symptom-only
    detection_signal: "Bottleneck named (e.g., 'approval takes too long') without the underlying constraint identified (e.g., 'single approver, no delegation')."
    correction_protocol: flag
  - name: handoff-blindness
    detection_signal: "Handoffs between actors presented without examining where information is lost, transformed, or queued."
    correction_protocol: flag
  - name: causal-overreach
    detection_signal: "Process map presented as causal explanation of why outcomes occur; mode boundary violation into T4."
    correction_protocol: escalate

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - meadows-twelve-leverage-points (when bottleneck-as-leverage-point analysis is central)
    - senge-system-archetypes (when process exhibits archetype-pattern signatures)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: systems-dynamics-structural
    when: "Process exhibits feedback loops where outputs cyclically influence inputs; linear-flow mapping insufficient."
  sideways:
    target_mode_id: null
    when: "Sibling specificity-organizational mode (organizational-structure) gap-deferred per CR-6."
  downward:
    target_mode_id: null
    when: "Process Mapping is the lightest specificity-process-flow mode in T17 at current population."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Process Mapping is the explicitness of (a) actor-and-role attribution per step (who does what), (b) decision-point criteria (what triggers each branch), (c) dependency relationships between steps (what blocks what), and (d) bottleneck constraint-identification (not just where it slows but why it slows). A thin pass lists the steps; a substantive pass attributes each step to an actor, identifies decision-point criteria explicitly, maps step-to-step dependencies, and names the underlying constraint at each bottleneck (capacity / authority / information / sequencing). Test depth by asking: could a new actor entering the process at any step understand from the map alone what they need, who they wait for, and what unblocks them?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for exception paths and edge cases (what happens when the input is malformed, when an actor is absent, when a dependency is unavailable), surfacing the gap between documented and actual process flow, and identifying handoff friction (information loss, role-confusion, queue accumulation) at every actor boundary. Breadth markers: the map shows at least one exception path explicitly, surfaces at least one official-vs-actual deviation, and flags handoffs as friction zones rather than treating them as transparent.

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) boundary lock; (CQ2) official-vs-actual distinction; (CQ3) decision-point and branch surfacing; (CQ4) bottleneck constraint-identification; (CQ5) handoff examination. The named failure modes (scope-creep, official-vs-actual-elision, happy-path-flattening, bottleneck-symptom-only, handoff-blindness, causal-overreach) are the evaluation checklist. A passing Process Mapping output locks scope, distinguishes documented from actual flow, surfaces decision points and branches with criteria, identifies bottlenecks with underlying constraints named, and examines handoffs for friction.

## REVISION GUIDANCE

Revise to add exception paths where the draft shows only the happy path. Revise to surface official-vs-actual deviations where the draft conflates them. Revise to identify the constraint underlying each bottleneck where the draft names only the symptom. Revise to examine handoffs as friction zones where the draft treats them as transparent. Resist revising toward causal explanation of outcomes — the mode's analytical character is descriptive process documentation. If the user wants causal analysis of why the process produces particular outcomes, escalate to T4 causal modes rather than overreaching the mapping.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a directed step-graph with actor swim-lanes, decision-point branches, bottleneck atoms (named with underlying constraints), and handoff-friction atoms**. The step graph is the load-bearing structure; actor attribution per step, constraint-typed bottlenecks, and explicit handoff-friction are the discipline. The atoms are:

1. **Scope-and-boundaries atom.** Process name, start-trigger, and end-condition stated once at the corpus head. Scope-creep is the named failure mode; the locked boundaries appear once and govern what survives into the step graph.

2. **Actor/role inventory atoms.** Each actor or role carries: name, scope of responsibility, and steps they perform. Actor atoms are cross-referenced by step atoms; orphan actors (named but doing no step in the map) are flagged as scope-creep residue or pending-clarification atoms.

3. **Step atoms.** Each step carries: step content, actor attribution (which role performs it), predecessor steps (what must complete first), successor steps, and lane assignment (when swim-lane format applies). Steps without actor attribution are component-inventory-without-function-equivalent residue — they do not survive as steps without a who.

4. **Decision-point atoms.** Each decision point carries: triggering condition, explicit decision criteria (not "depending on the situation"), and the branches it spawns with the predicate that routes to each. Happy-path-flattening is the named failure mode; a process with no decision-point atoms when branches actually exist is its corpus signature. At least one decision-point atom must survive when the process has any branching at all.

5. **Exception-path atoms.** Each names an exception case (malformed input, absent actor, unavailable dependency) and the alternative path taken. The breadth marker is at least one exception-path atom surviving; happy-path-only is happy-path-flattening residue.

6. **Dependency-map atoms.** Each is a "step A blocks step B" assertion, with the resource or precondition that creates the dependency. The dependency map is suitable for DAG rendering downstream; cycles are forbidden (process-mapping is acyclic by territory — feedback loops escalate to systems-dynamics-structural).

7. **Bottleneck atoms.** Each bottleneck carries: location (which step or handoff), symptom (what the user observes — "approval takes too long"), and **underlying constraint typed** as capacity / authority / information / sequencing (the actual mechanism creating the slow-down — "single approver with no delegation authority and full inbox"). Bottleneck-symptom-only is the named failure mode; an atom with symptom but no constraint-type does not survive as a bottleneck — it's either a pending-investigation atom or it's not a bottleneck.

8. **Handoff-friction atoms.** Each handoff between actors carries: source actor, target actor, what is transferred, friction type (information-loss / role-confusion / queue-accumulation / context-collapse), and the cost the friction imposes. Handoff-blindness is the named failure mode; handoffs treated as transparent are its corpus signature. At least one handoff-friction atom must survive when more than one actor participates in the process.

9. **Official-vs-actual divergence atoms.** Each names a step or handoff where the documented (official) process differs from the lived (actual) process, with the deviation and any workaround. Official-vs-actual-elision is the failure mode; a corpus that describes only one as if it were both is its signature. When neither divergence nor explicit alignment-confirmation is present, the corpus carries an explicit "official-vs-actual: not investigated in this pass" atom rather than silently defaulting to the official version.

10. **Confidence per finding.** Confidence markers attach to individual atoms. When the two streams assigned different confidences, audit conservatism applies.

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Step-listing without actor** — steps named without who-performs-them. The corpus does not carry steps without actor atoms; either the actor is identified or the step is downgraded to a pending-clarification atom.
- **Bottleneck-symptom phrasing without constraint-type** — "this takes too long", "this is where things slow down" without the typed underlying constraint. Bottleneck-symptom-only residue; the atom is incomplete.
- **Happy-path-only narration** — sequential prose covering only the main flow without decision-point branches. Happy-path-flattening residue; either decision-point atoms with explicit criteria are added, or the corpus carries an explicit "happy-path-only: no branches identified" atom.
- **Frictionless-handoff phrasing** — "the work passes to X" without examining what is transferred and what is lost. Handoff-blindness residue; the atom either earns a friction-type or is downgraded.
- **Causal-explanation residue** — "this happens because of X", "the root cause of slow-down is Y". Causal-overreach residue; the mode is descriptive process documentation, not causal analysis. Causal-language phrases either get reframed as descriptive (what occurs, not why) or escalated to T4.
- **Documented-only restatement** — both streams restating the same official policy description without surfacing actual practice. Official-vs-actual-elision residue; the second restatement is bloat unless it adds an actual-process divergence atom.

**What NOT to collapse:**

- **Official-vs-actual divergence** — when one stream described the official process and the other described an actual practice that diverges, preserve both as parallel atoms with the divergence explicitly named. The divergence is itself the finding; silent reconciliation toward the official version is the failure mode.
- **Bottleneck-constraint-type disagreement** — when streams diagnosed the same bottleneck with different underlying constraints (one says capacity, the other says authority), preserve both diagnoses as parallel atoms. The disagreement is consequential for what intervention would help; the consolidator must not silently pick.
- **Exception-path coverage** — when streams identified different exception cases, preserve all surviving exception-path atoms. The breadth value lies in the catalog of edge cases.

## VERIFICATION CRITERIA

Verified means: process boundaries are locked with explicit start trigger and end condition; actors are inventoried with role attribution per step; decision points are surfaced with criteria; dependencies are mapped; bottlenecks are identified with underlying constraints (not just symptoms); handoffs are examined for friction; official-vs-actual distinction is acknowledged. The five critical questions are addressable from the output. Confidence per finding accompanies every claim.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **diagram-friendly process map: swim-lane step graph with decision-point branches, dependency arcs, bottleneck atoms (constraint-typed), and handoff-friction findings**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Process scope and boundaries.** Three labelled lines at the top:
   - **Process:** [name]
   - **Start trigger:** [the event or condition that initiates the process]
   - **End condition:** [how the process is known to be complete]

2. **Actor / role inventory.** Numbered list of actors. Each actor: `A_n: [name]. Role: [responsibility scope]. Steps: [list of step IDs this actor performs].`

3. **Sequential step breakdown (swim-lane).** Numbered list of steps (1.1, 1.2, ...). Each step: `**[Step N: short name]** — actor: A_n. Action: [what happens]. Predecessors: [list of prior step IDs]. Successors: [list of next step IDs].` Render as a swim-lane structure when the medium supports it: each actor as a horizontal lane with their steps arranged left-to-right.

4. **Decision points and branches.** Numbered list. Each decision point: `**[DP_n: short name]** — triggered after step [N]. Decision criteria: [explicit criteria, not "depending on the situation"]. Branches: [(condition A → step path A), (condition B → step path B), …].` At least one decision-point atom when branches exist; happy-path-flattening is the named failure mode.

5. **Exception paths.** Bulleted list of exception cases. Each bullet: `**[Exception]** — trigger: [what causes the exception]. Path taken: [alternative flow]. Recovery: [how the process resumes or terminates].` At minimum one exception-path atom — breadth marker.

6. **Dependency map.** Numbered list of dependency arcs. Each arc: `Step [N] blocks step [M] — dependency: [resource / precondition / authorization / information] that creates the block.` Cycles are forbidden (process-mapping is acyclic; feedback escalates to systems-dynamics-structural).

7. **Bottleneck identification.** Numbered list. Each bottleneck: `**[Bottleneck at step/handoff N]** — symptom: [what the user observes]. **Underlying constraint:** [capacity / authority / information / sequencing]. Mechanism: [the specific mechanism creating the slow-down].` Bottleneck-symptom-only is the named failure mode; the constraint-type tag is operative.

8. **Handoff and friction points.** Numbered list. Each handoff: `**[Handoff: source actor → target actor at step N]** — what transfers: [content]. Friction type: [information-loss / role-confusion / queue-accumulation / context-collapse]. Cost: [what the friction imposes].` At minimum one handoff-friction atom when more than one actor participates.

9. **Official vs actual divergence.** Bulleted list of steps or handoffs where the documented process differs from the lived process. Each bullet: `Step/handoff [N]: official says [X]; actual is [Y]. Deviation: [reason]. Workaround: [if known].` When no divergences are identified, render: "Official-vs-actual: not investigated in this pass" rather than implying alignment.

10. **Confidence per finding.** Bulleted list of confidence markers per finding (bottleneck constraint-types, handoff frictions, dependency arcs).

**Per-section conventions:**

- Use H2 headings for sections 1 through 10.
- Step IDs follow consistent numbering (1.1, 1.2, ...) — visible in section 3 and referenced throughout.
- Bottleneck constraint-types use canonical four labels (capacity / authority / information / sequencing); do not invent intermediate categories.
- Handoff friction types use canonical four labels (information-loss / role-confusion / queue-accumulation / context-collapse).
- When the medium supports it, render the swim-lane visually (actors as rows, steps as cells); otherwise per-step list with explicit `Actor: A_n` tags.
- Avoid causal-explanation framing throughout (the mode is descriptive process documentation; causal-overreach escalates to T4).


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

**Prioritize:** `parent`, `child`, `produces`, `enables`, `requires`
**Deprioritize:** `contradicts`, `supersedes`

*Family: mechanism-structure. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
