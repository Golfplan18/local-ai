---
lens_id: greshams-law
name: Gresham's Law
lens_type: mental-model
applicability: [systems-analysis, incentive-design, organizational-diagnosis, market-dynamics-read]
foundational: false
source: "Gresham, Sir Thomas (16th c.). Memorandum to Queen Elizabeth I on the debasement of currency. Modern formulation in MacLeod, Henry Dunning (1858). The Elements of Political Economy."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - economics
  - systems
---

# Gresham's Law

## Trigger

Invoked from within systems-analysis, incentive-design, organizational-diagnosis, and market-dynamics modes when those modes need a named pattern to account for an observed displacement of high-quality contributions by low-quality ones in any system that fails to differentiate among them. The host mode supplies the system showing the decline (a market, an organization, a platform, a community); the lens supplies the diagnostic that locates the failure not in the people producing the work but in the system's failure to distinguish unequal things.

## Core Structure

### Core Insight

When a system treats unequal things as equivalent — equal pay for unequal work, identical labels for unequal products, same shelf space for unequal contributions — the lower-quality variant proliferates and the higher-quality variant disappears. The originating phrase is monetary ("bad money drives out good") but the pattern generalizes to any quality-blind system: the producers of quality have no way to be rewarded for it, so they leave or stop trying, while producers of low-quality output continue because the system rewards them identically.

### Mechanism

The system imposes uniform treatment across a quality dimension that the producers and consumers can in fact distinguish. The producer of high quality faces the same return as the producer of low quality but with higher cost; the rational producer either lowers their quality to match the median (reducing wasted effort) or exits the system entirely. The consumer, in turn, cannot signal preference for quality through the system's rewards. Over time the equilibrium quality drops to the level the system can detect, which is whatever the system's coarsest grain measures.

### Applicability Conditions

- Two or more quality variants of a contribution circulate in the same system.
- The system's reward, signaling, or selection mechanism does not discriminate between them.
- Producers can choose their quality level (it is a behavior, not a fixed trait).
- Consumers can in principle distinguish quality but the system does not transmit that distinction back to producers.

### Common Misapplications

- Attributing the decline to the people ("we have a talent problem") when the cause is the reward structure ("we have a differentiation problem"). Talent did not change; incentives did.
- Treating the pattern as a moral failure of low-quality producers, when the pattern is rational response to an undifferentiated reward. The fix is structural, not exhortation.
- Assuming any quality decline is Gresham. If consumers genuinely cannot distinguish quality, or if the high-quality variant's cost is the binding constraint, the pattern is something else (lemon market, cost disease).

### Related Models

- **Lemon market (Akerlof)** — adjacent: information asymmetry causes the same displacement when buyers cannot detect quality.
- **Goodhart's Law** — when a measure becomes a target it ceases to be a good measure; the quality-blind metric becomes the rewarded thing.
- **Tragedy of the Commons** — different mechanism (overuse of shared resource) but same structural blindness to individual contribution.

### Worked example

A company pays all software engineers in the same band identically regardless of output quality. The best engineers, whose code is cleaner and more maintainable, realize they could earn the same by doing less. Some leave for companies that differentiate; others reduce effort to match the median. Over two years, code quality declines and technical debt balloons. The compensation system — treating unequal contributions as equal — drove the bad-money dynamic.

## Application Steps

1. Identify the quality variants present in the system being analyzed.
2. Locate the system's reward, signaling, or selection mechanism.
3. Test whether the mechanism in fact discriminates among the variants; the displacement requires that it does not.
4. Trace the producer-side response: are high-quality producers exiting, lowering effort, or persisting at cost?
5. Identify a differentiation intervention (tiered rewards, quality signals, curation, gates) and project the new equilibrium.

## Detection Signals

- Top performers in a system are leaving or visibly reducing effort.
- The system is being flooded with low-effort contributions and the response is to add more contributors rather than to differentiate.
- Standards in an organization, market, or community are visibly declining without an obvious change in the talent pool.
- Compensation, promotion, or recognition flattens distinctions that producers and consumers can perceive.
- The system's measure of quality is much coarser than what the participants can themselves discriminate.

## Critical Questions

- Can the system actually distinguish the quality variants if it tried, or is the indistinguishability a real information problem (lemon market) rather than a reward-design problem?
- Are the high-quality producers exiting because of the reward structure, or because of cost, lifecycle, or unrelated factors? Misattribution to Gresham obscures the real cause.
- Is the differentiation intervention being proposed at the right grain? A signal too coarse to discriminate is no improvement; a signal too fine to administer collapses under measurement cost.
- Has the analysis distinguished the producer-side response (rational adjustment to flat reward) from a moral framing (low-quality producers as bad actors)? The pattern is structural; moral framing prevents the structural fix.

## Common Failure Modes

- **People-blame substitution** — diagnosing the decline as a talent problem when it is a reward-design problem. Detection: the proposed fix is hiring or firing rather than restructuring rewards. Correction: re-run the diagnosis explicitly looking for the equality-of-treatment that drives the equilibrium.
- **Premature Gresham labeling** — applying the pattern when the actual cause is information asymmetry (lemon market) or genuine cost disease. Detection: the high-quality producers can in fact be rewarded but no consumer is asking for the quality. Correction: distinguish information problems from reward-design problems; Gresham requires the consumer can in principle perceive quality.
- **Differentiation theater** — introducing nominal quality tiers that do not in fact change rewards. Detection: the new tiers exist on paper but the compensation, status, or selection consequences are unchanged. Correction: tie the differentiation to a consequential reward; without the consequence, the equilibrium is unchanged.

## Source Citations

- Gresham, Sir Thomas (16th c.). Memorandum to Queen Elizabeth I. The originating monetary observation, though the formulation was retroactively named.
- MacLeod, Henry Dunning (1858). *The Elements of Political Economy*. Coined "Gresham's Law" as the canonical name.
- Munger, Charles T. (various lectures, collected in *Poor Charlie's Almanack*). Generalizes the pattern beyond money to any quality-blind reward system.
- Related: Akerlof, George A. (1970). "The Market for 'Lemons': Quality Uncertainty and the Market Mechanism." *Quarterly Journal of Economics* 84(3):488-500. The information-asymmetry sibling.
