---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-24

---

# MODE: Dialectical Analysis

```yaml
# 0. IDENTITY
mode_id: dialectical-analysis
canonical_name: Dialectical Analysis
suffix_rule: analysis
educational_name: thesis-antithesis dialectical analysis

# 1. TERRITORY AND POSITION
territory: T12-cross-domain-and-knowledge-synthesis
gradation_position:
  axis: stance
  value: thesis-antithesis
adjacent_modes_in_territory:
  - mode_id: synthesis
    relationship: stance counterpart (neutral integrative examination, not adversarial)
  - mode_id: cross-domain-analogical
    relationship: specificity variant (cross-domain analogical, deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "two positions in genuine opposition each with real merit"
    - "compromise feels like cop-out — something genuinely new must emerge"
    - "trapped in what looks like a false dichotomy"
    - "fundamental tension or contradiction in the question itself"
  prompt_shape_signals:
    - "thesis / antithesis"
    - "dialectical"
    - "sublate"
    - "drive through the contradiction"
    - "Hegelian"
disambiguation_routing:
  routes_to_this_mode_when:
    - "drives toward a new position via adversarial commitment to both sides"
    - "willing to hold the antithesis with genuine force, not as token objection"
  routes_away_when:
    - "wants neutral examination of tension without adversarial commitment" → synthesis
    - "wants to choose between alternatives" → constraint-mapping (T3)
    - "wants the strongest version of one position" → steelman-construction (T15)
    - "wants adversarial-actor stress test on a single artifact" → red-team-assessment / red-team-advocate (T15)
when_not_to_invoke:
  - "Positions do not generate each other internally — antithesis would be external critique, not dialectical negation"
  - "User wants integrative connection-mapping rather than adversarial drive" → synthesis

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: adversarial

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [thesis_position, sensed_tension, prior_dialectical_attempts]
    optional: [historical_genealogy, citations_to_dialectical_tradition]
    notes: "Applies when user references the dialectical tradition explicitly (Hegel/Adorno/Marx) or supplies a developed thesis."
  accessible_mode:
    required: [tension_or_opposition_described]
    optional: [user_position_within_tension]
    notes: "Default. Mode infers thesis structure from the user's description of the tension."
  detection:
    expert_signals: ["thesis", "antithesis", "sublation", "Aufheben", "dialectical"]
    accessible_signals: ["seems like a contradiction", "false dichotomy", "tension I can't resolve"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the position you'd start from, and what's the opposing position you sense pulling against it?'"
    on_underspecified: "Ask: 'Is this a tension between two positions each holding real merit, or are you weighing alternatives to choose between? The first invites Dialectical Analysis; the second invites Constraint Mapping.'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Does the antithesis emerge from the thesis's own internal contradictions, or is it external critique?"
    failure_mode_if_unmet: weak-antithesis
  - cq_id: CQ2
    question: "Does the sublation transcend by mechanism, or does it average the two positions?"
    failure_mode_if_unmet: premature-synthesis
  - cq_id: CQ3
    question: "If no genuine sublation is available, has the analysis honored the irreducibility (Adornian escape valve) rather than forcing one?"
    failure_mode_if_unmet: forced-triad
  - cq_id: CQ4
    question: "Have the next-level contradictions the sublation generates been named explicitly?"
    failure_mode_if_unmet: recursion-omission

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: weak-antithesis
    detection_signal: "Antithesis is thesis with minor modifications, not genuine adversarial commitment."
    correction_protocol: re-dispatch (argue antithesis as if believed, emerging from thesis's contradictions)
  - name: premature-synthesis
    detection_signal: "Sublation averages positions ('do a little of both') rather than transcending."
    correction_protocol: re-dispatch (state mechanism by which sublation cancels false aspects while preserving true ones)
  - name: forced-triad
    detection_signal: "Analysis forces a sublation when the contradiction is genuinely irreducible."
    correction_protocol: flag (invoke Adornian escape valve and declare irreducibility)
  - name: teleological-construction
    detection_signal: "Antithesis appears constructed to arrive at a predetermined sublation."
    correction_protocol: re-dispatch (restart antithesis derivation from thesis's contradictions)
  - name: recursion-omission
    detection_signal: "Sublation presented as terminal without naming next-level contradictions it generates."
    correction_protocol: flag (add recursion paragraph)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - hegelian-dialectic-aufheben
  optional:
    - adornian-negative-dialectics (when irreducibility is in play)
    - marxist-historical-materialism (when material conditions structure the tension)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Dialectical Analysis is its own depth target in T12; deeper would shift mode."
  sideways:
    target_mode_id: synthesis
    when: "Positions do not generate each other internally; integrative neutral examination is correct rather than adversarial drive."
  downward:
    target_mode_id: null
    when: "T12 has no lighter sibling currently."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Dialectical Analysis is the strength of the antithesis's adversarial commitment and the genuineness of the sublation's transcendence. A thin pass produces an antithesis as token objection and a sublation as compromise. A substantive pass holds the antithesis with the literal commitment of "argued as if believed" and produces a sublation that names the mechanism by which it cancels what was false in each position while preserving what was true. Test depth by asking: would proponents of the original thesis recognize the antithesis as a serious challenge? Does the sublation generate new contradictions (it should) and have they been named?

## BREADTH ANALYSIS GUIDANCE

Breadth in Dialectical Analysis is the catalog of candidate antitheses considered before settling on the one that emerges most directly from the thesis's internal contradictions. Generate alternatives that arise from different internal contradictions in the thesis. Widen the lens to consider whether the apparent dialectic is in fact a Synthesis problem (positions do not generate each other) or a Constraint Mapping problem (alternatives to choose among). Breadth markers: the analysis tests at least one alternative antithesis derivation before locking the canonical one.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Dialectical Analysis is a thesis-antithesis-sublation drive operating in Hegelian Aufheben vocabulary (cancellation + preservation + elevation — sublation is a mechanism, not a synonym for "synthesis"), with Adornian negative-dialectics held as the counter-tradition for cases where the contradiction is genuinely irreducible. It is distinct from synthesis (neutral integrative examination, not adversarial drive), from constraint-mapping (choosing between alternatives), from steelman-construction (the strongest version of one position rather than triadic motion), and from red-team modes (adversarial stress on one artifact rather than dialectical emergence). The mode's character is to drive through the contradiction by adversarial commitment to both sides, not to neutralize the tension by averaging.

**Procedure.**

1. State the generating question once at the head — the framing question the dialectic addresses.
2. Articulate the thesis in its strongest form, with claims to completeness — not as the foil for an easier antithesis.
3. Surface internal contradictions WITHIN the thesis — tensions the thesis's own commitments produce, named with the specific aspect they target and the mechanism by which the contradiction surfaces.
4. Derive the antithesis from those internal contradictions — derivation-provenance points to specific contradictions; antithesis without that pointer is external critique mislabelled.
5. Argue the antithesis as if believed — a reader unfamiliar with the analyst's position cannot tell which side the analyst started from. Token-objection antitheses fail the commitment test.
6. Test the dialectic's possibilities — can the contradiction be sublated honestly (Aufheben: cancellation + preservation + transcendence mechanism), or is it genuinely irreducible (Adornian standoff)?
7. If sublation: name what is cancelled in thesis and antithesis (with reason), what is preserved from each (with the mechanism by which they coexist). Vocabulary tells: "balance", "middle ground", "drawing from each" are averaging-language and get reshaped.
8. If irreducibility: invoke the Adornian escape valve — name which mechanism for sublation was tested and failed, and what stays unresolved.
9. Resist teleological construction — the antithesis must not appear reverse-engineered to fit a predetermined sublation.
10. Name recursion — when sublation is offered, at least one next-level contradiction it generates; when irreducibility is declared, the forward problems the standoff implies.

**Goal.** Produce a triadic peer-position dialectic with explicit transcending mechanism (or honest irreducibility declaration) — thesis, antithesis, and (if present) sublation rendered as peer positions, never as thesis-with-modifications progression.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — internal derivation (load-bearing).** Does the antithesis emerge from the thesis's own internal contradictions, or is it external critique? Failure mode if unmet: `weak-antithesis`.
- **CQ2 — Aufheben mechanism (load-bearing).** Does the sublation transcend by mechanism (cancellation + preservation), or does it average the two positions? Failure mode if unmet: `premature-synthesis`.
- **CQ3 — Adornian honest standoff (load-bearing).** If no genuine sublation is available, has the analysis honored irreducibility rather than forcing one? Failure mode if unmet: `forced-triad`.
- **CQ4 — recursion named (load-bearing).** Have the next-level contradictions the sublation generates (or the forward problems the standoff implies) been named explicitly? Failure mode if unmet: `recursion-omission`.

A passing output states the thesis in its strongest form, names internal contradictions WITHIN the thesis with structural specificity, develops the antithesis with adversarial commitment from those contradictions, either produces a sublation with explicit cancellation + preservation mechanism or invokes the Adornian escape valve with the failed-mechanism reason, names at least one recursion (forward contradiction or forward problem), and preserves disagreements between streams as parallel atoms rather than silently picking.

**Named failure modes.**

- *weak-antithesis* — antithesis is thesis with minor modifications, not genuine adversarial commitment.
- *premature-synthesis* — sublation averages positions ("do a little of both") rather than transcending.
- *forced-triad* — analysis forces a sublation when the contradiction is genuinely irreducible.
- *teleological-construction* — antithesis appears constructed to arrive at a predetermined sublation.
- *recursion-omission* — sublation presented as terminal without naming next-level contradictions it generates.

## REVISION GUIDANCE

Revise to strengthen the antithesis where it reads as token. Revise to replace averaging language with transcending language in the sublation. Resist revising toward apparent resolution when the contradiction is genuinely irreducible — a forced sublation is worse than an honest standoff. Resist revising toward thesis-favorable framing — the antithesis must be argued with genuine force. If the sublation seems forced, invoke the Adornian escape valve explicitly rather than polishing a false synthesis.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **triadic peer-position atoms with adversarial-commitment provenance and transcending-mechanism atoms**, per Hegelian aufheben methodology. The thesis, antithesis, and (if present) sublation appear as peer positions — never as thesis-with-modifications progression. Internal-contradiction atoms bridge thesis to antithesis; the sublation's mechanism is the load-bearing atom for any non-irreducible dialectic. The atoms are:

1. **Generating-question atom.** The framing question the dialectic addresses, stated once at the corpus head. Cross-stream paraphrase collapses to one statement; if the streams framed the generating question differently, the difference is a real tension (preserve as a question-framing-tension atom rather than picking one).

2. **Thesis atom.** The position with its claims to completeness — the load-bearing dialectical commitment. The thesis is stated in its strongest form, not as the foil for an easier antithesis.

3. **Internal-contradiction atoms.** Tensions WITHIN the thesis that the antithesis exploits. Each carries: the specific aspect of the thesis it targets, and the mechanism by which the contradiction surfaces. These are the bridge atoms; their presence is what distinguishes genuine dialectical emergence from external critique (CQ1).

4. **Antithesis atom.** The adversarial position, with explicit derivation-provenance pointing to one or more internal-contradiction atoms it emerges from. "Argued as if believed" is the posture — the antithesis is stated with genuine commitment, not as token objection. The derivation-provenance atom is load-bearing: without it, the antithesis is external critique (weak-antithesis failure mode).

5. **Sublation atoms — when sublation is present.** The transcending move carries two distinct sub-atoms:
   - **Cancellation atom** — what aspect of the thesis is canceled, what aspect of the antithesis is canceled, and why each is correctly canceled.
   - **Preservation atom** — what aspect of the thesis is preserved, what aspect of the antithesis is preserved, and the mechanism by which they coexist in the sublation.
   A sublation without explicit cancellation + preservation atoms is averaging (premature-synthesis failure mode) and does not survive into the corpus.

6. **Irreducibility declaration — when the Adornian escape valve is invoked.** Replaces the sublation atoms. Carries: explicit statement of why the contradiction is irreducible (which mechanism for sublation was tested and failed), and what stays unresolved (what the dialectic establishes despite producing no synthesis). Forcing a sublation when irreducibility was the honest finding is the forced-triad failure mode; the corpus carries the irreducibility declaration rather than a manufactured sublation.

7. **Recursion atoms.** When sublation is present, at least one recursion atom must survive or CQ4 fails — naming the next-level contradictions the sublation generates. When irreducibility is declared, recursion atoms name the forward problems the standoff implies (what the dialectic still needs to address despite producing no synthesis).

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Thesis-restatement** — both streams may state the thesis in slightly different framings. Single canonical statement survives.
- **Internal-contradiction paraphrase** — same contradiction identified under different framings ("the thesis assumes X while requiring not-X" vs "the thesis depends on X but its premises preclude X"). Single contradiction atom survives.
- **Antithesis-wording variation** — both streams may state the antithesis in different phrasings. The most adversarial-committed version survives (the one that reads as "argued as if believed" rather than as commentary on the thesis).
- **Sublation-averaging language** — phrasings like "a balance of both", "the middle ground", "drawing from each", "combining the insights of...". This is averaging-disguised-as-sublation. If the sublation candidate does not name cancellation + preservation mechanism, it is bloat regardless of phrasing — the corpus carries no sublation atom in that case, and the irreducibility declaration becomes load-bearing.
- **Recursion-acknowledgement restatement** — both streams may state that the sublation generates new contradictions in different framings. Single recursion atom per named next-level contradiction.
- **Meta-dialectical posture restatement** — both streams may include passages defending the dialectical method ("this requires holding both positions seriously", "dialectical thinking requires...", etc.). The posture is implicit in the corpus structure; meta-commentary does not survive.

**What NOT to collapse:**

- **Genuinely different antitheses** — when the two streams produced different antitheses (each emerging from different internal contradictions in the thesis), preserve both with their derivation-provenance atoms. The breadth marker calls for tested alternative antithesis derivations; both surviving is evidence the marker was met, and the choice between them is a finding the dialectic produces.
- **Sublation vs irreducibility disagreement** — when one stream produced a sublation and the other declared irreducibility (Adornian escape valve), preserve both as a tension atom. The dialectic cannot determine which is correct without further work; the consolidator must not silently pick one. The tension atom names: stream A's sublation (with mechanism atoms), stream B's irreducibility declaration (with the failed-mechanism reason), and the structural reason the dialectic is at this fork.
- **Recursion divergence** — different next-level contradictions named by the streams. Preserve all as parallel atoms; the dialectic generates multiple kinds of forward problems and naming them is the corpus's value.

## VERIFICATION CRITERIA

Verified means: thesis stated with claims to completeness; ≥ 1 internal contradiction named; antithesis developed with adversarial commitment from those contradictions; sublation with transcending mechanism OR explicit irreducibility declaration; recursion named when sublation is present. The four critical questions are addressed. Silent forcing of a sublation when irreducibility was the honest finding is a verification failure.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **triadic peer-position dialectic with explicit transcending mechanism (or honest irreducibility declaration)**. Thesis, antithesis, and (if present) sublation appear as peer positions — never as thesis-with-modifications progression. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Generating question.** The framing question the dialectic addresses, stated once at the top. One sentence. When streams framed the generating question differently, render both and name the framing tension explicitly.

2. **Thesis.** The position with its claims to completeness, stated in its strongest form (not as the foil for an easier antithesis). One paragraph or short prose block. Frame as "The thesis, in its strongest form:"

3. **Internal contradictions in the thesis.** Numbered list of tensions WITHIN the thesis that the antithesis will exploit. Each bullet: `[Contradiction name or short phrase] — [specific aspect of thesis it targets] — [mechanism by which the contradiction surfaces].` At minimum one contradiction; these are the bridge atoms.

4. **Antithesis.** The adversarial position, stated with "argued as if believed" commitment. One paragraph. Open with explicit derivation-provenance: "Emerging from internal contradiction(s) [reference]:" — the antithesis must visibly derive from the thesis's own contradictions, not from external critique.

5. **Genuine contradiction or irreducibility.** A single block naming the structural tension between thesis and antithesis at the corpus level. Frame as either "Genuine contradiction:" (when sublation will be attempted in the next section) or "Irreducibility:" (when the Adornian escape valve will be invoked).

6. **Sublation OR irreducibility declaration.** Choose exactly one based on what the corpus established:

   **6a. Sublation (when present).** Render in two named sub-blocks:
   - **Cancellation:** what aspect of the thesis is canceled, what aspect of the antithesis is canceled, why each is correctly canceled.
   - **Preservation:** what aspect of the thesis is preserved, what aspect of the antithesis is preserved, and the mechanism by which they coexist in the sublation.

   The sublation is named explicitly (one to three sentences) followed by the cancellation+preservation sub-blocks. A sublation without explicit cancellation+preservation is averaging and was already cut at step 7 — if it appears here, that's a corpus error to surface.

   **6b. Irreducibility declaration (when sublation is not honest).** Render as: "The Adornian escape valve applies: the contradiction is irreducible because [specific reason — which mechanism for sublation was tested and failed]. What stays unresolved: [what the dialectic establishes despite producing no synthesis]."

7. **Recursion.** When sublation is present, numbered list of next-level contradictions the sublation generates (at minimum one). When irreducibility is declared, numbered list of forward problems the standoff implies. Each bullet: `[Contradiction or problem] — [how it emerges from the sublation/standoff].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- Thesis, antithesis, and sublation receive structurally equivalent rendering (paragraph blocks, not nested under each other). Peer-position visual parity matters.
- When sub-block 6a is in play, the cancellation/preservation pair renders as two named H3 sub-headers OR as bolded inline labels — choose whichever the medium supports cleanly.
- Avoid sublation-averaging vocabulary anywhere in the deliverable: "balance", "middle ground", "drawing from each", "combining the insights" are forbidden phrasings when describing the sublation. If the sublation is honestly transcending, name the mechanism; if it isn't, render 6b instead.

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

**Prioritize:** `extends`, `supersedes`, `derived-from`, `analogous-to`, `supports`
**Deprioritize:** `precedes`, `produces`

*Family: synthesis-dialectic. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
