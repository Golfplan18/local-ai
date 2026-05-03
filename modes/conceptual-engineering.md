---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
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
output_contract:
  artifact_type: clarification
  required_sections:
    - target_concept_named
    - current_usage_descriptive_baseline
    - identified_function_failures
    - ameliorative_purpose
    - candidate_revisions_with_rationale
    - implementation_problem_acknowledgment
    - revision_costs_and_displacement
    - confidence_per_finding
  format: structured

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

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) function-articulated purpose, not stipulation-smuggle; (CQ2) descriptive baseline before ameliorative move; (CQ3) implementation problem acknowledged; (CQ4) revision costs surfaced. The named failure modes (stipulation-smuggle, baseline-skip, implementation-blindness, cost-blindness, ameliorative-overreach) are the evaluation checklist. A passing engineering output maps current usage, articulates function-shaped purpose, proposes candidates with rationale, names implementation gap, and surfaces costs.

## REVISION GUIDANCE

Revise to recast stipulative purpose as functional purpose. Revise to add descriptive baseline where the engineering move proceeds without grounding. Revise to add implementation acknowledgment where the proposal treats proposal-as-adoption. Revise to add cost surfacing where current usage is dismissed without analysis. Resist revising toward false confidence — conceptual engineering is hard, and a passing artifact admits the difficulty rather than concealing it.

## CONSOLIDATION GUIDANCE

Consolidate as a structured clarification artifact with the eight required sections. Target concept is named explicitly. Current usage descriptive baseline appears as its own section before the ameliorative move. Identified function failures are itemized. Ameliorative purpose is stated as function the revised concept should serve. Candidate revisions appear with rationale and tradeoff notes. Implementation problem and revision costs each get their own section. Confidence-per-finding distinguishes confidence about the function-failure diagnosis from confidence about the proposed revision from confidence about adoption feasibility.

## VERIFICATION CRITERIA

Verified means: target concept is named; current usage baseline is mapped; function failures are itemized; ameliorative purpose is function-shaped (not conclusion-shaped); at least one candidate revision is proposed with rationale; implementation problem is acknowledged; revision costs are surfaced; the four critical questions are addressable from the output. Confidence per major finding accompanies each claim.

## CAVEATS AND OPEN DEBATES

**Debate D7 — The implementation problem (Cappelen 2018 vs. Haslanger).** Cappelen's *Fixing Language* (2018) argues that conceptual engineering faces a fundamental implementation problem: even if a philosopher correctly identifies that a concept should be revised and articulates a better one, there is no clear mechanism by which the revision is taken up by language users. Concepts are decentralized, distributed across speakers and contexts, and resistant to top-down redesign; the engineering move risks being academically satisfying but practically inert. Haslanger's earlier ameliorative analysis (2012, 2020) is more optimistic about implementation: she treats ameliorative analysis as continuous with social and political contestation, where revised concepts gain uptake through use in argument, education, legislation, and movement-building rather than through philosopher-fiat. This mode does not adjudicate the debate. It requires acknowledgment of the implementation problem (per the implementation-blindness failure mode) without prescribing the Cappelen-pessimist or Haslanger-engaged response. When the user is doing engineering for use within their own work or organization, the implementation problem may shrink (the user is the adopter); when proposing revision for a wide community, the problem looms larger and should be foregrounded. Citations: Cappelen 2018 *Fixing Language*; Haslanger 2012 *Resisting Reality*, 2020 "Going on, not in the same way."
