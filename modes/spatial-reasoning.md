---
nexus:
  - ora
type: mode
tags:
date created: 2026-04-17
date modified: 2026-05-01
wp: WP-3.4
---

# MODE: Spatial Reasoning

```yaml
# 0. IDENTITY
mode_id: spatial-reasoning
canonical_name: Spatial Reasoning
suffix_rule: analysis
educational_name: structural gap detection on diagrams

# 1. TERRITORY AND POSITION
territory: T11-structural-relationship-mapping
gradation_position:
  axis: specificity
  value: visual-input
adjacent_modes_in_territory:
  - mode_id: relationship-mapping
    relationship: specificity counterpart (general specificity — text-input variant of the same operation)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I have a sense of the structure but can't articulate it"
    - "what am I missing in this diagram"
    - "help me see what I'm not seeing"
    - "is there a relationship I haven't drawn"
  prompt_shape_signals:
    - "annotate this"
    - "what's missing"
    - "what node am I missing"
    - "what connection did I forget"
    - "is there a feedback loop I haven't drawn"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user submits a diagrammatic visual input (sketch, whiteboard photo, Excalidraw, Obsidian Canvas, prior Ora visual) AND the diagram IS the question"
    - "gap detection on user-drawn structure: missing nodes, missing connections, missing levels"
  routes_away_when:
    - "diagram is supporting evidence for a text question (text is query, image is context)" → mode matching the text query
    - "user wants a new visual deliverable constructed from scratch" → Project Mode with visual output
    - "user has spatial intuition but no spatial artifact (text-only query)" → relationship-mapping
    - "user wants to read the layout/composition itself as primary content (not the relations the diagram asserts)" → T19 spatial-composition modes
when_not_to_invoke:
  - "Question is about layout, composition, or what the spatial structure itself does as primary content (voids, groupings, forces, affordances)" → T19 (Spatial Composition modes: ma-reading / compositional-dynamics / place-reading-genius-loci / information-density)
  - "User has no spatial artifact and is asking text-only structural questions" → relationship-mapping
  - "User mentions feedback loops in pure text without a diagram" → systems-dynamics-causal or systems-dynamics-structural

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [spatial_artifact_with_resolvable_entity_ids, focal_gap_question]
    optional: [prior_spatial_representation, annotation_palette_preferences, domain_context_for_pattern_matching]
    notes: "Applies when user submits a structured spatial input (Excalidraw JSON, Obsidian Canvas) with addressable entity ids."
  accessible_mode:
    required: [visual_input_napkin_sketch_or_whiteboard_photo_or_canvas]
    optional: [hint_at_what_user_is_uncertain_about]
    notes: "Default. Mode extracts entities and relationships from rough input, flags ambiguities, and surfaces gaps. Confidence is calibrated lower for rough inputs."
  detection:
    expert_signals: ["Excalidraw JSON", "Obsidian Canvas", "annotate this CLD", "target_id", "annotation kind"]
    accessible_signals: ["what's missing", "what do you see", "help me see", "I have a sense but can't articulate"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you share the diagram or canvas you want me to look at, and the question you have about it?'"
    on_underspecified: "Ask: 'Is the diagram itself the question (gap detection — stay here), or is the diagram supporting evidence for a text question (route to the text-question mode)?'"
output_contract:
  artifact_type: mapping
  required_sections:
    - structural_summary
    - ambiguities_flagged
    - tversky_correspondence_findings
    - gap_analysis
    - pattern_identifications
    - fog_clearing_questions
    - annotated_visual_output
    - transition_prompt
  format: diagram-friendly

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Does the structural extraction capture all visible entities, relationships, clusters, and hierarchy with ambiguities flagged rather than silently resolved?"
    failure_mode_if_unmet: structural-misrepresentation
  - cq_id: CQ2
    question: "Are identified gaps genuine — implied by the spatial structure or domain logic — or are they template pattern-matching artifacts?"
    failure_mode_if_unmet: gap-fabrication
  - cq_id: CQ3
    question: "Are fog-clearing questions open (eliciting the user's pre-conscious structure) rather than leading (encoding a specific answer)?"
    failure_mode_if_unmet: leading-question
  - cq_id: CQ4
    question: "Does the mode preserve the user's spatial arrangement — annotating without rearranging?"
    failure_mode_if_unmet: rearrangement-trap

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: rearrangement-trap
    detection_signal: "Mode produces a 'cleaner' version of the user's diagram with entities relocated."
    correction_protocol: re-dispatch (annotate, do not rearrange — propose restructuring as suggestion only)
  - name: template-projection
    detection_signal: "A familiar pattern (hub-and-spoke, cycle, tree) is identified that the spatial arrangement visually suggests but the conceptual content does not actually instantiate."
    correction_protocol: flag (verify pattern is present in concepts, not just pixels)
  - name: gap-fabrication
    detection_signal: "Proposed missing elements are not implied by the spatial structure or domain logic; they are speculative additions."
    correction_protocol: re-dispatch (every gap identification cites specific spatial or domain evidence)
  - name: leading-question
    detection_signal: "Fog-clearing question encodes a specific answer ('Isn't there a feedback loop between A and B?')."
    correction_protocol: re-dispatch (rewrite as open question willing to accept 'no')
  - name: critic-trap
    detection_signal: "Mode evaluates the user's diagram as correct or incorrect rather than treating spatial intuition as signal."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - tversky-spatial-correspondence-principles
  optional:
    - structural-pattern-libraries (hub-and-spoke, chain, cycle, star, cluster bridge, orphan)
    - systems-archetypes (when causal structure present)
    - larkin-simon-diagram-literacy
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "T11 has no heavier mode in the visual-input variant; deeper analysis routes sideways."
  sideways:
    target_mode_id: relationship-mapping
    when: "User abandons the visual input and switches to text-only structural questions."
  downward:
    target_mode_id: null
    when: "Spatial Reasoning is already the lighter end of T11's specificity axis when diagrammatic input is given."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Spatial Reasoning is the rigour of structural extraction and gap analysis on user-drawn input. A thin pass labels what is visible; a substantive pass extracts entities, relationships, clusters, and hierarchy with positions and ambiguities flagged, applies Tversky's correspondence audit (proximity = relatedness, verticality = hierarchy, containment = category, connection = relationship), and identifies gaps with specific spatial or domain evidence per gap. Test depth by asking: would the gap analysis name what to look for in the user's intuition rather than what to add to the diagram?

## BREADTH ANALYSIS GUIDANCE

Breadth in Spatial Reasoning is the catalog of structural patterns considered (hub-and-spoke / chain / cycle / star / cluster bridge / orphan) and the range of fog-clearing questions generated. Widen the lens to identify multiple plausible patterns the arrangement might instantiate, generate open questions targeting different aspects of the user's pre-conscious understanding, and surface the single most consequential gap (the addition that, if real, would most change what the diagram implies). Breadth markers: ≥2 candidate patterns considered (with verification per CQ2); ≥1 fog-clearing question per ambiguity; one most-consequential gap highlighted.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing Spatial Reasoning output: extracts structure accurately with ambiguities flagged; identifies gaps grounded in evidence (not template artifacts); generates open fog-clearing questions; preserves the user's spatial arrangement (annotates without rearranging); treats spatial intuition as signal, not as a claim to be evaluated. Specifically check for the rearrangement trap, template projection (pattern in pixels not in concepts), gap fabrication (speculative additions), and leading questions.

## REVISION GUIDANCE

Revise to flag silently-resolved ambiguities. Revise to remove gaps that lack spatial or domain evidence. Revise to convert leading questions into open ones. Resist revising toward a "cleaner" version of the user's diagram — the arrangement is the user's signal. Resist revising toward judgment of the user's intuition — the mode surfaces what the diagram contains and implies, without ruling on whether the user's intuition is right.

## CONSOLIDATION GUIDANCE

Consolidate as a diagram-friendly mapping with the eight required sections (structural summary / ambiguities flagged / Tversky correspondence findings / gap analysis / pattern identifications / fog-clearing questions / annotated visual output / transition prompt). Format: diagram-friendly. When envelope-bearing: canvas_action must be "annotate" (never "replace" or "update"); target_id values must resolve to entity ids in the user's submitted spatial_representation; annotation kinds limited to "callout" or "highlight"; callout text ≤60 characters; one envelope per response. The user's spatial arrangement is preserved; annotations overlay it.

## VERIFICATION CRITERIA

Verified means: structural extraction faithful to input with ambiguities flagged (not silently resolved); every gap identification cites spatial or domain evidence; fog-clearing questions are open (not leading); user's spatial arrangement preserved (annotations overlay, not relocate); annotation envelope uses canvas_action="annotate" with valid target_ids; transition prompt fires when structure has crystallized into a specific analytical question. The four critical questions are addressed in the output.

## CAVEATS AND OPEN DEBATES

**Re-home from old T19 to T11 per Decision G.** Spatial Reasoning was originally placed in the old T19 territory ("Visual and Spatial Structure"). Decision G renamed T19 to "Spatial Composition" (analyzing what the spatial structure itself does as primary content — voids, groupings, forces, affordances per the Ma Reading / Compositional Dynamics / Place Reading / Information Density mode population). The mode's actual operation — structural gap detection on diagrammatic input (missing nodes, missing connections, missing levels, missing feedback loops) — is a T11 operation (notice missing relations) on visual-medium input rather than a T19 operation (read the composition's own meaning). Re-homed accordingly: territory is T11-structural-relationship-mapping; gradation_position is specificity-visual-input; adjacent_modes_in_territory pairs with relationship-mapping (general specificity counterpart). The mode_id remains `spatial-reasoning` for filename and registry continuity. When the user's input is a diagram and the question is about layout / composition / spatial-structure-as-primary-content rather than about the relations the diagram asserts, route to T19 instead. See `Reference — Analytical Territories.md` §T11 and §T19 and the boundary-verification entry T11 ↔ T19 for the disambiguating question.
