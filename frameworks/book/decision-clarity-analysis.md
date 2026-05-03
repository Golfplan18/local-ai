
# Decision Clarity Analysis Framework

*A Framework for Producing a Decision Clarity Document for a Decision-Maker Facing a Tangled Problem with Stakeholder Value Conflicts, Evolving Definitions, and No Objective Stopping Condition*

*Version 2.0 — restructured 2026-05-01 from the v1.0 Wicked Problems Framework per Decision H of the architectural lock.*

*Bridge Strip: `[DCA — Decision Clarity Analysis]`*

---

## Architectural Note (read first)

This framework was previously titled "Wicked Problems Framework" (v1.0, 2026-04-24). Per Decision H of the 2026-05-01 architectural lock, the analytical work this framework performs has been split into two operations sharing source material:

1. **Wicked Problems Analysis (mode)** — molecular integrated multi-perspective analysis per research report §6.2. Produces a synthesis artifact (reconciled framing + dynamic projection + intervention catalog + stress-test findings + residual tensions). Lives in `/Users/oracle/Documents/vault/Modes/wicked-problems.md`. T2 (Interest and Power Analysis), depth-molecular.

2. **Decision Clarity Analysis (mode + this framework)** — depth-molecular operation that produces a **Decision Clarity Document** for a decision-maker. The mode will be built in Wave 4 of Phase 4. **This framework carries the procedural detail (elicitation prompts, intermediate output formats, Decision Clarity Document template) for the decision-clarity mode.** Phase 2 prepares the framework's structural alignment based on the existing 4-stage protocol; Wave 4 finalizes the mode spec to align fully.

The split honors the parsing principle (Decision D / H): "different analytical paths even with shared goal and data = different operations." Wicked Problems Analysis is integrated multi-perspective; Decision Clarity Analysis is decision-maker-output-shaped. Both are in T2; both compose similar component modes; they differ in the synthesis stages and the output contract.

---

## How to Use This File

This is a procedural framework that supports the (Wave 4) `decision-clarity` mode. It operates when a problem has been provisionally identified as **wicked** in Rittel and Webber's sense — characterised by contested problem definitions, fundamental value conflicts between stakeholders, the absence of an objective stopping condition, and irreversibility of intervention. The framework does not solve the problem. It produces a **Decision Clarity Document** that makes the structure of the dilemma legible to whoever holds decision authority, so that any decision taken is taken with eyes open about what is being chosen and what is being sacrificed.

DCA (this framework's operation) runs after PEF has flagged a problem as wicked (or after the user invokes the `decision-clarity` mode directly via the four-stage pre-routing pipeline). It draws on the existing analytical modes — Competing Hypotheses, Cui Bono, Steelman Construction, Systems Dynamics (causal variant), Scenario Planning, and Red Team — at specific stages where each mode's epistemic posture matches the analytical work required.

When the user wants the integrated multi-perspective analysis (rather than the decision-maker-output document), the orchestrator routes to `wicked-problems` instead. Both modes draw on the same component-mode set; the difference is in the synthesis stages and output contract (see the architectural note above).

Three invocation paths are supported (see INPUT CONTRACT below):

**User invocation:** the user invokes `decision-clarity` directly (or DCA via this framework) with a problem description. The framework opens with brief progressive questioning to establish the problem domain and stakeholder landscape.

**Handoff from Problem Evolution Framework (PEF):** PEF's wicked-problem detection check has fired and PEF has handed off a structured package. WPF acknowledges the handoff and skips Stage 1 questioning that PEF has already answered.

**Escalation from Cui Bono mode:** the cui-bono mode has produced output showing wicked-problem indicators (incompatible benefit structures, no net-positive intervention, fundamental value conflicts in the distribution of benefits and harms) and has surfaced an escalation prompt offering full WPF analysis. WPF inherits the cui-bono findings into Stage 3 rather than regenerating them.

---

## Table of Contents

- Purpose
- Input Contract
- Output Contract
- Execution Tier
- Epistemological Posture
- The Four-Condition Trigger
- Handoff Acknowledgement Protocol
- Stage 1: Problem Space Mapping
- Stage 2: Value Conflict Identification
- Stage 3: Consequence Landscape Modeling
- Stage 4: Tradeoff Transparency and Decision Clarity
- Output Assembly
- Guard Rails
- Named Failure Modes
- When Not to Invoke This Framework
- Appendix A: Decision Clarity Document Template

---

## PURPOSE

Produce a Decision Clarity Document that makes a wicked problem's structure legible to a decision-maker. The framework does four things in sequence:

1. **Maps the contested problem definitions** held by different stakeholder groups, without reconciling them.
2. **Identifies which stakeholder value conflicts are fundamental** — meaning both values cannot be fully honoured simultaneously regardless of how much information is available — versus which are merely resolvable through better information or negotiation.
3. **Models the consequence landscape across each available intervention**, including direct, second-order, and third-order effects across multiple time horizons, with explicit attention to who benefits and who bears costs.
4. **Translates each intervention into a tradeoff statement** that names what is being chosen, what is being sacrificed, which stakeholder groups the intervention cannot satisfy, and what consequences are being accepted in exchange.

WPF does not recommend a decision. It makes the decision maximally legible. The judgement is the user's — or, in policy contexts, the user's principal's. The framework's purpose is to ensure that whoever decides cannot later claim they did not know what they were trading away.

The framework is bound by a parallel of PEF's Universal Problem-Definition Lock: WPF cannot silently reconcile competing problem definitions, dissolve fundamental value conflicts, or recommend an intervention as "best." Reconciliation, dissolution, and recommendation are decision-maker prerogatives, not analytical outputs.

## INPUT CONTRACT

Required (varies by invocation path):

**Path A — User invocation:**
- **User's Problem Description**: Natural language description of the problem and the stakeholder landscape, to whatever level of detail the user has. Partial or contested descriptions are expected — that's why WPF is being invoked.
- **Stance toward stakeholders** (optional): if the user is themselves a stakeholder with a position, they can declare it; this informs Stage 4's advocate-stance Red Team passes but does not bias Stage 1 or Stage 2.

**Path B — Handoff from PEF:**
- **PEF Handoff Package**: structured object containing:
  - The current Problem Definition from PEF's PED.
  - The four-condition trigger evaluation showing which conditions fired.
  - Stakeholder information already gathered (stakeholders named, their positions, prior PEF iterations' notes).
  - The PED's Excluded Outcomes (Lock-protected) — these constrain Stage 4's intervention list.
  - The PED's Constraints (Hard / Soft / Working Assumption) — these constrain Stage 3's modeling.

**Path C — Escalation from cui-bono mode:**
- **Cui Bono Output**: the prior turn's cui-bono analysis containing institutional authorship, beneficiaries and cost-bearers, distributional parameters, and the alternative design constructed from opposite constituency interests.
- **Wicked-problem indicator evidence**: which of the cui-bono escalation indicators fired (incompatible benefit structures, no net-positive intervention, fundamental value conflicts in distribution).

Optional (all paths):
- **Prior analyses or research** the user has already produced.
- **Time horizon constraints** if the decision must be made by a specific date.
- **Stakeholder list** if the user has already enumerated the parties involved.

## OUTPUT CONTRACT

Primary output:
- **Decision Clarity Document** — structured markdown following the template in Appendix A. Contains four labelled sections corresponding to the four stages, plus an executive summary.

Executive Summary (top of document):
- **Type of problem** — single sentence stating the problem and why it is wicked.
- **Number of fundamental value conflicts identified** — count + one-line characterisation of each.
- **Number of interventions modeled** — count + one-line characterisation of each.
- **What WPF does NOT do** — single sentence reminder that no recommendation follows; the decision is the user's.

Secondary outputs:
- **Reclassification Recommendation** if either Stage 1 or Stage 2 gates fail (problem may not be wicked after all — see those stages).
- **Mode Transition Suggestions** if WPF analysis surfaces work better suited to a different mode (e.g., paradigm-suspension if a stakeholder's framework is itself the load-bearing problem).

The document is labelled at the top with the bridge-strip indicator:

```
[WPF — Wicked Problems Analysis]
```

## EXECUTION TIER

Specification — this document is model-agnostic. WPF orchestrates other modes (competing-hypotheses, cui-bono, steelman-construction, systems-dynamics, scenario-planning, the red-team modes) which carry their own gear, RAG profile, and cascade specifications. WPF itself runs as a stage-by-stage protocol; the underlying modes execute at their own gears as invoked.

---

## EPISTEMOLOGICAL POSTURE

A wicked problem is not a hard tame problem. The categorical difference, traced from Rittel and Webber (1973) through Ackoff's "messes" through Churchman and Ulrich's boundary-setting to contemporary Problem Structuring Methods, is that **the problem definition itself is contested between stakeholders whose values cannot all be simultaneously honoured**. This is not an information failure that more research will resolve. It is a structural feature of pluralism.

The posture WPF takes:

1. **Multiple problem definitions are legitimate.** WPF does not select one stakeholder's framing as "the real" problem. Each major stakeholder's framing is documented as their own.
2. **Some value conflicts are fundamental.** Where two values cannot be fully honoured simultaneously regardless of information available, the framework names this and does not pretend the conflict is resolvable through further analysis.
3. **Solutions are better-or-worse, not true-or-false.** Per Rittel: judgement varies by stakeholder; an "objectively best" intervention does not exist for problems with this structure.
4. **Tradeoffs are real, not rhetorical.** The framework refuses to dissolve tradeoffs through synthesis-language ("balanced approach," "win-win solution," "stakeholder alignment"). When a tradeoff exists, it is named in the form: *"this intervention prioritises X and subordinates Y; the following stakeholders cannot be satisfied by this choice."*
5. **The decision-maker has no right to be wrong but no right to pretend there is no decision.** Per Rittel's tenth property: planners bear direct responsibility for consequences. WPF's job is to make sure the decision-maker cannot later claim ignorance about what was traded.

The framework deliberately resists the patterns that fail wicked problems:

- **Premature closure** on a single problem framing → counteracted by Stage 1's competing-hypotheses pass.
- **Synthesis-as-resolution** of fundamental value conflict → counteracted by Stage 2's explicit fundamental-vs-resolvable classification.
- **Optimism about consequence prediction** → counteracted by Stage 3's multi-horizon Scenario Planning + Cui Bono distributional analysis.
- **Sycophantic framing** of a chosen intervention → counteracted by Stage 4's Red Team passes in advocate stance per subordinated stakeholder group.

## THE FOUR-CONDITION TRIGGER

WPF is invoked when a problem meets at least three of these four conditions. The same four conditions are used by PEF's wicked-problem detection check.

1. **Definition shifts under perspective change.** The problem definition shifts materially when examined from different stakeholder perspectives. The same situation produces different "what the problem is" answers depending on whose values frame the question.

2. **Solutions generate new problem dimensions.** Proposed solutions generate new problem dimensions not present in the original definition. Implementing intervention A creates problems B, C, and D that were not part of the problem space before A was proposed.

3. **No objective stopping condition.** "Solved" means different things to different stakeholders. There is no single test for completion that all parties would accept.

4. **Value conflicts are fundamental.** Conflicts between stakeholders trace to values that cannot all be fully honoured simultaneously regardless of how much information is gathered or how much negotiation occurs. The conflict is structural, not informational.

If at least three conditions are true, the problem is classified as wicked and WPF is invoked. If fewer than three conditions are true but the problem has some wicked characteristics, the problem is classified as **partial complexity** and routed to ordinary analysis (PEF, Constraint Mapping, or another mode). The four-condition threshold is not arbitrary — it represents the minimum structural pattern at which conventional problem-solving methods systematically fail.

If the user invokes WPF directly without a prior PEF run, WPF performs the four-condition check itself before proceeding past Stage 1's gate.

## HANDOFF ACKNOWLEDGEMENT PROTOCOL

WPF opens with an acknowledgement of which invocation path is active. This is not ceremonial — it determines what work is skipped and what work is performed.

### Path A — User invocation (full sweep)

> Invoking the Wicked Problems Framework on the problem you've described. Before Stage 1 begins, I'll ask a brief set of questions to establish the stakeholder landscape and confirm this problem meets the four-condition threshold. If at the gate after Stage 1 it turns out the problem isn't actually wicked, I'll say so and recommend a more appropriate framework or mode.

Then proceed with progressive questioning at the start of Stage 1.

### Path B — Handoff from PEF

> WPF receiving handoff from Problem Evolution Framework. The four-condition check fired with [N/4] conditions met: [list]. Stakeholders already identified by PEF: [list]. Excluded Outcomes inherited (Lock-protected — these constrain Stage 4): [list]. Constraints inherited: [Hard: list / Soft: list / Working Assumption: list]. Skipping Stage 1's open questioning and beginning at Stage 1's confirmation gate.

Then proceed to Stage 1's confirmation gate using PEF's stakeholder material.

### Path C — Escalation from Cui Bono

> WPF receiving escalation from Cui Bono mode. Inheriting the cui-bono findings: institutional author [name], beneficiaries [list], cost-bearers [list], distributional parameters [list], alternative-constituency design [summary]. Wicked-problem indicators that fired: [list]. Stage 3's Cui Bono pass will not be regenerated; the existing analysis is integrated as the first intervention's distributional layer. Beginning at Stage 1.

Then proceed with Stage 1.

### Acknowledgement requirement

The acknowledgement is a structural check (G-WPF-HA): WPF cannot proceed without one. This guarantees the user knows which input WPF is operating on and what is being skipped. Silent inference of invocation path is forbidden.

---

## STAGE 1 — PROBLEM SPACE MAPPING

**Purpose:** Establish that the problem definition is contested. Document the competing framings held by different stakeholder groups without reconciling them.

**Mode active:** competing-hypotheses

**Inputs:**
- The problem description (user-provided or inherited via handoff).
- The stakeholder landscape (user-provided, PEF-inherited, or elicited via Stage 1's questioning sequence on Path A).

**Process:**

1. **Identify all major stakeholder groups.** A "major" stakeholder is any group whose interests, capacity, or values would be materially affected by any plausible intervention or by inaction. The threshold for inclusion is *materially affected*, not *politically organised* — unrepresented or weakly-organised stakeholders count.

2. **For each stakeholder group, extract four things:**
   - Their definition of the problem (what they would say is wrong).
   - Their assumed cause (what they think is producing the problem).
   - Their desired outcome (what "solved" looks like to them).
   - Their solution criteria (the observable conditions they would accept as evidence of resolution).

3. **Do NOT reconcile the four extracted things across stakeholders.** Document them as distinct and legitimate framings. The product of this stage is a map of competing problem definitions, not a synthesised summary.

4. **Apply Competing Hypotheses methodology** to the framings: treat each stakeholder's problem definition as a hypothesis about the situation, evaluate which observable evidence supports or contradicts each framing, and record the evidence-framing matrix. This matrix is part of Stage 1's output.

**Output of Stage 1:**

A structured map containing:
- One block per stakeholder group with the four extracted things.
- A competing-hypotheses-style matrix showing which observable evidence supports or contradicts each framing.
- Explicit attribution: every framing is tagged with the stakeholder group whose values produced it.

**Stage 1 Confirmation Gate:**

Confirm that **at least two stakeholder groups hold incompatible problem definitions** before advancing to Stage 2.

- IF at least two stakeholders hold incompatible definitions → advance to Stage 2.
- IF all stakeholders agree on the problem definition → flag that this may not be a wicked problem. Recommend returning to Framework — Problem Evolution for reclassification (the problem may be merely complex, not wicked). Output the partial Stage 1 work as a reclassification recommendation. Halt WPF execution.
- IF stakeholders disagree but the disagreement is about means rather than the problem definition itself → flag that this may be a constraint-mapping or strategic-interaction case rather than a wicked problem. Recommend the appropriate mode and halt.

The gate is not perfunctory. Many problems labelled "wicked" by users are actually complex-but-tame problems where stakeholders agree on the goal. Sending those to Stage 2 produces synthetic value conflicts that don't exist.

## STAGE 2 — VALUE CONFLICT IDENTIFICATION

**Purpose:** Establish *why* consensus is structurally impossible rather than merely politically difficult. Distinguish fundamental conflicts (cannot be resolved by information or negotiation) from resolvable conflicts (could be resolved with better information or longer negotiation).

**Mode active:** steelman-construction (applied per stakeholder group)

**Inputs:**
- Stage 1's stakeholder map.

**Process:**

1. **For each major stakeholder group, run Steelman Construction.** Build the strongest possible case for that stakeholder's position — the version a thoughtful, committed advocate of that stakeholder's values would endorse if asked "what is the best version of your case?"
   - Steelman Construction's mirror test applies: a thoughtful proponent must recognise the steelman as their own argument strengthened, not weakened.
   - The steelman must be logically coherent within the stakeholder's value framework, not merely sympathetic-sounding.
   - Tinmanning is a Stage 2 failure — see Named Failure Modes below.

2. **For each steelmanned position, identify the underlying value(s).** A value is the principle or end the position serves. *"Workers should be protected from arbitrary dismissal"* serves the value *"economic security as a precondition for human dignity."* Name the values explicitly. Vague value-language ("fairness", "freedom") fails this step — push to specific operational expressions ("freedom from interference by the state in market transactions" vs. "freedom from material deprivation").

3. **Map the value conflicts.** For each pair of stakeholder groups, identify which values are in direct conflict — meaning honouring one group's value subordinates another group's value below their threshold of acceptance.

4. **Classify each conflict:**
   - **Fundamental** — both values cannot be fully honoured simultaneously regardless of how much information is available. Example: maximum economic liberty for property-owners vs. maximum economic security for workers — these can be traded but not both maximised.
   - **Resolvable through information** — the conflict is real but new evidence could change one party's position (e.g., a disagreement about what intervention X actually does, where studies could settle it).
   - **Resolvable through negotiation** — the conflict is real but a tradeable exchange exists (e.g., compensation, side-payments, structural arrangements that satisfy both parties' minima).

5. **Produce the value conflict map**, listing every conflict with its classification and reasoning.

**Output of Stage 2:**

A value conflict map containing:
- One steelmanned position per stakeholder group, with the underlying values explicit.
- A pairwise value conflict matrix between stakeholder groups.
- A classification for each conflict: Fundamental / Resolvable-by-information / Resolvable-by-negotiation.
- For each Fundamental conflict, a one-paragraph explanation of why information and negotiation cannot resolve it.

**Stage 2 Gate:**

At least one Fundamental value conflict must be present.

- IF at least one Fundamental conflict → advance to Stage 3.
- IF all conflicts are classified as Resolvable-by-information or Resolvable-by-negotiation → flag for reclassification. The problem may be merely difficult rather than wicked. Recommend continued PEF iteration with targeted information-gathering or negotiation. Output the partial Stages 1-2 work as a reclassification package. Halt WPF execution.

## STAGE 3 — CONSEQUENCE LANDSCAPE MODELING

**Purpose:** Map who benefits, who is harmed, and what cascades through the system across each available intervention — including second- and third-order effects, and across multiple time horizons.

**Modes active:** cui-bono, systems-dynamics, scenario-planning

**Inputs:**
- Stage 1's stakeholder map.
- Stage 2's value conflict map.
- The PED's Excluded Outcomes (if Path B handoff) — these may eliminate intervention candidates from Stage 3's set.
- The cui-bono prior output (if Path C escalation) — integrated as the first intervention's distributional layer.

**Process:**

1. **Enumerate the available interventions.** Include:
   - Interventions currently under consideration by stakeholders.
   - Interventions historically attempted (with outcomes documented).
   - The null intervention (do nothing — explicitly modeled as a choice with consequences, not as the absence of choice).
   - Interventions a thoughtful party might propose but which no stakeholder has yet championed.

2. **For each intervention, run three parallel analyses:**

   **(a) Cui Bono pass.** Trace the institutional authorship, beneficiaries, cost-bearers, and distributional parameters. *(If Path C escalation, this analysis already exists for the original intervention and is inherited rather than regenerated.)*

   **(b) Systems Dynamics pass.** Identify feedback loops, delays, leverage points, and counterintuitive behaviours that the intervention will activate or interact with. The output is a feedback-structure map showing where the intervention's effects cycle back to alter its own preconditions.

   **(c) Scenario Planning pass across three time horizons:**
   - **Immediate** (0-12 months): direct effects, first-order responses, immediate winners and losers.
   - **Medium-term** (1-5 years): second-order responses, displaced costs, regulatory or market reactions, coalitional realignments.
   - **Long-term** (5+ years): third-order systemic effects, generational impacts, irreversibility considerations.
   
   Per Scenario Planning's contract, surface 2-4 plausible futures per horizon, identify driving forces and critical uncertainties, and name the leading indicators that distinguish which future is materialising.

3. **For each intervention, model how the intervention reshapes the problem definition itself.** Per Rittel's first property: information needed to understand the problem depends on the idea for solving it. Implementing intervention A makes some problem-aspects newly visible and others newly invisible. This reshaping is itself a consequence and is named explicitly.

**Output of Stage 3:**

A consequence landscape document, structured by intervention, containing:
- For each intervention:
  - Cui Bono distributional layer (authors, beneficiaries, cost-bearers, parameters).
  - Systems Dynamics feedback-structure map.
  - Scenario Planning narratives across the three time horizons (2-4 scenarios per horizon).
  - Problem-definition reshaping note: how the intervention changes what becomes visible and invisible.
- Cross-intervention table summarising who-wins / who-loses at each horizon.

## STAGE 4 — TRADEOFF TRANSPARENCY AND DECISION CLARITY

**Purpose:** Translate Stage 3's consequence landscape into a decision-maker-legible tradeoff statement per intervention. This stage **does not recommend a decision**. It makes the decision maximally legible.

**Modes active:** red-team-advocate (applied per subordinated stakeholder group per intervention); red-team-assessment (optional, for the user-favoured intervention if one exists)

**Inputs:**
- Stage 1's stakeholder map.
- Stage 2's value conflict map.
- Stage 3's consequence landscape.

**Process:**

1. **For each intervention modeled in Stage 3, produce a tradeoff statement** in the following structure:

   - **Intervention name and one-sentence description.**
   - **Beneficiaries** — the stakeholder groups this intervention benefits, with reference to which of their values it honours.
   - **Cost-bearers** — the stakeholder groups this intervention costs, with reference to which of their values it subordinates.
   - **Values prioritised** — the values the intervention honours.
   - **Values subordinated** — the values the intervention subordinates.
   - **Second- and third-order consequences accepted** — drawn from Stage 3's Scenario Planning + Systems Dynamics output.
   - **Stakeholder groups this intervention CANNOT satisfy** — the groups whose core values are incompatible with this choice. These groups will not accept the intervention as resolution; their values are subordinated below their threshold of acceptance. Naming this preempts the false-consensus failure mode.

2. **Stress-test each tradeoff statement using `red-team-advocate`, once per subordinated stakeholder group.**
   - For each stakeholder group whose values are subordinated by intervention X, invoke `red-team-advocate` with that stakeholder group as the "client."
   - The red-team-advocate pass produces the strongest case AGAINST intervention X from that subordinated stakeholder's perspective — using their values as the framework for attack.
   - The output is incorporated as part of the tradeoff statement's "Cannot satisfy" section, naming the strongest objection from each subordinated group.
   - This is automatic: Stage 4 dispatches `red-team-advocate` for each (intervention × subordinated-stakeholder) pair.

3. **Optional: `red-team-assessment`.** If the user has declared a favoured intervention, an additional `red-team-assessment` pass on that intervention is offered — checking whether the user's favoured intervention has internal flaws independent of stakeholder objections. This is opt-in (the user invokes it explicitly); WPF does not assume the user has a favourite.

4. **Sycophantic-inverse self-check.** Before emitting the tradeoff statement, verify that the cost-bearers and subordinated values are named with the same specificity as the beneficiaries and prioritised values. Asymmetric specificity (vague costs, specific benefits, or vice versa) is the signature of advocacy disguised as analysis. Per cui-bono's symmetry guard rail: apply the standard to both sides.

**Output of Stage 4 (Decision Clarity Document):**

One tradeoff statement per intervention, formatted for direct use by the decision-maker. Each statement is self-contained — readable without reference to Stages 1-3, though grounded in them. The statements are presented side-by-side for comparison, NOT ranked, NOT recommended.

The Decision Clarity Document closes with:

- **What this analysis does NOT do** — single paragraph noting that no recommendation has been made, no intervention has been ranked as best, and no synthesis has been offered. The decision is the user's.
- **What additional information would change the analysis** — list of empirical questions whose answers would materially change Stage 1, 2, or 3 outputs (informs whether further investigation is worth doing before deciding).
- **Reversibility note per intervention** — Rittel's "every wicked-problem solution is a one-shot operation" — for each intervention, note which effects are reversible if the decision turns out badly and which are not.

---

## OUTPUT ASSEMBLY

The complete WPF output delivered to the user contains:

1. **Bridge strip indicator** at the top:

   ```
   [WPF — Wicked Problems Analysis]
   ```

2. **Executive Summary** (≤ 200 words, plain language, readable by a non-technical audience):
   - Type of problem and why it is wicked.
   - Number of fundamental value conflicts identified.
   - Number of interventions modeled.
   - What this analysis does NOT do.

3. **Stage 1 — Problem Space Map** (labelled section).

4. **Stage 2 — Value Conflict Map** (labelled section).

5. **Stage 3 — Consequence Landscape** (labelled section, one block per intervention).

6. **Stage 4 — Decision Clarity Document** (labelled section, one tradeoff statement per intervention, plus the closing notes from Stage 4 above).

Each stage's output is preserved separately so the decision-maker can drill into the analysis behind any tradeoff statement.

## GUARD RAILS

**G-WPF-PD (Problem-Definition non-reconciliation guard rail).** Stage 1 must NOT reconcile competing problem definitions into a synthesis. If the output of Stage 1 contains a "unified" problem statement, the framework has failed.

**G-WPF-VC (Value-Conflict non-dissolution guard rail).** Stage 2 must NOT dissolve fundamental conflicts through synthesis-language. If a Fundamental conflict appears in the output as "balanced approach" or "win-win opportunity" or "stakeholder alignment," the framework has failed.

**G-WPF-NR (Non-Recommendation guard rail).** Stage 4 must NOT rank or recommend an intervention. The Decision Clarity Document presents tradeoffs side-by-side; ranking is decision-maker prerogative. If the output contains language like "intervention X is best" or "we recommend Y," the framework has failed. *Excepted:* the optional user-invoked `red-team-assessment` pass on a user-favoured intervention does not violate this rule, because the user has already declared the favourite — the red-team-assessment is checking it, not selecting it.

**G-WPF-HA (Handoff Acknowledgement guard rail).** WPF must open with an acknowledgement of which invocation path is active. Silent inference is forbidden.

**G-WPF-SY (Symmetry guard rail).** Specificity must be symmetric: cost-bearers and subordinated values are named with the same level of detail as beneficiaries and prioritised values. Asymmetric specificity is advocacy disguised as analysis.

**G-WPF-RT (Red Team mode integrity).** Stage 4's automatic red-team passes use `red-team-advocate` per subordinated stakeholder. If the consolidator returns `red-team-assessment` findings for a Stage 4 pass, that's a mode-mix failure — surface and rerun.

**G-WPF-EX (Excluded Outcomes preservation — Path B only).** Interventions modeled in Stage 3 must not contradict Excluded Outcomes inherited from PEF. PEF's Excluded Outcomes are Lock-protected; WPF cannot silently introduce interventions that violate them.

**G-WPF-RC (Reclassification honesty).** If Stage 1 or Stage 2 gates fail, WPF halts and recommends reclassification — it does not press through with synthetic findings to satisfy the request to produce a wicked-problem analysis.

## NAMED FAILURE MODES

**The False-Consensus Trap.** Stage 1 produces a "unified" problem statement that papers over the actual disagreement between stakeholders. Correction: enforce G-WPF-PD; if stakeholders disagree, the output preserves the disagreement.

**The Synthesis-as-Resolution Trap.** Stage 2 dissolves a Fundamental value conflict through synthesis-language ("balanced approach", "stakeholder alignment", "win-win"). Correction: enforce G-WPF-VC; Fundamental conflicts are named as such and not dissolved.

**The Sycophantic-Recommendation Trap.** Stage 4 ranks one intervention as best despite WPF's non-recommendation rule. Correction: enforce G-WPF-NR; if the user wants a recommendation, that is a constraint-mapping or decision-under-uncertainty task downstream of WPF, not WPF's output.

**The Tinman Trap (inherited from Steelman Construction).** Stage 2's per-stakeholder steelmans are designed to be defeated rather than honestly strengthened. Correction: apply Steelman Construction's mirror test inside Stage 2.

**The Asymmetric-Specificity Trap.** Stage 4 names beneficiaries and prioritised values with rich specificity but cost-bearers and subordinated values with vague hand-waving. Correction: enforce G-WPF-SY; if the cost side is specific, the benefit side must be specific to the same degree.

**The Premature-Wicked Trap.** WPF is invoked on a problem that is merely complex (not wicked). Stage 1 or Stage 2 will detect this via gate failure. Correction: trust the gates; recommend reclassification rather than fabricating value conflicts.

**The Stakeholder-Erasure Trap.** Stage 1 omits a stakeholder group whose interests are materially affected because that group is unrepresented or weakly organised. Correction: the threshold for inclusion is *materially affected*, not *politically organised*. Per Ulrich's CSH: the question "who speaks for the affected" is itself a boundary-setting question.

**The Reversibility-Blindness Trap.** Stage 4 omits the per-intervention reversibility note. Correction: every intervention's tradeoff statement closes with which effects are reversible and which are not. Per Rittel: every wicked-problem solution is a one-shot operation.

**The Optimism-Cascade Trap.** Stage 3's Scenario Planning produces only favourable scenarios across all three horizons. Correction: per Scenario Planning's contract, 2-4 plausible futures per horizon spanning the realistic range, not the favourable subset.

**The Solution-Reveals-Problem Trap (failure to apply Rittel's first property).** Stage 3 omits the problem-definition reshaping note for one or more interventions. Correction: every intervention reshapes what about the problem becomes visible vs. invisible; this is a structural consequence and is named.

## WHEN NOT TO INVOKE THIS FRAMEWORK

Not all hard problems are wicked. The four-condition trigger exists precisely to filter. WPF should NOT be invoked when:

- **The problem is complex but tame.** Stakeholders agree on what "solved" looks like even if they disagree on how to get there. Use Constraint Mapping or Decision Under Uncertainty.
- **The problem is contested but the conflict is resolvable through information.** Use Competing Hypotheses (or PEF) to identify the diagnostic information that would settle the dispute.
- **The problem is contested but the conflict is resolvable through negotiation.** Use Strategic Interaction to model the bargain.
- **The problem is a paradigm question, not a stakeholder-conflict question.** Use Paradigm Suspension to challenge the foundational framework rather than treating it as a value conflict.
- **The user wants a recommendation.** WPF refuses to recommend; if the user wants a recommendation, the appropriate flow is WPF first (to make the tradeoffs legible) and then a downstream Constraint Mapping or Decision Under Uncertainty session that applies the user's own value weights to the WPF output.
- **The problem is genuinely simple.** Use the simple or standard catch-all modes.

WPF is the heaviest analytical framework in the Ora system because wicked problems are the hardest analytical objects. Using it on lighter problems wastes effort, and worse, fabricates value conflicts where none structurally exist — which corrupts the framework's purpose.

---

## APPENDIX A: DECISION CLARITY DOCUMENT TEMPLATE

```
[WPF — Wicked Problems Analysis]

# Decision Clarity Document — <problem name>

## Executive Summary

- **Problem:** <one-sentence statement>.
- **Why it is wicked:** <which of the four conditions fired and how>.
- **Fundamental value conflicts identified:** <N> — <one-line characterisations>.
- **Interventions modeled:** <N> — <one-line characterisations>.
- **What this analysis does NOT do:** No recommendation has been made; no intervention is ranked. The decision is yours.

## Stage 1 — Problem Space Map

### Stakeholder framings

[For each stakeholder group:]
- **<Group name>**
  - Problem definition: <quote or paraphrase>
  - Assumed cause: <quote or paraphrase>
  - Desired outcome: <quote or paraphrase>
  - Solution criteria: <observable conditions they would accept>

### Competing-hypotheses matrix

| Evidence | <Group A's framing> | <Group B's framing> | <Group C's framing> |
|----------|---------------------|---------------------|---------------------|
| <observable evidence 1> | supports / contradicts / neutral | … | … |
| <observable evidence 2> | … | … | … |

## Stage 2 — Value Conflict Map

### Steelmanned positions

[For each stakeholder group:]
- **<Group name> — steelman**
  - Strongest version: <reconstructed argument>
  - Underlying values: <specific operational expressions>

### Pairwise value conflict matrix

| Pair | Conflict | Classification | Why information / negotiation cannot resolve (if Fundamental) |
|------|----------|----------------|-------------------------------------------------------------|
| <A, B> | <conflict> | Fundamental / Resolvable-by-info / Resolvable-by-negotiation | <reasoning> |
| <A, C> | … | … | … |

## Stage 3 — Consequence Landscape

[For each intervention:]
- **Intervention <N>: <name>**
  - Cui Bono distributional layer: <author, beneficiaries, cost-bearers, parameters>
  - Systems Dynamics feedback structure: <loops, delays, leverage points>
  - Scenario Planning — Immediate (0-12 months): <2-4 scenarios>
  - Scenario Planning — Medium-term (1-5 years): <2-4 scenarios>
  - Scenario Planning — Long-term (5+ years): <2-4 scenarios>
  - Problem-definition reshaping: <how this intervention changes what becomes visible / invisible>

### Cross-intervention summary

| Intervention | Immediate winners | Immediate losers | Medium-term shifts | Long-term shifts |
|--------------|-------------------|------------------|--------------------|------------------|
| 1 | … | … | … | … |
| 2 | … | … | … | … |

## Stage 4 — Decision Clarity Document

[For each intervention:]
- **Intervention <N>: <name>**
  - **Description (one sentence):** <…>
  - **Beneficiaries:** <stakeholder groups + values honoured>
  - **Cost-bearers:** <stakeholder groups + values subordinated>
  - **Values prioritised:** <list>
  - **Values subordinated:** <list>
  - **Second- and third-order consequences accepted:** <list>
  - **Stakeholder groups this intervention CANNOT satisfy:** <list with strongest objection from each, sourced from `red-team-advocate`>
  - **Reversibility note:** <which effects are reversible if this turns out badly, which are not>

### Closing notes

- **What additional information would change this analysis:** <list of empirical questions>
- **What this analysis does NOT do:** No recommendation. No ranking. No synthesis. The decision is yours.
```
