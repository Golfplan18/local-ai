---
lens_id: five-whys
name: Five Whys
lens_type: protocol
applicability: [root-cause-analysis, post-mortem, debug-loop, systemic-improvement]
foundational: false
source: "Ohno, Taiichi (1988). Toyota Production System: Beyond Large-Scale Production. Productivity Press."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - protocol
  - quality
  - root-cause
---

# Five Whys

## Trigger

Invoked from within root-cause-analysis, post-mortem, and systemic-improvement modes when an analyst observes that a fix at the symptom level has not prevented recurrence, when an incident report identifies what happened but not why, or when the proposed root cause is "human error" (which is almost never the actual root cause). The host mode supplies the problem statement and the proximate explanation; the lens supplies the iterative drill protocol that peels back layers of causation until a systemic cause (process gap, missing check, incentive misalignment) is reached, replacing reactive firefighting with structural correction.

## Core Structure

**Input:** A concrete problem with a known proximate cause that has not stopped recurrence; access to evidence that supports each "why" answer.

**Output:** A causal chain from symptom to systemic root cause, plus a corrective action that addresses the system rather than the individual instance.

1. **State the problem concretely.** Specify what happened, when, and what the impact was. Vague problem statements produce vague drilling. Input: the symptom or incident. Output: a specific problem statement.

2. **Ask "Why did this happen?" with a factual, verifiable answer.** Avoid speculation; require evidence for the answer. The answer becomes the new problem statement for the next iteration. Input: the problem statement. Output: the first-level cause.

3. **Take that answer and ask "Why?" again.** Treat each answer as a new problem; require the same evidentiary discipline. Input: the prior answer. Output: the next-level cause.

4. **Continue until reaching a systemic cause.** A systemic cause is structural — a process gap, a missing check, an incentive misalignment, an unrevisited assumption. Continue past proximate causes (someone forgot, a value was wrong) which describe what happened without explaining why the system permitted it. The number five is heuristic; some chains terminate sooner, some require more drilling. Input: each successive cause. Output: the systemic root cause.

5. **Define a corrective action at the systemic level.** The fix addresses the structure that permitted the failure, not just the individual instance. Without this, the same class of failure recurs. Input: the systemic root cause. Output: a corrective action targeting the system.

## Application Steps

1. Receive the problem and proximate explanation from the host mode.
2. Run the iterative drill per steps 1-4 above.
3. Define the systemic corrective action per step 5.
4. Return the causal chain, the systemic root cause, and the corrective action to the host mode.
5. Flag any "why" answer that lacks supporting evidence as a hypothesis requiring verification.

## Detection Signals

- A bug or failure has been patched but keeps coming back in slightly different forms.
- An incident post-mortem identifies what happened but not why it happened.
- "Human error" appears as the proposed root cause.
- A process is producing defects and the team is treating each defect individually.
- The team wants to move from reactive firefighting to systemic improvement.

## Critical Questions

- Is each "why" answer supported by evidence, or are answers being inferred to keep the chain moving?
- Has the chain been drilled to a systemic cause, or has it stopped at a proximate cause that does not explain why the system permitted the failure?
- Is the corrective action targeting the system, or is it still targeting the individual instance?
- Are alternative causal chains plausible? Five Whys produces one chain; the systemic cause may be over-determined or have multiple contributing structural factors.

## Common Failure Modes

- **Stop-at-blame** — Detection signal: the chain stops at "person X made an error." Correction: ask why the system permitted the error to cause the outcome; the systemic cause is the absence of a guard.
- **Speculative drilling** — Detection signal: each "why" answer is plausible but unsupported by evidence. Correction: require evidence per step; pause the drilling when evidence is unavailable and resume when it is.
- **Single-chain tunnel vision** — Detection signal: only one causal chain is drilled; alternative chains are not considered. Correction: when multiple proximate causes exist, drill each; the systemic root cause may be common or distinct.

## Source Citations

- Ohno, Taiichi (1988). *Toyota Production System: Beyond Large-Scale Production*. Productivity Press.
- Liker, Jeffrey K. (2004). *The Toyota Way: 14 Management Principles from the World's Greatest Manufacturer*. McGraw-Hill.
- Rother, Mike (2010). *Toyota Kata: Managing People for Improvement, Adaptiveness and Superior Results*. McGraw-Hill.
