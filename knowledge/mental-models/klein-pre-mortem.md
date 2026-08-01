---
lens_id: klein-pre-mortem
name: Klein Pre-Mortem
lens_type: protocol
applicability: [pre-mortem-action, pre-mortem-fragility]
foundational: true
source: "Klein, Gary (2007). Performing a Project Premortem. Harvard Business Review 85(9):18-19."
date created: 2026-05-01
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

# Klein Pre-Mortem

## Trigger

Invoked from within `pre-mortem-action` (T6) and `pre-mortem-fragility` (T7) when those modes need the structured failure-projection-and-backward-trace protocol. The host mode supplies the plan, intervention, or system that is the target of the projection; the lens supplies the procedure for imagining its catastrophic future failure and tracing causes back to current decision points where mitigation is possible.

## Core Structure

**Input:** A plan, intervention, or system that has been formed but not yet executed (or is at an early-execution stage where alteration remains feasible).
**Output:** A prioritized list of plausible failure causes, each tied to a current decision point, plus a list of warning signs to monitor and mitigation actions.

1. **Familiarize the team or analyst with the plan or system at hand.** Establish a shared, concrete picture of what is being proposed: scope, key actors, dependencies, and the success state the plan is aimed at. Input: the host mode's framing of the artifact. Output: a one-paragraph operational description of the plan/system.

2. **Project forward to a hypothetical failure state.** Imagine that, in some near-future timeframe (typically the plan's intended completion horizon), the plan or system has failed catastrophically. Treat the failure as a fact, not a possibility — this is the projection step that distinguishes pre-mortem from generic risk assessment. Input: operational description from step 1. Output: a stated failure scenario in past tense ("Six months from now, the launch has failed completely").

3. **Generate plausible reasons the failure occurred.** Each participant works independently to list reasons the projected failure happened (multi-party); a single analyst generates multiple competing causal hypotheses. Independence in this step is load-bearing — it prevents groupthink and surfaces causes a consensus discussion would suppress. Input: failure scenario from step 2. Output: a list of candidate failure causes per participant or per hypothesis stream.

4. **Aggregate, deduplicate, and prioritize.** Combine the lists; merge near-duplicates; rank by a composite of likelihood and severity. Input: per-participant cause lists. Output: a deduplicated, prioritized cause list.

5. **Trace each cause backward to current decision points.** For each prioritized cause, identify the specific decision, design choice, or assumption in the present plan where the failure could be averted or its severity mitigated. A cause that does not trace to a current decision point is either too vague to act on or genuinely outside the plan's control. Input: prioritized cause list. Output: a cause-to-decision-point mapping.

6. **Produce warning signs and mitigation actions.** For each cause-to-decision-point pair, write the observable early signal that would indicate the failure pathway is activating, plus the concrete mitigation action that would alter the decision. Input: cause-to-decision-point mapping. Output: a warning-sign-and-mitigation list ready for the host mode to incorporate into its final artifact.

## Application Steps

1. Receive the plan, intervention, or system from the host mode.
2. Run the six-step protocol above.
3. Return the warning-sign-and-mitigation list to the host mode in the format the host expects.
4. Flag any cause that did not trace to a current decision point as out-of-scope-for-mitigation, for the host to incorporate into its risk-acknowledgment section.

## Detection Signals

- A plan, intervention, design, or strategy is being formed and is not yet locked.
- A system is about to launch or be deployed, with alteration still feasible.
- A decision is converging toward a single course of action and contrarian input has been thin.
- A host mode (`pre-mortem-action` or `pre-mortem-fragility`) has been dispatched and explicitly references this lens in its `lens_dependencies`.
- Mid-analysis state where the analyst notices the planning conversation has shifted toward implementation detail without ever stress-testing the plan's failure pathways.

## Critical Questions

- Is the failure scenario projected as a hypothetical future state, not a current concern? If the analyst is treating an existing problem as the failure, the lens does not apply — use risk assessment or root-cause analysis instead. The pre-mortem's diagnostic value depends on the projection being counterfactual.
- Are the causes traced to specific decision points or to vague systemic factors? Specific decision points are necessary for actionable mitigation; "the team lacked alignment" is not a decision point, but "we approved the staffing plan without naming an alignment owner" is.
- Are the warning signs observable in advance, or only post-failure? Observable-in-advance signs are necessary for the lens's preventive value; a warning sign that only manifests at failure time is no warning at all.
- Was the cause-generation step performed independently before aggregation? If participants discussed and converged on causes before independently generating them, groupthink has likely suppressed important pathways.
- Is the projected failure timeframe within the analyst's planning horizon? A failure projected ten years out for a six-month plan is too distant to constrain present decisions.

## Common Failure Modes

- **Pessimism trap** — projecting failure becomes generic doom-mongering rather than specific cause-tracing. Detection: the cause list lacks specificity; entries read like "things just didn't work" or "everything fell apart." Correction: re-prompt for concrete failure pathways with the format "the failure happened because X, which was caused by Y, which was a consequence of decision Z."
- **Confirmation projection** — the analyst projects only failures consistent with prior beliefs about the plan's weaknesses. Detection: the cause list aligns suspiciously with the analyst's pre-existing position on the plan; failures the analyst would not have predicted are absent. Correction: invoke a steelman of the plan first; then re-run the pre-mortem with the steelmanned plan as the projected-failure target.
- **Cause without decision point** — every cause is identified but none is tied to a current decision the team can alter. Detection: the cause-to-decision-point mapping has cells filled with "we couldn't have known" or "this was external." Correction: either reframe the cause more narrowly to find the decision lever, or accept the cause as out-of-scope and document it in the residual-risk section.
- **Theatrical pre-mortem** — the protocol is run as a ritual without changing the plan. Detection: the warning-sign-and-mitigation list is produced but no mitigation actions are integrated into the actual plan. Correction: require the host mode to produce a revised plan that incorporates the mitigations, and check the diff against the original.
- **Single-failure tunnel** — the projection imagines one failure scenario when the plan has multiple distinct failure modes. Detection: the failure scenario is stated narrowly ("the launch missed its date") when broader failure modes ("the launch happened on time but produced unintended consequences") are equally plausible. Correction: run multiple parallel projections, one per major failure mode.

## Source Citations

- Klein, Gary (2007). "Performing a Project Premortem." *Harvard Business Review* 85(9):18-19. Originating short-form article.
- Klein, Gary (2003). *The Power of Intuition: How to Use Your Gut Feelings to Make Better Decisions at Work*. Currency. Broader naturalistic decision-making frame in which the pre-mortem method is situated.
- Mitchell, Deborah J., J. Edward Russo, and Nancy Pennington (1989). "Back to the future: Temporal perspective in the explanation of events." *Journal of Behavioral Decision Making* 2(1):25-38. Underlying empirical finding (prospective hindsight increases the ability to identify reasons for future outcomes by ~30%) on which the Klein method draws.
- Related: project autopsies / post-mortems (the retrospective sibling); red-teaming (the adversarial sibling).
