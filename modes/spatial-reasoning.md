---
nexus:
  - ora
type: mode
tags:
date created: 2026-04-17
date modified: 2026-05-24
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

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Spatial Reasoning is Tversky-correspondence structural gap detection on user-drawn diagrammatic input (sketches, whiteboard photos, Excalidraw, Obsidian Canvas, prior Ora visuals). It extracts the diagram's entities, relationships, clusters, and hierarchy, audits them against Tversky's correspondences (proximity = relatedness, verticality = hierarchy, containment = category, connection = relationship), identifies gaps with grounded evidence, and proposes open fog-clearing questions — all while *preserving the user's arrangement* (annotations overlay, never relocate). It is the visual-input variant within T11, distinct from relationship-mapping (text-input general-specificity counterpart), from T19 spatial-composition modes (read the layout itself as primary content), and from systems-dynamics modes (text-only feedback-loop work without diagrammatic input).

**Procedure.**

1. Extract structural elements — entities, relationships, clusters, hierarchy — with positions and ambiguities flagged rather than silently resolved.
2. Audit Tversky correspondences — where the arrangement honours or contradicts proximity = relatedness, verticality = hierarchy, containment = category, connection = relationship.
3. Scan structural-pattern candidates (hub-and-spoke / chain / cycle / star / cluster-bridge / orphan) — apply concept-verification per pattern: is it present in conceptual content, or only in pixels?
4. Identify gaps with specific spatial or domain evidence per gap — Tversky-correspondence contradiction, structural-pattern implication, or domain-logic constraint; mark the most-consequential gap with ★.
5. Generate open fog-clearing questions — willing to accept "no" as an answer; never lead with the expected answer ("Isn't there a feedback loop?" → "What relationship, if any, exists?").
6. Emit annotations that overlay the user's diagram (`canvas_action: annotate`) — entities are never relocated; restructuring suggestions belong only in the transition-prompt section.
7. Treat the user's diagram as signal of pre-conscious structure, not as a claim to be graded right/wrong (critic-trap avoidance).
8. Calibrate confidence lower for rough inputs (napkin sketches, low-resolution photos) than for structured inputs (Excalidraw JSON, Obsidian Canvas).
9. Surface the transition prompt when the structure has crystallised into a specific analytical question — route sideways to relationship-mapping or the matching analytical mode.

**Goal.** Produce a Tversky-correspondence audit on user-drawn input with grounded gap identifications, open fog-clearing questions, and an annotation envelope preserving the user's arrangement.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — structural extraction fidelity.** Does the structural extraction capture all visible entities, relationships, clusters, and hierarchy with ambiguities flagged rather than silently resolved? Failure mode if unmet: `structural-misrepresentation`.
- **CQ2 — gap grounding.** Are identified gaps genuine — implied by the spatial structure or domain logic — or are they template pattern-matching artifacts? Failure mode if unmet: `gap-fabrication`.
- **CQ3 — open fog-clearing questions (load-bearing).** Are fog-clearing questions open (eliciting the user's pre-conscious structure) rather than leading (encoding a specific answer)? Failure mode if unmet: `leading-question`.
- **CQ4 — arrangement preservation (load-bearing).** Does the mode preserve the user's spatial arrangement — annotating without rearranging? Failure mode if unmet: `rearrangement-trap`.

A passing output extracts the diagram faithfully with ambiguities flagged, cites spatial or domain evidence for every gap identification, phrases all fog-clearing questions openly, emits annotations with `canvas_action="annotate"` and valid target_ids, and fires the transition prompt when structure has crystallised into a specific analytical question.

**Named failure modes.**

- *rearrangement-trap* — mode produces a "cleaner" version of the user's diagram with entities relocated.
- *template-projection* — a familiar pattern (hub-and-spoke, cycle, tree) is identified that the spatial arrangement visually suggests but the conceptual content does not actually instantiate.
- *gap-fabrication* — proposed missing elements are not implied by the spatial structure or domain logic; they are speculative additions.
- *leading-question* — fog-clearing question encodes a specific answer ("Isn't there a feedback loop between A and B?").
- *critic-trap* — mode evaluates the user's diagram as correct or incorrect rather than treating spatial intuition as signal.

## REVISION GUIDANCE

Revise to flag silently-resolved ambiguities. Revise to remove gaps that lack spatial or domain evidence. Revise to convert leading questions into open ones. Resist revising toward a "cleaner" version of the user's diagram — the arrangement is the user's signal. Resist revising toward judgment of the user's intuition — the mode surfaces what the diagram contains and implies, without ruling on whether the user's intuition is right.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Tversky-correspondence diagram-gap atom set: structural-extraction atoms with ambiguities explicitly flagged, Tversky-correspondence findings, gap-analysis atoms grounded in spatial or domain evidence, structural-pattern atoms verified against concept-not-pixel, open fog-clearing question atoms, annotation atoms preserving the user's arrangement, and transition-prompt atom**. The atoms are:

1. **Structural-extraction atoms.** Each atom names: entities, relationships, clusters, and hierarchy visible in the input. Where the visual is ambiguous (a line that may or may not be a connection; a grouping that may or may not be a cluster), the ambiguity is flagged rather than silently resolved. Structural-misrepresentation is the named failure mode the consolidator watches for; silent ambiguity resolution gets reshaped to flagged ambiguity.

2. **Tversky-correspondence atoms.** Each atom audits one Tversky correspondence: `proximity = relatedness`, `verticality = hierarchy`, `containment = category`, `connection = relationship`. Where the spatial arrangement contradicts the conceptual structure (e.g., entities that should be hierarchically related are placed at the same level), the contradiction is surfaced.

3. **Gap-analysis atoms.** Each atom names: a potentially missing entity, relationship, or level, plus the specific spatial or domain evidence implying it. Gap-fabrication is the named failure mode; gaps without spatial or domain grounding get reshaped or removed.

4. **Structural-pattern atoms.** Each atom names a pattern (`hub-and-spoke` / `chain` / `cycle` / `star` / `cluster-bridge` / `orphan`) and a *verification* atom: the pattern is present in concepts, not just in pixels. Template-projection is the named failure mode; patterns visible in arrangement but not in conceptual content get reshaped or flagged.

5. **Open fog-clearing question atoms.** Each atom is a question targeting the user's pre-conscious structure, phrased openly (willing to accept "no" as an answer). Leading-question is the named failure mode; questions that encode a specific answer (`Isn't there a feedback loop between A and B?`) get reshaped to open form (`What relationship, if any, exists between A and B?`).

6. **Annotation atoms — preserving arrangement.** Each annotation overlays the user's diagram (callout / highlight) without relocating entities. Rearrangement-trap is the named failure mode; "cleaner" versions of the user's diagram with entities relocated get reshaped to overlay-only annotations.

7. **Transition-prompt atom — when applicable.** When the structure has crystallised into a specific analytical question (the user is now asking about relations the diagram asserts, not about gaps in the diagram), the transition-prompt fires sideways to relationship-mapping or to the appropriate analytical mode.

8. **Critic-trap flag — when applicable.** Where the corpus evaluated the user's diagram as correct or incorrect rather than treating spatial intuition as signal, the flag is preserved. Critic-trap is the named failure mode.

9. **Confidence per finding.** Confidence is calibrated lower for rough inputs (napkin sketches, low-fidelity photos) than for structured inputs (Excalidraw JSON, Obsidian Canvas).

**Mode-specific bloat patterns to cut:**

- **Silent ambiguity resolution** — ambiguous visual elements interpreted without flagging.
- **Gap fabrication** — proposed missing elements without spatial or domain evidence.
- **Template projection** — patterns identified that are present in pixels but not in concepts.
- **Leading questions** — fog-clearing questions that encode the expected answer.
- **Rearrangement** — "cleaner" versions of the user's diagram; the arrangement is the user's signal.
- **Critic posture** — evaluating the user's diagram as right/wrong rather than surfacing what it contains and implies.
- **Confidence inflation on rough input** — making mark-by-mark claims that the visual fidelity cannot support.

**What NOT to collapse:**

- **Flagged ambiguities** — these are the load-bearing findings; they surface what the diagram does not yet decide.
- **Multiple plausible pattern identifications** — when an arrangement could instantiate more than one structural pattern, both survive with verification per CQ2.
- **Stream disagreement about what's missing** — when streams identified different gaps, both survive with their respective evidence.
- **User's arrangement** — never reorganised, even subtly. Suggestions for restructuring sit in the transition-prompt, not in the deliverable's primary layer.

## VERIFICATION CRITERIA

Verified means: structural extraction faithful to input with ambiguities flagged (not silently resolved); every gap identification cites spatial or domain evidence; fog-clearing questions are open (not leading); user's spatial arrangement preserved (annotations overlay, not relocate); annotation envelope uses canvas_action="annotate" with valid target_ids; transition prompt fires when structure has crystallized into a specific analytical question. The four critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **diagram-gap annotation deliverable** — a Tversky-correspondence audit on user-drawn input, with grounded gap identifications, open fog-clearing questions, and annotation envelope preserving the user's arrangement. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Structural summary.** One paragraph naming the visible entities, relationships, clusters, and hierarchy. Ambiguities surface inline with explicit flags (`possible / ambiguous / unclear`).

2. **Ambiguities flagged.** Bulleted list. Each: `**[Ambiguity]** — what's visually ambiguous: [...]. Interpretations possible: [...]. Why this matters for the diagram's reading: [...].`

3. **Tversky correspondence findings.** A table or labelled block per correspondence:
   - `**Proximity = relatedness:** [where the arrangement honours / contradicts this].`
   - `**Verticality = hierarchy:** [where the arrangement honours / contradicts this].`
   - `**Containment = category:** [where the arrangement honours / contradicts this].`
   - `**Connection = relationship:** [where the arrangement honours / contradicts this].`

4. **Gap analysis.** Bulleted list. Each: `**[Potentially missing element]** — kind: [entity / relationship / level]. Spatial or domain evidence implying it: [...]. Most consequential gap (the addition that, if real, would most change the diagram's implications): [marked with **★**].`

5. **Pattern identifications.** Bulleted list. Each: `**[Pattern — hub-and-spoke / chain / cycle / star / cluster-bridge / orphan]** — pixel-evidence: [...]. Concept-verification: [is this pattern present in the conceptual content, or only in the arrangement]. Confidence: [high / medium / low].`

6. **Fog-clearing questions.** Numbered list of open questions targeting the user's pre-conscious structure. Each: `[N]. [Open question phrased to accept "no" as an answer].` Leading questions get reshaped at this layer.

7. **Annotated visual output.** One labelled envelope or annotation block. `canvas_action: annotate` (never `replace` / `update`); one envelope per response.

   - **Path A (structured input):** when the user submitted a structured `spatial_representation` with resolvable entity ids (Excalidraw JSON, Obsidian Canvas), emit `type: <existing diagram type>` and reference entities by `target_id` in each annotation. `annotation kind`: `callout` / `highlight`. Callout text ≤60 characters.

   - **Path B (photo or unstructured visual input):** when the user attached a photograph, whiteboard snapshot, or other raster image with no addressable entity ids, emit `type: annotated_image` and reference positions by normalized image-relative coordinates. The backdrop is the user's uploaded image (already on the visual panel's `backgroundLayer`). Each annotation carries `kind: callout | box | highlight | arrow | text`, plus normalized `x: 0–1` and `y: 0–1` (top-left origin) for its anchor point. Box and highlight may additionally carry `width: 0–1` and `height: 0–1`; arrow carries `to_x: 0–1` and `to_y: 0–1` for the endpoint. Callout text ≤60 characters. Coordinates are anchored to the image's drawn bounds, so 0.5/0.5 is the centre of the image regardless of pixel resolution.

     Envelope skeleton:

     ```json
     {
       "schema_version": "0.2",
       "id": "spatial-reasoning-annotations",
       "type": "annotated_image",
       "mode_context": "spatial-reasoning",
       "relation_to_prose": "integrated",
       "canvas_action": "annotate",
       "spec": { "image_source": { "kind": "user_upload" } },
       "annotations": [
         { "kind": "callout",  "x": 0.42, "y": 0.31, "text": "missing edge: training → champions" },
         { "kind": "box",      "x": 0.65, "y": 0.55, "width": 0.18, "height": 0.12, "text": "under-specified cluster" },
         { "kind": "arrow",    "x": 0.22, "y": 0.40, "to_x": 0.50, "to_y": 0.40, "text": "proposed connection" }
       ],
       "semantic_description": { /* per the envelope contract */ }
     }
     ```

8. **Transition prompt.** One paragraph (when applicable). `If the diagram has crystallised into a specific analytical question, the appropriate sideways-route is: [relationship-mapping for general-specificity continuation / specific analytical mode that matches the new question]. If gap-detection is still active, stay here.`

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- Tversky's four correspondences (`proximity = relatedness`, `verticality = hierarchy`, `containment = category`, `connection = relationship`) appear verbatim with their operative meanings.
- The user's spatial arrangement is *preserved*. Annotations overlay; entities are never relocated. Suggestions for restructuring sit in the transition prompt as recommendations, not in the annotated output as modifications.
- Fog-clearing questions (section 6) are open. Questions that encode the expected answer are reshaped at this layer.
- Pattern identifications (section 5) carry a *concept-verification* atom — the pattern must be present in the conceptual content, not just in the spatial arrangement. Template-projection gets reshaped to flagged-only pattern.
- When input fidelity is low (napkin sketch / low-resolution photo), the deliverable opens with: `**Note: input fidelity is low; confidence on mark-level findings is correspondingly reduced. Major structural findings are preserved; mark-specific claims should be treated as inferred rather than directly observed.**`
- When the critic-trap flag survived consolidation, the deliverable opens with: `**Note: the user's diagram is treated as signal of pre-conscious structure, not as a claim to be evaluated as right or wrong. Gap identifications surface what the diagram does not yet contain, without ruling on the user's intuition.**`

## CAVEATS AND OPEN DEBATES

**Re-home from old T19 to T11 per Decision G.** Spatial Reasoning was originally placed in the old T19 territory ("Visual and Spatial Structure"). Decision G renamed T19 to "Spatial Composition" (analyzing what the spatial structure itself does as primary content — voids, groupings, forces, affordances per the Ma Reading / Compositional Dynamics / Place Reading / Information Density mode population). The mode's actual operation — structural gap detection on diagrammatic input (missing nodes, missing connections, missing levels, missing feedback loops) — is a T11 operation (notice missing relations) on visual-medium input rather than a T19 operation (read the composition's own meaning). Re-homed accordingly: territory is T11-structural-relationship-mapping; gradation_position is specificity-visual-input; adjacent_modes_in_territory pairs with relationship-mapping (general specificity counterpart). The mode_id remains `spatial-reasoning` for filename and registry continuity. When the user's input is a diagram and the question is about layout / composition / spatial-structure-as-primary-content rather than about the relations the diagram asserts, route to T19 instead. See `Reference — Analytical Territories.md` §T11 and §T19 and the boundary-verification entry T11 ↔ T19 for the disambiguating question.


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

**Prioritize:** `parent`, `child`, `produces`, `enables`, `requires`
**Deprioritize:** `contradicts`, `supersedes`

*Family: mechanism-structure. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
