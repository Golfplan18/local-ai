---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Bayesian Hypothesis Network

```yaml
# 0. IDENTITY
mode_id: bayesian-hypothesis-network
canonical_name: Bayesian Hypothesis Network
suffix_rule: analysis
educational_name: Bayesian hypothesis network (probabilistic posterior over competing explanations)

# 1. TERRITORY AND POSITION
territory: T5-hypothesis-evaluation
gradation_position:
  axis: depth
  value: molecular
adjacent_modes_in_territory:
  - mode_id: differential-diagnosis
    relationship: depth-light sibling (medical-tradition triage)
  - mode_id: competing-hypotheses
    relationship: depth-thorough sibling (Heuer ACH)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want a probabilistic read on competing explanations, not just a ranked list"
    - "the hypotheses depend on each other and I need to see how priors propagate"
    - "willing to spend the time to set up priors and update with evidence properly"
    - "I want a network view, not a flat matrix"
  prompt_shape_signals:
    - "Bayesian network"
    - "posterior probability"
    - "prior and likelihood"
    - "probabilistic hypothesis"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants probability distribution over hypotheses with explicit priors and evidential updates"
    - "hypotheses are interdependent (one's truth affects another's prior)"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "want quick triage among 3-5 explanations" → differential-diagnosis
    - "want full ACH matrix without Bayesian formalism" → competing-hypotheses
    - "the disagreement is really about frame, not within-frame hypothesis weighing" → frame-comparison or worldview-cartography
when_not_to_invoke:
  - "User has no priors and no evidence-likelihood intuitions to anchor" → competing-hypotheses (qualitative ACH)
  - "Hypotheses are arguments-as-artifacts to audit" → T1 (argument-audit)

# 3. EXECUTION STRUCTURE
composition: molecular
molecular_spec:
  components:
    - mode_id: differential-diagnosis
      runs: fragment
      fragment_spec: "hypothesis-list-only — produce the candidate hypothesis set without ranking or full triage; serves as breadth seed for the Bayesian network"
    - mode_id: competing-hypotheses
      runs: full
  synthesis_stages:
    - name: prior-elicitation
      type: parallel-merge
      input: [differential-diagnosis-fragment, competing-hypotheses]
      output: "consolidated hypothesis set with elicited prior probabilities per hypothesis (and noted base-rate sources)"
    - name: bayesian-network-construction
      type: sequenced-build
      input: [prior-elicitation, competing-hypotheses]
      output: "Bayesian hypothesis network: hypotheses as nodes with priors; evidence-items as nodes with likelihoods; conditional dependencies between hypotheses named explicitly"
    - name: posterior-update
      type: dialectical-resolution
      input: [bayesian-network-construction]
      output: "posterior probability distribution over hypotheses after evidence integration; sensitivity analysis identifying which evidence items most shift the posterior"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected stage; if priors cannot be elicited with confidence, document as flat-prior assumption rather than fabricating point estimates

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [hypothesis_set, evidence_inventory, prior_estimates]
    optional: [base_rate_sources, conditional_dependency_map]
    notes: "Applies when user supplies hypotheses with prior estimates."
  accessible_mode:
    required: [phenomenon_or_question]
    optional: [evidence_observations, candidate_explanations]
    notes: "Default. Mode elicits hypotheses, evidence, and priors during execution."
  detection:
    expert_signals: ["prior probability", "likelihood", "base rate", "P(H)", "P(E|H)"]
    accessible_signals: ["competing explanations", "what's the most likely"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the phenomenon you're trying to explain, and what candidate explanations are on the table?'"
    on_underspecified: "Ask the user whether they want the full Bayesian network pass or a lighter ACH matrix (competing-hypotheses)."
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have priors been elicited from base rates or domain knowledge, or are they fabricated point estimates?"
    failure_mode_if_unmet: prior-fabrication
  - cq_id: CQ2
    question: "Have conditional dependencies among hypotheses been surfaced, or has the network treated all hypotheses as independent?"
    failure_mode_if_unmet: independence-assumption-collapse
  - cq_id: CQ3
    question: "Has sensitivity analysis identified which evidence items most shift the posterior, or does the output present a single posterior without robustness check?"
    failure_mode_if_unmet: sensitivity-omission
  - cq_id: CQ4
    question: "Are the hypotheses mutually exclusive and collectively exhaustive (or is non-MECE structure explicitly named)?"
    failure_mode_if_unmet: mece-violation-unnamed

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: prior-fabrication
    detection_signal: "Priors are stated as round numbers (0.5, 0.33) without base-rate or domain-knowledge anchor."
    correction_protocol: re-dispatch (with explicit base-rate-elicitation prompt) or flag and convert to flat-prior assumption
  - name: independence-assumption-collapse
    detection_signal: "Network has no conditional-dependency arcs even when hypotheses share underlying mechanism."
    correction_protocol: re-dispatch
  - name: sensitivity-omission
    detection_signal: "Posterior reported without indication of which evidence items dominate the update."
    correction_protocol: flag and re-dispatch
  - name: mece-violation-unnamed
    detection_signal: "Hypotheses overlap or do not exhaust the space, and this is not flagged in the output."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - heuer-ach-diagnosticity
  optional:
    - pearl-do-calculus (when network has causal interpretation)
    - tetlock-superforecasting (when long-horizon hypotheses)
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Bayesian Hypothesis Network is the heaviest mode in T5."
  sideways:
    target_mode_id: null
    when: "No within-T5 stance/complexity sibling beyond depth ladder."
  downward:
    target_mode_id: competing-hypotheses
    when: "User has time pressure or priors cannot be elicited; full ACH matrix substitutes."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Bayesian Hypothesis Network is the degree to which the prior-elicitation, network-construction, and posterior-update stages produce a probabilistic structure that no single component could have produced. A thin molecular pass extends ACH with point-estimate priors and reports a posterior; a substantive pass elicits priors from base rates, surfaces conditional dependencies among hypotheses, and runs sensitivity analysis identifying which evidence items dominate. Test depth by asking: would the analysis predict differently if a single key evidence item were removed?

## BREADTH ANALYSIS GUIDANCE

Breadth in Bayesian Hypothesis Network is the catalog of hypotheses considered before the network narrows. The differential-diagnosis fragment serves as breadth seed: enumerate widely (including unlikely-but-possible explanations) before pruning. Widen the lens to scan: dominant-narrative hypothesis; orthogonal hypothesis (different mechanism); null hypothesis (no underlying cause, observations are noise); cross-domain analogical hypothesis. Even when the network narrows to 3–5 hypotheses for the formalism, breadth is documented in the hypothesis-set section.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Bayesian Hypothesis Network is a molecular probabilistic mode that composes a differential-diagnosis hypothesis-list seed with a full competing-hypotheses (ACH) pass, then constructs an explicit network of hypothesis nodes (with priors) and evidence nodes (with likelihoods), conditional-dependency arcs, posterior-update calculation, and sensitivity analysis. It is distinct from differential-diagnosis (medical-tradition triage among 3-5 candidates, no formal posterior) and from competing-hypotheses (qualitative ACH matrix, no Bayesian formalism). The network is the load-bearing data structure; the mode produces probabilistic-but-honest output by reporting bands-with-confidence when priors and likelihoods are uncertain rather than fabricating point estimates.

**Procedure.**

1. Lock the phenomenon or question once at the head and confirm hypotheses are MECE-or-explicitly-not.
2. Enumerate hypotheses widely first — differential-diagnosis fragment seeds breadth (dominant-narrative, orthogonal-mechanism, null, cross-domain-analogical) before pruning.
3. Elicit priors per hypothesis from base rates or named domain knowledge — when no anchor exists, declare flat-prior assumption explicitly with reason rather than fabricating a round number.
4. Inventory evidence items, each with source attribution, credibility/relevance ratings, and likelihood per hypothesis (P(E|H)).
5. Surface conditional dependencies among hypotheses — each arc names the underlying mechanism creating the dependency; arcs without mechanism are not warranted. When no arcs apply, name independence explicitly as the default.
6. Compute posteriors by evidence integration — render as point estimates only when priors and likelihoods are well-anchored; otherwise render as bands with confidence intervals.
7. Run sensitivity analysis — identify which evidence items dominate the posterior; for each, name the magnitude of the shift if reversed or removed and whether leading-hypothesis ranking is stable, flips, or reorders.
8. Check MECE structure explicitly and state the result; when not MECE, name the specific overlap or gap rather than letting it pass silently.
9. Render the leading hypothesis with residual-uncertainty — name what would update the analysis.
10. Apply Knightian framing throughout — distinguish risk-quality (probabilities knowable in principle) from uncertainty-quality (probabilities as heuristic scaffolding); flag outputs that present the latter as the former.

**Goal.** Produce a Bayesian-network artifact with hypothesis-and-evidence nodes, mechanism-justified conditional-dependency arcs, posterior distribution (point or band per anchoring), and sensitivity findings identifying what could overturn the leading hypothesis.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — prior anchoring (load-bearing).** Have priors been elicited from base rates or named domain knowledge, or are they fabricated point estimates dressed up as quantitative? Failure mode if unmet: `prior-fabrication`.
- **CQ2 — conditional dependency.** Have conditional dependencies among hypotheses been surfaced with mechanism, or has the network silently treated all hypotheses as independent when they share a causal substrate? Failure mode if unmet: `independence-assumption-collapse`.
- **CQ3 — sensitivity analysis (load-bearing).** Has sensitivity analysis identified which evidence items most shift the posterior, or does the output present a single posterior without robustness check? Failure mode if unmet: `sensitivity-omission`.
- **CQ4 — MECE structure.** Are the hypotheses mutually exclusive and collectively exhaustive, or is non-MECE structure explicitly named? Failure mode if unmet: `mece-violation-unnamed`.

A passing output anchors every prior in a base rate or names a flat-prior assumption explicitly, justifies each arc with a mechanism (or declares independence), reports posteriors in the form anchoring discipline supports (point estimate vs. band-with-confidence), specifies sensitivity-dominant evidence with the magnitude of the resulting shift, and states MECE structure explicitly rather than assuming it.

**Named failure modes.**

- *prior-fabrication* — priors stated as round numbers (0.5, 0.33) without base-rate or domain-knowledge anchor.
- *independence-assumption-collapse* — network has no conditional-dependency arcs even when hypotheses share underlying mechanism.
- *sensitivity-omission* — posterior reported without indication of which evidence items dominate the update.
- *mece-violation-unnamed* — hypotheses overlap or do not exhaust the space, and this is not flagged in the output.

## REVISION GUIDANCE

Revise to anchor priors more rigorously where they appear fabricated. Revise to add conditional-dependency arcs where hypotheses share mechanism. Revise to add sensitivity analysis where the posterior is reported without robustness check. Resist revising toward false precision — when priors and likelihoods are genuinely uncertain, the output should report posterior as a distribution-with-confidence rather than a single number.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Bayesian network of hypothesis nodes and evidence nodes with conditional-dependency arcs**, plus posterior, sensitivity, and MECE atoms. The graph is the load-bearing data structure; everything else attaches to or derives from nodes and arcs. The atoms are:

1. **Phenomenon-or-question atom.** The phenomenon being explained or the question being adjudicated, stated once at the corpus head. Cross-stream paraphrase collapses to one canonical statement.

2. **Hypothesis-node atoms.** Each node carries: hypothesis statement, prior probability, base-rate or domain-knowledge anchor for the prior (or explicit "flat-prior assumption" tag when anchor unavailable), and component provenance (differential-diagnosis fragment / competing-hypotheses / both). Round-number priors (0.5, 0.33) without anchor are prior-fabrication and do not survive — either an anchor is found, or the prior is replaced with explicit flat-prior assumption.

3. **Evidence-node atoms.** Each node carries: evidence content, likelihood per hypothesis (P(E|H)), source attribution, and credibility/relevance ratings. Likelihoods that diverge between streams collapse to one value under audit conservatism when both anchored to the same source; preserved as tension when streams cite different sources.

4. **Conditional-dependency arc atoms.** Each arc carries: source hypothesis node, target hypothesis node, dependency direction, and the underlying mechanism that creates the dependency. Arcs whose mechanism cannot be named are independence-assumption-collapse residue (the consolidator inventing structure not in the source streams); these do not survive. Independence is named explicitly as a default assumption atom when no arcs are warranted.

5. **Posterior-distribution atoms.** Posterior probability per hypothesis after evidence integration. When priors and likelihoods are genuinely uncertain, the posterior atom carries a distribution-with-confidence-interval rather than a single point estimate — false precision is a named-by-revision-guidance pitfall, and a single-number posterior over uncertain inputs is its corpus signature.

6. **Sensitivity atoms.** Each names an evidence item whose removal or reversal would substantially shift the posterior, with the magnitude of the shift. At minimum one sensitivity atom is named or CQ3 fails. When the streams disagree on which evidence item dominates, preserve both as parallel sensitivity atoms.

7. **MECE-check atom.** A single atom flags whether the hypothesis set is mutually exclusive and collectively exhaustive, or names the specific overlap / gap if not. MECE violations that go unnamed are the mece-violation-unnamed failure mode; the corpus carries the check explicitly even when MECE is intact.

8. **Leading-hypothesis-with-residual-uncertainty atom.** The hypothesis with highest posterior probability, with explicit residual-uncertainty atom naming what would update the analysis. Single-leader output without residual-uncertainty atom is false-confidence bloat.

9. **Confidence map.** Confidence markers attach to individual atoms (priors, likelihoods, posterior). When the two streams assigned different confidences to the same atom, audit conservatism applies (the lower confidence survives).

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Hypothesis-statement paraphrase** — same hypothesis under different wordings across streams. Single canonical statement survives; both streams' prior estimates collapse with the more rigorously anchored one winning.
- **Prior-restatement loops** — same prior expressed in different framings ("about 1 in 5" vs "20%" vs "roughly a fifth"). One precise prior atom survives with the strongest anchor.
- **Likelihood-paraphrase** — same P(E|H) stated under different wordings. Single likelihood atom per (E, H) pair survives.
- **Round-number priors without anchor** — priors like 0.5 or 0.33 stated without base-rate or domain-knowledge anchor are prior-fabrication residue. Either both streams agree the prior is genuinely flat (in which case "flat-prior assumption" tag survives) or the round number does not survive into the corpus.
- **Posterior-restatement** — both streams may state the posterior in different forms (probability / odds / log-odds; point estimate / range). One canonical posterior atom survives with explicit form.
- **Sensitivity-finding overlap** — both streams may identify the same evidence-reversal as posterior-shifting. One sensitivity atom per such finding.
- **Independence-default-restatement** — when neither stream identifies conditional dependencies, the corpus carries one explicit "all hypotheses treated as independent — no arcs warranted in this case" atom rather than multiple restatements that the network has no arcs.

**What NOT to collapse:**

- **Conditional-dependency arc disagreement** — when one stream surfaced a dependency arc and the other did not, preserve as a tension atom. The presence-or-absence of an arc materially changes the posterior; the consolidator must not silently include or exclude it.
- **Prior-anchoring divergence** — when streams anchored the same hypothesis's prior in different base-rate sources, preserve both anchors as a multi-source-prior atom. The posterior changes based on which anchor governs; the disagreement is a finding about the analysis's robustness to base-rate selection.
- **MECE-assessment disagreement** — when one stream judged the hypothesis set MECE and the other identified a gap or overlap, preserve the disagreement explicitly. MECE is consequential for posterior interpretation; silent reconciliation is mece-violation-unnamed residue.

## VERIFICATION CRITERIA

Verified means: every component ran (or was flagged as proceeded-with-gap); priors are anchored or flat-prior assumption is explicit; conditional dependencies are surfaced or independence is named; sensitivity analysis identifies dominant evidence; MECE structure is checked. The four critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **Bayesian-network artifact with hypothesis-and-evidence nodes, conditional-dependency arcs, posterior distribution, and sensitivity findings**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Phenomenon or question.** The phenomenon being explained or the question being adjudicated, stated once at the top.

2. **Hypothesis nodes with priors.** Numbered list of canonical H1, H2, … Each hypothesis carries: one-line statement, prior probability (P(H) = ...), base-rate or domain-knowledge anchor (or explicit `flat-prior assumption: [reason]` when anchor unavailable), and component provenance (differential-diagnosis fragment / competing-hypotheses / both). Round-number priors without anchor do not appear in the deliverable.

3. **Evidence nodes with likelihoods.** Numbered list of canonical E1, E2, … Each evidence node carries: one-line content statement, source attribution, credibility / relevance ratings, and likelihood per hypothesis (P(E|H1) = ..., P(E|H2) = ..., …).

4. **Conditional dependencies.** Numbered list of arcs (when arcs exist). Each arc: `[Source hypothesis → Target hypothesis]: mechanism: [the underlying mechanism creating the dependency].` When no arcs are warranted, render: "Independence assumed: no conditional dependencies between hypotheses are identifiable from the available evidence and domain knowledge."

5. **Bayesian network — diagram or table.** Render the network as one of the following based on complexity:
   - **Table format** (when ≤4 hypotheses and ≤6 evidence items): rows = evidence, columns = hypotheses, cells = likelihoods.
   - **Diagram-friendly description** (when complexity exceeds table-readability): node-and-arc enumeration with explicit edge directionality. Example: `H1 (P=0.3) → E1 (P(E1|H1)=0.8); H2 (P=0.5) → E1 (P(E1|H2)=0.2); ...`
   - **Annotated table-plus-narrative** when the network combines both forms cleanly.

   Always state which form was chosen and why: `Rendering as [table / node-arc description / annotated-table-plus-narrative]: [reason — complexity / clarity / etc.].`

6. **Posterior distribution.** Per hypothesis: P(H|E) after evidence integration. When priors and likelihoods are uncertain, render as a band with confidence interval: `P(H1|E) ∈ [low, high] with [confidence]`. When point estimates are honest (well-anchored priors and likelihoods), render as: `P(H1|E) = [value]`. Order hypotheses by descending posterior.

7. **Sensitivity analysis.** Bulleted list of evidence items whose removal or reversal would substantially shift the posterior, with the magnitude of the shift. Each bullet: `E_n: if reversed, P(H_x|E) shifts from [before] to [after]; ranking [stable / flips / reorders].` At minimum one sensitivity finding.

8. **MECE check.** One sentence: "Hypothesis set is MECE: [yes / no]." When not MECE, name the specific overlap or gap: "Overlap: H1 and H2 share [aspect]." or "Gap: the set does not exhaust [outcome class]." MECE violations that are unnamed are the corpus-flagged failure mode.

9. **Leading hypothesis with residual uncertainty.** Short prose: the hypothesis with highest posterior probability, with explicit residual-uncertainty atom naming what would update the analysis. Frame as: "Leading: H_x (P = [value]). What would update this: [specific evidence or reversal]."

10. **Confidence map.** Bulleted list of confidence markers attached to priors, likelihoods, and posterior. Each bullet: `[atom] confidence: [high / moderate / low] — [reason].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 10.
- Probability values rendered with consistent form (decimals for point estimates; intervals for bands; never mix forms in the same section).
- Hypothesis and evidence IDs referenced consistently throughout once introduced.
- When the rendering form for section 5 is annotated-table-plus-narrative, the table goes first and the narrative supplements it.
- Conditional dependencies render with explicit edge direction (`→`) and a mechanism-per-edge — arcs without mechanisms do not appear.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~10+min
- **Context Budget:** extended

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- Challenge
- CAF
- FIP
- AGO

Mental models (always loaded):
- bayesian-reasoning
- base-rate-neglect
- confirmation-bias
- falsifiability
- occams-razor
- tetlock-superforecasting

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `contradicts`, `qualifies`, `produces`, `precedes`
**Deprioritize:** `parent`, `analogous-to`

*Family: hypothesis-future. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
