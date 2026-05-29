---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Multi-Criteria Decision

```yaml
# 0. IDENTITY
mode_id: multi-criteria-decision
canonical_name: Multi-Criteria Decision
suffix_rule: analysis
educational_name: "multi-criteria decision analysis (MCDM: AHP, SMART, ELECTRE, etc.)"

# 1. TERRITORY AND POSITION
territory: T3-decision-making-under-uncertainty
gradation_position:
  axis: complexity
  value: multi-criteria
adjacent_modes_in_territory:
  - mode_id: constraint-mapping
    relationship: depth-lighter sibling (environment-known)
  - mode_id: decision-under-uncertainty
    relationship: depth-thorough sibling (probability-and-time-weighted single-criterion)
  - mode_id: decision-architecture
    relationship: depth-molecular sibling (built Wave 4)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I'm choosing among options and they trade off across multiple things I care about"
    - "no single criterion can settle this"
    - "I want to see how the options stack up across all the dimensions"
    - "weighting matters here and I want to make my weights explicit"
  prompt_shape_signals:
    - "multi-criteria"
    - "MCDA"
    - "MCDM"
    - "weighted criteria"
    - "AHP"
    - "SMART analysis"
    - "criteria matrix"
    - "rank options across"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user has named (or implies) ≥3 criteria that matter to the decision"
    - "user wants explicit weights and a structured cross-criterion comparison"
    - "options are discrete and enumerable; criteria can be operationalized into scores"
  routes_away_when:
    - "decision turns on probability and time-weighting under a single dominant criterion" → decision-under-uncertainty
    - "decision is about mapping environmental constraints rather than choosing among options" → constraint-mapping
    - "decision requires molecular orchestration across stakeholders, scenarios, and criteria" → decision-architecture
when_not_to_invoke:
  - "Decision has only one or two criteria — overhead of MCDM exceeds value" → decision-under-uncertainty or constraint-mapping
  - "User is exploring the future or projecting consequences rather than choosing" → T6 modes
  - "Decision is among parties whose conflict is the analytical object" → T8 stakeholder-mapping or T13 modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [option_set, criteria_list, weighting_preferences]
    optional: [scoring_data, mcdm_method_preference, sensitivity_threshold, tradeoff_tolerances]
    notes: "Applies when user supplies enumerated options, named criteria, and at least preliminary weights."
  accessible_mode:
    required: [decision_description, options_being_considered]
    optional: [what_matters_most, dealbreakers]
    notes: "Default. Mode elicits criteria and weights during execution; criteria surfaced from 'what matters' phrasing."
  detection:
    expert_signals: ["criteria are", "weights are", "AHP", "SMART", "ELECTRE", "TOPSIS", "pairwise comparison"]
    accessible_signals: ["choosing between", "weighing", "tradeoff", "what matters most", "stack up"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What are the options you're choosing among, and what dimensions matter to the choice?'"
    on_underspecified: "Ask: 'Of those criteria, which carry more weight for you, and roughly by how much?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the criteria genuinely independent of one another, or do they double-count by measuring the same underlying attribute under different names?"
    failure_mode_if_unmet: criterion-redundancy
  - cq_id: CQ2
    question: "Are the weights elicited from the decision-maker's actual preferences, or imposed by the analyst's choice of MCDM method without preference elicitation?"
    failure_mode_if_unmet: weight-imposition
  - cq_id: CQ3
    question: "Has sensitivity analysis surfaced how robust the ranking is to weight perturbations and scoring uncertainty, or is the top-ranked option presented as if the ranking were stable?"
    failure_mode_if_unmet: false-stability
  - cq_id: CQ4
    question: "Have dominated options (those beaten by another option on every criterion) been identified and pruned, and have dominant options (beating others on every criterion) been flagged as no-brainer choices?"
    failure_mode_if_unmet: dominance-blindness

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: criterion-redundancy
    detection_signal: "Two or more criteria score highly correlated across options without explicit acknowledgment that they capture related aspects."
    correction_protocol: flag
  - name: weight-imposition
    detection_signal: "Weights stated without rationale or elicitation history; equal weights used as a 'neutral' default without surfacing that equal weighting is itself a preference choice."
    correction_protocol: re-dispatch
  - name: false-stability
    detection_signal: "Sensitivity analysis section is empty, or perturbation tested only one weight at a time when joint perturbation would change the ranking."
    correction_protocol: re-dispatch
  - name: dominance-blindness
    detection_signal: "Output presents a full ranking when dominance relations would have pruned the option set or made the top choice obvious."
    correction_protocol: flag
  - name: aggregation-method-opacity
    detection_signal: "Aggregation method (additive, multiplicative, ELECTRE-style outranking, etc.) not named, or named without explanation of why this method fits the decision shape."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - mcdm-methods
  optional:
    - kahneman-tversky-bias-catalog (when weight elicitation is anchored or framed)
    - rumelt-strategy-kernel (when criteria are strategic and the choice is strategy-shaped)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: decision-architecture
    when: "Decision involves multiple stakeholders with diverging weights, requires scenario integration, or carries sequential-decision structure (real options)."
  sideways:
    target_mode_id: decision-under-uncertainty
    when: "On reflection a single criterion dominates; multi-criteria framing was overhead."
  downward:
    target_mode_id: constraint-mapping
    when: "Choice resolves once constraints are mapped; no genuine multi-criteria tradeoff remains."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Multi-Criteria Decision is the explicitness of method choice, weight elicitation, and sensitivity testing. A thin pass produces a weighted-sum ranking with implicit method assumptions; a substantive pass names the MCDM method (additive SMART, AHP pairwise, ELECTRE outranking, TOPSIS distance-from-ideal, etc.), explains why it fits the decision shape, surfaces weights with elicited rationale, identifies dominance relations to prune the option set, runs sensitivity analysis on both weights and scores, and flags where the ranking is robust vs. fragile. Test depth by asking: could the analysis tell the decision-maker which weight or score perturbation would flip the top choice?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means surveying the criteria space for under-named dimensions (the criterion the decision-maker would notice they cared about only if it were missing), scanning for criterion redundancy (two criteria measuring the same underlying attribute), and considering whether the option set itself is complete (would option-set expansion change the analysis?). Breadth markers: criteria are surveyed across at least three categories (e.g., outcome-quality, cost, risk, fit, reversibility); option set is sanity-checked for completeness before scoring.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Multi-Criteria Decision (MCDM) is a structured comparison of discrete options across multiple weighted criteria, applying a named aggregation method (SMART additive, AHP pairwise, ELECTRE outranking, TOPSIS distance-from-ideal, etc.) with explicit weight elicitation, sensitivity analysis, and dominance pruning. It is the multi-criteria position in T3's complexity ladder — distinct from constraint-mapping (depth-lighter; environment-known, no scoring) and decision-under-uncertainty (depth-thorough; probability-and-time-weighted single criterion). When the decision involves multiple stakeholders, scenario integration, or sequential-decision structure, the mode escalates to decision-architecture; when a single criterion turns out to dominate, it routes sideways to decision-under-uncertainty.

**Procedure.**

1. Enumerate the option set and sanity-check completeness — flag missing options that would change the analysis.
2. Define each criterion operationally — name, units, score-assignment rule, preference direction (higher better / lower better / target).
3. Check criterion independence — flag or merge criteria measuring the same underlying attribute under different names.
4. Elicit weights with rationale — decision-maker preference statements, pairwise comparison, or explicit assignment; when weights are equal, state explicitly that equal weighting is itself a preference choice.
5. Score each (option × criterion) cell — score, units, grounding (evidence / inference / qualitative estimate); flag gaps rather than silently zeroing.
6. Name the aggregation method and explain why it fits the decision shape — additive SMART, AHP, ELECTRE, TOPSIS, etc.
7. Produce the aggregated ranking with per-option scores.
8. Run sensitivity analysis — at minimum one joint weight-score perturbation; identify the ranking-flip threshold; flag method-fragile top choices.
9. Surface dominance relations — prune dominated options; flag dominant ones as no-brainer choices that make the rest of the matrix ceremony.
10. Hold three confidence kinds distinct — scoring uncertainty, weight uncertainty, method-fit uncertainty.

**Goal.** Produce an MCDM matrix-with-ranking that names the aggregation method, makes weights explicit with elicitation rationale, surfaces sensitivity and dominance relations, and tells the decision-maker not just which option ranks first but how robust the ranking is to perturbation.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — criterion independence.** Are the criteria genuinely independent, or do they double-count by measuring the same underlying attribute under different names? Failure mode if unmet: `criterion-redundancy`.
- **CQ2 — weight elicitation.** Are the weights elicited from the decision-maker's actual preferences, or imposed by the analyst's method choice without preference elicitation? Failure mode if unmet: `weight-imposition`.
- **CQ3 — sensitivity robustness.** Has sensitivity analysis surfaced how robust the ranking is to weight perturbations and scoring uncertainty, or is the top-ranked option presented as if the ranking were stable? Failure mode if unmet: `false-stability`.
- **CQ4 — dominance handling.** Have dominated options been pruned and dominant options flagged as no-brainer choices? Failure mode if unmet: `dominance-blindness`.

A passing output names the aggregation method with rationale, surfaces weights with elicitation, scores each cell explicitly, runs at least one joint weight-score sensitivity perturbation, flags dominance relations, and keeps scoring / weight / method-fit confidences distinct.

**Named failure modes.**

- *criterion-redundancy* — two or more criteria score highly correlated across options without acknowledgment that they capture related aspects.
- *weight-imposition* — weights stated without rationale or elicitation history; equal weights used as a "neutral" default without surfacing that equal weighting is itself a preference choice.
- *false-stability* — sensitivity analysis section empty, or perturbation tested only one weight at a time when joint perturbation would change the ranking.
- *dominance-blindness* — output presents a full ranking when dominance relations would have pruned the option set or made the top choice obvious.
- *aggregation-method-opacity* — aggregation method (additive, multiplicative, ELECTRE-style outranking, etc.) not named, or named without explanation of why it fits the decision shape.

## REVISION GUIDANCE

Revise to add weight rationale where the draft presents weights without elicitation. Revise to add sensitivity analysis where the draft presents the ranking as stable. Revise to prune dominated options and flag dominant ones rather than presenting a flat ranking. Resist revising toward false consensus — if criteria genuinely conflict, the artifact's job is to surface the tradeoff, not to manufacture a clear winner. If the ranking is method-fragile (small perturbations flip the top choice), say so explicitly.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **an MCDM matrix atom set: enumerated options, operationally-defined criteria, weight atoms with elicitation rationale, scoring atoms per (option × criterion) cell, aggregation-method atom with rationale, sensitivity atoms covering joint weight-and-score perturbation, dominance-relation atoms, and per-finding confidence**. The atoms are:

1. **Option-inventory atoms.** Each atom names one option in the choice set. The set is sanity-checked for completeness — when streams flagged an under-considered option or option-set expansion that would change the analysis, the flag is preserved.

2. **Criterion-definition atoms.** Each atom carries: the criterion name and its *operational* definition (how a score would be assigned, what the units are, what the direction of preference is). Criterion-redundancy is the named failure mode the consolidator watches for; two criteria measuring the same underlying attribute under different names get flagged or merged.

3. **Weight atoms with elicitation rationale.** Each weight atom carries: the weight value, the elicitation history (decision-maker preference statement / pairwise comparison / explicit assignment / analyst-imposed equal-weighting), and the rationale. Weight-imposition is the named failure mode; weights stated without rationale, or equal-weights asserted as "neutral" without acknowledging that equal weighting is itself a preference choice, get reshaped.

4. **Scoring atoms per (option × criterion) cell.** Each cell carries: the score, the units, and a brief grounding (named evidence, structural inference, qualitative estimate). The matrix is filled; gaps are surfaced as flags rather than silent zeros.

5. **Aggregation-method atom.** The MCDM method chosen (additive SMART, AHP pairwise, ELECTRE outranking, TOPSIS distance-from-ideal, etc.), named explicitly, with the rationale tying it to the decision shape. Aggregation-method-opacity is the named failure mode; methods used without being named or without rationale get reshaped.

6. **Aggregated-ranking atom.** The ranking the method produces, with each option's aggregated score.

7. **Sensitivity-analysis atoms.** Each atom names: a perturbation (single-weight, joint-weight, scoring, joint weight-score), the perturbation magnitude, and the ranking-shift outcome. False-stability is the named failure mode; rankings presented as if stable without sensitivity testing (or with only single-weight perturbation when joint perturbation would change the ranking) get reshaped.

8. **Dominance-relation atoms.** Each atom names: a dominated option (beaten on every criterion) and a dominant option (beating others on every criterion). Dominance-blindness is the named failure mode; full rankings presented when dominance relations would have pruned the set or made the top choice obvious get reshaped.

9. **Confidence per finding** — three confidence kinds kept separate: scoring uncertainty, weight uncertainty, method-fit uncertainty. These do not blend.

**Mode-specific bloat patterns to cut:**

- **Criterion redundancy** — two criteria scoring highly correlated across options without explicit acknowledgment.
- **Weight imposition** — equal-weights used as "neutral default" without surfacing that equal weighting is a preference.
- **Single-perturbation sensitivity** — perturbing one weight at a time when joint perturbation would change the ranking.
- **Dominance blindness** — full rankings emitted when dominance pruning would have answered the decision.
- **Method opacity** — additive aggregation used without naming the method or explaining its fit.
- **False winners** — rankings presented as stable when small perturbations flip the top choice. If the ranking is method-fragile, the corpus says so.
- **Manufactured consensus** — if criteria genuinely conflict, the corpus surfaces the tradeoff rather than smoothing to a clear winner.

**What NOT to collapse:**

- **Method-fragile top choices** — when the top-ranked option flips under modest weight or score perturbation, the fragility is itself a finding and survives.
- **Genuine criterion conflict** — when two criteria pull in opposite directions and no single option satisfies both, the conflict is preserved rather than smoothed by weighting tricks.
- **Stream disagreement about method fit** — when streams diverged on which MCDM method fits the decision shape (e.g., additive SMART vs. ELECTRE outranking), both readings survive with their respective rankings.
- **Weight-elicitation disagreements** — when streams elicited different weights from the same preference signals, both weight sets survive with their elicitation histories; the disagreement reveals what the decision-maker's actual preferences are uncertain about.

## VERIFICATION CRITERIA

Verified means: criteria are named and defined operationally; weights are elicited or explicitly noted as analyst-imposed (with reason); aggregation method is named and explained; scoring is explicit per option per criterion; sensitivity analysis runs at least one joint weight-score perturbation; dominance relations are surfaced; the four critical questions are addressable from the output. Confidence accompanies each major finding.

## OUTPUT FORMAT GUIDANCE

The deliverable is an **MCDM matrix-with-ranking** — a structured analysis where options are scored across criteria with explicit weights, an aggregation method is named, and sensitivity analysis surfaces ranking-stability. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Options inventory.** Bulleted list. Each: `**[Option]** — brief characterisation.` Where the option set was flagged as potentially incomplete, the section closes with: `**Option-set completeness flag:** [missing option that would change the analysis, with reason].`

2. **Criteria definitions.** A table. Each row: `**[Criterion]** — operational definition: [how a score is assigned]. Units: [...]. Preference direction: [higher is better / lower is better / target].` Operationally-defined; "quality" or "fit" without operational grounding gets reshaped at this layer.

3. **Weights with rationale.** A table or bulleted list. Each: `**[Criterion]** — weight: [value]. Elicitation: [decision-maker preference / pairwise comparison / analyst-imposed with reason]. Rationale: [...].` When weights are equal, the rationale states explicitly that equal weighting is a preference choice, not a neutral default.

4. **Scoring matrix.** A table. Rows are options, columns are criteria, cells are scores. A weights row sits beneath the criteria headers. Score units appear in the column header. Cells where scoring was uncertain carry a confidence marker inline.

5. **Aggregated ranking.** A table or numbered list with the aggregated score per option. The method name appears: `Aggregation method: [SMART additive / AHP pairwise / ELECTRE outranking / TOPSIS / other]. Why this method fits this decision: [brief rationale].`

6. **Sensitivity analysis.** Bulleted list of perturbation results. Each: `**[Perturbation — single weight / joint weight / scoring / joint weight-score]** — magnitude: [...]. Ranking shift: [stable / top-choice flip at weight Δ = X / partial reorder].` At minimum, one joint weight-score perturbation appears.

7. **Dominant and dominated options.** Two labelled sub-blocks:
   - `**Dominant options (beat others on every criterion):** [list].`
   - `**Dominated options (beaten by another option on every criterion — can be pruned):** [list].`
   
   When dominance pruning would have made the choice obvious, this section closes with: `**Dominance verdict:** [option X dominates and is the no-brainer choice; subsequent sections may be skimmed].`

8. **Confidence per finding.** Three labelled confidence assessments:
   - `Scoring: [confidence and grounding per cell or per option].`
   - `Weights: [confidence and elicitation quality].`
   - `Method fit: [confidence the chosen method matches the decision shape].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- The MCDM vocabulary (SMART, AHP, ELECTRE, TOPSIS, pairwise comparison, dominance, outranking) is operative where it applies; methods are named verbatim.
- When the top choice is method-fragile (flips under modest perturbation), section 5 carries a labelled `**Stability flag:** the top-ranked option flips under [Δ = X] on [weight / score]. The recommendation is contingent on the named weights and scores holding.`
- When dominance relations make the choice obvious, sections 4–6 may be compressed; the deliverable surfaces the dominance verdict rather than producing matrix-and-ranking ceremony for a no-brainer choice.
- When streams diverged on method fit, section 5 renders the disagreement: `**Method-disagreement:** stream A favoured [method] for [reason]; stream B favoured [method] for [reason]. Where the two methods agree on the top choice: [...]. Where they diverge: [...].`
- Confidence (section 8) stays as three distinct kinds; collapsing to single overall confidence is reshaped here.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- CAF
- FIP
- APC
- AGO
- KVI

Mental models (always loaded):
- mcdm-methods
- trade-offs
- arrows-impossibility-theorem
- prospect-theory
- loss-aversion
- decision-trees

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `requires`, `enables`, `qualifies`, `supports`, `contradicts`
**Deprioritize:** `analogous-to`, `parent`

*Family: decision-risk. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
