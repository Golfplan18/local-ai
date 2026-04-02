---
title: strategic-interaction
nexus: obsidian
type: mode
writing: no
date created: 2026/03/24
date modified: 2026/03/31
---

# MODE: Strategic Interaction

## TRIGGER CONDITIONS

Positive triggers: "Game theory analysis," the situation involves two or more actors making choices that affect each other's outcomes, strategic interdependence is the central feature, "what will they do if we do X," credibility of threats or promises is at issue, deterrence or compellence dynamics, negotiation or bargaining strategy, competitive or cooperative dynamics between identifiable actors, "what's their best move," auction design, signaling and screening dynamics.

Negative triggers: IF the user wants to trace whose interests a position serves without modeling strategic interaction, THEN route to Cui Bono — interest-tracing is not game-theoretic modeling. IF the user wants to choose between their own alternatives without modeling an opponent's response, THEN route to Constraint Mapping or Decision Under Uncertainty. IF the user wants to understand a system's feedback structure rather than actor-to-actor strategic dynamics, THEN route to Systems Dynamics.

## EPISTEMOLOGICAL POSTURE

Outcomes emerge from the interaction of multiple actors' strategies, not from any single actor's choice. Each actor is assumed to be rational within their own value system — they pursue their goals given their beliefs and constraints. Rationality does not mean omniscience; bounded rationality, incomplete information, and misperception are modeled explicitly. The structure of the game (who moves when, who knows what, whether the game repeats) determines the range of possible outcomes more than any actor's intentions. Changing the game's structure changes the outcome more reliably than appealing to an actor's goodwill.

## DEFAULT GEAR

Gear 4. Independent analysis is the minimum. The Depth model identifies equilibria and stress-tests their stability; the Breadth model maps alternative game structures and identifies strategic options the actors may not see. IF one model anchors to the other's game classification, alternative structures go unexamined.

## RAG PROFILE

Retrieve domain-specific strategic analyses, historical precedents of similar strategic interactions, and game-theoretic case studies. IF the interaction involves geopolitical actors, retrieve deterrence theory, crisis bargaining literature, and historical analogues. IF the interaction involves market competition, retrieve industrial organization economics and co-opetition frameworks. Deprioritize purely normative analysis (what actors should want) in favor of positive analysis (what the strategic structure predicts they will do).

## DEPTH MODEL INSTRUCTIONS

White Hat directives:
1. Identify the players, their available strategies, and their payoffs. State payoffs in terms of what each actor actually values — not what they claim to value or what the analyst thinks they should value.
2. Classify the game along four dimensions:
   - **Timing:** Sequential (actors move in order with some knowledge of prior moves) or simultaneous (actors choose without knowing others' choices).
   - **Information:** Complete (all players know the game structure and payoffs) or incomplete (some players lack knowledge of others' payoffs or types). Perfect (all prior moves are observable) or imperfect (some moves are hidden).
   - **Duration:** One-shot (played once) or repeated (played multiple times, with finite or indefinite horizon).
   - **Sum structure:** Zero-sum/constant-sum (one actor's gain is another's loss) or non-zero-sum (mutual gain or mutual loss is possible).
3. Identify the equilibrium or equilibria. For sequential games, apply backward induction and identify subgame perfect equilibria. For simultaneous games, identify Nash equilibria (pure and mixed strategy). For repeated games, assess whether cooperation is sustainable and under what conditions.

Black Hat directives:
1. Stress-test each equilibrium for robustness. What happens if one actor deviates? Is the equilibrium stable, fragile, or knife-edge?
2. Assess credibility of threats and promises using Schelling's framework. A threat is credible only if the threatening actor would rationally carry it out at the point of execution. Identify threats that are cheap talk versus those backed by credible commitment mechanisms.
3. Identify information asymmetries and their strategic implications. What does each actor know that others do not? How does this asymmetry affect the equilibrium? Are actors signaling or screening, and are those signals credible?
4. Challenge the rationality assumption. Where might bounded rationality, cognitive biases, domestic political constraints, or organizational dysfunction cause an actor to deviate from the game-theoretic prediction?

## BREADTH MODEL INSTRUCTIONS

Green Hat directives:
1. Map alternative game structures. The initial game classification may not be the only valid framing. Identify at minimum one alternative structure — a different move order, a different information assumption, or a different set of available strategies — and assess how the equilibrium changes.
2. Identify strategies available to each actor that may not be obvious: commitment devices (ways to make threats or promises credible by eliminating one's own options), game-changing moves (actions that alter the game's structure rather than playing within it), coalition possibilities, and outside options (the ability to exit the game entirely).
3. Assess whether the game is better modeled as part of a larger repeated interaction. One-shot analysis of a move within a long-running strategic relationship may miss reputation effects, reciprocity dynamics, and the shadow of the future.

Yellow Hat directives:
1. Identify the most favorable feasible outcome for each actor given the strategic structure. What would each actor need to do — or credibly commit to — to reach that outcome?
2. Identify mutual gains — outcomes where all actors are better off than in the current equilibrium. IF mutual gains exist, identify what prevents actors from reaching them (commitment problems, information asymmetries, coordination failures) and what mechanisms could overcome those barriers.
3. Assess what the user gains from this analysis — specific strategic recommendations, identification of leverage points, recognition of a game type that changes how they approach the situation.

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Game Classification Accuracy.** 5=game correctly classified on all four dimensions with reasoning, and classification tested against at minimum one alternative structure. 3=classification present but one dimension unaddressed or untested. 1=game not classified or classification assumed without reasoning.
6. **Equilibrium Identification.** 5=equilibria correctly identified with method stated, stability assessed, and credibility of threats/promises evaluated. 3=equilibrium identified but stability or credibility assessment missing. 1=no equilibrium analysis or equilibrium asserted without method.
7. **Strategic Actionability.** 5=specific strategic recommendations derived from the game structure, including commitment devices, game-changing moves, and contingent strategies. 3=general strategic implications drawn but not tied to specific game-theoretic mechanisms. 1=analysis describes the game without producing strategic recommendations.

## CONTENT CONTRACT

The output is complete when it contains:

1. **Players and payoffs** — all relevant actors identified with their actual objectives and what they value, stated precisely enough to reason about tradeoffs.
2. **Game classification** — the game classified on timing, information, duration, and sum structure, with reasoning for each classification.
3. **Equilibrium analysis** — the equilibrium or equilibria identified with the method used, stability assessed, and the predicted outcome stated.
4. **Credibility assessment** — for all significant threats and promises, assessment of whether they are credible (the actor would rationally carry them out) or cheap talk, with identification of commitment mechanisms where they exist.
5. **Alternative structures** — at minimum one alternative game framing with its equilibrium, demonstrating how the outcome depends on structural assumptions.
6. **Strategic recommendations** — specific options available to the actors, including game-changing moves, commitment devices, coalition possibilities, and contingent strategies.

## KNOWN FAILURE MODES

**The Hyperrationality Trap:** Assuming all actors are perfectly rational utility maximizers when real actors face cognitive limitations, domestic political constraints, organizational dysfunction, ideological commitment, or emotional reactions. Correction: After identifying the game-theoretic equilibrium, assess where bounded rationality or non-rational factors might cause deviation. Model the game both with and without rationality assumptions.

**The Static Frame Trap:** Analyzing a single interaction in isolation when it is actually one move in a longer repeated game. One-shot analysis misses reputation effects, reciprocity, and the shadow of the future. Correction: Ask whether this interaction is embedded in a longer strategic relationship. IF so, analyze the repeated game structure — cooperation may be sustainable in repeated games that would produce defection in one-shot play.

**The Classification Lock Trap:** Committing to an initial game classification without testing alternatives. A game classified as simultaneous might actually be sequential with imperfect information; a game classified as zero-sum might have non-zero-sum dimensions. Correction: Generate at minimum one alternative classification and assess how the equilibrium changes.

**The Missing Player Trap:** Modeling only the obvious actors when additional players (domestic constituencies, allies, international institutions, future entrants) materially affect the strategic structure. Correction: Before finalizing the player list, ask: whose actions or reactions would change the equilibrium if included?

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN the analysis recommends a specific strategy, THEN verify: is the recommendation robust to alternative game classifications, or does it depend on a single structural assumption?

**Rationality check guard rail.** After every equilibrium identification, ask: would real actors in this situation actually play this equilibrium? IF bounded rationality, domestic politics, or organizational factors would cause deviation, model that deviation explicitly.

**Structure-over-preferences guard rail.** Focus on how the game's structure constrains and shapes outcomes rather than on actors' stated preferences. Actors can rarely change their opponents' preferences. They can often change the game's structure.

**Credibility guard rail.** Every threat and promise in the analysis must pass the credibility test: at the moment of execution, would the actor rationally carry it out? IF not, it is cheap talk and must be labeled as such regardless of how forcefully it is stated.

## TOOLS

Tier 1: OPV (identify all actors and what they think, want, and fear — feeds directly into payoff specification), FGL (Fear, Greed, Laziness analysis maps to payoff structure — what each actor is afraid of losing, trying to gain, and avoiding effort on), C&S (trace consequences of strategic choices across time horizons), Challenge (test whether the game classification is the right one).

Tier 2: Political and Social Analysis Module for geopolitical strategic interactions. Engineering and Technical Analysis Module for competitive technology or standards-setting games.

## TRANSITION SIGNALS

- IF the strategic interaction embeds distributional choices or institutional interests beyond the game structure → propose **Cui Bono** for the interest-tracing layer.
- IF the game involves deep uncertainty about future conditions rather than strategic uncertainty about opponents → propose **Scenario Planning** or **Decision Under Uncertainty**.
- IF the user wants to construct the strongest version of an opponent's strategic position → propose **Steelman Construction**.
- IF the game's feedback structure is more important than the actor-to-actor dynamics → propose **Systems Dynamics**.
- IF the user begins defining a deliverable (article, briefing, policy memo) based on the analysis → propose **Project Mode**.
- IF multiple explanations exist for an actor's observed behavior → propose **Competing Hypotheses** to determine which explanation best fits before modeling the game.
