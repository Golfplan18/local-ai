
# Framework — Hypothesis Evaluation

*Self-contained framework for taking multiple competing explanations and a body of evidence and adjudicating among them using diagnosticity, base rates, and Bayesian or quasi-Bayesian reasoning. Compiled 2026-05-01 from territory entry, member mode specs, lens dependencies, and open debates.*

---

## Territory Header

- **Territory ID:** T5
- **Name:** Hypothesis Evaluation
- **Super-cluster:** B (Causation, Hypothesis, and Mechanism)
- **Characterization:** Operations that take multiple competing explanations and a body of evidence and adjudicate among them using diagnosticity, base rates, and Bayesian or quasi-Bayesian reasoning.
- **Boundary conditions:** Input is two-or-more competing hypotheses plus evidence. Excludes single-hypothesis testing and excludes within-paradigm-debate cases that are really about frame (T9).
- **Primary axis:** Depth (light differential-diagnosis → full Heuer ACH → Bayesian network molecular).
- **Secondary axes:** Specificity (general ACH vs. forensic vs. scientific-hypothesis variants).

## When to use this framework

Use when there are multiple plausible explanations of a body of evidence and the question is which fits best. Plain-language triggers:

- "I have a few candidate explanations and need a quick weigh-in."
- "What are the main possibilities and which is most likely?"
- "Multiple plausible explanations for the same evidence."
- "I have a favoured theory but want it stress-tested."
- "The evidence is ambiguous or contradictory."
- "Which explanation fits best?"
- "I want a probabilistic read on competing explanations."
- "The hypotheses depend on each other and I need to see how priors propagate."

Do not route here when there is only one hypothesis on the table (T1 or T4 single-hypothesis modes); when the disagreement is really about frame rather than within-frame hypothesis weighing (T9 — paradigm modes); when the hypotheses are themselves complete arguments needing soundness audit (T1); when the question is about choosing between action alternatives rather than explanations (T3).

## Within-territory disambiguation

```
Q1 (depth): "Quick read on which explanation fits best,
             or do you want me to lay out evidence systematically against each candidate,
             or do you want a probabilistic model with priors?"
  ├─ "quick" → differential-diagnosis (Tier-1)
  ├─ "systematic" → competing-hypotheses (Tier-2, Heuer ACH)
  ├─ "probabilistic model with priors" → bayesian-hypothesis-network (Tier-3)
  └─ ambiguous → competing-hypotheses (the Tier-2 default)
```

**Default route.** `competing-hypotheses` at Tier-2 when ambiguous (the canonical Heuer ACH operation; both the quick differential and the formal Bayesian network are siblings of this baseline).

**Escalation hooks.**
- After `differential-diagnosis`: if more than two hypotheses survive the quick read, hook upward to `competing-hypotheses` ("Quick read complete — there's more here than one mode can disentangle, want the longer route?").
- After `competing-hypotheses`: if priors materially shift the diagnosis, hook upward to `bayesian-hypothesis-network`.
- After any T5 mode: if the disagreement is really about how to frame the issue rather than which hypothesis fits the evidence, hook sideways to T9 (`paradigm-suspension` or `frame-comparison`).
- After any T5 mode: if each hypothesis is itself a complete argument-as-artifact, hook sideways to T1 (audit each).

## Mode entries

### Mode — differential-diagnosis

- **Educational name:** light differential diagnosis (medical-tradition lighter sibling of ACH)
- **Plain-language description:** A quick weigh-in among 2–5 candidate explanations. The mode lists candidate hypotheses with one-line characterizations, lists evidence observed and tags it with which hypotheses it bears on, assesses diagnosticity (rules out / consistent with / discriminating between) for the top two, and identifies one disconfirming test per top candidate so the user can act to narrow further. Rare-but-serious "zebra" candidates are deliberately included so common-case explanations don't eclipse them.

- **Critical questions:**
  1. Are the candidate hypotheses genuinely different explanations of the evidence, or are some of them re-descriptions of the same underlying explanation?
  2. Does the diagnosticity assessment distinguish evidence that *rules out* hypotheses from evidence that is merely *consistent with* them, given that consistent evidence is weak diagnostic?
  3. Has the analysis identified at least one disconfirming test for each of the top two candidates, so the user can act to narrow further?
  4. Has the analysis flagged when the evidence base is too small for a confident ranking, rather than producing a ranking it cannot support?

- **Per-pipeline-stage guidance:**
  - **Depth.** Distinguish consistency from diagnosticity ("rules out H2" beats "consistent with H1"); name disconfirming tests; surface rare-but-serious "zebra" candidates.
  - **Breadth.** Deliberate inclusion of rare-but-serious candidates, candidates from adjacent domains, candidates that combine mechanisms (H1 *and* H3 together), and the null hypothesis (the situation is benign and self-resolving). Document candidates considered and rejected with one-line reasons.
  - **Evaluation.** Four critical questions plus failure modes (hypothesis-collapse, confirmation-anchoring, no-actionable-disconfirmer, false-confidence, missing-zebra).
  - **Consolidation.** Six required sections: candidate hypotheses listed; evidence observed; diagnosticity per hypothesis; ranking with reasoning; one disconfirming test per top two; confidence per ranking.
  - **Verification.** ≥2 distinct candidates; diagnosticity in disconfirming-power language for top two; ≥1 disconfirming test per top candidate; confidence honest about evidence sparseness; rare-but-serious candidates considered.

- **Source tradition:** Medical differential-diagnosis tradition (Sackett 1991 *Clinical Epidemiology*); medical zebra-rule (rare-but-serious always in the differential); Heuer ACH (lighter sibling).

- **Lens dependencies:**
  - `differential-diagnosis-schema`: Schema for organizing candidate explanations by diagnosticity rather than surface plausibility; emphasis on disconfirming tests and zebra candidates.
  - Optional: `heuer-ach` (when escalating); `bayesian-base-rate` (when prior probabilities are available).

### Mode — competing-hypotheses

- **Educational name:** analysis of competing hypotheses (ACH, Heuer-style)
- **Plain-language description:** A thorough Heuer-style ACH analysis. The mode generates ≥3 hypotheses (including ≥1 analyst-generated alternative beyond the user's set, plus a null/"something else" hypothesis), inventories ≥3 evidence items with credibility/relevance ratings, populates the evidence-by-hypothesis matrix using Heuer vocabulary (CC = strongly consistent, C = consistent, N = neutral, I = inconsistent, II = strongly inconsistent, NA = not applicable), works *across* the matrix (one piece of evidence evaluated against all hypotheses) rather than *down* it (collecting evidence for the favoured), names the surviving hypothesis as the one with fewest I+II cells (tie-broken by II count), runs sensitivity analysis on the most diagnostic evidence, and lists monitoring priorities. Where adversarial actors are plausible, assesses whether high-diagnosticity evidence could be manufactured.

- **Critical questions:**
  1. Has at least one hypothesis beyond the user's initial set been generated, or is the matrix limited to user-proposed explanations?
  2. Has each evidence item been assessed across all hypotheses (across-the-matrix), or only against the favoured one (down-the-matrix)?
  3. Is the conclusion framed as elimination of least-consistent hypotheses, or as confirmation of the favoured one?
  4. Has at least one piece of evidence been identified as high-diagnosticity, distinguishing sharply between hypotheses?
  5. If adversarial actors are plausible, has the analysis assessed whether high-diagnosticity evidence could be manufactured?

- **Per-pipeline-stage guidance:**
  - **Depth.** Working *across* the evidence-hypothesis matrix; full population with cell justification; diagnosticity assessment per evidence item; conclusion via elimination of least-consistent.
  - **Breadth.** Generate widest plausible hypothesis set including unconventional explanations and a null/"something else" hypothesis; identify what would *disconfirm* each hypothesis; identify the missing-evidence question (what single piece of information would most change the analysis); scan deception risk where applicable.
  - **Evaluation.** Five critical questions plus failure modes (missing-hypothesis, confirmation-framing, false-rigour, deception-blindness, wrong-tally, static-snapshot).
  - **Revision.** Fill missing cells (use NA explicitly when evidence does not bear); convert custom vocabulary to Heuer vocabulary; add hypotheses; convert confirmation framing to elimination framing; recount cell tallies if prose contradicts arithmetic. Resist revising toward the user's favoured hypothesis if matrix doesn't support it.
  - **Consolidation.** Seven required sections in matrix form: hypothesis list (stable IDs H1, H2 …); evidence inventory (stable IDs E1, E2 …); consistency matrix; diagnosticity assessment; tentative conclusions via elimination; sensitivity analysis; monitoring priorities. The matrix is the load-bearing structure; rows = evidence, columns = hypotheses, cells = Heuer vocabulary.
  - **Verification.** ≥3 hypotheses including ≥1 analyst-generated; ≥3 evidence items with credibility/relevance; every cell populated with Heuer vocabulary; ≥1 diagnostic row; surviving hypothesis named matches fewest I+II count; ≥1 high-diagnosticity item named; sensitivity analysis names ≥1 evidence item whose reversal would change ranking; deception check addressed when applicable; monitoring priorities listed.

- **Source tradition:** Heuer, Richards J. *Psychology of Intelligence Analysis* (1999); Heuer, Richards J., and Randolph H. Pherson *Structured Analytic Techniques for Intelligence Analysis* (2010); Popper *Logic of Scientific Discovery* (1959) for the falsifiability commitment underlying disconfirmation focus.

- **Lens dependencies:**
  - `heuer-ach-methodology`: Eight-step Analysis of Competing Hypotheses procedure — (1) identify hypotheses including unconventional and null; (2) make a list of significant evidence and arguments for and against each hypothesis; (3) prepare a matrix with hypotheses across the top and evidence down the side; (4) refine the matrix; (5) draw tentative conclusions about the relative likelihood of each hypothesis; (6) analyze how sensitive the conclusion is to a few critical items of evidence; (7) report conclusions with discussion of relative likelihood of all hypotheses; (8) identify milestones for future observation that may indicate events are taking a different course than expected. Cell vocabulary: CC, C, N, I, II, NA. Counting rule: surviving hypothesis = fewest I+II cells (tie-broken by II).
  - Optional: `bayesian-base-rate-reasoning`; `counter-deception-frameworks`; `falsifiability-popper`. Foundational: `kahneman-tversky-bias-catalog`; `knightian-risk-uncertainty-ambiguity`.

### Mode — bayesian-hypothesis-network

- **Educational name:** Bayesian hypothesis network (probabilistic posterior over competing explanations)
- **Plain-language description:** A molecular composition that builds an explicit Bayesian network with hypotheses as nodes carrying priors, evidence-items as nodes with likelihoods, and conditional dependencies between hypotheses named explicitly. Runs differential-diagnosis (fragment: hypothesis-list-only as breadth seed) plus competing-hypotheses (full). Synthesizes via three stages: prior-elicitation → bayesian-network-construction → posterior-update. Output: posterior probability distribution over hypotheses after evidence integration; sensitivity analysis identifying which evidence items most shift the posterior. When priors cannot be elicited with confidence, documents as flat-prior assumption rather than fabricating point estimates.

- **Critical questions:**
  1. Are the hypotheses mutually exclusive and collectively exhaustive (or is the residual "something else" hypothesis present)?
  2. Are the priors elicited from defensible base-rate sources (or from qualitative bands), or are they fabricated point estimates?
  3. Are the conditional dependencies between hypotheses named explicitly, or has the network treated hypotheses as independent when they aren't?
  4. Does the sensitivity analysis identify which evidence items most shift the posterior, so the user knows which evidence is doing the heavy lifting?

- **Per-pipeline-stage guidance:**
  - **Composition.** Molecular: differential-diagnosis fragment (breadth seed) + full competing-hypotheses; three synthesis stages.
  - **Breadth.** Hypothesis set seeded by differential-diagnosis fragment to ensure unconventional alternatives and zebra candidates appear; document priors with base-rate sources where possible.
  - **Consolidation.** Synthesis output: Bayesian network (hypothesis nodes with priors, evidence nodes with likelihoods, conditional-dependency arrows); posterior distribution; sensitivity ranking of evidence items by posterior-shift magnitude.
  - **Verification.** Hypothesis set seeded from differential-diagnosis; priors elicited with sources or noted as flat-prior assumption; conditional dependencies named; posterior computed and reported; sensitivity analysis ranks evidence by posterior-shift magnitude.

- **Source tradition:** Pearl *Probabilistic Reasoning in Intelligent Systems* (1988); Jensen & Nielsen *Bayesian Networks and Decision Graphs* (2007); Tetlock *Superforecasting* (2015) for the probability-calibration tradition.

- **Lens dependencies:**
  - `bayesian-reasoning`: Bayes' theorem P(H|E) = P(E|H) × P(H) / P(E); prior, likelihood, posterior; updating across multiple evidence items via product of likelihood ratios.
  - Inherits from `heuer-ach-methodology` and `differential-diagnosis-schema` via component composition.

- **For molecular modes:** Composition specified above. Paired execution framework: this framework supplies the synthesis-stage scaffolding directly.

## Cross-territory adjacencies

**T5 ↔ T9 (Paradigm Examination).** "Are you weighing competing explanations within a shared understanding of the problem, or are the explanations using such different frames that the disagreement is really about how to see the issue?" Within-frame hypothesis comparison → T5; inter-frame disagreement → T9. Example: "Doctor A says it's X, doctor B says it's Y — same evidence" → T5; "Doctor A and the homeopath disagree — different paradigms entirely" → T9.

**T5 ↔ T1 (Argumentative Artifact).** "Are the competing hypotheses each a complete argument-as-artifact (audit each), or are they propositions to weigh against evidence (ACH-style)?" Argument-as-artifact → T1 (Argument Audit on each); proposition-against-evidence → T5.

**T5 ↔ T4 (Causal Investigation).** When competing hypotheses are causal hypotheses about a single historical event, route to T4 `process-tracing` (which uses Bennett-Checkel evidence-tests as its diagnosticity apparatus).

## Lens references

### differential-diagnosis-schema

**Core insight.** When 2–5 candidate explanations are on the table and time is limited, organize the analysis around diagnosticity (what would distinguish them) rather than surface plausibility (which sounds most likely).

**Application steps.**
1. List candidate hypotheses with one-line characterizations.
2. List evidence observed and tag each piece with the hypotheses it bears on.
3. For the top two by surface plausibility, assess diagnosticity: does this evidence *rule out* the hypothesis, is it merely *consistent with* it, or does it *discriminate sharply between* this and competing hypotheses.
4. Name one disconfirming test per top candidate — what observation, if made, would eliminate this hypothesis.
5. Include rare-but-serious "zebra" candidates deliberately. Common-case explanations otherwise eclipse low-base-rate but high-cost diagnoses.
6. Honest confidence: when evidence is too sparse for a confident ranking, say so rather than producing a ranking the evidence cannot support.

**Common misapplications.** Treating "consistent with H1" as confirmation of H1 (consistency is weak diagnostic); ranking only by surface plausibility without disconfirming-power assessment; missing the zebra; producing a confident ranking from sparse evidence (false confidence).

### heuer-ach-methodology

**Core insight.** When multiple hypotheses are on the table and a body of evidence must be adjudicated, the human tendency is to work *down* the matrix — collect evidence for the favoured hypothesis, accumulate confirmations, and ignore evidence that doesn't fit. Heuer's reversal: work *across* the matrix — for each evidence item, ask what it implies for *every* hypothesis. Conclude by elimination of least-consistent hypotheses, not by confirmation of the favoured one.

**Eight-step procedure.**
1. *Identify hypotheses.* Generate a comprehensive set including unconventional explanations and a null/"something else" hypothesis. At least one analyst-generated alternative beyond the user's initial set.
2. *List significant evidence and arguments.* Evidence-items, contextual arguments, indicators, observations — anything that bears on the hypotheses.
3. *Prepare the matrix.* Hypotheses across the top, evidence down the side. Cells use Heuer vocabulary: CC = strongly consistent, C = consistent, N = neutral, I = inconsistent, II = strongly inconsistent, NA = not applicable.
4. *Refine the matrix.* Reconsider each cell; check that the cell reflects what the evidence actually implies for the hypothesis (not what the analyst believes about the hypothesis overall).
5. *Draw tentative conclusions about relative likelihood.* The surviving hypothesis is the one with the fewest I+II cells (tie-broken by II count). The conclusion is *elimination of least-consistent*, not *confirmation of favoured*.
6. *Analyze sensitivity.* Identify the few critical evidence items most affecting the conclusion. What if they were wrong? Could they have been manufactured (deception)?
7. *Report conclusions.* Discuss relative likelihood of *all* hypotheses, not just the leader. Note residual uncertainty.
8. *Identify milestones for future observation.* What developments would suggest the conclusion needs revision?

**Cell vocabulary discipline.** CC, C, N, I, II, NA. Custom vocabulary ("supports", "refutes", "weakly indicates") is to be converted to Heuer vocabulary. NA is explicit (use it when evidence does not bear on a hypothesis); never leave cells blank.

**Counting rule.** Surviving hypothesis = fewest I+II cells. Tie-breaker: fewer II cells. The arithmetic must match the prose verdict; if it doesn't, recount or revise the prose.

### bayesian-reasoning

**Core insight.** Bayes' theorem provides the formal updating rule for moving from prior probability P(H) (degree of belief in hypothesis H before evidence E is observed) to posterior probability P(H|E) (degree of belief in H after E).

**Bayes' theorem.** P(H|E) = P(E|H) × P(H) / P(E)

Where:
- P(H|E) = posterior — probability of H given E.
- P(E|H) = likelihood — probability of E given H.
- P(H) = prior — probability of H before E.
- P(E) = marginal probability of E = Σ_i P(E|H_i) × P(H_i) over all hypotheses H_i.

**Likelihood ratio form.** For two competing hypotheses H1 and H2: P(H1|E) / P(H2|E) = [P(E|H1) / P(E|H2)] × [P(H1) / P(H2)]. The likelihood ratio P(E|H1) / P(E|H2) is the diagnostic strength of evidence E for distinguishing H1 from H2.

**Sequential updating.** When multiple evidence items E1, E2, ... arrive, the posterior after each becomes the prior for the next. If evidence items are conditionally independent given the hypothesis, the updates multiply.

**Common misapplications.** Base-rate neglect (ignoring P(H) and updating from likelihoods alone); confusing P(H|E) with P(E|H) (the prosecutor's fallacy); fabricating point priors when only qualitative bands are defensible; treating dependent evidence as independent (overcounting evidence).

## Open debates

T5 modes carry no architecture-level debates that bear on territory operation. The choice of probability interpretation (frequentist vs. Bayesian vs. decision-theoretic) is handled within the lens framework rather than as a territory-level debate; the disposition is operationally Bayesian (subjective probabilities updated by evidence) for the `bayesian-hypothesis-network` mode, while `competing-hypotheses` and `differential-diagnosis` operate quasi-Bayesian without committing to a formal probability calculus.

## Citations and source-tradition attributions

**Intelligence analysis tradition.**
- Heuer, Richards J. (1999). *Psychology of Intelligence Analysis*. Center for the Study of Intelligence, CIA.
- Heuer, Richards J., and Randolph H. Pherson (2010). *Structured Analytic Techniques for Intelligence Analysis*. CQ Press.

**Medical differential diagnosis.**
- Sackett, David L., R. Brian Haynes, Gordon H. Guyatt, and Peter Tugwell (1991). *Clinical Epidemiology: A Basic Science for Clinical Medicine* (2nd ed.). Little, Brown.

**Bayesian reasoning.**
- Pearl, Judea (1988). *Probabilistic Reasoning in Intelligent Systems*. Morgan Kaufmann.
- Jensen, Finn V., and Thomas D. Nielsen (2007). *Bayesian Networks and Decision Graphs* (2nd ed.). Springer.
- Lindley, Dennis V. (2014). *Understanding Uncertainty* (rev. ed.). Wiley.

**Forecasting and probability calibration.**
- Tetlock, Philip E., and Dan Gardner (2015). *Superforecasting: The Art and Science of Prediction*. Crown.

**Falsifiability.**
- Popper, Karl R. (1959). *The Logic of Scientific Discovery*. Hutchinson.

*End of Framework — Hypothesis Evaluation.*
