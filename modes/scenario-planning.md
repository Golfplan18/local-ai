---
title: scenario-planning
nexus: obsidian
type: mode
writing: no
date created: 2026/03/23
date modified: 2026/03/31
---

# MODE: Scenario Planning

## TRIGGER CONDITIONS

Positive triggers: A decision depends on future conditions that are genuinely uncertain, strategic planning over a timeframe exceeding one year, "what could happen," "how should we prepare," "what if the environment changes," the analysis defaults to a single "official future" that needs challenging. The user is making a commitment that will be difficult to reverse and the environment could take multiple shapes.

Negative triggers: IF the user wants to map present-state tradeoffs between alternatives, THEN route to Constraint Mapping — present conditions, not future uncertainty. IF the user wants to trace a causal chain backward from a failure, THEN route to Root Cause Analysis. IF the user wants to choose between options based on probability and payoff, THEN route to Decision Under Uncertainty — scenario planning maps multiple futures, decision analysis chooses among them.

## EPISTEMOLOGICAL POSTURE

The future is fundamentally uncertain and multiple. Multiple plausible futures are simultaneously valid — no single scenario is designated "most likely." Single-point forecasting is explicitly rejected. The "official future" — the straight-line extrapolation of current trends — is the specific target of challenge. Uncertainty is treated as a structuring device, not an impediment. The purpose of scenarios is not to predict the future but to modify decision-makers' mental models and prepare for contingencies.

## DEFAULT GEAR

Gear 4. Independent scenario generation is the minimum for reliable output. IF the Depth model sees the Breadth model's scenarios before developing its own, the scenarios converge rather than spanning the possibility space. Independent generation, followed by cross-evaluation, produces genuinely different futures.

## RAG PROFILE

Retrieve strategic foresight literature, trend analyses, weak signal reports, and historical analogues of structural change in the relevant domain. Retrieve domain-specific driving forces (STEEP: Social, Technological, Economic, Environmental, Political). IF the user's vault contains prior strategic work, retrieve it for context. Deprioritize forecasts and predictions — these are single-point estimates that scenario planning is designed to transcend.

## DEPTH MODEL INSTRUCTIONS

White Hat directives:
1. Identify the focal question or strategic decision the scenarios must address. State it precisely.
2. Map all driving forces in the relevant environment. Classify each as a predetermined element (will happen regardless of scenario) or a critical uncertainty (could go either way).
3. For each critical uncertainty, assess the range of plausible outcomes and identify observable leading indicators that would signal which outcome is materializing.

Black Hat directives:
1. Evaluate the Breadth model's scenarios for internal consistency — does each scenario's causal logic hold? Could the elements of each scenario coexist?
2. Test whether the scenarios are genuinely structurally distinct or are variations of the same future with different magnitudes.
3. Stress-test proposed strategies against each scenario. Identify strategies that break under specific scenarios and conditions under which they break.

## BREADTH MODEL INSTRUCTIONS

Green Hat directives:
1. From the two most critical uncertainties, construct a 2×2 matrix with four structurally distinct scenarios. Each scenario occupies one quadrant.
2. Develop each scenario with a narrative: a name, a coherent causal logic explaining how this future came about, and the key characteristics of the world it describes. Scenarios must be plausible, internally consistent, and genuinely different from each other.
3. Generate at minimum one "wild card" scenario that falls outside the 2×2 matrix — a plausible future driven by a factor not captured in the two primary uncertainties.

Yellow Hat directives:
1. For each scenario, identify opportunities — what becomes possible in this future that is not possible now?
2. Identify robust strategies — approaches that work across all or most scenarios rather than depending on one future materializing.
3. Identify contingent actions — specific steps that should be taken IF specific leading indicators appear, tied to specific scenarios.

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Scenario Distinctiveness.** 5=each scenario represents a structurally different future with distinct causal logic. 3=scenarios are distinct but two share significant structural overlap. 1=scenarios are variations in magnitude rather than genuinely different futures.
6. **Uncertainty/Predetermined Separation.** 5=critical uncertainties cleanly distinguished from predetermined elements with reasoning for each classification. 3=distinction made but one element miscategorized. 1=no distinction drawn.
7. **Strategic Actionability.** 5=leading indicators identified for each scenario, robust strategies distinguished from scenario-dependent strategies, contingent actions specified. 3=some strategic implications drawn but leading indicators or contingent actions missing. 1=scenarios presented without strategic translation.

## CONTENT CONTRACT

The output is complete when it contains:

1. **Focal question** — the strategic decision or question the scenarios address.
2. **Driving forces** — key forces shaping the future environment, classified as predetermined or uncertain.
3. **Critical uncertainties** — the two most important uncertainties forming the scenario axes, with reasoning for their selection.
4. **Scenario matrix** — 2-4 structurally distinct scenarios, each with a name, narrative, and internally consistent causal logic.
5. **Leading indicators** — specific observable signals indicating which scenario is emerging. At minimum two per scenario.
6. **Strategic implications** — robust strategies (work across scenarios), fragile strategies (break under specific scenarios), and contingent actions tied to specific indicators.

## KNOWN FAILURE MODES

**The Good/Bad/Medium Trap:** Constructing scenarios as optimistic, pessimistic, and baseline rather than as structurally distinct futures. Correction: Each scenario must have its own causal logic. A "good" scenario and a "bad" scenario are not structurally distinct if they differ only in magnitude.

**The Official Future Trap:** Constructing three "alternative" scenarios and one "most likely" scenario that is actually the official future relabeled. Correction: No scenario receives a probability or "most likely" designation. All are equally plausible for planning purposes.

**The Story Without Strategy Trap:** Producing compelling scenario narratives without translating them into strategic implications, leading indicators, or actionable contingent plans. Correction: Every scenario must produce specific leading indicators and strategic implications. Narratives without strategy are incomplete.

**The Certainty Masquerade Trap:** Classifying a genuine uncertainty as a predetermined element because it would be uncomfortable to treat as uncertain. Correction: Test each "predetermined" classification by asking: what specific evidence makes this unavoidable rather than merely likely?

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN the analysis moves toward endorsing one scenario as most likely, THEN pause — Scenario Planning does not predict. All scenarios are planning tools, not forecasts.

**Structural distinctiveness guard rail.** Before finalizing scenarios, verify: if I remove the value-laden adjectives (good, bad, disruptive), are these scenarios still distinguishable by their causal logic? IF not, redesign.

**Strategy translation guard rail.** Do not present scenarios without strategic implications. The scenarios exist to inform decision-making, not to demonstrate imagination.

## TOOLS

Tier 1: C&S (consequence mapping across time horizons for each scenario), CAF (identify all driving forces), FIP (prioritize which uncertainties are most critical), OPV (map how different stakeholders experience different scenarios).

Tier 2: Load based on domain signals. Political and Social Analysis Module for geopolitical scenarios.

Enrichment framework: Historical-analogical reasoning — historical parallels to current driving forces inform scenario construction. The Shell methodology explicitly uses historical analogues as inputs.

## TRANSITION SIGNALS

- IF the user wants to choose between strategies surfaced by scenario analysis → propose **Decision Under Uncertainty** or **Constraint Mapping**.
- IF the scenarios reveal institutional interests shaping the driving forces → propose **Cui Bono**.
- IF the user begins building a specific plan or deliverable based on scenario results → propose **Project Mode**.
- IF the scenarios expose a foundational assumption the user wants to question → propose **Paradigm Suspension**.
- IF the driving forces involve complex feedback loops → propose **Systems Dynamics** to model the dynamics before constructing scenarios.
