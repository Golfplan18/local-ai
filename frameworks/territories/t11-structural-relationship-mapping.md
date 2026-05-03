# Framework — Structural Relationship Mapping

*Self-contained framework for extracting relations among entities in a representation — the topology of inter-element connections (textual or visual). Compiled 2026-05-01.*

---

## Territory Header

- **Territory ID:** T11
- **Name:** Structural Relationship Mapping
- **Super-cluster:** E (Synthesis, Orientation, Structure, Generation)
- **Characterization:** Operations that extract relations among entities in a representation (diagram, network, schema) — the topology of inter-element connections.
- **Boundary conditions:** Input is a representation of entities and their relations (textual list, diagram, network graph, organizational chart, schema). Excludes spatial-composition reading (T19 — what the spatial structure does as primary content) and excludes cases where the question is mechanism (T16) or process flow (T17).
- **Primary axis:** Specificity (general relationship mapping vs. visual-input variant).
- **Secondary axes:** None at current population.
- **Coverage status:** Strong (re-home aligns mode with proper territory per Decision G).

---

## When to use this framework

Use T11 when the user has entities and wants their relationships made explicit as a topology — a map of what is connected to what, with the nature of each connection labeled. T11 answers questions like "how do these entities connect?", "what affects what?", "where are the missing connections?", and "is there a feedback loop I haven't drawn?".

Common situations:
- A textual description of a domain that needs to be turned into a relational map.
- A diagram, sketch, or network graph where the user senses something is missing or off and wants gap detection.
- A concept-map exercise where the user wants the structural skeleton of a domain made visible.
- A causal-DAG exercise where the user wants entities and relationships labeled with directionality.

T11 does NOT do mechanism explanation (how the parts produce the whole's behavior — that is T16), process-flow analysis (sequenced steps over time — that is T17), or compositional reading of what the layout itself means (that is T19).

---

## Within-territory disambiguation

```
[Territory identified: structural relationship mapping]

Q1 (specificity): "Is your input a textual description of entities and their relationships,
                    or a visual diagram, network, or schema where the question is
                    what relations the picture asserts (or where relations are missing)?"
  ├─ "textual description / list of entities and relations" → relationship-mapping (Tier-2)
  ├─ "visual diagram / network / schema" → spatial-reasoning
                                            (Tier-2, specificity-visual-input)
  └─ ambiguous → relationship-mapping with escalation hook to spatial-reasoning
```

**Default route.** `relationship-mapping` at Tier-2 when ambiguous (the general atomic mode; `spatial-reasoning` is the visual-input specificity variant doing the same operation on diagrammatic input).

**Escalation hooks.**
- After `relationship-mapping`: if the input becomes visual mid-conversation, switch sideways to `spatial-reasoning`.
- After `spatial-reasoning`: if the question shifts from "what relations does this diagram assert" to "what is the layout itself doing", hook sideways to T19 — this is the canonical T11↔T19 cross-territory disambiguator.
- After either T11 mode: if the question becomes "how does this work", hook sideways to T16 (`mechanism-understanding`).
- After either T11 mode: if the question becomes "how does this flow over time", hook sideways to T17 (`process-mapping`).

---

## Mode entries

### `relationship-mapping` — Relationship Mapping

**Educational name:** structural relationship mapping (general specificity).

**Plain-language description.** Takes a textual description of entities and produces a structured relational map: every entity named, every connection labeled by type (causal, correlational, dependency, influential, structural) and directionality, with any non-obvious cross-links surfaced and the organizing structure (hub-and-spoke, chain, hierarchy, network, bipartite) named. The output is diagram-friendly and acyclic by default; cycles trigger transition to systems-dynamics modes (T4 or T17).

**Critical questions.**
- CQ1: Is every connection labelled with its type (causal / correlational / dependency / influential / structural) and directionality?
- CQ2: Have ≥2 non-obvious connections been surfaced, with at least one cross-link in concept-map outputs?
- CQ3: Is the output structured as a relational map, not flattened into a linear narrative?
- CQ4: Is the output genuinely acyclic — no feedback loops smuggled into a DAG?

**Per-pipeline-stage guidance.**
- **Analyst.** Identify entities, draw connections with type prefixes, name the organizing structure, surface ≥2 non-obvious connections, declare acyclicity.
- **Evaluator.** Check that every connection carries type and directionality; verify ≥1 cross-link in concept-map outputs; verify acyclicity discipline; flag causation-correlation traps.
- **Reviser.** Add type prefixes where missing; surface non-obvious connections where only obvious ones appear; restructure linear narrative as relational map; remove cycles or transition to systems-dynamics.
- **Verifier.** Confirm seven required sections present (focal_question, entities, connections_with_type_and_directionality, organising_structure, key_relationships, boundary_statement, acyclicity_check).
- **Consolidator.** Merge as a diagram-friendly mapping; concept_map envelope when heterogeneous relations dominate; causal_dag envelope when causal framing dominates.

**Source tradition.** Novak concept-map tradition (heterogeneous relations with cross-links); DAGitty / Pearl causal graphs (causal-specific framing with focal exposure and outcome); structural-relationship taxonomy (foundational classification).

**Lens dependencies.**
- Required: none.
- Optional: dagitty-causal-dag-formalism (when causal framing dominates), novak-concept-map-tradition (when heterogeneous relations dominate), pearl-causal-graphs.
- Foundational: structural-relationship-taxonomy.

**Composition.** Atomic.

### `spatial-reasoning` — Spatial Reasoning

**Educational name:** structural gap detection on diagrams (specificity-visual-input variant).

**Plain-language description.** Takes a visual diagram (sketch, whiteboard photo, Excalidraw, Obsidian Canvas, prior Ora visual) where the diagram itself is the question, and performs structural extraction with gap analysis: what's there, what's ambiguous, what's missing (missing nodes, connections, levels, feedback loops). The mode preserves the user's spatial arrangement (annotates without rearranging), uses Tversky correspondence principles (proximity = relatedness, verticality = hierarchy, containment = category, connection = relationship), and generates open fog-clearing questions rather than leading questions.

**Critical questions.**
- CQ1: Does the structural extraction capture all visible entities, relationships, clusters, and hierarchy with ambiguities flagged rather than silently resolved?
- CQ2: Are identified gaps genuine — implied by the spatial structure or domain logic — or are they template pattern-matching artifacts?
- CQ3: Are fog-clearing questions open (eliciting the user's pre-conscious structure) rather than leading (encoding a specific answer)?
- CQ4: Does the mode preserve the user's spatial arrangement — annotating without rearranging?

**Per-pipeline-stage guidance.**
- **Analyst.** Extract structure with ambiguities flagged; apply Tversky correspondence audit; identify gaps with specific spatial or domain evidence; generate open fog-clearing questions; preserve the user's arrangement.
- **Evaluator.** Verify ambiguities flagged not silently resolved; verify gaps cite spatial or domain evidence; verify questions are open not leading; verify rearrangement-trap not triggered.
- **Reviser.** Flag silently-resolved ambiguities; remove gaps lacking evidence; convert leading questions to open ones; resist "cleaner" diagrams.
- **Verifier.** Confirm eight required sections present (structural_summary, ambiguities_flagged, tversky_correspondence_findings, gap_analysis, pattern_identifications, fog_clearing_questions, annotated_visual_output, transition_prompt); confirm canvas_action="annotate" (not "replace"/"update").
- **Consolidator.** Merge as a diagram-friendly mapping with annotation overlay preserving arrangement.

**Source tradition.** Tversky spatial-correspondence principles; structural pattern libraries (hub-and-spoke, chain, cycle, star, cluster bridge, orphan); Larkin-Simon diagram literacy.

**Lens dependencies.**
- Required: tversky-spatial-correspondence-principles.
- Optional: structural-pattern-libraries, systems-archetypes (when causal structure present), larkin-simon-diagram-literacy.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

**Re-home note (per Decision G).** Spatial Reasoning was originally placed in the old T19 territory ("Visual and Spatial Structure"). Decision G renamed T19 to "Spatial Composition" (analyzing what the spatial structure itself does as primary content — voids, groupings, forces, affordances). The mode's actual operation — structural gap detection on diagrammatic input (missing nodes, missing connections, missing levels, missing feedback loops) — is a T11 operation (notice missing relations) on visual-medium input rather than a T19 operation (read the composition's own meaning). Re-homed accordingly: territory is T11, gradation_position is specificity-visual-input, adjacent_modes_in_territory pairs with relationship-mapping (general specificity counterpart). When the user's input is a diagram and the question is about layout / composition / spatial-structure-as-primary-content rather than about the relations the diagram asserts, route to T19 instead.

---

## Cross-territory adjacencies

### T11 ↔ T19 (Structural Relationship ↔ Spatial Composition)

**Why adjacent.** Same input — a diagram or visual artifact — answers different questions. T11 reads the diagram as notation: what relations are asserted among elements. T19 reads the diagram as composition: what the layout itself is doing.

**Disambiguating question.** "Is the question about what relations the diagram asserts among elements, or about what the layout or composition itself is doing?"

**Routing.**
- Relation-extraction (the diagram-as-notation) → T11 (Relationship Mapping / Spatial Reasoning).
- Layout-doing (the diagram-as-composition) → T19 (Compositional Dynamics / Ma Reading / Place Reading / Information Density).

**Examples.**
- "What does this org chart say about reporting lines?" → T11.
- "What is this org chart's layout doing — why does it feel hierarchical even where the lines say it isn't?" → T19.
- "Read this network diagram for me — who's connected to whom?" → T11.
- "This network diagram is dense in the middle and sparse at the edges — what is that doing to the reader?" → T19.
- "Both: tell me what the diagram asserts and what the layout is doing." → T11 + T19 (sequential, T11 first).

**Sequential dispatch note.** When both legitimately fire on the same input, T11 runs first because relation-extraction is the lighter, more determinate operation; T19 layers compositional reading on top of an artifact whose asserted relations have already been characterized.

### T11 ↔ T16 ↔ T17 (Mechanism / Process / Structure cluster)

**Why adjacent.** These three cluster tightly because they all engage with how something works internally — but they ask different questions about it. T16 asks how the gears interlock to produce behavior; T17 asks how the flow runs in sequence; T11 asks how the parts relate as a structure.

**Disambiguating question.** "Is the question about *how* this works (the gears), about the *flow or process* (sequence), or about how the *parts relate* (structure)?"

**Routing.**
- How → T16 (Mechanism Understanding).
- Flow → T17 (Process Mapping / Systems Dynamics Structural).
- Structure → T11 (Relationship Mapping / Spatial Reasoning).

**Sequential dispatch.** When two of the three fire on the same input, the lighter framing typically runs first: T11 (structure) before T17 (process) before T16 (mechanism), because each successive territory builds on the prior.

---

## Lens references (Core Structure embedded)

### Tversky Spatial-Correspondence Principles (required for spatial-reasoning)

**Core Structure.** Tversky's principle: spatial properties of a diagram correspond to conceptual properties through systematic mappings. Four operative correspondences:
- **Proximity = relatedness.** Items placed close together are read as related; items separated as not.
- **Verticality = hierarchy.** Items higher on the page are read as superior, dominant, or earlier; lower as subordinate, weaker, or later.
- **Containment = category.** Items inside a boundary are read as members of the category the boundary names.
- **Connection = relationship.** Items connected by a line/arrow are read as related, with the line carrying directionality if drawn with an arrow.

A spatial-reasoning audit checks whether the user's diagram honors each correspondence (e.g., are related items placed close, or has proximity drifted? Are subordinates below, or has the hierarchy been flipped?). Mismatches between spatial properties and intended conceptual meaning are a primary source of diagram ambiguity.

### Novak Concept-Map Tradition (optional for relationship-mapping)

**Core Structure.** A concept map is a structured relational artifact with three required elements:
- **Concepts** (≥4) at varying hierarchy levels.
- **Linking phrases** (≥2) labeling each connection (e.g., "causes", "is part of", "depends on").
- **Propositions** (≥3) — concept-link-concept triples that read as semantic claims.

A genuine concept map carries at least one **cross-link** (`is_cross_link: true`) — a connection bridging two otherwise-separate sub-trees. Cross-links are Novak's marker of integrative understanding: they indicate the mapper has seen a connection that the standard taxonomy of the domain does not assert.

### DAGitty / Pearl Causal Graphs (optional for relationship-mapping)

**Core Structure.** A causal DAG is an acyclic directed graph where:
- Nodes are variables.
- Edges are causal claims (X → Y means X causes Y).
- The graph is **acyclic** by construction (no node reaches itself by following arrows).
- A focal **exposure** and a focal **outcome** are declared.

The DAG enables identification of confounders (common causes of exposure and outcome that must be controlled for), mediators (variables on the causal path), and colliders (common effects whose conditioning induces spurious association). The acyclicity constraint distinguishes causal DAGs from feedback-system diagrams (which require systems-dynamics modes in T4/T17).

### Structural-Relationship Taxonomy (foundational for relationship-mapping)

**Core Structure.** A controlled vocabulary for connection types:
- **Causal** — A produces or contributes to B; mechanism specifiable.
- **Correlational** — A and B co-vary; mechanism unspecified or unknown.
- **Dependency** — B requires A (A blocks B; A is prerequisite).
- **Influential** — A shapes or constrains B without strict causation.
- **Structural** — A and B stand in a defined formal relation (subset, superset, sibling, etc.).

The taxonomy's discipline: every connection in a relationship map carries a literal type prefix. Defaulting to the weakest type the evidence supports prevents the causation-correlation trap.

### Structural Pattern Libraries (optional for spatial-reasoning)

**Core Structure.** Catalog of recurring topological patterns:
- **Hub-and-spoke** — one central node connects to many peripherals.
- **Chain** — sequential linear connection.
- **Cycle** — closed loop (signals system-dynamics territory).
- **Star** — variant of hub-and-spoke with no peripheral-to-peripheral connections.
- **Cluster bridge** — two dense sub-graphs connected by a thin bridge.
- **Orphan** — node with no connections (signals incomplete map or genuinely isolated entity).

Pattern identification supports gap detection: a hub-and-spoke pattern with one missing spoke may suggest the spoke exists but was not drawn; a chain with a missing link suggests the link is implicit or unknown.

---

## Open debates

T11 carries no territory-level open debates. The Decision G re-home resolved the placement question for `spatial-reasoning` (T19's old name "Visual and Spatial Structure" had created ambiguity; T11 is the proper home for structural gap detection on diagrammatic input, while T19 renamed to "Spatial Composition" for compositional reading). Mode-level debates do not currently apply.

---

## Citations and source-tradition attributions

- Tversky, B. (2005). "Visualizing Thought." *Topics in Cognitive Science*. Foundational treatment of spatial-conceptual correspondence.
- Tversky, B. (2019). *Mind in Motion: How Action Shapes Thought*. Basic Books. Spatial cognition's role in reasoning.
- Novak, J. D. & Cañas, A. J. (2008). *The Theory Underlying Concept Maps and How to Construct and Use Them*. IHMC Cmap Tools. Concept map theory and the cross-link as marker of integrative understanding.
- Pearl, J. (2009). *Causality: Models, Reasoning, and Inference* (2nd ed.). Cambridge University Press. Causal DAG theory.
- Textor, J., Hardt, J., & Knüppel, S. (2011). "DAGitty: A Graphical Tool for Analyzing Causal Diagrams." *Epidemiology*. The DAGitty tool and its DSL.
- Larkin, J. H. & Simon, H. A. (1987). "Why a Diagram is (Sometimes) Worth Ten Thousand Words." *Cognitive Science*. Foundational treatment of diagram literacy.
- Kahneman, D. & Tversky, A. (Various). Heuristics-and-biases catalog (foundational lens for both T11 modes via the bias-catalog substrate).
- Senge, P. M. (1990). *The Fifth Discipline*. System archetypes (used optionally in spatial-reasoning when causal structure surfaces in diagrams).

*End of Framework — Structural Relationship Mapping.*
