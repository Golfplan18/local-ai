---
lens_id: fgl-fear-greed-laziness
name: FGL Fear Greed Laziness
lens_type: protocol
applicability: [cui-bono, red-team-advocate, red-team-assessment]
foundational: false
source: "Ora Tier 1 thinking-tool implementation, adapted from the de Bono CoRT thinking-tools tradition."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - protocol
  - motivation
  - incentives
---

# FGL Fear Greed Laziness

## Trigger

Invoked when a mode needs a compact motivational scan for actors, institutions, or positions. The host mode supplies the claim, actor, role, or incentive environment; the lens supplies the Fear-Greed-Laziness triad so the analyst can test whether behavior is being shaped by loss avoidance, gain seeking, or inertia.

## Core Structure

FGL is a structured suspicion tool. It does not prove motive. It keeps the analyst from accepting stated reasons as the whole explanation.

### Fear

What might this actor be afraid of losing? Fear includes status, legitimacy, budget, control, safety, reputation, market position, legal protection, or narrative authority. Fear often explains defensive behavior that looks irrational from the outside.

### Greed

What might this actor be trying to gain, protect, or expand? Greed includes money, influence, attention, market share, authority, optionality, and future bargaining power. It is broader than personal avarice; institutions can be structurally greedy through their incentives.

### Laziness

What path of least resistance, inertia, habit, convenience, or bureaucratic default might explain the behavior? Laziness is not a moral insult. It names the tendency of systems to preserve routines and avoid costly rethinking.

## Application Steps

1. Identify the actor and role being analyzed.
2. State the actor's public or explicit reason for acting.
3. Run the fear pass: what loss would this action prevent?
4. Run the greed pass: what gain or protected advantage would this action secure?
5. Run the laziness pass: what default, habit, or path of least resistance would this action preserve?
6. Separate evidence from hypothesis for each motive.
7. Reconstruct the position after accounting for plausible fear, greed, and laziness.
8. Apply the same scan symmetrically to favored and disfavored actors.

## Detection Signals

- A stated explanation sounds too clean for the incentive environment.
- A red-team analysis needs to identify hidden motive or institutional vulnerability.
- A policy, argument, or proposal strongly benefits its advocate.
- The same behavior persists despite repeated evidence that it is not working.
- An actor's position can be explained by loss avoidance, advantage protection, or convenience.

## Critical Questions

- What would this actor lose if the opposite decision were made?
- What does the actor gain if their preferred framing wins?
- What costly work is avoided by maintaining the current approach?
- Which motive is supported by evidence, and which is only plausible speculation?
- Would the same analysis look fair if applied to the analyst's own side?
- Is the actor an individual, an institution, or a role with structural incentives?

## Common Failure Modes

- **Cynicism generator** - Detection: the scan treats every motive as corrupt. Correction: use FGL to generate hypotheses, then require evidence.
- **Laziness omission** - Detection: fear and greed are explored, but inertia and convenience are ignored. Correction: ask what the system can avoid by doing nothing new.
- **Individualization error** - Detection: institutional incentives are assigned to personal character. Correction: analyze roles and reward structures before personal motive.
- **Asymmetry** - Detection: FGL is applied only to opponents. Correction: run the triad on all materially involved parties.
- **Motive replacement** - Detection: hidden motive is treated as disproving the stated reason. Correction: allow stated reasons and FGL motives to coexist unless evidence rules one out.

## Source Citations

- de Bono, Edward (1973). *CoRT Thinking*. Direct Education Services.
- de Bono, Edward (1992). *Serious Creativity*. HarperBusiness.
- Ora Tier 1 thinking-tool implementation: Fear, Greed, Laziness scan.

