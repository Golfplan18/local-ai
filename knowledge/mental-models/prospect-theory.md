---
lens_id: prospect-theory
name: Prospect Theory
lens_type: mental-model
applicability: [decision-design, behavioral-prediction, framing-analysis]
foundational: false
source: "Kahneman, Daniel and Amos Tversky (1979). 'Prospect theory: An analysis of decision under risk.' *Econometrica* 47(2):263-291."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - behavioral-economics
  - decision
---

# Prospect Theory

## Trigger

Invoked from modes that predict or design decisions involving risk, gain, and loss — pricing, incentive design, negotiation, policy choice — when the question is how reference-relative framing will shape behavior. The host mode supplies the choice set and the affected parties; the lens supplies the value function (concave for gains, convex for losses), loss aversion (~2x weight), and probability distortion that predict deviations from expected-utility maximization.

## Core Structure

### Core Insight

People evaluate outcomes relative to a reference point rather than in absolute terms, and they weigh losses roughly twice as heavily as equivalent gains. The value function is concave for gains (risk-averse) and convex for losses (risk-seeking), and people systematically overweight small probabilities while underweighting large ones. "Losses loom larger than gains" — Daniel Kahneman and Amos Tversky, 1979.

### Mechanism

The reference point determines what counts as gain or loss. The value function is steeper on the loss side than the gain side, producing loss aversion. Concavity on gains makes people risk-averse when choosing among gains (prefer certain $100 to 50/50 of $200/$0). Convexity on losses makes people risk-seeking when choosing among losses (prefer 50/50 of -$200/$0 to certain -$100). Probability weighting overweights small probabilities (lottery, insurance) and underweights large ones (treats 95% as ~certain).

### Applicability Conditions

- The decision involves risk, uncertainty, or gain/loss framing.
- Reference points can be identified or designed.
- The decision-maker is human (or otherwise behaviorally similar).
- The framing is not so neutral as to render reference points irrelevant.

### Common Misapplications

- Treating prospect theory as a recipe for manipulation rather than a model of behavior.
- Ignoring that reference points can be designed and shifted.
- Applying the value function quantitatively when only qualitative direction is reliable.
- Confusing loss aversion with general risk aversion.

### Related Models

- **Loss Aversion** — the asymmetric-weighting component, often invoked separately.
- **Endowment Effect** — applied case: ownership establishes the reference point.
- **Framing Effect** — the more general phenomenon of which prospect theory is one mechanism.

### Worked example

A company offers employees two retirement plan options: Option A guarantees a 5% return; Option B has a 50% chance of 12% return and a 50% chance of 0%. Expected value favors B, yet most employees choose A. Prospect theory explains this: from the reference point of "my current savings," the potential 0% return feels like a painful loss of expected growth, and the certain 5% eliminates that pain. The same employees, if already enrolled in B and losing money, would likely gamble on a riskier strategy — risk-seeking in the loss domain.

## Application Steps

1. Identify the reference point the decision-maker is using — it determines what counts as a gain or loss.
2. Recognize that the same outcome framed as a loss will produce a stronger reaction than when framed as a gain.
3. Check for probability distortion — are small risks being overweighted or large probabilities being treated as certainties?
4. When designing choices, consider how shifting the reference point changes the perceived value of each option.
5. Use the asymmetry constructively: frame desired behaviors in terms of what is lost by not acting.

## Detection Signals

- The same option is accepted under one frame and rejected under another.
- Decision-makers are risk-averse on gains but risk-seeking on losses (or vice versa).
- Insurance is bought for small risks while lotteries are simultaneously played.
- Reference points (status quo, expectations) clearly anchor the perceived value of options.
- Behavior diverges systematically from expected-utility predictions.

## Critical Questions

- What reference point is the decision-maker actually using, and is it the one the analyst assumed?
- Has the loss/gain framing been chosen ethically, or is it manipulating without informing?
- Does the predicted asymmetry hold for this population, or are there cultural or expertise differences?
- Are the probability distortions material to the decision, or only to the analyst's prediction?
- Is the analyst designing for behavioral accuracy or for normative correction?

## Common Failure Modes

- **Quantitative overreach** — treating the value function as a precise mathematical model. Detection: predictions specify percentages that the underlying parameters do not support. Correction: use the model qualitatively for direction; calibrate empirically for magnitude.
- **Reference-point assumption** — assuming the analyst's reference point matches the decision-maker's. Detection: predictions fail in the field. Correction: ask or measure the reference point directly.
- **Manipulation framing** — using the model as a manipulation toolkit without informed consent. Detection: framing choices systematically disadvantage one party. Correction: hold to informed-consent standards; disclose framing choices.

## Source Citations

- Kahneman, Daniel and Amos Tversky (1979). "Prospect theory: An analysis of decision under risk." *Econometrica* 47(2):263-291. Originating paper.
- Tversky, Amos and Daniel Kahneman (1992). "Advances in prospect theory: Cumulative representation of uncertainty." *Journal of Risk and Uncertainty* 5(4):297-323. Cumulative variant.
- Kahneman, Daniel (2011). *Thinking, Fast and Slow*. Farrar, Straus and Giroux. Accessible synthesis.
- Thaler, Richard H. (1980). "Toward a positive theory of consumer choice." *Journal of Economic Behavior and Organization* 1(1):39-60. Endowment-effect application.
