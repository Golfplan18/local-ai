---
lens_id: swiss-cheese-model
name: Swiss Cheese Model
lens_type: mental-model
applicability: [defense-in-depth-design, post-mortem-analysis, layered-safety-audit]
foundational: false
source: "Reason, James (1990). *Human Error*. Cambridge University Press; Reason (2000). 'Human error: models and management.' *BMJ* 320:768-770."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - safety
  - systems
---

# Swiss Cheese Model

## Trigger

Invoked from modes that design or audit layered defenses, conduct post-mortems on failures that passed multiple safeguards, or evaluate whether existing layers are independent — when the question is which layers failed and whether their failure modes were correlated. The host mode supplies the failure trace and the defense layers; the lens supplies the holes-and-alignment analysis that distinguishes layer failures from layer correlations.

## Core Structure

### Core Insight

Defenses against failure are like slices of Swiss cheese: each layer has holes (weaknesses), but the holes are in different places. An accident happens only when the holes in every layer momentarily align, allowing a hazard to pass through all defenses. No single layer is expected to be perfect — safety comes from having multiple independent layers whose holes don't overlap. James Reason (1990): "Defences in depth work not because each barrier is perfect, but because the weaknesses in each are offset by the strengths in others."

### Mechanism

Each defensive layer has both active failures (acts that cause holes) and latent conditions (organizational and design factors that make holes more likely or larger). Active failures are visible at the time of accident; latent conditions are pre-existing weaknesses that the active failure exposes. A failure occurs when the trajectory through the layers finds aligned holes. Layer correlation (shared failure modes, common causes) increases the probability of alignment dramatically and is the central design concern.

### Applicability Conditions

- Multiple defensive layers exist or are being designed.
- Layer failures can be at least partially observed.
- The layers are intended to be independent.
- The cost of failure justifies the analytical investment.

### Common Misapplications

- Assuming layer independence without verification.
- Treating layer addition as the universal remedy without considering correlation.
- Focusing on active failures while ignoring latent conditions.
- Using the model to assign individual blame rather than identify systemic patterns.

### Related Models

- **Defense in Depth** — the design principle the model formalizes.
- **Normal Accident Theory** — what produces the conditions where holes align.
- **Practical Drift** — what enlarges holes over time.

### Worked example

A production deployment pipeline has four layers: automated tests, code review, staging environment, and canary deployment. A bug ships to production. Analysis reveals: tests didn't cover the edge case (hole 1), the reviewer was fatigued on a Friday afternoon (hole 2), staging used synthetic data that didn't trigger the bug (hole 3), and the canary period was shortened due to a release deadline (hole 4). All four holes aligned. The fix targets independence: add property-based tests, require a second reviewer for Friday deploys, seed staging with anonymized production data, enforce a minimum canary period.

## Application Steps

1. List all existing defense layers between the hazard and the harmful outcome.
2. For each layer, identify its "holes" — conditions under which it fails to catch the problem.
3. Check for correlated holes: do multiple layers fail under the same conditions (fatigue, time pressure, same data source)?
4. Add layers whose failure modes are independent of existing layers.
5. Shrink existing holes: training, automation, checklists, and fresh-eyes reviews each reduce hole size.

## Detection Signals

- A failure passed through multiple safeguards that should have caught it.
- Designing a defense-in-depth strategy for safety, security, or quality.
- Conducting a post-mortem and need to identify which layers failed and why.
- Evaluating whether existing layers are truly independent or share common failure modes.
- Deciding where to add a new safety layer for maximum impact.

## Critical Questions

- Are the layers actually independent, or do they share common modes?
- What latent conditions make holes larger or more likely?
- Is adding a new layer addressing a real gap or duplicating an existing one?
- Did the failure expose a single aligned-holes event, or a systemic pattern of drift?
- Does the fix reduce hole size, increase layer count, or address correlation?

## Common Failure Modes

- **Independence assumption** — adding layers that share failure modes with existing ones. Detection: new layer fails when the existing layer fails. Correction: explicitly test for layer correlation before deployment.
- **Active-failure focus** — fixating on the immediate act while ignoring latent conditions. Detection: post-mortem identifies the proximate cause but no systemic factors. Correction: trace latent conditions for each hole.
- **Layer-count fetishism** — adding layers without regard for marginal value. Detection: cost of layers grows without proportional safety improvement. Correction: prefer hole reduction in existing layers over adding redundant ones.

## Source Citations

- Reason, James (1990). *Human Error*. Cambridge University Press. Originating treatment.
- Reason, James (1997). *Managing the Risks of Organizational Accidents*. Ashgate. Extended application.
- Reason, James (2000). "Human error: Models and management." *BMJ* 320:768-770. Accessible synthesis.
- Perneger, Thomas V. (2005). "The Swiss cheese model of safety incidents: are there holes in the metaphor?" *BMC Health Services Research* 5:71. Critical examination.
