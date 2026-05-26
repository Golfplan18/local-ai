---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-24

---

# MODE: Competing Hypotheses

```yaml
# 0. IDENTITY
mode_id: competing-hypotheses
canonical_name: Competing Hypotheses
suffix_rule: analysis
educational_name: analysis of competing hypotheses (ACH, Heuer-style)

# 1. TERRITORY AND POSITION
territory: T5-hypothesis-evaluation
gradation_position:
  axis: depth
  value: thorough
adjacent_modes_in_territory:
  - mode_id: differential-diagnosis
    relationship: depth-lighter sibling
  - mode_id: bayesian-hypothesis-network
    relationship: depth-molecular sibling

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "multiple plausible explanations for the same evidence"
    - "I have a favoured theory but want it stress-tested"
    - "the evidence is ambiguous or contradictory"
    - "what is actually happening here"
    - "there might be deception or information manipulation"
  prompt_shape_signals:
    - "which explanation fits best"
    - "make me an ACH matrix"
    - "what rules out X"
    - "how would we know if we're wrong"
    - "what's the strongest evidence against each theory"
    - "competing hypotheses"
disambiguation_routing:
  routes_to_this_mode_when:
    - "two or more hypotheses on the table plus a body of evidence to weigh against them"
    - "want diagnosticity-driven adjudication, not interest analysis"
    - "the question is what is true, not what to do"
  routes_away_when:
    - "choosing between action alternatives, not explanations" → decision-under-uncertainty
    - "questioning the foundational framework rather than testing within it" → paradigm-suspension
    - "tracing institutional interests behind competing claims" → cui-bono
    - "only one plausible explanation, want to strengthen it" → steelman-construction
    - "competing hypotheses are themselves whole arguments to audit" → T1
when_not_to_invoke:
  - "User has only one explanation in play; ACH requires at least two competing hypotheses" → steelman-construction or differential-diagnosis
  - "User wants a quick-read differential without full matrix construction" → differential-diagnosis (lighter T5 sibling)
  - "Hypothesis disagreement is really inter-frame disagreement using different paradigms" → T9 paradigm modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: neutral

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [hypothesis_set, evidence_inventory]
    optional: [diagnosticity_priors, deception_context, scoring_method_preference]
    notes: "Applies when user supplies explicit hypotheses (H1, H2 …) and/or an evidence inventory with credibility/relevance ratings."
  accessible_mode:
    required: [situation_with_multiple_explanations]
    optional: [user_favoured_hypothesis, evidence_so_far]
    notes: "Default. Mode generates additional hypotheses, structures evidence, and constructs the matrix."
  detection:
    expert_signals: ["ACH matrix", "Heuer", "diagnosticity", "hypothesis H1, H2", "evidence E1"]
    accessible_signals: ["which explanation", "competing theories", "what's most likely happening", "stress-test my theory"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe the situation, the explanations on the table, and the evidence you've seen so far?'"
    on_underspecified: "Ask: 'What are the competing explanations you'd like me to weigh against each other, and what evidence have you encountered?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has at least one hypothesis beyond the user's initial set been generated, or is the matrix limited to user-proposed explanations?"
    failure_mode_if_unmet: missing-hypothesis
  - cq_id: CQ2
    question: "Has each evidence item been assessed across all hypotheses (across-the-matrix), or only against the favoured one (down-the-matrix)?"
    failure_mode_if_unmet: confirmation-framing
  - cq_id: CQ3
    question: "Is the conclusion framed as elimination of least-consistent hypotheses, or as confirmation of the favoured one?"
    failure_mode_if_unmet: confirmation-framing
  - cq_id: CQ4
    question: "Has at least one piece of evidence been identified as high-diagnosticity, distinguishing sharply between hypotheses?"
    failure_mode_if_unmet: false-rigour
  - cq_id: CQ5
    question: "If adversarial actors are plausible, has the analysis assessed whether high-diagnosticity evidence could be manufactured?"
    failure_mode_if_unmet: deception-blindness

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: missing-hypothesis
    detection_signal: "All hypotheses are user-proposed; no analyst-generated alternative or null/'something else' hypothesis."
    correction_protocol: re-dispatch
  - name: confirmation-framing
    detection_signal: "Conclusion phrased as 'H_x is supported by E1, E3' rather than 'H_x survives because fewer items contradict it'; or evidence assessed only against the favoured hypothesis."
    correction_protocol: re-dispatch
  - name: false-rigour
    detection_signal: "Matrix format used but consistency ratings are uniform across rows or unjustified; all rows non-diagnostic."
    correction_protocol: flag
  - name: deception-blindness
    detection_signal: "Adversarial context plausible but no assessment of whether high-diagnosticity evidence could be planted or manufactured."
    correction_protocol: flag
  - name: wrong-tally
    detection_signal: "Endorsed surviving hypothesis has more inconsistent (I + II) cells than an alternative; conclusion contradicts cell count."
    correction_protocol: re-dispatch
  - name: static-snapshot
    detection_signal: "No monitoring priorities or leading indicators stated; analysis treated as final in evolving situation."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - heuer-ach-methodology
  optional:
    - bayesian-base-rate-reasoning
    - counter-deception-frameworks
    - falsifiability-popper
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: bayesian-hypothesis-network
    when: "Hypothesis dependencies form a network with non-trivial conditional structure; quasi-Bayesian tally insufficient."
  sideways:
    target_mode_id: differential-diagnosis
    when: "Time-pressed user wants light-weight ranking without full matrix construction."
  downward:
    target_mode_id: differential-diagnosis
    when: "User wants quick differential rather than thorough ACH; complexity does not warrant full matrix."
```

## DEPTH ANALYSIS GUIDANCE

Going deeper in Competing Hypotheses means working **across** the evidence-hypothesis matrix (one piece of evidence evaluated against all hypotheses) rather than **down** it (collecting evidence for a favoured hypothesis). Depth shows itself in disconfirmation rigor: the matrix is fully populated, every cell is justified, the diagnosticity of each evidence item is assessed, and the conclusion follows from elimination of least-consistent hypotheses rather than confirmation of the favoured one. A thin pass tallies confirmations; a substantive pass identifies the rows whose values vary sharply (high-diagnosticity), names what would falsify each surviving hypothesis, and conducts sensitivity analysis on the most diagnostic evidence.

## BREADTH ANALYSIS GUIDANCE

Widening the lens means generating the widest plausible hypothesis set — at minimum one beyond the user's initial proposals, including unconventional explanations and a null/"something else" hypothesis. Identify what evidence would **disconfirm** each hypothesis, since disconfirmation is more diagnostic than confirmation. Identify the missing-evidence question: what single piece of information would most change the analysis? Where adversarial actors are plausible, scan for whether high-diagnosticity evidence could be manufactured. Breadth markers: at least one hypothesis is explicitly flagged as analyst-generated, sensitivity analysis names at least one evidence item whose reversal would change the ranking, and leading indicators are identified for each surviving hypothesis.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Competing Hypotheses applies Heuer's Analysis of Competing Hypotheses (ACH) — a hypothesis-by-evidence matrix evaluated **across** rather than down, with consistency ratings (CC, C, N, I, II, NA) per cell, diagnosticity assessment per evidence row, and elimination arithmetic naming the surviving hypothesis as the one with fewest inconsistent cells. It is distinct from differential-diagnosis (lighter triage among 3-5 candidates, no full matrix) and from bayesian-hypothesis-network (full molecular pass with priors, likelihoods, posterior, conditional-dependency arcs). Its discipline is disconfirmation rigor — the methodology's value emerges when the user's favoured hypothesis loses.

**Procedure.**

1. Enumerate hypotheses widely — at least three, including ≥1 analyst-generated beyond the user's initial set; add a null / "something else" hypothesis when applicable.
2. Inventory evidence items — each with credibility, relevance, source attribution.
3. Populate the matrix across — for each evidence row, rate every hypothesis cell with Heuer vocabulary (CC, C, N, I, II, NA). NA is explicit; never leave cells absent.
4. Assess diagnosticity per evidence row — high-diagnosticity rows discriminate sharply; low-diagnosticity rows are uniform. At minimum one high-diagnosticity item must be named.
5. Compute elimination arithmetic — I+II count per hypothesis, II as tie-breaker. The surviving hypothesis is the one with fewest I+II cells.
6. Frame the verdict in elimination language — "H_x survives because fewer items contradict it" — not confirmation framing ("H_x is supported by E1, E3").
7. Run sensitivity analysis — name at least one evidence item whose reversal would flip the ranking, with the specific cell change required.
8. When adversarial actors are plausible, assess whether high-diagnosticity evidence could be manufactured or planted, and which hypotheses benefit.
9. List monitoring priorities per surviving hypothesis — leading indicators that would update the analysis.

**Goal.** Produce a matrix-format ACH artifact with Heuer vocabulary, elimination-arithmetic verdict, diagnosticity assessment, sensitivity findings, and (when applicable) deception assessment.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — hypothesis breadth.** Has at least one hypothesis beyond the user's initial set been generated, or is the matrix limited to user-proposed explanations? Failure mode if unmet: `missing-hypothesis`.
- **CQ2 — across-not-down posture.** Has each evidence item been assessed across all hypotheses, or only against the favoured one? Failure mode if unmet: `confirmation-framing`.
- **CQ3 — elimination framing.** Is the conclusion framed as elimination of least-consistent hypotheses, or as confirmation of the favoured one? Failure mode if unmet: `confirmation-framing`.
- **CQ4 — diagnosticity.** Has at least one piece of evidence been identified as high-diagnosticity, distinguishing sharply between hypotheses? Failure mode if unmet: `false-rigour`.
- **CQ5 — deception assessment.** If adversarial actors are plausible, has the analysis assessed whether high-diagnosticity evidence could be manufactured? Failure mode if unmet: `deception-blindness`.

A passing output has a fully populated matrix in Heuer vocabulary, names the surviving hypothesis as the one with fewest I+II cells with arithmetic shown, identifies high-diagnosticity evidence explicitly, performs sensitivity analysis with at least one ranking-flip candidate, addresses deception when applicable, and lists monitoring priorities.

**Named failure modes.**

- *missing-hypothesis* — all hypotheses user-proposed; no analyst-generated alternative or null hypothesis.
- *confirmation-framing* — conclusion phrased as "H_x is supported by E1, E3" rather than "H_x survives because fewer items contradict it"; or evidence assessed only against the favoured hypothesis.
- *false-rigour* — matrix format used but consistency ratings uniform across rows or unjustified; all rows non-diagnostic.
- *deception-blindness* — adversarial context plausible but no assessment of whether high-diagnosticity evidence could be planted or manufactured.
- *wrong-tally* — endorsed surviving hypothesis has more inconsistent (I + II) cells than an alternative; conclusion contradicts cell count.
- *static-snapshot* — no monitoring priorities or leading indicators stated; analysis treated as final in an evolving situation.

## REVISION GUIDANCE

Revise to fill missing cells (use NA explicitly when evidence does not bear on a hypothesis; never leave cells absent). Revise to convert custom vocabulary ("supports", "refutes") to Heuer vocabulary. Revise to add hypotheses where the matrix is too narrow, including at least one analyst-generated alternative. Revise to convert confirmation framing ("H2 is supported by E1, E3") to elimination framing ("H2 survives because fewer items contradict it — count of I+II cells per hypothesis"). Revise to recount cell tallies if the prose conclusion contradicts the matrix arithmetic. Resist revising toward the user's favoured hypothesis if the matrix doesn't support it — the methodology's purpose is to surface when the favourite loses. Silent conclusion flips during revision are failures unless cell values were also changed with rationale.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a hypothesis × evidence matrix with diagnosticity atoms and elimination-arithmetic verdicts**, per Heuer ACH methodology. The matrix is the load-bearing data structure; everything else attaches to it. The atoms are:

1. **Hypothesis atoms.** Canonical IDs H1, H2, … assigned to each surviving hypothesis after cross-stream deduplication. Same hypothesis under different wordings collapses to one canonical statement (most precise phrasing wins). At least one analyst-generated hypothesis must survive the dedup (CQ1). A null / "something else" hypothesis appears when applicable.

2. **Evidence atoms.** Canonical IDs E1, E2, … assigned to each evidence item, each carrying: short content statement, credibility rating, relevance rating, source attribution. Cross-stream evidence overlap collapses to one atom; when credibility or relevance ratings diverge between streams, audit conservatism applies (the lower rating survives).

3. **Matrix cells.** Every (H_i, E_j) cell carries a Heuer-vocabulary rating: CC (very consistent), C (consistent), N (neutral), I (inconsistent), II (very inconsistent), NA (not applicable). NA is explicit, never absent. When the two streams rated the same cell differently, **the cell carries both ratings as a marked tension** — the disagreement is a real analytical signal, not bloat. The tension atom names: H_i, E_j, stream-A rating, stream-B rating, and a one-line divergence reason if extractable.

4. **Diagnosticity atoms per evidence row.** High-diagnosticity (cells vary sharply across hypotheses — the row discriminates), low-diagnosticity (cells uniform — the row doesn't discriminate), or NA-dominated. At least one high-diagnosticity evidence item must be flagged or CQ4 fails.

5. **Elimination-arithmetic verdicts per hypothesis.** I+II count per H_i, II count as tie-breaker. The surviving hypothesis is the one with fewest I+II cells; this corpus-level verdict atom is stated once. When the streams disagree on cell ratings, the arithmetic is computed twice (once per rating set) and both counts appear, with the difference flagged — automatic sensitivity-on-divergence.

6. **Sensitivity atoms.** Each names an evidence item whose reversal would flip the ranking, citing the specific cell change required and the resulting arithmetic shift. At minimum one such atom is named or CQ4 fails.

7. **Deception atoms.** When adversarial actors are plausible (CQ5 applies), atoms name which high-diagnosticity evidence items could be manufactured or planted, and which hypotheses benefit. Absent adversarial context, a single atom records "deception-not-applicable" with brief reason.

8. **Monitoring-priority atoms per surviving hypothesis.** Each names a leading indicator: what new evidence or evidence reversal would update the analysis.

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Hypothesis-statement paraphrase** — same hypothesis under different wordings across streams ("the system is failing because of X" vs "X is causing the system to fail"). Single canonical statement survives.
- **Evidence-summary paraphrase** — same evidence item summarized in different prose. Single evidence atom survives with the most precise content statement.
- **Diagnosticity-narrative duplication** — same evidence row flagged as high-diagnosticity in different language ("E3 distinguishes sharply" vs "E3 is the most discriminating item"). One diagnosticity atom per row.
- **Elimination-discipline restatement** — Heuer's "elimination, not confirmation" posture surfaces multiple times across passages in varied framings. The corpus carries one elimination-arithmetic verdict atom; the disconfirmation discipline does not need restating per hypothesis.
- **Sensitivity-finding overlap** — both streams identify the same evidence-reversal as ranking-flipping. One sensitivity atom per such finding.
- **Monitoring-priority overlap** — overlapping leading indicators across streams union to one atom per indicator.

**What NOT to collapse:**

- **Cell-rating divergence** — when the two streams rated the same (H_i, E_j) cell differently, that disagreement is preserved as a tension atom on the cell. ACH's analytical value lies in disconfirmation rigor; suppressing rating disagreement to produce a clean-looking matrix is a synthesis injection (the consolidator inventing certainty the streams did not establish).
- **Single-stream hypothesis origination** — when one stream generated a hypothesis the other did not, the hypothesis survives in the canonical set with provenance noted as "single-stream origination." Both shared and unshared hypotheses are auditable downstream.

## VERIFICATION CRITERIA

Verified means: at least 3 hypotheses in play, including at least one analyst-generated; at least 3 evidence items with credibility/relevance ratings; every (evidence × hypothesis) cell populated with Heuer vocabulary; at least one diagnostic row (cells not all equal); the surviving hypothesis named in prose has the fewest I+II cells in the matrix (tie-broken by II); at least one high-diagnosticity item explicitly named; sensitivity analysis names at least one evidence item whose reversal would change the ranking; deception check addressed when adversarial actors are plausible; monitoring priorities listed. The five critical questions are addressable from the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **matrix-format ACH artifact with elimination-arithmetic verdict and sensitivity findings**, per Heuer methodology. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Hypothesis list.** Numbered list of canonical H1, H2, … Each hypothesis stated in one sentence. Tag each with origin (user-supplied / analyst-generated / null hypothesis). At minimum 3 hypotheses; at least one analyst-generated.

2. **Evidence inventory.** Numbered list of canonical E1, E2, … Each evidence atom carries: one-line content statement, credibility rating (high / moderate / low), relevance rating (high / moderate / low), source attribution.

3. **Consistency matrix.** A table with hypotheses as columns (H1 … Hn) and evidence as rows (E1 … En). Each cell carries Heuer vocabulary: **CC** (very consistent), **C** (consistent), **N** (neutral), **I** (inconsistent), **II** (very inconsistent), **NA** (not applicable). NA is explicit, never absent. When the streams disagreed on a cell's rating, render the cell as `A_rating | B_rating` with both values and a footnote naming the divergence reason.

4. **Diagnosticity assessment.** Per evidence row: **high-diagnosticity** / **low-diagnosticity** / **NA-dominated**, with a one-line reason. Highlight which evidence items are the most discriminating across hypotheses.

5. **Tentative conclusions via elimination.** State the elimination arithmetic explicitly: I+II count per hypothesis, with the surviving hypothesis named as the one with fewest I+II cells (tie-broken by II count alone). Frame the verdict as "H_x survives because it has fewer items contradicting it" — NOT "H_x is confirmed by E1, E3, …" Confirmation framing is forbidden. When streams' cell ratings produced different counts, render both arithmetics with the difference flagged.

6. **Sensitivity analysis.** A bulleted list naming evidence items whose reversal would flip the ranking, with the specific cell change required and the resulting arithmetic shift. At minimum one sensitivity finding.

7. **Deception assessment.** When adversarial actors are plausible, name which high-diagnosticity evidence items could be manufactured or planted, and which hypotheses benefit. Absent adversarial context, write "Deception assessment not applicable: [brief reason]."

8. **Monitoring priorities.** Bulleted list of leading indicators per surviving hypothesis — what new evidence or evidence reversal would update the analysis.

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- The consistency matrix is rendered as a markdown table when supported. When width would be unwieldy, fall back to a per-evidence list with each cell value tagged.
- Hypothesis and evidence IDs are referenced consistently throughout (H1 not "Hypothesis 1" inline once the IDs are introduced).
- Elimination arithmetic is shown numerically (e.g., "H1: I+II = 3, II = 1"), not paraphrased.
- Across-the-matrix posture is preserved in framing: the analysis is keyed to evidence-rows (what does each evidence item discriminate among hypotheses?), not to hypothesis-columns (what supports each hypothesis?).


---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~10min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `contradicts`, `qualifies`, `produces`, `precedes`
**Deprioritize:** `parent`, `analogous-to`

*Family: hypothesis-future. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
