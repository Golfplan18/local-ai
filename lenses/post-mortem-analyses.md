---
lens_id: post-mortem-analyses
name: Post-Mortem Analyses
lens_type: evidence-pattern
applicability: [red-team-advocate, red-team-assessment]
foundational: false
source: "Vaughan, Diane (1996). The Challenger Launch Decision. University of Chicago Press."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - risk
  - red-team
  - postmortem
---

# Post-Mortem Analyses

## Trigger

Invoked when a red-team mode can learn from comparable failures after the fact. The host mode supplies the target plan, system, or claim; the lens supplies post-mortem reading discipline: find causal pathways, warning signs, decision conditions, and hindsight traps.

## Core Structure

Post-mortems are useful when they are mined for mechanisms rather than anecdotes. A good post-mortem scan extracts:

1. **Initiating conditions.** What made the failure possible?
2. **Normalization path.** Which deviations became acceptable over time?
3. **Decision points.** Where could actors have chosen differently?
4. **Weak signals.** What evidence appeared before collapse?
5. **Organizational filters.** What incentives, reporting paths, or authority patterns shaped interpretation?
6. **Recovery gap.** Why did detection not convert into correction?
7. **Hindsight caution.** What only looks obvious after the outcome is known?

## Application Steps

1. Identify comparable historical failures or post-mortems.
2. Extract mechanisms rather than surface resemblance.
3. Map warning signs and decision points onto the current target.
4. Ask which safeguards failed or were bypassed in the precedent.
5. Translate lessons into current leading indicators and mitigations.
6. Mark where the analogy is weak or incomplete.

## Detection Signals

- A target resembles known failures in industry, governance, product, safety, or strategy.
- The team says "we would catch that" without specifying how.
- A red-team critique needs evidence from real failure pathways.
- Hindsight bias may be distorting blame or confidence.

## Critical Questions

- What mechanism from the post-mortem is actually shared with the current case?
- What warning signs existed before failure?
- Why were those signals missed or discounted?
- Which decision point is analogous now?
- What would make this case different enough that the lesson does not transfer?

## Common Failure Modes

- **Anecdotal analogy** - Detection: a famous failure is invoked because it feels similar. Correction: map the causal mechanism.
- **Outcome hindsight** - Detection: actors are judged as if the outcome was obvious. Correction: reconstruct what was knowable then.
- **Lesson laundering** - Detection: broad slogans replace concrete safeguards. Correction: convert the lesson into a signal, threshold, or action.
- **Hero-villain compression** - Detection: failure is reduced to bad individuals. Correction: map system incentives and information flows.

## Source Citations

- Vaughan, Diane (1996). *The Challenger Launch Decision*. University of Chicago Press.
- Perrow, Charles (1984). *Normal Accidents*. Basic Books.
- Dekker, Sidney (2014). *The Field Guide to Understanding Human Error*. CRC Press.

