---
lens_id: bounded-rationality
name: Bounded Rationality
lens_type: mental-model
applicability: [decision-quality-review, system-design, organizational-analysis]
foundational: false
source: "Simon, Herbert A. (1955). A Behavioral Model of Rational Choice. Quarterly Journal of Economics 69(1):99-118. Simon, Herbert A. (1957). Models of Man. Wiley."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - decision-making
  - cognition
---

# Bounded Rationality

*A lens that replaces the fiction of the perfectly rational agent with the reality of decision-makers operating under cognitive, informational, and time constraints, and reframes good decisions as those that satisfice well rather than those that optimize.*

---

## Trigger

Invoked when an actor's decision is being criticized for not finding "the best" option when "good enough" was the realistic ceiling, when a decision must be made under time pressure with incomplete information, or when the analyst is designing a system, interface, or process that real humans must navigate. The lens supplies the satisficing frame and the operational implication that better choice architecture beats better choosers.

## Core Structure

### Core Insight

Humans do not optimize — they satisfice. Real decision-makers have limited information, limited computation, and limited time. They search through options until they find one that meets a minimum threshold of acceptability, then stop. The quality of decisions depends not just on the chooser but on the structure of the environment — how information is presented and how options are organized. Simon's articulation: "The capacity of the human mind for formulating and solving complex problems is very small compared with the size of the problems whose solution is required."

### Mechanism

Optimization requires evaluating all options on all criteria, which is exponential in the number of dimensions and infeasible at any realistic scale. Satisficing is a tractable substitute: define an aspiration level on each criterion, search options sequentially, accept the first option that meets all aspirations, then stop searching. The aspiration level encodes the trade-off between search cost and decision quality; raising it produces better decisions at higher search cost, lowering it produces faster decisions at lower quality. The structure of the environment — how options are ordered, what defaults exist, what information is foregrounded — sets the conditions under which satisficing produces good or bad results.

### Applicability Conditions

- The decision-maker has materially limited time, information, or computational capacity.
- The option space is large enough that exhaustive evaluation is infeasible.
- The decision-maker can specify aspiration levels (what counts as "good enough") on relevant criteria.
- The environment can be designed (choice architecture is a lever).

### Common Misapplications

- Treating bounded rationality as a defense for any decision; it explains why optimization fails but does not justify negligence in setting aspirations or structuring the environment.
- Conflating with bias; bounded rationality is the structural condition, biases are the patterns of error within it.
- Assuming aspiration levels are fixed; in practice they adjust to feedback (Simon's "level of aspiration" dynamics).

### Related Models

- **Satisficing** — the operational decision rule under bounded rationality.
- **Choice Architecture** — the design lever that shapes satisficing outcomes.
- **Heuristics and Biases** (Kahneman/Tversky) — the catalog of patterns within bounded rationality.
- **Ecological Rationality** (Gigerenzer) — the alternative tradition: heuristics are well-adapted to specific environments.

## Application Steps

1. Identify the binding constraint: is it time, information, attention, or computational complexity?
2. Define "good enough": set explicit satisficing criteria before searching so the decision-maker knows when to stop.
3. Invest in better choice architecture rather than demanding better choosers — simplify options, provide defaults, structure information.
4. Accept that optimization is often infeasible and design processes around satisficing — checklists, heuristics, decision rules.
5. When evaluating others' decisions, ask what constraints they were operating under before judging the outcome.

## Detection Signals

- A decision-maker is being criticized for not finding "the best" option when an exhaustive search was infeasible.
- A team is debating whether to invest more time in a decision that has already met reasonable criteria.
- A system, interface, or process produces poor outcomes that no individual user can correct without re-architecting.
- An organization's decisions are being analyzed using a fully-rational-actor model that does not match its actual capacity.
- The conversation about a poor outcome focuses on the chooser's deficiencies rather than on the environment that constrained them.

## Critical Questions

- Has the binding constraint been identified — time, information, attention, or computational capacity?
- Have the aspiration levels been set explicitly, or is the decision-maker satisficing implicitly without knowing the criteria?
- Is the environment designed to support satisficing toward good outcomes, or against them (poor defaults, overwhelming information, hidden options)?
- Is the analyst attributing the outcome to the chooser when the environment is the cause?
- Are the aspiration levels appropriate for the stakes, or are they too low (negligent) or too high (paralysis)?

## Common Failure Modes

- **Satisficing-as-license** — bounded rationality is invoked to defend any decision regardless of whether aspiration levels were appropriate. Detection: the analyst defends the outcome by citing the chooser's constraints without examining whether those constraints justified the specific decision. Correction: bounded rationality explains why optimization fails, not why poor satisficing succeeds; the aspiration levels themselves must be defensible.
- **Chooser-blame** — the analyst attributes poor outcomes to the chooser when the environment was the cause. Detection: identical choosers in better-designed environments produce better outcomes. Correction: redesign the environment (choice architecture) before blaming the chooser.
- **Aspiration-stagnation** — aspiration levels remain fixed despite feedback that they are mismatched to the problem. Detection: the same decision rules produce repeatedly poor outcomes. Correction: explicitly review and update aspirations on a cycle proportionate to the decision's stakes.
- **Bias-conflation** — bounded rationality is conflated with the catalog of specific biases. Detection: the analyst uses "bounded rationality" as a synonym for "made a mistake." Correction: bounded rationality is the structural condition; specific biases are particular patterns of error within it. Diagnose the specific bias if applicable.

## Source Citations

- Simon, Herbert A. (1955). "A Behavioral Model of Rational Choice." *Quarterly Journal of Economics* 69(1):99-118. Founding paper.
- Simon, Herbert A. (1957). *Models of Man*. Wiley. Synthesis of the early decision-theoretic work.
- Simon, Herbert A. (1979). "Rational Decision Making in Business Organizations." *American Economic Review* 69(4):493-513. Nobel-lecture statement.
- Gigerenzer, Gerd, Peter Todd, et al. (1999). *Simple Heuristics That Make Us Smart*. Oxford University Press. The ecological-rationality extension.
- Related: Satisficing; Choice Architecture; Heuristics and Biases; Ecological Rationality.
