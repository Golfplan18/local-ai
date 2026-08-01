---
lens_id: adversarial-case-studies
name: Adversarial Case Studies
lens_type: evidence-pattern
applicability: [red-team-advocate, red-team-assessment]
foundational: false
source: "Zenko, Micah (2015). Red Team: How to Succeed by Thinking Like the Enemy. Basic Books."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - red-team
  - adversarial
  - case-study
---

# Adversarial Case Studies

## Trigger

Invoked when a red-team mode needs to derive attack paths from real adversarial examples rather than from abstract worry. The host mode supplies the system, decision, argument, or plan under attack; the lens supplies a case-study transfer protocol.

## Core Structure

Adversarial case studies are precedent libraries for how determined opponents exploit assumptions, incentives, defenses, and blind spots.

1. **Adversary objective.** What was the attacker trying to achieve?
2. **Target assumption.** What did defenders assume would hold?
3. **Exploit path.** How did the adversary convert a weakness into leverage?
4. **Defensive blind spot.** Why was the exploit missed or underestimated?
5. **Transfer condition.** What must be true for the case to apply here?
6. **Adapted attack.** What analogous attack would fit the current target?

## Application Steps

1. Select comparable adversarial cases by mechanism, not topic.
2. Extract the adversary's objective, constraint, and exploit path.
3. Identify the defender assumption that failed.
4. Test whether the current target has the same assumption or blind spot.
5. Construct an adapted attack path.
6. Recommend a mitigation that blocks the mechanism, not just the precedent.

## Detection Signals

- The target has strategic opponents, incentives for misuse, or motivated critics.
- A plan assumes cooperative behavior from actors who may benefit by defecting.
- A red-team pass needs concrete attack stories.
- The current defense relies on obscurity, norms, or untested deterrence.

## Critical Questions

- What adversary would benefit from breaking this?
- Which historical case shares the exploit mechanism?
- What assumption did defenders make in that case?
- Does the current target make an analogous assumption?
- What would the adapted attack look like under current constraints?

## Common Failure Modes

- **Case-story theater** - Detection: case studies are told dramatically but not transferred structurally. Correction: extract mechanism and transfer condition.
- **Villain caricature** - Detection: adversaries are assumed reckless or omniscient. Correction: model incentives, constraints, and information.
- **Defense mismatch** - Detection: mitigation addresses the old case but not the current mechanism. Correction: block the adapted path.
- **Overfitting** - Detection: one case dominates the analysis. Correction: compare multiple cases or mark uncertainty.

## Source Citations

- Zenko, Micah (2015). *Red Team: How to Succeed by Thinking Like the Enemy*. Basic Books.
- Heuer, Richards J. and Pherson, Randolph H. (2014). *Structured Analytic Techniques for Intelligence Analysis*. CQ Press.
- Central Intelligence Agency (2009). *A Tradecraft Primer: Structured Analytic Techniques for Improving Intelligence Analysis*.

