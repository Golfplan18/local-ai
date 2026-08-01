---
lens_id: decoy-effect
name: Decoy Effect
lens_type: mental-model
applicability: [bias-audit, choice-architecture, pricing-analysis, negotiation-anchoring]
foundational: false
source: "Huber, Joel, John W. Payne, and Christopher Puto (1982). Adding asymmetrically dominated alternatives: Violations of regularity and the similarity hypothesis. Journal of Consumer Research 9(1):90-98."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - behavioral-economics
  - choice
---

# Decoy Effect

## Trigger

Invoked from within bias-audit, choice-architecture, and pricing-analysis modes when an analyst observes that a third option in a choice set appears to exist only to make another option look better, or when preferences shift after adding an alternative that is itself rarely chosen. The host mode supplies the choice set under analysis (pricing tiers, product variants, negotiation offers); the lens supplies the asymmetric-dominance diagnostic and the protocol for identifying the target option, the decoy, and whether to remove the decoy mentally for a clean evaluation.

## Core Structure

### Core Insight

Adding an asymmetrically dominated option — one that is clearly worse than one alternative and only slightly worse than another — shifts preferences toward the dominating option. The decoy is rarely chosen itself; its function is to make the target option look like a better deal by comparison. The phenomenon (also called the attraction effect) violates the rational assumption that adding irrelevant alternatives should not change preferences between existing ones.

### Mechanism

The mind compares options on multiple attributes simultaneously. When a new option is dominated by one existing option but not by another, the comparison highlights the dominance relationship and the dominating option becomes the easy choice — the comparison feels conclusive even though the original two-option decision was genuinely difficult. The decoy reframes the question from "do I want X or Y?" to "obviously not the dominated option, and if not that, then the option that dominates it." The reframing exploits a comparison-by-comparison evaluation strategy rather than a holistic value judgment.

### Applicability Conditions

- A choice set has at least three options.
- One option is asymmetrically dominated (clearly worse than one alternative on key attributes, but not clearly worse than another).
- The decision-maker is using attribute-by-attribute comparison rather than holistic evaluation.
- Preferences in the two-option subset (without the decoy) would be different from preferences in the three-option set.

### Common Misapplications

- Diagnosing the decoy effect whenever a choice set has three options, including cases where each option is genuinely on a Pareto frontier.
- Treating any pricing tier that is rarely chosen as a decoy when it may be a legitimate option targeted at a small segment.

### Related Models

- **Anchoring** — the broader category of reference-point manipulation; decoy effect is anchoring via dominance comparison.
- **Choice Architecture (Thaler-Sunstein)** — the engineering discipline that uses decoy effects intentionally.
- **Framing Effect** — adjacent reference-point manipulation through wording rather than alternatives.

## Application Steps

1. Identify the two real options the chooser is deciding between.
2. Look for a third option that is clearly inferior to one but competitive with the other.
3. Determine which option the decoy makes look better — that is the target.
4. If designing a choice set: create a decoy that is dominated on the key attribute of the option you want chosen.
5. If defending against a decoy: remove the decoy mentally and re-evaluate only the genuine alternatives.

## Detection Signals

- A pricing structure has three tiers and one tier seems pointless or rarely chosen.
- Product offerings include a "bad middle option" that appears designed to make a premium option attractive.
- A choice set has recently expanded and preferences have shifted without new information.
- A negotiation offer appears designed as an anchor rather than as a genuine alternative.

## Critical Questions

- Is the dominated option genuinely dominated, or does it serve a small segment with different preferences? Misdiagnosing a niche option as a decoy removes a legitimate choice.
- Would the decision-maker's preference change if the decoy were removed? If the answer is no, the decoy effect is not operative.
- Is the decoy creating value or extracting it? In choice-architecture design for the chooser's benefit, decoys can guide; in extraction design, they manipulate.
- Has the chooser been informed that the option set includes a designed decoy? Disclosure changes the ethical and practical character of the design.

## Common Failure Modes

- **Three-option = decoy assumption** — Detection signal: any three-option set is automatically diagnosed as containing a decoy. Correction: verify asymmetric dominance and verify preference shift before invoking the bias.
- **Niche-option misclassification** — Detection signal: an option targeted at a small segment is removed as a decoy, eliminating a legitimate choice. Correction: check whether the rarely-chosen option is dominated or just niche.
- **Manipulation framing** — Detection signal: the lens is invoked solely to indict a designer of manipulation, missing cases where decoys serve choice clarity. Correction: distinguish decoys-for-choice-quality from decoys-for-extraction.

## Source Citations

- Huber, Joel, John W. Payne, and Christopher Puto (1982). Adding asymmetrically dominated alternatives: Violations of regularity and the similarity hypothesis. *Journal of Consumer Research* 9(1):90-98.
- Ariely, Dan (2008). *Predictably Irrational*. HarperCollins.
- Thaler, Richard H. and Cass R. Sunstein (2008). *Nudge: Improving Decisions About Health, Wealth, and Happiness*. Yale University Press.
