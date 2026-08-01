---
lens_id: pearl-do-calculus
name: Pearl Do-Calculus
lens_type: protocol
applicability: [causal-dag]
foundational: false
source: "Pearl, Judea (1995). Causal diagrams for empirical research. Biometrika 82(4):669-710. Pearl, Judea (2009). Causality: Models, Reasoning, and Inference (2nd edition). Cambridge University Press, chapters 3-4."
date created: 2026-05-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - protocol
  - causality
  - inference
---

# Pearl Do-Calculus

## Trigger

Invoked from within `causal-dag` (T4) when that mode, having established the rung of the claim and sketched a DAG (typically via the `pearl-causal-graphs` lens), needs the formal procedure that determines whether a desired interventional quantity P(Y | do(X)) can be identified from the available observational distribution and the DAG's structure — and if so, how. The host mode supplies the DAG, the target query, and the set of observable (vs. unobservable) variables; the lens supplies the three rules of do-calculus, the d-separation test, and the backdoor and frontdoor criteria as decision procedures. The output is either an identifying expression (an integral or sum over observable quantities equal to the desired interventional effect) or an "unidentifiable" verdict with the structural reason the identification fails.

## Core Structure

**Input:** A DAG over a variable set V partitioned into observable (O) and unobservable (U) variables; a target interventional query P(Y | do(X)) for X, Y ⊆ O; an observational distribution P(O).
**Output:** Either (a) an identifying expression for P(Y | do(X)) in terms of P(O), with the procedure (backdoor adjustment, frontdoor adjustment, or do-calculus derivation) named; or (b) an unidentifiable verdict with the named obstruction (e.g., "unobserved confounding on the only available adjustment set") and the auxiliary data (e.g., an instrument or quasi-experiment) that would unblock identification.

### The Three Rules of Do-Calculus

The do-calculus is a complete inference system: every identifiable causal query can be reduced to an observational expression by repeated application of the three rules (Shpitser & Pearl, 2006). Each rule licenses a substitution between expressions involving do(·) and expressions involving only observation, conditional on a d-separation criterion holding in a specified mutilated graph. (G_X̄ denotes the graph with all incoming edges to X removed; G_X denotes the graph with all outgoing edges from X removed.)

1. **Rule 1 — Insertion/deletion of observations.** P(Y | do(X), Z, W) = P(Y | do(X), W) if Z is d-separated from Y by W in G_X̄. *Reading.* When you intervene on X, observations of Z give no further information about Y if Z and Y are independent given W in the post-intervention graph. *Use.* Removes nuisance observations from the conditioning set when they convey no additional information about Y given the intervention.

2. **Rule 2 — Action/observation exchange.** P(Y | do(X), do(Z), W) = P(Y | do(X), Z, W) if Z is d-separated from Y by W in G_X̄,Z (the graph with X̄'s incoming edges removed and Z's outgoing edges removed). *Reading.* Setting Z (intervening) and observing Z have the same effect on Y when there is no back-door path from Z to Y through unobserved confounders, given W. *Use.* Replaces an interventional do(Z) with an observation of Z, which is the central move that makes identification from observational data possible.

3. **Rule 3 — Insertion/deletion of actions.** P(Y | do(X), do(Z), W) = P(Y | do(X), W) if Z is d-separated from Y by W in G_X̄,Z(W) (the graph with X̄'s incoming edges removed and Z's incoming edges removed for all Z not in an ancestor of W in G_X̄). *Reading.* An intervention on Z has no effect on Y if Z is causally disconnected from Y in the relevant mutilated graph. *Use.* Eliminates redundant interventions from the expression.

### d-Separation

d-separation is the graphical criterion that determines whether a set of variables Z blocks all paths between two variables X and Y in a DAG. It is the core machinery underlying all three do-calculus rules and the backdoor and frontdoor criteria. The procedure: for each path between X and Y, check whether the path is blocked by Z. A path is blocked if it contains:

- A chain (A → B → C) or a fork (A ← B → C) with B in Z. (Conditioning on B blocks the path.)
- A collider (A → B ← C) with B not in Z and no descendant of B in Z. (A collider blocks the path by default; conditioning on B or any of its descendants opens the path.)

If every path between X and Y is blocked by Z, then X and Y are d-separated by Z. The faithfulness assumption then licenses the conclusion that X ⊥ Y | Z in the population.

### Backdoor Criterion

The backdoor criterion gives a sufficient condition for identifying P(Y | do(X)) by conditioning on a set Z of observed variables. Z satisfies the backdoor criterion relative to (X, Y) if:

1. No node in Z is a descendant of X.
2. Z blocks every path between X and Y that contains an arrow into X (a "backdoor path" — a non-causal route from X to Y running through a confounder).

When such a Z exists and is observed, identification proceeds by **backdoor adjustment**: P(Y | do(X)) = ∑_z P(Y | X, Z=z) P(Z=z). *Reading.* The backdoor criterion isolates the causal effect of X on Y by blocking all the non-causal pathways that confound the observed correlation between X and Y. *Use.* The first identification strategy to attempt; works whenever the relevant confounders are observed.

### Frontdoor Criterion

The frontdoor criterion identifies P(Y | do(X)) when the backdoor criterion fails (typically because confounders between X and Y are unobserved) but a mediator M is available that:

1. M intercepts all directed paths from X to Y (every causal path X to Y goes through M).
2. There is no unblocked backdoor path from X to M.
3. All backdoor paths from M to Y are blocked by X.

When such an M exists and is observed, identification proceeds by **frontdoor adjustment**: P(Y | do(X)) = ∑_m P(M=m | X) ∑_x' P(Y | M=m, X=x') P(X=x'). *Reading.* The frontdoor criterion exploits the mediator M to bypass the unobserved confounder between X and Y by chaining together two effects (X → M and M → Y) that are each individually identifiable. *Use.* Apply when an unobserved confounder blocks backdoor adjustment but a clean mediator is available; the canonical example is Pearl's smoking → tar → cancer chain when the smoking-genotype confounder is unobserved but tar levels are measurable.

## Application Steps

1. Receive the DAG, observable/unobservable partition, and target query P(Y | do(X)) from the host mode.
2. Attempt **backdoor adjustment** first: search for a set Z of observed variables satisfying the backdoor criterion relative to (X, Y). If found, return the backdoor adjustment expression and stop.
3. If backdoor fails (no qualifying observed Z), attempt **frontdoor adjustment**: search for a mediator M satisfying the frontdoor criterion. If found, return the frontdoor adjustment expression and stop.
4. If both standard adjustments fail, attempt full **do-calculus derivation**: apply rules 1–3 iteratively to reduce P(Y | do(X)) to an expression involving only observable distributions. Use the ID algorithm (Shpitser & Pearl, 2006) for systematic search.
5. If no derivation succeeds, return the **unidentifiable verdict**: name the structural obstruction (e.g., "bidirected edge between X and Y reflecting unobserved confounding with no available adjustment set") and the auxiliary data (instrument, quasi-experiment, additional measurement) that would unblock identification.
6. Return the identifying expression (or unidentifiable verdict) and the procedure name to the host mode.

## Detection Signals

- The host mode has a DAG and an interventional query P(Y | do(X)) but only observational data.
- A natural experiment or randomized intervention on X is unavailable, but the analyst suspects identification from observational data may be possible if the right adjustment set can be found.
- A confounder between X and Y is suspected and the analyst needs to determine whether observed covariates suffice for identification.
- A complex DAG involves multiple potential adjustment sets and the analyst needs the formal criterion to choose among them.
- A claimed causal effect was computed by adjustment without the backdoor criterion being explicitly checked; an audit is needed.

## Critical Questions

- Is the DAG itself defensible? Do-calculus operates *given* the DAG; if the DAG is wrong (missing edges, spurious edges, missing latent confounders represented as bidirected edges), the identifying expression is wrong.
- Has the backdoor criterion been checked properly? A common error is to adjust for a descendant of X (which violates condition 1) or to fail to block all backdoor paths.
- When frontdoor adjustment is used, are the three frontdoor conditions all satisfied? The mediator M must intercept *all* directed paths from X to Y; partial mediation does not license frontdoor adjustment.
- Has the analyst confirmed positivity? Backdoor and frontdoor adjustment formulas assume P(X | Z) > 0 for all relevant Z; positivity violations break identification even when the criterion is met.
- When the verdict is "unidentifiable," has the auxiliary data that would unblock identification been named? An unidentifiable verdict without such guidance is incomplete.
- Is the analyst conflating "identified from this DAG" with "true in the population"? Identification is conditional on the DAG; a wrong DAG yields a wrong identified expression that may be confidently computed and confidently wrong.

## Common Failure Modes

- **Adjustment-for-descendant** — including a descendant of X in the adjustment set Z, which can introduce bias rather than remove it. Detection: a variable in Z has an arrow from X (directly or via a directed path). Correction: remove descendants from Z; re-test the backdoor criterion.
- **Collider-bias-by-conditioning** — conditioning on a collider (or its descendant) opens a non-causal path between X and Y, biasing the estimate. Detection: a node in the adjustment set has incoming arrows from both X-side and Y-side ancestors. Correction: remove the collider from Z; if necessary, find a different adjustment set.
- **Partial-mediation-mistaken-for-frontdoor** — applying frontdoor adjustment when the mediator does not intercept *all* directed paths from X to Y. Detection: there exists a directed path X → Y that does not pass through M. Correction: frontdoor adjustment does not apply; attempt backdoor adjustment with a different set, or seek auxiliary data.
- **Unidentifiable-disguised-as-identified** — computing an "identifying" expression that is in fact biased because the DAG omitted a relevant confounder. Detection: domain experts identify a plausible confounder absent from the DAG. Correction: revise the DAG to include the confounder (typically as a latent variable creating a bidirected edge); re-attempt identification.
- **Positivity-violation** — applying the adjustment formula in a region where some treatment-covariate combinations are not represented in the data. Detection: P(X | Z) is zero or near-zero for some realized Z. Correction: restrict the analysis to the region of common support; report the restriction.
- **DAG-confidence-overflow** — treating the identified expression as a fact about the world when it is a fact about the DAG. Detection: the analyst defends the estimate against a critique by citing the do-calculus derivation rather than by defending the DAG. Correction: separate the structural assumption (the DAG) from the algebraic consequence (the identifying expression); defend each layer on its own grounds.

## Source Citations

- Pearl, Judea (1995). "Causal diagrams for empirical research." *Biometrika* 82(4):669–710. The originating paper introducing the do-operator, the backdoor criterion, and the frontdoor criterion in the form used here.
- Pearl, Judea (2009). *Causality: Models, Reasoning, and Inference* (2nd edition). Cambridge University Press, chapters 3–4. The canonical formal treatment of do-calculus with proofs and worked examples.
- Shpitser, Ilya, and Judea Pearl (2006). "Identification of joint interventional distributions in recursive semi-Markovian causal models." *Proceedings of the AAAI Conference on Artificial Intelligence*. Establishes the ID algorithm and the completeness of do-calculus for identifiable queries.
- Tian, Jin, and Judea Pearl (2002). "A general identification condition for causal effects." *Proceedings of the AAAI Conference on Artificial Intelligence*. Generalizes the conditions under which interventional distributions can be identified.
- Hernán, Miguel A., and James M. Robins (2020). *Causal Inference: What If*. Chapman & Hall/CRC. Companion treatment from the counterfactual-framework tradition; complementary to Pearl's structural-equations approach.
- Related: `pearl-causal-graphs` (the foundational lens establishing the rung-vocabulary and DAG conventions on which this protocol operates); `bennett-checkel-process-tracing-tests` (a within-case alternative when statistical identification is unavailable).
