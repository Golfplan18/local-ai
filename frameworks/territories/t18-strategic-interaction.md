# Framework — Strategic Interaction

*Self-contained framework for modeling situations as games between rational (or boundedly rational) agents — equilibria, signaling, incentive design (singleton territory). Compiled 2026-05-01.*

---

## Territory Header

- **Territory ID:** T18
- **Name:** Strategic Interaction
- **Super-cluster:** D (Position, Stakeholder, and Strategy)
- **Characterization:** Operations that model a situation as a game between rational (or boundedly rational) agents and analyze likely play, equilibria, signaling, and incentive design.
- **Boundary conditions:** Input is a situation modelable as a game with two-or-more agents. Excludes situations where the parties' conflict is to be resolved rather than analyzed strategically (T13).
- **Primary axis:** Complexity (2-to-n-player → mechanism design).
- **Secondary axes:** Specificity (signaling games as their own variant).
- **Coverage status:** Moderate (founder strong; gaps deferred per CR-6).

---

## When to use this framework

Use T18 when the user has a situation involving two or more agents whose choices interact and wants game-theoretic analysis of likely play: equilibria (Nash, subgame perfect, Perfect Bayesian), credibility of threats and promises, alternative game structures, strategic recommendations grounded in game structure. T18 answers questions like "what will they do if we do X?", "is this threat credible?", "what's their best move?", "are we in a repeated game or one-shot?".

T18 does NOT do interest-mapping for active negotiation guidance (that is T13), descriptive interest-power analysis (that is T2), or feedback-system structural mapping (T4/T17 systems-dynamics).

---

## Within-territory disambiguation

```
[Territory identified: strategic interaction, situation modelable as a game]

Route: strategic-interaction (Tier-2, territory founder)
```

**Singleton territory.** T18 currently has one resident mode (`strategic-interaction`). Expansion candidates `mechanism-design` and `signaling` are deferred per CR-6.

**Default route.** `strategic-interaction` at Tier-2.

**Escalation hooks.**
- After `strategic-interaction`: if the question becomes about designing rules under which agents will produce a desired equilibrium, hook upward to `mechanism-design` (deferred — surface the flag).
- After `strategic-interaction`: if the question becomes specifically about signaling-game dynamics (asymmetric information, costly signals), hook sideways to `signaling` (deferred — surface the flag).
- After `strategic-interaction`: if the question shifts from analyzing the game to actually negotiating it, hook sideways to T13 (`principled-negotiation` or `third-side`).
- After `strategic-interaction`: if the question shifts to "where could this strategic structure fail", hook sideways to T7 (`pre-mortem-fragility` or `fragility-antifragility-audit`).
- After `strategic-interaction`: if the question is really about who benefits and who has power rather than equilibrium analysis, hook sideways to T2 (`cui-bono`).

---

## Mode entries

### `strategic-interaction` — Strategic Interaction

**Educational name:** strategic interaction analysis (game-theoretic, 2-to-n-player) (complexity-2-to-n-player).

**Plain-language description.** Game-theoretic analysis of a multi-agent situation. Names players with payoffs in their actual value terms (not what they claim to want); classifies the game on all four dimensions (timing — simultaneous vs. sequential; information — complete vs. incomplete, perfect vs. imperfect; duration — one-shot vs. repeated; sum — zero-sum vs. positive-sum); identifies equilibria with method named (backward induction / Nash / subgame perfect / repeated cooperation / Perfect Bayesian); audits threats and promises for credibility (cheap talk vs. commitment device; sunk costs vs. future-shadow); tests at least one alternative game structure (different timing/information/duration/sum framing); produces specific strategic recommendations grounded in game structure.

**Critical questions.**
- CQ1: Has the game been classified on all four dimensions (timing, information, duration, sum)?
- CQ2: Has the equilibrium method been named (backward induction / Nash / subgame perfect / repeated cooperation / Perfect Bayesian)?
- CQ3: Have threats and promises passed the credibility test, or are some cheap talk?
- CQ4: Has at least one alternative game structure been tested, or is the analysis classification-locked?
- CQ5: Have payoffs been stated in each player's actual value terms, not what they claim to want?

**Per-pipeline-stage guidance.**
- **Analyst.** Name players with actual-value payoffs; classify game on four dimensions; identify equilibria with method named; audit credibility of threats/promises; test ≥1 alternative structure; produce mechanism-grounded strategic recommendations.
- **Evaluator.** Verify four-dimension classification; verify method named with derivation traceable; verify credibility check on each threat/promise; verify alternative structure tested; verify payoffs in actual value terms.
- **Reviser.** Name equilibrium method where asserted without trace; add missing classification dimension; add credibility assessment where missing; add alternative structure paragraph if locked; resist hyperrationality drift.
- **Verifier.** Confirm six required sections (players_and_payoffs, game_classification, equilibrium_analysis, credibility_assessment, alternative_structures, strategic_recommendations); confirm no decision-node edge carries probability (decisions are choices, not chance outcomes — hard verification failure).
- **Consolidator.** Merge as a structured analysis; decision-tree-friendly when sequential; matrix-friendly when simultaneous.

**Source tradition.** Game-theory equilibrium concepts (Nash, subgame perfect, Perfect Bayesian); Schelling strategy of conflict (commitment, credibility, focal points); Axelrod evolution of cooperation (when game is repeated); mechanism-design foundations (when designing rather than playing the game).

**Lens dependencies.**
- Required: game-theory-equilibrium-concepts, schelling-strategy-of-conflict.
- Optional: axelrod-evolution-of-cooperation (when game is repeated), mechanism-design-foundations (when designing rather than playing).
- Foundational: kahneman-tversky-bias-catalog, bounded-rationality-simon.

**Composition.** Atomic.

---

## Cross-territory adjacencies

### T13 ↔ T18 (Negotiation ↔ Strategic Interaction)

**Disambiguating question.** Active negotiation guidance with integrative possibility (T13), or game-theoretic equilibrium analysis with formal payoffs (T18)?

**Routing.** Active negotiation guidance → T13. Strategic-game equilibrium analysis → T18.

### T2 ↔ T18 (Interest and Power ↔ Strategic Interaction)

**Disambiguating question.** Descriptive interest/power analysis (T2), or formal game-theoretic equilibrium with payoffs (T18)?

**Routing.** Distributive interest tracing without modeling interaction → T2. Equilibrium analysis with credibility assessment → T18.

### T7 ↔ T18 (Risk and Failure ↔ Strategic Interaction)

**Disambiguating question.** Where could the strategic structure fail (T7), or what is the equilibrium analysis (T18)?

**Routing.** Failure of strategic structure → T7. Equilibrium analysis → T18.

---

## Lens references (Core Structure embedded)

### Game-Theory Equilibrium Concepts (required)

**Core Structure.** A taxonomy of equilibrium concepts, each with a different solution method:

- **Nash equilibrium** — a strategy profile where no player can improve their payoff by unilaterally changing strategy. Method: best-response analysis on the payoff matrix; intersection of best-response correspondences identifies Nash equilibria.
- **Subgame perfect equilibrium** — a Nash equilibrium that remains a Nash equilibrium in every subgame. Method: backward induction in extensive-form (sequential) games; eliminates non-credible threats. Required when the game has sequential moves.
- **Perfect Bayesian equilibrium** — generalizes subgame perfect to games with incomplete information; players' beliefs about types must be Bayes-consistent. Method: pair strategies with beliefs and check both incentive compatibility and Bayes consistency.
- **Repeated-game cooperation** — in indefinitely repeated games, cooperation can be sustained as equilibrium via grim-trigger or tit-for-tat strategies (folk theorems). Method: identify the discount factor at which cooperation becomes self-enforcing.

The discipline: name the method explicitly. Asserting equilibria without naming the method is a failure mode (`method-unnamed`). The method's derivation should be traceable from the players, payoffs, and game classification.

### Schelling Strategy of Conflict (required)

**Core Structure.** Thomas Schelling's framework for analyzing strategic interaction with emphasis on the credibility of threats and promises. Key concepts:

- **Commitment device** — a constraint a player imposes on their own future choices to make a threat or promise credible. Burn the bridges behind you so retreat is impossible.
- **Credibility test** — would the threatener actually carry out the threat if put to the test? Threats that would harm the threatener as much as the target are typically not credible (cheap talk).
- **Focal point** — in coordination games with multiple equilibria, a salient solution that players converge on without communication (the natural meeting place at noon under the clock).
- **Sunk costs** — investments already made that cannot be recovered; properly ignored in forward decisions but often signal commitment to others.
- **Future shadow** — the expected continuation of the relationship; in repeated games, the future shadow's length determines whether cooperation is self-enforcing.

The credibility audit: for each declared threat or promise, name whether it is cheap talk (no commitment), backed by sunk costs (signal commitment), backed by commitment device (binds future), or backed by future shadow (repeated game). Cheap talk treated as credible is a hard failure mode.

### Axelrod Evolution of Cooperation (optional for repeated games)

**Core Structure.** Robert Axelrod's tournament results on the iterated prisoner's dilemma:

- **Tit-for-tat** wins repeated tournaments by being nice (never first to defect), retaliatory (responds to defection immediately), forgiving (one-period punishment), and clear (predictable).
- **Cooperation can emerge** in indefinitely repeated games even among self-interested agents when the discount factor is high enough.
- **Population dynamics** — strategies that cooperate with similar strategies and punish defectors can outperform always-defect populations through differential reproduction.

For T18, Axelrod's results inform repeated-game analysis: when the game is genuinely repeated and the discount factor is high, cooperation may be the equilibrium even though one-shot analysis would predict defection. The static-frame trap (one-shot analysis applied to what is actually a repeated game) is a failure mode addressed by repeated-game testing.

### Mechanism Design Foundations (optional for game-design rather than game-playing)

**Core Structure.** Reverse game theory: rather than analyzing equilibria of a given game, design the rules so that agents pursuing their own interests produce a desired equilibrium outcome. Key concepts:

- **Incentive compatibility** — the mechanism's payoffs make truth-telling (or the desired action) the agents' best strategy.
- **Individual rationality** — agents prefer participating to not participating.
- **Revelation principle** — any equilibrium of any mechanism can be replicated by a direct-revelation mechanism in which agents report their types truthfully.
- **Auction theory** — applications to selling and buying with private information (Vickrey auction, English auction, sealed-bid auctions).

Mechanism-design extensions are deferred per CR-6 to a future `mechanism-design` mode; the founder T18 mode names the lens for transparency when game-design questions surface.

### Bounded Rationality (Simon) (foundational)

**Core Structure.** Herbert Simon's foundational alternative to perfect rationality: agents have computational limits, information limits, and time limits that constrain their decision-making. Key concepts:

- **Satisficing** — agents accept the first option that meets a threshold rather than optimizing.
- **Heuristics** — rules of thumb that approximate optimal decisions under bounded resources.
- **Decision costs** — analyzing alternatives is itself costly; rational agents do not analyze indefinitely.
- **Procedural vs. substantive rationality** — a procedure can be rational (good given limits) even when the resulting choice is not substantively optimal.

For T18, the hyperrationality-trap is the failure mode that bounded rationality guards against: equilibrium analyses that assume perfect rationality without bounded-rationality assessment misrepresent how real agents will play. The credibility audit and the alternative-structure test partly address this; explicit bounded-rationality flagging is the additional discipline.

---

## Open debates

T18 carries no territory-level open debates at present. As a singleton territory, mode-level debates do not currently apply. The Hyperrationality vs. Bounded-Rationality choice is treated within the mode rather than as a debate.

---

## Citations and source-tradition attributions

- von Neumann, J. & Morgenstern, O. (1944). *Theory of Games and Economic Behavior*. Princeton University Press. Foundational text.
- Nash, J. F. (1950). "Equilibrium Points in N-person Games." *Proceedings of the National Academy of Sciences*. Nash equilibrium.
- Schelling, T. C. (1960). *The Strategy of Conflict*. Harvard University Press. Commitment, credibility, focal points.
- Schelling, T. C. (1980). *Micromotives and Macrobehavior*. W. W. Norton. Aggregation of strategic interaction.
- Axelrod, R. (1984). *The Evolution of Cooperation*. Basic Books. Iterated prisoner's dilemma tournament.
- Fudenberg, D. & Tirole, J. (1991). *Game Theory*. MIT Press. Standard graduate-level reference.
- Myerson, R. B. (1991). *Game Theory: Analysis of Conflict*. Harvard University Press. Mechanism design foundations.
- Simon, H. A. (1955). "A Behavioral Model of Rational Choice." *Quarterly Journal of Economics*. Bounded rationality.
- Simon, H. A. (1996). *The Sciences of the Artificial* (3rd ed.). MIT Press. Foundational bounded-rationality treatment.
- Kahneman, D. & Tversky, A. (Various). Heuristics-and-biases catalog (foundational substrate).

*End of Framework — Strategic Interaction.*
