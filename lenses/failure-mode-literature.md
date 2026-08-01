---
lens_id: failure-mode-literature
name: Failure Mode Literature
lens_type: catalog
applicability: [red-team-advocate, red-team-assessment]
foundational: false
source: "Reason, James (1990). Human Error. Cambridge University Press; IEC 60812 FMEA tradition."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - risk
  - red-team
  - failure
---

# Failure Mode Literature

## Trigger

Invoked when red-team modes need a disciplined catalog of ways plans, systems, products, or arguments fail. The host mode supplies the target; the lens supplies failure-mode categories so the analysis is not limited to the first obvious weakness.

## Core Structure

Failure-mode analysis asks how something can fail, what causes the failure, how severe it is, how detectable it is, and what prevents or mitigates it.

Common classes include:

1. **Component failure.** A part, role, tool, supplier, assumption, or capability does not perform.
2. **Interface failure.** Handoffs, dependencies, translations, or integrations break.
3. **Process failure.** The intended procedure is skipped, misunderstood, overloaded, or inconsistently executed.
4. **Human-factor failure.** Cognitive load, fatigue, incentives, training gaps, or ambiguity degrade performance.
5. **Organizational failure.** Authority, communication, culture, or incentives prevent correction.
6. **Context-shift failure.** External conditions change and the design no longer fits.
7. **Detection failure.** Weak signals are missed, suppressed, or noticed too late.
8. **Recovery failure.** The system lacks buffers, rollback paths, or decision rights after failure begins.

## Application Steps

1. Define the target and intended success state.
2. Enumerate failure modes across component, interface, process, human, organizational, context, detection, and recovery classes.
3. For each failure mode, identify cause, effect, warning sign, and mitigation.
4. Prioritize by severity, likelihood, detectability, and reversibility.
5. Convert the highest-risk modes into red-team attacks or precommitment mitigations.

## Detection Signals

- A red-team pass is producing generic objections.
- The plan has many dependencies or handoffs.
- A proposed mitigation assumes failures will be obvious early.
- The analysis needs a structured inventory before adversarial prioritization.

## Critical Questions

- What has to work for this plan to succeed?
- Where are the interfaces and handoffs?
- What weak signal would appear before the failure becomes unrecoverable?
- Which failure is severe, likely, hard to detect, and hard to reverse?
- What mitigation changes the failure path rather than naming it?

## Common Failure Modes

- **Generic-risk list** - Detection: risks are vague and not tied to mechanisms. Correction: state cause, effect, signal, and mitigation.
- **Likelihood tunnel** - Detection: low-probability catastrophic failures are dismissed. Correction: consider severity and reversibility separately.
- **Detection optimism** - Detection: the team assumes it will notice failure early. Correction: define concrete leading indicators.
- **Single-class scan** - Detection: technical failures are listed while organizational or recovery failures are ignored. Correction: force all categories.

## Source Citations

- Reason, James (1990). *Human Error*. Cambridge University Press.
- IEC 60812. *Failure Modes and Effects Analysis (FMEA and FMECA)*.
- Stamatis, D. H. (2003). *Failure Mode and Effect Analysis: FMEA from Theory to Execution*. ASQ Quality Press.

