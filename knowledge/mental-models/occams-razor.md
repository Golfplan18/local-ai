---
lens_id: occams-razor
name: Occam's Razor
lens_type: mental-model
applicability: [hypothesis-evaluation, debugging, abductive-reasoning]
foundational: false
source: "Attributed to William of Ockham (c. 1287–1347); modern formalization in Sober, Elliott (2015). *Ockham's Razors*. Cambridge University Press."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - reasoning
  - epistemology
---

# Occam's Razor

## Trigger

Invoked from modes that evaluate competing explanations or hypotheses — abductive reasoning, debugging, diagnostic analysis, theory comparison — when multiple accounts could explain the same evidence and a tie-break is needed. The host mode supplies the candidate explanations and the evidence; the lens supplies the parsimony preference that breaks ties and orders investigation.

## Core Structure

### Core Insight

Among competing explanations that account for the same evidence, prefer the one with the fewest assumptions. This is not a law of nature — simpler explanations are not guaranteed to be correct — but they are more likely to be correct because each additional assumption is an additional chance to be wrong. William of Ockham: "Entities must not be multiplied beyond necessity."

### Mechanism

Each assumption in an explanation has some probability of being false; assumptions combine multiplicatively when they are independent. An explanation with five independent assumptions each at 80% confidence is roughly 33% likely to hold; reducing to two assumptions raises that to 64%. Beyond probability, simpler explanations are easier to test, more falsifiable, and impose lower epistemic costs. The razor is a decision procedure for ordering investigation, not a verdict on truth.

### Applicability Conditions

- Multiple explanations genuinely account for the same evidence.
- Differences in assumption count are meaningful (not splitting hairs).
- The simpler explanation is not actually too simple to cover the evidence.
- Empirical testing of the simpler explanation is feasible as a next step.

### Common Misapplications

- Preferring a simple but inadequate explanation that fails to cover evidence.
- Counting assumptions inconsistently across competing explanations.
- Confusing simplicity of statement with simplicity of underlying assumptions.
- Treating the razor as a final verdict rather than an investigation-ordering principle.

### Related Models

- **Falsifiability** — the parsimonious explanation should still be testable.
- **Hanlon's Razor** — domain-specific application: prefer incompetence over malice.
- **First Principles** — complement: when simple explanations fail, derive from foundations rather than adding patches.

### Worked example

A web application starts returning 500 errors after a deploy. Complex hypothesis: a race condition in the new async code triggers a deadlock under specific load patterns that only manifests in production due to network latency differences. Simple hypothesis: the deploy introduced a typo in an environment variable and the database connection string is wrong. Check the simple one first — inspect the environment config. Nine times out of ten, the mundane explanation is the right one.

## Application Steps

1. List all plausible explanations for the observed evidence.
2. For each, count the independent assumptions required.
3. Check that simpler explanations truly account for all the evidence — do not oversimplify.
4. Prefer the explanation with fewer assumptions as the working hypothesis.
5. Test the simplest explanation first; escalate to complex ones only when the simple ones fail.

## Detection Signals

- Two or more hypotheses explain the same observations equally well.
- A proposed explanation requires a long chain of unlikely coincidences.
- A debugging session is going down increasingly exotic rabbit holes.
- A conspiracy theory is competing with a mundane explanation.
- Architecture or design is accumulating complexity without clear benefit.

## Critical Questions

- Does the simpler explanation actually account for all the evidence, or only most of it?
- Have assumptions been counted consistently across hypotheses?
- Is the apparent simplicity of one explanation hiding implicit assumptions?
- Is the choice of "simpler" robust to small changes in framing?
- What evidence would distinguish the competing explanations?

## Common Failure Modes

- **Premature simplification** — accepting a simple explanation that does not cover the evidence. Detection: residual unexplained data. Correction: keep the explanation that covers the data, even if more complex.
- **Assumption miscount** — implicit assumptions in the "simple" hypothesis make it actually more complex. Detection: when forced to articulate, the simple hypothesis requires many tacit conditions. Correction: enumerate assumptions explicitly.
- **Razor-as-verdict** — using parsimony to declare the question settled rather than ordering tests. Detection: no empirical follow-up planned. Correction: simpler-first means test first, not "decided first."

## Source Citations

- William of Ockham, *Summa Logicae* (c. 1323). Original principle source.
- Sober, Elliott (2015). *Ockham's Razors: A User's Manual*. Cambridge University Press. Modern philosophical analysis.
- Jefferys, William H. and James O. Berger (1992). "Ockham's razor and Bayesian analysis." *American Scientist* 80(1):64-72. Bayesian formalization.
- Solomonoff, Ray (1964). "A formal theory of inductive inference." *Information and Control* 7(1):1-22. Algorithmic-information formalization.
