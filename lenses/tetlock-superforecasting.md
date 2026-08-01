---
lens_id: tetlock-superforecasting
name: Tetlock Superforecasting
lens_type: protocol
applicability: [probabilistic-forecasting]
foundational: true
source: "Tetlock, Philip E., and Dan Gardner (2015). Superforecasting: The Art and Science of Prediction. Crown. Tetlock, Philip E. (2005). Expert Political Judgment. Princeton University Press. Good Judgment Project (IARPA-sponsored geopolitical forecasting tournament 2011-2015)."
date created: 2026-05-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - protocol
  - forecasting
  - decision
---

# Tetlock Superforecasting

## Trigger

Invoked from within `probabilistic-forecasting` (T6) when that mode needs the disciplined forecasting protocol that produced the Good Judgment Project's calibration results. The host mode supplies the question, the time horizon, and any available evidence; the lens supplies the ten commandments and the reference-class forecasting protocol that together structure both the initial probability assignment and the disciplined updating that follows.

## Core Structure

**Input:** A forecasting question with a clearly resolvable outcome and a defined time horizon; available evidence (base rates, indicators, expert judgments) bearing on the question.
**Output:** A calibrated probability estimate, a stated reference class, an inside-view adjustment with reasons, an explicit confidence interval, and a pre-committed updating protocol triggered by named indicators.

### The Ten Commandments

1. **Triage.** Sort questions by tractability. Some are unsolvable in the available time with the available evidence; some are trivial and require no structured forecasting; the productive zone is the middle. Operational rule: spend forecasting effort on questions where calibrated probabilities will discriminate among future actions, and where evidence permits movement off the base rate. Input: a candidate question. Output: triage verdict (forecast, defer, decline) with reason.

2. **Break problems into tractable sub-problems.** Decompose the question until each sub-question has a base rate or an evidence stream that can be assessed independently. The sub-question probabilities then combine (multiplicatively for independent conjunctions; via more careful reasoning when correlated). Input: triage-passed question. Output: a decomposition into 2-7 sub-questions plus the combination rule.

3. **Strike the right balance between inside and outside views.** The outside view is the reference class — what proportion of comparable cases produced the outcome in question. The inside view is the case's specific features and dynamics. Anchor on the outside view first; let inside-view considerations move the estimate but not dominate it. Operational rule: state the reference-class base rate before adjusting. Input: decomposed question. Output: outside-view base rate plus inside-view adjustment with reasons.

4. **Strike the right balance between under- and overreaction to evidence.** Updates should be proportional to the diagnosticity of new evidence, not to its salience or recency. A small piece of high-diagnosticity evidence (likelihood ratio far from 1) should move the estimate substantially; a large volume of low-diagnosticity evidence (likelihood ratio near 1) should not. Operational rule: when evidence arrives, ask "does this evidence look very different in worlds where the answer is yes vs. no?" If yes, update; if no, do not. Input: prior estimate plus new evidence. Output: updated estimate with diagnosticity reasoning.

5. **Look for the clashing causal forces at work.** Most non-trivial forecasting questions feature multiple causal forces pushing in different directions. Identify each, estimate its strength, and consider how their interaction shapes the outcome distribution. Avoid the failure mode of fixating on a single causal narrative. Input: question and decomposition. Output: list of major causal forces with directional and magnitude assessment.

6. **Strive to distinguish as many degrees of doubt as the problem permits.** Resist the impulse to default to round numbers (10%, 25%, 50%, 75%, 90%). Superforecasters distinguish 71% from 73% when evidence supports the discrimination. Calibration scoring rewards finer-grained distinctions when justified and penalizes them when not. Input: rough estimate. Output: refined estimate with the finest grain the evidence supports.

7. **Strike the right balance between under- and overconfidence.** Forecasters err systematically in both directions: novices toward overconfidence in detail, experts toward overconfidence in domain mastery. Calibration training corrects both. Operational rule: state confidence intervals (e.g., 80% confidence band around the point estimate) and check whether named confidence is consistent with the actual diagnosticity of the evidence. Input: point estimate. Output: point estimate plus confidence interval, with overconfidence and underconfidence checks performed.

8. **Look for the errors behind your mistakes but beware rearview-mirror hindsight.** When a forecast resolves wrongly, ask whether the error was in the probability assigned given what was known, or in what was known given what could have been learned. Avoid the failure mode of treating the resolved outcome as having been obvious in advance (hindsight bias). Input: resolved forecast. Output: error attribution distinguishing knowable-in-advance from unknowable-in-advance components.

9. **Bring out the best in others and let others bring out the best in you.** Forecasting accuracy improves with disciplined cross-examination by other forecasters who hold different priors and use different reference classes. Aggregation of independent forecasts (with weighting toward calibrated forecasters) outperforms any individual. Operational rule: subject the forecast to red-team challenge before final commitment. Input: candidate forecast. Output: forecast adjusted in light of independent challenges, with adjustment reasoning.

10. **Master the error-balancing bicycle.** Calibration is a continuous balancing act between overreaction and underreaction, between inside and outside views, between confidence and humility. There is no algorithm; there is only the discipline of monitoring one's own tendencies and correcting them. Operational rule: after each resolution, log which tendency dominated (over- or under-reaction; over- or under-confidence) and bias future forecasts in the corrective direction. Input: forecast history. Output: forecaster's tendency profile and a corrective adjustment protocol.

### Reference-Class Forecasting Protocol

Reference-class forecasting (Kahneman & Tversky's outside view, operationalized for forecasting) is the spine of the protocol. It runs as follows:

1. **Identify the reference class.** State the class of cases similar enough to the question that their outcome distribution is informative. Reference classes can be narrow (specific historical cases) or broad (statistical base rates); narrower is more informative when sample size is adequate.
2. **Compute or estimate the base rate.** What proportion of the reference class produced the outcome in question? This is the prior probability.
3. **Identify dimensions on which the case differs from the reference class.** Each named difference is a candidate inside-view adjustment.
4. **Make adjustments cautiously.** Each adjustment should be small (typically a few percentage points) and justified by an explicit causal mechanism, not by gut feeling about the case's "specialness."
5. **Document the reference class and adjustments.** A forecast accompanied by explicit reference class and adjustments is auditable and updatable; one without is opaque.
6. **Pre-commit to update triggers.** Before the forecast is filed, name the indicators that, if observed, would move the estimate by a stated amount. Pre-commitment prevents motivated post-hoc updating.

## Application Steps

1. Receive the question and time horizon from the host mode.
2. Triage (commandment 1); decompose if it passes (commandment 2).
3. Run reference-class forecasting on each sub-question to establish base rates (commandment 3).
4. Identify clashing causal forces and adjust inside-view (commandments 3, 5).
5. Refine to the finest grain the evidence supports (commandment 6); state confidence interval (commandment 7).
6. Subject to red-team challenge (commandment 9); incorporate corrections.
7. Pre-commit update triggers (reference-class protocol step 6).
8. Return the forecast, reference class, adjustment reasoning, confidence interval, and update protocol to the host mode.

## Detection Signals

- A question requires a probability estimate over a future event with a resolvable outcome.
- The host mode is `probabilistic-forecasting` and the dispatch invokes this lens explicitly.
- An analyst is being asked for a confident verdict on a question where calibrated humility would serve better.
- Multiple expert opinions are diverging and aggregation discipline is needed.
- A prior forecast needs disciplined updating in light of new evidence and the analyst risks over- or under-reacting.

## Critical Questions

- Has the question been triaged? Forecasting effort spent on unsolvable or trivial questions is wasted; the protocol applies to the productive middle.
- Has a reference class been stated explicitly? A forecast without an explicit reference class is opaque and not auditable.
- Are inside-view adjustments small and justified by causal mechanisms? Large adjustments justified by "this case is special" typically reflect overconfidence in the case's distinctiveness.
- Is the confidence interval honest about uncertainty? A narrow interval on weak evidence is overconfidence; a wide interval on strong evidence is underconfidence.
- Have update triggers been pre-committed? Post-hoc updating is vulnerable to motivated reasoning; pre-commitment disciplines the updating process.
- Has the forecast been subjected to independent challenge? Forecasts unchallenged before commitment carry the forecaster's idiosyncratic biases unfiltered.

## Common Failure Modes

- **Inside-view dominance** — anchoring on the case's specific features without consulting the reference class. Detection: the forecast cannot be decomposed into "base rate plus adjustments." Correction: force a reference class, compute its base rate, then apply adjustments.
- **Round-number anchoring** — defaulting to 10%, 25%, 50%, 75%, 90% regardless of evidence. Detection: forecast probabilities cluster suspiciously on round values. Correction: ask what evidence would justify moving from 70% to 73%; if it exists, use 73%.
- **Overreaction to vivid evidence** — updating heavily on salient but low-diagnosticity evidence. Detection: estimate moves substantially in response to evidence that does not look meaningfully different in yes-vs-no worlds. Correction: explicitly state the likelihood ratio of the evidence and update only proportional to it.
- **Underreaction to diagnostic evidence** — sticking with the prior despite evidence with substantial diagnosticity. Detection: prior estimate is unchanged in the face of evidence that should have moved it. Correction: state the likelihood ratio explicitly and apply Bayes' rule.
- **Hindsight bias on resolution** — treating resolved outcomes as having been obvious. Detection: post-resolution review claims the forecaster "should have known" without identifying the specific evidence available in advance. Correction: distinguish what was knowable in advance from what was knowable only retrospectively; calibrate against the former, not the latter.
- **Forecaster solipsism** — treating one's own forecast as definitive without aggregation or challenge. Detection: no other forecasters' estimates are consulted; no red-team challenge has occurred. Correction: aggregate with calibrated peers; subject to independent challenge before commitment.

## Source Citations

- Tetlock, Philip E., and Dan Gardner (2015). *Superforecasting: The Art and Science of Prediction*. Crown. The accessible exposition of the ten commandments and the Good Judgment Project findings.
- Tetlock, Philip E. (2005). *Expert Political Judgment: How Good Is It? How Can We Know?* Princeton University Press. The foundational empirical work establishing that domain-expert forecasts are typically not better than chance, with the "fox vs. hedgehog" cognitive-style finding.
- Mellers, Barbara, et al. (2014). "Psychological strategies for winning a geopolitical forecasting tournament." *Psychological Science* 25(5):1106-1115. The Good Judgment Project's findings on what distinguishes superforecasters.
- Mellers, Barbara, et al. (2015). "The psychology of intelligence analysis: Drivers of prediction accuracy in world politics." *Journal of Experimental Psychology: Applied* 21(1):1-14. Empirical decomposition of accuracy drivers.
- Kahneman, Daniel, and Amos Tversky (1979). "Intuitive prediction: Biases and corrective procedures." *TIMS Studies in Management Science* 12:313-327. The originating reference-class / outside-view paper.
- Related: Brier scoring (the calibration metric used in the Good Judgment Project); Heuer ACH (a complementary structured-analysis protocol for hypothesis evaluation).
