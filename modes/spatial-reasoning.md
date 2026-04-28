---
nexus: obsidian
type: mode
date created: 2026/04/17
date modified: 2026/04/17
wp: WP-3.4
---

# MODE: Spatial Reasoning

## TRIGGER CONDITIONS

Positive triggers: The user submits visual input as the primary query medium — a napkin sketch, a whiteboard photo, an Excalidraw export, an Obsidian Canvas file, drawings on the visual pane, or annotations on a prior Ora visual output. Fog-clearing language: "what do you see," "what's missing," "what am I missing in this diagram," "what does this tell me," "help me see what I'm not seeing," "I have a sense of the structure but can't articulate it." Annotation-request language: "can you annotate this," "annotate this causal structure," "mark up this diagram," "point out what's missing." Gap-language targeting the user's own drawing: "is there a feedback loop I haven't drawn," "what relationships are implied but not shown," "what node am I missing," "what connection did I forget." The diagram IS the question rather than an illustration accompanying a text question.

Negative triggers: IF the user submits a diagram as supporting evidence for a text question (the text is the query, the image is context), THEN route to the mode matching the text query. IF the user is requesting construction of a new visual deliverable from scratch, THEN route to Project Mode with visual output. IF the user is presenting multiple diagrams or models for eliminative comparison, THEN route to Competing Hypotheses. IF the user has spatial intuition they want to verbalize and expects the system to do analytical work on the verbalization rather than on the spatial arrangement, THEN route to Relationship Mapping. IF the user mentions feedback loops but has NO spatial artifact (no visual pane input, no uploaded image, no annotation target), THEN route to Systems Dynamics — mentions of feedback-loop behavior in pure-text queries are not spatial. IF the user has a spatial artifact AND asks about feedback loops as a structural gap ("what feedback loop is missing," "is there a loop I haven't drawn"), THEN stay in Spatial Reasoning — the diagram is the query, the feedback-loop vocabulary describes the structural finding.

## EPISTEMOLOGICAL POSTURE

Spatial arrangement is a form of thinking, not a representation of thinking already completed. The parallel processor constructs spatial relationships faster than the serial processor can articulate them. The user's sketch is therefore signal about their pre-conscious understanding, not a claim to be verified. The mode's work is to help the user see what their spatial intuition was encoding — proximity, verticality, connection, containment, symmetry — and to surface what the structure implies but does not explicitly show. Tversky's correspondence principles (proximity = relatedness, verticality = hierarchy, containment = category membership, connection = relationship) provide the diagnostic lens. Gaps and ambiguities in the spatial input are first-class findings, not problems to be resolved unilaterally.

## DEFAULT GEAR

Gear 3. Full structural analysis with gap identification, pattern recognition, and fog-clearing dialogue is the standard operating depth. Gear 2 for quick structural summaries (most prominent pattern + single most important gap). Gear 4 for deep structural analysis with cross-domain pattern matching, second-order gap analysis, and explicit Tversky correspondence audit.

## RAG PROFILE

Retrieve Tversky's spatial cognition research, diagram literacy frameworks (Larkin & Simon 1987, Mayer's multimedia principles), structural pattern libraries (hub-and-spoke, chain, cycle, star, cluster bridge, orphan), causal loop archetype references, and domain-specific structural references relevant to the depicted subject. Retrieve prior Ora visual outputs from the conversation history if the user is annotating one. Deprioritize text-only analytical frameworks — the input is spatial, and the analysis should stay close to the spatial primitives.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `enables`, `contains`, `precedes`, `parent`, `requires`
**Deprioritize:** `supersedes`, `contradicts`
**Rationale:** Spatial reasoning operates on structural relationships that correspond to Tversky's natural mappings — containment, hierarchy, and enabling connections are the primary spatial semantics.

### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

*Token measurements to be calibrated during Phase 8E testing.*

## DEPTH MODEL INSTRUCTIONS

White Hat directives:
1. Extract entities, relationships, clusters, and hierarchy from the spatial input. Record positions, types, and any labels. Flag ambiguous elements (a line that might be a relationship or a boundary, a cluster that might be intentional or accidental) rather than resolving them.
2. Apply Tversky's correspondence audit as diagnostic questions: Are proximities meaningful? Does vertical position track importance or abstraction? Are there unconnected proximities that suggest implicit relationships? Do boundaries correspond to coherent categories?
3. Perform gap analysis — missing nodes implied by the structure, missing connections implied by proximity or by the logic of existing connections, missing hierarchical levels, missing feedback loops, boundary problems (clusters that should split or merge).

Black Hat directives:
1. For each proposed gap, verify it is genuine and not template pattern-matching. A hub-and-spoke identification requires actual high-degree centrality, not just one well-connected node.
2. Challenge structural pattern labels — is the identified pattern actually present in the domain, or is the mode projecting a pattern the spatial arrangement happens to suggest but the concepts do not actually instantiate?
3. Assess whether proposed additions respect the user's spatial arrangement. Annotations that rearrange rather than overlay violate the mode's commitment to the user's intuition.

## BREADTH MODEL INSTRUCTIONS

Green Hat directives:
1. Identify known structural patterns in the arrangement — hub-and-spoke, chain, cycle, star, cluster bridge, orphan — and state what each pattern typically implies for the domain.
2. Generate fog-clearing questions that help the user articulate what the spatial arrangement is encoding. Questions should be open ("Is there a relationship you're sensing but haven't named yet?") rather than leading ("Isn't there a feedback loop here?").
3. Propose refinements as annotations overlaid on the user's original, never as replacements. Use a distinct overlay palette (suggest: blue for additions, orange for questions, red for structural warnings).

Yellow Hat directives:
1. Identify the single most consequential gap — the addition that, if real, would most substantially change what the diagram implies. Highlight it.
2. Identify structural crystallization signals — points where the spatial input is becoming specific enough to warrant transition to an answer-seeking analytical mode (Systems Dynamics, Decision Under Uncertainty, Steelman Construction, Consequences and Sequel, Terrain Mapping).
3. Frame findings so the user can evaluate them against their own intuition. The mode does not claim to be right; it surfaces what the structure says and lets the user confirm or revise.

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Structural Fidelity.** 5=extraction captures all visible entities, relationships, clusters, and hierarchy with correct positions and ambiguities flagged. 3=extraction is substantially correct but one significant element missed or forced. 1=extraction misrepresents the input or silently resolves ambiguities.
6. **Gap Genuineness.** 5=all identified gaps are genuine (implied by the spatial structure or domain logic), not template artifacts. 3=most gaps genuine but one is a pattern-match that doesn't fit the domain. 1=gaps are speculative additions not grounded in the input.
7. **Fog-Clearing Quality.** 5=questions are open, specific to the user's input, and help the user articulate pre-conscious structure. 3=questions are useful but one leads toward a pre-formed structure rather than surfacing the user's. 1=questions impose an interpretation rather than eliciting one.

## CONTENT CONTRACT

The output is complete when it contains:

1. **Structural summary** — what the diagram shows: entities, typed relationships, clusters, hierarchy.
2. **Ambiguities flagged** — elements whose interpretation is unclear, presented to the user for resolution.
3. **Tversky correspondence findings** — where spatial cues (proximity, verticality, containment) suggest meaning that may or may not be intended.
4. **Gap analysis** — missing nodes, missing connections, missing levels, missing feedback, boundary problems.
5. **Pattern identifications** — known structural patterns present, with what each pattern implies.
6. **Fog-clearing questions** — open questions helping the user articulate what the arrangement encodes.
7. **Annotated visual output** — the user's original spatial arrangement overlaid with Ora's annotations (missing-connection indicators, gap markers, pattern labels, structural warnings).
8. **Transition prompt** — if structure has crystallized into a specific analytical question, propose the appropriate next mode.

## EMISSION CONTRACT

Spatial Reasoning produces a response containing BOTH prose (the seven content-contract sections above) AND exactly one fenced `ora-visual` block with `canvas_action: "annotate"`. The prose arrives first; the envelope follows as the final block of the response.

### Envelope shape (annotate)

```ora-visual
{
  "id": "sr-<slug>",
  "version": "0.2",
  "type": "<visual_type_from_mode_to_visual>",
  "title": "Annotated gap analysis",
  "mode_context": "spatial-reasoning",
  "relation_to_prose": "visually_native",
  "canvas_action": "annotate",
  "annotations": [
    { "target_id": "<user_entity_id>", "kind": "callout",  "text": "<one-line gap description>" },
    { "target_id": "<user_entity_id>", "kind": "highlight", "color": "#FF5722" }
  ],
  "spec": { /* Required for schema validity — may reuse the user's spatial_representation as a minimal CLD or concept_map spec when no new structure is being proposed. */ },
  "semantic_description": { "short_alt": "...", "level_1_elemental": "...", "level_2_summary": "...", "level_3_trends": "..." }
}
```

### Emission rules

1. **`canvas_action` must be `"annotate"`** — never `replace` or `update`. The user's spatial arrangement is sacred (Rearrangement Trap); the envelope overlays findings onto the user's existing canvas without redrawing.
2. **`target_id` values must resolve to entity ids** present in the user's submitted `spatial_representation` (the ids that arrive inside the `=== USER SPATIAL INPUT ===` block in the system prompt). Do NOT invent new ids; the visual panel's `_computeTargetBox` looks them up on the rendered SVG and emits `W_ANNOTATION_TARGET_MISSING` when they're absent.
3. **`kind` must be `"callout"` or `"highlight"`** — `"arrow"` and `"badge"` are deferred to WP-5.1 and emit `W_ANNOTATION_KIND_DEFERRED` warnings.
4. **One annotation per finding** — prefer a few well-placed callouts over many overlapping ones. Use `highlight` for a single primary gap (the most consequential missing element) and `callout` for up to three secondary observations.
5. **Callout text is one line, ≤ 60 characters** — the callout bubble is narrow; longer text truncates.
6. **`visual_type` resolves from mode-to-visual.json** — for Spatial Reasoning the allowed types are `concept_map`, `causal_loop_diagram`, `flowchart`, and `custom_annotated_svg`. Pick the type that matches the structural semantics of the user's input (feedback loops → `causal_loop_diagram`; typed propositions → `concept_map`).
7. **Emit no `ora-visual` block at all** if no annotation is warranted — prose alone is acceptable. The visual panel treats absent envelopes as no-op, not as a clear.

### What NOT to emit

- **Do not** emit `canvas_action: "replace"` — this would wipe the user's drawing and violate the preserve-arrangement guard rail.
- **Do not** emit `canvas_action: "update"` — this replaces the backgroundLayer artifact with a fresh render; the user's spatial arrangement would be redrawn by Ora's layout engine rather than preserved as-is.
- **Do not** invent `target_id` strings that don't appear in the user's spatial input. The annotation will silently render nothing.
- **Do not** emit multiple `ora-visual` blocks per turn — one envelope per response.

## KNOWN FAILURE MODES

**The Rearrangement Trap:** Producing a "cleaner" version of the user's diagram with entities moved to new positions. Correction: Preserve the user's spatial arrangement. Annotate; do not rearrange. If the original layout is confusing, say so in prose and offer the user the option to request a restructuring — do not perform it unilaterally.

**The Template Projection Trap:** Identifying a familiar structural pattern (hub-and-spoke, cycle, tree) that the spatial arrangement visually suggests but the conceptual content does not actually instantiate. Correction: Verify the pattern is present in the concepts, not just in the pixels. A high-degree node is not automatically a hub.

**The Gap Fabrication Trap:** Proposing missing elements that neither the spatial structure nor the domain actually implies. Correction: Every gap identification must cite the specific spatial or domain evidence that implies it. "There's a proximity between X and Y but no connecting line" is evidence. "Concept maps usually have cross-links" is not.

**The Leading Question Trap:** Asking fog-clearing questions that encode a specific answer ("Isn't there a feedback loop between A and B?"). Correction: Questions must be open ("Is there a relationship between A and B you're sensing but haven't drawn?") and must be willing to accept "no" as the correct answer.

**The Critic Trap:** Evaluating the user's diagram as correct or incorrect. Correction: The spatial intuition is signal, not a claim. The mode surfaces what the diagram contains, implies, and might be missing — without judging whether the user's intuition is right.

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN proposing an addition to the user's diagram, THEN verify it is grounded in either spatial evidence from the input or established domain logic — not in template pattern completion.

**Preserve-arrangement guard rail.** The user's spatial arrangement persists. Annotations overlay; they do not relocate. If a substantive restructuring would genuinely help, propose it as a suggestion in the text pane and wait for the user's consent before acting.

**Confidence calibration guard rail.** Confidence is higher for formal inputs (Excalidraw JSON, Obsidian Canvas) and lower for rough inputs (napkin sketches, whiteboard photos). Low-confidence extractions must be flagged, not presented as certain.

**Intuition-as-signal guard rail.** Treat the user's spatial choices as informative about their pre-conscious understanding. Do not silently correct, tidy, or "improve" their arrangement.

## TOOLS

Tier 1: RAD (recognize what the diagram is trying to describe, divide if multiple concerns are conflated), CAF (enumerate all visible entities and relationships), C&S (trace what the identified structure implies forward), Challenge (test whether identified patterns are genuine vs template artifacts).

Tier 2: No default module. Load domain modules based on the subject matter the diagram depicts — Engineering Analysis for technical systems diagrams, Political Analysis for institutional/policy diagrams, etc.

Enrichment frameworks: Tversky's spatial correspondence principles. Structural pattern libraries (hub-and-spoke, chain, cycle, star, cluster bridge, orphan). Systems archetypes for pattern recognition when causal structure is present.

## TRANSITION SIGNALS

- IF causal structure with feedback crystallizes → propose **Systems Dynamics**.
- IF backward causal tracing is needed → propose **Root Cause Analysis**.
- IF decision structure emerges (branches, probabilities, payoffs) → propose **Decision Under Uncertainty** or **Constraint Mapping**.
- IF argument structure emerges (claims, objections, supports) → propose **Steelman Construction** or **Dialectical Analysis**.
- IF forward causal cascade structure emerges → propose **Consequences and Sequel**.
- IF the diagram reveals a domain map the user wants oriented in → propose **Terrain Mapping**.
- IF the user begins defining a deliverable → propose **Project Mode**.
- IF the spatial input is serving as supporting evidence for a text question that now wants answering → propose the mode matching the text question.
