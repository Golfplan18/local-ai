
# Framework — Decision-Making Under Uncertainty

*Self-contained framework for taking a decision context (alternatives, criteria, constraints, uncertainty) and producing structured guidance for choice. Compiled 2026-05-01 from territory entry, member mode specs, lens dependencies, and open debates.*

---

## Territory Header

- **Territory ID:** T3
- **Name:** Decision-Making Under Uncertainty
- **Super-cluster:** C (Decision, Future, and Risk)
- **Characterization:** Operations that take a decision context (alternatives, criteria, constraints, uncertainty) and produce structured guidance for choice.
- **Boundary conditions:** Input is a decision the user faces. Excludes negotiation-like situations where the parties' conflict itself is the analytical object (T8/T13) and excludes decision-clarity-document production for a third-party decision-maker (`decision-clarity` lives in T2 because its primary work is interest/stakeholder articulation, not optimization-under-uncertainty).
- **Primary axis:** All three (depth, complexity, stance) active.
- **Secondary axes:** Specificity (general decision → real-options → ethical-trade-off).

## When to use this framework

Use when the user faces a decision and wants structured guidance — mapping the option space, weighting criteria, dealing with uncertainty, or orchestrating all of these in a single integrated architecture. Plain-language triggers:

- "Multiple viable options exist; which should I choose?"
- "A choice must be made between alternatives with uncertain outcomes."
- "Probabilities matter but are not precisely known."
- "I'm choosing among options and they trade off across multiple things I care about."
- "No single criterion can settle this."
- "This is a big decision and I want the full treatment — stakeholders, constraints, what could go wrong."
- "Should we act now or wait?"
- "Is it worth waiting for more information?"

Do not route here when the question is exploring how the future might unfold irrespective of what you do (T6); when failure-stress-testing is the focus rather than choice (T7); when the conflict among parties is the analytical object (T8/T13); when producing a decision document for a third-party decision-maker (T2 `decision-clarity`).

## Within-territory disambiguation

```
Q1 (situation): "Is the environment basically known and you're picking from clear options,
                 or are there real unknowns about how things will play out,
                 or are you weighing several criteria that don't reduce to one number,
                 or are values in tension where the choice is partly about what you stand for?"
  ├─ "known environment" → constraint-mapping (Tier-2)
  ├─ "real unknowns / probability matters" → decision-under-uncertainty (Tier-2)
  ├─ "many criteria pulling different ways" → multi-criteria-decision (Tier-2)
  ├─ "values in tension" → ethical-tradeoff (deferred per CR-6)
  └─ ambiguous → decision-under-uncertainty with escalation hook to multi-criteria-decision

Q2 (specificity, optional): "Is this a one-shot choice, or staged where you can learn
                              between steps?"
  └─ "staged" → real-options-decision (deferred per CR-6)

Q3 (depth, optional): "Want me to bring it all together into a decision architecture
                        that tracks the constraints, uncertainties, and criteria
                        in one integrated frame?"
  └─ yes → decision-architecture molecular (Tier-3)
```

**Default route.** `decision-under-uncertainty` at Tier-2 when ambiguous (the central mode of the territory; constraint-mapping is the lighter sibling, decision-architecture the molecular sibling).

**Escalation hooks.**
- After `constraint-mapping`: if real unknowns surface that change the option set, hook upward to `decision-under-uncertainty`.
- After `decision-under-uncertainty`: if multiple non-commensurable criteria are in play, hook sideways to `multi-criteria-decision`.
- After any Tier-2 T3 mode: if the user wants a single integrated artifact tracking all dimensions, hook upward to `decision-architecture` molecular.
- After any T3 mode: if the question shifts from "what should I do" to "how could this fail", hook sideways to T7 (`pre-mortem-action` or `pre-mortem-fragility`).

## Mode entries

### Mode — constraint-mapping

- **Educational name:** constraint and option mapping (light decision analysis)
- **Plain-language description:** A descriptive light pass that maps the choice terrain — at least three alternatives (or two in pro/con form for genuinely binary choices) with success conditions, failure conditions, what is uniquely gained, and what is forfeited per alternative — without making the choice for the user. Surfaces no-lose elements (actions valuable regardless of which alternative is chosen). Operates in known environments where probability arithmetic is not central.

- **Critical questions:**
  1. Are at least three alternatives mapped, including any the user has not named?
  2. Are success and failure conditions stated as testable propositions for each alternative, with identical analytical depth across alternatives?
  3. Have no-lose elements (actions valuable regardless of which alternative is chosen) been surfaced explicitly?
  4. Does the mode map the choice terrain without making the choice for the user, unless explicitly asked?

- **Per-pipeline-stage guidance:**
  - **Depth.** Testability of success and failure conditions per alternative. State each success condition as a testable proposition with a threshold or observable; trace the cost of each forfeit concretely. Identical depth across alternatives.
  - **Breadth.** Identify ≥3 alternatives (or 2 in genuinely binary cases); generate hybrid or sequencing strategies; surface no-lose elements.
  - **Evaluation.** Four critical questions plus failure modes (false-dichotomy, advocacy-asymmetry, abstraction-trap, choice-collapse).
  - **Revision.** Add alternatives until ≥3; equalize depth; convert vague conditions into testable propositions. Resist revising toward a final choice if the user asked for the terrain mapped.
  - **Consolidation.** Five required sections in matrix form: decision context and constraints; alternatives (≥3); per-alternative analysis (success / failure / gained / forfeited); cross-alternative comparison; no-lose elements.
  - **Verification.** ≥3 alternatives mapped (or 2 in pro/con form); testable conditions; symmetric depth; no-lose elements explicit; mode does not make the choice unless asked.

- **Source tradition:** Rumelt strategy-kernel for the alternative-design test; strategic 2×2 matrix tradition (Boston Consulting Group; later iterations); Heath & Heath *Decisions in Practice* tradition for the no-lose framing.

- **Lens dependencies:**
  - Optional: `rumelt-strategy-kernel` (when alternatives are strategic options); `strategic-2x2-matrix-tradition`. Foundational: `kahneman-tversky-bias-catalog`; `knightian-risk-uncertainty-ambiguity`.

### Mode — decision-under-uncertainty

- **Educational name:** decision analysis under uncertainty (probability and time-weighted)
- **Plain-language description:** A thorough decision-analysis pass when probabilities and time-value are central. Classifies each critical variable as risk (assignable probability), uncertainty (estimable range), or deep uncertainty (no meaningful probability). Considers defer / sequence / hedge / buy-information alternatives alongside direct choices. Presents non-quantifiable factors (ethics, relationships, identity, reputation) alongside the quantitative framework. Names what would change the recommendation.

- **Critical questions:**
  1. Is each critical variable classified as risk (assignable probability), uncertainty (estimable range), or deep uncertainty (no meaningful probability)?
  2. Have defer / sequence / hedge / buy-information alternatives been considered alongside direct choices?
  3. Have non-quantifiable factors (ethics, relationships, identity, reputation) been presented alongside the quantitative framework, not as footnotes?
  4. Does the recommendation name what would change it — the conditions under which it should be revisited?
  5. Are probabilities grounded in base rates or qualitative bands, not anchored to initial guesses presented as point estimates?

- **Per-pipeline-stage guidance:**
  - **Depth.** Classify each variable; ground probabilities in base rates or qualitative bands; trace consequences under each plausible state; assess value of information against cost of delay.
  - **Breadth.** Surface defer / sequence / hedge / buy-information options. Identify robust alternatives (perform acceptably across multiple states) vs. optimal alternatives (best in one state). Surface non-quantifiable factors.
  - **Evaluation.** Five critical questions plus failure modes (false-precision, analysis-paralysis, quantification-trap, missing-defer, anchoring-trap).
  - **Revision.** Convert point probabilities into ranges when no base rate grounds the precision; add defer/pilot/hedge alternatives when binary framing has masked them; add non-quantifiable factors.
  - **Consolidation.** Six required sections: decision framing; uncertainty identification; consequence analysis; value-of-information analysis; recommendation; non-quantifiable factors. When envelope-bearing: decision-tree for sequential choices; influence-diagram when dependency structure dominates; tornado for parameter-sensitivity.
  - **Verification.** Each variable classified; defer/sequence/hedge alternatives considered; VOI assessed against cost of delay; recommendation states what would change it; non-quantifiable factors present; probabilities grounded.

- **Source tradition:** Expected utility theory (von Neumann–Morgenstern; Savage); decision-tree analysis (Raiffa); real-options methodology (Trigeorgis; Dixit-Pindyck); minimax-regret and robust decision-making (Lempert et al. RAND tradition); Knight's distinction between risk and uncertainty.

- **Lens dependencies:**
  - `expected-utility-theory`: Probability-weighted-utility framework for choice under risk; basis for decision-tree and influence-diagram analysis.
  - Optional: `real-options-methodology` (when financial / staged investment); `minimax-regret-and-robust-decision-making` (under deep uncertainty); `tetlock-superforecasting` (when probabilities can be calibrated).
  - Foundational: `kahneman-tversky-bias-catalog`; `knightian-risk-uncertainty-ambiguity`.

### Mode — multi-criteria-decision

- **Educational name:** multi-criteria decision analysis (MCDM: AHP, SMART, ELECTRE, etc.)
- **Plain-language description:** A descriptive pass when ≥3 criteria matter and explicit weights are needed. Names the MCDM method (additive SMART, AHP pairwise, ELECTRE outranking, TOPSIS distance-from-ideal, etc.) and explains why it fits the decision shape; surfaces weights with elicited rationale; identifies dominance relations to prune the option set; runs sensitivity analysis on both weights and scores; flags where the ranking is robust vs. fragile.

- **Critical questions:**
  1. Are the criteria genuinely independent of one another, or do they double-count by measuring the same underlying attribute under different names?
  2. Are the weights elicited from the decision-maker's actual preferences, or imposed by the analyst's choice of MCDM method without preference elicitation?
  3. Has sensitivity analysis surfaced how robust the ranking is to weight perturbations and scoring uncertainty, or is the top-ranked option presented as if the ranking were stable?
  4. Have dominated options (those beaten by another option on every criterion) been identified and pruned, and have dominant options (beating others on every criterion) been flagged as no-brainer choices?

- **Per-pipeline-stage guidance:**
  - **Depth.** Explicitness of method choice, weight elicitation, and sensitivity testing.
  - **Breadth.** Survey criteria across at least three categories (outcome-quality, cost, risk, fit, reversibility); sanity-check option-set completeness.
  - **Evaluation.** Four critical questions plus failure modes (criterion-redundancy, weight-imposition, false-stability, dominance-blindness, aggregation-method-opacity).
  - **Revision.** Add weight rationale; add sensitivity analysis; prune dominated options; flag dominant ones rather than presenting a flat ranking.
  - **Consolidation.** Eight required sections in matrix form: options inventory; criteria definitions; weights with rationale; scoring matrix (rows=options, columns=criteria); aggregated ranking with method-name; sensitivity analysis; dominant and dominated options; confidence per finding.
  - **Verification.** Criteria operationally defined; weights elicited or noted as analyst-imposed; aggregation method named and explained; scoring explicit per option per criterion; sensitivity runs at least one joint perturbation; dominance surfaced.

- **Source tradition:** Saaty AHP (Analytic Hierarchy Process); Edwards SMART (Simple Multi-Attribute Rating Technique); Roy ELECTRE (ELimination Et Choix Traduisant la REalité); Hwang & Yoon TOPSIS; broad MCDM tradition (Belton & Stewart 2002 *Multiple Criteria Decision Analysis*).

- **Lens dependencies:**
  - `mcdm-methods`: Catalog of multi-criteria decision methods — additive (weighted sum), AHP (pairwise comparison + eigenvector), ELECTRE (outranking), TOPSIS (distance from ideal), PROMETHEE (preference functions), each with its decision-shape fit, scoring requirements, and sensitivity properties.
  - Optional: `kahneman-tversky-bias-catalog` (when weight elicitation is anchored or framed); `rumelt-strategy-kernel`.

### Mode — decision-architecture

- **Educational name:** decision architecture (integrated decision analysis with stakeholders + risk + alternatives)
- **Plain-language description:** Molecular composition for high-stakes decisions where the user wants integrated architecture spanning constraints + uncertainty + stakeholders + failure modes. Runs decision-under-uncertainty (full), constraint-mapping (full), stakeholder-mapping (full), and pre-mortem-action (full). Synthesizes via four stages: decision-frame integration → stakeholder-impact overlay → failure-mode stress-test → integrated decision architecture. Output: single integrated document with recommendation, residual risks, and decision-conditions-to-monitor.

- **Critical questions:**
  1. Have the alternatives been generated broadly enough, or is the analysis evaluating an artificially narrow option set?
  2. Do the constraint findings actually bound the alternatives, or do they sit in a separate silo from the probability-weighted outcomes?
  3. Are the stakeholder impacts surfaced per alternative, or aggregated into a generic stakeholder list disconnected from choice?
  4. Has the leading alternative been pre-mortem-stress-tested, or has the synthesis presented a recommendation without naming failure pathways?
  5. Are the decision-conditions-to-monitor concrete enough to detect drift, or vague enough to be unfalsifiable?

- **Per-pipeline-stage guidance:**
  - **Composition.** Molecular: four full components, four synthesis stages.
  - **Breadth.** Catalog of alternatives: status-quo, obvious binary, creative third option, do-nothing, reverse-the-question, defer-and-monitor. Stakeholder enumeration includes absent voices.
  - **Evaluation.** CQ1–CQ5 plus failure modes (option-set-poverty, silo-aggregation, stakeholder-disconnection, pre-mortem-omission, monitoring-vagueness).
  - **Consolidation.** Eight required sections: decision frame; alternatives with probability-weighted outcomes; binding constraints; stakeholder impact per alternative; failure-mode stress-test findings; recommended alternative with residual risks; decision-conditions-to-monitor; confidence map.
  - **Verification.** Every component ran (or proceeded-with-gap flagged); four synthesis stages integrated; leading alternative carries pre-mortem stress-test; monitoring conditions concrete; confidence map populated.

- **Source tradition:** Decision analysis tradition (Howard, Raiffa, Keeney) integrated with stakeholder analysis (Freeman) and pre-mortem (Klein 2007).

- **Lens dependencies:**
  - Optional: `kahneman-tversky-bias-catalog`; `knightian-risk-uncertainty-ambiguity`.

- **For molecular modes:** Composition specified above. Paired execution framework: this framework supplies the synthesis-stage scaffolding directly.

## Cross-territory adjacencies

**T3 ↔ T2.** `decision-clarity` lives in T2 because its primary work is interest/stakeholder articulation for a third-party decision-maker. Decision Architecture (T3) is for the user's own decision; Decision Clarity (T2) is for someone else's.

**T3 ↔ T6 (Future Exploration).** "Are you choosing among options now, or exploring how the future might unfold (irrespective of what you do)?" Choice-now → T3; future-shape → T6. When the future must be explored before the decision can be framed, T6 runs first; T3 then operates on the scenarios T6 produces.

**T3 ↔ T7 (Risk and Failure).** "Choosing among options where risk is one input among several, or specifically stress-testing how things could fail?" Multi-input choice → T3; failure-focused → T7.

**T3 ↔ T8 (Stakeholder Conflict).** "Is this fundamentally your decision to make (with the parties as inputs), or is it a situation where the parties' conflict itself is what needs to be worked through first?" Your-decision → T3; parties'-conflict-first → T8. When the conflict structure must be characterized before the decision can be framed, T8 runs first.

## Lens references

### expected-utility-theory

**Core insight.** Under uncertainty, the rational choice is the alternative maximizing expected utility — the probability-weighted sum of utilities across possible outcomes. Utility is *not* monetary value: utility functions can be concave (risk-averse), linear (risk-neutral), or convex (risk-seeking) in the underlying outcome variable.

**Mechanism.** For each alternative A and each possible state of the world s, identify the outcome o(A,s) and its utility u(o(A,s)). Multiply by the probability p(s) of that state. Sum across states. The expected utility EU(A) = Σ p(s) × u(o(A,s)) is the comparable measure across alternatives. Choose the alternative maximizing EU.

**Apparatus.**
- *Decision tree.* Sequential choices and chance events laid out in tree form. Decision nodes (the user's choice) alternate with chance nodes (nature's draw). Each chance-node branch carries a probability summing to 1.0 across siblings. Terminal leaves carry utilities. Backward-induction from leaves resolves the tree.
- *Influence diagram.* Compact alternative when dependency structure dominates the tree. Decision nodes (rectangles), chance nodes (ovals), value nodes (diamonds). Arrows indicate dependence, not temporal order.
- *Value of information (VOI).* The maximum amount the decision-maker should pay for additional information about an uncertain variable. VOI(X) = EU(decision with X resolved) − EU(decision without X). When VOI > cost of acquiring information, acquire it; when VOI < cost, decide without it.

**Applicability conditions.** Probabilities can be assigned (or estimated as ranges); utilities can be elicited or constructed; outcomes can be enumerated. Where any of these fails, the EU framework degrades and alternative apparatus (minimax regret; robust decision-making; Knightian-uncertainty methods) becomes appropriate.

**Common misapplications.** Treating utility as monetary value (and missing risk attitude); using point probabilities when only ranges are defensible (false precision); applying EU under deep uncertainty where probabilities cannot be assigned at all (Knightian regime).

### mcdm-methods

**Core structure.** Multi-criteria decision methods convert multi-attribute option sets into rankings or selections. The methods differ in their elicitation requirements, aggregation logic, and sensitivity properties.

**Principal methods.**
- *Weighted Sum (Additive).* Score each option on each criterion; multiply by weight; sum. Simple, transparent, requires commensurable criteria scales. Method assumption: criteria are independent and trade off linearly.
- *Analytic Hierarchy Process (AHP).* Saaty's method. Pairwise comparison of criteria yields weights via principal eigenvector; pairwise comparison of options on each criterion yields scores; weights × scores → ranking. Consistency ratio audits the pairwise judgments. Heavy elicitation but explicit preference structure.
- *Simple Multi-Attribute Rating Technique (SMART).* Edwards's method. Direct rating of weights (typically on 0–100 scale) and scores. Lower elicitation cost than AHP; less internal consistency check.
- *ELECTRE (ELimination Et Choix).* Roy's outranking method. Rather than aggregating into a single score, builds an outranking relation (option A outranks option B if A is at least as good on enough criteria). Output is a partial order; not all options need be comparable. Useful when criteria are non-commensurable.
- *TOPSIS (Technique for Order Preference by Similarity to Ideal Solution).* Hwang & Yoon's method. Identify the ideal solution (best on every criterion) and anti-ideal (worst on every criterion); rank options by distance from ideal and proximity to anti-ideal. Method assumption: criteria can be normalized to a common scale.
- *PROMETHEE (Preference Ranking Organization Method for Enrichment Evaluation).* Brans's method. Pairwise comparison using preference functions (linear, V-shape, Gaussian, etc.) per criterion; flow-based ranking.

**Application steps.** (1) Identify the option set and the criteria; (2) elicit weights from the decision-maker (or note as analyst-imposed); (3) score each option on each criterion (with operationally defined measures); (4) select the aggregation method whose assumptions fit the decision shape; (5) compute the ranking; (6) run sensitivity analysis on weights and scores to check robustness; (7) prune dominated options and flag dominant ones; (8) report the method, the assumptions, the result, and the robustness.

**Common misapplications.** Equal-weighting as a "neutral default" (equal weights are themselves a preference choice); using point scores when ranges are defensible; selecting the method by analyst familiarity rather than decision-shape fit; treating the top-ranked option as the decision when sensitivity shows the ranking is fragile.

## Open debates

T3 modes carry no architecture-level debates that bear on territory operation. Debate-relevant material at the lens level (e.g., the interpretation of probability as frequentist vs. Bayesian; the legitimacy of expected-utility maximization under deep uncertainty) is handled within mode-specific lens dependencies and the Knightian risk/uncertainty/ambiguity foundational lens.

## Citations and source-tradition attributions

**Decision theory.**
- von Neumann, John, and Oskar Morgenstern (1944). *Theory of Games and Economic Behavior*. Princeton University Press.
- Savage, Leonard J. (1954). *The Foundations of Statistics*. Wiley.
- Raiffa, Howard (1968). *Decision Analysis*. Addison-Wesley.
- Howard, Ronald A. (1966). "Decision Analysis: Applied Decision Theory." *Proceedings of the Fourth International Conference on Operational Research.*
- Knight, Frank (1921). *Risk, Uncertainty, and Profit*. Houghton Mifflin.
- Keeney, Ralph L., and Howard Raiffa (1976). *Decisions with Multiple Objectives*. Wiley.

**Real options.**
- Trigeorgis, Lenos (1996). *Real Options*. MIT Press.
- Dixit, Avinash K., and Robert S. Pindyck (1994). *Investment under Uncertainty*. Princeton University Press.

**Robust and deep-uncertainty methods.**
- Lempert, Robert J., Steven W. Popper, and Steven C. Bankes (2003). *Shaping the Next One Hundred Years: New Methods for Quantitative, Long-Term Policy Analysis*. RAND.
- Ben-Haim, Yakov (2006). *Info-Gap Decision Theory*. Academic Press.

**Multi-criteria.**
- Saaty, Thomas L. (1980). *The Analytic Hierarchy Process*. McGraw-Hill.
- Edwards, Ward (1977). "How to use multi-attribute utility measurement for social decision making." *IEEE Transactions on Systems, Man, and Cybernetics* 7:326–340.
- Roy, Bernard (1968/1996). *Multicriteria Methodology for Decision Aiding*. Kluwer.
- Hwang, Ching-Lai, and Kwangsun Yoon (1981). *Multiple Attribute Decision Making: Methods and Applications*. Springer.
- Belton, Valerie, and Theodor Stewart (2002). *Multiple Criteria Decision Analysis: An Integrated Approach*. Kluwer.

**Cognitive bias and heuristic.**
- Kahneman, Daniel, and Amos Tversky (1979). "Prospect Theory: An Analysis of Decision under Risk." *Econometrica* 47:263–291.
- Kahneman, Daniel (2011). *Thinking, Fast and Slow*. Farrar, Straus and Giroux.

**Strategic decision.**
- Rumelt, Richard (2011). *Good Strategy / Bad Strategy*. Crown Business.
- Klein, Gary (2007). "Performing a Project Premortem." *Harvard Business Review* (September).

*End of Framework — Decision-Making Under Uncertainty.*
