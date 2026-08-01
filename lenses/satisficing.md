---
lens_id: satisficing
name: Satisficing
lens_type: mental-model
applicability: [decision-strategy, search-stopping, optimization-cost-analysis]
foundational: false
source: "Simon, Herbert A. (1956). 'Rational choice and the structure of the environment.' *Psychological Review* 63(2):129-138; Simon (1957). *Models of Man*."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - decision
  - bounded-rationality
---

# Satisficing

## Trigger

Invoked from modes that design search-and-decision processes — vendor selection, hiring, design choice, tool evaluation — when continued optimization has diminishing returns and the cost of additional search exceeds expected gain. The host mode supplies the option space and the decision criteria; the lens supplies the threshold-based stopping rule that replaces exhaustive comparison.

## Core Structure

### Core Insight

Choose the first option that meets your minimum acceptable threshold rather than exhaustively searching for the optimal one. Herbert Simon coined the term — a blend of "satisfy" and "suffice" — to describe how rational agents actually make decisions under real-world constraints of time, information, and cognitive capacity. Maximizing (evaluating every option to find the best) is theoretically superior but practically impossible in most situations. Maximizers often end up less satisfied than satisficers even when they objectively choose better, because awareness of unchosen alternatives breeds regret.

### Mechanism

Bounded rationality means search has cost (time, attention, cognitive load). Each marginal option evaluated extends the decision but provides only the chance of finding a better option than the current best. When the current best already meets requirements, additional search has near-zero expected gain but real cost. Satisficing makes this trade-off explicit: define the threshold, search until met, stop. The discipline avoids both analysis paralysis and post-decision regret.

### Applicability Conditions

- The option space is large or expensive to fully evaluate.
- A meaningful minimum-acceptable threshold can be defined.
- The decision is not so high-stakes that exhaustive optimization is genuinely warranted.
- The actor can commit to the satisficing rule rather than constantly re-evaluating.

### Common Misapplications

- Setting the threshold so low that the first acceptable option is far below available options.
- Satisficing on irreversible high-stakes decisions where optimization is warranted.
- Failing to define the threshold up front, then post-hoc justifying whatever was chosen.
- Treating satisficing as laziness rather than as a deliberate cost-benefit choice.

### Related Models

- **Bounded Rationality** — the foundational concept.
- **Diminishing Returns** — why additional search has falling marginal value.
- **Decision Trees** — alternative structured-decision approach when stakes warrant.

### Worked example

A team needs to choose a logging library. There are twelve viable options. Maximizing would mean benchmarking all twelve, reading every GitHub issue, and building proof-of-concepts — consuming two weeks of engineering time. Satisficing: define criteria upfront — must support structured JSON output, must have active maintenance, must handle at least 10,000 events per second, must have English documentation. Evaluate libraries one at a time. The third library checked meets all four criteria. Ship it.

## Application Steps

1. Before searching, define your minimum acceptable criteria — what must be true for an option to be good enough.
2. Evaluate options sequentially rather than in parallel.
3. Accept the first option that meets all your criteria — stop searching.
4. Reserve maximizing for decisions that are high-stakes, irreversible, and where the variance between options is genuinely large.
5. After deciding, do not look back at unchosen options — the satisficing advantage disappears if you second-guess.

## Detection Signals

- The number of options is large and the differences between good options are small.
- The cost of evaluating one more option exceeds the likely improvement.
- A decision is reversible — if you can course-correct later, optimizing upfront is waste.
- Analysis paralysis has set in and no decision is being made at all.
- The decision is not high-stakes enough to warrant exhaustive optimization.

## Critical Questions

- Is the threshold appropriate to the decision stakes, or is it set too low?
- Has the analyst committed to the threshold before searching, or will they raise it post-hoc to disqualify acceptable options?
- Is satisficing actually appropriate, or is this a high-stakes decision where optimization is warranted?
- Will the decision be revisable if it turns out poorly?
- Is the analyst defaulting to satisficing because of fatigue rather than reasoned trade-off?

## Common Failure Modes

- **Threshold drift** — raising the threshold mid-search to disqualify the first acceptable option. Detection: threshold expressions get more demanding as candidates appear. Correction: lock the threshold before search begins.
- **Inappropriate satisficing** — applying the rule to high-stakes irreversible decisions. Detection: satisficing decision produces regret because real optimization was warranted. Correction: classify decision stakes before choosing strategy.
- **Post-decision rumination** — second-guessing the satisficing choice by evaluating unchosen options. Detection: regret rises after the decision. Correction: commit to not re-evaluating; trust the threshold.

## Source Citations

- Simon, Herbert A. (1956). "Rational choice and the structure of the environment." *Psychological Review* 63(2):129-138. Originating concept.
- Simon, Herbert A. (1957). *Models of Man: Social and Rational*. Wiley. Book-length treatment.
- Schwartz, Barry et al. (2002). "Maximizing versus satisficing: Happiness is a matter of choice." *Journal of Personality and Social Psychology* 83(5):1178-1197. Maximizer-satisficer well-being comparison.
- Schwartz, Barry (2004). *The Paradox of Choice*. HarperCollins. Popular synthesis.
