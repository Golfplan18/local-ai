---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Mechanism Understanding

```yaml
# 0. IDENTITY
mode_id: mechanism-understanding
canonical_name: Mechanism Understanding
suffix_rule: analysis
educational_name: mechanism understanding (how parts produce the whole's behavior)

# 1. TERRITORY AND POSITION
territory: T16-mechanism-understanding
gradation_position:
  axis: depth
  value: thorough
adjacent_modes_in_territory: []

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want to understand how this actually works under the hood"
    - "I need to know how the parts produce the behavior I'm seeing"
    - "I want a principled explanation of the mechanism, not just a description"
    - "I need to understand the gears, not just the inputs and outputs"
  prompt_shape_signals:
    - "how does this work"
    - "mechanism"
    - "under the hood"
    - "how do the parts produce"
    - "what's the principle"
    - "explain the gears"
    - "internal workings"
    - "structural explanation"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants explanation of how parts of a phenomenon produce the whole's behavior at the principle level"
    - "user wants the gears, not the timeline (process flow) or the cause (causal chain)"
    - "user wants structural explanation rather than narrative description"
  routes_away_when:
    - "user wants to know why a particular outcome occurred (backward to causes)" → T4 causal modes
    - "user wants step-by-step process flow over time" → process-mapping (T17)
    - "user wants to know who has what role and authority" → organizational-structure (gap-deferred, T17)
    - "user wants relationships between entities in a representation" → relationship-mapping (T11)
    - "user wants to evaluate the mechanism as a proposal" → T15 stance modes
when_not_to_invoke:
  - "User wants forward-looking projection rather than current-mechanism explanation" → T6 modes
  - "User wants to find the cause of a problem to fix" → T4 modes
  - "User wants to map a process step by step" → T17 process-mapping

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [phenomenon_or_system, behavior_to_be_explained, known_components]
    optional: [domain_briefing, prior_mechanism_descriptions, scale_or_level_of_analysis]
    notes: "Applies when user supplies a scoped phenomenon with named components and an explicit behavior-to-be-explained."
  accessible_mode:
    required: [phenomenon_description]
    optional: [what_user_already_understands, why_user_wants_mechanism]
    notes: "Default. Mode elicits components and behavior-to-be-explained during execution."
  detection:
    expert_signals: ["mechanism", "structural explanation", "components and interactions", "principle-level"]
    accessible_signals: ["how does this work", "explain the gears", "what makes this happen", "under the hood"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What phenomenon are you trying to understand, and what specifically about its behavior do you want explained?'"
    on_underspecified: "Ask: 'Are you asking how it works at the principle level (the mechanism), or how it works step-by-step over time (the process)?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the level of analysis been locked (e.g., molecular, organizational, system-wide), or has the explanation jumped between levels without acknowledgment?"
    failure_mode_if_unmet: level-confusion
  - cq_id: CQ2
    question: "Have the components been inventoried with each component's function stated, rather than merely named?"
    failure_mode_if_unmet: component-inventory-without-function
  - cq_id: CQ3
    question: "Has the interaction pattern among components been described as the source of the whole's behavior, rather than treating the whole's behavior as a separate fact alongside the components?"
    failure_mode_if_unmet: emergence-elision
  - cq_id: CQ4
    question: "Are the boundary conditions of the mechanism named — under what circumstances it applies, when it breaks down, what it does not explain?"
    failure_mode_if_unmet: scope-overreach
  - cq_id: CQ5
    question: "Has the explanation been distinguished from a process map (temporal flow) and a causal chain (backward-to-causes), or have these been conflated?"
    failure_mode_if_unmet: territory-conflation

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: level-confusion
    detection_signal: "Explanation moves between molecular, organizational, and system-wide accounts without explicit acknowledgment of level shift."
    correction_protocol: re-dispatch
  - name: component-inventory-without-function
    detection_signal: "Components named but their functional role in producing the whole's behavior not stated."
    correction_protocol: re-dispatch
  - name: emergence-elision
    detection_signal: "Whole's behavior described separately from components without an explicit account of how the interaction pattern produces it."
    correction_protocol: re-dispatch
  - name: scope-overreach
    detection_signal: "Mechanism explanation extended to phenomena outside the boundary conditions; over-generalization."
    correction_protocol: flag
  - name: territory-conflation
    detection_signal: "Output blends process-flow narration (T17) or causal-chain investigation (T4) with mechanism explanation; not parsed."
    correction_protocol: re-dispatch
  - name: just-so-explanation
    detection_signal: "Explanation appears to fit the observed behavior but makes no predictions about behavior under altered conditions."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - meadows-twelve-leverage-points (when leverage-points framework illuminates which components do most of the work)
    - senge-system-archetypes (when archetype-pattern signatures help identify mechanism class)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Mechanism Understanding is the territory founder mode in T16; expansion deferred per Wave 3 plan."
  sideways:
    target_mode_id: null
    when: "T16 has no current sibling modes; cross-territory routing handled by adjacency map."
  downward:
    target_mode_id: null
    when: "Mechanism Understanding is the only mode in T16 at current population."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Mechanism Understanding is the explicitness of (a) level-of-analysis selection, (b) per-component function attribution, and (c) the account of how interaction pattern produces the whole's behavior (the emergence account). A thin pass names components and asserts the behavior; a substantive pass locks the level of analysis, inventories components with their functional role in producing the behavior, describes the interaction pattern as the source of the behavior (rather than alongside it), and names the boundary conditions under which the mechanism applies. Test depth by asking: could the explanation predict how the whole's behavior would change if a specific component were altered, removed, or replaced — and does the answer follow from the stated mechanism rather than from intuition?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for components the analyst might omit (background conditions, supporting infrastructure, regulatory or constraining elements that do not actively contribute but enable contribution), considering alternative mechanism descriptions at different levels of analysis, and surfacing where the mechanism is incomplete or where multiple mechanisms could account for the same observed behavior. Breadth markers: the analysis names at least one background-or-enabling component that easy descriptions tend to omit, and acknowledges at least one alternative-mechanism candidate the available evidence cannot rule out.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Mechanism Understanding is a principle-level structural explanation of how the parts of a phenomenon produce the whole's behavior. It is descriptive of how-it-works, distinct from a process map (T17 — temporal flow, step-by-step over time) and from a causal-chain analysis (T4 — backward-to-causes for a particular outcome). The mode locks a level of analysis, inventories components with their functional role (not just their names), describes the interaction pattern as the source of the whole's behavior, and names the boundary conditions under which the mechanism applies. It is the founder and currently only mode in T16.

**Procedure.**

1. State the phenomenon and the specific behavior to be explained — one canonical pairing at the head.
2. Lock the level of analysis (molecular / organizational / system-wide / domain-specific). The lock is the load-bearing precondition; explanation that drifts between levels without acknowledgment is the level-confusion failure mode.
3. Inventory the components at the locked level — each component named with its functional role in producing the whole's behavior, not merely identified as present.
4. Surface background and enabling components — regulatory conditions, supporting infrastructure, constraining elements that enable contribution without actively contributing; easy explanations omit these.
5. Describe the interaction pattern explicitly — the choreography among components, the relationship-among-components that is the actual mechanism. A list of components and their separate functions is not a mechanism.
6. Render the emergence account — state as a single integrated claim that the interaction pattern produces the whole's behavior, rather than describing behavior alongside components.
7. Name boundary conditions — when the mechanism applies, when it breaks down, what it does not explain.
8. Produce at least one prediction under altered conditions — what changes in the whole's behavior if a specific component is altered, removed, or replaced, with the prediction following from the stated mechanism.
9. Surface at least one alternative mechanism the available evidence cannot rule out, with discrimination criteria.
10. Hold the territory line — distinguish the mechanism explanation from a T4 causal chain or a T17 process flow.

**Goal.** Produce a structured mechanism explanation that locks a level of analysis, attributes function per component, accounts for emergence as interaction-pattern-producing-behavior, names boundary conditions, and produces falsifiable predictions about behavior under altered conditions.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — level lock.** Has the level of analysis been locked (molecular / organizational / system-wide), or has the explanation jumped between levels without acknowledgment? Failure mode if unmet: `level-confusion`.
- **CQ2 — function per component.** Have components been inventoried with each component's function stated, rather than merely named? Failure mode if unmet: `component-inventory-without-function`.
- **CQ3 — emergence account.** Has the interaction pattern among components been described as the source of the whole's behavior, rather than treating the whole's behavior as a separate fact alongside the components? Failure mode if unmet: `emergence-elision`.
- **CQ4 — boundary conditions.** Are boundary conditions named — when the mechanism applies, when it breaks down, what it does not explain? Failure mode if unmet: `scope-overreach`.
- **CQ5 — territory distinction.** Has the explanation been distinguished from a process map (temporal flow) and a causal chain (backward-to-causes), or have these been conflated? Failure mode if unmet: `territory-conflation`.

A passing output locks the level of analysis, attributes function per component, names at least one background/enabling component, makes the interaction pattern explicit, renders the emergence account, names boundary conditions, produces at least one falsifiable prediction under altered conditions, and stays within T16's mechanism territory rather than drifting into T4 causation or T17 process-flow.

**Named failure modes.**

- *level-confusion* — explanation moves between molecular, organizational, and system-wide accounts without explicit acknowledgment of level shift.
- *component-inventory-without-function* — components named but their functional role in producing the whole's behavior not stated.
- *emergence-elision* — whole's behavior described separately from components without an explicit account of how the interaction pattern produces it.
- *scope-overreach* — mechanism explanation extended to phenomena outside the boundary conditions; over-generalization.
- *territory-conflation* — output blends process-flow narration (T17) or causal-chain investigation (T4) with mechanism explanation.
- *just-so-explanation* — explanation appears to fit the observed behavior but makes no predictions about behavior under altered conditions.

## REVISION GUIDANCE

Revise to lock the level of analysis where the draft drifts. Revise to add functional role per component where components are merely named. Revise to make the emergence account explicit — the interaction pattern producing the behavior — where the draft asserts the behavior and the components separately. Revise to add boundary conditions where the explanation appears unbounded. Resist revising toward narrative process-flow or causal-chain explanation — these are different territories. If the user wants temporal flow, escalate to T17 process-mapping; if they want causes of an outcome, escalate to T4 causal modes.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a locked-level-of-analysis component inventory with function-per-component, interaction-pattern, and emergence atoms**. The level lock is the load-bearing precondition; the emergence atom is the load-bearing analytical product — it is what distinguishes a mechanism from a component list. The atoms are:

1. **Phenomenon-and-behavior atom.** The phenomenon and the specific behavior to be explained, stated once at the corpus head. Cross-stream paraphrase collapses to one canonical pairing.

2. **Level-of-analysis lock atom.** A single locked claim — molecular / organizational / system-wide / [other domain-specific level]. Level-confusion is the named failure mode; an explanation that drifts between levels without acknowledgment is its corpus signature. When streams locked different levels, preserve as a tension atom (the choice-of-level is itself analytical, not a detail to silently reconcile).

3. **Component-inventory atoms with function-per-component.** Each component atom carries: component name, scale or class at the locked level, and **functional role** — the specific contribution the component makes to producing the whole's behavior. Components named without functional role are component-inventory-without-function residue; they do not survive into the corpus as components — they either earn a function attribution or are dropped.

4. **Background/enabling-component atoms.** Components that do not actively contribute but enable contribution (regulatory conditions, supporting infrastructure, constraining elements). The breadth marker for this mode is that at least one such component is surfaced; easy explanations omit them. Background components carry their enabling-role atom (what their presence makes possible, what their absence would prevent).

5. **Interaction-pattern atom.** An explicit description of how components together produce the behavior — the choreography among components, not a list of their separate functions. The interaction-pattern atom is load-bearing because it names the relationship-among-components that is the actual mechanism. A corpus with components-and-behavior but no interaction-pattern atom is a list, not a mechanism.

6. **Emergence-account atom.** The corpus-level claim that the interaction pattern produces the whole's behavior — stated as a single integrated claim, not as the behavior and the components separately. Emergence-elision is the named failure mode; describing the whole's behavior alongside the components without the producing-account is its signature.

7. **Boundary-condition atoms.** Each atom names: a condition under which the mechanism applies, a condition under which it breaks down, and a phenomenon outside the boundary the mechanism does not explain. At least three boundary atoms must survive or scope-overreach is unguarded.

8. **Prediction-under-altered-conditions atom.** A single corpus-level atom names at least one prediction the mechanism produces about behavior when a specific component is altered, removed, or replaced. Just-so-explanation is the failure mode; an explanation that fits the observed behavior but makes no predictions about altered conditions is its corpus signature. The prediction is operative content, not optional.

9. **Alternative-mechanism atoms.** Each names a candidate mechanism the available evidence cannot rule out, with a brief discrimination atom (what evidence would distinguish this mechanism from the leading one). At least one alternative-mechanism atom must survive or the breadth marker is unmet.

10. **Territory-distinction atom.** A single corpus-level atom names how this mechanism explanation differs from a T17 process-flow account (temporal sequence) and a T4 causal-chain account (backward-to-causes). Territory-conflation is the failure mode; the atom defends against drift into adjacent territories.

11. **Confidence per finding.** Confidence markers attach to individual atoms. When the two streams assigned different confidences, audit conservatism applies.

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Component-naming without function** — components listed as named entities without functional-role attributions. Component-inventory-without-function residue; the atom is incomplete and does not survive.
- **Level-drift residue** — explanation moving between molecular, organizational, and system-wide accounts without acknowledgment. Level-confusion residue; the corpus carries one locked level, and material at other levels either gets reframed or is flagged as a level-distinction atom.
- **Behavior-restatement-without-mechanism** — the whole's behavior described in different framings without the interaction-pattern atom. Emergence-elision residue; restatements of behavior are bloat unless they're contributing to the emergence account.
- **Just-so phrasing** — "this happens because X is structured to produce Y" without a prediction-under-altered-conditions test. Just-so-explanation residue; the phrasing survives only when paired with a prediction atom.
- **Territory-bleed-in** — process-flow narration ("first this happens, then that") or causal-chain language ("the cause of X is Y") leaking into the mechanism account. Territory-conflation residue; the consolidator distinguishes the mechanism description from the temporal or causal framings.
- **Scope-overreach phrasing** — "this mechanism explains [much broader class of phenomena]" beyond the boundary atoms. Scope-overreach residue; the corpus carries the boundary atoms as the limit, and overreach phrasing does not survive.

**What NOT to collapse:**

- **Level-of-analysis disagreement** — when one stream locked molecular and the other locked system-wide for the same phenomenon, preserve both lockings as parallel level atoms with their respective component inventories. The choice-of-level is itself an analytical move; silent reconciliation is level-confusion injection.
- **Alternative-mechanism disagreement** — when streams identified different alternative mechanisms the evidence cannot rule out, preserve all surviving alternatives. The breadth value lies in the catalog of candidates; merging non-overlapping alternatives is content loss.
- **Boundary-condition disagreement** — when streams disagreed on whether the mechanism extends to a particular condition, preserve both judgments as a contested-boundary atom. The disagreement is a finding about the mechanism's robustness to edge cases.

## VERIFICATION CRITERIA

Verified means: the level of analysis is locked; components are inventoried with functional role per component; the interaction pattern is described as the source of the whole's behavior; emergence is accounted for rather than elided; boundary conditions are named; the explanation makes at least one prediction about behavior under altered conditions. The five critical questions are addressable from the output. Confidence per finding accompanies every claim. The output is distinguishable from a T4 causal-chain analysis or a T17 process-map.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structured mechanism explanation: phenomenon-and-behavior locked, level-of-analysis locked, component inventory with function-per-component, interaction pattern, emergence account, boundary conditions, and prediction-under-altered-conditions**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Phenomenon and behavior.** Two short labelled lines at the top:
   - **Phenomenon:** [the system or process being explained]
   - **Behavior to be explained:** [the specific behavior of the phenomenon under analysis]

2. **Level of analysis.** A single labelled line: `Level: [molecular / organizational / system-wide / domain-specific level]. Reason: [why this level fits the behavior in question].` Level-confusion is the named failure mode; the lock is explicit. When streams locked different levels, render both as a tension: "Stream A locked [level X]; Stream B locked [level Y]. The choice is itself analytical: [reason for the tension]."

3. **Component inventory with function per component.** A table or per-component block. For each component, render:
   - **Component:** name
   - **Scale or class at the locked level:** [classification]
   - **Functional role:** [specific contribution to producing the whole's behavior]

   Components without functional role do not appear. The function-per-component is load-bearing.

4. **Background and enabling components.** Bulleted list of components that do not actively contribute but enable contribution (regulatory conditions, supporting infrastructure, constraining elements). Each bullet: `**[Component]** — enabling role: [what its presence makes possible; what its absence would prevent].` At minimum one such atom — easy explanations omit them.

5. **Interaction pattern.** A prose block explicit-naming the choreography among components — the relationship-among-components that is the actual mechanism. Render as a directed-relation list or a structured description. The interaction-pattern atom is what distinguishes a mechanism from a component list; the section is load-bearing.

6. **Emergence account.** A short prose block (two to four sentences) stating the corpus-level claim that the interaction pattern produces the whole's behavior. Frame as: "The interaction pattern in section 5 produces the behavior named in section 1 by [specific account]." Emergence-elision is the named failure mode; do not describe the whole's behavior alongside the components without the producing-account.

7. **Boundary conditions and limits.** Numbered list. At minimum three atoms:
   - Conditions under which the mechanism applies
   - Conditions under which it breaks down
   - Phenomena outside the boundary the mechanism does not explain

8. **Prediction under altered conditions.** A single block: `If [specific component] is altered, removed, or replaced, the whole's behavior changes by [specific prediction]. The prediction follows from the mechanism in section 5 because [reason].` Just-so-explanation is the named failure mode; an explanation that fits without predicting under altered conditions is its corpus signature.

9. **Alternative mechanisms (where applicable).** Bulleted list of candidate mechanisms the available evidence cannot rule out. Each bullet: `**[Alternative mechanism]** — discrimination: [what evidence would distinguish this from the leading mechanism].` At minimum one alternative-mechanism atom or the breadth marker is unmet.

10. **Territory distinction.** One sentence flagging how this mechanism explanation differs from a T4 causal-chain account (backward-to-causes) and a T17 process-flow account (temporal sequence). Frame as: `This is a mechanism explanation, not [T4 causal chain / T17 process flow]: [structural reason for the distinction in this case].` Territory-conflation is the named failure mode.

11. **Confidence per finding.** Bulleted list of confidence markers per major claim (component-function attributions, interaction pattern, emergence account, prediction).

**Per-section conventions:**

- Use H2 headings for sections 1 through 11.
- Section 3's component inventory: table form when components are uniform in description; per-component blocks when functional roles need elaboration.
- The level-of-analysis lock in section 2 is enforced throughout; material at other levels gets flagged as level-distinction rather than smuggled into the inventory.
- Avoid causal-chain framing in the emergence account ("X causes Y" with backward-to-causes posture) — keep the structural framing ("interaction pattern produces behavior").
- The prediction in section 8 is concrete and falsifiable, not a hedged "behavior might change."

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- AGO
- CAF
- Concept Fan
- Challenge
- FIP
- RAD

Mental models (always loaded):
- first-principles
- map-territory
- lakoff-conceptual-metaphor
- occams-razor
- falsifiability
- emergence
- feedback-loops
- system-one-system-two

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `parent`, `child`, `produces`, `enables`, `requires`
**Deprioritize:** `contradicts`, `supersedes`

*Family: mechanism-structure. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
