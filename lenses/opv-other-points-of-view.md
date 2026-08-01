---
lens_id: opv-other-points-of-view
name: OPV Other Points of View
lens_type: protocol
applicability: [red-team-advocate, red-team-assessment]
foundational: false
source: "de Bono, Edward (1973). CoRT Thinking. Direct Education Services."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - thinking-tool
  - red-team
  - perspective
---

# OPV Other Points of View

## Trigger

Invoked when red-team modes need to inspect a target from the perspective of actors other than the designer, advocate, or analyst. The host mode supplies the target and actor set; the lens supplies de Bono's OPV discipline.

## Core Structure

OPV asks how the situation looks from other positions in the system. It is not empathy as sentiment; it is role-based perspective-taking for incentives, constraints, knowledge, and likely reactions.

Common viewpoints include:

1. **User or beneficiary.** What feels useful, costly, confusing, or risky?
2. **Opponent or adversary.** What can be exploited, resisted, or reframed?
3. **Operator or implementer.** What is hard to execute under real conditions?
4. **Gatekeeper or regulator.** What standard, liability, or rule matters?
5. **Bystander or affected third party.** What externality appears from outside the main bargain?
6. **Future maintainer.** What debt, ambiguity, or fragility will be inherited?

## Application Steps

1. Identify the relevant actor roles.
2. For each role, state what they know, want, fear, and control.
3. Ask how the target looks from that role's constraints.
4. Identify objections, exploit paths, adoption barriers, or externalities.
5. Compare viewpoints and surface conflicts the original analysis missed.

## Detection Signals

- A plan is described only from the builder's or advocate's view.
- Adoption, misuse, compliance, or implementation risk matters.
- Red-team analysis needs stakeholder-specific attack or failure paths.
- The user's preferred solution may impose hidden costs on others.

## Critical Questions

- Whose point of view is missing?
- What does that actor know that the analyst does not?
- What would that actor resist, exploit, ignore, or reinterpret?
- What cost is shifted onto someone outside the main decision?
- Which viewpoint changes the recommendation most?

## Common Failure Modes

- **Token stakeholder pass** - Detection: actors are listed but their constraints do not affect conclusions. Correction: state the specific implication of each point of view.
- **Empathy blur** - Detection: OPV becomes generic kindness. Correction: model knowledge, incentives, and constraints.
- **Adversary omission** - Detection: hostile or strategic actors are left out. Correction: include at least one misuse or opposition viewpoint when relevant.
- **Projection** - Detection: the analyst gives other actors the analyst's beliefs. Correction: separate role incentives from analyst preference.

## Source Citations

- de Bono, Edward (1973). *CoRT Thinking*. Direct Education Services.
- de Bono, Edward (1985). *Six Thinking Hats*. Little, Brown.

