---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Frame Comparison

```yaml
# 0. IDENTITY
mode_id: frame-comparison
canonical_name: Frame Comparison
suffix_rule: analysis
educational_name: frame comparison (Lakoff strict-father vs. nurturant-parent and other frames)

# 1. TERRITORY AND POSITION
territory: T9-paradigm-and-assumption-examination
gradation_position:
  axis: stance
  value: comparing
adjacent_modes_in_territory:
  - mode_id: paradigm-suspension
    relationship: stance-counterpart (suspending — single-frame surfacing without comparison)
  - mode_id: worldview-cartography
    relationship: depth-molecular sibling (built Wave 4)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "two camps are talking past each other"
    - "I want to see what each side is assuming about the same situation"
    - "the disagreement isn't about facts, it's about how we frame the issue"
    - "I want to understand both worldviews on their own terms"
  prompt_shape_signals:
    - "frame comparison"
    - "compare the framings"
    - "Lakoff"
    - "strict father vs nurturant parent"
    - "conceptual metaphor"
    - "competing frames"
    - "how each side sees this"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user has named (or implies) ≥2 frames or worldviews to compare"
    - "user wants each frame articulated on its own terms before any cross-frame evaluation"
    - "the analytical object is the frames themselves, not which frame is correct"
  routes_away_when:
    - "user wants to surface the implicit frame of a single artifact" → paradigm-suspension or T1 frame-audit
    - "user wants integrated cartography across many worldviews" → worldview-cartography
    - "user wants to evaluate which frame is more sound" → T1 modes (frame as embedded in argument)
    - "user wants synthesis across the frames" → T12 synthesis
when_not_to_invoke:
  - "Disagreement is about empirical facts within a shared frame — frames are not in dispute" → T5 hypothesis evaluation
  - "Only one frame is in play (no comparison object)" → paradigm-suspension
  - "User wants to negotiate between parties holding the frames" → T13 negotiation modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [frame_inventory, comparison_axis, situation_or_issue]
    optional: [frame_typology_reference, prior_frame_analyses, conceptual_metaphor_seeds]
    notes: "Applies when user supplies named frames (e.g., 'strict-father vs. nurturant-parent', 'systemic vs. individual', 'market vs. commons') or a frame typology to apply."
  accessible_mode:
    required: [issue_or_disagreement, two_or_more_perspectives_to_compare]
    optional: [why_user_wants_comparison, named_camps_or_voices]
    notes: "Default. Mode infers frames from descriptions of the perspectives or camps."
  detection:
    expert_signals: ["frame typology", "Lakoff", "conceptual metaphor", "strict-father", "nurturant-parent", "narrative frames"]
    accessible_signals: ["how each side sees", "compare the framings", "two camps", "talking past each other"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the issue, and what are the perspectives or camps you want to compare?'"
    on_underspecified: "Ask: 'Could you describe how each camp talks about the issue, in their own words if possible?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has each frame been articulated on its own terms (steelman-mode within the frame), or has the analyst's preferred frame received fuller articulation than the others?"
    failure_mode_if_unmet: asymmetric-articulation
  - cq_id: CQ2
    question: "Have the core conceptual metaphors of each frame been surfaced (Lakoff-style), or has the analysis stayed at the level of stated positions without descending to the metaphors that structure the positions?"
    failure_mode_if_unmet: surface-position-only
  - cq_id: CQ3
    question: "Has the analysis surfaced what each frame *obscures* as well as what it makes visible, or has it presented each frame as if the frame had no blind spots?"
    failure_mode_if_unmet: blind-spot-omission
  - cq_id: CQ4
    question: "Has irreducibility been honored — i.e., has the analysis resisted the temptation to translate one frame into the other's vocabulary, when such translation distorts?"
    failure_mode_if_unmet: false-translation

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: asymmetric-articulation
    detection_signal: "One frame's section is substantially longer, more nuanced, or more sympathetic than the others'."
    correction_protocol: re-dispatch
  - name: surface-position-only
    detection_signal: "Frames are described in terms of stated positions and policy preferences without surfacing the underlying conceptual metaphors that structure them."
    correction_protocol: re-dispatch
  - name: blind-spot-omission
    detection_signal: "What-each-frame-obscures section is empty, thin, or applied only to the analyst's non-preferred frame."
    correction_protocol: flag
  - name: false-translation
    detection_signal: "Cross-frame translation is presented as smooth when residual-irreducibility is more honest; or one frame's vocabulary is used to describe the other's commitments."
    correction_protocol: flag
  - name: typology-imposition
    detection_signal: "Lakoff's strict-father / nurturant-parent (or other named typology) is applied to a domain where it does not naturally fit, distorting the actual frames in play."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - lakoff-conceptual-metaphor
  optional:
    - lakoff-strict-father-nurturant-parent (when political-moral framings are in play)
    - schon-rein-frame-reflection (when policy frames are in play)
    - benford-snow-collective-action-frames (when movement frames are in play)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: worldview-cartography
    when: "More than three frames are in play, or frames need to be situated in a larger cartography of worldviews."
  sideways:
    target_mode_id: paradigm-suspension
    when: "On reflection only one frame is the analytical object; comparison was not the right move."
  downward:
    target_mode_id: paradigm-suspension
    when: "User wants single-frame surfacing rather than cross-frame comparison."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Frame Comparison is the descent from stated positions to the conceptual metaphors and moral commitments that structure them. A thin pass restates each side's position; a substantive pass surfaces the core metaphor each frame deploys (e.g., nation-as-family with strict father vs. nurturant parent; market-as-natural-system vs. market-as-human-construction; disease-as-invader vs. disease-as-imbalance), names the moral commitments the metaphor entails, articulates what each frame makes visible and what it obscures, and honors residual irreducibility where translation distorts. Test depth by asking: could a partisan of each frame recognize their own view in the analysis as a steelmanned articulation, not as the opposing camp's caricature?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means surveying the frame typologies that might apply (Lakoff's family-based moral frames, Schön-Rein policy frames, collective-action frames, narrative frames, frame-of-justice variants), considering whether the named frames exhaust the live alternatives or whether unnamed frames are also in play (a third or fourth perspective excluded from the comparison), and scanning for hybrid or emerging frames that don't fit either pole cleanly. Breadth markers: at least three frame-typology candidates are considered before locking the comparison axis; the possibility of frames-not-yet-named is acknowledged.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Frame Comparison is a symmetric multi-frame mapping — articulating two or more frames each on its own terms (steelman-discipline within each frame), descending to the conceptual metaphors that structure each, surfacing what each makes visible and what each obscures, and honoring residual irreducibility where one frame's commitments cannot be cashed out in another's vocabulary without loss. It is distinct from paradigm-suspension (stance-counterpart: single-frame surfacing without comparison), from worldview-cartography (depth-molecular sibling integrating many worldviews), from frame-audit (single-artifact frame-surfacing in T1), and from T12 synthesis (which integrates frames rather than comparing them). The mode's posture is comparing, not integrating — when integration is wanted, route to T12.

**Procedure.**

1. Identify the frames in play (2 or more) — name each in the frame's own preferred or neutral vocabulary, not in the rival camp's caricature.
2. Articulate each frame symmetrically — steelmanned one-paragraph treatment per frame, with parallel internal structure across all frames. Asymmetric articulation is the named failure mode.
3. Anchor each to a typology where one applies — Lakoff strict-father / nurturant-parent for moral-political; Schön-Rein for policy frames; Snow-Benford for collective-action frames. Note when typology-imposition risk is high (the typology doesn't naturally fit the domain).
4. Descend to core conceptual metaphors per frame — source-domain → target-domain mapping with inferential entailments the metaphor licenses.
5. Name moral and value commitments that flow from the core metaphor of each frame.
6. Surface what each frame makes visible — what it foregrounds, enables, gives analytical purchase on.
7. Surface what each frame obscures — what it backgrounds, makes harder to see, cannot represent. Every frame has blind spots, including the analyst's preferred one.
8. Catalogue cross-frame translation attempts — concept from frame A, attempted translation into frame B's vocabulary, whether the translation works or distorts.
9. Honor residual irreducibility — where one frame's commitment cannot be cashed out in another's vocabulary without loss, name the loss and why the irreducibility matters.
10. Flag frames-not-yet-named when a third or fourth perspective doesn't fit either pole cleanly.

**Goal.** Produce a frame comparison mapping — a symmetric articulation of two or more frames on their own terms, with descent to conceptual metaphor, parallel blind-spot surfacing, and explicit residual irreducibility.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — symmetric articulation.** Has each frame been articulated on its own terms with equal rigor, or has the analyst's preferred frame received fuller articulation than the others? Failure mode if unmet: `asymmetric-articulation`.
- **CQ2 — descent to conceptual metaphor.** Have the core conceptual metaphors of each frame been surfaced, or has the analysis stayed at the level of stated positions? Failure mode if unmet: `surface-position-only`.
- **CQ3 — blind-spot surfacing.** Has the analysis surfaced what each frame obscures as well as what it makes visible — for every frame, including the analyst's preferred one? Failure mode if unmet: `blind-spot-omission`.
- **CQ4 — irreducibility honored.** Has the analysis resisted false translation between frames where such translation distorts? Failure mode if unmet: `false-translation`.

A passing output articulates each frame symmetrically in the frame's own vocabulary, names core conceptual metaphors with their inferential entailments, names moral/value commitments per frame, surfaces what each makes visible AND what each obscures, catalogues cross-frame translation difficulty, honors residual irreducibility explicitly, and resists synthesis drift (synthesis routes to T12).

**Named failure modes.**

- *asymmetric-articulation* — one frame's section is substantially longer, more nuanced, or more sympathetic than the others'.
- *surface-position-only* — frames described in stated positions and policy preferences without surfacing the underlying conceptual metaphors.
- *blind-spot-omission* — what-each-frame-obscures is empty, thin, or applied only to the analyst's non-preferred frame.
- *false-translation* — cross-frame translation presented as smooth when residual irreducibility is more honest; one frame's vocabulary used to describe the other's commitments.
- *typology-imposition* — named typology applied to a domain where it doesn't naturally fit, distorting the actual frames in play.

## REVISION GUIDANCE

Revise to balance asymmetric articulation where one frame received fuller treatment. Revise to descend to conceptual metaphor where the draft stayed at stated positions. Revise to add blind-spot surfacing per frame where the draft presented frames as if blind-spot-free. Resist revising toward synthesis — the mode's analytical character is comparing, not integrating. If integration is wanted, escalate to T12 synthesis rather than collapsing irreducibility within this mode.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a symmetric multi-frame mapping: each frame articulated on its own terms with parallel internal structure (description, core metaphor, moral commitments, visibilities, obscurings), cross-frame translation atoms, and explicit residual-irreducibility atoms where one frame's commitments cannot be cashed out in another's vocabulary without loss**. The atoms are:

1. **Frame-description atoms — one per frame.** Each atom carries: the frame's name (in the frame's own preferred or neutral vocabulary, not the rival camp's caricature), a steelmanned one-paragraph articulation, and the typological label if one applies (Lakoff strict-father / nurturant-parent; Schön-Rein policy frame; collective-action diagnostic/prognostic/motivational; etc.). Asymmetric-articulation is the named failure mode the consolidator watches for; frames where one atom is substantially longer, more nuanced, or more sympathetic than its sibling get reshaped to symmetric depth.

2. **Core-metaphor atoms — one per frame.** Each atom names the conceptual metaphor that structures the frame (nation-as-family, market-as-natural-system, disease-as-invader, etc.), the source-domain → target-domain mapping, and the inferential entailments the metaphor licenses. Surface-position-only is the named failure mode; frames described in terms of stated positions and policy preferences without descent to structuring metaphor get reshaped.

3. **Moral/value-commitment atoms — per frame.** Each atom names the moral or value commitments that flow from the core metaphor: what each frame casts as good, what as bad, what as necessary, what as forbidden.

4. **What-each-frame-makes-visible atoms — per frame.** What the frame surfaces, foregrounds, enables the analyst to see — its analytical purchase.

5. **What-each-frame-obscures atoms — per frame.** What the frame's blind spots are — what it makes harder to see, what it backgrounds, what it cannot represent. Blind-spot-omission is the named failure mode; frames where the obscures-section is empty, thin, or applied only to the analyst's non-preferred frame get reshaped. The corpus standard is that every frame has blind spots, including the analyst's preferred one.

6. **Cross-frame translation atoms.** Each atom names: a concept or commitment from frame A, the attempted translation into frame B's vocabulary, and whether the translation works smoothly or distorts. False-translation is the named failure mode; smooth-translation claims where translation actually distorts get reshaped.

7. **Residual-irreducibility atoms.** Each atom names a place where one frame's commitment cannot be cashed out in another's vocabulary without loss — what is lost in translation, why the irreducibility matters. The corpus does not smooth over irreducibility; preserving it is the mode's analytical character.

8. **Typology-imposition flag — when applicable.** When a named typology (Lakoff strict-father/nurturant-parent; Schön-Rein; etc.) has been applied to a domain where it does not naturally fit and is distorting the actual frames in play, the flag is preserved. Typology-imposition is the named failure mode.

9. **Frames-not-yet-named flag — when applicable.** When the breadth pass surfaced a third or fourth perspective that doesn't fit either pole cleanly (hybrid or emerging frames, frames excluded from the comparison), the flag survives so the comparison is not falsely closed.

10. **Confidence per finding.** Each major claim carries a confidence with grounding.

**Mode-specific bloat patterns to cut:**

- **Asymmetric articulation** — one frame receives fuller, more nuanced, or more sympathetic treatment than its sibling.
- **Surface-position-only** — frames described in stated positions and policy preferences without descent to the metaphors that structure those positions.
- **One-sided blind-spot surfacing** — blind spots catalogued only for the analyst's non-preferred frame.
- **Smooth translation that distorts** — cross-frame translation presented as cleaner than it is, with the residual loss hidden.
- **Typology imposition** — a named typology applied to a domain where it does not naturally fit; the actual frames in play get distorted to match the typology.
- **Synthesis drift** — the comparison tipping into integration. The mode's analytical character is comparing, not integrating. (If integration is wanted, T12 synthesis is the right escalation, not collapsing irreducibility within this mode.)
- **Caricature framings** — a frame articulated in the rival camp's vocabulary rather than on its own terms; the steelman discipline is broken.

**What NOT to collapse:**

- **Residual irreducibility itself** — places where frame A's commitment cannot be cashed out in frame B's vocabulary without loss are themselves load-bearing findings, never smoothed over.
- **Disagreement about which typology applies** — when streams applied different frame typologies (Lakoff vs. Schön-Rein vs. Snow-Benford), both readings survive with their respective analytical purchase.
- **Multiple operative metaphors per frame** — frames sometimes rest on more than one structuring metaphor; the corpus preserves the multiplicity rather than picking one.
- **Stream disagreement about what's visible vs obscured** — when streams diverged on whether a particular consideration is foregrounded or backgrounded by a frame, the disagreement is the finding.

## VERIFICATION CRITERIA

Verified means: each frame is articulated symmetrically; core conceptual metaphors per frame are surfaced; moral/value commitments per frame are named; what-each-frame-makes-visible and what-it-obscures are both populated; cross-frame translation difficulty is acknowledged; residual irreducibility is honored where present; the four critical questions are addressable from the output. Confidence per major finding accompanies each claim.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **frame comparison mapping** — a symmetric articulation of two or more frames on their own terms, with descent to conceptual metaphor, parallel blind-spot surfacing, and explicit residual irreducibility. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Frames named and described.** Per frame, one labelled sub-block. Each: `**[Frame name]:** [steelmanned one-paragraph articulation in the frame's own preferred vocabulary]. Typological anchor: [Lakoff strict-father / nurturant-parent / Schön-Rein / Snow-Benford / other, with brief rationale].` Symmetric depth across sub-blocks; asymmetric articulation is reshaped at this layer.

2. **Core metaphors per frame.** Per frame, one labelled sub-block. Each: `**[Frame]** — core metaphor: [source → target]. Inferential entailments: [what reasoning this metaphor licenses; what it makes harder].`

3. **Moral / value commitments per frame.** Per frame, one labelled sub-block listing the commitments that flow from the core metaphor.

4. **What each frame makes visible.** Per frame, one sub-block: `**[Frame]:** [what it foregrounds, enables, gives analytical purchase on].`

5. **What each frame obscures.** Per frame, one sub-block: `**[Frame]:** [what it backgrounds, makes harder to see, cannot represent].` Every frame's obscurings appear — including the analyst's preferred frame.

6. **Cross-frame translation difficulty.** Bulleted list. Each: `**[Concept from frame A]** ↔ **[attempted translation in frame B]** — translation [works smoothly / partially / distorts]. What is lost: [...].`

7. **Residual irreducibility.** Bulleted list. Each: `**[Frame A commitment]** — cannot be cashed out in frame B's vocabulary without loss because [reason]. What this means for cross-frame dialogue: [...].` This section is never collapsed or minimised; preserving irreducibility is the mode's analytical character.

8. **Confidence per finding.** Bulleted list of confidence assessments per major claim, with grounding.

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- Each frame's sub-blocks appear in the same order across sections; the structural parallelism is what surfaces asymmetric articulation if any.
- Frames are named in their own (or neutral) vocabulary, not the rival camp's caricature. Caricature naming is reshaped at this layer.
- The mode's posture is comparing, not integrating. When the corpus reads as if heading toward synthesis, the deliverable surfaces a `**Note: integration is not this mode's operation; if synthesis across the frames is what's wanted, the appropriate escalation is to T12 synthesis.**` block rather than allowing the comparison to collapse into a unified position.
- When a typology-imposition flag survived consolidation, the deliverable opens (before section 1) with: `**Note: the named typology applied to this comparison may not naturally fit the actual frames in play. The articulation below honors the actual frames; the typological labels are provisional.**`
- When frames-not-yet-named were flagged, section 1 closes with `**Frames not represented in this comparison:** [...] — [why they may also be in play, what the comparison would gain from including them].`
- Residual irreducibility (section 7) is never described as a flaw to be resolved; it is the analytical finding that justifies the comparing-stance over false synthesis.


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

**Prioritize:** `contradicts`, `qualifies`, `analogous-to`, `extends`, `supersedes`
**Deprioritize:** `precedes`, `produces`

*Family: frame-paradigm. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
