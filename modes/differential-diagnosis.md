---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Differential Diagnosis

```yaml
# 0. IDENTITY
mode_id: differential-diagnosis
canonical_name: Differential Diagnosis
suffix_rule: analysis
educational_name: light differential diagnosis (medical-tradition lighter sibling of ACH)

# 1. TERRITORY AND POSITION
territory: T5-hypothesis-evaluation
gradation_position:
  axis: depth
  value: light
adjacent_modes_in_territory:
  - mode_id: competing-hypotheses
    relationship: depth-heavier sibling (full Heuer ACH)
  - mode_id: bayesian-hypothesis-network
    relationship: depth-molecular sibling (built Wave 4)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I have a few candidate explanations and need a quick weigh-in"
    - "what are the main possibilities and which is most likely"
    - "narrow down the candidates"
    - "rule things out quickly"
    - "what else could this be"
  prompt_shape_signals:
    - "differential"
    - "differential diagnosis"
    - "candidate explanations"
    - "what are the possibilities"
    - "rule out"
    - "most likely cause"
disambiguation_routing:
  routes_to_this_mode_when:
    - "two-to-five candidate explanations; user wants light diagnosticity weighing"
    - "user has limited time and prefers a quick narrowing over a full ACH matrix"
    - "evidence-set is small enough to weigh informally"
  routes_away_when:
    - "user wants full evidence-by-hypothesis matrix with disconfirming-evidence focus" → competing-hypotheses
    - "user wants probability network with conditional dependencies" → bayesian-hypothesis-network
    - "competing explanations are really inter-frame disagreement (paradigm clash)" → frame-comparison or worldview-cartography (T9)
when_not_to_invoke:
  - "Only one hypothesis on the table — no differential to make" → use a single-hypothesis-test mode in T1 or T4
  - "Hypotheses are themselves complete arguments needing soundness audit" → T1
  - "User wants to know who benefits, not which explanation fits" → cui-bono (T2)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: neutral

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [observed_evidence, candidate_hypotheses, prior_probability_estimates]
    optional: [diagnosticity_notes, base_rate_data, cost_of_misdiagnosis]
    notes: "Applies when user supplies a structured hypothesis list and evidence inventory."
  accessible_mode:
    required: [situation_description, candidate_explanations]
    optional: [evidence_observed_so_far]
    notes: "Default. Mode elicits evidence and infers candidate hypothesis structure if not supplied."
  detection:
    expert_signals: ["candidate hypotheses", "prior probability", "diagnosticity", "base rate", "evidence inventory"]
    accessible_signals: ["differential", "what else could this be", "rule out", "most likely cause"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you tell me what you've observed and which explanations are on the table?'"
    on_underspecified: "Ask: 'What's the symptom or pattern, and what explanations have you considered so far?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the candidate hypotheses genuinely different explanations of the evidence, or are some of them re-descriptions of the same underlying explanation?"
    failure_mode_if_unmet: hypothesis-collapse
  - cq_id: CQ2
    question: "Does the diagnosticity assessment distinguish evidence that *rules out* hypotheses from evidence that is merely *consistent with* them, given that consistent evidence is weak diagnostic?"
    failure_mode_if_unmet: confirmation-anchoring
  - cq_id: CQ3
    question: "Has the analysis identified at least one disconfirming test for each of the top two candidates, so the user can act to narrow further?"
    failure_mode_if_unmet: no-actionable-disconfirmer
  - cq_id: CQ4
    question: "Has the analysis flagged when the evidence base is too small for a confident ranking, rather than producing a ranking it cannot support?"
    failure_mode_if_unmet: false-confidence

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: hypothesis-collapse
    detection_signal: "Two or more named hypotheses make identical predictions about the evidence; the differential is artificial."
    correction_protocol: re-dispatch
  - name: confirmation-anchoring
    detection_signal: "Diagnosticity is assessed via consistency only (this evidence is consistent with H1) rather than via disconfirming power (this evidence rules out H2)."
    correction_protocol: re-dispatch
  - name: no-actionable-disconfirmer
    detection_signal: "Top-ranked hypotheses are returned without naming a test that would distinguish them."
    correction_protocol: flag
  - name: false-confidence
    detection_signal: "A ranking is produced when evidence is too sparse to support it; confidence per ranking is inflated."
    correction_protocol: flag
  - name: missing-zebra
    detection_signal: "Common-case explanations dominate; rare-but-serious explanations are not present even as low-rank candidates."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - differential-diagnosis-schema
  optional:
    - heuer-ach (when escalating to full ACH)
    - bayesian-base-rate (when prior probabilities are available)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~1min
escalation_signals:
  upward:
    target_mode_id: competing-hypotheses
    when: "Hypothesis count exceeds five, evidence inventory is large, or user wants disconfirming-evidence focus across the matrix."
  sideways:
    target_mode_id: frame-comparison
    when: "On reflection the candidates are inter-frame disagreements (paradigm clashes) rather than within-frame hypotheses; route to T9."
  downward:
    target_mode_id: null
    when: "Differential Diagnosis is the lightest mode in T5."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Differential Diagnosis is the rigor with which diagnosticity is assessed: not just "this evidence is consistent with H1" but "this evidence rules out H2 because H2 predicted X and we observed not-X." A thin pass ranks by surface plausibility; a substantive pass distinguishes consistency from diagnosticity, names which observations would rule each top hypothesis out, and surfaces the rare-but-serious "zebra" candidates that common-case explanations would otherwise eclipse. Test depth by asking: does the ranking change appropriately when one piece of evidence is hypothetically inverted?

## BREADTH ANALYSIS GUIDANCE

Widening the lens in Differential Diagnosis means deliberate inclusion of rare-but-serious candidates, candidates from adjacent domains (a symptom that looks like X in domain A might be Y in domain B), candidates that combine mechanisms (the situation may be H1 *and* H3 together rather than H1 alone), and the null hypothesis (the situation is benign and self-resolving). Even when only the top two-or-three are ranked, the breadth pass documents the candidates considered and rejected with a one-line reason for rejection.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Differential Diagnosis is a light medical-tradition differential — the depth-light sibling of competing-hypotheses' full ACH matrix. Given two-to-five candidate explanations and a modest evidence base, it ranks the candidates by diagnosticity in disconfirming-power language and produces an actionable disconfirming test per top candidate. It is distinct from competing-hypotheses (full Heuer ACH with evidence-by-hypothesis matrix and disconfirming focus across all cells), from bayesian-hypothesis-network (probability network with conditional dependencies), and from frame-comparison (which handles inter-frame paradigm clash rather than within-frame hypothesis weighing). The mode's value is honest residual uncertainty when evidence supports two or three candidates roughly equally, not a forced single-explanation verdict.

**Procedure.**

1. Name the candidate hypotheses as genuinely distinct explanations — collapse candidates that make identical predictions, or differentiate them by surfacing where their predictions diverge.
2. Inventory the evidence — each observation named once, tagged with which hypotheses it bears on.
3. Assess diagnosticity per (evidence × hypothesis) cell in disconfirming-power language verbatim: `rules out` / `discriminating-positive` / `consistent with` / `irrelevant`.
4. Surface rare-but-serious "zebra" candidates that common-case explanations would otherwise eclipse — explicitly note them at low rank rather than omitting, or state "no plausible zebra in this evidence base" with reason.
5. Consider combination candidates — when the situation may be one hypothesis AND another together rather than one alone, render as its own candidate with joint diagnosticity reasoning.
6. Rank candidates with reasoning — name which evidence cells were load-bearing for each rank, plus a sensitivity check (what perturbation would change the rank).
7. Produce a disconfirming test per top-two candidate — actionable observation or experiment, cost or feasibility, and the evidence-shift it would produce.
8. Flag evidence sufficiency — when the evidence base is too sparse for a confident ranking, surface the `Evidence-sufficiency flag` explicitly rather than inflating confidence.
9. Calibrate confidence per ranking — per-candidate, not collapsed into a single overall verdict.

**Goal.** Produce a structured differential — a ranked-options artifact where distinct candidates are weighed against the evidence in disconfirming-power language and each top candidate carries an actionable test.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — hypothesis distinctness.** Are the candidates genuinely different explanations of the evidence, or are some re-descriptions of the same underlying explanation? Failure mode if unmet: `hypothesis-collapse`.
- **CQ2 — consistency vs diagnosticity.** Does the diagnosticity assessment distinguish evidence that rules out from evidence merely consistent with, given that consistent evidence is weak diagnostic? Failure mode if unmet: `confirmation-anchoring`.
- **CQ3 — actionable disconfirmer.** Has the analysis identified at least one disconfirming test for each of the top two candidates? Failure mode if unmet: `no-actionable-disconfirmer`.
- **CQ4 — confidence honesty.** Has the analysis flagged when the evidence base is too small for a confident ranking, rather than producing one it cannot support? Failure mode if unmet: `false-confidence`.

A passing output ranks distinct candidate hypotheses by diagnosticity in disconfirming-power language verbatim (`rules out`, `discriminating-positive`, `consistent with`, `irrelevant`), offers at least one actionable disconfirming test per top candidate, surfaces zebra candidates (or notes their absence with reason), preserves equally-ranked candidates as ties rather than forcing a verdict, and either supports its confidence with evidence or flags the ranking as evidence-limited.

**Named failure modes.**

- *hypothesis-collapse* — two or more named hypotheses make identical predictions about the evidence; the differential is artificial.
- *confirmation-anchoring* — diagnosticity assessed via consistency only, rather than via disconfirming power.
- *no-actionable-disconfirmer* — top-ranked hypotheses returned without naming a test that would distinguish them.
- *false-confidence* — ranking produced when evidence is too sparse to support it; confidence inflated.
- *missing-zebra* — common-case explanations dominate; rare-but-serious explanations absent even at low rank.

## REVISION GUIDANCE

Revise to merge collapsed hypotheses where two candidates make identical predictions, or to differentiate them by predicting where their predictions diverge. Revise to upgrade consistency-language to diagnosticity-language. Revise to add a disconfirming test where the top candidates are ranked without one. Resist revising toward a single-explanation summary when the evidence supports two or three competing candidates equally — the mode's value is in honest residual uncertainty, not in delivering a verdict.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a diagnosticity-ranked candidate-hypothesis atom set: distinct candidates, evidence-by-hypothesis atoms, diagnosticity atoms (in disconfirming-power language), ranking with reasoning, one disconfirming test per top-two candidate, and confidence honest about evidence sparseness**. The atoms are:

1. **Candidate-hypothesis atoms.** Each atom names one candidate explanation in a single line: the hypothesis, its mechanism in one phrase, and any prior probability or base-rate hint. Hypothesis-collapse is the named failure mode the consolidator watches for; candidates that make identical predictions are merged here (or differentiated by surfacing where their predictions diverge).

2. **Evidence atoms.** Each atom carries: the observation, when/how it was made, and a tag noting which candidate hypotheses it bears on. The corpus does not duplicate the evidence across hypothesis blocks; each piece of evidence is named once and referenced.

3. **Diagnosticity atoms per (evidence × hypothesis) cell.** Each cell carries a diagnosticity label in disconfirming-power language: `rules out` (the hypothesis predicted the opposite of what was observed), `discriminating-positive` (the hypothesis predicted this observation specifically, in contrast to others), `consistent with` (the observation does not bear against the hypothesis but does not discriminate it from siblings), `irrelevant`. Confirmation-anchoring is the named failure mode; cells labelled `consistent with` are weak diagnostic and the corpus surfaces this explicitly rather than treating consistency as confirmation.

4. **Ranking atoms with reasoning.** Each ranked candidate carries: rank position, the diagnostic reasoning that places it there (which evidence drove the ranking, which cells were load-bearing), and the alternative ranking that would emerge under a small perturbation (sensitivity check).

5. **Disconfirming-test atoms — one per top-two candidate.** Each atom carries: the observation or test that would rule the candidate out, the cost or feasibility of running the test, and the evidence-shift the test would produce. No-actionable-disconfirmer is the named failure mode; rankings without disconfirming-test atoms for the top two get flagged.

6. **Zebra-candidate atoms — when applicable.** Rare-but-serious candidates that common-case explanations would otherwise eclipse, named explicitly with their mechanism and the cost of missing them. Missing-zebra is the named failure mode; the corpus surfaces zebras at low-rank rather than omitting them, or explicitly notes "no plausible zebra in this evidence base" with reason.

7. **Combination-candidate atoms (optional).** When the situation may be one hypothesis *and* another together rather than one alone, the combination is its own candidate atom with the joint diagnosticity reasoning.

8. **Evidence-sufficiency flag.** When the evidence base is too sparse to support a confident ranking, the corpus carries an explicit flag — false-confidence is the named failure mode the consolidator watches for. The flag does not suppress the ranking but qualifies the confidence per ranking.

9. **Confidence per ranking.** Each rank carries a confidence assessment with explicit grounding in evidence-sufficiency. Confidences are not blended into a single overall verdict; they remain per-candidate.

**Mode-specific bloat patterns to cut:**

- **Hypothesis-collapse residue** — candidates that make identical predictions presented as different rankings. Merged or differentiated at this layer.
- **Consistency-as-diagnosticity** — language that treats "evidence is consistent with H1" as if it confirmed H1. The corpus reshapes to disconfirming-power language.
- **Ranking without disconfirming tests** — top candidates returned without actionable tests that would distinguish them.
- **Missing zebras** — common-case explanations dominate without rare-but-serious candidates even at low rank.
- **Inflated confidence on sparse evidence** — rankings that don't acknowledge their own evidential limits.
- **Single-explanation collapse** — corpus that picks a winner when the evidence supports two or three competing candidates roughly equally. Honest residual uncertainty is the mode's value, not a verdict.
- **Re-narration of each hypothesis-by-evidence cell** — the corpus uses the diagnosticity-cell shape, not paragraph re-narration that paraphrases the same content per hypothesis.

**What NOT to collapse:**

- **Equally-ranked candidates** — when streams produced rankings where two or three candidates are roughly tied on diagnosticity, the tie is the finding. Forcing a verdict is single-explanation collapse.
- **Stream disagreement about diagnosticity-cell labels** — when one stream rated evidence as `rules out` and another as `consistent with`, the disagreement is the finding and both labels survive with their respective reasoning.
- **Zebra-candidate inclusion vs. omission** — when one stream surfaced a zebra and another omitted it, the zebra survives at low rank with the omission-reason noted.
- **Frame-clash flag** — when one stream treated the candidates as within-frame hypotheses and another flagged them as inter-frame paradigm clash (sideways to frame-comparison), the flag survives so the user can choose the right mode.

## VERIFICATION CRITERIA

Verified means: at least two candidate hypotheses are present and distinct; diagnosticity is assessed in disconfirming-power language for at least the top two; at least one disconfirming test is emitted per top candidate; confidence per ranking explicitly addresses evidence sufficiency; rare-but-serious "zebra" candidates have been considered (or their absence noted with reason); the four critical questions are addressable from the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structured differential** — a ranked-options artifact where distinct candidates are weighed against the evidence in disconfirming-power language and each top candidate carries an actionable test. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Candidate hypotheses.** Bulleted list. Each: `**[Candidate hypothesis name]** — mechanism in one phrase. [Prior probability or base-rate hint, if available].` Each candidate is genuinely distinct from its siblings; collapsed candidates are merged at this layer.

2. **Evidence observed.** Bulleted list. Each: `**[Observation]** — context: [when / how observed]. Bears on: [hypothesis tags — H1, H2, H3 ...].` Each piece of evidence is named once.

3. **Diagnosticity per hypothesis.** A table or per-hypothesis block. For each (evidence × hypothesis) cell, a label in disconfirming-power language: `rules out` / `discriminating-positive` / `consistent with` / `irrelevant`. The table makes it possible to see at a glance which cells are load-bearing.

4. **Ranking with reasoning.** A numbered ranking. Each entry: `[N]. **[Candidate]** — placed here because [diagnostic reasoning, naming the load-bearing cells]. Sensitivity: [what would change this rank under small perturbation].` Zebra candidates appear at appropriate low ranks with a one-line note on why they were considered.

5. **Disconfirming tests for top two.** Two labelled sub-blocks:
   - `**Test for top candidate ([Candidate 1]):** [observation or experiment]. Cost / feasibility: [...]. Evidence-shift if positive / negative: [...].`
   - `**Test for second candidate ([Candidate 2]):** [observation or experiment]. Cost / feasibility: [...]. Evidence-shift: [...].`

6. **Confidence per ranking.** Bulleted list. Each: `**[Candidate]** — confidence: [grounded in cells / limited by sparse evidence / contested between streams]. Evidence sufficiency: [adequate / sparse / inconclusive].` When evidence is too sparse to support the ranking, the deliverable carries an explicit `**Evidence-sufficiency flag:** the evidence base may be too small for a confident ranking; the top candidates above represent the best current reading rather than a stable diagnosis.`

**Per-section conventions:**

- Use H2 headings for sections 1 through 6.
- Diagnosticity vocabulary in section 3 is operative — `rules out`, `discriminating-positive`, `consistent with`, `irrelevant` appear verbatim. Consistency language is not silently elevated to confirmation.
- The ranking (section 4) does not converge to a single verdict when streams produced roughly-tied candidates; ties are rendered as `[1, tied]. [Candidate A]` / `[1, tied]. [Candidate B]` with the tie reasoning attached.
- Disconfirming tests (section 5) are actionable — they name what to observe or do, not what to think.
- When streams diverged on a diagnosticity-cell label, the deliverable renders the disagreement inside the matrix: `[evidence] × [hypothesis]: stream-A: rules out; stream-B: consistent with. Resolution path: [what test or further evidence would decide].`
- When the corpus carried a frame-clash flag (the candidates may be inter-frame paradigm disagreement rather than within-frame hypotheses), the deliverable opens with a brief note before section 1: `**Note: if the candidates below are reading the situation through different frames rather than offering different explanations within one frame, frame-comparison is the appropriate sideways-route.**`
- Confidence (section 6) stays per-candidate; collapsing into a single overall confidence is reshaped at this layer.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~1min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- CAF
- FIP
- Challenge

Mental models (always loaded):
- bayesian-reasoning
- base-rate-neglect
- representativeness-heuristic
- differential-diagnosis-schema
- occams-razor

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `contradicts`, `qualifies`, `produces`, `precedes`
**Deprioritize:** `parent`, `analogous-to`

*Family: hypothesis-future. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
