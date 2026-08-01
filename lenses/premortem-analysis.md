---
lens_id: premortem-analysis
name: Premortem Analysis
lens_type: protocol
applicability: [pre-mortem-action, decision-review, project-launch-review]
foundational: false
source: "Klein, Gary (2007). 'Performing a Project Premortem.' *Harvard Business Review* 85(9):18-19."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - protocol
  - decision
  - foresight
---

# Premortem Analysis

## Trigger

Invoked from modes that review a finalized plan or decision before commitment — project launches, major investments, strategy approvals — when optimism bias, sunk-cost momentum, or social pressure is suppressing critical examination. The host mode supplies the plan and the decision context; the lens supplies the prospective-failure protocol that surfaces hidden risks.

## Core Structure

**Input:** A plan or decision that has been finalized but not yet executed; a team or analyst with knowledge of the plan.
**Output:** A prioritized list of plausible failure causes with mitigations, plus an updated plan that incorporates the highest-priority mitigations.

1. **Set the scene.** Gather the full team after the plan is complete but before execution begins. State the setup: "Imagine it is twelve months from now. This plan has failed completely. It was a disaster." Input: the host mode's plan. Output: shared projection scenario.

2. **Independent generation.** Each person independently writes down all the reasons they can think of for the failure — two to three minutes of silent writing. Independence is load-bearing; it prevents groupthink and surfaces causes that consensus discussion would suppress. Input: scenario from step 1. Output: per-participant cause lists.

3. **Round-robin disclosure.** Go around the room; each person reads one reason at a time until all are shared. Avoid commentary or evaluation during disclosure — pure capture. Input: per-participant lists. Output: aggregated cause list.

4. **Consolidate and prioritize.** Combine the lists; merge near-duplicates; rank by a composite of likelihood and severity. Input: aggregated list. Output: prioritized cause list.

5. **Map causes to current decisions.** For each high-priority cause, identify the specific decision in the present plan where the failure could be averted. Input: prioritized list. Output: cause-to-decision-point mapping.

6. **Generate mitigations.** For each mapped cause, write a concrete mitigation action that would alter the decision or reduce the cause's likelihood/severity. Input: mapping. Output: mitigation list.

7. **Update the plan.** Incorporate the mitigations into the actual plan; document the residual risks that could not be mitigated. Input: mitigations. Output: revised plan.

## Application Steps

1. Receive the finalized plan from the host mode.
2. Run the seven-step protocol with the planning team.
3. Return the revised plan with embedded mitigations and a residual-risk section.
4. Flag any high-priority cause that did not map to a current decision as out-of-scope-for-mitigation.

## Detection Signals

- A major initiative has reached the commitment point and the team is feeling confident.
- Post-mortems in the organization consistently reveal risks that "someone knew about but didn't raise."
- The plan was developed by the same team that will evaluate it, creating ownership bias.
- Stakeholders are showing signs of optimism bias — only discussing success scenarios.
- A decision is expensive to reverse once committed.

## Critical Questions

- Is the failure scenario projected as a specific future state, or merely "things go badly"?
- Was the cause-generation step performed independently before any group discussion?
- Are the causes traced to specific decision points, or to vague systemic factors?
- Is the projected failure timeframe within the plan's actual horizon?
- Was the revised plan actually updated, or did the protocol run as ritual?

## Common Failure Modes

- **Theatrical pre-mortem** — the protocol is run but no mitigations enter the actual plan. Detection: revised plan equals original plan. Correction: require the host to produce a diff and review what changed.
- **Group-influenced generation** — participants discussed before generating, contaminating independence. Detection: cause lists are similar across participants. Correction: enforce silent-writing phase strictly.
- **Vague causes** — failure causes are too abstract to map to decision points. Detection: cause-to-decision mapping has many unfilled cells. Correction: re-prompt for concrete failure pathways with the format "the failure happened because X, which was caused by Y, which was a consequence of decision Z."
- **Confirmation projection** — analysts project only failures consistent with prior beliefs. Detection: cause list aligns suspiciously with pre-existing positions. Correction: steelman the plan before re-running the protocol.

## Source Citations

- Klein, Gary (2007). "Performing a Project Premortem." *Harvard Business Review* 85(9):18-19. Originating short-form article.
- Klein, Gary (2003). *The Power of Intuition*. Currency. Broader naturalistic-decision-making frame.
- Mitchell, Deborah J., J. Edward Russo, and Nancy Pennington (1989). "Back to the future: Temporal perspective in the explanation of events." *Journal of Behavioral Decision Making* 2(1):25-38. Empirical foundation: prospective hindsight increases identification of future-outcome reasons by ~30%.
