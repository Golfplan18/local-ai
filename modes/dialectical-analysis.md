---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01

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

## EVALUATION CRITERIA

Dialectical Analysis is read in Hegelian Aufheben vocabulary (cancellation + preservation + elevation — sublation is a mechanism, not a synonym for "synthesis") with Adornian negative-dialectics as the load-bearing counter-tradition for irreducibility cases, and Marxist historical-materialism when material conditions structure the tension. The "argued as if believed" standard governs the antithesis posture. All four critical questions are load-bearing because each protects a distinct part of the methodology: CQ1 (weak-antithesis) protects the dialectical-emergence contract that distinguishes Dialectical Analysis from external critique, CQ2 (premature-synthesis) protects sublation from collapse into averaging, CQ3 (forced-triad) protects the Adornian escape valve against manufactured resolution, CQ4 (recursion-omission) protects against treating sublation as terminal. The unnamed teleological-construction failure mode acts as an additional gate.

Evaluator checks:

1. **Internal-derivation provenance for the antithesis (CQ1, load-bearing).** The antithesis must visibly emerge from contradictions internal to the thesis — not from external critique, not from a position the analyst already held. Weak-antithesis residue is an antithesis that reads as "an alternative view" rather than as "what the thesis itself, taken seriously, generates as its negation." The test: does the antithesis's derivation-provenance atom point to specific internal-contradiction atoms in the thesis? Antithesis without that pointer is external critique mislabelled.

2. **Adversarial commitment, "argued as if believed" (CQ1, continued).** The antithesis must be stated with genuine force — a reader unfamiliar with the analyst's position should be unable to tell which side the analyst started from. Token-objection antitheses fail the commitment test. The reading vocabulary is the steelman discipline applied internally: the antithesis is the strongest version the analyst can construct, including premises the thesis would reject.

3. **Aufheben mechanism on sublation (CQ2, load-bearing).** Where sublation is offered, the deliverable must carry both a cancellation atom (what aspect of thesis is cancelled, what aspect of antithesis is cancelled, and why each is correctly cancelled) and a preservation atom (what is preserved from each, and the mechanism by which the preserved aspects coexist in the sublation). Sublation without explicit cancellation + preservation is premature-synthesis — averaging disguised as transcendence. Vocabulary tells: "a balance of both," "the middle ground," "drawing from each," "combining the insights of" are all averaging-language and are reshaped or downgraded.

4. **Adornian honest standoff (CQ3, load-bearing).** When sublation cannot be achieved honestly, the deliverable must invoke the Adornian escape valve — declare irreducibility, name which mechanism for sublation was tested and failed, and state what stays unresolved. Forcing a sublation when irreducibility was the honest finding is forced-triad — a manufactured resolution that pretends Hegel where Adorno applies. The evaluator confirms the choice between sublation and irreducibility is grounded in what the dialectic actually produced, not in what would be more satisfying.

5. **No teleological construction.** The antithesis must not appear reverse-engineered to fit a predetermined sublation. Teleological-construction residue shows up as antithesis premises that, on inspection, are exactly what the sublation needs to cancel — making the dialectic a stage performance rather than analysis. The evaluator's test: would the antithesis's "argued as if believed" version generate this sublation, or only this exact constructed version?

6. **Recursion named (CQ4).** When sublation is offered, the deliverable must name at least one next-level contradiction the sublation generates — a forward problem the synthesis itself opens. Sublation-as-terminal is recursion-omission; the Hegelian tradition's claim is precisely that aufheben moves dialectical thinking forward by generating new contradictions. When irreducibility is declared (the Adornian path), the recursion section names the forward problems the standoff implies rather than the sublation's generated contradictions.

Confidence applies differently per atom: the antithesis is the riskiest commitment (carries the highest analytic load even when the analyst doesn't share the position); the sublation is the highest-confidence-required claim (averaging slips in here). Where streams disagreed on which is the right antithesis (different internal contradictions in the thesis admit different antitheses), or where one stream produced a sublation and the other declared irreducibility, the evaluator confirms the disagreements are preserved as parallel atoms — the dialectic cannot determine which is correct without further work.

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
