---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Information Density

```yaml
# 0. IDENTITY
mode_id: information-density
canonical_name: Information Density
suffix_rule: analysis
educational_name: information density and visual hierarchy (Tufte, Bertin, Cleveland-McGill)

# 1. TERRITORY AND POSITION
territory: T19-spatial-composition
gradation_position:
  axis: specificity
  value: applied-evaluative
  stance_axis_value: applied-evaluative-medium-depth
  depth_axis_value: medium
adjacent_modes_in_territory:
  - mode_id: compositional-dynamics
    relationship: depth-lighter sibling (universal-perceptual descriptive medium-depth; gestalt + Arnheim + Itten + Albers; built Wave 2)
  - mode_id: ma-reading
    relationship: stance-counterpart (contemplative-descriptive-deep, aesthetic-experiential, Japanese aesthetics; built Wave 2)
  - mode_id: place-reading-genius-loci
    relationship: specificity-counterpart (descriptive-evaluative-deep; affordance + inhabited-place; Wave 3)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "want a Tufte-style critique of this chart / dashboard / info-graphic"
    - "want a data-ink ratio audit"
    - "the visual encoding doesn't seem to be doing the job"
    - "want to know whether the right perceptual task is supported by this chart"
    - "want a Bertin visual-variables analysis"
    - "want a typographic-hierarchy / grid analysis of this page"
    - "evaluating an info-graphic and need prescriptive recommendations"
    - "designing a chart and need to choose the right encoding for the elementary task"
  prompt_shape_signals:
    - "information density"
    - "visual hierarchy"
    - "Tufte"
    - "data-ink ratio"
    - "chartjunk"
    - "small multiples"
    - "Bertin"
    - "visual variables"
    - "selective associative ordered quantitative"
    - "Cleveland McGill"
    - "elementary perceptual tasks"
    - "graphical perception"
    - "Bringhurst"
    - "Lupton"
    - "typographic hierarchy"
    - "grid analysis"
    - "critique this chart"
    - "this dashboard isn't working"
disambiguation_routing:
  routes_to_this_mode_when:
    - "input is an information graphic (chart, dashboard, table, infographic, map, typographic page)"
    - "user wants prescriptive critique with specific recommendations (not just descriptive reading)"
    - "user wants the data-encoding tradition (Tufte / Bertin / Cleveland-McGill / Bringhurst / Lupton) applied"
    - "user is designing or evaluating an info-graphic and needs encoding-fitness assessment"
  routes_away_when:
    - "user wants the void / interval / silence read as primary content (Japanese aesthetics)" → ma-reading
    - "user wants the universal compositional-forces / gestalt reading without info-encoding focus" → compositional-dynamics
    - "user wants prospect-refuge / pattern-language / inhabited-place reading" → place-reading-genius-loci
    - "user wants relation-extraction from a diagram (what does the diagram assert about A→B→C)" → relationship-mapping or spatial-reasoning (T11)
    - "user wants statistical analysis of the underlying data rather than analysis of its encoding" → other territory
when_not_to_invoke:
  - "Input is not an information graphic (a painting, garden, room, raw data without visual encoding)" → other T19 modes or other territory
  - "User wants the data analyzed (not its visual encoding evaluated)" → other territory
  - "User wants pure aesthetic reading without prescriptive recommendation" → ma-reading or compositional-dynamics
  - "User wants relation-extraction from a diagram qua notation" → T11

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: constructive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [information_graphic, intended_message_or_decision_supported, intended_audience]
    optional: [data_source, prior_design_iterations, brand_or_house_style_constraints, cultural_or_regional_context, accessibility_requirements]
    notes: "Applies when user supplies the graphic plus the message it is meant to communicate or the decision it is meant to support, and identifies the intended audience."
  accessible_mode:
    required: [information_graphic]
    optional: [what_user_wants_the_graphic_to_show, what_user_thinks_is_wrong_with_it, who_will_see_it]
    notes: "Default. Mode infers intended message and audience from the graphic and surrounding context."
  detection:
    expert_signals: ["data-ink", "chartjunk", "Tufte", "Bertin", "visual variables", "Cleveland McGill", "elementary perceptual task", "Bringhurst", "Lupton", "small multiples", "sparkline"]
    accessible_signals: ["this chart isn't working", "critique this dashboard", "the typography on this page", "is this graphic clear"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you share the graphic (image or description) and tell me what message it's meant to communicate or what decision it's meant to support?'"
    on_underspecified: "Ask: 'Who is the intended audience, and what should they be able to read off the graphic at a glance vs. with sustained attention?'"
output_contract:
  artifact_type: critique-with-prescriptive-recommendations
  required_sections:
    - graphic_summary_and_intended_message
    - data_ink_ratio_audit
    - visual_variable_to_data_attribute_mapping_check
    - elementary_perceptual_task_fitness_check
    - typographic_hierarchy_and_grid_analysis
    - chartjunk_and_redundancy_inventory
    - prescriptive_recommendations_ranked
    - residual_tradeoffs_and_constraints
    - confidence_per_recommendation
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the analysis identified the elementary perceptual task the graphic requires (position-on-common-scale, nonaligned-position, length, angle, direction, area, volume, curvature, color/shading) and assessed whether the visual encoding supports that task at the accuracy the message demands? (Cleveland-McGill check.)"
    failure_mode_if_unmet: elementary-task-mismatch-undiagnosed
  - cq_id: CQ2
    question: "Has the visual-variable-to-data-attribute mapping (Bertin: position, size, shape, value, color, orientation, texture × selective / associative / ordered / quantitative) been checked for fitness, or has the analysis assumed the encoding is appropriate without testing?"
    failure_mode_if_unmet: bertin-mapping-unchecked
  - cq_id: CQ3
    question: "Has data-ink ratio been audited specifically (which marks carry data; which carry decoration / structure / context; what could be removed without information loss), or has 'too much chartjunk' been asserted as a vague label?"
    failure_mode_if_unmet: data-ink-as-slogan
  - cq_id: CQ4
    question: "Has the typographic hierarchy and grid analysis (Bringhurst / Lupton: scale, weight, color, rhythm, measure, leading, grid alignment) been performed where the input includes typography, or skipped on the assumption that text is not part of the encoding?"
    failure_mode_if_unmet: typography-as-not-encoding
  - cq_id: CQ5
    question: "Are the prescriptive recommendations specific (which mark to change, which encoding to substitute, which element to remove, which hierarchy to strengthen), or are they general gestures (simplify, declutter, improve hierarchy) without specific changes?"
    failure_mode_if_unmet: recommendations-as-gestures
  - cq_id: CQ6
    question: "Have residual tradeoffs and constraints been acknowledged — situations where the prescriptive recommendation conflicts with brand / house-style / accessibility / data-honesty / audience-expectation constraints — rather than asserting recommendations as unconstrained?"
    failure_mode_if_unmet: constraint-blindness

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: elementary-task-mismatch-undiagnosed
    detection_signal: "Analysis does not identify the elementary perceptual task the graphic requires; Cleveland-McGill ranking not applied; encoding-fitness for the task not assessed."
    correction_protocol: re-dispatch
  - name: bertin-mapping-unchecked
    detection_signal: "Visual-variable-to-data-attribute mapping not assessed for fitness (selective / associative / ordered / quantitative properties of the encoding vs. the data attribute it represents)."
    correction_protocol: re-dispatch
  - name: data-ink-as-slogan
    detection_signal: "Data-ink ratio invoked as a label (too much chartjunk; data-ink ratio is low) without auditing specific marks for which ones carry data vs. decoration vs. structure."
    correction_protocol: re-dispatch
  - name: typography-as-not-encoding
    detection_signal: "Input includes typography (chart labels, dashboard text, page layout) but typographic hierarchy and grid analysis not performed; text treated as carrier rather than as encoding."
    correction_protocol: re-dispatch
  - name: recommendations-as-gestures
    detection_signal: "Prescriptive recommendations are general (simplify, declutter, improve hierarchy) rather than specific (replace pie chart with horizontal bar; reduce gridline contrast to 30%; align number labels right; remove the 3D effect)."
    correction_protocol: re-dispatch
  - name: constraint-blindness
    detection_signal: "Recommendations asserted without acknowledging brand / house-style / accessibility / data-honesty / audience-expectation constraints that may make some recommendations infeasible or undesirable."
    correction_protocol: flag
  - name: tufte-orthodoxy
    detection_signal: "Recommendations apply Tufte minimalism dogmatically (maximize data-ink, eliminate all decoration) without acknowledging contexts where minor redundancy / framing / annotation actively serves the audience or message."
    correction_protocol: flag
  - name: aesthetic-only-critique
    detection_signal: "Critique addresses aesthetic preferences (this chart looks ugly; this dashboard is busy) without grounding the critique in encoding-fitness or perceptual-task analysis."
    correction_protocol: re-dispatch
  - name: m5-promotion-evidence
    detection_signal: "Multiple recent invocations on info-graphic inputs encounter operations this mode handles awkwardly (specialty: dashboard-orchestration analysis; chart-type-selection deep dive; sparkline-and-small-multiples specialty); Reserved-M5 (Information-Graphic Visual-Hierarchy Analysis) promotion threshold approached per T19 reserved-M5 spec."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - tufte-data-ink-chartjunk
    - bertin-visual-variables
    - cleveland-mcgill-perceptual-tasks
    - bringhurst-typographic-hierarchy
  optional:
    - lupton-thinking-with-type (when typography is dominant in the input)
    - few-information-dashboard-design (when input is a dashboard with multiple coordinated views)
    - munzner-visualization-analysis-and-design (when chart-type selection requires task-data-encoding triple analysis)
    - kosslyn-graph-design (when audience cognition / message-graphic alignment requires deeper treatment)
    - wilkinson-grammar-of-graphics (when systematic chart-type comparison is needed)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Information Density is the deepest applied-evaluative info-graphic mode in T19 at present. The Reserved-M5 mode (Information-Graphic Visual-Hierarchy Analysis specialty) is held against a promotion threshold per T19 reanalysis; promote when info-graphic critique workload exceeds ~15% of T19 invocations or when this mode visibly fails to distinguish encoding-misfit from generic compositional critique."
  sideways:
    target_mode_id: compositional-dynamics
    when: "On reflection the operative work is being done by general gestalt / Arnheim compositional forces rather than by data-encoding fitness; switch to universal-perceptual reading."
  downward:
    target_mode_id: compositional-dynamics
    when: "User wants only the universal compositional reading without prescriptive recommendation or encoding-fitness analysis."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Information Density is the rigor with which four analytical operations are integrated rather than aggregated: (1) **data-ink ratio audit** (Tufte) — for each mark in the graphic, classify as data-ink (carries data), structure-ink (carries necessary scaffolding: axes, scale references, data-defining frames), or chartjunk (carries decoration / redundancy / moiré / 3D effect / unnecessary color); compute or estimate the ratio; identify specific removals or simplifications without information loss; (2) **visual-variable mapping check** (Bertin) — for each data attribute, identify which visual variable encodes it (position, size, shape, value, color, orientation, texture) and check fitness against the variable's selective / associative / ordered / quantitative properties (e.g., color is selective but not quantitative; position is all four); flag mismatches (categorical data on a quantitative variable like length; quantitative data on a non-ordered variable like color hue); (3) **elementary perceptual task fitness check** (Cleveland-McGill) — identify the perceptual task the graphic requires (position-on-common-scale > nonaligned-position > length > angle > direction > area > volume > color/shading, in descending accuracy); check whether the chart type supports the required task at the accuracy the message demands (e.g., pie charts ask for angle / area judgment; horizontal bar charts ask for length judgment, more accurate); (4) **typographic hierarchy and grid analysis** (Bringhurst / Lupton) where applicable — scale, weight, color, rhythm, measure, leading, grid alignment, the page-as-designed-space; check that hierarchy supports reading order and that the grid carries the composition. A thin pass invokes labels (chartjunk; clean up; improve hierarchy); a substantive pass performs each of the four operations with specific findings and produces specific recommendations. Test depth by asking: could a designer implement the recommendations without further interpretation?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning across the four lens-clusters before narrowing (Tufte data-ink / Bertin visual-variables / Cleveland-McGill perceptual-tasks / Bringhurst-Lupton typography); considering the graphic in its decision-support context (what does the audience need to read off the graphic at a glance, what at sustained attention, what should they decide or notice); considering the chart-type alternatives at the decision point (could a different chart type — small multiples, sparkline, dot plot, slope graph, table — support the elementary task more accurately); considering the constraints (brand / house-style; accessibility — color-blindness, contrast, screen-reader; data-honesty — does the encoding mislead through truncation, area-vs-length confusion, or 3D distortion; audience expectation — convention may justify deviation from theoretical optimum); and noting where the input is part of a larger system (a dashboard's coordination, a report's narrative arc, a presentation's slide rhythm). Breadth markers: at least three of the four lens-clusters substantively addressed (typography skipped only if input is purely chart-without-text); at least one chart-type alternative considered if the chart-type-fit is in question; at least one constraint acknowledged.

## EVALUATION CRITERIA

Evaluate against the six critical questions: (CQ1) elementary perceptual task identified and encoding-fitness assessed; (CQ2) visual-variable mapping checked against Bertin properties; (CQ3) data-ink ratio audited specifically not asserted as label; (CQ4) typographic hierarchy and grid analyzed where applicable; (CQ5) recommendations specific not gestures; (CQ6) constraints acknowledged. The named failure modes are the evaluation checklist. A passing Information Density output addresses the four operations substantively, produces specific prescriptive recommendations (which mark to change, which encoding to substitute, which element to remove), acknowledges residual tradeoffs and constraints, ranks recommendations by impact, and assigns confidence per recommendation.

## REVISION GUIDANCE

Revise to identify the elementary perceptual task and check encoding-fitness where the draft skipped Cleveland-McGill. Revise to check visual-variable mapping where the draft skipped Bertin. Revise to audit specific marks where the draft asserted "chartjunk" generically. Revise to perform typographic hierarchy analysis where the draft skipped typography-as-encoding. Revise to make recommendations specific (which mark, which encoding, which element, which hierarchy) where the draft offered gestures. Revise to acknowledge constraints (brand / accessibility / data-honesty / audience-expectation) where the draft asserted recommendations as unconstrained. Resist revising toward Tufte orthodoxy — the mode's character is *applied-evaluative-medium-depth* with prescriptive recommendation; minimalism is a strong default but not a dogma, and contexts where minor redundancy / framing / annotation actively serves the audience or message are real. Resist revising toward aesthetic-only critique — the mode is grounded in encoding-fitness and perceptual-task analysis, not in aesthetic preference.

## CONSOLIDATION GUIDANCE

Consolidate as a structured critique-with-prescriptive-recommendations artifact with the nine required sections. Graphic summary and intended message appear first (the analytical object plus what it is meant to communicate). Data-ink ratio audit lists data-ink, structure-ink, and chartjunk marks with specific identification. Visual-variable mapping check lists each data attribute with its encoding and a fitness assessment per Bertin properties. Elementary perceptual task fitness check identifies the task the graphic requires and assesses encoding accuracy at that task per Cleveland-McGill ranking. Typographic hierarchy and grid analysis is present where input includes typography (or marked as not-applicable for chart-without-text). Chartjunk and redundancy inventory lists specific removable elements. Prescriptive recommendations are ranked by impact (high-impact first), each specific (which mark, which encoding, which removal, which hierarchy strengthening), each keyed to the operation that diagnosed the problem. Residual tradeoffs and constraints are acknowledged (brand / accessibility / data-honesty / audience-expectation conflicts; cases where the recommendation should not be implemented despite encoding-fitness gain). Confidence per recommendation distinguishes high-confidence (encoding-misfit clearly diagnosed; replacement clearly better) from medium-confidence (tradeoff-dependent) from low-confidence (depends on audience testing).

## VERIFICATION CRITERIA

Verified means: graphic and intended message identified; data-ink ratio audited with specific marks classified; visual-variable mapping checked per Bertin properties for each data attribute; elementary perceptual task identified and encoding-fitness assessed per Cleveland-McGill ranking; typographic hierarchy and grid analyzed where applicable; chartjunk and redundancy inventory present; at least three prescriptive recommendations specific (which mark / encoding / element / hierarchy) and ranked by impact; residual tradeoffs and constraints acknowledged; the six critical questions are addressable from the output. Confidence per recommendation accompanies each claim. Cross-reference to T19 territory-level open debates is noted where the analysis depends on contested framing decisions (especially Debate 5 on AI implementability of perceptual operations for direct-image vs. verbal-description input — Information Density degrades for hand-sketched info-graphics where mark-by-mark audit is impossible). The Reserved-M5 promotion threshold is monitored: if this mode begins failing on dashboard-orchestration / chart-type-selection / sparkline-specialty cases, surface that signal for orchestrator review per T19 reserved-M5 spec.

## CAVEATS AND OPEN DEBATES

This mode does not carry mode-specific debates. Five territory-level debates (per Decision G) are documented in `Reference — Analytical Territories.md` T19 entry and bear on Information Density specifically:

1. **Spatial vs. compositional framing.** Information Density operates on spatial info-graphics; the temporal generalization (animated charts, slide sequences over time) is partially relevant — the mode handles slide-rhythm and presentation-arc as breadth scanning, but its core operations are on static graphics.
2. **Aesthetic-only or also abstract spatial inputs?** Information Density sits firmly on the *applied-analytical* side of this debate: the traditions (Tufte, Bertin, Cleveland-McGill, Bringhurst, Lupton) operate on functional info-graphics with prescriptive critique, not on aesthetic-experiential reading. The territory's coherence rests on the operation (read spatial structure as primary content with consequence) being shared with aesthetic-experiential modes (ma-reading) and applied-evaluative modes like this one.
3. **Western-analytical and Eastern-aesthetic: same operation or convergent traditions?** Information Density is firmly Western-analytical; the Eastern-aesthetic question bears on the territory's overall framing more than on this mode's internal stance. The Bringhurst case for "page-as-composition" is a Western analog of ma-reading's white-space attention, but applied prescriptively rather than contemplatively.
4. **Verbal accessibility for AI implementation.** Information Density requires direct image input or high-fidelity verbal-spatial description (mark inventory, encoding identification, scale and proportion data, typography specifications) for the data-ink audit and visual-variable mapping check to be performed mark-by-mark. The mode degrades for rough verbal sketch where critical features (which marks carry data vs. decoration; which visual variable encodes which attribute; which elementary task the chart requires) cannot be inferred. This is a real implementation constraint, not academic.
5. **Mode granularity: general vs. tradition-specific.** Whether the Reserved-M5 mode (Information-Graphic Visual-Hierarchy Analysis specialty) should be promoted to a first-class fifth T19 mode. Per T19 reanalysis §3, the promotion threshold is: info-graphic critique exceeds ~15% of T19 invocations, *or* this mode plus Compositional Dynamics outputs on dashboards visibly fail to distinguish encoding-misfit from generic compositional critique. Below threshold, Information Density covers the applied-evaluative info-graphic operations with the four required lenses. Above threshold, dashboard-orchestration / chart-type-selection / sparkline-and-small-multiples specialty would justify a fifth mode. The `m5-promotion-evidence` failure-mode flag is the structural mechanism for surfacing the signal to the orchestrator.

These five debates are *not* re-documented here. They are referenced because they bear on Information Density's stance, lens dependencies, and implementability. See the T19 entry in `Reference — Analytical Territories.md` for the full debate text and citations.
