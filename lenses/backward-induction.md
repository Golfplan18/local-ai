---
lens_id: backward-induction
name: Backward Induction
lens_type: mental-model
applicability: [game-theoretic-analysis, sequential-planning, negotiation-strategy]
foundational: false
source: "Zermelo, Ernst (1913). Über eine Anwendung der Mengenlehre auf die Theorie des Schachspiels. Proceedings of the Fifth International Congress of Mathematicians. Selten, Reinhard (1965). Spieltheoretische Behandlung eines Oligopolmodells mit Nachfrageträgheit. Zeitschrift für die gesamte Staatswissenschaft 121."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - game-theory
  - planning
---

# Backward Induction

*A lens that solves sequential decision problems by reasoning from the final stage backward to the first, ensuring each choice accounts for the rational responses that will follow rather than optimizing myopically for the immediate next step.*

---

## Trigger

Invoked when the analyst faces a sequential decision with a known endpoint where each choice changes the options available later, and forward planning is producing too many branching possibilities or missing the strategic interactions of later stages. The lens supplies the recursive reasoning protocol — start at the last stage, fold each future-stage solution back into the current stage — that produces subgame-perfect strategies in finite games.

## Core Structure

### Core Insight

To find the optimal strategy in a sequential decision problem, start at the final decision point, determine what the rational choice would be there, then step backward to the preceding decision point — now knowing what will happen next — and repeat until you reach the present. The method ensures that every move accounts for the full chain of future consequences rather than optimizing myopically for the next step.

### Mechanism

In a finite sequential game, the rational choice at the last stage is determined by the immediate payoffs alone (no future stages remain). This determines the payoff at the penultimate stage as a function of the choices made there; each choice's payoff includes the rational last-stage response to it. The penultimate stage thus reduces to a one-shot decision with payoffs that already encode future rationality. Iterating this folding process backward produces a fully-specified optimal strategy at every stage — the subgame-perfect equilibrium. Forward reasoning fails because each early choice's payoff cannot be evaluated without already knowing what later players will do; backward induction supplies that information by construction.

### Applicability Conditions

- The decision problem is sequential and finite (a definite endpoint exists).
- The endpoint's payoffs are known or computable.
- All players (or the single decision-maker at multiple stages) are reasoning rationally and this is common knowledge.
- The branching tree is bounded enough to traverse in reverse.

### Common Misapplications

- Applying to infinite or indefinitely-repeated games where backward induction does not terminate; folk theorems and other tools are needed.
- Applying when players are not common-knowledge rational; behavioral departures (limited foresight, fairness preferences, threats) break the construction.
- Treating the produced strategy as descriptively correct in real-world settings where the rationality assumptions fail; backward induction often *predicts* outcomes that humans do not actually choose (e.g., the centipede game).

### Related Models

- **Subgame Perfection** — the equilibrium concept backward induction produces in extensive-form games.
- **Dynamic Programming** — the algorithmic generalization for non-strategic sequential optimization.
- **Folk Theorems** — what replaces backward induction in indefinitely-repeated games.

## Application Steps

1. Define the decision tree: stages, choices at each stage, terminal payoffs.
2. Solve the final stage: determine the optimal choice and payoff at every leaf.
3. Step back one stage: at each node, fold in the optimal response from the next stage and choose the best move at this node given that fold.
4. Repeat until reaching the root (the present); the move chosen at the root is the optimal first action given full backward reasoning.
5. Test the produced strategy against the rationality assumptions: do the predicted later-stage choices match what the actual players would do?

## Detection Signals

- The decision is sequential with a known endpoint and each choice changes later options.
- Forward planning is producing an unmanageable branching tree.
- The optimal first move is non-obvious because its value depends on responses many stages later.
- A negotiation has multiple rounds and the analyst is trying to determine the opening offer.
- A planning problem has a fixed deadline and the question is what must happen now to land at the desired end state.

## Critical Questions

- Is the game finite with a known endpoint, or indefinitely repeated? Backward induction does not apply to the latter.
- Are all players rational and is rationality common knowledge? Behavioral departures invalidate the produced strategy as a prediction (though it may still be the strategist's best response).
- Are the terminal payoffs accurately specified? Errors at the leaf compound through every backward step.
- Is the produced strategy actually played by the relevant counterparties, or do they depart from it (e.g., the centipede paradox)? If they depart, the analyst may need to abandon strict backward induction.
- Is the branching tree small enough to traverse, or does it require approximation (the limit case where dynamic programming and heuristics substitute for full induction)?

## Common Failure Modes

- **Infinite-game misapplication** — the lens is applied to an indefinitely-repeated game where backward induction does not terminate. Detection: there is no known last stage. Correction: switch to folk-theorem analysis or use a finite truncation as an approximation, with caveats.
- **Rationality assumption failure** — the strategy is predicted using full common-knowledge rationality but the counterparty is behavioral. Detection: predicted last-stage moves do not match observed play. Correction: model the counterparty's actual decision rule (level-k thinking, fairness preferences, threats) and re-induct.
- **Payoff misspecification** — terminal payoffs are estimated incorrectly, propagating errors backward through every stage. Detection: the optimal first move is highly sensitive to specific payoff numbers. Correction: sensitivity analysis on terminal payoffs; if small changes flip the optimal first move, the analysis is fragile.
- **Centipede paradox** — the lens produces a counterintuitive prediction (e.g., immediate defection in long-cooperation games) that contradicts actual play. Detection: humans cooperate where backward induction predicts defection. Correction: this is a known limit; supplement with behavioral or limited-rationality models.

## Source Citations

- Zermelo, Ernst (1913). "Über eine Anwendung der Mengenlehre auf die Theorie des Schachspiels." Earliest formalization in chess theory.
- Selten, Reinhard (1965). "Spieltheoretische Behandlung eines Oligopolmodells mit Nachfrageträgheit." Subgame perfection in industrial economics; awarded Nobel Prize 1994.
- Kuhn, Harold W. (1953). "Extensive Games and the Problem of Information." *Contributions to the Theory of Games* II. Princeton University Press. Extensive-form game theory.
- Rosenthal, Robert (1981). "Games of Perfect Information, Predatory Pricing and the Chain-Store Paradox." *Journal of Economic Theory* 25(1):92-100. The centipede paradox.
- Related: Subgame Perfection; Dynamic Programming; Folk Theorems.
