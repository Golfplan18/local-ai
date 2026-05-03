---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-30
date modified: 2026-05-01
meta_mode: true
passthrough: true
---

# MODE: Structured Output

```yaml
# 0. IDENTITY
mode_id: structured-output
canonical_name: Structured Output
suffix_rule: none
educational_name: structured output formatting

# 1. TERRITORY AND POSITION
territory: T21-execution-project-mode
gradation_position:
  axis: specificity
  value: rendering-only
adjacent_modes_in_territory:
  - mode_id: project-mode
    relationship: specificity variant (original-execution; PM thinks, SO renders)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "user has content and wants it rendered into a specific format"
    - "deliverable is presentational rather than analytical"
    - "task is faithful rendering of existing material, not original analysis"
  prompt_shape_signals:
    - "write this as a report"
    - "format as a memo"
    - "create a comparison table"
    - "put this in outline form"
    - "draft a one-pager"
    - "render this in"
disambiguation_routing:
  routes_to_this_mode_when:
    - "content already exists and the task is rendering"
    - "deliverable is primarily presentational; format is the core value-add"
  routes_away_when:
    - "original analysis is needed to produce the deliverable" → project-mode (T21)
    - "content does not yet exist" → upstream Front-End Process for clarification first
    - "user wants to explore rather than format" → passion-exploration (T20) or terrain-mapping (T14)
when_not_to_invoke:
  - "Original analysis is required — Project Mode thinks; Structured Output renders. SO does NOT generate content to compensate for missing input."
  - "User wants the content itself adversarially reviewed — that requires the source content's analytical mode, not SO"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [source_content_reference, requested_format_specification, target_audience]
    optional: [format_template, voice_or_style_constraints, prior_format_examples]
    notes: "Applies when user supplies precise source-content reference and named format template."
  accessible_mode:
    required: [source_content, format_request]
    optional: [audience_or_purpose]
    notes: "Default. Mode infers format conventions from the named document type."
  detection:
    expert_signals: ["template", "format spec", "house style", "per the standard"]
    accessible_signals: ["write this as", "format as", "put in the form of", "render this"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the source content I should render, and what format do you want it in?'"
    on_underspecified: "Ask: 'Should I render existing content into this format (Structured Output), or do you need me to also produce the analysis first (Project Mode or an analytical mode)?'"
output_contract:
  artifact_type: other
  required_sections:
    - formatted_deliverable
    - gap_report
    - format_notes
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Does every substantive claim in the output trace to source content, or has the rendering introduced new claims?"
    failure_mode_if_unmet: analyst-trap
  - cq_id: CQ2
    question: "Has the requested format been followed faithfully, or has format mismatch occurred?"
    failure_mode_if_unmet: format-mismatch
  - cq_id: CQ3
    question: "Have gaps between source and format been flagged explicitly, or have they been silently filled?"
    failure_mode_if_unmet: gap-silently-filled
  - cq_id: CQ4
    question: "Has the rendering avoided introducing recommendation or conclusion not in source — SO renders, does not advise?"
    failure_mode_if_unmet: embellishment
  - cq_id: CQ5
    question: "If source contains visual envelopes, are they preserved byte-equivalent in the output (no schema drift)?"
    failure_mode_if_unmet: schema-drift-on-passthrough

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: analyst-trap
    detection_signal: "Output contains substantive claims that do not trace to source content."
    correction_protocol: re-dispatch (every claim must trace to source; remove or attribute SO-added inferences explicitly)
  - name: template-trap
    detection_signal: "Source content forced into ill-fitting structure; misalignment between content and format."
    correction_protocol: flag (adapt the format to serve the content; note the adaptation)
  - name: compression-trap
    detection_signal: "Compression dropped critical qualifications or caveats."
    correction_protocol: flag (preserve nuance; declare compression explicitly)
  - name: embellishment
    detection_signal: "Transitional framing introduced substantive claim not in source."
    correction_protocol: re-dispatch (transitions are structural, not analytical)
  - name: schema-drift-on-passthrough
    detection_signal: "Visual envelope JSON differs from source after rendering."
    correction_protocol: re-dispatch (byte-equivalent passthrough; no regeneration)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - format-template-library (per document type)
    - debono-ago (when format selection requires goal clarification)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~1min
escalation_signals:
  upward:
    target_mode_id: project-mode
    when: "User realizes original analysis is needed to produce the deliverable, not just rendering."
  sideways:
    target_mode_id: null
    when: "T21 has only PM and SO; no sideways sibling within territory."
  downward:
    target_mode_id: null
    when: "Structured Output is already T21's lightest execution sibling."
```

## DEPTH ANALYSIS GUIDANCE

Structured Output is rendering-oriented; depth here means the rigor of fidelity-to-source rather than depth-of-analysis. Going deeper means tracing every substantive claim to a specific passage in the source, preserving qualifications and caveats through compression, and surfacing gaps between source and requested format rather than filling them silently. A thin pass renders the format and stops; a substantive pass cross-checks each output claim against source, declares format adaptations explicitly, and produces a Gap report when source does not fully satisfy the format. Test depth by asking: could the user audit the output line by line and trace each claim to its source passage?

The depth ceiling for SO is set by the source — SO does not deepen content beyond what source supports. Adversarial review at Gear 3 is appropriate for high-stakes rendering (publication, client-facing, regulatory) but consolidator merging is NOT applied (passthrough fidelity defeats parallel consolidation).

## BREADTH ANALYSIS GUIDANCE

Breadth in Structured Output is the survey of format options considered before settling on the rendering approach. Widen the lens to: alternative organizations (chronological vs thematic vs priority-ordered); alternative compression levels (one-pager vs full report); alternative section conventions per requested format. Breadth markers: when source does not cleanly fit the requested format, alternative formats are surfaced as adaptations rather than the rendering being forced. Compression notes name what was dropped; format adaptations name what was changed and why.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ5. The named failure modes are the evaluation checklist. A passing Structured Output (a) preserves fidelity (every substantive claim traces to source); (b) follows the requested format; (c) flags gaps explicitly rather than silently filling; (d) adds no recommendation not in source; (e) preserves visual envelopes byte-equivalent (no schema drift; mode_context preserved from source). The fidelity invariant is load-bearing — silent addition of substantive claims is the worst failure mode. Threshold is **higher** here (≥ 95%) because rendering should be reliable.

## REVISION GUIDANCE

Revise to remove substantive claims that do not trace to source. Revise to flag gaps that were silently filled. Revise to restore visual envelope byte-equivalence where regeneration occurred. Revise to preserve `mode_context` on passthrough envelopes (do NOT rewrite to `structured-output`). Resist revising toward analytical contribution — SO renders, does not advise. If the source is genuinely insufficient for the format, expand the Gap report rather than padding the output.

## CONSOLIDATION GUIDANCE

Consolidate as the formatted deliverable plus the two universal elements: gap report and format notes. The formatted deliverable follows the requested format's conventions. Visual envelopes from source are passed through byte-equivalent with `mode_context` preserved (NOT rewritten to `structured-output`). Format notes record structural choices (ordering, compression, section organisation). Gap report names where source did not fully satisfy format requirements. Format follows the deliverable type. Conversation history weight is higher than for analytical modes — source content is usually in history.

## VERIFICATION CRITERIA

Verified means: every substantive claim in output traces to source; format follows requested conventions; gaps explicitly flagged; no recommendation added that was not in source; visual envelopes preserved byte-equivalent with `mode_context` from source. The five critical questions are addressed. Silent gap-filling, silent recommendation injection, and silent schema drift on passthrough envelopes are all verification failures. Envelope count must match source (if source has N visuals, output has N visuals).
