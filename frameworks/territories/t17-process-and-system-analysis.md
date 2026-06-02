# Framework — Process and System Analysis

*Self-contained framework for mapping a process, workflow, organization, or system as it currently is — components, flows, bottlenecks, and dependencies. Compiled 2026-05-01.*

---

## Territory Header

- **Territory ID:** T17
- **Name:** Process and System Analysis
- **Super-cluster:** B (Causation, Hypothesis, and Mechanism)
- **Characterization:** Operations that map a process, workflow, organization, or system as it currently is — identifying components, flows, bottlenecks, and dependencies. Diagnostic in posture; not yet seeking causes (T4) or interventions.
- **Boundary conditions:** Input is a process, workflow, or system. Excludes causal investigation (why this happens — T4) and excludes mechanism understanding (how parts produce behavior at the principle level rather than operational — T16).
- **Primary axis:** Specificity (general process vs. organizational structure vs. systems-dynamics-with-feedback).
- **Secondary axes:** Complexity (single process → multi-process system).
- **Coverage status:** Moderate after Wave 3 (Organizational Structure deferred per CR-6).

---

## When to use this framework

Use T17 when the user wants a current-state map of how a process, workflow, or system actually works — sequenced steps, actors, decision points, dependencies, bottlenecks, handoffs, and (for feedback-bearing systems) loops with polarity. T17 is descriptive: it documents what is, not why it produces particular outcomes (T4) and not what should be done about it (T15 stance modes).

T17 has three primary modes: `process-mapping` (linear / branching workflow without feedback dominance), `systems-dynamics-structural` (feedback structure with stocks, flows, and loops), and `market-dynamics` (descriptive analysis of how a market or economic system behaves — supply and demand, equilibrium, selection effects, network effects, returns to scale, competitive dynamics). The Organizational Structure mode is deferred per CR-6.

T17 does NOT do causal investigation (T4), mechanism explanation (T16), or relationship topology without temporal flow (T11).

---

## Within-territory disambiguation

```
[Territory identified: process or system mapping, current state]

Q1 (specificity): "Is the system you're mapping a market or economy
                    (prices, supply and demand, competition, network effects),
                    a feedback structure
                    (loops, reinforcing or balancing dynamics),
                    or a process flow
                    (sequenced steps, inputs producing outputs)?"
  ├─ "a market or economy / prices / supply and demand / competition / network effects" →
        market-dynamics (Tier-2; describes market behavior — design of a mechanism or
                          contract routes to T18 mechanism-design)
  ├─ "feedback structure / loops / reinforcing or balancing dynamics" →
        systems-dynamics-structural (Tier-2; cross-territory note: causal variant
                                      lives in T4, parsed per Decision D)
  ├─ "process flow / sequenced steps" → process-mapping (Tier-2)
  ├─ "organizational structure (formal reporting and roles)" →
        organizational-structure (deferred per CR-6)
  └─ ambiguous → process-mapping with escalation hook to systems-dynamics-structural
```

**Default route.** `process-mapping` at Tier-2 when ambiguous (the lightest of the resident modes; systems-dynamics-structural is the feedback-specific sibling).

**Escalation hooks.**
- After `process-mapping` Tier-2: if the process map surfaces feedback loops that account for the system's behavior, hook sideways to `systems-dynamics-structural`.
- After `systems-dynamics-structural`: if the question becomes "why does this keep happening" (causal rather than structural), hook sideways to T4 `systems-dynamics-causal` (the parsed sibling per Decision D).
- After either T17 mode: if the question becomes "how do the parts produce the whole's behavior at the principle level", hook sideways to T16 (`mechanism-understanding`).
- After either T17 mode: if the question becomes "what relations does the system assert among its parts", hook sideways to T11 (`relationship-mapping`).
- After `market-dynamics`: if the question shifts from describing how the market behaves to designing a mechanism, contract, or auction, hook sideways to T18 (`mechanism-design`).
- After `market-dynamics`: if the question shifts to advising a specific participant what to do, hook sideways to T3 (`decision-architecture`).

---

## Mode entries

### `process-mapping` — Process Mapping

**Educational name:** process mapping (workflow / dependency / bottleneck identification) (specificity-process-flow).

**Plain-language description.** Step-by-step current-state documentation of a process. Locks process boundaries (start trigger and end condition); inventories actors/roles; breaks down sequential steps with actor attribution; surfaces decision points and branching paths with explicit decision criteria; maps step-to-step dependencies (what blocks what); identifies bottlenecks with the underlying constraint named (capacity / authority / information / sequencing — not just the symptom); examines handoffs between actors for friction and information loss; distinguishes documented (official) process from actual (lived) process.

**Critical questions.**
- CQ1: Have process boundaries been locked (clear start trigger and end condition), or is scope ambiguous?
- CQ2: Has the analysis distinguished between documented (official) and actual (lived) process, or described only one as both?
- CQ3: Have decision points and branching paths been identified with explicit decision criteria, or has the process been flattened into a single happy path?
- CQ4: Have bottlenecks been identified with the constraint that creates them named, rather than just the symptom?
- CQ5: Have handoffs between actors been examined for friction and information loss, or treated as frictionless?

**Per-pipeline-stage guidance.**
- **Analyst.** Lock boundaries; inventory actors/roles; sequence steps with actor attribution; surface decision points with criteria; map dependencies; identify bottlenecks with constraints; examine handoffs for friction.
- **Evaluator.** Verify boundary lock; verify official-vs-actual distinction; verify decision-point and branch surfacing; verify bottleneck-constraint identification; verify handoff examination.
- **Reviser.** Add exception paths where draft shows only happy path; surface official-vs-actual deviations; identify constraint underlying each bottleneck; examine handoffs as friction zones; resist drift toward causal explanation.
- **Verifier.** Confirm eight required sections (process_scope_and_boundaries, actor_or_role_inventory, sequential_step_breakdown, decision_points_and_branches, dependency_map, bottleneck_identification, handoff_and_friction_points, confidence_per_finding).
- **Consolidator.** Merge as a diagram-friendly mapping; sequential step breakdown suitable for swim-lane or flow-chart rendering.

**Source tradition.** Meadows twelve leverage points (when bottleneck-as-leverage-point analysis is central); Senge system archetypes (when process exhibits archetype-pattern signatures).

**Lens dependencies.**
- Required: none.
- Optional: meadows-twelve-leverage-points, senge-system-archetypes.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

### `systems-dynamics-structural` — Systems Dynamics Structural

**Educational name:** feedback-system structural mapping (Forrester/Senge lineage) (complexity-feedback).

**Plain-language description.** Current-state structural map of a feedback system. Declares system boundary explicitly; names variables and stocks (with roles: stock, flow, auxiliary, exogenous); maps feedback loops with polarity (R for reinforcing, B for balancing — verified by parity of negative edges); marks delays explicitly; identifies system archetypes when present (with matching loop topology, not name-drop); produces structural observations describing what is (not what should be — prescriptive drift is a failure mode). The mode is the structural counterpart to T4's `systems-dynamics-causal`; both share feedback-loop lenses but differ in operation (mapping vs. causal investigation).

**Critical questions.**
- CQ1: Are declared loops genuine cycles in the graph (closing edge present), or are they linear chains mis-labelled as loops?
- CQ2: Does each loop's declared type (R or B) match its polarity parity (even number of negative edges → R; odd → B)?
- CQ3: Has the system boundary been stated explicitly, or has the map silently absorbed every adjacent variable?
- CQ4: Does the structural map describe the system as it currently is, or has it drifted into prescriptive recommendations that belong in a different mode?
- CQ5: If a system archetype is named, does its characteristic loop topology actually appear in the declared loops, or is it a name-drop?

**Per-pipeline-stage guidance.**
- **Analyst.** Declare boundary explicitly; name variables/stocks with roles; map loops with id pattern R<n>/B<n> and verified polarity parity; mark delays; identify archetypes with matching topology; describe structurally (not prescriptively).
- **Evaluator.** Verify loop genuineness with closing edge; verify polarity parity matches declared type; verify boundary stated explicitly; verify descriptive (not prescriptive) posture; verify archetype-loop fit.
- **Reviser.** Add closing edge or remove loop where genuineness fails; fix polarity-parity mismatches before semantic refinement; strip prescriptive language; resist pull toward "what should be done".
- **Verifier.** Confirm seven required sections (system_boundary, variables_and_stocks, feedback_loops_with_polarity, delays, system_archetypes_present, structural_observations, confidence_and_boundary_caveats); confirm polarity-parity validator passes.
- **Consolidator.** Merge as a structured mapping with system boundary first, then variables/stocks, then loops with polarity, then delays, then archetypes (with matching topology), then structural observations.

**Source tradition.** Forrester industrial dynamics (foundational); Senge system archetypes; Sterman quantitative system-dynamics modeling; Meadows leverage points.

**Lens dependencies.**
- Required: feedback-loops, senge-system-archetypes.
- Optional: sterman-system-dynamics-modelling, forrester-industrial-dynamics, meadows-twelve-leverage-points (named for transparency; used only if structural map enables intervention discussion).
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

**Decision D parse note.** This mode is one of two parsed from the legacy Systems Dynamics mode per Decision D (parsing principle, 2026-05-01 architecture lock). The legacy mode conflated two distinct operations: causal investigation ("why does this keep happening, given the feedback dynamics?") and structural mapping ("how does this system currently work, including its feedback dynamics?"). Both share the same feedback-loop lenses and the same diagrammatic vocabulary, but they differ in posture (causal-investigation vs structural-descriptive), output contract (counterintuitive-behaviour prediction vs current-state mapping), and disambiguation question (why vs how). This mode is the T17 structural variant; its causal counterpart `systems-dynamics-causal` lives in T4.

### `market-dynamics` — Market Dynamics

**Educational name:** market and economic-system behavior analysis (supply-demand / selection / network-effects lineage) (specificity-market-system).

**Plain-language description.** Descriptive current-state read of how a market or economic system behaves. States the market boundary (good/service/factor, participants, in/out of scope); models BOTH sides (demand-side and supply-side drivers, with qualitative elasticity reasoning); identifies the equilibrium (or disequilibrium) and the adjustment process that reaches it; separates the short-run response from the long-run response (entry, exit, capacity change, substitution); grounds any named economic dynamic (Gresham's law, diminishing returns, critical mass / network effects, creative destruction, Red Queen) in an actual mechanism on this market rather than a name-drop; and produces a descriptive market read (direction and rough magnitude, with the timescale at which it holds). Descriptive in posture — participant advice routes to T3 `decision-architecture`; mechanism / contract / auction design routes to T18 `mechanism-design`.

**Critical questions.**
- CQ1: Are both sides of the market modeled (supply AND demand), or has the analysis silently fixed one side?
- CQ2: Is the equilibrium (or disequilibrium) identified, with the adjustment process that moves the market toward or away from it?
- CQ3: Is the short-run response distinguished from the long-run response (entry, exit, capacity, substitution)?
- CQ4: When a named economic dynamic is invoked (Gresham's law, creative destruction, Red Queen, critical mass), is its actual mechanism shown to operate here, or is it a name-drop?
- CQ5: Does the analysis describe how the market behaves, or has it drifted into prescribing what a participant SHOULD do?

**Per-pipeline-stage guidance.**
- **Analyst.** State the market boundary; model both sides with drivers and qualitative elasticity; identify equilibrium and adjustment; separate short-run from long-run; scan named dynamics and rule each in or out with a mechanism; state the descriptive read with confidence and load-bearing assumptions.
- **Evaluator.** Verify both sides modeled (one-sided-market); verify equilibrium and adjustment named (equilibrium-unstated); verify timescale separated (timescale-collapse); verify named dynamics grounded (dynamic-name-drop); verify descriptive posture (prescriptive-drift); watch for ceteris-paribus-blindness.
- **Reviser.** Add the missing side of the market; name the equilibrium and adjustment before stylistic refinement; split conflated timescales into explicit short-run and long-run; strip prescriptive advice (route to decision-architecture / mechanism-design); ground each named dynamic in its mechanism on this market or cut the name.
- **Verifier.** Confirm seven sections (market_boundary, supply_and_demand, equilibrium_and_adjustment, short_run_vs_long_run, named_dynamics, market_read, confidence_and_assumptions); confirm the read is descriptive (no participant advice) and the load-bearing assumptions are named.
- **Consolidator.** Merge as a descriptive market-read atom set: boundary lock, two-sided supply/demand atoms, equilibrium-and-adjustment atoms, short-run/long-run atoms, named-dynamic atoms grounded in mechanism, descriptive market-read atoms, and confidence-with-assumption-caveat atoms.

**Source tradition.** Neoclassical price theory (Marshall — supply, demand, equilibrium, elasticity); information-economics selection (Gresham's law: bad drives out good under hidden quality); Schumpeterian creative destruction; network economics and critical mass (Katz-Shapiro, Rohlfs); evolutionary competitive coevolution (Van Valen's Red Queen).

**Lens dependencies.**
- Required: supply-demand, equilibrium.
- Optional: greshams-law, diminishing-returns, critical-mass, creative-destruction, red-queen-effect, feedback-loops.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

**Decision note (2026-06-01).** Market Dynamics was added to T17 to home the market-behavior economics lenses (supply-demand, Gresham's law, diminishing returns, critical mass, creative destruction, Red Queen) that no prior mode loaded. It is the market-specialized sibling of `systems-dynamics-structural` along the territory's specificity axis: structural reads a generic feedback system; market-dynamics reads the specific case of a market or economic system. The parse-preserving boundary is descriptive-vs-prescriptive — analyzing how a market behaves stays here; designing a mechanism / contract / auction routes to T18 `mechanism-design`; advising a specific participant routes to T3 `decision-architecture`. Defaults to a partial-equilibrium (single-market) read with cross-market spillovers flagged, not fully modeled.

---

## Cross-territory adjacencies

### T4 ↔ T17 (Causal Investigation ↔ Process and System Analysis)

**Why adjacent.** Both can engage with workflows or systems. T4 asks why a pattern recurs; T17 maps the process as it currently is.

**Disambiguating question.** "Why does this keep happening (causes), or how does this currently work (process map)?"

**Routing.** Causal investigation → T4. Process mapping → T17.

**Examples.**
- "Why does our deployment process keep producing outages?" → T4.
- "Walk me through our deployment process as it currently runs." → T17.
- "Map the workflow." → T17.
- "Why does the workflow keep stalling at the same step?" → T4 (with T17 likely as upstream input).

**Sequential dispatch.** When causal investigation requires a process map first, T17 runs first; T4 follows.

### T11 ↔ T16 ↔ T17 (Mechanism / Process / Structure cluster)

**Disambiguating question.** "Is the question about *how* this works (the gears), about the *flow or process* (sequence), or about how the *parts relate* (structure)?"

**Routing.** How → T16. Flow → T17. Structure → T11.

### T17 ↔ T18 (Process and System Analysis ↔ Strategic Interaction)

**Why adjacent.** Both can engage with markets and economic situations. T17's `market-dynamics` describes how a market *behaves* (prices, quantities, selection, competition); T18's `mechanism-design` analyzes the *information-and-incentive structure* and *designs* the rules, contract, or auction.

**Disambiguating question.** "Is the question how this market behaves (prices, supply and demand, competition — describe), or is it about hidden information / hidden action and designing the incentives or contract (analyze / design)?"

**Routing.** Market behavior, descriptive → T17 `market-dynamics`. Information-and-incentive structure or mechanism design → T18 `mechanism-design`.

**Examples.**
- "What happens to rents if the city upzones?" → T17 `market-dynamics`.
- "Why is this insurance market full of high-risk customers, and how do we design the policy so it isn't?" → T18 `mechanism-design`.
- "How will competitive dynamics play out as this platform scales?" → T17 `market-dynamics`.
- "Design the auction so bidders don't overpay." → T18 `mechanism-design`.

---

## Lens references (Core Structure embedded)

### Feedback Loops (required for systems-dynamics-structural)

**Core Structure.** A feedback loop is a closed cycle in a system's causal graph where the output of a process eventually becomes input to the same process via one or more intermediate variables. Two types:

- **Reinforcing (R) loops** — the loop amplifies disturbances; effects of a change feed back to compound it. Polarity parity: even number of negative edges (or zero). Behavior signatures: exponential growth, exponential collapse, virtuous and vicious cycles.
- **Balancing (B) loops** — the loop dampens disturbances; effects of a change feed back to counteract it. Polarity parity: odd number of negative edges. Behavior signatures: goal-seeking, oscillation (especially with delays), homeostasis.

Polarity parity is the validator: count negative edges in the loop walk; even → R; odd → B. Mis-declared polarity is a hard failure mode (validator-rejected). Genuine loops have a closing edge in the graph; declared loops without closing edges are linear chains mis-labelled.

Delays — the time between a cause and its effect — are first-class elements. Loops with significant delays often produce counterintuitive behavior (oscillation in a balancing loop with long delay; surprising tipping points in reinforcing loops). The structural map marks delays explicitly when present.

### Senge System Archetypes (required for systems-dynamics-structural)

**Core Structure.** Catalog of recurring loop patterns:
- **Fixes That Fail** — short-term fix produces long-term consequences worsening the original problem (one balancing loop addressing symptom; one reinforcing loop produced as side-effect).
- **Shifting the Burden** — symptomatic solution displaces fundamental solution; addiction patterns (two balancing loops competing; symptomatic solution erodes capacity for fundamental).
- **Limits to Growth** — reinforcing loop produces growth until balancing loop kicks in (R loop bumping against B loop).
- **Eroding Goals** — gap between desired and actual closed by lowering goals (balancing loop with goal as variable).
- **Escalation** — two parties view welfare relatively; each takes action threatening the other (two reinforcing loops in mutual amplification).
- **Success to the Successful** — initial advantage produces resources that further the advantage (reinforcing loop with allocation).
- **Tragedy of the Commons** — shared resource overused because individual incentives diverge from collective good (multiple reinforcing loops + one balancing loop with delay).
- **Growth and Underinvestment** — growth approaches limit; investment lag prevents capacity keeping up (reinforcing growth + balancing capacity loop with delay).

Archetype-name-drop failure mode applies: naming the archetype is not sufficient; the matching loop topology must be present in the declared loops with verified polarity.

### Sterman System-Dynamics Modeling (optional for systems-dynamics-structural)

**Core Structure.** Stocks-and-flows formal modeling tradition (Forrester foundational; Sterman standard reference). Distinguishes:
- **Stocks** — accumulations (water in a tank, money in account, people in organization).
- **Flows** — rates of change in stocks (flow into tank, spending rate, hiring rate).
- **Auxiliaries** — derived variables that depend on stocks/flows.
- **Exogenous variables** — driven from outside the system boundary.

Quantitative modeling supports prediction of behavior over time, but the structural map at Tier 2 typically remains qualitative (stocks-and-flows topology with polarity, not numerical simulation). Quantitative escalation routes through dedicated modeling rather than through this mode.

### Meadows Twelve Leverage Points (optional for both T17 modes)

**Core Structure.** Hierarchy of intervention points (least to most effective): numbers → buffers → stock-and-flow structures → delays → balancing loops → reinforcing loops → information flows → rules → self-organization → goals → paradigms → power to transcend paradigms. Used in T17 for transparency only — T17 is descriptive and structural-mapping does not include intervention recommendations. The mention of leverage points names them as a vocabulary if the structural map enables a future intervention discussion in another mode.

### Supply and Demand (required for market-dynamics)

**Core Structure.** A market is modeled as two opposing schedules: the demand schedule (quantity buyers will take at each price, falling in price) and the supply schedule (quantity sellers will offer at each price, rising in price). Each side carries drivers (the non-price factors that shift the whole schedule) and an elasticity (responsiveness of quantity to price). The market read is two-sided by construction: a shock to one side moves price and quantity only as far as the *other* side's elasticity accommodates. Modeling one side while silently fixing the other (one-sided-market) is a hard failure mode. Elasticity is reasoned about qualitatively when no data is given, and flagged wherever it is load-bearing (a read can reverse between elastic and inelastic supply).

### Market Equilibrium (required for market-dynamics)

**Core Structure.** Equilibrium is the price-quantity pair where the quantity demanded equals the quantity supplied — the market clears and no participant has an unmet incentive to change behavior. The equilibrium is named together with the *adjustment process* that reaches it (a shortage pulling price up, entry bidding price down, a queue clearing) and its stability (does the adjustment converge on the equilibrium or push away from it). A conclusion asserted with no settling point and no path to it is the equilibrium-unstated failure mode. Short-run equilibrium (before entry, exit, capacity change, or substitution) is distinguished from long-run equilibrium (after those adjustments work through) — the two frequently differ in direction, and conflating them is timescale-collapse.

---

## Open debates

T17 carries no territory-level open debates at present. The Decision D parse (separating Systems Dynamics into T4 causal and T17 structural variants) is documented in mode-level Caveats and Open Debates, not as a territory-level debate.

---

## Citations and source-tradition attributions

- Forrester, J. W. (1961). *Industrial Dynamics*. MIT Press. Foundational system-dynamics text.
- Senge, P. M. (1990). *The Fifth Discipline*. Doubleday. System archetypes.
- Sterman, J. D. (2000). *Business Dynamics: Systems Thinking and Modeling for a Complex World*. McGraw-Hill. Standard quantitative reference.
- Meadows, D. H. (1999). *Leverage Points: Places to Intervene in a System*. Sustainability Institute.
- Meadows, D. H. (2008). *Thinking in Systems: A Primer*. Chelsea Green.
- Lean / Toyota Production System tradition (foundational for swim-lane and value-stream mapping in process-mapping).
- Marshall, A. (1890). *Principles of Economics*. Macmillan. Supply, demand, equilibrium, and elasticity (foundational for market-dynamics).
- Schumpeter, J. A. (1942). *Capitalism, Socialism and Democracy*. Harper. Creative destruction (market-dynamics).
- Katz, M. L. & Shapiro, C. (1985). "Network Externalities, Competition, and Compatibility." *American Economic Review* 75(3). Network effects and critical mass (market-dynamics).
- Kahneman, D. & Tversky, A. (Various). Heuristics-and-biases catalog (foundational substrate).

*End of Framework — Process and System Analysis.*
