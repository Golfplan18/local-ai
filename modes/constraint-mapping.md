---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01

---

# MODE: Constraint Mapping

```yaml
# 0. IDENTITY
mode_id: constraint-mapping
canonical_name: Constraint Mapping
suffix_rule: analysis
educational_name: constraint and option mapping (light decision analysis)

# 1. TERRITORY AND POSITION
territory: T3-decision-making-under-uncertainty
gradation_position:
  axis: depth
  value: light
adjacent_modes_in_territory:
  - mode_id: decision-under-uncertainty
    relationship: depth-thorough sibling (probability and time-weighted)
  - mode_id: multi-criteria-decision
    relationship: complexity sibling (multi-criteria)
  - mode_id: decision-architecture
    relationship: depth-molecular sibling
  - mode_id: real-options-decision
    relationship: specificity counterpart (staged investment) — gap-deferred
  - mode_id: ethical-tradeoff
    relationship: stance counterpart (normative + values-laden) — gap-deferred

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "multiple viable options exist"
    - "which should I choose"
    - "tradeoff analysis"
    - "compare alternatives"
  prompt_shape_signals:
    - "compare alternatives"
    - "map the tradeoffs"
    - "what are the pros and cons of each option"
disambiguation_routing:
  routes_to_this_mode_when:
    - "deterministic tradeoffs in a known environment; no probability arithmetic needed"
    - "the user wants the choice terrain mapped, not the choice made"
  routes_away_when:
    - "probabilities and time-value are central" → decision-under-uncertainty
    - "decision involves multiple weighted criteria" → multi-criteria-decision
    - "decision is a molecular orchestration with stakeholders + risk + future" → decision-architecture
    - "user wants to evaluate ONE proposal's merits and risks" → benefits-analysis (T15)
    - "user is questioning the framework within which alternatives exist" → paradigm-suspension (T9)
when_not_to_invoke:
  - "User has already chosen and wants execution" → Project Mode
  - "Decision is fundamentally about who benefits from each alternative" → Cui Bono (T2)
  - "User is searching for the right answer rather than choosing among alternatives" → other T-investigative mode

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [decision_context, candidate_alternatives_named, hard_constraints]
    optional: [soft_constraints, prior_decision_history]
    notes: "Applies when user explicitly names the alternatives and the constraint structure."
  accessible_mode:
    required: [decision_or_choice_situation]
    optional: [hint_at_some_alternatives]
    notes: "Default. Mode elicits at least 3 alternatives during execution, including any the user has not named."
  detection:
    expert_signals: ["alternatives are A, B, C", "hard constraint is", "must satisfy", "the constraints are"]
    accessible_signals: ["which should I choose", "compare these options", "what are the tradeoffs"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the choice you're facing, and what are the alternatives you're considering?'"
    on_underspecified: "Ask: 'Are probabilities and time-value central to this choice (route to Decision Under Uncertainty), or are the tradeoffs deterministic?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are at least three alternatives mapped, including any the user has not named?"
    failure_mode_if_unmet: false-dichotomy
  - cq_id: CQ2
    question: "Are success and failure conditions stated as testable propositions for each alternative, with identical analytical depth across alternatives?"
    failure_mode_if_unmet: advocacy-asymmetry
  - cq_id: CQ3
    question: "Have no-lose elements (actions valuable regardless of which alternative is chosen) been surfaced explicitly?"
    failure_mode_if_unmet: missed-no-lose
  - cq_id: CQ4
    question: "Does the mode map the choice terrain without making the choice for the user, unless explicitly asked?"
    failure_mode_if_unmet: choice-collapse

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: false-dichotomy
    detection_signal: "Only two alternatives mapped when ≥3 are viable, OR a binary framing masks the option space."
    correction_protocol: re-dispatch (generate ≥3 alternatives or switch to pro/con form for genuinely binary choices)
  - name: advocacy-asymmetry
    detection_signal: "One alternative receives substantially deeper analysis than others."
    correction_protocol: re-dispatch (equalise analytical depth across alternatives)
  - name: abstraction-trap
    detection_signal: "Success or failure conditions stated as vague abstractions, not testable propositions with thresholds or observables."
    correction_protocol: re-dispatch (rewrite as testable conditions)
  - name: choice-collapse
    detection_signal: "Mode delivers a single recommended alternative when the user asked for the terrain mapped."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - rumelt-strategy-kernel (when alternatives are strategic options)
    - strategic-2x2-matrix-tradition
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~1min
escalation_signals:
  upward:
    target_mode_id: decision-under-uncertainty
    when: "Probability arithmetic or time-value analysis is required for the choice."
  sideways:
    target_mode_id: multi-criteria-decision
    when: "Decision involves multiple weighted criteria across alternatives."
  downward:
    target_mode_id: null
    when: "Constraint Mapping is already the lightest depth in T3."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Constraint Mapping is the testability of success and failure conditions per alternative. A thin pass enumerates pros and cons in vague terms; a substantive pass states each success condition as a testable proposition with a threshold or observable, and traces the cost of each forfeit concretely. Test depth by asking: could each alternative's success be falsified by a specific observation? Each alternative carries the same four sub-sections (success conditions / failure conditions / uniquely gained / forfeited), with identical analytical depth.

## BREADTH ANALYSIS GUIDANCE

Breadth in Constraint Mapping is the catalog of alternatives, including any the user has not named. Widen the lens to identify ≥3 alternatives (or 2 in genuinely binary cases), generate hybrid or sequencing strategies, and surface no-lose elements (actions valuable regardless of choice). Breadth markers: alternatives include at least one the user did not initially name; at least one no-lose element is identified; hybrid or sequencing options are considered.

## EVALUATION CRITERIA

Constraint Mapping is read in the light decision-theoretic tradition — Rumelt strategy-kernel framing where alternatives are strategic options, plus the strategic 2×2 matrix tradition where alternatives plot on orthogonal criteria, with Knightian risk-vs-uncertainty distinctions for the conditions under which constraint mapping (deterministic) is the right mode rather than decision-under-uncertainty (probabilistic). The evaluator's primary axis is whether the deliverable is mapping the terrain or making the choice. CQ4 (choice-collapse) is load-bearing — the mode's contract is to map, not decide. CQ2 (advocacy-asymmetry) is also load-bearing because asymmetric depth across alternatives is the analyst tilting the map. CQ1 (false-dichotomy) and CQ3 (missed-no-lose) act as breadth gates; the unnamed abstraction-trap acts as a specificity gate.

Evaluator checks:

1. **Choice abstention (CQ4, load-bearing).** The recommendation slot must be empty unless the user explicitly asked for a final choice. Phrasings like "the best option appears to be," "I would recommend," "the clear winner is" are choice-collapse residue — the analyst has slipped from mapping into deciding. The deliverable presents the terrain; the user makes the choice. When asked for a recommendation, the slot is populated explicitly; when not, the slot carries an explicit empty-with-reason atom rather than silent omission.

2. **Symmetric analytical depth (CQ2, load-bearing).** Each alternative carries the same four parallel slots (success conditions / failure conditions / uniquely gained / forfeited), and they render at parallel depth. Advocacy-asymmetry — one alternative analysed at noticeably greater depth than others — is the analyst tilting the map toward a preferred option without saying so. The evaluator's check: do the four slots for each alternative carry comparable substance, or does one alternative read like a recommendation in disguise? When asymmetry is honest (an alternative is genuinely thinner because less viable), the deliverable names the reason explicitly rather than padding the thin alternative or silently leaning on the deep one.

3. **Testable conditions, not vague abstractions.** Each success condition and failure condition must be stated as a testable proposition with threshold or observable — "completes within 90 days at ≤$50K" rather than "improves efficiency." Abstraction-trap residue is conditions that could not be falsified by any specific observation. The test: could each condition's satisfaction or violation be settled by data the user could in principle obtain? If not, the condition is reshaped.

4. **Alternative breadth (CQ1).** At minimum three alternatives must survive (or two in genuinely binary cases with an explicit pro/con-form tag and reason). At least one alternative should be analyst-generated rather than user-named — the breadth marker that the analyst widened the option space beyond what the user brought. False-dichotomy is the failure mode; a two-alternative analysis when three viable options exist has narrowed the choice prematurely.

5. **No-lose elements surfaced (CQ3).** No-lose elements are actions valuable regardless of which alternative is chosen — they cut across the choice and let the user act before deciding. At minimum one no-lose element must be named, or the deliverable says explicitly that none exist. Test: does each named no-lose element pass the cross-alternative-applicability check (it's valuable under A1 *and* A2 *and* A3, not just under one)? Single-alternative items mis-tagged as no-lose are misclassified gains.

6. **Format-choice grounded.** The cross-alternative comparison renders as one of three forms (strategic 2×2 grid when alternatives plot on orthogonal criteria, four-quadrant per-alternative table when the four slots are the grid, or pro/con tree when binary). The deliverable names the chosen format with a reason — why this form fits this case better than the alternatives. Format chosen by default rather than by case-fit is its own failure of methodology.

Confidence is per-alternative when relevant — alternatives whose viability rests on weaker information bases carry that confidence marker explicitly. Where streams disagreed on which alternative is dominant or which format fits, the evaluator confirms the disagreements are preserved as parallel atoms rather than silently picked.

## REVISION GUIDANCE

Revise to add alternatives until ≥3 (or switch to pro/con form for genuinely binary choices). Revise to equalise analytical depth across alternatives. Revise to convert vague conditions into testable propositions. Resist revising toward a final choice if the user asked for the terrain mapped — the mode's contract is mapping, not deciding. Resist revising toward consensus framing — the mode honours genuine tradeoffs.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **alternative atoms with symmetric four-slot per-alternative analysis (success / failure / gain / forfeit), plus no-lose elements and cross-alternative comparison atoms**. The four slots are the load-bearing parallel structure; symmetric analytical depth across alternatives is the mode's discipline. The atoms are:

1. **Decision-context atom.** The choice situation, hard constraints, and soft constraints, stated once at the corpus head. Cross-stream paraphrase collapses to one canonical statement.

2. **Alternative atoms — at least three.** Each alternative carries four parallel sub-atoms:
   - **Success conditions** — testable propositions with thresholds or observables (not vague abstractions; abstraction-trap residue does not survive)
   - **Failure conditions** — testable propositions naming what would falsify the alternative's success
   - **Uniquely gained** — what this alternative provides that the others do not
   - **Forfeited** — what this alternative costs that the others retain

   At least three alternatives must survive cross-stream dedup (CQ1, false-dichotomy failure mode), unless the choice is genuinely binary in which case the corpus carries an explicit "binary choice — pro/con form" atom with the reason. At least one alternative must be analyst-generated (the user did not initially name it).

3. **Analytical-depth-symmetry atom.** A corpus-level atom flags the analytical depth across alternatives. Advocacy-asymmetry is the named failure mode; when one alternative receives substantially deeper analysis than others, the corpus carries the asymmetry as a finding (with reason — is the deeper-analyzed alternative genuinely better-supported, or has the analyst tilted toward it?). Symmetric depth is the default expectation; asymmetric depth requires explicit justification.

4. **No-lose-element atoms.** Each carries: action statement, value-rationale, and which alternatives it applies under (the test of a no-lose element is that it's valuable across all alternatives — single-alternative-only "no-lose" items are misclassified gains). At least one no-lose element atom must survive or the breadth marker is unmet.

5. **Cross-alternative-comparison atoms.** Each names a differentiating factor — the dimensions on which alternatives diverge most sharply. These are not restatements of the per-alternative slots; they are the comparison-level findings (e.g., "alternatives A and B both succeed on cost but fail on time-to-implement; alternative C inverts this").

6. **Format-choice atom.** The format selected for the deliverable corpus organization — 2×2 matrix (when alternatives plot cleanly on two orthogonal criteria), four-quadrant per-alternative table (when the four slots are the structuring grid), or pro/con tree (when the choice is genuinely binary). The format-choice atom carries the reason — why this format fits this case better than the alternatives.

7. **Choice-recommendation atom — conditional.** Empty by default. Populated only when the user explicitly asked for a recommendation (not just a terrain map). Choice-collapse is the named failure mode; an unsolicited recommendation invalidates the mode's contract, which is to map the terrain.

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Alternative-paraphrase loops** — both streams may state the same alternative under different framings ("invest in X" vs "allocate resources to X"). Single canonical statement survives.
- **Vague-condition residue** — success or failure conditions stated as "improves outcomes" or "reduces risk" without threshold or observable. Abstraction-trap residue; either a testable proposition replaces the vague version or the condition does not survive into the corpus.
- **Per-slot paraphrase** — same gain or forfeit stated under different wordings. Single slot atom survives.
- **Choice-collapse residue** — phrasings like "the best option appears to be", "I would recommend", "the clear winner". Choice-collapse residue does not survive unless the user asked for a recommendation.
- **Asymmetric-padding** — one alternative's four slots padded with weak content to match the depth of another's. The honest finding is the asymmetry, not the padding; padding does not survive.
- **Restated-differentiating-factors** — both streams may state the same differentiating factor under different framings. Single comparison atom survives.

**What NOT to collapse:**

- **Genuinely different alternative sets** — when the two streams enumerated different alternatives (with overlap but not identity), preserve all surviving alternatives. The mode's breadth marker is generating alternatives the user did not name; both streams' analyst-generated alternatives are evidence of breadth, not redundancy.
- **Real depth-asymmetry across alternatives** — when one alternative is genuinely thinner because it's less viable (rather than because the analyst neglected it), preserve the asymmetric depth and carry the reason in the analytical-depth-symmetry atom. Forcing symmetric length onto genuinely asymmetric viability is its own failure.
- **Format-choice disagreement** — when one stream selected 2×2 and the other selected pro/con tree (or four-quadrant table), preserve the disagreement in the format-choice atom with both formats' reasons. The format choice is consequential for what the deliverable looks like; the consolidator must not silently pick.

## VERIFICATION CRITERIA

Verified means: ≥3 alternatives mapped (or 2 in pro/con form for genuinely binary choices); success and failure conditions stated as testable propositions per alternative; analytical depth symmetric across alternatives; no-lose elements explicitly called out; the mode does not make the final choice unless the user explicitly asked. The four critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structured matrix of alternatives with per-alternative four-slot analysis (success / failure / gain / forfeit), no-lose elements, and cross-alternative comparison**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Decision context and constraints.** Two short blocks at the top:
   - **Decision:** the choice situation, in one or two sentences.
   - **Constraints:** numbered list of hard constraints (must-satisfy) and soft constraints (would-prefer-to-satisfy), each labelled `[hard]` or `[soft]`.

2. **Alternatives at a glance.** A bulleted list of A1, A2, A3, … (canonical IDs) with one-line characterizations. At minimum three alternatives (or two in pro/con form for genuinely binary choices, with explicit `[binary choice — pro/con form]` tag and reason). At least one alternative is tagged `[analyst-generated]` for breadth marker.

3. **Per-alternative analysis — symmetric four-slot.** For each alternative A1, A2, A3, …, render a block with these four parallel slots in this exact order:
   - **Success conditions** — testable propositions with thresholds or observables. No vague abstractions.
   - **Failure conditions** — testable propositions naming what would falsify success.
   - **Uniquely gained** — what this alternative provides that others do not.
   - **Forfeited** — what this alternative costs that others retain.

   The four slots render at parallel depth across all alternatives. Asymmetric depth (one alternative noticeably deeper than others) renders only with explicit reason flagged in section 5.

4. **Cross-alternative comparison.** Choose ONE of three format options based on the choice space (and name the choice):
   - **Strategic 2×2** — when alternatives plot cleanly on two orthogonal criteria. Render as a 2×2 grid with axes named, alternatives positioned in quadrants.
   - **Four-quadrant per-alternative table** — when each alternative's four slots are the structuring grid. Render as a markdown table: alternatives as columns, four slots as rows.
   - **Pro/con tree** — when the choice is genuinely binary. Render as two parallel columns with pros/cons for each side.

   Open the section with: `Format: [chosen format] — reason: [why this format fits this case better].`

5. **Analytical-depth-symmetry note.** One sentence flagging whether alternatives received symmetric depth. When asymmetric, name the reason explicitly: "Asymmetric depth: A3 is shallower because [reason — e.g., low viability, less information available]." Padding to artificial symmetry is the named failure mode; honest asymmetry is preserved.

6. **No-lose elements.** Bulleted list of actions valuable regardless of which alternative is chosen. Each bullet: `[Action] — value: [why valuable]. Applies under: [which alternatives — should be all].` Single-alternative-only items are misclassified gains and do not appear here.

7. **Cross-alternative differentiating factors.** Bulleted list of the dimensions on which alternatives diverge most sharply. Each bullet: `[Differentiating factor]: A1 [position], A2 [position], A3 [position].` These are comparison-level findings, distinct from the per-alternative slots.

8. **Recommendation — conditional.** Empty by default. Render as: `Recommendation: empty (user did not request a final choice — Constraint Mapping maps the terrain, does not decide).` Populate only when the user explicitly asked for a recommendation.

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- Alternative IDs (A1, A2, …) are referenced consistently throughout once introduced.
- The four-slot template in section 3 renders as four bolded sub-headers per alternative, never collapsed into prose paragraphs that lose the parallel structure.
- The format-choice in section 4 is operative — choose one and commit; the deliverable should not carry both a 2×2 grid and a pro/con tree.
- Hard vs soft constraint tags are explicit; do not list constraints without classification.


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

**Prioritize:** `requires`, `enables`, `qualifies`, `supports`, `contradicts`
**Deprioritize:** `analogous-to`, `parent`

*Family: decision-risk. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
