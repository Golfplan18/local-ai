---
lens_id: pearl-causal-graphs
name: Pearl Causal Graphs and the Ladder of Causation
lens_type: causal-framework
applicability: [causal-dag]
foundational: true
source: "Pearl, Judea (2009). Causality: Models, Reasoning, and Inference (2nd edition). Cambridge University Press. Pearl, Judea, and Dana Mackenzie (2018). The Book of Why: The New Science of Cause and Effect. Basic Books."
date created: 2026-05-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - causal-framework
  - causality
  - inference
---

# Pearl Causal Graphs and the Ladder of Causation

## Trigger

Invoked from within `causal-dag` (T4) when that mode needs the foundational vocabulary distinguishing observational, interventional, and counterfactual causal claims, and the formal directed-acyclic-graph (DAG) representation that supports each level. The host mode supplies a candidate causal claim or a set of variables suspected of causal interrelation; the lens supplies the three-rung ladder (so the analyst can name precisely which kind of claim is being made) and the DAG conventions (nodes as variables, directed edges as direct causal influence) that license the structural reasoning the next steps depend on. Also invoked when a host mode receives evidence framed in associational terms but is being asked to deliver a verdict in interventional or counterfactual terms — the ladder names the gap.

## Core Structure

Causal claims belong to one of three rungs in an ascending hierarchy. Each rung licenses claims the lower rungs cannot license, requires evidence the lower rungs do not require, and is operationally distinguishable from the others by the kind of question it can answer. DAGs are the common formal representation across rungs: nodes denote variables; directed edges denote *direct* causal influence (not mere correlation); the absence of an edge is itself a substantive causal claim (no direct influence). A DAG plus an assumption of faithfulness encodes which conditional independencies hold in the population; a DAG plus the do-operator encodes which interventions can be evaluated; a DAG plus a structural causal model (functions on each node) encodes which counterfactuals can be evaluated.

| Rung | Definition | Question form | Operational test |
|---|---|---|---|
| 1. Association | Statistical dependency between variables; "seeing." Captured by P(Y \| X). | "What does observing X tell me about Y?" | Can the claim be settled by observational data alone, with no intervention required and no counterfactual asserted? |
| 2. Intervention | Effect of an action on a variable, with all other inputs held fixed; "doing." Captured by P(Y \| do(X)). | "What happens to Y if I set X to a specific value?" | Does the claim require predicting the result of a manipulation, not merely a correlation? Is the answer different when X is set vs. when X is observed at the same value? |
| 3. Counterfactual | What would have been for an individual unit, given what actually was; "imagining." Captured by P(Y_x \| X', Y') for individual i. | "Given that Y' actually happened with X = X', what would Y have been if X had been x instead?" | Does the claim require reasoning about a world that did not occur? Does it concern a specific unit's alternative trajectory rather than a population-level effect of intervention? |

DAG conventions. Nodes are variables. A directed edge X → Y means "X is a direct cause of Y, holding all other parents of Y fixed." The absence of an edge between X and Y means "X is not a direct cause of Y." A path is a sequence of edges connecting two nodes, irrespective of edge direction. Three structural patterns recur: chain (X → M → Y, M mediates), fork (X ← C → Y, C confounds), collider (X → V ← Y, conditioning on V opens a non-causal path). Reading these patterns is the basic skill that the next-step lens (do-calculus) operationalizes via d-separation and the backdoor/frontdoor criteria.

Common confusion: treating Level-1 correlations as Level-2 causal claims is the dominant failure pattern. Detection signal: claim asserts that intervening on X will change Y, but evidence supports only that X and Y co-vary in observed data. A second, subtler confusion is treating Level-2 interventional claims as Level-3 counterfactuals: "if we increase the minimum wage, employment will fall" is a population-level interventional claim; "if this firm had not raised wages last year, it would have hired three more workers" is a unit-level counterfactual. They have different evidence requirements and different defeasibility conditions.

Debate D4 — Maudlin–Pearl exchange. A live disagreement in the foundations of causal inference concerns whether levels 2 and 3 are well-defined as genuinely distinct, or whether the apparent distinction collapses under closer inspection. Tim Maudlin and others have argued that counterfactual claims either reduce to interventional claims about appropriately-described populations (collapsing level 3 into level 2) or require metaphysical assumptions about closest-possible-worlds that the Pearl framework does not earn. Pearl maintains that level 3 is operationally distinct because it concerns the specific unit's trajectory in light of what actually was, which the do-operator alone cannot recover without the full structural causal model (functions, not just graph). The lens does not adjudicate the debate; it surfaces it. When a host mode is making a counterfactual claim, the analyst should disclose whether the claim's defensibility depends on assumptions Pearl's framework licenses but which the Maudlin objection contests, and present a counter-reading where the claim is restated in interventional terms.

## Application Steps

1. Receive the candidate causal claim or variable set from the host mode.
2. Identify which rung the claim belongs to (association, intervention, counterfactual) by matching its question form against the table above.
3. Sketch a DAG: list variables as nodes; draw directed edges where the claim or background knowledge asserts direct causal influence; mark suspected confounders, mediators, and colliders.
4. Check the rung-evidence match: if the claim is rung 2 or 3, confirm the available evidence supports a higher-rung inference, not just associational data.
5. When the claim is counterfactual (rung 3), surface Debate D4 explicitly: disclose whether the claim's force depends on Pearl-style structural causal models, and offer a counter-reading that restates the claim in interventional terms.
6. Return the rung classification, the DAG sketch, the rung-evidence-match verdict, and any D4 disclosure to the host mode for downstream use (typically by the do-calculus lens for backdoor/frontdoor analysis).

## Detection Signals

- A claim of the form "X causes Y" or "X affects Y" is being made and the analyst must distinguish what kind of causal claim it is.
- The host mode `causal-dag` is dispatching and the dispatch invokes this lens explicitly to establish the rung-vocabulary baseline.
- Available evidence is observational but the claim being delivered is interventional or counterfactual; the rung-mismatch needs to be named.
- A policy claim ("if we do X, Y will happen") is being made on the basis of correlational evidence; the rung-1-to-rung-2 jump needs auditing.
- A retrospective claim ("if we hadn't done X, Y would not have happened") is being made; the rung-2-to-rung-3 jump and Debate D4 need surfacing.
- The host mode needs to draw a DAG before applying do-calculus, process tracing, or any structural causal analysis.

## Critical Questions

- Has the rung of the claim been correctly identified? Misclassifying an interventional claim as associational understates what evidence is needed; misclassifying a counterfactual as interventional smuggles in metaphysical commitments the framework does not earn.
- Does the available evidence support inference at the claimed rung? Observational evidence alone cannot license rung-2 claims without strong identifying assumptions (no unobserved confounding, valid instruments, or quasi-experimental variation).
- Is the DAG's structure justified by domain knowledge or empirically tested? A DAG drawn to make a desired conclusion follow is an instrument of motivated reasoning, not an instrument of inference.
- Are the absences of edges defensible? An absent edge is a substantive claim of no direct influence; the DAG must justify each absence as well as each presence.
- When the claim is counterfactual, has Debate D4 been disclosed? A counterfactual claim presented without acknowledgment of the Maudlin–Pearl dispute treats a contested foundational question as settled.
- Is the analyst conflating population-level interventional claims with unit-level counterfactual claims? Different evidence requirements; different defeasibility conditions.

## Common Failure Modes

- **Rung-1-as-rung-2** — treating an observed correlation as a causal effect. Detection: the claim says "X causes Y" or "X will change Y" but the evidence is an observational regression coefficient. Correction: restate the claim in associational terms or supply identifying assumptions that license the rung-2 inference.
- **Rung-2-as-rung-3** — treating a population-level interventional claim as a unit-level counterfactual. Detection: the claim concerns a specific case ("this firm," "this patient") but the evidence is a population-level treatment effect. Correction: distinguish average treatment effects from individual counterfactuals; supply the structural causal model required for unit-level reasoning, or restate the claim at the population level.
- **DAG-as-summary** — drawing a DAG to summarize what is already believed rather than to license inference from data. Detection: the DAG's structure is assumed without justification; the analysis would proceed identically without it. Correction: justify each edge (and each absent edge) from domain knowledge or empirical test; treat the DAG as a falsifiable model, not a diagram.
- **Faithfulness blindness** — ignoring that the DAG's inference licenses depend on the faithfulness assumption (observed independencies match the DAG's structure). Detection: independence tests fail in ways the analysis ignores. Correction: test the faithfulness assumption; revise the DAG if observed independencies do not match.
- **Counterfactual-without-D4-disclosure** — making a unit-level counterfactual claim without acknowledging the Maudlin–Pearl dispute about whether such claims are well-defined. Detection: the analysis treats counterfactuals as straightforwardly meaningful and offers no counter-reading. Correction: surface D4; offer an interventional restatement; flag the metaphysical commitment.

## Source Citations

- Pearl, Judea (2009). *Causality: Models, Reasoning, and Inference* (2nd edition). Cambridge University Press. The canonical formal treatment of structural causal models, the do-operator, and the three-rung ladder.
- Pearl, Judea, and Dana Mackenzie (2018). *The Book of Why: The New Science of Cause and Effect*. Basic Books. The accessible exposition of the ladder of causation; canonical reference for the three rungs.
- Pearl, Judea (1995). "Causal diagrams for empirical research." *Biometrika* 82(4):669–710. The originating paper for DAG-based identification.
- Spirtes, Peter, Clark Glymour, and Richard Scheines (2000). *Causation, Prediction, and Search* (2nd edition). MIT Press. The complementary tradition of causal discovery from observational data.
- Maudlin, Tim (2019). "The Why of the World." *Boston Review* (review essay on Pearl & Mackenzie). Articulates the principal philosophical objection to treating Level 3 as distinct from Level 2; locus of Debate D4 in accessible form.
- Related: `pearl-do-calculus` (the formal apparatus for evaluating rung-2 claims from rung-1 data); `bennett-checkel-process-tracing-tests` (an alternative tradition for warranting causal inference from within-case evidence rather than between-case statistical leverage).
