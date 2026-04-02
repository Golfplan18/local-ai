---
title: relationship-mapping
nexus: obsidian
type: mode
writing: no
date created: 2026/03/23
date modified: 2026/03/31
---

# MODE: Relationship Mapping

## TRIGGER CONDITIONS

Positive triggers: "How do these connect," systems analysis, causal modeling, dependency graphs, "what affects what," mapping the structure of a situation rather than analyzing it linearly. The user wants to understand a network of relationships rather than reach a conclusion.

Negative triggers: IF the relationships involve feedback loops, delays, emergent behavior, or counterintuitive dynamics, THEN route to Systems Dynamics — Relationship Mapping is structural and static; Systems Dynamics adds temporal behavior. IF the user wants to understand a single concept deeply rather than its connections, THEN route to Deep Clarification.

## EPISTEMOLOGICAL POSTURE

Structure is the primary analytical object. The relationships between entities are as important as the entities themselves. The output is a relational map — entities, connections, directionality, and types of relationship — not a linear narrative. Correlation is distinguished from causation. Dependency is distinguished from influence. Association is distinguished from mechanism.

## DEFAULT GEAR

Gear 3. Sequential adversarial review is sufficient. The Breadth model maps the relationship structure; the Depth model challenges whether connections are genuine, whether directionality is correct, and whether relationships have been miscategorized.

## RAG PROFILE

Retrieve structural analyses, systems descriptions, dependency documentation, and relational frameworks from the relevant domain. IF the mapped entities include items in the user's vault, retrieve those notes for context. Favor sources that describe how things connect over sources that describe what things are.

## DEPTH MODEL INSTRUCTIONS

White Hat directives:
1. For each proposed connection, assess the type: causal (A causes B), correlational (A and B co-occur), dependency (A requires B), influential (A affects B's probability or magnitude), or structural (A and B share a common structure).
2. For causal and influential connections, assess directionality — is the relationship unidirectional or bidirectional?
3. Identify connections that are missing — entities that should be connected based on domain knowledge but are not represented in the Breadth model's map.

Black Hat directives:
1. Challenge at minimum two connections in the map. For each: is this a genuine connection or an assumed one? What evidence supports the relationship?
2. Identify where the map presents correlation as causation or assumption as established relationship.
3. Assess the map's completeness — are any important entities or connections missing?

## BREADTH MODEL INSTRUCTIONS

Green Hat directives:
1. Identify all entities relevant to the user's question and map the connections between them.
2. For each connection, state the type (causal, correlational, dependency, influential, structural) and directionality.
3. Identify at minimum two non-obvious connections — relationships that are not immediately apparent but emerge from structural analysis.

Yellow Hat directives:
1. Identify which relationships are most important — which connections, if disrupted, would change the most about the system?
2. Surface the organizing structure — is there a hierarchy, a network, a hub-and-spoke pattern, or some other structural pattern in the relationships?
3. Note where the map connects to other domains or systems the user is working on.

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Relational Precision.** 5=every connection has a stated type and directionality, and the distinction between causal, correlational, and dependency relationships is maintained. 3=types stated but one connection miscategorized. 1=connections presented without type or directionality.
6. **Structural Completeness.** 5=all significant entities and connections represented, including at minimum two non-obvious connections. 3=major entities and connections present but non-obvious connections missing. 1=significant entities or connections omitted.
7. **Map vs. Narrative.** 5=output is structured as a relational map with entities and connections, not as a linear narrative. 3=relational structure present but embedded in narrative prose. 1=output is a linear narrative about the entities without explicit relational structure.

## CONTENT CONTRACT

The output is complete when it contains:

1. **Entities** — all relevant entities identified and named.
2. **Connections** — relationships between entities with type (causal, correlational, dependency, influential, structural) and directionality for each.
3. **Organizing structure** — the overall pattern of the relational map (hierarchy, network, hub-and-spoke, or other).
4. **Key relationships** — which connections are most significant, with reasoning.
5. **Boundary statement** — what the map does not include and what would be needed to extend it.

## KNOWN FAILURE MODES

**The Linear Reduction Trap:** Flattening a network of relationships into a sequential narrative ("A leads to B which causes C"). Correction: Present the map as a structure, not a story. IF the structure is a network, present it as a network.

**The Kitchen Sink Trap:** Including every conceivable entity and connection, producing a map so dense it conveys no structure. Correction: Identify the entities and connections that are significant to the user's question. Peripheral entities and weak connections can be noted as boundary elements without full mapping.

**The Causation-Correlation Trap:** Labeling correlational relationships as causal without evidence for the causal mechanism. Correction: Default to the weakest relationship type that the evidence supports. Upgrade only when mechanistic evidence justifies it.

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN the analysis moves toward recommending an action based on the map, THEN pause — Relationship Mapping produces structural understanding, not action recommendations.

**Structure-over-narrative guard rail.** IF the output is structured as a linear narrative, restructure it as an explicit relational map before presenting.

**Humility guard rail.** Every map is a simplification. State what the map omits and what assumptions govern its boundary.

## TOOLS

Tier 1: CAF (identify all entities and factors), RAD (recognize what kind of structure this is, analyze components, divide if multiple systems are conflated), OPV (if entities include stakeholders, map their relational positions), C&S (if connections have temporal dynamics, map consequences across time horizons — but if temporal dynamics are dominant, consider transition to Systems Dynamics).

Tier 2: Module 3 — Structural Analysis (diagramming, flow charting, decision tree questions).

## TRANSITION SIGNALS

- IF the map reveals feedback loops, delays, emergent behavior, or counterintuitive dynamics → propose **Systems Dynamics**.
- IF the relational structure reveals institutional interests or distributional patterns → propose **Cui Bono**.
- IF the user wants to understand one specific relationship deeply → propose **Deep Clarification**.
- IF the user begins defining a deliverable based on the map → propose **Project Mode**.
- IF the mapped relationships span multiple domains with structural parallels → propose **Synthesis**.
