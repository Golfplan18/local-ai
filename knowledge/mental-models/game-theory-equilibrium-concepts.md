---
lens_id: game-theory-equilibrium-concepts
name: Game Theory Equilibrium Concepts
lens_type: catalog
applicability: [strategic-interaction]
foundational: true
source: "Nash, John (1950). Equilibrium Points in n-Person Games. Proceedings of the National Academy of Sciences."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - game-theory
  - strategy
  - equilibrium
---

# Game Theory Equilibrium Concepts

## Trigger

Invoked when strategic-interaction analysis needs to identify stable strategy profiles rather than simply list incentives. The host mode supplies players, choices, payoffs, and information; the lens supplies equilibrium concepts.

## Core Structure

Equilibrium concepts describe strategy patterns that are stable under specified assumptions.

1. **Dominant strategy.** Best response regardless of what others do.
2. **Nash equilibrium.** No player benefits by unilaterally deviating.
3. **Mixed equilibrium.** Players randomize to make opponents indifferent.
4. **Subgame-perfect equilibrium.** Sequential-game equilibrium that remains credible in every subgame.
5. **Pareto efficiency.** No player can be made better off without making another worse off.
6. **Coordination equilibrium.** Multiple stable outcomes exist; expectations select among them.
7. **Evolutionary stability.** A strategy resists invasion by alternatives in repeated population dynamics.

## Application Steps

1. Identify players, strategies, payoffs, timing, and information.
2. Check for dominant strategies.
3. Identify best responses for each player.
4. Find strategy profiles where best responses coincide.
5. Test credibility in sequential settings.
6. Distinguish equilibrium stability from social desirability.

## Detection Signals

- Strategic actors respond to each other's expected choices.
- The analysis needs to know whether an outcome is stable.
- Multiple possible coordination points exist.
- A policy tries to move actors from one equilibrium to another.

## Critical Questions

- What is each player's best response?
- Can any player improve by unilateral deviation?
- Is the equilibrium credible after the game begins?
- Is the equilibrium efficient, or merely stable?
- What expectation or institution selects among multiple equilibria?

## Common Failure Modes

- **Equilibrium-good confusion** - Detection: stable is treated as desirable. Correction: separate stability from welfare.
- **Static-game mismatch** - Detection: a sequential game is analyzed as simultaneous. Correction: model timing and credibility.
- **Payoff vagueness** - Detection: preferences are assumed rather than mapped. Correction: state payoff ordering.
- **Single-equilibrium tunnel** - Detection: one stable outcome is named while alternatives exist. Correction: search for multiple equilibria.

## Source Citations

- Nash, John (1950). "Equilibrium Points in n-Person Games." *Proceedings of the National Academy of Sciences*.
- Osborne, Martin J. and Rubinstein, Ariel (1994). *A Course in Game Theory*. MIT Press.

