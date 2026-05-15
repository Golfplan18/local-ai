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

Spatial Reasoning is read in Tversky's spatial-correspondence-principles vocabulary (proximity = relatedness, verticality = hierarchy, containment = category, connection = relationship), with structural-pattern libraries (hub-and-spoke, chain, cycle, star, cluster-bridge, orphan) as the catalog the gap analysis draws from, Larkin-Simon diagrammatic-representation theory for what diagrams do that text doesn't, and systems-archetype recognition when causal structure is implied. The evaluator's primary axis is *spatial fidelity to the user* — the user's arrangement is signal of their pre-conscious structure, and the methodology surfaces what that arrangement implies without rearranging it or evaluating its correctness. CQ4 (rearrangement-trap) and CQ3 (leading-question) are load-bearing because they protect the elicitation contract: the mode pulls the user's structure into articulation, it does not impose the analyst's. CQ1 (structural-misrepresentation) and CQ2 (gap-fabrication) act as fidelity gates on extraction and gap proposal.

Evaluator checks:

1. **Arrangement preservation (CQ4, load-bearing).** The user's spatial arrangement must be preserved exactly; annotations overlay, entities are never relocated. Rearrangement-trap residue is a "cleaner" version of the user's diagram with entities moved — even subtle relocation is a violation, because the arrangement carries the user's pre-conscious structure. Suggestions for restructuring belong in the transition-prompt section as recommendations, never in the annotated output as modifications. The envelope `canvas_action` must be `annotate`, not `replace` or `update`.

2. **Open fog-clearing questions (CQ3, load-bearing).** Questions targeting the user's structure must be open — willing to accept "no" as an answer. Leading-question residue is "Isn't there a feedback loop between A and B?" which encodes the expected answer; the open form is "What relationship, if any, exists between A and B?" Questions that the user could only answer in one direction are reshaped to admit multiple directions, or downgraded to gap-hypothesis findings rather than questions.

3. **Spatial-extraction fidelity with ambiguities flagged (CQ1).** The structural extraction must capture entities, relationships, clusters, and hierarchy accurately, with ambiguous elements explicitly flagged rather than silently resolved. Structural-misrepresentation residue is a line that may or may not be a connection silently read as a connection; a grouping that may or may not be a cluster silently read as a cluster. The reading discipline: ambiguity is content, not noise, and the deliverable surfaces it.

4. **Gap grounding (CQ2).** Each proposed missing element must cite specific spatial or domain evidence — Tversky-correspondence contradiction (e.g., proximity suggests relatedness that the connections don't draw), structural-pattern implication (an incomplete hub-and-spoke missing its hub), or domain-logic constraint (a feedback-loop the topology implies). Gap-fabrication residue is speculative additions without grounding — "you should add X" with no evidence trail. Gaps without evidence are reshaped or downgraded to questions.

5. **Pattern-in-concept, not pattern-in-pixel.** Where the deliverable identifies a structural pattern, the pattern must be present in the conceptual content of the diagram, not merely in its visual arrangement. Template-projection residue is hub-and-spoke (or cycle, or hierarchy) identified because the arrangement looks like one without verifying that the concepts at the nodes actually instantiate the pattern. Each pattern atom carries a concept-verification atom: yes-or-no, is the pattern present in concept space?

6. **Spatial intuition as signal, not as claim.** The user's diagram is treated as evidence of their pre-conscious structure, not as a proposition to be evaluated. Critic-trap residue is the analyst grading the diagram (right/wrong/inaccurate) rather than surfacing what it contains and implies. The methodology's posture is collaborative articulation — pulling the user's intuition into legible form — not evaluation of whether the intuition was correct.

7. **Confidence calibration to input fidelity.** Rough inputs (napkin sketches, low-resolution photos) carry lower confidence on mark-level claims than structured inputs (Excalidraw JSON, Obsidian Canvas). Confidence inflation on rough input — making fine-grained claims the visual fidelity cannot support — is its own failure mode the evaluator flags.

Where streams disagreed on what's missing (different gap-hypotheses for the same arrangement), the evaluator confirms both are preserved with their respective evidence. Where the structure has crystallised into a specific analytical question (the user is now asking about relations the diagram asserts, not about gaps in the diagram), the evaluator confirms the transition-prompt fires sideways to relationship-mapping or the appropriate analytical mode.

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

7. **Annotated visual output.** One labelled envelope or annotation block. `canvas_action: annotate` (never `replace` / `update`); `target_id` values resolve to entity ids in the user's submitted `spatial_representation`; `annotation kind`: `callout` / `highlight` only; callout text ≤60 characters; one envelope per response.

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
