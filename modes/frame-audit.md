---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
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
output_contract:
  artifact_type: audit
  required_sections:
    - operative_frames_named
    - lakoff_metaphor_inventory
    - goffman_primary_framework_and_keyings
    - entman_four_functions_per_frame
    - selection_and_salience_inventory
    - presupposition_and_nominalization_audit
    - counterframe_what_an_alternative_frame_would_look_like
    - confidence_per_finding
  format: structured

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

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) frame named in alternative-comparable vocabulary; (CQ2) Entman four functions populated; (CQ3) selection and silence both catalogued; (CQ4) lexical and grammatical mechanisms inventoried; (CQ5) counterframe constructed. The named failure modes (frame-naturalization, function-collapse, silence-blindness, macro-frame-only-reading, counterframe-omission, stance-slippage-into-attack) are the evaluation checklist. A passing Frame Audit names frames in vocabulary that travels across alternatives, populates the four functions per frame, inventories selection and silence, cites the lexical-grammatical mechanisms with quoted text, and constructs at least one counterframe.

## REVISION GUIDANCE

Revise to extract the frame to alternative-comparable vocabulary where the draft has restated the artifact's framing in its own terms. Revise to populate Entman's four functions per frame where the draft has named the frame without showing its work. Revise to add the silence inventory where selection-and-salience reads only inclusions. Revise to add lexical-grammatical mechanisms where the draft operates only at the macro-frame level. Revise to construct the counterframe where it is missing. Resist revising toward attack on the frame — the mode is stance-suspending; surfacing the frame and showing its costs is the analytical character, but rejecting the frame belongs in propaganda-audit (if propaganda is suspected) or in the red-team modes (if the artifact is being evaluated as a proposal).

## CONSOLIDATION GUIDANCE

Consolidate as a structured audit with the eight required sections. Operative frames are named explicitly with one-sentence characterizations in vocabulary that travels across alternatives. The Lakoff metaphor inventory cites quoted text and names the source-domain → target-domain mapping with its inferential entailments. Goffman primary framework and keyings are identified (natural / social; make-believe / contests / ceremonials / technical-redoings / regroundings; fabrication if applicable). The four Entman functions are populated per frame with quoted evidence. Selection and salience inventory has both included-and-emphasized and excluded-and-downplayed columns. Presupposition and nominalization audit cites quoted text per finding. The counterframe is sketched as a one-paragraph alternative reading the artifact does not perform. Confidence per finding accompanies each major claim.

## VERIFICATION CRITERIA

Verified means: operative frames are named in alternative-comparable vocabulary; the four Entman functions are populated per frame with quoted evidence; the selection-and-silence inventory has entries in both columns; lexical and grammatical mechanisms are cited with quoted text; at least one counterframe is constructed; the audit has not slipped from frame-surfacing into frame-rejection. The five critical questions are addressable from the output. Confidence per finding accompanies each major claim.
</content>
</invoke>