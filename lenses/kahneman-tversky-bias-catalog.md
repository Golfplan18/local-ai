---
lens_id: kahneman-tversky-bias-catalog
name: Kahneman-Tversky Bias Catalog
lens_type: catalog
applicability: [judgment-quality-review, decision-architecture, evidence-evaluation, cross-mode-bias-audit]
foundational: true
source: "Tversky, Amos and Kahneman, Daniel (1974). Judgment under Uncertainty: Heuristics and Biases. Science 185(4157):1124-1131; Kahneman, Daniel (2011). Thinking, Fast and Slow."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - catalog
  - cognition
  - bias
  - decision
---

# Kahneman-Tversky Bias Catalog

## Trigger

Invoked from any mode when human judgment, evidence weighting, forecasting, value elicitation, or decision framing may be distorted by systematic cognitive bias. The host mode supplies the object of judgment and the decision context; the lens supplies a compact bias scan so the analyst can identify where intuitive judgment may be substituting an easier question for the one actually being asked.

## Core Structure

This catalog groups the most common Kahneman-Tversky and closely related behavioral-judgment biases by the cognitive operation that produces them.

1. **Anchoring and adjustment.** Initial numbers, frames, examples, or salient reference points pull later estimates toward themselves, even when the anchor is arbitrary. Use when a valuation, forecast, weight, or threshold appears to inherit its shape from the first value encountered.

2. **Availability heuristic.** Events that are vivid, recent, emotionally intense, or easy to recall are judged more likely than they are. Use when salience is standing in for frequency.

3. **Representativeness heuristic.** A case is judged by resemblance to a prototype rather than by base rates and diagnostic evidence. Use when a story "looks like" a category and the analyst treats that match as probability.

4. **Base-rate neglect.** Prior frequencies are ignored when case-specific evidence is vivid or narratively satisfying. Use when an assessment of a rare event or category does not explicitly integrate the relevant base rate.

5. **Framing effect.** Equivalent information produces different choices when expressed as gain vs. loss, survival vs. mortality, default vs. opt-in, or problem vs. opportunity. Use when the conclusion changes with wording while the underlying facts do not.

6. **Prospect-theory pattern.** People evaluate outcomes relative to a reference point, overweight losses relative to gains, and distort probabilities. Use when risk posture changes between gains and losses or when small probabilities dominate behavior.

7. **Loss aversion.** Avoiding a loss is weighted more strongly than obtaining an equivalent gain. Use when a party resists a trade or reform because the losses are concrete and the gains are diffuse.

8. **Status quo and endowment effects.** What is already held, defaulted, or owned receives extra weight because departure from it feels like a loss. Use when current arrangements are defended more strongly than an equivalent new option would be chosen.

9. **Sunk cost and commitment escalation.** Past unrecoverable investment is treated as a reason to continue rather than as irrelevant to the next decision. Use when "we have already spent too much" becomes an argument against stopping.

10. **Confirmation bias.** Evidence that supports a working hypothesis is noticed, remembered, and interpreted more favorably than evidence against it. Use when the analysis searches for support rather than discriminating tests.

11. **Hindsight bias.** Once an outcome is known, it appears more predictable than it was. Use in post-mortems, blame analysis, and forecasting review when people treat what happened as what should have been obvious.

12. **Illusion of validity and overconfidence.** Coherent stories and confident pattern recognition create unwarranted certainty. Use when a judgment feels strong because the explanation is fluent, not because the evidence is diagnostic.

## Application Steps

1. Identify the judgment being made: estimate, classification, causal claim, forecast, preference, or choice.
2. Identify the reference point, initial anchor, salient story, default, or emotional cue shaping the judgment.
3. Check whether base rates, disconfirming evidence, and alternative frames have been explicitly considered.
4. Name the likely bias pattern and state how it could distort the current analysis.
5. Apply the correction: re-anchor on base rates, reframe symmetrically, seek disconfirming tests, or separate sunk costs from future consequences.

## Detection Signals

- The analysis relies on a vivid example, recent case, or emotionally salient incident.
- A number, threshold, weight, or probability appears close to the first value mentioned.
- A category judgment is defended by resemblance rather than by base rates.
- Equivalent facts produce different conclusions when framed differently.
- A post-mortem treats the outcome as obvious in retrospect.
- Prior investment is used as a reason to continue a failing course.
- The conclusion feels coherent but the evidence base is thin.

## Critical Questions

- What is the relevant base rate, and has it been integrated rather than merely mentioned?
- What anchor or reference point is shaping the estimate, and would the answer change if a different anchor were supplied?
- Is the conclusion invariant under an equivalent gain/loss or default/opt-in frame?
- What evidence would be diagnostic against the favored interpretation?
- Are sunk costs being separated from future costs and benefits?
- Is the confidence level justified by evidence quality, or by story coherence?

## Common Failure Modes

- **Bias-name-drop** - Detection: the analysis names a bias but does not show how it changes the current judgment. Correction: identify the distorted variable and rerun the judgment with a correction.
- **All-bias cynicism** - Detection: every disagreement is treated as bias. Correction: distinguish bias from legitimate value conflict, information asymmetry, or different incentives.
- **One-sided debiasing** - Detection: bias is applied only to the opposing view. Correction: run the same bias scan on the analyst's preferred conclusion.
- **Base-rate tokenism** - Detection: base rates are mentioned but not used to update probability. Correction: force a before/after estimate.
- **Frame manipulation** - Detection: framing is used to steer the user rather than clarify choices. Correction: present symmetric frames and name the reference point.

## Source Citations

- Tversky, Amos and Kahneman, Daniel (1974). "Judgment under Uncertainty: Heuristics and Biases." *Science* 185(4157):1124-1131.
- Kahneman, Daniel and Tversky, Amos (1979). "Prospect Theory: An Analysis of Decision under Risk." *Econometrica* 47(2):263-291.
- Tversky, Amos and Kahneman, Daniel (1981). "The Framing of Decisions and the Psychology of Choice." *Science* 211(4481):453-458.
- Kahneman, Daniel (2011). *Thinking, Fast and Slow*. Farrar, Straus and Giroux.
- Related runtime lenses: Anchoring, Availability Heuristic, Base Rate Neglect, Framing Effect, Loss Aversion, Prospect Theory, Representativeness Heuristic, Status Quo Bias, Sunk Cost Fallacy, Confirmation Bias, Hindsight Bias.
