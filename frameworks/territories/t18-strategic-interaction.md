# Framework — Strategic Interaction

*Self-contained framework for modeling situations as games between rational (or boundedly rational) agents — equilibria, signaling, incentive design, and mechanism design. Compiled 2026-05-01; `mechanism-design` (Mechanism and Incentive Analysis) added 2026-06-01.*

---

## Territory Header

- **Territory ID:** T18
- **Name:** Strategic Interaction
- **Super-cluster:** D (Position, Stakeholder, and Strategy)
- **Characterization:** Operations that model a situation as a game between rational (or boundedly rational) agents and analyze likely play, equilibria, signaling, and incentive design.
- **Boundary conditions:** Input is a situation modelable as a game with two-or-more agents. Excludes situations where the parties' conflict is to be resolved rather than analyzed strategically (T13).
- **Primary axis:** Complexity (2-to-n-player → mechanism design).
- **Secondary axes:** Specificity (signaling games as their own variant).
- **Coverage status:** Moderate (founder strong; `mechanism-design` built 2026-06-01; signaling gap deferred per CR-6).

---

## When to use this framework

Use T18 when the user has a situation involving two or more agents whose choices interact and wants game-theoretic analysis of likely play: equilibria (Nash, subgame perfect, Perfect Bayesian), credibility of threats and promises, alternative game structures, strategic recommendations grounded in game structure. T18 answers questions like "what will they do if we do X?", "is this threat credible?", "what's their best move?", "are we in a repeated game or one-shot?".

T18 has two resident modes. `strategic-interaction` (the founder) analyzes games of observable moves — equilibria, credibility of threats and promises, repeated play. `mechanism-design` (Mechanism and Incentive Analysis) handles the case where hidden information, hidden action, and the incentive structure are the crux: adverse selection (hidden type, pre-contract), moral hazard (hidden action, post-contract), the winner's curse, signaling, and screening — and it designs the rules, contract, or auction that aligns incentives. It answers questions like "why is this market full of lemons?", "will only the high-risk people opt in?", "design the contract so people behave honestly". The `signaling`-game variant remains deferred per CR-6.

T18 does NOT do interest-mapping for active negotiation guidance (that is T13), descriptive interest-power analysis (that is T2), or feedback-system structural mapping (T4/T17 systems-dynamics). The descriptive behavior of a market's prices and quantities is T17 `market-dynamics`, not this territory.

---

## Within-territory disambiguation

```
[Territory identified: strategic interaction, situation modelable as a game]

Q1 (complexity): "Is the crux observable moves between players
                  (what will they do, what's the equilibrium),
                  or hidden information / hidden action and the incentive structure
                  (who privately knows or does what; designing rules so agents behave)?"
  ├─ "observable moves / equilibrium / what will they do if we do X" →
        strategic-interaction (Tier-2, territory founder)
  ├─ "hidden information / hidden action / adverse selection / moral hazard /
        design the incentives or contract or auction" → mechanism-design (Tier-2)
  └─ ambiguous → strategic-interaction with escalation hook to mechanism-design
```

**Population note.** T18 has two resident modes: `strategic-interaction` (founder) and `mechanism-design` (Mechanism and Incentive Analysis, added 2026-06-01, un-deferring the CR-6 expansion candidate). The `signaling`-game variant remains deferred per CR-6.

**Default route.** `strategic-interaction` at Tier-2 when ambiguous (the founder mode); `mechanism-design` when hidden information, hidden action, or incentive / contract design is the crux.

**Escalation hooks.**
- After `strategic-interaction`: if the question becomes about hidden information / hidden action or designing rules under which agents will produce a desired outcome, hook sideways to `mechanism-design` (now resident).
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

### `mechanism-design` — Mechanism and Incentive Analysis

**Educational name:** mechanism design and information-economics analysis (adverse-selection / moral-hazard / auction lineage) (complexity-mechanism-design).

**Plain-language description.** Analysis of situations where hidden information, hidden action, and the incentive structure — not the observable moves — determine the outcome, and (when asked) design of the rules, contract, or auction that aligns incentives. Names the parties and the information asymmetry (who privately knows or does what, unobserved by whom, and when); classifies it as adverse selection (hidden type, pre-contract) or moral hazard (hidden action, post-contract), naming both if both operate; traces the distortion (which good actors exit, which hidden risks are taken, who overpays, pooling vs. separating outcome); grounds named mechanisms (winner's curse, signaling, screening, principal-agent) in their operation here; for a design, satisfies BOTH participation (individual-rationality) and incentive-compatibility constraints and surfaces the residual gaming surface; marks the analysis-vs-design posture explicitly.

**Critical questions.**
- CQ1: Is the information asymmetry named explicitly — who holds private information or takes hidden action, and who cannot observe it?
- CQ2: Is hidden information (adverse selection — type private before contracting) distinguished from hidden action (moral hazard — effort private after contracting)?
- CQ3: For a designed mechanism, are participation (individual-rationality) and incentive-compatibility both addressed?
- CQ4: When a named mechanism concept is invoked (winner's curse, screening, signaling), is its actual mechanism shown to operate here, or is it a name-drop?
- CQ5: Is the analytical-vs-design posture explicit, rather than silently sliding between explaining a failure and proposing a fix?

**Per-pipeline-stage guidance.**
- **Analyst.** Name the parties and the asymmetry (who knows/does what unseen, and when); classify adverse selection vs. moral hazard; trace the distortion; scan named mechanisms and ground each; for a design, check both participation and incentive-compatibility and surface the gaming surface; mark posture.
- **Evaluator.** Verify the asymmetry is named (asymmetry-unnamed, assume-away-asymmetry); verify selection/hazard distinguished (selection-hazard-conflation); verify both design constraints present (constraint-omission); verify named mechanisms grounded (mechanism-name-drop); verify posture marked (posture-drift).
- **Reviser.** Name the asymmetry first; separate adverse selection from moral hazard (the pre-contract/post-contract distinction is the parse-preserving core); add the missing design constraint (participation or incentive-compatibility); ground each named concept or cut it; mark analysis vs. design explicitly.
- **Verifier.** Confirm seven sections (parties_and_asymmetry, selection_vs_hazard, distortion, named_mechanisms, mechanism_for_design, read, confidence_and_assumptions); confirm a design carries BOTH constraints and that the posture is explicit.
- **Consolidator.** Merge as an information-and-incentive atom set: party-and-asymmetry lock, selection-vs-hazard classification atoms, distortion-trace atoms, named-mechanism atoms grounded in operation, design-constraint atoms (participation + incentive-compatibility), gaming-surface atoms, confidence-with-information-assumption atoms.

**Source tradition.** Akerlof market-for-lemons (adverse selection); Holmström / principal-agent theory (moral hazard); Spence signaling; Stiglitz-Rothschild screening; Vickrey-Myerson mechanism design and auction theory.

**Lens dependencies.**
- Required: adverse-selection, moral-hazard.
- Optional: winners-curse, signaling, principal-agent-problem.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

**Decision note (2026-06-01).** Mechanism and Incentive Analysis un-defers the `mechanism-design` CR-6 expansion candidate. It is the complexity-axis sibling of `strategic-interaction`: that mode analyzes games of observable moves; this one handles the case where hidden information (adverse selection), hidden action (moral hazard), and incentive structure are the crux, and extends to designing mechanisms. The parse-preserving boundary against T17 `market-dynamics` is information-vs-price: this mode is about who-knows-what and how incentives are structured; market-dynamics is about how prices and quantities behave. v1 keeps designs at the structural level (constraints named and satisfied qualitatively) and flags when a problem needs formal optimization (revelation principle, optimal-auction derivation).

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

### T17 ↔ T18 (Process and System Analysis ↔ Strategic Interaction)

**Why adjacent.** Both can engage with markets and economic situations. T17's `market-dynamics` describes how a market *behaves* (prices, quantities, selection, competition); T18's `mechanism-design` analyzes the *information-and-incentive structure* and *designs* the rules, contract, or auction.

**Disambiguating question.** "Is the question how this market behaves (prices, supply and demand, competition — describe), or is it about hidden information / hidden action and designing the incentives or contract (analyze / design)?"

**Routing.** Market behavior, descriptive → T17 `market-dynamics`. Information-and-incentive structure or mechanism design → T18 `mechanism-design`. (A used-car or insurance market can be read either way: market-dynamics asks where the price settles; mechanism-design asks why the informed side self-selects and how to separate the types.)

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

Mechanism design is now a resident T18 mode (`mechanism-design`, built 2026-06-01); this lens supplies its formal-design foundations alongside the adverse-selection and moral-hazard lenses below.

### Adverse Selection (required for mechanism-design)

**Core Structure.** A hidden-*type* problem: one side knows its own quality or risk type before contracting, and the other side cannot observe it. Because the uninformed side can only price to the average, the best types are underpaid and exit, lowering the average, which drives out the next-best types — the market unravels toward the worst types (Akerlof's "lemons"). Distinguished from moral hazard by timing: the asymmetry is over a *type fixed before* the contract. Remedies separate the types: signaling (the informed side takes a costly action only good types will bear) and screening (the uninformed side offers a self-sorting menu). Conflating adverse selection with moral hazard is a hard failure mode (`selection-hazard-conflation`).

### Moral Hazard (required for mechanism-design)

**Core Structure.** A hidden-*action* problem: after contracting, one party takes an action (effort, risk-taking, care) the other cannot observe, and the incentive structure makes the unobserved action diverge from what the counterparty would want — the insured drives less carefully, the agent shirks, the borrower takes on more risk. Distinguished from adverse selection by timing: the asymmetry is over an *action exercised after* the contract. Remedies tie payoff to observable proxies of the action (deductibles, performance pay, monitoring, bonding) so the incentive-compatible action moves toward the desired one. The principal-agent split is the canonical frame.

### Bounded Rationality (Simon) (foundational)

**Core Structure.** Herbert Simon's foundational alternative to perfect rationality: agents have computational limits, information limits, and time limits that constrain their decision-making. Key concepts:

- **Satisficing** — agents accept the first option that meets a threshold rather than optimizing.
- **Heuristics** — rules of thumb that approximate optimal decisions under bounded resources.
- **Decision costs** — analyzing alternatives is itself costly; rational agents do not analyze indefinitely.
- **Procedural vs. substantive rationality** — a procedure can be rational (good given limits) even when the resulting choice is not substantively optimal.

For T18, the hyperrationality-trap is the failure mode that bounded rationality guards against: equilibrium analyses that assume perfect rationality without bounded-rationality assessment misrepresent how real agents will play. The credibility audit and the alternative-structure test partly address this; explicit bounded-rationality flagging is the additional discipline.

---

## Open debates

T18 carries no territory-level open debates at present. Mode-level debates are carried in the mode specs: the Hyperrationality vs. Bounded-Rationality choice within `strategic-interaction`, and the structural-vs-formal boundary within `mechanism-design` (how far a design should go before it needs the revelation principle or an optimal-auction derivation).

---

## Citations and source-tradition attributions

- von Neumann, J. & Morgenstern, O. (1944). *Theory of Games and Economic Behavior*. Princeton University Press. Foundational text.
- Nash, J. F. (1950). "Equilibrium Points in N-person Games." *Proceedings of the National Academy of Sciences*. Nash equilibrium.
- Schelling, T. C. (1960). *The Strategy of Conflict*. Harvard University Press. Commitment, credibility, focal points.
- Schelling, T. C. (1980). *Micromotives and Macrobehavior*. W. W. Norton. Aggregation of strategic interaction.
- Axelrod, R. (1984). *The Evolution of Cooperation*. Basic Books. Iterated prisoner's dilemma tournament.
- Fudenberg, D. & Tirole, J. (1991). *Game Theory*. MIT Press. Standard graduate-level reference.
- Myerson, R. B. (1991). *Game Theory: Analysis of Conflict*. Harvard University Press. Mechanism design foundations.
- Akerlof, G. A. (1970). "The Market for 'Lemons': Quality Uncertainty and the Market Mechanism." *Quarterly Journal of Economics* 84(3). Adverse selection (mechanism-design).
- Spence, M. (1973). "Job Market Signaling." *Quarterly Journal of Economics* 87(3). Signaling (mechanism-design).
- Holmström, B. (1979). "Moral Hazard and Observability." *Bell Journal of Economics* 10(1). Moral hazard / principal-agent (mechanism-design).
- Vickrey, W. (1961). "Counterspeculation, Auctions, and Competitive Sealed Tenders." *Journal of Finance* 16(1). Auction theory (mechanism-design).
- Simon, H. A. (1955). "A Behavioral Model of Rational Choice." *Quarterly Journal of Economics*. Bounded rationality.
- Simon, H. A. (1996). *The Sciences of the Artificial* (3rd ed.). MIT Press. Foundational bounded-rationality treatment.
- Kahneman, D. & Tversky, A. (Various). Heuristics-and-biases catalog (foundational substrate).

*End of Framework — Strategic Interaction.*
