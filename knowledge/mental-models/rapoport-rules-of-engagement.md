---
lens_id: rapoport-rules-of-engagement
name: Rapoport Rules of Engagement
lens_type: protocol
applicability: [red-team-advocate, steelman-construction]
foundational: false
source: "Rapoport, Anatol (1960). Fights, Games, and Debates. University of Michigan Press."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - argumentation
  - steelman
  - critique
---

# Rapoport Rules of Engagement

## Trigger

Invoked when critique must be fair enough that the target view's advocate would recognize it. The host mode supplies the position to reconstruct or attack; the lens supplies Rapoport's construction-before-critique sequence.

## Core Structure

Rapoport's rules, popularized in a similar form by Dennett, discipline criticism by requiring accurate reconstruction first.

1. **Restate the target view clearly and fairly.** The other side should be able to say, "Yes, that is what I mean."
2. **Identify points of agreement.** Name what is true, useful, or shared before disagreement.
3. **State what was learned.** Identify any insight gained from the opposing view.
4. **Then criticize.** Only after the first three steps may the critique begin.

## Application Steps

1. Reconstruct the position in its strongest recognizable form.
2. Preserve identity: do not replace the view with a more convenient argument.
3. List at least two points of agreement or merit when possible.
4. State what the analyst learned or what the view helps reveal.
5. Critique only claims actually present in the reconstruction.
6. Mark any remaining disagreement as substantive, evidentiary, or value-based.

## Detection Signals

- A critique may be attacking a weak or caricatured version of the view.
- A steelman pass needs explicit discipline.
- Red-team advocacy risks becoming hostile rather than useful.
- The output should be acceptable to readers who hold the target view.

## Critical Questions

- Would the target advocate endorse this reconstruction?
- What real merit or shared premise exists?
- What did this view help the analyst see?
- Does the critique address the reconstructed view or drift back to a strawman?
- Which disagreement remains after charity is applied?

## Common Failure Modes

- **Fake charity** - Detection: the reconstruction is polite but still weak. Correction: strengthen until the target advocate would recognize it.
- **Agreement tokenism** - Detection: points of agreement are trivial. Correction: find substantive common ground or say none was found.
- **Critique leakage** - Detection: criticism appears before reconstruction is complete. Correction: enforce sequence.
- **Identity replacement** - Detection: the steelman becomes a different view. Correction: preserve the original commitments.

## Source Citations

- Rapoport, Anatol (1960). *Fights, Games, and Debates*. University of Michigan Press.
- Dennett, Daniel C. (2013). *Intuition Pumps and Other Tools for Thinking*. W. W. Norton.

