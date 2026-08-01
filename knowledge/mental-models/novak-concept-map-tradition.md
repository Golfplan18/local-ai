---
lens_id: novak-concept-map-tradition
name: Novak Concept Map Tradition
lens_type: mapping-framework
applicability: [relationship-mapping, terrain-mapping]
foundational: true
source: "Novak, Joseph D. and Gowin, D. Bob (1984). Learning How to Learn. Cambridge University Press."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - concept-map
  - mapping
  - learning
---

# Novak Concept Map Tradition

## Trigger

Invoked when a mapping mode needs a concept-map standard rather than a loose association graph. The host mode supplies the domain or relationship set; the lens supplies Novak's focus-question, proposition, hierarchy, and cross-link discipline.

## Core Structure

Novak concept maps represent knowledge as concepts connected by labeled relationships that form propositions.

1. **Focus question.** The map answers a specific question.
2. **Concepts.** Nodes are concepts, usually noun phrases.
3. **Linking phrases.** Edges contain words that make a meaningful proposition.
4. **Propositions.** Concept-link-concept units can be read as claims.
5. **Hierarchy.** More general concepts sit above more specific ones.
6. **Cross-links.** Connections across map regions show integrative understanding.
7. **Examples.** Concrete instances can clarify abstract concepts without replacing them.

## Application Steps

1. State the focus question.
2. List the most important concepts.
3. Arrange from general to specific.
4. Add labeled relationships that form readable propositions.
5. Add cross-links between branches where relations are meaningful.
6. Check whether the map reveals structure rather than merely listing topics.

## Detection Signals

- A domain needs orientation for a newcomer.
- Relationship mapping risks becoming an unlabeled node graph.
- Cross-domain links or adjacent concepts matter.
- The output needs propositions that can be inspected for truth.

## Critical Questions

- What focus question is the map answering?
- Can each edge be read as a meaningful proposition?
- Are concepts organized hierarchically?
- Does the map include at least one non-trivial cross-link?
- Are examples clearly distinguished from concepts?

## Common Failure Modes

- **Topic web** - Detection: nodes are connected without labeled propositions. Correction: require linking phrases.
- **No focus question** - Detection: the map sprawls. Correction: state the question before mapping.
- **Flat list** - Detection: no hierarchy appears. Correction: sort general concepts above specific ones.
- **No cross-links** - Detection: branches never integrate. Correction: look for relations across subdomains.

## Source Citations

- Novak, Joseph D. and Gowin, D. Bob (1984). *Learning How to Learn*. Cambridge University Press.
- Novak, Joseph D. and Canas, Alberto J. (2008). "The Theory Underlying Concept Maps and How to Construct and Use Them." IHMC technical report.

