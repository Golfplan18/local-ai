---
lens_id: structural-relationship-taxonomy
name: Structural Relationship Taxonomy
lens_type: taxonomy
applicability: [relationship-mapping]
foundational: true
source: "Ora relationship-mapping implementation, informed by semantic-network and concept-map traditions."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - relationship-mapping
  - taxonomy
  - structure
---

# Structural Relationship Taxonomy

## Trigger

Invoked when relationship mapping needs typed edges rather than a generic network. The host mode supplies concepts, entities, claims, or artifacts; the lens supplies a taxonomy of structural relationships so the map can be inspected and reasoned over.

## Core Structure

A relationship map is more useful when each edge says what kind of relation it represents.

Common relationship types:

1. **Causal.** A produces, enables, inhibits, or changes B.
2. **Temporal.** A precedes, follows, overlaps, or recurs with B.
3. **Hierarchical.** A is broader, narrower, parent, child, class, or instance of B.
4. **Part-whole.** A is a component, subsystem, layer, or member of B.
5. **Dependency.** A requires, blocks, gates, or constrains B.
6. **Functional.** A serves, implements, measures, or substitutes for B.
7. **Conceptual.** A defines, reframes, distinguishes, or generalizes B.
8. **Analogical.** A maps structurally onto B.
9. **Oppositional.** A conflicts with, negates, competes with, or trades off against B.
10. **Evidential.** A supports, weakens, exemplifies, or tests B.

## Application Steps

1. List the nodes to be mapped.
2. For each edge, choose the most specific relationship type.
3. Add direction where direction matters.
4. Add a linking phrase that can be read as a claim.
5. Flag ambiguous edges for clarification rather than leaving them generic.
6. Check whether the map contains mixed relation types that should be separated into layers.

## Detection Signals

- A network diagram has many unlabeled links.
- The user needs to understand how ideas relate, not just that they relate.
- Different edge types are being confused.
- A relationship map needs to become actionable or testable.

## Critical Questions

- What kind of relationship is this edge?
- Is the relation directional?
- Can the edge be read as a proposition?
- Are causal, conceptual, and evidential links being mixed?
- Which ambiguous edge changes the interpretation most?

## Common Failure Modes

- **Generic-link fog** - Detection: every edge means "related to." Correction: assign relationship types.
- **Direction erasure** - Detection: dependency or causality is shown as symmetric. Correction: mark direction.
- **Layer collapse** - Detection: causal, hierarchical, and evidential relations clutter one map. Correction: split layers or label clearly.
- **False precision** - Detection: an uncertain relation is over-typed. Correction: mark uncertainty and needed evidence.

## Source Citations

- Novak, Joseph D. and Gowin, D. Bob (1984). *Learning How to Learn*. Cambridge University Press.
- Sowa, John F. (1984). *Conceptual Structures: Information Processing in Mind and Machine*. Addison-Wesley.
- Ora relationship-mapping mode specification.

