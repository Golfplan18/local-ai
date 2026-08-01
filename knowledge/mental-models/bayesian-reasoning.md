---
lens_id: bayesian-reasoning
name: Bayesian Reasoning
lens_type: mental-model
applicability: [belief-updating, evidence-evaluation, forecast-revision]
foundational: false
source: "Bayes, Thomas (1763). An Essay towards solving a Problem in the Doctrine of Chances. Philosophical Transactions of the Royal Society 53:370-418. Jaynes, E.T. (2003). Probability Theory: The Logic of Science. Cambridge University Press."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - probability
  - reasoning
---

# Bayesian Reasoning

*A lens that prescribes how beliefs should be updated when new evidence arrives: weight the evidence by its diagnostic strength and combine it with the prior probability via Bayes' theorem to produce a coherent posterior.*

---

## Trigger

Invoked when new evidence arrives and beliefs need updating, when the analyst is tempted to over-react or under-react to a single data point, or when two analysts viewing the same evidence reach opposite conclusions and the source of disagreement (priors vs. evidence) needs to be diagnosed. The lens supplies Bayes' theorem as the coherence constraint and the operational discipline of stating priors and likelihoods explicitly before computing the posterior.

## Core Structure

### Core Insight

Update beliefs proportionally to the strength of new evidence, weighted by how probable those beliefs were before the evidence arrived. Bayes' theorem — P(H|E) = P(E|H) × P(H) / P(E) — formalizes this. A hypothesis already likely needs less evidence to confirm; an extraordinary claim requires extraordinary evidence. Ignoring priors produces overreaction; ignoring evidence produces stubbornness.

### Mechanism

The probability of a hypothesis after observing evidence depends on three components: the prior probability of the hypothesis, the likelihood of the evidence given the hypothesis is true, and the likelihood of the evidence given the hypothesis is false. Strong evidence is evidence that would be much more likely under one hypothesis than another; weak evidence is evidence roughly equally likely under both. The posterior is the prior multiplied by the likelihood ratio, normalized. Coherence over time requires that today's posterior become tomorrow's prior, with each update conditional on accumulated evidence.

### Applicability Conditions

- A hypothesis can be stated with a definable prior probability (even a rough estimate).
- New evidence is observable and its likelihood under each hypothesis can be estimated.
- The analyst is willing to convert intuitive belief into explicit probability.
- The hypothesis space is well-defined enough to permit the computation (or its qualitative analog).

### Common Misapplications

- Treating Bayesian reasoning as requiring precise numerical priors and likelihoods; qualitative Bayesian thinking (state priors, weight evidence, update proportionally) is the operational core, not the arithmetic.
- Conflating prior with anchor; the Bayesian prior should reflect actual probability, not a salient initial number.
- Updating the prior with the same evidence twice (double-counting); each piece of evidence should update once.
- Ignoring P(E|¬H) — the likelihood of the evidence under the alternative — without which Bayes cannot be applied.

### Related Models

- **Base Rate Neglect** — the bias Bayesian reasoning corrects: failure to weight the prior.
- **Cromwell's Rule** — never assign 0 or 1 as priors (no evidence can update them); leave room for surprise.
- **Likelihood Ratio** — the operational core of evidence weighting in Bayes.
- **Bayesian Network** — extension to multiple interrelated hypotheses.

## Application Steps

1. State the prior belief as an explicit probability (even a rough estimate forces clarity).
2. Identify the new evidence and estimate how likely that evidence would appear if the belief were true (P(E|H)) versus if it were false (P(E|¬H)).
3. Compute the likelihood ratio (P(E|H) / P(E|¬H)); this is the strength of the evidence.
4. Update: posterior odds = prior odds × likelihood ratio; convert to probability if useful.
5. State the updated (posterior) belief explicitly; this becomes the prior for the next update.

## Detection Signals

- New information has arrived and the analyst is unsure how much to shift position.
- Two analysts viewing the same evidence reach opposite conclusions; differing priors are the likely cause.
- A diagnostic test or screening result is being interpreted without reference to the base rate.
- An extraordinary claim is being accepted on weak evidence; or an ordinary claim is being rejected against strong evidence.
- A forecast has remained constant despite multiple rounds of new information.

## Critical Questions

- Has the prior been stated explicitly, or is it implicit and therefore unaccountable?
- Has P(E|¬H) been estimated, or has the analyst computed only P(E|H) and called it Bayes? Without the alternative, there is no update.
- Is the evidence being counted multiple times across updates, inflating its impact?
- Are the prior and likelihoods independent, or are they secretly the same judgment counted twice (e.g., the prior was set by the same anecdote that constitutes the evidence)?
- Is the posterior a coherent representation of belief, or does it conflict with other beliefs the analyst holds (a sign of incoherence elsewhere)?

## Common Failure Modes

- **Likelihood-only updating** — the analyst notes that the evidence is probable under the hypothesis and updates strongly, ignoring that it may also be probable under the alternative. Detection: P(E|¬H) was not estimated. Correction: estimate the alternative's likelihood; the diagnostic strength is the ratio, not the numerator alone.
- **Evidence double-counting** — the same observation is split into multiple "pieces of evidence" and used to update multiple times. Detection: the cumulative update exceeds what a single application of the evidence would justify. Correction: enumerate evidence at the level of independent observations and update once per observation.
- **Cromwell violation** — a prior is set to 0 or 1, locking the belief against any future update. Detection: no evidence can move the analyst's position. Correction: replace 0/1 priors with very small/large probabilities (e.g., 0.001/0.999) to permit updating in the limit.
- **Anchor-as-prior** — the prior is set to a recently mentioned number rather than to the analyst's actual probability assessment. Detection: the prior tracks the anchor, not the analyst's reflective judgment. Correction: construct the prior from independent reasoning before consulting any salient number.

## Source Citations

- Bayes, Thomas (1763). "An Essay towards solving a Problem in the Doctrine of Chances." *Philosophical Transactions of the Royal Society* 53:370-418. Posthumous founding paper.
- Jaynes, E.T. (2003). *Probability Theory: The Logic of Science*. Cambridge University Press. Comprehensive Bayesian-as-extended-logic treatment.
- Gelman, Andrew et al. (2013). *Bayesian Data Analysis* (3rd ed.). Chapman and Hall. Modern computational treatment.
- Tetlock, Philip and Dan Gardner (2015). *Superforecasting*. Crown. Empirical evidence that Bayesian-style updating distinguishes top forecasters.
- Related: Base Rate Neglect; Cromwell's Rule; Likelihood Ratio.
