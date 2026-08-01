---
lens_id: decision-trees
name: Decision Trees
lens_type: protocol
applicability: [sequential-decision-analysis, expected-value-calculation, scenario-comparison]
foundational: false
source: "Raiffa, Howard (1968). Decision Analysis: Introductory Lectures on Choices Under Uncertainty. Addison-Wesley."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - protocol
  - decision
  - probability
---

# Decision Trees

## Trigger

Invoked from within sequential-decision-analysis, expected-value-calculation, and scenario-comparison modes when an analyst is comparing options that have different risk profiles, multi-stage contingencies, or branching outcomes that resist intuitive comparison. The host mode supplies the decision and its candidate options; the lens supplies the construction-and-evaluation protocol that maps decisions, chance events, and outcomes into a structured tree, then works backward from terminal values to identify the option with highest expected value.

## Core Structure

**Input:** A decision with multiple options, where outcomes depend on uncertain events that can be assigned probabilities; terminal outcomes that can be assigned values (monetary, utility, or scored).

**Output:** A branching tree diagram with computed expected values at each node, identifying the option with highest expected value plus a sensitivity analysis showing which probabilities or values are load-bearing for the recommendation.

1. **Identify the first decision point.** State the immediate decision and list the options as branches from a square (decision) node. Input: the decision under analysis. Output: an initial decision node with labeled branches.

2. **Identify the next event for each branch.** Determine whether the next event is a chance event (assign a circle node) or another decision (assign another square node). For chance events, list each possible outcome as a branch. Input: option list from step 1. Output: extended tree with second-tier nodes.

3. **Continue branching to terminal outcomes.** Repeat step 2 for each new node until each path terminates in an outcome that can be assigned a value. Input: tree-in-progress. Output: complete tree structure with terminal nodes.

4. **Assign probabilities to chance branches.** For each set of branches emerging from a chance node, assign probabilities that sum to 1.0. Use the best available estimate; document the basis (data, expert judgment, prior decisions). Input: tree from step 3. Output: tree with probabilities.

5. **Assign values to terminal outcomes.** Use a consistent unit (dollars, utility points, scored consequence). Document the basis for each value. Input: probability-annotated tree. Output: fully annotated tree.

6. **Work backward from terminal nodes.** At each chance node, compute expected value (sum of probability-weighted terminal values from that node's branches). At each decision node, select the branch with the highest expected value as the recommended choice. Input: annotated tree. Output: recommended decision path with computed expected value.

7. **Perform sensitivity analysis.** Vary key probabilities and values; identify which inputs change the recommended decision. Document the threshold values at which the recommendation flips. Input: completed tree. Output: sensitivity report identifying load-bearing inputs.

8. **Report.** Present the tree, the recommended path, the expected values, and the sensitivity findings. Note any inputs whose uncertainty is large enough to make the recommendation fragile. Input: outputs of steps 6-7. Output: decision-tree analysis report.

## Application Steps

1. Receive the decision and option set from the host mode.
2. Construct the tree per steps 1-5 above.
3. Compute expected values per step 6.
4. Run sensitivity analysis per step 7.
5. Return the tree, the recommendation, and the load-bearing inputs to the host mode.

## Detection Signals

- A sequence of decisions is involved, where later choices depend on earlier outcomes.
- Options have substantively different risk profiles and payoff structures.
- Uncertain outcomes can be assigned at least rough probabilities.
- A decision involves multiple stages or contingencies hard to hold in mind.
- Communication of decision logic to others requires that the reasoning be visible.

## Critical Questions

- Are the assigned probabilities defensible, or are they being assigned to make the analysis tractable? Indefensible probabilities produce indefensible recommendations.
- Have all material options been included as branches, or is the tree implicitly constraining the analysis to a subset?
- Are terminal values being measured in consistent units, or is the analysis mixing dollars, utility, and qualitative scores in a way that distorts the expected-value calculation?
- Has sensitivity analysis identified the load-bearing inputs, and are those inputs the ones the analyst is most uncertain about?

## Common Failure Modes

- **False precision** — Detection signal: probabilities and values are quoted to multiple decimal places when their underlying basis is rough estimate. Correction: round inputs to appropriate precision and report sensitivity bands.
- **Pruning by anchor** — Detection signal: branches are excluded because they are unfamiliar or unattractive, not because they are infeasible. Correction: include all material options; let the expected-value calculation prune.
- **Terminal-value mismatch** — Detection signal: terminal values are quoted in mixed units or fail to capture material consequences. Correction: convert to a single unit (typically utility or monetary equivalent) and verify all material consequences are represented.

## Source Citations

- Raiffa, Howard (1968). *Decision Analysis: Introductory Lectures on Choices Under Uncertainty*. Addison-Wesley.
- Howard, Ronald A. (1966). Decision analysis: Applied decision theory. *Proceedings of the 4th International Conference on Operational Research*.
- Magee, John F. (1964). Decision trees for decision making. *Harvard Business Review* 42(4):126-138.
