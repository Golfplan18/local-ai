# Framework — Mechanism Understanding

*Self-contained framework for explaining how parts produce the whole's behavior at the principle level (singleton territory). Compiled 2026-05-01.*

---

## Territory Header

- **Territory ID:** T16
- **Name:** Mechanism Understanding
- **Super-cluster:** B (Causation, Hypothesis, and Mechanism)
- **Characterization:** Operations that take a phenomenon and explain *how* it works — the parts, their relationships, the process by which inputs become outputs.
- **Boundary conditions:** Input is a phenomenon whose internal workings are sought. Excludes causal investigation (T4 — backward to causes) and process mapping (T17 — temporal flow).
- **Primary axis:** Depth (mechanism founder mode at thorough depth).
- **Secondary axes:** None at current population; grows specificity axis as domain-specific mechanism modes added.
- **Coverage status:** Moderate after Wave 3 (founder built; expansion deferred).

---

## When to use this framework

Use T16 when the user wants to understand *how* something works at the principle level — what the parts are, how they interact, how the interaction produces the whole's observed behavior. T16 answers questions like "how does this work under the hood?", "explain the mechanism", "what's the principle?", "how do the parts produce the behavior I'm seeing?".

T16 does NOT do causal investigation (why a particular outcome occurred — that is T4), process flow over time (sequenced steps — that is T17), or relationship topology (how the parts relate structurally — that is T11).

---

## Within-territory disambiguation

```
[Territory identified: mechanism understanding — how does this work?]

Route: mechanism-understanding (Tier-2, territory founder)
```

**Singleton territory.** T16 currently has one resident mode (`mechanism-understanding`, Wave 3 founder). No within-territory disambiguation needed. Domain-specific mechanism variants are deferred per CR-6 — they would expand the specificity axis as Ora encounters domain-specific mechanism work that the founder mode handles inadequately.

**Default route.** `mechanism-understanding` at Tier-2.

**Escalation hooks.**
- After `mechanism-understanding`: if the question becomes "why does this happen" (causal investigation) rather than "how does it work", hook sideways to T4 (`root-cause-analysis` or `systems-dynamics-causal`).
- After `mechanism-understanding`: if the question becomes "how does this flow over time as a process", hook sideways to T17 (`process-mapping`).
- After `mechanism-understanding`: if the question becomes "how do the parts relate structurally" (topology rather than working-principle), hook sideways to T11 (`relationship-mapping`).

---

## Mode entries

### `mechanism-understanding` — Mechanism Understanding

**Educational name:** mechanism understanding (how parts produce the whole's behavior).

**Plain-language description.** Explains how a phenomenon works at the principle level. Locks the level of analysis (e.g., molecular, organizational, system-wide); inventories components with each component's function stated (not merely named); describes the interaction pattern among components as the source of the whole's behavior (the emergence account — not whole-behavior alongside components but whole-behavior produced by components-in-interaction); names boundary conditions (under what circumstances the mechanism applies, when it breaks down, what it does not explain). Distinguishes mechanism explanation from process map (T17) and causal chain (T4).

**Critical questions.**
- CQ1: Has the level of analysis been locked, or has the explanation jumped between levels without acknowledgment?
- CQ2: Have the components been inventoried with each component's function stated, rather than merely named?
- CQ3: Has the interaction pattern among components been described as the source of the whole's behavior, rather than treating the whole's behavior as a separate fact alongside the components?
- CQ4: Are the boundary conditions of the mechanism named — under what circumstances it applies, when it breaks down, what it does not explain?
- CQ5: Has the explanation been distinguished from a process map (temporal flow) and a causal chain (backward-to-causes), or have these been conflated?

**Per-pipeline-stage guidance.**
- **Analyst.** Lock level of analysis; inventory components with function per component; describe interaction pattern as source of behavior (emergence account); name boundary conditions; distinguish from T4 / T17 framings.
- **Evaluator.** Verify level lock (no level-jumping without acknowledgment); verify function attribution; verify emergence account explicit; verify boundary conditions named; verify territory distinction maintained.
- **Reviser.** Lock level where draft drifts; add functional role per component; make emergence account explicit; add boundary conditions; resist drift toward narrative process-flow or causal-chain explanation.
- **Verifier.** Confirm eight required sections (phenomenon_and_behavior_locked, level_of_analysis, component_inventory, component_function_per_component, interaction_pattern_among_components, emergence_account, boundary_conditions_and_limits, confidence_per_finding); confirm at least one prediction about behavior under altered conditions.
- **Consolidator.** Merge as a structured synthesis; level of analysis stated as locked claim; components in structured table with function per component; interaction pattern as explicit description of how components together produce behavior.

**Source tradition.** Meadows twelve leverage points (when leverage-points framework illuminates which components do most of the work); Senge system archetypes (when archetype-pattern signatures help identify mechanism class).

**Lens dependencies.**
- Required: none.
- Optional: meadows-twelve-leverage-points, senge-system-archetypes.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

---

## Cross-territory adjacencies

### T4 ↔ T16 (Causal Investigation ↔ Mechanism Understanding)

**Why adjacent.** Both engage with how things produce outcomes. T4 traces backward from outcome to cause; T16 explains how the parts of a phenomenon work together to produce its behavior.

**Disambiguating question.** "Tracing back to causes, or explaining how the parts produce the behavior?"

**Routing.** Backward-to-causes → T4. How-it-works → T16.

**Examples.**
- "Why did the rollout fail?" → T4.
- "How does this recommendation algorithm actually work?" → T16.
- "What caused the market shift?" → T4.
- "How does fiscal policy translate into household spending?" → T16.

### T11 ↔ T16 ↔ T17 (Mechanism / Process / Structure cluster)

**Why adjacent.** These three cluster tightly because they all engage with how something works internally — but they ask different questions about it. T16 asks how the gears interlock to produce behavior; T17 asks how the flow runs in sequence; T11 asks how the parts relate as a structure.

**Disambiguating question.** "Is the question about *how* this works (the gears), about the *flow or process* (sequence), or about how the *parts relate* (structure)?"

**Routing.** How → T16. Flow → T17. Structure → T11.

**Sequential dispatch.** When two of the three fire on the same input, the lighter framing typically runs first: T11 (structure) before T17 (process) before T16 (mechanism), because each successive territory builds on the prior.

---

## Lens references (Core Structure embedded)

### Meadows Twelve Leverage Points (optional for mechanism-understanding)

**Core Structure.** Donella Meadows's hierarchy of intervention points in a system, ordered from least to most effective:
1. **Numbers** — constants and parameters (subsidies, taxes, standards).
2. **Buffers** — sizes of stabilizing stocks relative to flows.
3. **Stock-and-flow structures** — physical systems and their nodes of intersection.
4. **Delays** — lengths of time relative to system change rates.
5. **Balancing feedback loops** — strength of self-correcting feedbacks relative to impacts they correct.
6. **Reinforcing feedback loops** — strength of self-reinforcing feedbacks producing growth or collapse.
7. **Information flows** — structure of who has access to what information.
8. **Rules** — incentives, punishments, constraints.
9. **Self-organization** — power to add, change, or evolve system structure.
10. **Goals** — purpose or function of the system.
11. **Paradigms** — mindset out of which the system arises.
12. **The power to transcend paradigms.**

For Mechanism Understanding, the leverage-points hierarchy serves as a checklist: when explaining how a phenomenon works, the higher-leverage components (loops, rules, goals, paradigms) often do most of the explanatory work, while lower-leverage components (numbers, buffers) are operational details. The hierarchy guides component-inventory toward the work-doing components rather than the merely-present components.

### Senge System Archetypes (optional for mechanism-understanding)

**Core Structure.** Peter Senge's catalog of recurring system patterns (drawn from Forrester's system dynamics):
- **Fixes That Fail** — short-term fix produces long-term consequences that worsen the original problem.
- **Shifting the Burden** — symptomatic solution displaces fundamental solution; addiction patterns.
- **Limits to Growth** — reinforcing loop produces growth until a balancing loop kicks in.
- **Eroding Goals** — gap between desired and actual is closed by lowering goals rather than improving performance.
- **Escalation** — two parties view their welfare as relative; each takes action that threatens the other.
- **Success to the Successful** — initial advantage produces resources that further the advantage.
- **Tragedy of the Commons** — shared resource overused because individual incentives diverge from collective good.
- **Growth and Underinvestment** — growth approaches limit; investment lag prevents capacity from keeping up.

For Mechanism Understanding, archetype identification supports mechanism-class recognition: when a phenomenon's behavior signature matches an archetype, the mechanism explanation can leverage the archetype's known structure rather than reconstructing from scratch. The archetype-name-drop failure mode applies — naming the archetype is not sufficient; the matching loop topology must be present in the components and their interactions.

---

## Open debates

T16 carries no territory-level open debates. As a singleton territory, mode-level debates do not currently apply.

---

## Citations and source-tradition attributions

- Meadows, D. H. (1999). *Leverage Points: Places to Intervene in a System*. Sustainability Institute. The leverage-points hierarchy.
- Meadows, D. H. (2008). *Thinking in Systems: A Primer*. Chelsea Green. Standard system-thinking treatment.
- Senge, P. M. (1990). *The Fifth Discipline: The Art and Practice of the Learning Organization*. Doubleday. System archetypes.
- Forrester, J. W. (1961). *Industrial Dynamics*. MIT Press. Foundational system-dynamics text.
- Sterman, J. D. (2000). *Business Dynamics: Systems Thinking and Modeling for a Complex World*. McGraw-Hill. Standard quantitative system-dynamics reference.
- Kahneman, D. & Tversky, A. (Various). Heuristics-and-biases catalog (foundational substrate).

*End of Framework — Mechanism Understanding.*
