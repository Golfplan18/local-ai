---
lens_id: representativeness-heuristic
name: Representativeness Heuristic
lens_type: mental-model
applicability: [judgment-bias-detection, probability-evaluation, diagnostic-reasoning]
foundational: false
source: "Tversky, Amos and Daniel Kahneman (1972). 'Subjective probability: A judgment of representativeness.' *Cognitive Psychology* 3(3):430-454."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - cognition
  - probability
---

# Representativeness Heuristic

## Trigger

Invoked from modes that evaluate probability judgments, assess diagnostic reasoning, or analyze category-membership claims — when judgment is being made by similarity to a prototype rather than by base-rate-anchored estimation. The host mode supplies the judgment and its supporting reasoning; the lens supplies the resemblance-vs-frequency diagnostic that surfaces base-rate neglect.

## Core Structure

### Core Insight

When judging whether A belongs to category B, people rely on how much A resembles their mental image of B — ignoring base rates, sample sizes, and statistical structure. This is why a shy, detail-oriented person is judged "probably a librarian" despite librarians being vastly outnumbered by other professions with shy members. Tversky and Kahneman showed that representativeness leads to base-rate neglect, the conjunction fallacy (Linda the bank teller), and insensitivity to sample size.

### Mechanism

System 1 generates rapid similarity judgments by matching observed features against stored prototypes. The judgment is fast and feels confident, but it ignores prior probability of category membership. When the prototype is rare in the population, similarity-based judgment produces probability estimates that systematically exceed the actual likelihood. The heuristic also produces the conjunction fallacy: "feminist bank teller" is judged more likely than "bank teller" because the conjunction matches the prototype more closely.

### Applicability Conditions

- Judgment of probability or category membership is being made.
- A prototype or stereotype is salient.
- Base rates are available but not being centrally weighted.
- The decision-maker is operating under time pressure or without explicit statistical training.

### Common Misapplications

- Using the lens to dismiss all prototype-based reasoning, including legitimate domain expertise.
- Failing to apply when the prototype is actually well-calibrated to base rates.
- Treating base-rate neglect as the only failure mode (conjunction fallacy and sample-size insensitivity also apply).
- Conflating with availability heuristic (similar surface, different mechanism).

### Related Models

- **Base Rate Neglect** — the dominant failure mode this lens corrects.
- **Availability Heuristic** — adjacent System-1 substitution that operates on different cues.
- **Bayesian Reasoning** — the formal corrective for representativeness errors.

### Worked example

A venture capitalist meets a founder who went to Stanford, previously worked at Google, and has a polished pitch deck. The founder "looks like" a successful startup CEO. The VC's representativeness heuristic fires: this person matches the prototype. But the base rate of startup success is roughly 10%, and the attributes described are common among both successful and failed founders. A disciplined investor asks: "What is the base rate of success for companies at this stage?" and adjusts the prototype-based impression accordingly.

## Application Steps

1. Always start with the base rate: how common is this category in the relevant population?
2. Ask: "Am I judging probability by resemblance or by frequency?" — resemblance is the trap.
3. Check for the conjunction fallacy: a more detailed description cannot be more probable than a less detailed one.
4. Demand sample size: small samples produce extreme results that look representative but are just noise.
5. Separate the story from the statistics — a coherent narrative is not evidence of high probability.

## Detection Signals

- A vivid narrative or stereotype is available for the judgment.
- A personality description "feels like" it belongs to a rare category.
- Someone argues that a sequence of events is likely because it tells a coherent story.
- Small-sample results are being treated as definitive.
- Diagnostic reasoning in medicine, hiring, risk assessment, or criminal profiling.

## Critical Questions

- What is the relevant base rate, and how does it compare to the prototype-based estimate?
- Is the prototype itself well-calibrated, or is it shaped by selection effects?
- Has the analyst checked for conjunction fallacy by comparing the detailed and undetailed descriptions?
- Is the sample size large enough to distinguish the claimed pattern from chance?
- Would the judgment change if the prototype features were absent?

## Common Failure Modes

- **Base-rate omission** — making category-membership claims without ever stating the base rate. Detection: probability estimates lack reference to population frequency. Correction: require explicit base-rate statement before specific-evidence adjustment.
- **Conjunction inflation** — adding details that make the description more vivid and judging the conjunction more probable. Detection: longer descriptions feel more likely. Correction: explicitly compare the detailed claim's probability to the briefer claim it implies.
- **Prototype fetishism** — believing the prototype is reality. Detection: judgments confidently exceed what evidence would support. Correction: treat prototypes as hypotheses to test against base rates and individual evidence.

## Source Citations

- Tversky, Amos and Daniel Kahneman (1972). "Subjective probability: A judgment of representativeness." *Cognitive Psychology* 3(3):430-454. Originating paper.
- Tversky, Amos and Daniel Kahneman (1983). "Extensional versus intuitive reasoning: The conjunction fallacy in probability judgment." *Psychological Review* 90(4):293-315. Conjunction-fallacy formalization.
- Kahneman, Daniel (2011). *Thinking, Fast and Slow*. Farrar, Straus and Giroux. Accessible synthesis with the Linda problem.
- Gigerenzer, Gerd (1991). "How to make cognitive illusions disappear: Beyond 'heuristics and biases.'" *European Review of Social Psychology* 2(1):83-115. Counterpoint on framing effects.
