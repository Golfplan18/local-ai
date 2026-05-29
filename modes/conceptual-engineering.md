---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Conceptual Engineering

```yaml
# 0. IDENTITY
mode_id: conceptual-engineering
canonical_name: Conceptual Engineering
suffix_rule: analysis
educational_name: conceptual engineering (Cappelen-Plunkett ameliorative analysis)

# 1. TERRITORY AND POSITION
territory: T10-conceptual-clarification
gradation_position:
  axis: stance
  value: ameliorative
adjacent_modes_in_territory:
  - mode_id: deep-clarification
    relationship: stance-counterpart (descriptive ordinary-language clarification)
  - mode_id: definitional-dispute
    relationship: specificity-counterpart (essentially-contested concepts; gap-deferred)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "the current definition of this concept isn't doing the work it should"
    - "I want to redesign what this term means for our purposes"
    - "the inherited concept is causing problems and we should engineer a better one"
    - "the word is being used in incompatible ways and we need to choose"
  prompt_shape_signals:
    - "conceptual engineering"
    - "ameliorative analysis"
    - "redefine"
    - "engineer the concept"
    - "Cappelen"
    - "Haslanger"
    - "should the concept be"
    - "what should X mean"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants normative redesign of a concept rather than descriptive clarification of current usage"
    - "user accepts that the concept could or should be different than it currently is"
    - "the question 'what should this concept be' is in scope, not just 'what does this concept mean'"
  routes_away_when:
    - "user wants ordinary-language clarification of how the concept is currently used" → deep-clarification
    - "concept is essentially contested (Gallie sense) and the dispute itself is the object" → definitional-dispute (gap-deferred)
    - "concept is embedded in a specific argument whose soundness is at issue" → T1 modes
    - "concept is embedded in a paradigm whose framing is at issue" → T9 modes
when_not_to_invoke:
  - "User wants to know what a term currently means (descriptive task) — ameliorative move would be presumptuous" → deep-clarification
  - "Concept is technical with a settled stipulative definition — engineering move is unnecessary" → exposit existing definition

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: ameliorative

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [target_concept, current_usage_problems, ameliorative_purpose]
    optional: [proposed_revision, prior_engineering_attempts, normative_framework]
    notes: "Applies when user supplies the concept, names what's wrong with current usage, and articulates the purpose the revised concept should serve."
  accessible_mode:
    required: [concept_or_term, why_it_feels_off]
    optional: [what_user_wants_concept_to_do, examples_of_misuse]
    notes: "Default. Mode elicits ameliorative purpose during execution if missing."
  detection:
    expert_signals: ["ameliorative", "engineering", "redefine", "the function the concept should serve", "normative purpose"]
    accessible_signals: ["should mean", "isn't doing its job", "needs to be redefined", "the word is being used to"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What concept are we working on, and what's it failing to do for you in its current form?'"
    on_underspecified: "Ask: 'What would the concept ideally help us do, distinguish, or accomplish?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the ameliorative purpose been articulated as something the revised concept should *do* (a function it should serve), rather than as a stipulation that smuggles in conclusions?"
    failure_mode_if_unmet: stipulation-smuggle
  - cq_id: CQ2
    question: "Has the current concept's descriptive baseline been mapped before the ameliorative move, so the revision is responsive to actual usage rather than to a strawman?"
    failure_mode_if_unmet: baseline-skip
  - cq_id: CQ3
    question: "Has the implementation problem been acknowledged — i.e., the gap between proposing a revision and actually getting communities to adopt it (Cappelen 2018's challenge) — rather than treating the proposal as if proposal-equals-adoption?"
    failure_mode_if_unmet: implementation-blindness
  - cq_id: CQ4
    question: "Have revision costs been surfaced — what current uses, distinctions, or commitments would be lost or displaced by the proposed engineering?"
    failure_mode_if_unmet: cost-blindness

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: stipulation-smuggle
    detection_signal: "Ameliorative purpose is stated as a desired conclusion rather than a function (e.g., 'the concept should classify X as Y' rather than 'the concept should help us distinguish operations of class A from class B')."
    correction_protocol: re-dispatch
  - name: baseline-skip
    detection_signal: "Current usage descriptive section is absent or thin; the engineering move proceeds without grounding in what the concept currently does."
    correction_protocol: re-dispatch
  - name: implementation-blindness
    detection_signal: "Output proposes a revision without acknowledging the gap between proposal and uptake (no mention of who would need to adopt it, what coordination problem the revision faces, or what mechanism would carry the revision into community usage)."
    correction_protocol: flag
  - name: cost-blindness
    detection_signal: "Revision costs section is absent or treats current usage as having no value worth preserving."
    correction_protocol: flag
  - name: ameliorative-overreach
    detection_signal: "Engineering move applied to a concept whose contested status is constitutive (e.g., 'art', 'democracy') without acknowledging essentially-contested character; revision treated as resolvable when it is not."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - cappelen-plunkett-conceptual-engineering
  optional:
    - haslanger-ameliorative-analysis (when target concept is socially loaded)
    - gallie-essentially-contested-concepts (when concept may resist engineering)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "T10 currently has no molecular mode; if engineering proposal entails systemic implications, sideways-route to T9 worldview-cartography or T12 synthesis."
  sideways:
    target_mode_id: deep-clarification
    when: "On reflection the user wants descriptive clarification of current usage rather than normative redesign."
  downward:
    target_mode_id: deep-clarification
    when: "Engineering move is premature — the concept first needs descriptive clarification."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Conceptual Engineering is the rigor of the function-failure analysis and the candidness about implementation. A thin pass proposes a redefinition with stipulative language; a substantive pass maps current usage descriptively, identifies specific functions the current concept fails to perform (or performs in distorting ways), articulates the ameliorative purpose as a function the revised concept should serve (not as a desired conclusion), proposes candidate revisions with rationale, acknowledges the implementation problem (the gap between proposal and community uptake), and surfaces revision costs. Test depth by asking: could the analysis tell a community considering the revision what it would gain, what it would lose, and what coordination problem adoption would face?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means surveying the conceptual landscape around the target: adjacent concepts that would shift under the revision, alternative engineering moves the same problem might admit, prior engineering attempts (successful or failed) that bear on the proposal, normative frameworks that motivate or resist the revision. Breadth markers: at least two candidate revisions are surfaced; at least one alternative ameliorative purpose is considered; the revision's relationship to neighboring concepts is mapped.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Conceptual Engineering applies Cappelen-Plunkett ameliorative analysis — normative redesign of a concept to better serve a stated function, distinguished from descriptive clarification of current usage. It is distinct from deep-clarification (descriptive ordinary-language clarification of how the concept is currently used) and from definitional-dispute (essentially-contested concepts where the dispute is constitutive). It produces a proposal-with-honest-difficulty rather than a stipulative redefinition — the implementation problem (the gap between proposing a revision and getting communities to adopt it, Cappelen 2018) and the revision's costs are surfaced rather than concealed.

**Procedure.**

1. Name the target concept explicitly and minimally; state the engineering question on the table.
2. Map the descriptive baseline — current uses, distinctions, and commitments the concept carries. This is descriptive, not normative; the ameliorative move begins only after the baseline is in place.
3. Identify function failures — for each, name the function the concept should serve, how the current concept fails or distorts it, and what the failure costs in practice.
4. Articulate the ameliorative purpose as a *function* (something the revised concept should do, distinguish, accomplish), not as a *conclusion* (a desired classification the concept should produce). Stipulation-smuggle is the failure mode here.
5. Propose candidate revisions — each with rationale tying it to the ameliorative purpose and a tradeoff/cost note. Multiple candidates are preserved when streams converged on different proposals; collapse to a single recommendation prematurely is breadth-loss.
6. Acknowledge the implementation problem — who would need to adopt the revision, what coordination problem adoption faces, what mechanism (use, argument, education, legislation, movement-building) could carry it into community usage.
7. Surface revision costs — current uses, distinctions, or commitments the revision would displace or lose, with an assessment of whether the loss is worth the gain.
8. Flag ameliorative-overreach when the concept's contested status is constitutive (Gallie's essentially-contested concepts) — engineering move offered with explicit caveat rather than as a resolution.
9. Keep three confidences separate — function-failure diagnosis, proposed revision, adoption feasibility — they are not blended into a single verdict.

**Goal.** Produce an ameliorative-analysis clarification that walks from descriptive baseline through function-failure to candidate revision, with the implementation problem and revision costs honestly surfaced rather than concealed by stipulative confidence.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — function-articulated purpose.** Has the ameliorative purpose been articulated as something the revised concept should *do* (a function it should serve), rather than as a stipulation that smuggles in conclusions? Failure mode if unmet: `stipulation-smuggle`.
- **CQ2 — descriptive baseline first.** Has the current concept's descriptive baseline been mapped before the ameliorative move, so the revision is responsive to actual usage rather than to a strawman? Failure mode if unmet: `baseline-skip`.
- **CQ3 — implementation problem acknowledged.** Has the implementation problem been acknowledged — the gap between proposing a revision and getting communities to adopt it — rather than treating proposal as adoption? Failure mode if unmet: `implementation-blindness`.
- **CQ4 — revision costs surfaced.** Have revision costs been surfaced — what current uses, distinctions, or commitments would be lost or displaced by the proposed engineering? Failure mode if unmet: `cost-blindness`.

A passing output maps current usage as descriptive baseline, articulates function-shaped purpose (not conclusion-shaped), proposes candidate revisions with rationale and tradeoffs, names the implementation gap explicitly, surfaces revision costs, and keeps three confidence categories separate.

**Named failure modes.**

- *stipulation-smuggle* — ameliorative purpose stated as a desired conclusion rather than a function.
- *baseline-skip* — current usage descriptive section absent or thin; the engineering move proceeds without grounding in what the concept currently does.
- *implementation-blindness* — output proposes a revision without acknowledging the gap between proposal and uptake.
- *cost-blindness* — revision costs absent or treats current usage as having no value worth preserving.
- *ameliorative-overreach* — engineering move applied to a concept whose contested status is constitutive without acknowledging essentially-contested character.

## REVISION GUIDANCE

Revise to recast stipulative purpose as functional purpose. Revise to add descriptive baseline where the engineering move proceeds without grounding. Revise to add implementation acknowledgment where the proposal treats proposal-as-adoption. Revise to add cost surfacing where current usage is dismissed without analysis. Resist revising toward false confidence — conceptual engineering is hard, and a passing artifact admits the difficulty rather than concealing it.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **an ameliorative-analysis atom set: target-concept naming, descriptive baseline atoms, function-failure atoms, ameliorative-purpose statement, candidate-revision atoms with rationale, implementation-problem atoms, and revision-cost atoms**. The atoms are:

1. **Target-concept atom.** The concept being engineered, named explicitly and minimally. One short clause; no premature characterisation.

2. **Descriptive-baseline atoms.** Each atom captures one current use, distinction, or commitment the concept presently does (or is taken to do). Atoms here are descriptive, not normative — they record what current usage is, regardless of whether the engineering move will preserve it. Baseline-skip is the named failure mode the consolidator watches for; if streams arrived at the engineering move without a baseline section, the corpus reconstructs at least the minimum baseline before the ameliorative atoms.

3. **Function-failure atoms.** Each atom names one specific function the current concept fails to perform, or performs in a distorting way. Function-failure atoms carry: which function is at stake, how the current concept fails it, what the failure costs.

4. **Ameliorative-purpose atom.** The function the revised concept should serve, stated as a *function* (something it should do, distinguish, accomplish) rather than as a *conclusion* (a desired classification the revised concept should produce). Stipulation-smuggle is the named failure mode; function-shaped purposes survive into the corpus, conclusion-shaped purposes get reshaped or flagged.

5. **Candidate-revision atoms.** Each atom carries: the proposed revision, the rationale tying it to the ameliorative purpose, and the tradeoff or cost note attached to it. Multiple candidates are preserved (breadth marker); the corpus does not collapse to a single recommendation prematurely.

6. **Implementation-problem atoms.** Each atom names: who would need to adopt the revision, what coordination problem adoption faces, what mechanism (use, argument, education, legislation, movement) could carry the revision into community usage. Implementation-blindness is the named failure mode.

7. **Revision-cost atoms.** Each atom names: a current use, distinction, or commitment that the revision would displace or lose, and an assessment of whether the loss is worth the gain. Cost-blindness is the named failure mode.

8. **Ameliorative-overreach flag — when applicable.** When the target concept's contested status is constitutive (Gallie's essentially-contested concepts, where the dispute is itself the object), the corpus carries an explicit flag rather than smoothing the contestation into a candidate revision.

9. **Confidence per finding** distinguishing three kinds: confidence about the function-failure diagnosis, confidence about the proposed revision, and confidence about adoption feasibility. These three confidences are kept separate — a high-confidence diagnosis does not imply a high-confidence revision, and a high-confidence revision does not imply a high-confidence adoption forecast.

**Mode-specific bloat patterns to cut:**

- **Stipulative phrasing of the ameliorative purpose** — purpose statements that smuggle in the desired conclusion ("the concept should classify X as Y") rather than naming the function ("the concept should help us distinguish operations of class A from class B").
- **Engineering-without-baseline** — candidate revisions proposed without descriptive grounding in current usage; revision-as-strawman.
- **Proposal-equals-adoption assumption** — language that treats the engineering proposal as if articulation alone produced uptake.
- **Costless-revision framing** — revisions presented as pure gain, with current usage written off as having no value worth preserving.
- **Adjudication of the Cappelen-Haslanger implementation debate** — the corpus acknowledges the implementation problem without taking a side; arguments for or against the Cappelen-pessimist or Haslanger-engaged view are not in scope for the deliverable.

**What NOT to collapse:**

- **Competing candidate revisions** — when streams produced different ameliorative proposals for the same function-failure, both candidates are preserved with their respective rationales and tradeoff notes. The user, not the consolidator, chooses between competing engineering moves.
- **Disagreements about whether the concept admits engineering at all** — when one stream proposed a revision and another flagged ameliorative-overreach (the concept is essentially contested), both stances survive; the disagreement is itself the finding.
- **Stream disagreement about implementation feasibility** — when streams diverge on whether adoption is plausible for a particular candidate, both assessments are preserved.

## VERIFICATION CRITERIA

Verified means: target concept is named; current usage baseline is mapped; function failures are itemized; ameliorative purpose is function-shaped (not conclusion-shaped); at least one candidate revision is proposed with rationale; implementation problem is acknowledged; revision costs are surfaced; the four critical questions are addressable from the output. Confidence per major finding accompanies each claim.

## OUTPUT FORMAT GUIDANCE

The deliverable is an **ameliorative-analysis clarification** — a structured engineering proposal that walks from descriptive baseline through function-failure to candidate revision, with implementation and cost honestly surfaced. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Target concept.** One paragraph naming the concept explicitly and stating, in a sentence, what the engineering question on the table is.

2. **Current usage — descriptive baseline.** Itemise the current uses, distinctions, and commitments the concept presently carries. Each item: `**[Current use / distinction / commitment]** — [brief description of how the concept currently does this work].` This section is descriptive, not evaluative; the ameliorative move does not begin here.

3. **Identified function failures.** Bulleted list. Each: `**[Function the concept should serve]** — current concept's failure mode: [how it fails or distorts]. Cost of the failure: [what this costs in practice].`

4. **Ameliorative purpose.** One paragraph stating the function(s) the revised concept should serve, phrased as functions (distinguishing, enabling, supporting) rather than as conclusions (classifying X as Y). When the ameliorative purpose carries multiple sub-functions, enumerate them as a short bulleted list under the paragraph.

5. **Candidate revisions.** Each candidate gets its own labelled sub-block:
   - `**Candidate [N]: [revision phrased as a proposed reading or definition of the concept]**`
   - `Rationale: [how this revision answers the ameliorative purpose].`
   - `Tradeoffs and costs: [what current usage this revision preserves, displaces, or loses].`
   
   Multiple candidates appear when streams converged on different proposals; do not collapse to a single recommendation.

6. **Implementation problem.** One paragraph naming: who would need to adopt the revision, what coordination problem adoption faces, what mechanism (use, argument, education, legislation, movement-building) could carry it into community usage. When the user is doing engineering for use within their own work or organisation, this section is brief and notes the reduced scope of the implementation problem; when proposing revision for a wide community, this section is foregrounded.

7. **Revision costs and displacement.** Bulleted list. Each: `**[Current use / distinction / commitment that would be displaced]** — assessment: [is the loss worth the gain? What would the community lose access to?].`

8. **Confidence per finding.** Three labelled confidence assessments, kept distinct:
   - `Function-failure diagnosis: [confidence and basis].`
   - `Proposed revision(s): [confidence and basis].`
   - `Adoption feasibility: [confidence and basis].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- Ameliorative purpose is stated functionally throughout — purpose phrasings that smuggle in conclusions are reshaped or flagged at this layer if they survived consolidation.
- The Cappelen-Plunkett vocabulary (ameliorative analysis, implementation problem, function the concept should serve) is operative throughout; it is not paraphrased away into generic redefinition language.
- When the concept's contested status is constitutive (essentially-contested concept), the deliverable renders an explicit ameliorative-overreach block before section 5: `**Note: this concept's contestation may be constitutive (essentially contested in Gallie's sense); the engineering move risks treating as resolvable what is in fact the object of legitimate ongoing dispute. Candidate revisions below are offered with this caveat.**` The block does not suppress the rest of the deliverable; it qualifies it.
- The three confidence kinds (diagnosis, revision, adoption) stay separated in section 8 — they are not blended into a single confidence verdict.

## CAVEATS AND OPEN DEBATES

**Debate D7 — The implementation problem (Cappelen 2018 vs. Haslanger).** Cappelen's *Fixing Language* (2018) argues that conceptual engineering faces a fundamental implementation problem: even if a philosopher correctly identifies that a concept should be revised and articulates a better one, there is no clear mechanism by which the revision is taken up by language users. Concepts are decentralized, distributed across speakers and contexts, and resistant to top-down redesign; the engineering move risks being academically satisfying but practically inert. Haslanger's earlier ameliorative analysis (2012, 2020) is more optimistic about implementation: she treats ameliorative analysis as continuous with social and political contestation, where revised concepts gain uptake through use in argument, education, legislation, and movement-building rather than through philosopher-fiat. This mode does not adjudicate the debate. It requires acknowledgment of the implementation problem (per the implementation-blindness failure mode) without prescribing the Cappelen-pessimist or Haslanger-engaged response. When the user is doing engineering for use within their own work or organization, the implementation problem may shrink (the user is the adopter); when proposing revision for a wide community, the problem looms larger and should be foregrounded. Citations: Cappelen 2018 *Fixing Language*; Haslanger 2012 *Resisting Reality*, 2020 "Going on, not in the same way."

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- AGO
- Concept Fan
- Challenge
- CAF
- RAD

Mental models (always loaded):
- cappelen-plunkett-conceptual-engineering
- lakoff-conceptual-metaphor
- map-territory
- framing-effect
- narrative-instinct

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `contradicts`, `qualifies`, `analogous-to`, `extends`, `supersedes`
**Deprioritize:** `precedes`, `produces`

*Family: frame-paradigm. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
