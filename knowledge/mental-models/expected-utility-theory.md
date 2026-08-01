---
lens_id: expected-utility-theory
name: Expected Utility Theory
lens_type: analytical-framework
applicability: [decision-under-uncertainty]
foundational: true
source: "von Neumann, John and Morgenstern, Oskar (1944). Theory of Games and Economic Behavior. Princeton University Press."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - decision
  - uncertainty
  - probability
---

# Expected Utility Theory

## Trigger

Invoked when a decision-under-uncertainty mode needs the canonical normative model for comparing risky options. The host mode supplies options, outcomes, probabilities, and values; the lens supplies expected-utility structure and caveats.

## Core Structure

Expected utility evaluates an option by multiplying each possible outcome's utility by its probability, then summing across outcomes.

1. **Options.** The available choices.
2. **States of the world.** Uncertain conditions that affect outcomes.
3. **Probabilities.** Credences assigned to states or outcomes.
4. **Utilities.** Value of outcomes to the decision-maker.
5. **Expected utility.** Probability-weighted utility for each option.
6. **Choice rule.** Prefer the option with the highest expected utility, subject to caveats about risk attitude, ambiguity, and model error.

## Application Steps

1. Define options and mutually relevant states.
2. Assign probabilities or probability ranges.
3. Assign utilities, not just dollar values.
4. Compute or qualitatively compare expected utility.
5. Test sensitivity to probability and utility assumptions.
6. Flag ambiguity, tail risk, and values that resist quantification.

## Detection Signals

- A choice involves probabilities and materially different outcomes.
- Options are being compared by best case or worst case alone.
- Tradeoffs require explicit value weighting.
- A decision needs a normative baseline before applying robustness or regret lenses.

## Critical Questions

- Are the states mutually clear and collectively adequate?
- Are probabilities calibrated or guessed?
- Are utilities representing actual value, including risk attitude?
- Which assumption changes the decision if varied?
- Is this risk, ambiguity, or Knightian uncertainty?

## Common Failure Modes

- **False precision** - Detection: made-up probabilities create spurious authority. Correction: use ranges and sensitivity checks.
- **Money-utility collapse** - Detection: dollars are treated as utility. Correction: model risk attitude and non-monetary values.
- **Tail blindness** - Detection: low-probability catastrophic outcomes are averaged away. Correction: inspect downside separately.
- **Ambiguity laundering** - Detection: unknown probabilities are forced into exact values. Correction: switch to ambiguity-aware tools where needed.

## Source Citations

- von Neumann, John and Morgenstern, Oskar (1944). *Theory of Games and Economic Behavior*. Princeton University Press.
- Savage, Leonard J. (1954). *The Foundations of Statistics*. Wiley.

