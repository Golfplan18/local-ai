---
lens_id: base-rate-neglect
name: Base Rate Neglect
lens_type: mental-model
applicability: [bias-audit, diagnostic-quality-review, screening-design]
foundational: false
source: "Kahneman, Daniel, and Amos Tversky (1973). On the Psychology of Prediction. Psychological Review 80(4):237-251. Bar-Hillel, Maya (1980). The base-rate fallacy in probability judgments. Acta Psychologica 44(3):211-233."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - probability
  - cognition
---

# Base Rate Neglect

*A lens that explains how people focus on individuating evidence and ignore the prior frequency of the category being judged, producing systematic errors that are most severe when categories are rare and individuating evidence is moderately diagnostic.*

---

## Trigger

Invoked when a probability or classification judgment appears to track the strength of case-specific evidence without incorporating the underlying frequency of the category, especially when a positive result from a moderately accurate test is being treated as confirmation of a rare condition. The lens supplies Bayes' theorem as the corrective and the diagnostic that ignoring base rates is the dominant cause of false-positive over-confidence in screening systems.

## Core Structure

### Core Insight

When judging the probability that something belongs to a category, people focus on how well it matches the category description (representativeness) and ignore how common that category is in the population (the base rate). A positive result from a 95%-accurate test means very little if the condition it detects occurs in only 1 in 10,000 people — most positives will be false. The error is systematic and persists even when subjects are explicitly given the base rate.

### Mechanism

The cognitive system compares the case to the category prototype and treats the strength of the match as the probability of category membership. The base rate enters explicitly into Bayes' theorem (P(Category|Evidence) = P(Evidence|Category) × P(Category) / P(Evidence)), but the prior P(Category) — the base rate — is given little weight in intuitive judgment. When the base rate is low and the evidence is moderately diagnostic, the false-positive rate (cases where the evidence appears but the category is absent) dominates the true-positive rate; ignoring the base rate hides this and produces an over-confident classification.

### Applicability Conditions

- A probability or classification judgment is being formed about a specific case.
- A base rate exists (the category has a definable frequency in the relevant population).
- Individuating evidence is available (a test result, a profile, a story).
- The base rate is materially different from 50%; the bias is most consequential when the category is rare.

### Common Misapplications

- Failing to identify the relevant population for the base rate; the wrong base rate produces wrong answers.
- Over-correcting by ignoring strong individuating evidence in favor of the base rate; both should be weighted per Bayes.
- Conflating with availability (the category may *seem* common because it is vivid, not because it actually is); availability and base-rate neglect interact.

### Related Models

- **Bayesian Reasoning** — the formal corrective; base-rate neglect is the failure to apply Bayes intuitively.
- **Availability Heuristic** — a related cause of base-rate distortion (the perceived base rate is inflated by recall ease).
- **Representativeness Heuristic** — the cognitive operation that substitutes for base-rate weighting.

## Application Steps

1. Identify the base rate: how common is the condition or category in the relevant population?
2. Identify the evidence's diagnostic strength: P(Evidence|Category) and P(Evidence|Not-Category).
3. Apply Bayes' theorem (even roughly): combine the base rate with the evidence to get the posterior probability.
4. Compare the Bayesian posterior to the analyst's intuitive estimate; the gap measures the base-rate neglect.
5. When base rates are very low, expect most positive signals to be false positives and design downstream review tiers accordingly.

## Detection Signals

- A test, screen, or alert has flagged a rare condition and the analyst is treating the flag as near-certain confirmation.
- Vivid case-specific evidence is being weighted heavily; statistical base rates are not being mentioned.
- A story or profile feels like a strong match for a category and the analyst defends the classification by reciting the matching features.
- A detection or classification system is being designed without specifying its expected false-positive rate at the operating base rate.
- The analyst can recite the base rate when asked but does not incorporate it into the working judgment.

## Critical Questions

- What is the base rate of the category in the relevant population, and is the relevant population the right one for the question?
- What is the evidence's diagnostic strength — both P(Evidence|Category) and P(Evidence|Not-Category)? Without the second, Bayes cannot be applied.
- Has Bayes been applied (even approximately), or has the analyst stopped at the strength of the match?
- Are most positives in this system likely to be false positives at the operating base rate? If yes, what review tier addresses them?
- Is the base rate stable, or is it changing in ways that affect the calculation?

## Common Failure Modes

- **Match-as-classification** — strong feature match is treated as classification certainty. Detection: the analyst cites matching features without citing the base rate. Correction: require explicit base-rate citation in any classification judgment.
- **Wrong-population base rate** — the base rate is computed for the wrong reference class. Detection: the population from which the base rate is drawn does not include the case under judgment, or includes irrelevant cases. Correction: define the reference class precisely; re-compute.
- **Base-rate over-correction** — the analyst dismisses strong evidence in favor of the base rate. Detection: the posterior is unchanged from the prior despite genuinely diagnostic evidence. Correction: weight evidence per Bayes; the goal is integration, not replacement.
- **Hidden screening cost** — a system is deployed without analyzing its false-positive rate at the operating base rate, producing alert overload. Detection: alerts are mostly false and operators begin ignoring them. Correction: design downstream review tiers proportionate to the predicted false-positive volume.

## Source Citations

- Kahneman, Daniel, and Amos Tversky (1973). "On the Psychology of Prediction." *Psychological Review* 80(4):237-251. Foundational paper.
- Bar-Hillel, Maya (1980). "The base-rate fallacy in probability judgments." *Acta Psychologica* 44(3):211-233. Comprehensive review and extensions.
- Gigerenzer, Gerd, and Ulrich Hoffrage (1995). "How to improve Bayesian reasoning without instruction: Frequency formats." *Psychological Review* 102(4):684-704. The natural-frequency corrective.
- Related: Bayesian Reasoning; Representativeness Heuristic.
