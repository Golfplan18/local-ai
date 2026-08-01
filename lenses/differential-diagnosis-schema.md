---
lens_id: differential-diagnosis-schema
name: Differential Diagnosis Schema
lens_type: protocol
applicability: [differential-diagnosis]
foundational: false
source: "Sackett, David L. (1991). Clinical Epidemiology: A Basic Science for Clinical Medicine, 2nd ed. Little, Brown. Kassirer, Jerome P. (1989). Diagnostic reasoning. Annals of Internal Medicine 110(11):893-900. Eddy, David M. (1996). Clinical Decision Making: From Theory to Practice. Jones and Bartlett."
date created: 2026-05-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - protocol
  - diagnosis
  - hypothesis-comparison
---

# Differential Diagnosis Schema

## Trigger

Invoked from within the `differential-diagnosis` (T5) mode when the analyst needs a structured hypothesis-comparison procedure that is lighter than the full Heuer Analysis of Competing Hypotheses (ACH) protocol. The host mode supplies the situation requiring explanation and the candidate hypotheses; the lens supplies a five-step procedure for comparing hypotheses by evidence diagnosticity, with explicit escalation to full ACH when the lighter analysis proves borderline.

## Core Structure

**Input:** A situation requiring explanation, plus 2–5 candidate hypotheses about its cause or nature.
**Output:** A ranked hypothesis list with diagnosticity-weighted evidence support, plus a confidence assessment and an escalate-to-ACH flag when warranted.

1. **List the candidate hypotheses.** Enumerate 2–5 plausible explanations for the situation. The lens is calibrated for this range — fewer than 2 makes "differential" trivial; more than 5 makes the matrix unwieldy and triggers escalation to full ACH. Input: the host mode's situation framing. Output: a numbered hypothesis list. Sub-step: if more than 5 candidates surface, group near-duplicates or escalate immediately to Heuer ACH; do not proceed with a degraded version of this lens.

2. **List the key distinguishing evidence per hypothesis.** For each hypothesis, identify the evidence (observations, signals, base rates, expected indicators) that would best distinguish it from the others. The same piece of evidence may bear on multiple hypotheses; that is captured in the next step. Input: hypothesis list. Output: an evidence list, with a note per item identifying which hypotheses it bears on.

3. **Rate each evidence item's diagnosticity.** Diagnosticity is the degree to which the evidence distinguishes between hypotheses, not the degree to which it supports any particular one. Use a three-band rating: **high** (the evidence strongly distinguishes — observed only under one hypothesis or strongly excludes others); **medium** (the evidence somewhat distinguishes but is consistent with two or more hypotheses); **low** (the evidence is consistent with all hypotheses and so contributes nothing to the differential). Input: evidence list. Output: diagnosticity-rated evidence list.

4. **Apply a quick consistency check across hypotheses.** Strike out the **low**-diagnosticity evidence (it does not differentiate). For the remaining **high** and **medium** evidence, identify which hypothesis is best supported. The leading hypothesis is the one most consistent with the high-diagnosticity evidence — not the one that has the most evidence consistent with it overall (that scoring leads directly to the confirmation-lock failure mode below). Input: diagnosticity-rated evidence. Output: ranked hypothesis list.

5. **Note unresolved evidence and confidence level.** Flag any high-diagnosticity evidence that does not cleanly support any single hypothesis (anomalies). Assess overall confidence: **high** (one hypothesis dominates and no major anomalies); **medium** (one hypothesis leads but anomalies persist); **borderline** (two hypotheses are roughly tied, or anomalies are substantial). If confidence is borderline, flag for escalation to full Heuer ACH — the lighter procedure has reached its limits. Input: ranked hypothesis list. Output: ranking + confidence assessment + escalation flag (if warranted).

## Application Steps

1. Receive the situation and candidate hypotheses from the host mode.
2. If hypotheses exceed five, escalate to Heuer ACH rather than proceeding.
3. Run steps 1–5 of the protocol above.
4. Return the ranked hypothesis list, confidence assessment, and any anomaly flags to the host mode.
5. If the escalation flag is set, instruct the host to dispatch Heuer ACH (or recommend the user do so).

## Detection Signals

- The situation has 2–5 candidate explanations and the analyst needs a structured comparison.
- The analytical context calls for a quick read on which hypothesis is best supported, not a full intelligence-grade analysis.
- The analyst has identified candidate hypotheses but is uncertain whether the leading candidate is truly best-supported or merely the one they thought of first.
- The host mode (`differential-diagnosis`, T5) has been dispatched and explicitly references this lens in its `lens_dependencies`.
- Time, scope, or stakes do not justify the full Heuer ACH protocol, but informal hypothesis comparison would be too unstructured.

## Critical Questions

- Are the hypotheses genuinely competing — mutually exclusive in their core claims — or do they overlap? Overlapping hypotheses make differential diagnosis ill-defined; the lens requires that adopting one hypothesis would mean rejecting the others. If hypotheses can be simultaneously true, restructure them before running the protocol.
- Is the evidence rated for diagnosticity (how well it distinguishes) and not just for consistency with the leading hypothesis? Confirmation lock occurs when evidence is rated by support for the analyst's preferred hypothesis rather than by its differentiating power across hypotheses.
- Is the analysis acknowledging the lighter scope and recommending escalation to full ACH if confidence is borderline? The lens's value depends on knowing its limits; treating a borderline result as definitive defeats the purpose of the staged diagnostic approach.
- Have alternatives been generated independently of the leading hypothesis, or were they constructed as foils to make the leading hypothesis look stronger? Foil-hypotheses produce illusory differentiation; alternatives must be plausible on their own terms.
- Is the evidence list complete with respect to high-diagnosticity items, or has the analyst stopped at the first piece of supportive evidence? Premature termination of evidence-listing is a precursor to premature closure on the hypothesis ranking.

## Common Failure Modes

- **Confirmation lock** — the analyst ranks evidence by its support for the leading hypothesis rather than by its diagnosticity across hypotheses. Detection: the evidence-diagnosticity column is dominated by "supports H1" rather than by "distinguishes H1 from H2/H3." Correction: re-rate each evidence item by asking "what would I expect to see if H1 were true vs. if H2 were true?" rather than "does this evidence fit H1?"
- **Premature closure** — the analyst terminates the analysis at the first plausible hypothesis without considering the alternatives in earnest. Detection: alternatives are listed but receive no serious evidence-mapping; the diagnosticity ratings on alternatives are all "low" by default. Correction: require a minimum of one high-diagnosticity evidence item per hypothesis, even if that means actively searching for distinguishing observations the analyst has not yet considered.
- **Foil hypotheses** — alternatives are included to make the leading hypothesis look stronger by contrast, not because the analyst takes them seriously. Detection: alternatives are stated in straw-man form, or are obviously implausible given the situation. Correction: steelman each alternative before rating evidence; if the alternative cannot be steelmanned, drop it and look for a real competitor.
- **Treating borderline as definitive** — the analyst proceeds with a confident ranking when the protocol's confidence assessment is borderline. Detection: the confidence column reads "medium" or "borderline" but the host mode's output presents the leading hypothesis as if it were "high" confidence. Correction: enforce the escalation flag; either dispatch Heuer ACH or report the result with explicit borderline-confidence framing.
- **Evidence without diagnosticity column** — the protocol is run with an evidence list but no per-item diagnosticity rating. Detection: step 3 was skipped or collapsed into step 4. Correction: re-run the protocol with explicit diagnosticity ratings; without them, the lens degenerates into informal weighing.

## Source Citations

- Sackett, David L. (1991). *Clinical Epidemiology: A Basic Science for Clinical Medicine*, 2nd ed. Little, Brown. Foundational text establishing systematic approaches to clinical diagnostic reasoning.
- Kassirer, Jerome P. (1989). "Diagnostic reasoning." *Annals of Internal Medicine* 110(11):893-900. Canonical statement of hypothesis-driven differential diagnosis as a structured cognitive process.
- Eddy, David M. (1996). *Clinical Decision Making: From Theory to Practice*. Jones and Bartlett. Decision-analytic framing of diagnostic reasoning under uncertainty.
- Heuer, Richards J. (1999). *Psychology of Intelligence Analysis*. Center for the Study of Intelligence, CIA. The full ACH protocol to which this lens escalates when its lighter procedure proves insufficient.
- Related: Bayesian reasoning lens (for the underlying probabilistic frame); Heuer ACH lens (the heavier sibling protocol).
