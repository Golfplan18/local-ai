---
lens_id: wisdom-of-crowds
name: Wisdom of Crowds
lens_type: mental-model
applicability: [forecasting, estimation, prediction-market-design]
foundational: false
source: "Surowiecki, James (2004). *The Wisdom of Crowds*. Doubleday; Galton, Francis (1907). 'Vox populi.' *Nature* 75:450-451."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - prediction
  - aggregation
---

# Wisdom of Crowds

## Trigger

Invoked from modes that design forecasting systems, aggregate estimates, or evaluate when collective judgment outperforms individual experts — prediction markets, planning poker, jury decisions. The host mode supplies the estimation problem and the candidate participants; the lens supplies the four-conditions diagnostic (diversity, independence, decentralization, aggregation) that distinguishes wise crowds from herding ones.

## Core Structure

### Core Insight

When individuals form judgments independently, the aggregate of those judgments often outperforms any single expert. The errors cancel out while the signal accumulates. This requires four conditions: diversity of opinion, independence, decentralization, and a good aggregation mechanism. James Surowiecki formalized the concept; Francis Galton demonstrated it in 1906 when the median guess of a county fair crowd estimating an ox's weight was off by less than 1%.

### Mechanism

When each estimator's error has independent random components, averaging cancels out the noise while preserving the systematic signal. The cancellation requires error independence; if estimators copy each other, errors correlate and the aggregation fails. Diversity ensures different error structures (so they cancel rather than reinforce). Decentralization prevents single-source contamination. The aggregation mechanism (median, mean, weighted average) determines how robustly errors cancel.

### Applicability Conditions

- The estimators form judgments independently.
- The estimator pool is diverse in information and reasoning.
- The estimators are decentralized (no central authority shaping their views).
- A good aggregation mechanism is available.

### Common Misapplications

- Aggregating opinions formed in a discussion (independence violated).
- Treating any large group as wise without checking the four conditions.
- Using mean when median is more robust to outliers.
- Failing to recognize that wisdom of crowds is domain-specific (works better in some domains than others).

### Related Models

- **Information Cascade** — what happens when independence breaks down.
- **Tetlock Superforecasting** — disciplined extension to expert forecaster pools.
- **Prediction Markets** — institutional implementation.

### Worked example

A software team needs to estimate how long a feature will take. Instead of deferring to the tech lead, they use planning poker: each developer independently estimates, then all reveal simultaneously. The estimates range from 3 to 13 story points. The outliers explain their reasoning — the high estimator knows about a hidden dependency, the low estimator has done similar work before. The median of 8 points, informed by the discussion but not anchored by the first speaker, proves more accurate than the tech lead's solo guess of 5.

## Application Steps

1. Collect estimates or judgments from as many independent sources as possible.
2. Ensure independence: participants must not see each other's answers before committing their own.
3. Ensure diversity: include people with different backgrounds, information sets, and analytical approaches.
4. Aggregate using median or mean — median is more robust to outliers.
5. Check the conditions: if estimates were made socially (discussion, anchoring, groupthink), the crowd is no longer wise.

## Detection Signals

- An estimate is needed and no single expert is clearly reliable.
- Designing a forecasting system, prediction market, or estimation process.
- A group is converging on a consensus too quickly — threatening the independence condition.
- Evaluating whether a collective judgment is actually wise or merely a cascade of social influence.
- Deciding how much weight to give expert opinion vs. aggregated non-expert estimates.

## Critical Questions

- Were the estimates formed independently, or did participants see each other's answers?
- Is the estimator pool diverse enough that errors will cancel rather than reinforce?
- Is the aggregation mechanism robust to outliers and gaming?
- Is the domain one where crowd wisdom typically performs well?
- Has the analyst tested the aggregation against held-out cases?

## Common Failure Modes

- **Independence violation** — discussion before estimation contaminates independence. Detection: estimates cluster more than independent error model would predict. Correction: enforce private estimation before any group discussion.
- **Diversity collapse** — all estimators come from the same background or training. Detection: errors correlate strongly. Correction: actively recruit diverse estimators.
- **Wrong-aggregation choice** — using mean when extreme outliers distort. Detection: aggregate is dominated by outliers. Correction: switch to median; use trimmed mean for moderate cases.

## Source Citations

- Surowiecki, James (2004). *The Wisdom of Crowds*. Doubleday. Originating modern formulation.
- Galton, Francis (1907). "Vox populi." *Nature* 75:450-451. Originating empirical demonstration.
- Page, Scott E. (2007). *The Difference: How the Power of Diversity Creates Better Groups, Firms, Schools, and Societies*. Princeton University Press. Diversity formalization.
- Tetlock, Philip E. and Dan Gardner (2015). *Superforecasting*. Crown. Disciplined-aggregation extension.
