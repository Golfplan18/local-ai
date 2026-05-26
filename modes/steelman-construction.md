---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-24
no_visual: true

---

# MODE: Steelman Construction

```yaml
# 0. IDENTITY
mode_id: steelman-construction
canonical_name: Steelman Construction
suffix_rule: analysis
educational_name: strongest-case construction (steelman)

# 1. TERRITORY AND POSITION
territory: T15-artifact-evaluation-by-stance
gradation_position:
  axis: stance
  value: constructive-strong
adjacent_modes_in_territory:
  - mode_id: benefits-analysis
    relationship: stance-counterpart (constructive-balanced — Plus/Minus/Interesting)
  - mode_id: balanced-critique
    relationship: stance-counterpart (neutral)
  - mode_id: red-team-assessment
    relationship: stance-counterpart (adversarial-actor-modeling, assessment — direct opposite)
  - mode_id: red-team-advocate
    relationship: stance-counterpart (adversarial-actor-modeling, advocate)
  - mode_id: devils-advocate-lite
    relationship: stance-counterpart (adversarial-light — gap-deferred)
cross_territory_reference:
  - territory: T1-argumentative-artifact-examination
    note: "When the artifact under steelmanning is itself an argument, T1 cross-reference activates. The home territory remains T15; T1 informs lens selection (e.g., argument-coherence considerations) without re-homing the mode."

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "a position is about to be critiqued or dismissed"
    - "I want to understand the opposing argument at its strongest before evaluating"
    - "the debate involves caricature of one side"
    - "I want to give this idea its fairest hearing"
  prompt_shape_signals:
    - "steelman"
    - "best case for"
    - "strongest version of"
    - "what's the best argument for X"
    - "give me the strongest formulation"
disambiguation_routing:
  routes_to_this_mode_when:
    - "you want a single artifact reconstructed at its logical best, then critiqued only at that strength"
    - "the input is one position or proposal you want strengthened"
    - "self-directed epistemic hygiene — strengthen-then-critique workflow"
  routes_away_when:
    - "balanced evaluation across positive, negative, and interesting" → benefits-analysis
    - "neutral examination weighing both sides equally" → balanced-critique
    - "tear it down adversarially for own decision" → red-team-assessment
    - "build the case against for external use" → red-team-advocate
    - "drive thesis through antithesis to synthesis" → dialectical-analysis (T12)
    - "trace whose interests the position serves" → cui-bono (T2)
    - "question the foundational frame the position rests on" → paradigm-suspension (T9)
when_not_to_invoke:
  - "User wants a balanced evaluation, not a constructive-strong stance" → benefits-analysis or balanced-critique
  - "User wants the artifact attacked for own fix-prioritisation" → red-team-assessment
  - "User wants an argument brief against the artifact for external use" → red-team-advocate
  - "User is auditing the argument's soundness as an argument, not building its best version" → T1 (argument-audit / coherence-audit / frame-audit)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: constructive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [position_or_proposal, position_proponents_or_canonical_sources]
    optional: [user_position_for_agreement_mapping, prior_critiques_to_avoid_recapitulating]
    notes: "Applies when user supplies the position with explicit attribution to proponents or canonical formulations."
  accessible_mode:
    required: [position_or_proposal_to_steelman]
    optional: [user_position_or_critique_context]
    notes: "Default. Mode infers proponents and canonical formulations from the position."
  detection:
    expert_signals: ["canonical formulation", "the proponents' best argument", "Rawls argues", "academic literature on"]
    accessible_signals: ["steelman", "best case for", "strongest version", "give it the fairest hearing"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What position or argument do you want me to construct the strongest case for?'"
    on_underspecified: "Ask: 'Could you state the position you want steelmanned, and whether you'd like me to identify points of agreement with your own view?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Would a thoughtful proponent of this position endorse the reconstruction (mirror test), or would they recognize their argument weakened?"
    failure_mode_if_unmet: tinman-trap
  - cq_id: CQ2
    question: "Is the steelman recognizably the same argument strengthened, or has it drifted into a different argument the analyst prefers?"
    failure_mode_if_unmet: identity-loss
  - cq_id: CQ3
    question: "Does the critique address only the steelmanned version, or does it retreat to the weaker original at any point?"
    failure_mode_if_unmet: retreat-to-original
  - cq_id: CQ4
    question: "Was the steelman built fully before critique began, or were construction and critique entangled?"
    failure_mode_if_unmet: entangled-construction

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: tinman-trap
    detection_signal: "Reconstruction appears strong but is designed to be defeated; mirror test fails (proponent would not endorse)."
    correction_protocol: re-dispatch
  - name: identity-loss
    detection_signal: "Reconstruction has drifted into a different argument; core claim of original position no longer present."
    correction_protocol: re-dispatch
  - name: retreat-to-original
    detection_signal: "Critique paragraph addresses the weaker original formulation at one or more passages."
    correction_protocol: re-dispatch
  - name: steel-strawman
    detection_signal: "Steelman appears generally strong but a specific point is engineered for defeat by the subsequent critique."
    correction_protocol: re-dispatch
  - name: projection-trap
    detection_signal: "Reconstruction filtered through analyst's worldview rather than the proponent's values; charitable inferences favour analyst's frame."
    correction_protocol: flag
  - name: entangled-construction
    detection_signal: "Construction and critique appear interleaved; steelman was not built fully before critique began."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - rapoport-rules-of-engagement
    - dennett-charitable-interpretation
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Steelman Construction is the canonical constructive-strong mode in T15; no heavier sibling along the stance axis."
  sideways:
    target_mode_id: benefits-analysis
    when: "User wants balanced evaluation rather than asymmetric strengthening; switch to constructive-balanced."
  downward:
    target_mode_id: null
    when: "No lighter constructive-strong sibling; if user wants a quick endorsement rather than a strengthened reconstruction, route out of T15 entirely."
```

## DEPTH ANALYSIS GUIDANCE

Going deeper in Steelman Construction means reconstructing the position at its logical best — surfacing hidden premises that would make the argument stronger, filling logical gaps with the most charitable inferences, and marshalling the best available evidence. Depth shows itself in the mirror test: would a thoughtful proponent say "I wish I'd thought of putting it that way"? A thin pass paraphrases; a substantive pass formulates more precisely than proponents have, identifies the strongest premises, and marshalls evidence that would be most difficult for a critic to dismiss. Construction completes fully before critique begins — entangled construction-and-critique is a structural failure mode.

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for the proponent's full philosophical or strategic context, not just the immediate claim. Identify hidden premises, fill gaps, and look for the strongest available support across the position's intellectual lineage. Identify at least two points of agreement between the steelmanned position and the user's own — these are not concessions but genuine common ground that often opens unexpected analytical leverage. Identify what is genuinely valuable in the position, separate from its rhetorical packaging. Breadth markers: hidden premises are explicitly surfaced, points of agreement are numbered and grounded in the user's stated view, and the steelman's intellectual lineage is acknowledged.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Steelman Construction is a constructive-strong stance mode that reconstructs a position at its logical best — surfacing hidden premises, filling logical gaps charitably, and marshalling the best available evidence — then critiques only that strongest version. It is asymmetric by design: it is distinct from balanced-critique (neutral weighing), benefits-analysis (Plus/Minus/Interesting balanced evaluation), red-team-assessment (adversarial-stance evaluation of an artifact for the user's own decision), and red-team-advocate (adversarial brief for external use). The mode is prose-only — any visual emission is a structural failure.

**Procedure.**

1. State the original position once in bounded form (≤ ⅓ of the steelman section length) — including the weaknesses the reconstruction will strengthen.
2. Reconstruct the position at its logical best — surface hidden premises that strengthen the argument, fill logical gaps with the most charitable inferences, marshal the most defensible evidence and intellectual lineage.
3. Apply the mirror test — would a thoughtful proponent endorse the reconstruction? If not, strengthen further before proceeding.
4. Identify load-bearing strengths — the most defensible premises, the hardest-to-dismiss evidence, the intellectual lineage that gives the position weight.
5. Surface at least two concrete points of agreement between the steelmanned position and the user's own view (when supplied) — genuine common ground, not concessions.
6. Critique only the steelman — each critique passage anchors to a strength identified in step 4. If a critique only applies to the original-position weaknesses, drop it; do not weaken the steelman to make the critique fit.
7. Maintain construction-before-critique ordering — build the steelman fully before critique begins. Interleaved construction-and-critique is a structural failure.
8. Produce the survival assessment — what remains compelling after critique. Even when the critique lands, name what holds, what is qualified, and what falls.
9. When multiple positions are steelmanned, apply identical rigor to each (symmetry guard rail).

**Goal.** Produce a constructive-strong charitable reconstruction with critique-at-steelman-strength, in prose only — where the steelman is recognizably the same argument strengthened, at least two points of agreement are explicit, the critique addresses only the strongest version, and the survival assessment names what remains compelling.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — mirror test pass.** Would a thoughtful proponent endorse the reconstruction, or would they recognize their argument weakened? Failure mode if unmet: `tinman-trap`.
- **CQ2 — identity preservation.** Is the steelman recognizably the same argument strengthened, or has it drifted into a different argument the analyst prefers? Failure mode if unmet: `identity-loss`.
- **CQ3 — critique targets steelman only.** Does the critique address only the steelmanned version, or does it retreat to the weaker original at any point? Failure mode if unmet: `retreat-to-original`.
- **CQ4 — construction before critique.** Was the steelman built fully before critique began, or were construction and critique entangled? Failure mode if unmet: `entangled-construction`.

A passing output has all six required sections, the steelmanned reconstruction is recognizably the same argument strengthened, at least two points of agreement are explicit, the critique addresses only the strongest version, the survival assessment names what remains compelling after critique, and no visual envelope is emitted.

**Named failure modes.**

- *tinman-trap* — reconstruction appears strong but is designed to be defeated; mirror test fails (proponent would not endorse).
- *identity-loss* — reconstruction has drifted into a different argument; core claim of original position no longer present.
- *retreat-to-original* — critique paragraph addresses the weaker original formulation at one or more passages.
- *steel-strawman* — steelman appears generally strong but a specific point is engineered for defeat by the subsequent critique.
- *projection-trap* — reconstruction filtered through analyst's worldview rather than the proponent's values; charitable inferences favour analyst's frame.
- *entangled-construction* — construction and critique appear interleaved; steelman was not built fully before critique began.

## REVISION GUIDANCE

Revise to strengthen the reconstruction wherever a thoughtful proponent would recognize weakness — apply the mirror test until it passes. Revise to re-anchor to the original claim wherever the steelman has drifted into a different argument. Revise to rewrite critique passages that retreat to the weaker original; if a critique doesn't apply to the steelmanned version, drop it rather than weakening the steelman to make the critique fit. Revise to rebuild from the proponent's values where the reconstruction has filtered through the analyst's worldview. Resist revising toward "balanced" presentation — the mode is asymmetric by design; the constructive-strong stance is the deliverable. If multiple positions need steelmanning, apply identical rigor to each (symmetry guard rail).

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Rapoport/Dennett charitable-reconstruction atom set: original-position atom (faithful, weaknesses included), steelmanned-reconstruction atoms (the strongest version, identity-preserved), strength-identification atoms, points-of-agreement atoms (≥2), critique atoms addressing only the steelman, survival-assessment atom, and explicit construction-completes-before-critique ordering**. The atoms are:

1. **Original-position atom.** A faithful re-expression of the position as it appears in the wild, including the weaknesses the steelman will strengthen. The atom is *bounded* (≤ ⅓ of steelman section length) so construction dominates rather than repetition of the weak formulation.

2. **Steelmanned-reconstruction atoms.** The strongest possible version of the argument — hidden premises surfaced to strengthen, logical gaps filled with the most charitable inferences, the best available evidence marshalled. Tinman-trap is the named failure mode the consolidator watches for; reconstructions that *appear* strong but are designed to be defeated (mirror test fails — proponent would not endorse) get reshaped. Identity-loss is the mirror failure; reconstructions that drift into a different argument the analyst prefers get re-anchored to the original's core claim.

3. **Strength-identification atoms.** Each atom names: the most defensible premises in the reconstruction, the hardest-to-dismiss evidence, the intellectual lineage that gives the position weight.

4. **Points-of-agreement atoms.** At least two atoms naming concrete agreement between the steelmanned position and the user's own view (when the user supplied a view). These are not concessions; they are genuine common ground that often opens analytical leverage. Projection-trap is the named failure mode; reconstructions filtered through analyst's worldview such that charitable inferences favour analyst's frame get reshaped to build from the proponent's values.

5. **Critique atoms — addressing only the steelman.** Each critique addresses the strongest version, not the original. Retreat-to-original is the named failure mode; critique passages that target the weaker original get reshaped (or dropped if they don't survive against the steelman). Steel-strawman is also flagged: portions of the steelman engineered for defeat get reshaped.

6. **Survival-assessment atom.** What remains compelling after the critique. Even when the critique lands, what survives is the load-bearing finding — the original position's residual force.

7. **Construction-completes-before-critique ordering.** A standing structural commitment: the steelman is built *fully* before critique begins. Entangled-construction is the named failure mode; interleaved construction-and-critique gets reshaped to sequential ordering.

8. **No-visual atom.** The mode is prose-only. Any visual envelope emission is a structural failure; if visual rendering is wanted, dialectical-analysis (T12) is the right sideways-route.

9. **Confidence per finding.** Each major claim (mirror-test pass, identity preservation, points-of-agreement, survival assessment) carries confidence with grounding.

**Mode-specific bloat patterns to cut:**

- **Tinman** — reconstruction looks strong but is designed to be defeated; mirror test fails.
- **Identity loss** — reconstruction drifts into a different argument; core claim no longer present.
- **Retreat to original** — critique addresses the weaker formulation at one or more passages.
- **Steel-strawman** — generally strong reconstruction with a specific point engineered for defeat.
- **Projection** — reconstruction filtered through analyst's worldview rather than the proponent's values.
- **Entangled construction** — interleaved construction-and-critique rather than sequential.
- **Balanced presentation drift** — the mode is asymmetric by design (constructive-strong stance); balanced-presentation drift gets reshaped (if balance is wanted, route to benefits-analysis or balanced-critique).
- **Visual emission** — any diagram, envelope, or visual summary is a structural failure.
- **Original-position dominance** — original-position paragraph exceeding ⅓ of the steelman length; reshape to construction-dominant proportions.

**What NOT to collapse:**

- **Identity-preserving strength** — the reconstruction must remain the same argument strengthened, not replaced. The corpus preserves the core claim throughout.
- **Points-of-agreement** — at least two are required when a user position is in play. They are not optional.
- **Survival under critique** — what remains compelling is the load-bearing finding; never elided for a clean "and the steelman fails" verdict.
- **Construction-before-critique ordering** — never collapsed into interleaved presentation.
- **Multiple steelmans applied to multiple positions** — when more than one position is being steelmanned, identical rigour applies to each (symmetry guard rail).

## VERIFICATION CRITERIA

Verified means: all six required sections present in order or clearly demarcated; original-position paragraph bounded (≤ ⅓ of steelman section length); mirror test passes (a thoughtful proponent would endorse the reconstruction); steelman is recognizably the same argument strengthened (not replaced); at least two points of agreement explicit; critique addresses only the steelmanned version with no retreat to the original; survival assessment present; no visual envelope emitted. The four critical questions are addressable from the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **constructive-strong charitable reconstruction with critique-at-steelman-strength** — prose-only, with the original position bounded, the steelmanned reconstruction dominant, points of agreement explicit, and the critique addressing only the strongest version. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Original position.** One bounded paragraph (≤ ⅓ of section 2's length). A faithful re-expression of the position as it appears in the wild, including the weaknesses that will be addressed in reconstruction.

2. **Steelmanned reconstruction.** The largest section. Multiple paragraphs constructing the strongest possible version of the argument — hidden premises surfaced, logical gaps filled charitably, best evidence marshalled, intellectual lineage acknowledged. The reconstruction is recognizably the same argument strengthened, not a different argument the analyst prefers.

3. **Strength identification.** Bulleted list of the steelman's load-bearing elements. Each: `**[Premise or evidence]** — why this is hardest to dismiss: [...]. Where in the reconstruction it appears: [...].`

4. **Points of agreement.** Numbered list. At least two. Each: `[N]. **[Point]** — how the steelmanned position holds it: [...]. How the user's view holds it: [...]. What common ground this opens: [...].`

5. **Critique of the steelman.** Prose addressing only the strongest version. Each critique passage anchors to a strength identified in section 3 rather than to the original-position weaknesses. Critique passages that don't apply to the steelman get reshaped or dropped, not the steelman.

6. **Survival assessment.** One paragraph naming what remains compelling after critique. Even if the critique lands, what the steelmanned position retains is named explicitly. `**Survives critique:** [what holds]. **Modified by critique:** [what is qualified]. **Defeated by critique:** [what falls — only if the critique against the steelman is decisive].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 6.
- Format is **prose-only**. No diagram, no envelope, no visual summary. If the user requests visual rendering, the deliverable surfaces a sideways-route: `**Note: visual rendering is not part of this mode's contract. Dialectical-analysis (T12) emits IBIS and may be the appropriate transition if the back-and-forth structure is what's wanted visually.**`
- Original-position (section 1) is bounded — repetition of the weak formulation does not dominate the deliverable. Original sections that exceed ⅓ of the steelman length get reshaped to bounded proportions.
- The mirror test discipline is operative throughout: would a thoughtful proponent endorse the reconstruction in section 2? If not, the reconstruction is reshaped, not the critique.
- Critique (section 5) anchors to the steelman's strengths from section 3. Passages that target the original-position weaknesses from section 1 get reshaped or removed.
- When multiple positions are being steelmanned (rare but possible), each receives identical rigour — symmetry across reconstructions. Asymmetric treatment is reshaped at this layer.
- Survival assessment (section 6) preserves the residual force of the position. "And the steelman fails" verdicts that elide what survives get reshaped to honest accounting of what holds.


---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `contradicts`, `qualifies`, `extends`
**Deprioritize:** `precedes`, `parent`

*Family: argument-evaluation. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
