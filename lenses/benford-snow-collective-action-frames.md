---
lens_id: benford-snow-collective-action-frames
name: Benford Snow Collective Action Frames
lens_type: optional-lens
applicability: [frame-comparison]
foundational: false
source: "Benford, Robert D. and Snow, David A. (2000). Framing Processes and Social Movements. Annual Review of Sociology."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - optional
  - framing
  - social-movements
---

# Benford Snow Collective Action Frames

## Trigger

Invoked from `frame-comparison` when the host analysis needs the specialized optional perspective named by this lens. The host mode supplies the case, artifact, decision, or conflict; the lens supplies a bounded check focused on this tradition: Examines movement frames through diagnostic, prognostic, motivational, resonance, and mobilization functions.

## Core Structure

Examines movement frames through diagnostic, prognostic, motivational, resonance, and mobilization functions. Use this lens as an optional focusing device inside `frame-comparison`, not as a replacement for the host mode's full contract.

The lens asks the analyst to separate five things:

1. **Object.** What concrete claim, artifact, actor, system, or decision is being examined?
2. **Fit.** Why is this optional lens relevant here rather than merely name-dropped?
3. **Mechanism.** What specific distinction, pattern, or causal logic does the lens add?
4. **Evidence.** What in the prompt or retrieved context supports applying it?
5. **Limit.** Where does the lens stop being useful or become misleading?

## Application Steps

1. State the object of analysis in one sentence.
2. State why `benford-snow-collective-action-frames` is relevant to this case.
3. Apply the lens's central distinction or pattern to the evidence at hand.
4. Identify what the host mode would miss without this optional perspective.
5. Mark uncertainty, counterexamples, or scope limits.
6. Return the result to the host mode as an enrichment, not a standalone verdict.

## Detection Signals

- The host mode's ordinary analysis is correct but too generic for this case.
- The prompt contains cues that match the named tradition or pattern.
- A user would benefit from a more specialized vocabulary for the issue.
- The evidence supports a focused optional pass without forcing the lens.

## Critical Questions

- What makes this lens applicable in this case?
- Which concrete evidence supports the lens application?
- What new distinction or warning does the lens add?
- What would change if the lens were removed?
- Where could this lens overreach or distort the host analysis?

## Common Failure Modes

- **Name-dropping** - Detection: the lens is mentioned but no case-specific distinction is applied. Correction: state the mechanism and evidence.
- **Lens override** - Detection: the optional lens replaces the host mode's required output. Correction: return it as an enrichment only.
- **Forced fit** - Detection: weak cues are stretched to justify the lens. Correction: mark the lens inapplicable or low-confidence.
- **Source drift** - Detection: the lens is used as authority without checking its source tradition. Correction: cite or verify the source when the output depends on it.

## Source Citations

- Benford, Robert D. and Snow, David A. (2000). Framing Processes and Social Movements. Annual Review of Sociology.
