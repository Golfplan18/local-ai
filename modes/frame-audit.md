---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Frame Audit

```yaml
# 0. IDENTITY
mode_id: frame-audit
canonical_name: Frame Audit
suffix_rule: analysis
educational_name: frame audit (Lakoff + Goffman + Entman)

# 1. TERRITORY AND POSITION
territory: T1-argumentative-artifact-examination
gradation_position:
  axis: depth
  value: light
  stance_axis_value: suspending
adjacent_modes_in_territory:
  - mode_id: coherence-audit
    relationship: depth-light + neutral-stance sibling (built Wave 2)
  - mode_id: propaganda-audit
    relationship: specificity-specialized + adversarial-stance sibling (built Wave 2)
  - mode_id: argument-audit
    relationship: depth-molecular sibling (composes coherence + frame + propaganda; Wave 4)
  - mode_id: position-genealogy
    relationship: specificity-sibling (stance-historical; gap-deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "want to see how this artifact frames the issue"
    - "suspect the framing is doing more work than the argument"
    - "the parameters of the debate feel pre-set; want to surface the frame"
    - "want to know what the artifact selects in and selects out"
    - "the metaphors here may be carrying the argument"
  prompt_shape_signals:
    - "frame audit"
    - "framing analysis"
    - "what frame is this using"
    - "what is selected in and selected out"
    - "Lakoff frame"
    - "Goffman frame analysis"
    - "Entman framing functions"
    - "naturalization"
    - "presupposition smuggling"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants frame-surfacing on a single argumentative artifact (one frame, one text)"
    - "user wants stance-suspending analysis: surface the frame without endorsing or attacking it"
    - "user wants Lakoff/Goffman/Entman taxonomies applied (metaphor, primary frame and keying, four frame functions)"
  routes_away_when:
    - "user wants neutral inferential-structure assessment" → coherence-audit
    - "user suspects propaganda specifically and wants Stanley diagnostic" → propaganda-audit
    - "user wants integrated coherence + frame + propaganda synthesis" → argument-audit (Wave 4)
    - "user wants comparison of multiple frames or paradigms" → frame-comparison (T9)
    - "user wants to step outside the artifact's frame to examine the assumptions generating it" → paradigm-suspension (T9)
when_not_to_invoke:
  - "Artifact has no detectable framing structure (raw data, neutral exposition without selection-and-salience choices)" → other territory
  - "User wants comparison across two-or-more paradigms" → frame-comparison (T9)
  - "User wants to evaluate the artifact as a proposal with a defined stance" → T15 modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: suspending

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [argumentative_artifact, focal_question_or_topic]
    optional: [genre_context, source_inventory, suspected_frame_manipulation_techniques, counterframe_candidates]
    notes: "Applies when user supplies the artifact plus the focal topic and optionally the suspected frames in play."
  accessible_mode:
    required: [argumentative_artifact]
    optional: [what_seems_off_about_the_framing, related_artifacts_with_competing_frames]
    notes: "Default. Mode identifies the focal topic from the artifact and surfaces the operative frame(s) without prior specification."
  detection:
    expert_signals: ["Lakoff", "Goffman", "Entman", "frame analysis", "primary framework", "keying", "fabrication", "selection and salience", "problem definition", "causal interpretation", "moral evaluation", "treatment recommendation", "presupposition", "nominalization"]
    accessible_signals: ["how does this frame", "what's selected in", "the framing here", "the metaphors are doing work"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you paste the article, ad, op-ed, or document, and tell me roughly what topic or question you want the framing audit to focus on?'"
    on_underspecified: "Ask: 'Are you noticing something specific about how the issue is being set up, or do you want me to surface whatever frames are operative?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the audit named the operative frame(s) explicitly, in vocabulary that allows comparison with alternative frames, rather than treating the artifact's framing as the natural way to see the issue?"
    failure_mode_if_unmet: frame-naturalization
  - cq_id: CQ2
    question: "Has the analysis applied the four Entman functions (problem definition / causal interpretation / moral evaluation / treatment recommendation) per frame, or has it surfaced the frame without showing what each function is doing?"
    failure_mode_if_unmet: function-collapse
  - cq_id: CQ3
    question: "Has the audit surfaced selection and salience explicitly — what the artifact includes and excludes, what it emphasizes and downplays — given that frames work as much by what they leave silent as by what they assert?"
    failure_mode_if_unmet: silence-blindness
  - cq_id: CQ4
    question: "Has the audit catalogued the linguistic mechanisms (metaphor activation per Lakoff; presupposition, nominalization, passivization, lexicalization choices per CDA) by which the frame travels at the word and grammar level?"
    failure_mode_if_unmet: macro-frame-only-reading
  - cq_id: CQ5
    question: "Has the audit constructed at least one counterframe (what would the issue look like under an alternative frame), to test whether the operative frame is doing analytical work or just describing the topic?"
    failure_mode_if_unmet: counterframe-omission

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: frame-naturalization
    detection_signal: "Audit reads the artifact's framing as 'the way the issue is' rather than naming it as one frame among possible alternatives."
    correction_protocol: re-dispatch
  - name: function-collapse
    detection_signal: "Audit names the operative frame but does not break it into Entman's four functions (problem / cause / moral / treatment)."
    correction_protocol: re-dispatch
  - name: silence-blindness
    detection_signal: "Selection-and-salience inventory is empty or focuses only on what is included; what is excluded or downplayed is not catalogued."
    correction_protocol: re-dispatch
  - name: macro-frame-only-reading
    detection_signal: "Audit identifies a frame at the macro level but does not show the lexical and grammatical mechanisms (metaphors, presuppositions, nominalizations, passivizations) by which the frame travels."
    correction_protocol: re-dispatch
  - name: counterframe-omission
    detection_signal: "Counterframe section is empty or asserts that no alternative frame is available."
    correction_protocol: re-dispatch
  - name: stance-slippage-into-attack
    detection_signal: "Audit slides from frame-surfacing into frame-rejection, asserting the operative frame is wrong rather than naming what it does and what it costs."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - lakoff-conceptual-metaphor
    - goffman-frame-analysis
    - entman-framing-functions
  optional:
    - cda-fairclough-presupposition-and-nominalization (when grammatical-syntactic mechanisms are central)
    - iyengar-episodic-thematic (when policy framing and attribution-of-responsibility are in scope)
    - chong-druckman-emphasis-equivalence (when frame strength, frequency, competition are at stake)
    - snow-benford-frame-alignment (when the artifact is a contribution to a campaign-level alignment process)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: argument-audit
    when: "Audit reveals coherence problems and propaganda mechanisms beyond frame-surfacing; molecular synthesis is needed (Wave 4)."
  sideways:
    target_mode_id: frame-comparison
    when: "On reflection there are two-or-more frames in play across multiple artifacts; comparison across frames is the right operation (T9)."
  downward:
    target_mode_id: null
    when: "Frame Audit is already the lightest atomic mode in T1 for frame-surfacing."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Frame Audit is the precision with which (1) the operative frame is named in alternative-comparable vocabulary (not in the artifact's own naturalized terms), (2) the four Entman functions are populated per frame (problem definition, causal interpretation, moral evaluation, treatment recommendation), (3) the linguistic mechanisms (Lakoff metaphors, CDA presuppositions and nominalizations) are inventoried with quoted text, and (4) at least one counterframe is constructed to make the operative frame visible as a frame. A thin pass paraphrases the artifact's framing in its own terms; a substantive pass extracts the frame to a level of generality where alternative frames become thinkable, then shows what the frame selects in, selects out, and naturalizes. Test depth by asking: would a defender of the operative frame recognize the audit as accurate, while a defender of an alternative frame find new analytical purchase from it?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning all seven framing-tradition layers before narrowing: cognitive linguistic (Lakoff — lexical activation, metaphor); sociological (Goffman — primary frameworks, keyings, fabrications); media studies (Entman — selection, salience, four functions; Gitlin — institutional routinization; Tuchman — news-net constitutive activity); CDA (Fairclough, van Dijk, Wodak — presupposition, nominalization, passivization, ideological square, intertextuality); propaganda analysis (Bernays, Ellul, Herman/Chomsky, Stanley — strategic deployment, institutional incentives, not-at-issue content); political communication (Iyengar — episodic/thematic; Chong/Druckman — emphasis/equivalence); social-movement framing (Snow/Benford — diagnostic/prognostic/motivational; alignment processes). Breadth markers: the audit has surveyed at least four of these layers before producing findings.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Frame Audit is a stance-suspending frame-surfacing analysis on a single argumentative artifact — operating in Lakoff conceptual-metaphor, Goffman primary-frameworks-and-keyings, and Entman four-functions (problem definition / causal interpretation / moral evaluation / treatment recommendation) vocabularies, with CDA mechanisms (presupposition, nominalisation, passivisation, lexicalisation) inventoried where they appear. It is distinct from coherence-audit (which checks internal inferential structure neutrally), from propaganda-audit (which is adversarial-stance Stanley-influenced), from argument-audit (the depth-molecular sibling that composes coherence + frame), from frame-comparison (which compares multiple frames across artifacts), and from paradigm-suspension (which questions the framework holding the concept). The mode's posture is suspending — surface what the frame does and what it costs, without rejecting it.

**Procedure.**

1. Identify the operative frame(s) — name each in vocabulary that travels across alternative frames (e.g., `markets-as-rational-actors`, `nation-as-family`), not in the artifact's own naturalised terms.
2. Surface the focal topic the audit centers on.
3. Inventory Lakoff metaphors — each carries quoted text, source-domain → target-domain mapping, and the inferential entailments the mapping smuggles in.
4. Apply Goffman primary-framework analysis — natural / social, any keying (make-believe / contests / ceremonials / technical-redoings / regroundings), fabrication flag if present.
5. Populate Entman four functions per frame — problem definition, causal interpretation, moral evaluation, treatment recommendation — each with quoted evidence.
6. Inventory selection AND silence — both what the artifact includes/emphasises AND what it excludes/downplays. Frames live in their silences.
7. Catalogue lexical-grammatical mechanisms — presupposition, nominalisation, passivisation, lexicalisation choices — with quoted text and the framing work each does.
8. Construct at least one counterframe — what the issue would look like under an alternative frame, with the four Entman functions briefly re-populated under it.
9. Hold the stance-suspending posture — do not slip from frame-surfacing into frame-rejection. (If adversarial reading is wanted, route to propaganda-audit or the red-team modes.)
10. Calibrate confidence per major claim with quoted-text or lens-application grounding.

**Goal.** Produce a frame audit — a stance-suspending analysis that names operative frames in alternative-comparable vocabulary, populates Entman's four functions with quoted evidence, inventories selection and silence, cites the lexical-grammatical mechanisms by which the frame travels, and sketches at least one counterframe.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — frame named in alternative-comparable vocabulary.** Has the operative frame been named in vocabulary that allows comparison with alternative frames, rather than treating the artifact's framing as the natural way to see the issue? Failure mode if unmet: `frame-naturalization`.
- **CQ2 — Entman four functions populated.** Has the analysis applied the four functions (problem / cause / moral / treatment) per frame with quoted evidence? Failure mode if unmet: `function-collapse`.
- **CQ3 — selection and silence both catalogued.** Has the audit surfaced what the artifact excludes and downplays as well as what it includes and emphasises? Failure mode if unmet: `silence-blindness`.
- **CQ4 — lexical-grammatical mechanisms inventoried.** Has the audit catalogued the metaphors, presuppositions, nominalisations, and lexicalisation choices by which the frame travels at the word and grammar level? Failure mode if unmet: `macro-frame-only-reading`.
- **CQ5 — counterframe constructed.** Has at least one counterframe been sketched to make the operative frame visible as a frame? Failure mode if unmet: `counterframe-omission`.

A passing output names operative frames in alternative-comparable vocabulary, populates Entman's four functions per frame with quoted evidence, inventories both inclusions and silences, cites lexical-grammatical mechanisms with quoted text, constructs at least one counterframe, holds the stance-suspending posture without slipping into frame-rejection, and carries per-finding confidence.

**Named failure modes.**

- *frame-naturalization* — audit reads the artifact's framing as "the way the issue is" rather than as one frame among possible alternatives.
- *function-collapse* — audit names the operative frame but does not break it into Entman's four functions.
- *silence-blindness* — selection-and-salience inventory focuses only on what is included; what is excluded or downplayed is not catalogued.
- *macro-frame-only-reading* — audit identifies a frame at the macro level but does not show the lexical and grammatical mechanisms by which the frame travels.
- *counterframe-omission* — counterframe section is empty or asserts that no alternative frame is available.
- *stance-slippage-into-attack* — audit slides from frame-surfacing into frame-rejection, asserting the operative frame is wrong rather than naming what it does and what it costs.

## REVISION GUIDANCE

Revise to extract the frame to alternative-comparable vocabulary where the draft has restated the artifact's framing in its own terms. Revise to populate Entman's four functions per frame where the draft has named the frame without showing its work. Revise to add the silence inventory where selection-and-salience reads only inclusions. Revise to add lexical-grammatical mechanisms where the draft operates only at the macro-frame level. Revise to construct the counterframe where it is missing. Resist revising toward attack on the frame — the mode is stance-suspending; surfacing the frame and showing its costs is the analytical character, but rejecting the frame belongs in propaganda-audit (if propaganda is suspected) or in the red-team modes (if the artifact is being evaluated as a proposal).

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a stance-suspending frame audit: operative frames named in alternative-comparable vocabulary, Lakoff metaphor atoms with source→target inferential mappings, Goffman primary-framework and keying atoms, Entman four-function atoms per frame, selection-and-silence inventory, presupposition/nominalization atoms with quoted text, and counterframe construction**. The atoms are:

1. **Operative-frame atoms.** Each atom names one frame operative in the artifact, characterised in vocabulary that travels across alternative frames (i.e., not the artifact's own naturalised terms). Frame-naturalization is the named failure mode the consolidator watches for; atoms that restate the artifact's framing in the artifact's vocabulary get reshaped to alternative-comparable vocabulary.

2. **Lakoff-metaphor atoms.** Each atom carries: quoted text from the artifact, the source-domain → target-domain mapping the metaphor activates, and the inferential entailments the mapping smuggles in (what reasoning the metaphor licenses, what reasoning it makes harder).

3. **Goffman-frame atoms.** Each atom carries: the primary framework (natural / social), the keying applied (make-believe / contests / ceremonials / technical-redoings / regroundings) if any, and any fabrication flag.

4. **Entman four-function atoms — per frame.** Each frame carries four sub-atoms: problem definition, causal interpretation, moral evaluation, treatment recommendation. Each sub-atom carries quoted evidence from the artifact. Function-collapse is the named failure mode; frames named without populated four-function atoms get reshaped.

5. **Selection-and-salience atoms.** Two paired sub-inventories: what the artifact *includes and emphasises*, and what it *excludes or downplays*. Silence-blindness is the named failure mode; inventories with empty exclusion columns get reshaped — frames work as much by silence as by speech.

6. **Lexical-and-grammatical-mechanism atoms.** Each atom names one mechanism (presupposition, nominalisation, passivisation, lexicalisation choice) with quoted text and the framing work the mechanism does. Macro-frame-only-reading is the named failure mode; audits that operate only at macro-frame level without showing how the frame travels at the word and grammar level get reshaped.

7. **Counterframe atom.** A one-paragraph sketch of what the issue would look like under at least one alternative frame — what would change in problem definition, causal interpretation, moral evaluation, treatment recommendation. Counterframe-omission is the named failure mode; audits that assert no alternative is available get reshaped to surface at least one.

8. **Stance-discipline flag — when applicable.** Where streams slipped from frame-surfacing into frame-rejection (asserting the operative frame is wrong rather than showing what it does and what it costs), the slippage is flagged. Stance-slippage-into-attack is the named failure mode; the mode's posture is suspending, not adversarial. (If adversarial reading is wanted, propaganda-audit or the red-team modes are the right sideways-routes.)

9. **Confidence per finding.** Each major claim carries a confidence with grounding (quoted-text evidence, structural inference, lens-application).

**Mode-specific bloat patterns to cut:**

- **Frame-naturalization** — the artifact's framing restated in the artifact's own vocabulary, as if it were the natural way to see the issue.
- **Function-collapse** — frame named without Entman's four functions populated; the frame's *work* is invisible.
- **Inclusion-only inventory** — what's left in is catalogued; what's left out and what's downplayed is not. Frames live in their silences.
- **Macro-frame-only reading** — the operative frame named at high abstraction without showing the lexical-grammatical mechanisms (metaphor activation, presupposition smuggling, nominalisation hiding agency) by which it travels.
- **Counterframe-omission** — empty counterframe section, or asserting no alternative exists.
- **Stance-slippage** — frame-surfacing tipping into frame-rejection; the mode is suspending, not adversarial.
- **Lens-citation without text** — Lakoff/Goffman/Entman vocabulary deployed without quoted artifact evidence to ground it.

**What NOT to collapse:**

- **Multiple operative frames** — when streams surfaced different operative frames (or different primary frames in a multi-frame artifact), all survive as their own atoms with their respective four-function populations.
- **Stream disagreement about what's in vs out** — when streams diverged on which elements were emphasised vs downplayed, the disagreement reveals what's genuinely contested about the artifact's selection structure.
- **Counterframe multiplicity** — when streams constructed different counterframes, both survive; the choice of counterframe is itself a finding about what alternatives the analytical horizon contains.
- **Lakoff vs Goffman primacy** — when one stream foregrounded metaphor activation and another foregrounded primary-framework keying, both readings survive; the layers operate at different scales.

## VERIFICATION CRITERIA

Verified means: operative frames are named in alternative-comparable vocabulary; the four Entman functions are populated per frame with quoted evidence; the selection-and-silence inventory has entries in both columns; lexical and grammatical mechanisms are cited with quoted text; at least one counterframe is constructed; the audit has not slipped from frame-surfacing into frame-rejection. The five critical questions are addressable from the output. Confidence per finding accompanies each major claim.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **frame audit** — a stance-suspending analysis that names operative frames in alternative-comparable vocabulary, populates Entman's four functions with quoted evidence, inventories selection and silence, cites the lexical-grammatical mechanisms by which the frame travels, and sketches at least one counterframe. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Operative frames named.** Bulleted list. Each: `**[Frame name]** — one-sentence characterisation in alternative-comparable vocabulary. Where it surfaces in the artifact: [brief location pointer].` Frame names use vocabulary that travels (e.g., `markets-as-rational-actors`, `nation-as-family`); not the artifact's own naturalised terms.

2. **Lakoff metaphor inventory.** Bulleted list. Each: `**[Source → target metaphor]** — quoted text: "..." Inferential entailments: [what reasoning this licenses; what it makes harder].`

3. **Goffman primary framework and keyings.** One paragraph. Identifies the primary framework (natural / social), any keying applied (make-believe / contests / ceremonials / technical-redoings / regroundings), and fabrication flag if applicable.

4. **Entman four functions per frame.** Per frame, four labelled sub-blocks:
   - `**Problem definition:** [what the frame names as the problem]. Quoted text: "..."`
   - `**Causal interpretation:** [what the frame attributes causation to]. Quoted text: "..."`
   - `**Moral evaluation:** [what the frame casts as good / bad / acceptable]. Quoted text: "..."`
   - `**Treatment recommendation:** [what the frame proposes as the response]. Quoted text: "..."`

5. **Selection and salience inventory.** A two-column table or paired bulleted lists:
   - `**Included and emphasised:** [what the artifact foregrounds].`
   - `**Excluded or downplayed:** [what the artifact omits or backgrounds].`
   
   Both columns are populated; an empty exclusion column gets reshaped at this layer.

6. **Presupposition and nominalisation audit.** Bulleted list. Each: `**[Mechanism — presupposition / nominalisation / passivisation / lexicalisation]** — quoted text: "..." Framing work it does: [what the mechanism makes invisible, naturalises, or smuggles].`

7. **Counterframe — what an alternative frame would look like.** One paragraph sketching the alternative reading, with the four Entman functions briefly re-populated under the counterframe to show what would shift.

8. **Confidence per finding.** Bulleted list of confidence assessments per major claim, with grounding.

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- The mode's stance is suspending — the deliverable surfaces what the frame does and what it costs, without rejecting it. Stance-slippage into rejection is reshaped at this layer; if the adversarial reading is what's wanted, the deliverable surfaces a sideways-route note (`**If frame-rejection rather than frame-surfacing is the operative question, propaganda-audit or red-team-assessment is the appropriate sideways-route.**`).
- Quoted text appears throughout — Lakoff metaphors, Entman functions, lexical-grammatical mechanisms all cite the artifact's words. Macro-level claims without textual grounding get reshaped.
- The counterframe (section 7) is a one-paragraph sketch with the four Entman functions briefly re-populated under it, not a full second audit; it exists to make the operative frame visible *as* a frame.
- When multiple operative frames survived consolidation, sections 4 and 7 render each frame as its own labelled sub-block; the deliverable does not collapse to a single dominant frame unless one stream uniquely identified one.
- When streams disagreed on selection-vs-silence cells, the disagreement renders in section 5 as `**Contested:** [item] — stream A: included and emphasised; stream B: downplayed. [What this contest reveals about the artifact's framing structure].`


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
