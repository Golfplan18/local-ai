
# Framework — Interest and Power Analysis

*Self-contained framework for surfacing who benefits, who pays, who has power to shape this, whose voices are absent, and how interest structures explain what is observed. Compiled 2026-05-01 from territory entry, member mode specs, lens dependencies, and open debates.*

---

## Territory Header

- **Territory ID:** T2
- **Name:** Interest and Power Analysis
- **Super-cluster:** A (Argument and Reasoning)
- **Characterization:** Operations that ask, of a state of affairs, decision, claim, or text: who benefits, who pays, who has power to shape this, whose voices are absent, and how do interest structures explain what is observed.
- **Boundary conditions:** Input is a situation, decision, or claim with multiple parties whose interests may diverge. Excludes negotiation/conflict-resolution operations (T13) and pure stakeholder-mapping without interest analysis (T8).
- **Primary axis:** Complexity (Cui Bono → Stakeholder Mapping → Wicked Problems molecular; Decision Clarity is depth-molecular along the same complexity ladder).
- **Secondary axes:** Stance (descriptive cui bono vs. critical/Ulrich-CSH boundary critique).

## When to use this framework

Use when the question is not whether an argument holds, but who is served by it (or by some state of affairs, decision, or institutional position). Plain-language triggers:

- "Trying to understand who's behind this."
- "Want to know who benefits from this."
- "Feels like someone's pushing this for a reason."
- "This policy or standard sounds objective but I suspect it isn't."
- "I think the framing of this leaves people out."
- "Who isn't being asked."
- "Whose perspective is being treated as natural or inevitable."
- "This feels tangled — every solution we try makes it worse somewhere else."
- "Stakeholders disagree about what the problem even is."
- "I need a decision document for a decision-maker, not an exploratory analysis."

Do not route here when the question is whether the argument itself holds (T1), when active negotiation guidance is needed (T13), or when multiple competing explanations need to be adjudicated against evidence (T5).

**Cross-territory note on Stakeholder Mapping.** The `stakeholder-mapping` mode lives in T8 (Stakeholder Conflict). T2 routes to it via cross-territory adjacency when interest analysis requires multi-party complexity that exceeds Cui Bono.

## Within-territory disambiguation

```
Q1 (complexity): "Are you trying to figure out who benefits from this single situation,
                  or map out a landscape of multiple parties with different stakes,
                  or work through something that feels tangled across many dimensions?"
  ├─ "this one situation" → cui-bono (Tier-2)
  ├─ "landscape of parties" → stakeholder-mapping (Tier-2; cross-territory dispatch into T8)
  ├─ "tangled / wicked / many interacting interests" → wicked-problems molecular (Tier-3)
  └─ ambiguous → cui-bono with escalation hook to stakeholder-mapping

Q2 (stance, optional): "Are you also asking about whose voices are being left out
                         of the picture entirely?"
  └─ yes → boundary-critique (Ulrich CSH, sideways/stance variant)

Q3 (output, optional): "Are you producing a decision-clarity document for someone else
                         (you're the analyst, they're the decision-maker)?"
  └─ yes → decision-clarity molecular (Tier-3)
```

**Default route.** `cui-bono` at Tier-2 when ambiguous, with stakeholder-mapping as the most common upward hook.

**Escalation hooks.**
- After `cui-bono`: if more than two stakeholder groups surface, hook upward to `stakeholder-mapping` (cross-territory into T8).
- After `stakeholder-mapping`: if interactions among parties surface feedback structure, hook upward to `wicked-problems` molecular.
- After any T2 mode: if voices may be missing, hook sideways to `boundary-critique`.
- After `cui-bono` or `stakeholder-mapping`: if producing analysis for a third-party decision-maker, hook upward to `decision-clarity`.

## Mode entries

### Mode — cui-bono

- **Educational name:** who-benefits analysis (cui bono)
- **Plain-language description:** A descriptive read on who benefits from a situation, decision, or institutional position. The mode names the institutional author of the position (whose office, agency, or coalition produced it), states the rationale on offer, traces concrete distributional impact (money flows, power-position changes, time-and-attention captures, narrative-control gains), constructs the alternative design that would emerge from the opposite constituency's interests with equal technical sophistication, applies FGL (Fear, Greed, Laziness) symmetrically across constituencies, and separates legitimate value from distributional overlay.

- **Critical questions:**
  1. Are the identified beneficiaries actually positioned to benefit, or is the inference symbolic (mistaking narrative resonance for actual benefit)?
  2. Are there beneficiaries the analysis is missing because they are not visible from the artifact's frame?
  3. Are the costs identified actually borne by the parties named, or is incidence misattributed?
  4. Has FGL (Fear, Greed, Laziness) been applied symmetrically across constituencies, or only against the disfavoured side?

- **Per-pipeline-stage guidance:**
  - **Depth.** Trace concrete benefit pathways (money, power, time, narrative control) rather than asserting alignment-based benefit. A thin pass names parties; a substantive pass names institutional author, the specific parameters or definitional choices that drive distribution, and the counterparty's loss-pathway. Apply FGL explicitly per constituency.
  - **Breadth.** Scan for parties not visible from the artifact's own frame — parties who would benefit if the situation were framed differently; parties who pay costs the artifact treats as natural; parties absent from the discussion. Construct the alternative design from the opposite constituency's interests with equal technical sophistication. Identify legitimate value separate from distributional overlay.
  - **Evaluation.** Four critical questions plus failure modes (symbolic-inference, frame-bounded-blindness, cost-incidence-error, conspiracy-trap, cynicism-trap, mirror-trap, asymmetric-fgl).
  - **Revision.** Add concrete pathways where benefit is asserted without mechanism; add specific parameters; add boundary cases (absent or marginalized parties); make the alternative design technically sophisticated rather than cosmetic. Resist revising toward neutrality if real power-asymmetries are surfaced.
  - **Consolidation.** Seven required sections in matrix form: institutional authorship; stated rationale; distributional impact; alternative design from opposite constituency; FGL motivational analysis; legitimate value; confidence per finding.
  - **Verification.** Institutional author named; ≥2 specific parameters driving distribution stated; alternative design constructed with equal technical rigor; FGL applied to ≥2 constituencies; legitimate value separated; every beneficiary has concrete pathway; absent voices surfaced or boundary-critique handoff noted.

- **Source tradition:** The Roman juridical question *cui bono* (Cicero); modern public-choice tradition (Buchanan & Tullock); Rumelt strategy-kernel framing for distributional analysis; Ulrich CSH for the boundary-extension where cui-bono routes to boundary-critique.

- **Lens dependencies:**
  - Optional: `rumelt-strategy-kernel` (when alternatives are strategic options); `ulrich-csh-boundary-categories` (when boundary critique cross-cuts); `public-choice-theory` (when institutional incentive structures are central); `fgl-fear-greed-laziness` (motivational catalog applied symmetrically).
  - Foundational: `kahneman-tversky-bias-catalog`.

### Mode — boundary-critique

- **Educational name:** boundary critique (Ulrich CSH: critical systems heuristics)
- **Plain-language description:** A critical-stance audit of the boundary judgments embedded in a system, decision, or design. The mode applies Ulrich's twelve boundary categories — organized in four clusters of three (motivation, control, expertise, legitimacy) — in *is/ought* form: what the artifact takes as given vs. what it would take as given if those affected (especially affected-but-not-involved parties) had standing. Surfaces who currently provides the source of motivation/control/knowledge/legitimacy and on whose behalf, identifies affected-but-not-involved parties per category, and constructs the *ought* counterpart.

- **Critical questions:**
  1. Have boundary judgments been surfaced as judgments (contestable, made by someone for some purpose), or are they treated as natural givens of the system?
  2. Has the analysis distinguished those involved in the system's design and benefit from those affected by but not involved in the system, per Ulrich's core asymmetry?
  3. Have all four of Ulrich's category-clusters (motivation, control, knowledge, legitimacy) been audited, or has the analysis selected only the categories that confirm an initial suspicion?
  4. Has the *is* vs. *ought* boundary comparison been performed — what the boundary currently is vs. what it would be if affected-but-not-involved parties were included?

- **Per-pipeline-stage guidance:**
  - **Depth.** Rigor in applying the twelve Ulrich categories, four category-clusters, audited along the *is/ought* axis, distinguishing involved from affected-but-not-involved.
  - **Breadth.** Survey the full Ulrich category-cluster space; consider boundary frames from adjacent traditions (Habermasian discourse-ethics, Midgley's systemic intervention, Mackenzie's situated knowledges); treat the worldview category with care (the deepest boundary judgments).
  - **Evaluation.** Four critical questions plus failure modes (boundary-naturalization, involved-affected-collapse, selective-categories, ought-omission, critique-without-purpose).
  - **Revision.** Denaturalize boundary judgments treated as system-given; maintain involved/affected distinction; complete the four category-clusters; add the *ought* counterpart. Resist revising toward neutrality — the analytical character is critical.
  - **Consolidation.** Nine required sections: system under critique; current boundary judgments embedded; sources of motivation audit; sources of control audit; sources of knowledge audit; sources of legitimacy audit; affected-but-not-involved parties; is-vs-ought boundary comparison; confidence per finding.
  - **Verification.** System named; current boundary judgments surfaced as judgments; all four category-clusters audited; affected-but-not-involved parties identified per category; is-vs-ought comparison performed.

- **Source tradition:** Ulrich, Werner *Critical Heuristics of Social Planning* (1983); Ulrich & Reynolds "Critical Systems Heuristics" in Reynolds & Holwell (2010); Habermas discourse-ethics; Midgley *Systemic Intervention* (2000).

- **Lens dependencies:**
  - `ulrich-csh-boundary-categories`: Twelve boundary categories grouped into four sources of design judgment (motivation, control, expertise, legitimacy) — each run in is/ought form to surface the gap between what the artifact takes as given and what it would take as given if those affected counted.
  - Optional: `habermas-discourse-ethics` (when legitimacy category is foregrounded); `midgley-systemic-intervention` (when intervention is in scope).

### Mode — wicked-problems

- **Educational name:** integrated multi-perspective analysis of tangled problems (Rittel-Webber lineage)
- **Plain-language description:** A molecular composition for problems where every solution makes things worse somewhere else, the problem itself keeps shifting as it is defined, and stakeholders disagree about what the problem even is. The mode runs competing-hypotheses (fragment), cui-bono, steelman-construction (fragment), systems-dynamics-causal, scenario-planning, and red-team-assessment (fragment), then synthesizes via three stages: framing-reconciliation (dialectical resolution of the framings); dynamic-projection (sequenced build of dynamic projection under multiple framings and scenarios); intervention-stress-test (contradiction-surfacing of the leading intervention candidate against the red-team-assessment fragment).

- **Critical questions:**
  1. Have all major framings been steelmanned, or has the analysis privileged one frame?
  2. Do the systems-dynamics findings actually integrate with the cui-bono findings, or do they sit in separate silos?
  3. Have candidate interventions been stress-tested against the leading adversarial scenarios, or only against neutral projections?
  4. Are the residual tensions named explicitly, or has the synthesis collapsed them prematurely?

- **Per-pipeline-stage guidance:**
  - **Composition.** Molecular: six components, three synthesis stages.
  - **Breadth.** Catalog framings considered before steelman narrows: dominant-paradigm, stakeholder-position, historical-genealogy, cross-domain analogical.
  - **Evaluation.** CQ1–CQ4 plus failure modes (frame-privileging, silo-aggregation, stress-test-omission, premature-resolution).
  - **Consolidation.** Six required sections: reconciled framing; dynamic projection; candidate intervention catalog; stress-test findings; residual tensions; confidence map. Each section carries provenance to component sources.
  - **Verification.** Every component ran (or proceeded-with-gap flagged); synthesis stages integrated rather than concatenated; residual tensions named; confidence map populated.

- **Source tradition:** Rittel & Webber 1973 "Dilemmas in a General Theory of Planning" *Policy Sciences* (the founding articulation of wicked-problem characteristics); Conklin 2006 *Dialogue Mapping*; Meadows 2008 *Thinking in Systems* (twelve leverage points); Senge 1990 *The Fifth Discipline* (system archetypes); Pesch & Vermaas 2020.

- **Lens dependencies:**
  - `rittel-webber-wicked-characteristics`: The ten characteristics of wicked problems — no definitive formulation; no stopping rule; solutions not true-or-false but good-or-bad; no immediate test of solutions; every solution is a one-shot operation; no enumerable set of potential solutions; every wicked problem essentially unique; every wicked problem is a symptom of another problem; choice of explanation determines nature of resolution; planner has no right to be wrong.
  - `meadows-twelve-leverage-points`: Hierarchy of intervention points in a complex system from least to most powerful (constants and parameters → buffers → stocks-and-flows → delays → balancing feedback loops → reinforcing feedback loops → information flows → rules → self-organization → goals → paradigm → power to transcend paradigms).
  - `senge-system-archetypes`: Recurring structural patterns producing characteristic dynamics — limits to growth, shifting the burden, eroding goals, escalation, success to the successful, tragedy of the commons, fixes that fail, growth and underinvestment, accidental adversaries.
  - Optional: `ulrich-csh-boundary-categories`; `tetlock-superforecasting`. Foundational: `kahneman-tversky-bias-catalog`; `knightian-risk-uncertainty-ambiguity`.

- **For molecular modes:** Composition specified above. Paired execution framework: this framework supplies the synthesis-stage scaffolding directly.

### Mode — decision-clarity

- **Educational name:** decision clarity document (for decision-maker; cui-bono + stakeholder + scenario + red-team-assessment composition)
- **Plain-language description:** A molecular composition that produces a decision-clarity document for a third-party decision-maker (not the analyst). The mode runs cui-bono (full), stakeholder-mapping (full), scenario-planning (fragment: two contrasting scenarios — most-likely + most-adverse), and red-team-assessment (fragment: adversarial-stress-test of leading intervention only). Synthesizes via four stages: interest-and-stakeholder-merge → scenario-overlay → intervention-stress-test → decision-clarity-document. The output is decision-shaped (situation framing, stakeholder map, scenario range, recommended intervention with stress-test, residual risks, decision-maker-actionable recommendations) rather than analysis-shaped.

- **Critical questions:**
  1. Does the document address the actual decision-maker's context (what they can do, what they cannot), or does it present generic analysis?
  2. Are stakeholder positions surfaced with concrete interests and concerns, or have they been collapsed into generic categories?
  3. Has the leading intervention been stress-tested by the red-team-assessment fragment, or has the recommendation been presented without adversarial pressure?
  4. Are the recommendations actionable by the named decision-maker, or do they exceed the decision-maker's authority or scope?
  5. Are the two scenarios genuinely contrasting (most-likely + most-adverse), or are they variations of the same trajectory?

- **Per-pipeline-stage guidance:**
  - **Composition.** Molecular: four components (two full + two fragments), four synthesis stages.
  - **Breadth.** Catalog of stakeholders and intervention candidates; scan visible stakeholders, absent stakeholders (boundary-critique territory), intervention status quo, intervention reversal, intervention defer-and-monitor.
  - **Evaluation.** CQ1–CQ5 plus failure modes (decision-maker-disconnection, stakeholder-collapse, stress-test-omission, out-of-scope-recommendation, scenario-flattening).
  - **Consolidation.** Ten required sections: decision at hand; decision-maker context; stakeholder map with positions; interest and power summary; scenario range; leading intervention recommendation; stress-test findings; residual risks and decision conditions; decision-maker-actionable recommendations; confidence map.
  - **Verification.** Every component ran; four synthesis stages integrated; leading intervention carries red-team-assessment stress-test; recommendations within decision-maker's scope; two scenarios genuinely contrasting; confidence map populated.

- **Source tradition:** Decision-clarity document genre (executive briefing tradition); Rumelt strategy-kernel; Ulrich CSH where boundary cross-cuts.

- **Lens dependencies:**
  - Optional: `rumelt-strategy-kernel`; `ulrich-csh-boundary-categories`. Foundational: `kahneman-tversky-bias-catalog`.

- **For molecular modes:** Composition specified above. Paired execution framework: `Framework — Decision Clarity Analysis.md` (restructured 2026-05-01 from the prior Wicked Problems framework per Decision H).

## Cross-territory adjacencies

**T2 ↔ T1.** "Are you mostly asking whether the argument itself holds up, or who benefits if people accept it?" Argument-soundness focus → T1; interest-pattern focus → T2; both → sequential dispatch, T1 first.

**T2 ↔ T8 (Stakeholder Conflict).** "Mostly asking who benefits or has power, or asking how the parties' competing claims can be worked through?" Power/interest analysis → T2; conflict structure → T8. When both fire, T2 typically runs first because interest analysis grounds the descriptive conflict mapping that T8 produces.

**T2 ↔ T13 (Negotiation).** "Are you mapping the interest landscape, or are you about to negotiate?" Mapping → T2; active negotiation guidance → T13.

**T2 ↔ T18 (Strategic Interaction).** When power as strategic resource is the question, T2 grounds the interest analysis and T18 models the strategic moves on top.

## Lens references

### ulrich-csh-boundary-categories

**Core structure.** Twelve boundary categories grouped into four sources of design judgment. Each category is run in *is/ought* form: what the artifact takes as given vs. what it would take as given if those affected counted. The gap is the locus of critique.

**Sources of Motivation (whose purposes are served?).**
1. *Beneficiary (client).* Who is and ought to be the client of the system?
2. *Purpose.* What is and ought to be the purpose of the system?
3. *Measure of improvement.* What is and ought to be the measure of success?

**Sources of Control (who has decision authority?).**
4. *Decision-maker.* Who is and ought to be in command?
5. *Resources.* What conditions of success are and ought to be under the decision-maker's control?
6. *Decision environment.* What conditions of success are and ought to be outside the decision-maker's control?

**Sources of Expertise (who has knowledge to inform the design?).**
7. *Expert (planner).* Who is and ought to be involved as planner?
8. *Expertise.* What expertise does and ought to inform the design?
9. *Guarantee (guarantor).* What does and ought to guarantee that the planning will succeed?

**Sources of Legitimacy (who speaks for the affected?).**
10. *Witness.* Who is and ought to be witness for the interests of those affected but not involved?
11. *Emancipation.* What are and ought to be the chances for the affected to emancipate themselves from the premises of the design?
12. *Worldview.* What worldview is and ought to be determining the design?

**Application steps.** (1) Identify the artifact's *implicit* answer in **is** mode (what the artifact takes as given, even when unstated); (2) generate the *ought* answer from the standpoint of the affected; (3) surface the gap; (4) flag gaps that are largest, most consequential, or most invisible; (5) group gaps into the four source-clusters to identify which source of judgment is most contested; (6) return the twelve-category boundary critique with named gaps and consequences.

**Common failure modes.** Implicit-boundary overlook (only the categories the artifact explicitly addresses are critiqued); analyst-substitution for witness (the analyst speaks for the affected-but-absent without naming this); worldview category skipped (treated as too philosophical); is/ought collapse (the gap is never produced); consensus-seeking framing (treating boundary judgments as resolvable through dialogue when they are political).

### rittel-webber-wicked-characteristics

**Core insight.** Wicked problems are problems that resist the formulation–solution sequence of well-defined problems. They have ten characteristics that distinguish them from "tame" problems addressable by ordinary professional methods.

**The ten characteristics.**
1. There is no definitive formulation of a wicked problem (formulating it is part of solving it).
2. Wicked problems have no stopping rule (the planner stops when out of resources, time, or patience, not when the problem is solved).
3. Solutions are not true-or-false but good-or-bad.
4. There is no immediate and no ultimate test of a solution.
5. Every solution is a one-shot operation (no opportunity to learn by trial and error; every attempt counts significantly).
6. There is no enumerable (or exhaustively describable) set of potential solutions.
7. Every wicked problem is essentially unique.
8. Every wicked problem can be considered a symptom of another problem.
9. The existence of a discrepancy representing a wicked problem can be explained in numerous ways; the choice of explanation determines the nature of the problem's resolution.
10. The planner has no right to be wrong.

**Application.** When an apparent problem exhibits ≥6 of these characteristics, the wicked-problem frame applies. The frame implies that solution attempts are themselves analytical moves with consequences; that the formulation/solution boundary is permeable; and that stakeholder framings cannot be cleanly arbitrated by appeal to facts.

**Debate D3 (carried by `wicked-problems` mode).** Are wicked problems sui generis or extreme cases of complex problems? Rittel & Webber treat wickedness as intrinsic and distinct from complexity. Later scholarship (Pesch & Vermaas; some complexity-science readings) treats them as extreme cases along the complexity gradient. The mode operates without adjudicating: applies the ten characteristics as analytical lens while remaining agnostic on whether wickedness is a category or a degree.

### meadows-twelve-leverage-points

**Core insight.** Donella Meadows' hierarchy of intervention points in a complex system, ordered from least to most powerful. Most interventions target weak leverage points; the strongest leverage is at the level of paradigms and the power to transcend them.

**The twelve points (least to most powerful).**
12. Constants, parameters, numbers (subsidies, taxes, standards).
11. The sizes of buffers and other stabilizing stocks, relative to their flows.
10. The structure of material stocks and flows (transport networks, population age structures).
9. The lengths of delays, relative to the rate of system change.
8. The strength of negative feedback loops, relative to the impacts they are trying to correct against.
7. The gain around driving positive feedback loops.
6. The structure of information flows (who does and does not have access to information).
5. The rules of the system (incentives, punishments, constraints).
4. The power to add, change, evolve, or self-organize system structure.
3. The goals of the system.
2. The mindset or paradigm out of which the system — its goals, structure, rules, delays, parameters — arises.
1. The power to transcend paradigms.

**Application.** When intervention is in scope, locate the candidate intervention's leverage point on the ladder. Most policy interventions sit at points 12–9. The most consequential interventions touch 4–1, and these are also the most contested.

### senge-system-archetypes

**Core structure.** Recurring patterns of system structure that produce characteristic dynamics, identifiable across very different domains.

**The principal archetypes.**
- *Limits to Growth.* A reinforcing process generates accelerating success until a limiting factor activates a balancing process; growth slows, stalls, or reverses. Intervention: anticipate the limit early; do not push harder on the engine that generated the early success.
- *Shifting the Burden.* A symptomatic solution solves the immediate symptom but undermines the system's ability to generate the fundamental solution. Intervention: name the fundamental solution explicitly; resist the lure of the quick fix; build the slower capability.
- *Eroding Goals.* When pressure mounts and the gap between desired and actual cannot be closed, the goal slowly erodes. Intervention: anchor the goal externally; make goal-erosion visible.
- *Escalation.* Two parties react to each other's actions in a positive-feedback structure that escalates without limit. Intervention: change the goal of one or both parties; introduce a third-side mediator.
- *Success to the Successful.* Resources flow toward the more successful party in a way that further increases its success and starves the alternative. Intervention: introduce balancing flows; question the metric defining "success."
- *Tragedy of the Commons.* Individual rational use of a shared resource depletes the resource for all. Intervention: regulate access; price the externality; transform the resource ownership structure.
- *Fixes That Fail.* A fix that solves the immediate problem produces unintended consequences that worsen the underlying condition. Intervention: identify the unintended consequences before deploying the fix; design the fix to be self-limiting.
- *Growth and Underinvestment.* Growth slows because of underinvestment in capacity; the slowdown justifies further underinvestment. Intervention: invest ahead of demand; treat capacity-building as a primary goal.
- *Accidental Adversaries.* Two parties whose joint action would benefit both come to see each other as adversaries through a series of misattributions. Intervention: surface the misattribution loop; rebuild joint understanding.

**Application.** When systems-dynamics-causal or wicked-problems modes detect a recurring pattern, identify whether one of these archetypes fits. The archetype carries with it a characteristic intervention and a characteristic failure mode (treating the symptom rather than the structure).

## Open debates

### Debate D3 — Wicked problems: sui generis or extreme cases of complex problems?

Rittel & Webber (1973) treat wickedness as intrinsic and distinct from ordinary complexity. Later scholarship (Pesch & Vermaas 2020; some complexity-science readings) treats wicked problems as extreme cases along the complexity gradient rather than as a separate category.

**Disposition.** The `wicked-problems` mode operates without adjudicating: it applies the Rittel-Webber characteristics as analytical lens (treating "wickedness" as a useful descriptor for problems exhibiting the ten characteristics) while remaining agnostic on whether wickedness is a category or a degree.

**Citations.** Rittel & Webber 1973; Pesch & Vermaas 2020; Conklin 2006 *Dialogue Mapping*.

## Citations and source-tradition attributions

**Interest and power.**
- Cicero, *Pro Roscio Amerino* (orig. cui bono attribution to Lucius Cassius Longinus Ravilla).
- Buchanan, James M., and Gordon Tullock (1962). *The Calculus of Consent*. University of Michigan Press.
- Rumelt, Richard (2011). *Good Strategy / Bad Strategy*. Crown Business.

**Critical systems heuristics.**
- Ulrich, Werner (1983). *Critical Heuristics of Social Planning*. Bern: Haupt.
- Ulrich, Werner & Reynolds, Martin (2010). "Critical Systems Heuristics." In Reynolds, M. & Holwell, S. (eds.), *Systems Approaches to Managing Change*. Springer.
- Ulrich, Werner (1996). *A Primer to Critical Systems Heuristics for Action Researchers*. University of Hull.
- Midgley, Gerald (2000). *Systemic Intervention: Philosophy, Methodology, and Practice*. Kluwer.

**Wicked problems and systems thinking.**
- Rittel, Horst W.J., and Melvin M. Webber (1973). "Dilemmas in a General Theory of Planning." *Policy Sciences* 4:155–169.
- Conklin, Jeff (2006). *Dialogue Mapping: Building Shared Understanding of Wicked Problems*. Wiley.
- Pesch, Udo, and Pieter Vermaas (2020). "The Wickedness of Rittel and Webber's Dilemmas." *Administration & Society* 52(6):960–979.
- Meadows, Donella H. (2008). *Thinking in Systems: A Primer*. Chelsea Green.
- Senge, Peter M. (1990). *The Fifth Discipline*. Doubleday.
- Forrester, Jay W. (1961). *Industrial Dynamics*. MIT Press.

*End of Framework — Interest and Power Analysis.*
