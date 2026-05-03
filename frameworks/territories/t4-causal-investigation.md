
# Framework — Causal Investigation

*Self-contained framework for taking an outcome, symptom, or pattern of events and tracing backward to causes, mechanisms, or generative structures. Compiled 2026-05-01 from territory entry, member mode specs, lens dependencies, and open debates.*

---

## Territory Header

- **Territory ID:** T4
- **Name:** Causal Investigation
- **Super-cluster:** B (Causation, Hypothesis, and Mechanism)
- **Characterization:** Operations that take an outcome, symptom, or pattern of events and trace backward to causes, mechanisms, or generative structures.
- **Boundary conditions:** Input is an outcome or pattern; question is *why did this happen*. Excludes process mapping (T17 — *how does this work*) and mechanism understanding (T16 — *how do the parts produce the whole's behavior*).
- **Primary axis:** Complexity (single cause-chain → feedback structure).
- **Secondary axes:** Specificity (general → historical-event-specific); depth (light → DAG-formal).

## When to use this framework

Use when something has gone wrong (or keeps going wrong) and the question is *why* — tracing backward from outcome to cause. Plain-language triggers:

- "Something has gone wrong and we don't know why."
- "A problem has recurred despite attempts to fix it."
- "The presented issue feels like a symptom, not the real problem."
- "This keeps happening despite our attempts to fix it."
- "Fixing X seems to make Y worse."
- "Interventions produce counterintuitive results."
- "I want to know what would happen if we intervened."
- "I need to separate correlation from causation."
- "I want to know what actually caused this specific historical event."
- "I want to test competing causal explanations of a single case."

Do not route here when the question is how the system currently works (T17 — process mapping), how the parts produce the whole's behavior at the principle level (T16 — mechanism understanding), or whether the framing itself is generating the problem (T9 — paradigm examination, frame-as-cause).

## Within-territory disambiguation

```
Q1 (complexity): "Is the question more like 'what one thing went wrong here',
                  or more like 'what set of things keep producing this',
                  or do you want a formal causal model with arrows you can reason over,
                  or are you tracing how a specific historical event actually unfolded?"
  ├─ "one thing / chain back to root" → root-cause-analysis (Tier-2)
  ├─ "feedback / things reinforcing each other" → systems-dynamics-causal (Tier-2)
  ├─ "formal causal model with arrows" → causal-dag (Tier-3, Pearl-style)
  ├─ "specific historical event, step by step" → process-tracing (Tier-3, Bennett/Checkel)
  └─ ambiguous → root-cause-analysis with escalation hook to systems-dynamics-causal
```

**Default route.** `root-cause-analysis` at Tier-2 when ambiguous; this is the lightest path and surfaces feedback signals naturally.

**Escalation hooks.**
- After `root-cause-analysis`: if the analysis surfaces reinforcing loops or competing causes that interact, hook upward to `systems-dynamics-causal`.
- After `systems-dynamics-causal`: if formalism is needed to share with others, hook upward to `causal-dag`.
- After any T4 mode: if the framing itself appears to be generating the problem, hook sideways to T9 (`paradigm-suspension` or `frame-comparison`).
- After any T4 mode: if the question shifts to "how do the parts produce the whole's behavior", hook sideways to T16 (`mechanism-understanding`).

## Mode entries

### Mode — root-cause-analysis

- **Educational name:** backward causal-chain tracing for failure diagnosis (5 Whys / Ishikawa)
- **Plain-language description:** A descriptive backward-chain trace from observed symptom to genuine root cause. The mode declares its categorization framework first (6M for manufacturing — Methods, Machines, Materials, Manpower, Measurement, Milieu; 4P for service — Place, Procedure, People, Policy; 4S for organizational — Surroundings, Suppliers, Systems, Skills; 8P for process — Product, Price, Place, Promotion, People, Process, Physical evidence, Productivity), populates each category with candidate causes, applies five-whys to deepen each branch to sub-cause depth ≥2 on at least one branch, and distinguishes root causes (whose removal prevents recurrence) from contributing factors (which amplify probability). Crucially, no chain terminates at human error without a process or incentive sub-cause beneath it.

- **Critical questions:**
  1. Has the chain reached a genuine root cause, or has it stopped at an intermediate cause that itself has deeper causes beneath it?
  2. Has any branch terminated at human error, bad judgment, or insufficient effort without naming the process that permitted or incentivised the behaviour?
  3. Are causal claims supported by evidence, with correlation explicitly distinguished from causation on at least one link?
  4. Is the declared categorisation framework used coherently — every category populated by causes that genuinely belong, every category name canonical for the framework?

- **Per-pipeline-stage guidance:**
  - **Depth.** Number of genuine causal levels traversed beneath the symptom; sub-cause depth ≥2 on at least one branch; surface process/incentive structure beneath any human-error candidate.
  - **Breadth.** Catalog categories considered before fishbone is committed; scan alternative causal chains; consider whether two-or-more chains converge on the same symptom.
  - **Evaluation.** Four critical questions plus failure modes (premature-stop, human-error-terminal, correlation-causation-conflation, framework-incoherence, linear-chain-isolation, restatement-as-cause).
  - **Revision.** Deepen any branch that stops at intermediate cause; add process/incentive sub-cause beneath any human-error leaf (load-bearing); align category names with declared framework; resist collapsing toward a single tidy chain when contributing factors or alternative chains were surfaced.
  - **Consolidation.** Seven required sections: presented problem (phrased as observed failure, not target state); chosen framework and rationale; category analysis (one paragraph per category); root causes (distinguished from contributing factors); evidence assessment (with correlation-causation called out); recommendations (corrective and preventive distinguished); confidence and alternative framings.
  - **Verification.** Presented problem phrased as failure not target state; canonical category names used; ≥1 branch reaches sub-cause depth 2; no chain terminates at human error without a process sub-cause; correlation-vs-causation addressed on ≥1 link; ≥1 alternative causal framing considered.

- **Source tradition:** Ishikawa Kaoru's fishbone (cause-and-effect) diagram (1968 *Guide to Quality Control*); Toyota Production System / Sakichi Toyoda *Five Whys*; Reason's Swiss-cheese model (1990) for multi-layer defense; Dekker's *Just Culture* (2007) for the process-not-people reframing.

- **Lens dependencies:**
  - `ishikawa-fishbone-frameworks`: 6M / 4P / 4S / 8P canonical category sets — declare framework first, populate categories, name causes from canonical category names; framework choice matches failure domain.
  - `five-whys-protocol`: Ask "why" five times (or until you reach a root) on each candidate cause; one more "why" on each candidate root before stopping; protocol designed to catch premature-stop.
  - Optional: `reason-swiss-cheese-model` (when failure crosses multiple defensive layers); `dekker-just-culture` (when human-error terminal needs process re-framing).

### Mode — systems-dynamics-causal

- **Educational name:** feedback-system causal analysis (Forrester/Senge lineage)
- **Plain-language description:** A descriptive causal-feedback analysis when the recurring symptom is driven by loops rather than a single chain. The mode states the system boundary explicitly, identifies variables, draws feedback loops with polarity (R = reinforcing or B = balancing — with even number of negative edges in a loop being R, odd being B), surfaces delays between action and effect, names system archetypes (limits to growth, shifting the burden, fixes that fail, etc.), and ranks leverage points per Meadows depth (parameters → buffers → stocks → delays → balancing loops → reinforcing loops → information flows → rules → self-organization → goals → paradigm → power to transcend paradigms).

- **Critical questions:**
  1. Are the declared loops genuine cycles in the graph (closing edge present), or are they linear chains mis-labelled as loops?
  2. Does each loop's declared type (R or B) match its polarity parity (even number of negative edges → R; odd → B)?
  3. Has the system boundary been stated explicitly, or has the analysis silently expanded to absorb every adjacent variable?
  4. If a system archetype is named, does its characteristic loop topology actually appear in the declared loops, or is it a name-drop?
  5. Are leverage points ranked by Meadows depth with reasoning, or is the recommendation a parameter tweak presented as systemic intervention?

- **Per-pipeline-stage guidance:**
  - **Depth.** Articulation of feedback structure with polarity, delays, and leverage points ranked by Meadows depth.
  - **Breadth.** Scan candidate archetypes; consider whether what appears as one loop is actually two interacting loops; consider whether the system boundary should be expanded or contracted.
  - **Evaluation.** Five critical questions plus failure modes (linear-masquerading-as-loop, polarity-parity-mismatch, boundary-dishonesty, archetype-name-drop, deep-leverage-omission).
  - **Consolidation.** Eight required sections in diagram-friendly format: system boundary; variables; feedback loops with polarity; delays; system archetypes; leverage points (Meadows ranked); counterintuitive behaviours; confidence and boundary caveats.
  - **Verification.** All declared loops genuine cycles; polarity parity matches loop type; system boundary stated explicitly; archetypes (if named) supported by actual loop topology; leverage points ranked by Meadows with reasoning.

- **Source tradition:** Forrester *Industrial Dynamics* (1961); Senge *The Fifth Discipline* (1990); Meadows *Thinking in Systems* (2008); Sterman *Business Dynamics* (2000) for the systems-dynamics-modeling tradition.

- **Lens dependencies:**
  - `feedback-loops`: Reinforcing (R) and balancing (B) loop structure; polarity-parity rule; delay characterization; oscillation, overshoot, and equilibrium dynamics.
  - `senge-system-archetypes`: Recurring patterns with characteristic dynamics (limits to growth, shifting the burden, fixes that fail, eroding goals, escalation, success to the successful, tragedy of the commons, growth and underinvestment, accidental adversaries).
  - `meadows-twelve-leverage-points`: Hierarchy from parameters (least powerful) to power to transcend paradigms (most powerful); used to rank candidate interventions.
  - Foundational: `kahneman-tversky-bias-catalog`.

### Mode — causal-dag

- **Educational name:** causal directed acyclic graph analysis (Pearl do-calculus)
- **Plain-language description:** A formal causal-graph analysis using Pearl's framework. The mode locks the question at a Pearl-ladder rung (observation, intervention, or counterfactual), enumerates variables and classifies each by role (cause / effect / confounder / mediator / collider / instrument), draws the DAG with explicit absent-arrow assumptions, applies the back-door (or front-door) criterion to check identifiability, and answers the intervention or counterfactual query in the language proper to its rung. Avoids collider-conditioning (which would induce spurious dependence). Surfaces the most fragile structural assumptions.

- **Critical questions:**
  1. Has the causal question been locked at a specific rung of Pearl's ladder (observation, intervention, or counterfactual), and is the analysis using the operators appropriate to that rung?
  2. Have all plausible confounders been named and either included in the DAG or explicitly assumed away with justification?
  3. Has the back-door (or front-door) criterion been checked, and is the causal effect identifiable from the assumed graph?
  4. Have collider variables been correctly classified, with the analysis avoiding conditioning on them (which would induce spurious dependence)?
  5. Are the structural assumptions encoded in the DAG (which arrows present, which absent) made explicit, with the most fragile assumptions flagged?

- **Per-pipeline-stage guidance:**
  - **Depth.** Explicit Pearl-ladder rung selection; graphical representation with all variables classified by role; identifiability verdict from criterion application.
  - **Breadth.** Scan plausible confounders the analyst might miss (selection effects, reverse causation candidates, time-varying confounders, latent variables); consider alternative DAG structures consistent with the same observations; surface the identifiability boundary.
  - **Evaluation.** Five critical questions plus failure modes (rung-confusion, hidden-confounder, non-identifiability-elision, collider-conditioning, implicit-assumption, cycle-violation).
  - **Consolidation.** Eight required sections in diagram-friendly format: causal question locked; variable inventory with roles; DAG specification (node-and-arrow listing plus absent-arrow inventory); confounder/mediator/collider classification; identifiability verdict; intervention or counterfactual answer; assumption inventory (ordered by fragility); confidence per finding.
  - **Verification.** Question locked at Pearl rung; variables classified; DAG specified with absent-arrow assumptions enumerated; back-door or front-door criterion applied with verdict; collider variables correctly handled; intervention/counterfactual answer matches the rung; assumption inventory ordered by fragility.

- **Source tradition:** Pearl *Causality* (2009); Pearl *The Book of Why* (2018); Hernán & Robins *Causal Inference: What If* (2020) for the structural-causal-model tradition; counterfactual-theoretic critiques (Maudlin and others).

- **Lens dependencies:**
  - `pearl-causal-graphs`: DAG syntax — nodes for variables, directed arrows for direct causal effects, no cycles. Variable roles: cause, effect, confounder (common cause of two variables), mediator (on the causal path), collider (common effect of two variables), instrument (causes the cause but does not cause the effect through any other path).
  - `pearl-do-calculus`: Operator do(X = x) representing intervention (setting X to x by external action). Three rules of do-calculus permit reduction of interventional expressions to observational ones under specific graphical conditions. Back-door criterion: a set Z satisfies the back-door criterion relative to (X, Y) if Z blocks every path from X to Y starting with an arrow into X, and Z contains no descendants of X. Front-door criterion: applies when no back-door adjustment set is available but a mediator chain exists.
  - Optional: `bennett-checkel-process-tracing-tests`; `knightian-risk-uncertainty-ambiguity`.

### Mode — process-tracing

- **Educational name:** process tracing (Bennett-Checkel hoop / smoking-gun / doubly-decisive tests)
- **Plain-language description:** A historical-event-specific causal-inference pass. The mode locks the case and the question, names ≥2 competing causal hypotheses, inventories evidence with provenance, classifies each evidence piece by test type (hoop = necessary-but-not-sufficient: failed hoop eliminates; smoking-gun = sufficient-but-not-necessary: passed smoking-gun strongly confirms; doubly-decisive = both: changes everything; straw-in-the-wind = neither: weak Bayesian update), updates hypothesis status appropriately given test outcomes, reconstructs the causal chain in temporal sequence with explicit links, and notes residual uncertainty (what evidence would change the conclusion).

- **Critical questions:**
  1. Have at least two genuinely competing causal hypotheses been named, or has the analysis privileged one explanation by failing to construct alternatives?
  2. Has each piece of evidence been classified by test type (hoop / smoking-gun / doubly-decisive / straw-in-the-wind), with the classification justified rather than asserted?
  3. Has the analysis updated each hypothesis's status appropriately given the test outcomes (failed-hoop eliminates, passed-smoking-gun strongly confirms, etc.), or has it overweighted weak evidence?
  4. Has the provenance and reliability of each evidence piece been assessed, or has the analysis treated all sources as equally credible?
  5. Has the causal chain been reconstructed in temporal sequence with explicit links, or have intermediate steps been elided?

- **Per-pipeline-stage guidance:**
  - **Depth.** Competing hypotheses constructed before evidence is considered; per-evidence-piece test classification; update of hypothesis status given test outcomes.
  - **Breadth.** Scan additional plausible causal hypotheses (especially ones favored by different theoretical traditions or stakeholder perspectives); surface evidence the analyst lacks but could obtain; identify the most diagnostic evidence-piece that does not currently exist.
  - **Evaluation.** Five critical questions plus failure modes (hypothesis-monoculture, test-misclassification, evidence-overreach, source-naivety, chain-elision, presentism).
  - **Consolidation.** Eight required sections: case and question locked; competing hypotheses inventory; evidence inventory with provenance; test classification per evidence piece; hypothesis status after tests; causal chain reconstruction; residual uncertainty; confidence per finding.
  - **Verification.** ≥2 competing hypotheses tested; each evidence piece classified by test type with justification; hypothesis status reflects appropriate Bayesian updating; source provenance assessed; causal chain reconstructed in temporal sequence; residual uncertainty names diagnostic evidence not yet available.

- **Source tradition:** Bennett, Andrew, and Jeffrey T. Checkel (eds.) *Process Tracing: From Metaphor to Analytic Tool* (2015); van Evera *Guide to Methods for Students of Political Science* (1997) for the test-classification origin; King, Keohane & Verba *Designing Social Inquiry* (1994) for the broader case-study causal-inference framework.

- **Lens dependencies:**
  - `bennett-checkel-process-tracing-tests`: Four test types — hoop test (necessary but not sufficient: passing leaves the hypothesis viable, failing eliminates it); smoking-gun test (sufficient but not necessary: passing strongly confirms the hypothesis, failing leaves it viable); doubly-decisive test (both necessary and sufficient: outcome resolves the question); straw-in-the-wind test (neither necessary nor sufficient: weak Bayesian update only). Classification grounded in the *implications* of evidence presence and absence for each hypothesis.
  - `pearl-causal-graphs`: Same DAG apparatus, here applied to the historical-event-specific causal chain.
  - Optional: `pearl-do-calculus`; `tetlock-superforecasting`.

## Cross-territory adjacencies

**T4 ↔ T9 (Paradigm Examination).** "Looking for the causes within how the problem is currently framed, or stepping back to ask whether the framing itself is generating the problem?" Within-frame → T4; frame-as-cause → T9, possibly with T4 follow-up.

**T4 ↔ T16 (Mechanism Understanding).** "Tracing back to causes, or explaining how the parts produce the behavior?" Backward-to-causes → T4; how-it-works → T16.

**T4 ↔ T17 (Process Analysis).** "Why does this keep happening (causes), or how does this currently work (process map)?" Causal investigation → T4; process mapping → T17. When causal investigation requires a process map first, T17 runs first; T4 follows.

**T4 ↔ T5 (Hypothesis Evaluation).** When multiple causal hypotheses must be adjudicated against evidence with formal Bayesian diagnosticity, route to T5 (`competing-hypotheses` or `bayesian-hypothesis-network`).

## Lens references

### ishikawa-fishbone-frameworks

**Core structure.** Cause-and-effect diagram for organizing candidate causes by domain-specific category sets. Four canonical frameworks:
- *6M (manufacturing).* Methods, Machines, Materials, Manpower, Measurement, Milieu (Mother Nature / environment).
- *4P (service / marketing).* Place, Procedure, People, Policy.
- *4S (organizational).* Surroundings, Suppliers, Systems, Skills.
- *8P (process / business).* Product, Price, Place, Promotion, People, Process, Physical evidence, Productivity.

**Application.** Declare the framework first based on failure domain. Each category receives a "bone" of the fishbone, populated with candidate causes. Apply five-whys to each candidate to deepen toward root causes. Categories are populated only by causes that genuinely belong; canonical category names are used (not analyst-coined alternatives).

**Common misapplications.** Naming categories before declaring framework; mixing causes across multiple frameworks; using non-canonical category names; treating the diagram as the analysis (the diagram is a tool; the analysis is the substantive cause-tracing work).

### five-whys-protocol

**Core structure.** Iterative "why" questioning: ask "why" of the symptom; the answer becomes the new symptom; ask "why" again; repeat until reaching a genuine root cause whose removal would prevent recurrence. The "five" is heuristic — sometimes three are sufficient, sometimes seven are needed.

**Operational rule.** *One more "why" on each candidate root before stopping.* The protocol is designed to catch premature-stop. If one more "why" yields non-trivial structure, the candidate was an intermediate cause, not a root.

**Failure mode the protocol prevents.** Stopping at a satisfying or actionable cause that itself has deeper causes. Example: "Why did the deployment fail?" → "Because the database migration failed." → "Why did the migration fail?" → "Because the engineer ran the wrong command." Stopping here terminates at human error. One more "why": "Why did the engineer run the wrong command?" → "Because the runbook lacked a confirmation step for destructive operations." Now we have a process root cause whose removal prevents recurrence.

### feedback-loops

**Core structure.** A feedback loop is a closed circuit of cause-effect arrows where the output of the system feeds back as input.

**Types.**
- *Reinforcing loops (R).* Outputs amplify inputs. Even number of negative edges in the loop → reinforcing. Produces exponential growth or collapse.
- *Balancing loops (B).* Outputs counter inputs to maintain a goal. Odd number of negative edges → balancing. Produces stability around a setpoint, oscillation, or convergence.

**Polarity rule.** Count negative (inverse) edges in the loop. Even → R. Odd → B. This rule is a verification check: a loop declared R but containing an odd number of negative edges is mis-classified.

**Delays.** Time gaps between cause and effect. Delays in balancing loops cause oscillation. Delays in reinforcing loops produce slow ignition followed by rapid acceleration. Delays in interaction with feedback are the principal source of counterintuitive system behavior.

**Diagnostic value.** When a symptom recurs despite intervention, the intervention is likely targeting a parameter (Meadows leverage point 12) when the structure (loops, delays, archetype) operates at deeper leverage points.

### senge-system-archetypes

(See full description in `Framework — Interest and Power Analysis.md` Lens references.)

### meadows-twelve-leverage-points

(See full description in `Framework — Interest and Power Analysis.md` Lens references.)

### pearl-causal-graphs

**Core structure.** Directed acyclic graphs (DAGs) representing causal structure.

**Syntax.**
- *Nodes.* Variables (random variables in a probabilistic graphical model).
- *Directed arrows.* Direct causal effects (X → Y means X is a direct cause of Y, holding other parents of Y fixed).
- *No cycles.* DAGs cannot represent X → Y → X feedback (use systems-dynamics-causal for feedback structures).

**Variable roles.**
- *Cause.* X is a cause of Y if there is a directed path from X to Y.
- *Effect.* Y is an effect of X if there is a directed path from X to Y.
- *Confounder.* Z is a confounder of (X, Y) if Z is a common cause of both — Z → X and Z → Y. Confounders open back-door paths.
- *Mediator.* M is a mediator of (X, Y) if X → M → Y, and X has no direct effect on Y.
- *Collider.* C is a collider on a path if C is a common effect of two variables — A → C ← B. Conditioning on a collider opens a path that was previously closed (induces spurious association).
- *Instrument.* I is an instrument for the causal effect of X on Y if I causes X but does not cause Y through any other path.

**Pearl's ladder of causation.**
- *Rung 1 — Observation (seeing).* P(Y | X = x) — what does Y look like when X is observed to equal x?
- *Rung 2 — Intervention (doing).* P(Y | do(X = x)) — what would Y be if X were set to x by external action?
- *Rung 3 — Counterfactual (imagining).* P(Y_x | X = x', Y = y') — given that we observed X = x' and Y = y', what would Y have been if X had been x?

Each rung requires strictly more structural commitment than the one below.

### pearl-do-calculus

**Core structure.** Algebraic system for reducing interventional expressions P(Y | do(X)) to observational expressions P(Y | X) under specific graphical conditions, allowing causal effects to be identified from observational data alone.

**Three rules.**
- *Rule 1 (insertion/deletion of observations).* Adding or removing an observed variable from the conditioning set is permissible if the variable is independent of Y in the manipulated graph.
- *Rule 2 (action/observation exchange).* Replacing do(X) with X (treating an intervention as an observation) is permissible under specific independence conditions on the manipulated graph.
- *Rule 3 (insertion/deletion of actions).* Adding or removing do(X) from the expression is permissible if X has no causal effect on Y in the manipulated graph.

**Identifiability criteria.**
- *Back-door criterion.* A set Z satisfies the back-door criterion relative to (X, Y) if Z blocks every back-door path from X to Y (every path with an arrow into X) and Z contains no descendants of X. When Z exists, P(Y | do(X)) = Σ_z P(Y | X, Z = z) P(Z = z) — adjustment by Z.
- *Front-door criterion.* When no back-door adjustment set is available but a mediator chain X → M → Y exists with M satisfying specific conditions, the front-door formula identifies the effect.

**Identifiability verdict.** A causal effect P(Y | do(X)) is identifiable from observational data if it can be written as a function of P (the observational distribution) using do-calculus rules. Otherwise the effect is not identifiable from observational data alone, and intervention or counterfactual reasoning requires additional information.

### bennett-checkel-process-tracing-tests

**Core structure.** Four test types classifying evidence by what its presence-or-absence does to a hypothesis.

**The four tests.**
- *Hoop test.* Necessary but not sufficient. The hypothesis must clear the hoop (the test must pass) to remain viable. Passing leaves the hypothesis viable but does not strongly confirm; failing eliminates the hypothesis. *Asymmetric.* Example: "If H1 is true, document D must exist." Finding D does not confirm H1; not finding D refutes H1.
- *Smoking-gun test.* Sufficient but not necessary. Finding the evidence strongly confirms the hypothesis; not finding it leaves the hypothesis viable. *Asymmetric.* Example: "If H1 is true, document D may exist." Finding D strongly confirms H1; not finding D does not refute H1.
- *Doubly-decisive test.* Both necessary and sufficient. The outcome resolves the question. *Symmetric.* Example: "If H1 is true, document D must exist; if H1 is false, document D cannot exist." Finding D confirms H1; not finding D refutes H1.
- *Straw-in-the-wind test.* Neither necessary nor sufficient. Weak Bayesian update only. *Symmetric.* Example: "If H1 is true, D is somewhat more likely." Provides only weak evidence either way.

**Application.** Classification is grounded in the *implications* of evidence presence and absence for each hypothesis. The classification must be justified rather than asserted: what would we expect to see if H1 is true vs. false; what would absence of the evidence imply.

## Open debates

### Debate D4 — Are Pearl's ladder levels 2 (intervention) and 3 (counterfactual) genuinely distinct rungs, or is intervention a special case of counterfactual reasoning?

Pearl (2009 *Causality*; 2018 *The Book of Why*) argues for a strict three-rung hierarchy: observation (seeing), intervention (doing, via the do-operator), and counterfactuals (imagining what would have been). Each rung requires strictly more structural commitment than the one below; effects identifiable at level 3 are not generally identifiable from level 2 information alone. Maudlin and other philosophers of causation have argued the distinction is blurrier — interventions are themselves a kind of counterfactual ("what if we set X to x"), and the three-rung architecture is more pedagogical than ontological.

**Disposition.** The `causal-dag` mode operates with Pearl's strict hierarchy as the operational stance: critical question CQ1 requires explicit rung selection, and the intervention-or-counterfactual-answer section is rung-tagged. The debate is surfaced for users whose causal question sits at the level-2/level-3 boundary and who want to know whether the distinction matters for their application.

**Citations.** Pearl 2009 *Causality*; Pearl 2018 *The Book of Why*; Maudlin and related counterfactual-theoretic critiques.

## Citations and source-tradition attributions

**Root-cause and quality-engineering tradition.**
- Ishikawa, Kaoru (1968). *Guide to Quality Control*. Asian Productivity Organization.
- Ohno, Taiichi (1988). *Toyota Production System: Beyond Large-Scale Production*. Productivity Press.
- Reason, James (1990). *Human Error*. Cambridge University Press.
- Dekker, Sidney (2007). *Just Culture: Balancing Safety and Accountability*. Ashgate.

**Systems dynamics.**
- Forrester, Jay W. (1961). *Industrial Dynamics*. MIT Press.
- Senge, Peter M. (1990). *The Fifth Discipline*. Doubleday.
- Sterman, John D. (2000). *Business Dynamics: Systems Thinking and Modeling for a Complex World*. McGraw-Hill.
- Meadows, Donella H. (2008). *Thinking in Systems: A Primer*. Chelsea Green.

**Causal inference (Pearl tradition).**
- Pearl, Judea (2009). *Causality: Models, Reasoning, and Inference* (2nd ed.). Cambridge University Press.
- Pearl, Judea, and Dana Mackenzie (2018). *The Book of Why: The New Science of Cause and Effect*. Basic Books.
- Hernán, Miguel A., and James M. Robins (2020). *Causal Inference: What If*. Chapman & Hall/CRC.
- Spirtes, Peter, Clark Glymour, and Richard Scheines (2000). *Causation, Prediction, and Search* (2nd ed.). MIT Press.

**Process tracing and case-study causal inference.**
- Bennett, Andrew, and Jeffrey T. Checkel, eds. (2015). *Process Tracing: From Metaphor to Analytic Tool*. Cambridge University Press.
- Van Evera, Stephen (1997). *Guide to Methods for Students of Political Science*. Cornell University Press.
- King, Gary, Robert O. Keohane, and Sidney Verba (1994). *Designing Social Inquiry*. Princeton University Press.
- George, Alexander L., and Andrew Bennett (2005). *Case Studies and Theory Development in the Social Sciences*. MIT Press.

*End of Framework — Causal Investigation.*
