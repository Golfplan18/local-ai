---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Argument Audit

```yaml
# 0. IDENTITY
mode_id: argument-audit
canonical_name: Argument Audit
suffix_rule: analysis
educational_name: argument audit (Frame Audit + Coherence Audit integrated)

# 1. TERRITORY AND POSITION
territory: T1-argumentative-artifact-examination
gradation_position:
  axis: depth
  value: molecular
adjacent_modes_in_territory:
  - mode_id: coherence-audit
    relationship: depth-light sibling (internal-consistency)
  - mode_id: frame-audit
    relationship: depth-light sibling (frame-surfacing + suspending)
  - mode_id: propaganda-audit
    relationship: specificity-specialized sibling (Stanley-influenced, adversarial-stance variant)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want a full audit of this argument: both whether it coheres and what frame it imports"
    - "the standard light passes each catch part of what's wrong; I want them integrated"
    - "willing to spend the time on a thorough integrated audit, not just a quick coherence or frame check"
    - "I want cross-cutting issues that neither the coherence pass nor the frame pass would catch alone"
  prompt_shape_signals:
    - "argument audit"
    - "full audit of this argument"
    - "coherence and frame check"
    - "thorough argument analysis"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants integrated audit spanning frame-audit + coherence-audit + cross-cutting synthesis"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "want only internal-consistency check" → coherence-audit
    - "want only frame-surfacing" → frame-audit
    - "argument is propaganda or persuasion-engineered" → propaganda-audit
    - "want to evaluate the argument as a proposal with stance" → T15 modes (steelman, balanced-critique, red-team-assessment / red-team-advocate)
when_not_to_invoke:
  - "User has time pressure" → coherence-audit or frame-audit
  - "User is asking who benefits from the argument's acceptance, not whether it holds" → cui-bono (T2)
  - "User wants paradigm-level comparison rather than single-artifact audit" → frame-comparison or worldview-cartography (T9)

# 3. EXECUTION STRUCTURE
composition: molecular
# NOTE: Decision N — Wave 4 build at depth-molecular position completing T1 depth ladder
# (coherence-audit → frame-audit → argument-audit). Carries Debate D2 (motte-and-bailey:
# fallacy or doctrine? Shackel preference vs. common usage).
molecular_spec:
  components:
    - mode_id: frame-audit
      runs: full
    - mode_id: coherence-audit
      runs: full
  synthesis_stages:
    - name: frame-coherence-merge
      type: parallel-merge
      input: [frame-audit, coherence-audit]
      output: "merged audit: per-claim coherence findings paired with frame-surfacing findings; identification of where frame-imports do analytical work coherence-audit alone would miss"
    - name: cross-cutting-integration
      type: contradiction-surfacing
      input: [frame-coherence-merge]
      output: "cross-cutting issues: where the argument's coherence depends on frame-imports that are themselves contested; where coherence-failures track frame-substitutions; where motte-and-bailey-style structure (or other frame-shifting fallacies) operates across claims"
    - name: integrated-audit-document
      type: dialectical-resolution
      input: [frame-coherence-merge, cross-cutting-integration]
      output: "integrated argument audit: per-claim findings, frame-level findings, cross-cutting issues, named fallacies (with debate notes where applicable), and overall argument-soundness assessment"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; do not aggregate over low-confidence frame or coherence findings

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [argumentative_artifact, audit_focus]
    optional: [prior_audits, contextual_background]
    notes: "Applies when user supplies the artifact plus a stated audit focus."
  accessible_mode:
    required: [argumentative_artifact]
    optional: [why_audit, contextual_background]
    notes: "Default. Mode elicits audit focus during execution."
  detection:
    expert_signals: ["audit this argument", "frame and coherence", "thorough audit"]
    accessible_signals: ["does this hold up", "something feels off", "check this argument"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you paste or describe the argument you want audited?'"
    on_underspecified: "Ask the user whether they want the full Argument Audit molecular pass or a lighter Coherence Audit / Frame Audit read."
output_contract:
  artifact_type: audit
  required_sections:
    - argument_summary
    - per_claim_coherence_findings
    - frame_surfacing_findings
    - cross_cutting_issues
    - named_fallacies_and_argumentative_moves
    - overall_argument_soundness_assessment
    - residual_uncertainties
    - confidence_map
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Does the cross-cutting-integration stage actually surface issues that neither component pass would catch alone, or does it merely concatenate them?"
    failure_mode_if_unmet: integration-failure
  - cq_id: CQ2
    question: "Are frame-imports identified concretely (which premises smuggle in which framings), or are they noted vaguely?"
    failure_mode_if_unmet: frame-import-vagueness
  - cq_id: CQ3
    question: "Are coherence findings grounded in specific claim-pairs and inference steps, or are they stated as general impressions?"
    failure_mode_if_unmet: coherence-impressionism
  - cq_id: CQ4
    question: "Where named fallacies are invoked (motte-and-bailey, equivocation, etc.), is the invocation specific and warranted, or is it a label slapped on a contested move?"
    failure_mode_if_unmet: fallacy-labeling-without-warrant

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: integration-failure
    detection_signal: "Cross-cutting-issues section restates per-claim and frame findings without identifying interactions between them."
    correction_protocol: re-dispatch (synthesis stage with explicit interaction prompt)
  - name: frame-import-vagueness
    detection_signal: "Frame findings refer to 'the frame' or 'the assumption' without naming which premise carries which import."
    correction_protocol: re-dispatch
  - name: coherence-impressionism
    detection_signal: "Coherence findings cite no specific claim-pair or inference step."
    correction_protocol: re-dispatch
  - name: fallacy-labeling-without-warrant
    detection_signal: "Named fallacies (motte-and-bailey, etc.) are invoked without showing the specific structural move."
    correction_protocol: flag and re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - walton-argumentation-schemes
  optional:
    - lakoff-framing
    - shackel-motte-and-bailey (when motte-and-bailey is in play; carries Debate D2)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Argument Audit is the heaviest mode in T1's depth ladder."
  sideways:
    target_mode_id: propaganda-audit
    when: "Artifact is propaganda or persuasion-engineered; Stanley-influenced specialized variant applies."
  downward:
    target_mode_id: coherence-audit
    when: "User has time pressure or scope is narrower (internal-consistency only)."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Argument Audit is the degree to which the cross-cutting-integration stage produces issues that no single component pass would catch alone. A thin molecular pass concatenates frame-audit and coherence-audit outputs; a substantive pass identifies where coherence depends on contested frame-imports, where coherence-failures track frame-substitutions across claims, and where motte-and-bailey-style structure operates across an argument's parts. Test depth by asking: does the audit name a structural move that requires both frame-perception and coherence-tracking to detect?

## BREADTH ANALYSIS GUIDANCE

Breadth in Argument Audit is the catalog of frames considered before frame-audit narrows. Widen the lens to scan: dominant-paradigm frame; minority-tradition frame; rhetorical-genre frame; historical-genealogy frame. Even when the cross-cutting-integration narrows to specific cross-cutting issues, breadth is documented in the frame-surfacing-findings section. Note: alternative compositions considered included adding propaganda-audit; current composition stays neutral and routes to propaganda-audit when artifact is propaganda-engineered.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing Argument Audit output identifies cross-cutting issues that single-component passes would miss, names frame-imports concretely (which premise carries which import), grounds coherence findings in specific claim-pairs and inference steps, and warrants any fallacy labels with structural specificity.

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates. Revise to add specificity to vague frame-imports or impressionistic coherence findings. Revise to warrant named fallacies with structural detail. Resist revising toward stance-bearing evaluation — Argument Audit is neutral; stance-bearing evaluation belongs in T15 (steelman, the red-team modes, balanced-critique). When the audit surfaces something that warrants stance-bearing follow-up, flag the handoff rather than performing it.

## CONSOLIDATION GUIDANCE

Consolidate as a structured audit with the eight required sections. Each finding carries provenance to its component source (frame-audit for frame findings; coherence-audit for coherence findings; synthesis stages for cross-cutting issues). The named-fallacies-and-argumentative-moves section includes Debate D2 references where motte-and-bailey is invoked. Confidence map is per-finding.

## VERIFICATION CRITERIA

Verified means: both component passes ran (or were flagged as proceeded-with-gap); cross-cutting-integration surfaces issues neither component caught alone; frame-imports and coherence findings are concretely grounded; named fallacies are warranted; confidence map is populated. The four critical questions are addressed in the output.

## CAVEATS AND OPEN DEBATES

**Debate D2 — Motte-and-bailey: fallacy or doctrine?** Shackel (2005, "The Vacuity of Postmodernist Methodology") introduced the term as a *doctrine* — a structural feature of certain argumentative positions in which an arguer alternates between a defensible "motte" (modest claim) and a desirable "bailey" (ambitious claim) when challenged. Shackel's preferred usage frames motte-and-bailey as a *characterization of a doctrine's structure*, not as a fallacy committed in a single inferential step. In wider usage (online discourse, popular argumentation guides), the term has come to function as a *fallacy label* applied to single moves where an arguer retreats from an ambitious claim under pressure. This mode operates without adjudicating the debate: when motte-and-bailey is invoked, the audit names the structural move in the argument's terms (which claim is motte, which is bailey, where the alternation occurs) rather than relying on the label alone, and notes whether Shackel's doctrinal usage or the wider fallacy-label usage best fits the case. Consumers seeking a stricter Shackel-aligned reading should treat motte-and-bailey invocations as doctrinal characterizations requiring multi-claim evidence; consumers using the wider sense may accept single-move applications. Citations: Shackel 2005; cf. wider discussion in popular argumentation literature.
