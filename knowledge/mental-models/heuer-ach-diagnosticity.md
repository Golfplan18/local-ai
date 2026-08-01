---
lens_id: heuer-ach-diagnosticity
name: Heuer ACH Diagnosticity
lens_type: analytical-framework
applicability: [bayesian-hypothesis-network]
foundational: true
source: "Heuer, Richards J. (1999). Psychology of Intelligence Analysis. Center for the Study of Intelligence."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - intelligence-analysis
  - evidence
  - bayesian
---

# Heuer ACH Diagnosticity

## Trigger

Invoked when a hypothesis-network mode needs to judge which evidence actually distinguishes hypotheses. The host mode supplies hypotheses and observations; the lens supplies Heuer's diagnosticity discipline from Analysis of Competing Hypotheses.

## Core Structure

Evidence is diagnostic when it is much more expected under one hypothesis than under its competitors. Evidence that is consistent with every hypothesis is weak, even if it feels supportive.

1. **Hypothesis set.** The live alternatives under consideration.
2. **Evidence item.** A discrete observation, report, fact, or absence.
3. **Consistency pattern.** Which hypotheses the evidence fits or conflicts with.
4. **Diagnostic value.** How strongly the evidence separates hypotheses.
5. **Disconfirming weight.** Evidence that contradicts a hypothesis often matters more than confirmatory evidence.

## Application Steps

1. List all live hypotheses before scoring evidence.
2. For each evidence item, ask how expected it is under each hypothesis.
3. Mark evidence that fits all hypotheses as low diagnosticity.
4. Highlight evidence that sharply conflicts with one or more hypotheses.
5. Use the most diagnostic evidence to update the hypothesis network.
6. Preserve uncertainty where evidence quality or source reliability is weak.

## Detection Signals

- Analysts are accumulating evidence for a favored hypothesis.
- Several hypotheses can explain the same facts.
- The mode needs to distinguish support from discrimination.
- An absence of evidence may be diagnostic under some hypotheses.

## Critical Questions

- Which hypothesis would have predicted this evidence least?
- Does this evidence separate hypotheses or merely fit the story?
- What evidence would be surprising if the favored hypothesis were true?
- Is source reliability being confused with diagnosticity?
- Are missing observations being evaluated where they should have appeared?

## Common Failure Modes

- **Confirmation pile** - Detection: evidence is listed because it supports the favorite. Correction: score it against all hypotheses.
- **Non-diagnostic support** - Detection: an item fits every hypothesis. Correction: downgrade it.
- **Evidence-quality confusion** - Detection: reliable evidence is treated as diagnostic by default. Correction: separate credibility from discriminating power.
- **Hypothesis lock-in** - Detection: new hypotheses are excluded after evidence review begins. Correction: reopen the hypothesis set when evidence does not fit.

## Source Citations

- Heuer, Richards J. (1999). *Psychology of Intelligence Analysis*. Center for the Study of Intelligence.
- Heuer, Richards J. and Pherson, Randolph H. (2014). *Structured Analytic Techniques for Intelligence Analysis*. CQ Press.

