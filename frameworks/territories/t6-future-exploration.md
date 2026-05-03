
# Framework — Future Exploration

*Self-contained framework for looking forward — projecting consequences, building scenarios, forecasting probabilities, exploring possibility-spaces, anticipating sequels and failure modes. Compiled 2026-05-01 from territory entry, member mode specs, lens dependencies, and open debates.*

---

## Territory Header

- **Territory ID:** T6
- **Name:** Future Exploration
- **Super-cluster:** C (Decision, Future, and Risk)
- **Characterization:** Operations that look forward — projecting, scenario-building, forecasting probabilities, exploring possibility-spaces, anticipating sequels.
- **Boundary conditions:** Input is the present plus a forward-looking question. Excludes risk-and-failure-specific analysis (T7), which has its own territory.
- **Primary axis:** Depth (light projection → probabilistic forecasting → scenario planning → wicked-future molecular).
- **Secondary axes:** Stance (neutral forecasting vs. adversarial pre-mortem-action vs. constructive backcasting).

## When to use this framework

Use when the question is forward-looking — what will happen, what could happen, what should we prepare for. Plain-language triggers:

- "What would happen if we did X?"
- "What are the second-order consequences?"
- "I want a probability on this happening."
- "What are the odds?"
- "Multiple plausible futures need to be explored."
- "5–20 year strategic horizon under genuine uncertainty."
- "Imagine it's six months from now and this failed."
- "Before we sign off, what would have to go wrong?"
- "I need narrative scenarios, calibrated probabilities, and stress tests, not one or the other."

Do not route here when the question is choosing among options now (T3 — decision-making); when the focus is specifically failure modes of a system or design rather than future broadly (T7 — Risk and Failure); when the question is causal investigation of what already happened (T4); when the framing itself is in question (T9).

## Within-territory disambiguation

```
Q1 (stance): "Mostly looking forward to anticipate likely consequences,
              wanting probability estimates,
              wanting alternative future stories,
              stress-testing a plan against how it could go wrong,
              or imagining the success and working backward to today?"
  ├─ "likely consequences" → consequences-and-sequel (Tier-2)
  ├─ "probabilities" → probabilistic-forecasting (Tier-2, Tetlock-style)
  ├─ "alternative stories" → scenario-planning (Tier-2, Wack-style)
  ├─ "what could go wrong with the plan" → pre-mortem-action
                                            (cross-territory note: parsed from
                                             pre-mortem; structural-fragility
                                             variant lives in T7)
  ├─ "imagining the success and working backward" → backcasting (deferred per CR-6)
  └─ ambiguous → consequences-and-sequel with escalation to scenario-planning

Q2 (depth, optional): "Want me to bring it all together — multiple scenarios,
                        probability estimates, and pre-mortems composed into
                        a wicked-future analysis?"
  └─ yes → wicked-future molecular (Tier-3)
```

**Default route.** `consequences-and-sequel` at Tier-2 when ambiguous (the lightest forward-projection mode; scenario-planning is the most common upward hook).

**Escalation hooks.**
- After `consequences-and-sequel`: if multiple plausible futures diverge, hook upward to `scenario-planning`; if probabilities can be quantified usefully, hook sideways to `probabilistic-forecasting`.
- After `scenario-planning`: if the user wants stress-testing of a chosen path, hook sideways to `pre-mortem-action`; if integrated with probabilities and pre-mortem, hook upward to `wicked-future` molecular.
- After `pre-mortem-action`: if the failure modes are structural rather than action-specific, hook sideways to T7 `pre-mortem-fragility` (cross-territory parse).
- After any T6 mode: if the question is really about choosing among options now, hook sideways to T3.

## Mode entries

### Mode — consequences-and-sequel

- **Educational name:** forward causal-cascade tracing (de Bono C&S, second-and-third-order effects)
- **Plain-language description:** A light forward-cascade pass mapping immediate, second-, and third-order effects of a proposed action. Linear cascade (may fork but not loop) — circular feedback structures escalate to systems-dynamics-causal. Output is a structured cascade of effects rather than scenarios or probability estimates.

- **Critical questions:**
  1. Have second- and third-order effects been surfaced, or has the cascade stopped at immediate effects?
  2. Are the effects causally linked (this leads to that because) rather than associatively listed?
  3. Have non-obvious branches been considered (effects on parties not visible from the action's frame)?
  4. Has the cascade been distinguished from feedback structure (where escalation to systems-dynamics-causal is needed)?

- **Per-pipeline-stage guidance:**
  - **Depth.** Reach second- and third-order effects on at least one branch; causal links rather than associative lists.
  - **Breadth.** Scan branches affecting parties not visible from the action's frame; consider effects on time-and-attention as well as material outcomes.
  - **Consolidation.** Structured cascade format: immediate effects → second-order → third-order, with branching where appropriate.

- **Source tradition:** de Bono *Six Thinking Hats* and *Lateral Thinking* (consequence-and-sequel as one of the lateral-thinking moves); policy-impact-analysis tradition (Stone *Policy Paradox*).

- **Lens dependencies:**
  - Optional: `de-bono-c-and-s` (forward consequence-and-sequel as a lateral-thinking move). Foundational: `kahneman-tversky-bias-catalog`.

### Mode — probabilistic-forecasting

- **Educational name:** probabilistic forecasting (Tetlock superforecasting)
- **Plain-language description:** A thorough probabilistic forecast pass producing a numeric probability or range. The mode locks resolution criteria (how would we know the forecast resolved yes or no, in concrete observable terms), identifies the reference class and base rate (outside view), names inside-view drivers (specific features that distinguish this case from the reference class), adjusts the inside view by the outside view, produces a probability estimate with range, and identifies leading indicators and update triggers.

- **Critical questions:**
  1. Have resolution criteria been locked in concrete observable terms, or is the question vague enough to be unresolvable?
  2. Has the reference class been identified and the base rate computed, or is the inside view operating without outside-view anchoring?
  3. Have inside-view drivers been adjusted *toward* the outside view rather than treated as overriding it?
  4. Are the probability range and confidence calibrated to evidence, not anchored to initial guesses?
  5. Have leading indicators and update triggers been identified, so the forecast can be revised as evidence arrives?

- **Per-pipeline-stage guidance:**
  - **Depth.** Resolution criteria locked; base rate from reference class; inside-view drivers named with adjustment direction; probability range honest about uncertainty.
  - **Breadth.** Scan multiple plausible reference classes; consider whether the question can be decomposed into sub-questions whose probabilities are easier to estimate (Fermi-style).
  - **Consolidation.** Seven required sections: resolution criteria locked; reference class and base rate; inside-view drivers; outside-view adjustment; probability estimate with range; leading indicators and update triggers; confidence in estimate.
  - **Verification.** Resolution criteria observable and date-bounded; reference class named with base rate; inside-view drivers identified; outside-view adjustment direction stated; probability range reported; update triggers concrete.

- **Source tradition:** Tetlock *Superforecasting* (2015); Tetlock *Expert Political Judgment* (2005); Kahneman *Thinking, Fast and Slow* (2011) for inside-view/outside-view distinction; Galef *The Scout Mindset* (2021) for calibration practices.

- **Lens dependencies:**
  - `tetlock-superforecasting`: Outside view (reference-class base rate) → inside view (case-specific drivers) → adjusted forecast. Granularity, frequent updating, tracking calibration over time. Triage: only worth forecasting questions that are resolvable, time-bounded, and substantively important.
  - Optional: `bayesian-base-rate-reasoning`. Foundational: `kahneman-tversky-bias-catalog`.

### Mode — scenario-planning

- **Educational name:** alternative-future scenario planning (Wack/Schwartz lineage)
- **Plain-language description:** A thorough scenario-planning pass for strategic horizons under genuine uncertainty. The mode identifies driving forces (often via STEEP — Social, Technological, Economic, Environmental, Political), classifies them as predetermined (will obtain in any plausible future) vs. critical uncertainties (could go either way), selects two critical uncertainties as axes of a 2×2 matrix, generates four scenarios (one per quadrant) with internally consistent narrative logic, and identifies leading indicators per scenario plus implications for the focal question.

- **Critical questions:**
  1. Have driving forces been generated broadly (STEEP-style) and classified into predetermined vs. critical uncertainties?
  2. Are the chosen axes genuinely critical uncertainties (could plausibly resolve either way) and genuinely independent of each other?
  3. Are the four scenarios internally consistent narratives, or are they variations of a single trajectory dressed up?
  4. Have implications for the focal question been derived per scenario, with leading indicators that would signal which scenario is materializing?

- **Per-pipeline-stage guidance:**
  - **Depth.** Driving-force inventory; predetermined-vs-uncertain classification; axis-pair genuinely independent and critical; narrative scenarios internally consistent.
  - **Breadth.** STEEP categorization to ensure driving forces span multiple domains; consider wild cards (low-probability high-impact developments) as a fifth scenario or as an overlay.
  - **Consolidation.** Structured artifact: focal question; driving forces (STEEP-categorized); predetermined elements; critical uncertainties; selected axes; four scenario narratives; per-scenario implications; leading indicators.

- **Source tradition:** Pierre Wack at Shell (1970s, internal reports); Schwartz *The Art of the Long View* (1991); van der Heijden *Scenarios: The Art of Strategic Conversation* (1996); Heijden, Bradfield, Burt, Cairns, & Wright *The Sixth Sense* (2002).

- **Lens dependencies:**
  - `scenario-planning-method`: Wack/Schwartz scenario method — driving forces, predetermined elements, critical uncertainties, 2×2 axis selection, four-scenario construction with internal-consistency check, leading indicators per scenario.
  - Optional: `steep-categorization`; `wild-card-overlay`. Foundational: `kahneman-tversky-bias-catalog`.

### Mode — pre-mortem-action

- **Educational name:** pre-mortem on the action plan (Klein, Tetlock lineage)
- **Plain-language description:** An adversarial-future pass on an action plan. Imagines it is six months (or some appropriate horizon) from now and the plan has failed; narrates the failure backward; inventories failure modes; traces causal pathways to failure; identifies leading indicators per failure mode; proposes pre-commitment mitigations; and surfaces residual unmitigated risks. **Parsed sibling of `pre-mortem-fragility` (T7) per Decision D — they share `klein-pre-mortem` lens but differ in operation: `pre-mortem-action` operates on the action plan; `pre-mortem-fragility` operates on the system or design.**

- **Critical questions:**
  1. Has the imagined-failure narrative been written from a future perspective looking back, with concrete failure detail rather than generic risks?
  2. Have failure modes been distinguished from causal pathways (the failure mode is what failed; the pathway is how it failed)?
  3. Are leading indicators per failure mode concrete enough to detect drift before failure crystallizes?
  4. Are the pre-commitment mitigations actionable now, or do they require resources or authority not currently available?
  5. Are residual unmitigated risks named explicitly, rather than treated as accepted by silence?

- **Per-pipeline-stage guidance:**
  - **Depth.** Imagined-failure narrative concrete; failure modes distinguished from pathways; leading indicators per mode.
  - **Breadth.** Scan failure modes across categories: technical, organizational, market, regulatory, stakeholder, narrative, timing.
  - **Consolidation.** Seven required sections: imagined failure narrative; failure mode inventory; causal pathways to failure; leading indicators per failure mode; pre-commitment mitigations; residual unmitigated risks; confidence per finding.

- **Source tradition:** Klein, Gary "Performing a Project Premortem" *Harvard Business Review* (Sept 2007); Klein *Sources of Power* (1998); Kahneman *Thinking, Fast and Slow* (2011) for prospective hindsight; Tetlock *Superforecasting* (2015) for the calibration discipline.

- **Lens dependencies:**
  - `klein-pre-mortem`: Prospective-hindsight method — imagine the project has failed at some future point; narrate the failure backward; the technique surfaces failure modes that prospective optimism would suppress. Two parsed applications: `pre-mortem-action` (T6, on the action plan) and `pre-mortem-fragility` (T7, on the system or design).
  - Optional: `tetlock-superforecasting`. Foundational: `kahneman-tversky-bias-catalog`.

### Mode — wicked-future

- **Educational name:** wicked future analysis (scenario + pre-mortem + probabilistic forecast composition)
- **Plain-language description:** Molecular composition that runs scenario-planning (full), pre-mortem-action (full), and probabilistic-forecasting (full). Synthesizes via three stages: scenario-probability-overlay (parallel-merge produces scenario set with calibrated probability bands and divergence points); failure-pathway-stress-test (contradiction-surfacing identifies which scenarios contain pre-mortem-flagged failure modes); integrated-future-architecture (dialectical-resolution produces probability-weighted scenarios with named failure pathways and divergence-points-to-monitor). Explicitly gap-flags missing constructive-future (`backcasting` deferred per CR-6) rather than substituting.

- **Critical questions:**
  1. Have probability bands been overlaid on scenarios in a way that respects scenario-internal consistency (rather than treating scenarios as discrete random outcomes)?
  2. Have pre-mortem failure modes been mapped to specific scenarios (not all scenarios contain all failure modes)?
  3. Are divergence points (the moments at which scenarios branch) identified concretely, with leading indicators?
  4. Is the absence of constructive-future (backcasting) gap-flagged in the output rather than silently substituted?

- **Per-pipeline-stage guidance:**
  - **Composition.** Molecular: three full components, three synthesis stages.
  - **Consolidation.** Synthesis output: probability-weighted scenarios; per-scenario failure pathways with leading indicators; divergence-points-to-monitor; explicit gap-flag for backcasting.
  - **Verification.** Every component ran; synthesis stages integrated; probability bands respect scenario-internal consistency; failure modes mapped to specific scenarios; divergence points concrete; backcasting gap-flagged.

- **Source tradition:** Inherits from scenario-planning, pre-mortem-action, and probabilistic-forecasting; the composition principle from Rittel-Webber wicked-problem analysis (the analytical operation honors irresolvability rather than collapsing to a single recommendation).

- **Lens dependencies:**
  - Inherits component lens dependencies via composition.

- **For molecular modes:** Composition specified above. Paired execution framework: this framework supplies the synthesis-stage scaffolding directly.

## Cross-territory adjacencies

**T6 ↔ T3 (Decision-Making).** "Are you choosing among options now, or exploring how the future might unfold (irrespective of what you do)?" Choice-now → T3; future-shape → T6. When the future must be explored before the decision can be framed, T6 runs first; T3 then operates on the scenarios T6 produces.

**T6 ↔ T7 (Risk and Failure — Pre-Mortem parse).** Pre-Mortem is parsed (per Decision D) into two modes that share the `klein-pre-mortem` lens but differ in operation:
- `pre-mortem-action` (T6): adversarial-future stance applied to *the action plan*.
- `pre-mortem-fragility` (T7): adversarial-future stance applied to *the system or design*.
Disambiguating question: "Is this about an action plan that could fail, or about a system or design with structural fragilities?"

## Lens references

### tetlock-superforecasting

**Core insight.** Forecast accuracy is a learnable skill. The best forecasters ("superforecasters" in the Good Judgment Project) outperform domain experts and intelligence-community forecasters on resolvable questions. The methodology is reproducible.

**Operational principles.**
1. *Triage.* Only forecast questions that are resolvable (will be observably true or false by some date), time-bounded, and substantively important. Vague or unresolvable questions waste forecast effort.
2. *Reference class first (outside view).* Identify the class of similar past cases and compute the base rate. The base rate is the prior; case-specific reasoning is the adjustment.
3. *Decompose.* Break the question into sub-questions whose answers combine into the answer to the focal question (Fermi-style decomposition).
4. *Inside view second.* After the outside-view base rate is established, consider what makes this case different from the reference class. Adjust the base rate by the inside-view drivers — but adjust *toward* the outside view, not from it.
5. *Granularity.* Probabilities at fine granularity (5% increments, not 25% increments) — finer probabilities are more accurate when the forecaster has the relevant information.
6. *Update frequently.* As new evidence arrives, update the forecast. Bayesian updating is the norm; resistance to updating is anti-correlated with accuracy.
7. *Calibration tracking.* Track forecast accuracy over time using a proper scoring rule (Brier score). Calibration is the alignment between stated probability and observed frequency.
8. *Pre-commit to triggers.* Identify what evidence would change the forecast in advance, so the update is principled rather than ad hoc.

**Common misapplications.** Forecasting unresolvable questions (no feedback signal, no calibration); operating only on the inside view (no base-rate anchoring); over-confidence (extreme probabilities on questions with thin evidence); under-confidence (50% on questions where evidence supports a clearer probability); resistance to updating.

### scenario-planning-method

**Core insight.** When the future is genuinely uncertain over a strategic horizon, the value of planning is not to predict the future but to prepare for multiple plausible futures. Scenarios are not predictions; they are tools for testing strategy against alternative environmental futures.

**Application steps.**
1. *Identify the focal question.* The strategic question whose answer depends on uncertain environmental developments.
2. *Inventory driving forces.* Use STEEP (Social, Technological, Economic, Environmental, Political) or similar to span the relevant domains.
3. *Classify driving forces.* For each, ask: will this obtain in any plausible future (predetermined element), or could it go either way (critical uncertainty)?
4. *Select two critical uncertainties as axes.* Choose uncertainties that are (a) genuinely could-go-either-way, (b) substantively important to the focal question, (c) genuinely independent of each other (not two sides of the same coin).
5. *Construct four scenarios.* One per quadrant of the 2×2. Each scenario is a coherent narrative — a story about how the future unfolds in that quadrant, including how the predetermined elements interact with the critical-uncertainty resolution.
6. *Internal-consistency check.* Each scenario must be internally consistent: the events, actors, and dynamics within it must hang together as a believable trajectory.
7. *Per-scenario implications.* For each scenario, what does the focal question's answer look like? What strategy is robust across scenarios? What is fragile in only some?
8. *Leading indicators.* For each scenario, what observable developments would signal that scenario is materializing? Watch them.

**Common misapplications.** Single-trajectory dressed up as scenarios (the four scenarios are variations on one future); axes that are not independent (two sides of the same coin); axes that are not critical uncertainties (one side of the axis is a predetermined element); scenarios without internal consistency (events thrown together without narrative coherence); skipping the implications and leading-indicators steps.

### klein-pre-mortem

**Core insight.** Prospective hindsight — imagining a future failure as if it had already happened and narrating it backward — surfaces failure modes that prospective optimism suppresses. The technique was developed by Gary Klein (cognitive psychologist of expert decision-making) and published in *Harvard Business Review* in 2007.

**Operational protocol.** 
1. *Set the scene.* It is some future date (typically 6 months to 2 years from now, depending on plan horizon). The plan has failed. The team is reviewing what went wrong.
2. *Independent generation.* Each participant writes down (or in solo work, the analyst generates) reasons for the failure independently — without consultation. Independent generation prevents anchoring on the first-stated reason.
3. *Pool the failure modes.* Aggregate the independently generated failure modes. Often the pooled list contains failure modes that no single person would have generated.
4. *Distinguish failure modes from causal pathways.* The failure mode is what failed (e.g., "adoption stalled"); the causal pathway is how it failed (e.g., "the onboarding flow was too friction-heavy and the value-proposition wasn't visible until step 4").
5. *Leading indicators per failure mode.* For each failure mode, what would we observe before failure crystallized? Set up monitoring for those indicators.
6. *Pre-commitment mitigations.* For each failure mode, what action taken now would reduce its probability or impact? Pre-commit to those actions.
7. *Residual unmitigated risks.* What failure modes cannot be mitigated within current resources or authority? Name them explicitly; do not let them be accepted by silence.

**Two parsed applications (Decision D parsing principle).**
- *pre-mortem-action* (T6): operates on *the action plan* — a plan about to be executed. Failure mode: the plan as it unfolds in time fails to achieve its objective.
- *pre-mortem-fragility* (T7): operates on *the system or design* — a structural artifact whose failure modes are properties of its structure under stress. Failure mode: the structure cracks under pressure regardless of intentional execution.

The parse is not redundant. The action-plan pre-mortem asks "what could go wrong as we do this"; the fragility pre-mortem asks "where is this brittle". Both share the prospective-hindsight technique but operate on different objects.

## Open debates

### Debate D8 — Pre-Mortem parse: action vs. fragility

The Pre-Mortem operation appears to fit both T6 (Future Exploration — adversarial-future stance) and T7 (Risk and Failure — failure-mode focus). Per Decision D parsing principle, the candidate mode is split into two modes that share the `klein-pre-mortem` lens but differ in operation, rather than dual-citizened.

**The parse.**
- `pre-mortem-action` (T6): adversarial-future stance applied to *the action plan* — what could go wrong with this plan as it unfolds in time. The object is the plan; the failure question is execution.
- `pre-mortem-fragility` (T7): adversarial-future stance applied to *the system or design* — what failure modes does this structure exhibit under stress. The object is the system; the failure question is structural integrity.

**Disambiguating question.** "Is this about an action plan that could fail, or about a system or design with structural fragilities?"

**Examples.**
- "We're launching this campaign next month — pre-mortem it." → T6 (Pre-Mortem Action: the campaign unfolds in time, what derails it).
- "This architecture is going into production — pre-mortem it." → T7 (Pre-Mortem Fragility: the system is structural, where does it break).
- "Run a pre-mortem on this initiative." → ambiguous; the sufficiency analyzer asks whether the focus is the rollout (T6) or the design (T7).

**Disposition.** The parse is the disposition. Both modes coexist with shared lens; routing distinguishes by object (plan vs. system).

## Citations and source-tradition attributions

**Forecasting.**
- Tetlock, Philip E., and Dan Gardner (2015). *Superforecasting: The Art and Science of Prediction*. Crown.
- Tetlock, Philip E. (2005). *Expert Political Judgment: How Good Is It? How Can We Know?* Princeton University Press.
- Galef, Julia (2021). *The Scout Mindset: Why Some People See Things Clearly and Others Don't*. Portfolio.

**Scenario planning.**
- Wack, Pierre (1985). "Scenarios: Uncharted Waters Ahead." *Harvard Business Review* (Sept-Oct).
- Schwartz, Peter (1991). *The Art of the Long View*. Doubleday.
- van der Heijden, Kees (1996). *Scenarios: The Art of Strategic Conversation*. Wiley.
- Heijden, Kees van der, Ron Bradfield, George Burt, George Cairns, and George Wright (2002). *The Sixth Sense: Accelerating Organizational Learning with Scenarios*. Wiley.

**Pre-mortem and prospective hindsight.**
- Klein, Gary (2007). "Performing a Project Premortem." *Harvard Business Review* (Sept).
- Klein, Gary (1998). *Sources of Power: How People Make Decisions*. MIT Press.
- Kahneman, Daniel (2011). *Thinking, Fast and Slow*. Farrar, Straus and Giroux.

**Forward-cascade tradition.**
- de Bono, Edward (1985). *Six Thinking Hats*. Little, Brown.
- de Bono, Edward (1970). *Lateral Thinking*. Penguin.
- Stone, Deborah (2012). *Policy Paradox: The Art of Political Decision Making* (3rd ed.). W.W. Norton.

*End of Framework — Future Exploration.*
