---
lens_id: recovery-window
name: Recovery Window
lens_type: mental-model
applicability: [crisis-detection, escalation-design, asymmetric-risk-action]
foundational: false
source: "Various; clinical-medicine sepsis literature; organizational crisis-management literature."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - risk
  - crisis
---

# Recovery Window

## Trigger

Invoked from modes that evaluate ambiguous early warning signals, design escalation protocols, or analyze whether to act on incomplete information — when waiting for certainty would close the window during which intervention is cheap. The host mode supplies the warning signal and the consequence model; the lens supplies the asymmetric-cost analysis that justifies action before proof.

## Core Structure

### Core Insight

Between the first ambiguous warning sign and the point of irreversible damage, there exists a finite window during which preventive action is still possible and relatively cheap. The window narrows as time passes: early in the window, intervention is inexpensive but feels unjustified because the evidence is unclear; late in the window, the need is obvious but options have collapsed. Most catastrophes are not failures of detection — the signals were visible — but failures to act within the recovery window.

### Mechanism

Asymmetric costs drive the logic. If early intervention is cheap and false-positive cost is low, while delayed intervention is expensive and false-negative cost is catastrophic, the rational threshold for action is well below certainty. The threshold collapses as the window narrows because the cost of waiting compounds. Standard "wait for proof" thresholds optimize for false-positive avoidance; recovery-window thinking optimizes for total expected loss across the asymmetric cost structure.

### Applicability Conditions

- The threat has identifiable early signals.
- There is a meaningful gap between early signal and irreversible consequence.
- Early intervention is materially cheaper than late intervention.
- The cost asymmetry favors acting on probability rather than proof.

### Common Misapplications

- Treating every ambiguous signal as crisis, producing alert fatigue.
- Using the lens to justify pet interventions for which the cost asymmetry doesn't actually hold.
- Ignoring that some windows have been overestimated and the threat is less time-sensitive than assumed.
- Building escalation protocols that bypass judgment when judgment was the protection.

### Related Models

- **Asymmetric Bets** — the broader category of action under unequal payoff structure.
- **Pre-mortem Analysis** — prospective version: imagine the window has closed and trace back.
- **Sensemaking** — the cognitive process that determines whether early signals get acted on.

### Worked example

A hospital patient develops a mildly elevated heart rate and slight temperature increase 36 hours after surgery. Each sign alone is unremarkable. The recovery window for sepsis intervention is roughly 6 hours from onset of systemic response — within that window, antibiotics and fluids are almost always sufficient. The attending physician orders a precautionary blood culture and starts broad-spectrum antibiotics. The culture comes back positive. Had the team waited for "clear" symptoms, the window would have closed.

## Application Steps

1. Identify the earliest signal — what is the first thing that looks "off" even if explainable?
2. Estimate the window: how much time exists between this signal and the point where options narrow dramatically?
3. Calculate the asymmetry: what does early action cost vs. what does delayed action cost if the threat materializes?
4. Set a trigger threshold lower than certainty — if the downside is catastrophic, act on probability not proof.
5. Build escalation protocols that create automatic action points, so the decision to intervene doesn't require someone to override normalcy bias in real time.

## Detection Signals

- An anomaly or weak signal has appeared but doesn't yet demand action.
- The cost of early intervention is low relative to the cost of the full crisis.
- Decision-makers are waiting for more certainty before acting.
- Post-mortem analysis reveals that warning signs existed well before the failure.
- Designing monitoring systems or escalation protocols for high-consequence environments.

## Critical Questions

- Is the cost asymmetry actually as steep as claimed, or is it being overstated to justify pre-emptive action?
- Does the window estimate come from data or from anxiety?
- Is the proposed intervention actually cheap, or does it have hidden second-order costs?
- Will repeated false-positive interventions degrade trust in the protocol?
- Is the early signal genuinely diagnostic, or is it common enough that intervention triggers will fire constantly?

## Common Failure Modes

- **Alert fatigue** — too many low-threshold alerts produce desensitization. Detection: response time degrades over time. Correction: tune thresholds to maintain a sustainable signal-to-noise ratio.
- **Window-padding** — overestimating the window to delay action. Detection: window estimates expand when intervention is inconvenient. Correction: lock the window estimate before considering intervention cost.
- **Bypass-by-protocol** — automatic action points fire when human judgment would have correctly identified false positives. Detection: protocol fires repeatedly on conditions humans recognize as benign. Correction: incorporate judgment loops at high-cost intervention thresholds.

## Source Citations

- Rivers, Emanuel et al. (2001). "Early goal-directed therapy in the treatment of severe sepsis and septic shock." *New England Journal of Medicine* 345(19):1368-1377. Sepsis recovery-window evidence.
- Reason, James (1997). *Managing the Risks of Organizational Accidents*. Ashgate. Organizational application.
- Klein, Gary (1998). *Sources of Power: How People Make Decisions*. MIT Press. Naturalistic-decision framing.
- Weick, Karl E. and Kathleen M. Sutcliffe (2007). *Managing the Unexpected: Resilient Performance in an Age of Uncertainty*. Jossey-Bass. High-reliability-organization application.
