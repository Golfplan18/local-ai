---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-24
date modified: 2026-05-24

---

# MODE: Strategic Interaction

```yaml
# 0. IDENTITY
mode_id: strategic-interaction
canonical_name: Strategic Interaction
suffix_rule: analysis
educational_name: strategic interaction analysis (game-theoretic, 2-to-n-player)

# 1. TERRITORY AND POSITION
territory: T18-strategic-interaction
gradation_position:
  axis: complexity
  value: 2-to-n-player
adjacent_modes_in_territory:
  - mode_id: mechanism-design
    relationship: complexity-heavier sibling (mechanism design, deferred per CR-6)
  - mode_id: signaling
    relationship: specificity variant (signaling games, deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "what will they do if we do X"
    - "credibility of threats or promises is at issue"
    - "deterrence or compellence dynamics in play"
    - "two-or-more actors making choices that affect each other's outcomes"
    - "negotiation or bargaining strategy"
  prompt_shape_signals:
    - "game theory"
    - "what's their best move"
    - "payoff matrix"
    - "Nash"
    - "deterrence"
    - "bargaining"
    - "signaling"
disambiguation_routing:
  routes_to_this_mode_when:
    - "opponent responds strategically — outcome depends on interaction not single choice"
    - "wants equilibrium analysis with credibility assessment"
  routes_away_when:
    - "tracing whose interests a position serves without modeling interaction" → cui-bono (T2)
    - "choosing between own alternatives without modeling opponent response" → constraint-mapping or decision-under-uncertainty (T3)
    - "feedback structure rather than actor-to-actor dynamics" → systems-dynamics-causal (T4)
    - "parties' conflict needs to be resolved (not analyzed strategically)" → principled-negotiation (T13)
when_not_to_invoke:
  - "Uncertainty is from nature rather than from strategic opponent" → decision-under-uncertainty (T3)
  - "User wants distributive interest tracing rather than equilibrium analysis" → cui-bono (T2)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [players_inventoried, payoff_structure_or_value_terms, move_order_or_information_structure]
    optional: [historical_precedents, prior_equilibrium_analyses, repeated_interaction_history]
    notes: "Applies when user supplies game classification information explicitly (timing, information, duration, sum)."
  accessible_mode:
    required: [actors_described, interaction_situation_described]
    optional: [stakes, prior_history_between_parties]
    notes: "Default. Mode infers payoff structure and game type from user description."
  detection:
    expert_signals: ["payoff matrix", "Nash equilibrium", "subgame perfect", "backward induction"]
    accessible_signals: ["if we do X they'll", "what's their best response", "two parties trying to"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Who are the actors involved, and what is each one trying to achieve in their own terms?'"
    on_underspecified: "Ask: 'Is this primarily an interaction where the other party responds to our moves (Strategic Interaction), or is it about choosing under uncertainty from nature (Decision Under Uncertainty)?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the game been classified on all four dimensions (timing, information, duration, sum)?"
    failure_mode_if_unmet: classification-incomplete
  - cq_id: CQ2
    question: "Has the equilibrium method been named (backward induction / Nash / subgame perfect / repeated cooperation / Perfect Bayesian)?"
    failure_mode_if_unmet: method-unnamed
  - cq_id: CQ3
    question: "Have threats and promises passed the credibility test, or are some cheap talk?"
    failure_mode_if_unmet: cheap-talk-treated-as-credible
  - cq_id: CQ4
    question: "Has at least one alternative game structure been tested, or is the analysis classification-locked?"
    failure_mode_if_unmet: classification-lock
  - cq_id: CQ5
    question: "Have payoffs been stated in each player's actual value terms, not what they claim to want?"
    failure_mode_if_unmet: stated-vs-actual-payoffs

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: hyperrationality-trap
    detection_signal: "Equilibrium assumes perfect rationality without bounded-rationality assessment."
    correction_protocol: flag (assess deviation from real-actor behavior)
  - name: static-frame-trap
    detection_signal: "One-shot analysis applied to what is actually a repeated game."
    correction_protocol: re-dispatch (test repeated framing)
  - name: classification-lock
    detection_signal: "Only one game classification tested; no alternative structure considered."
    correction_protocol: re-dispatch (test ≥ 1 alternative timing/information/duration framing)
  - name: missing-player-trap
    detection_signal: "Only obvious actors modeled; reactive third parties absent."
    correction_protocol: flag (identify whose reaction would change the equilibrium)
  - name: probability-on-decision-trap
    detection_signal: "Decision-node edges carry probabilities (decisions are choices, not chance outcomes)."
    correction_protocol: re-dispatch (probabilities belong only on chance/nature nodes)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - game-theory-equilibrium-concepts (Nash, subgame perfect, Perfect Bayesian)
    - schelling-strategy-of-conflict (commitment, credibility, focal points)
  optional:
    - axelrod-evolution-of-cooperation (when game is repeated)
    - mechanism-design-foundations (when designing rather than playing the game)
  foundational:
    - kahneman-tversky-bias-catalog
    - bounded-rationality-simon

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: mechanism-design
    when: "User is designing the game's structure rather than playing within it (deferred sibling)."
  sideways:
    target_mode_id: signaling
    when: "Information asymmetry and signaling dominate the analysis (deferred sibling)."
  downward:
    target_mode_id: null
    when: "Strategic Interaction is T18's founder mode."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Strategic Interaction is the explicitness of the equilibrium derivation and the credibility audit on threats/promises. A thin pass asserts equilibria; a substantive pass names the method (backward induction / Nash / subgame perfect / repeated cooperation / Perfect Bayesian) and traces the derivation. Test depth by asking: could a reader reproduce the equilibrium from the players, payoffs, and method? Credibility depth means assessing each threat/promise with the literal phrase "credibility:" — cheap talk vs commitment device, sunk costs vs future-shadow.

## BREADTH ANALYSIS GUIDANCE

Breadth in Strategic Interaction is the catalog of alternative game structures considered before locking the canonical one. Widen the lens to scan: alternative move-order assumptions; alternative information structures (complete vs incomplete; perfect vs imperfect); alternative duration framings (one-shot vs repeated); alternative sum (zero-sum vs positive-sum). Breadth markers: at least one alternative structure is tested with its own equilibrium derivation; commitment devices, game-changing moves, coalition possibilities, and outside options are surveyed.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Strategic Interaction is a 2-to-n-player game-theoretic analysis of situations where outcomes depend on actors' choices affecting one another. It is read in Schelling's strategy-of-conflict vocabulary (commitment, credibility, focal points, deterrence vs compellence) combined with equilibrium concepts (Nash, subgame-perfect, Perfect Bayesian, backward induction, repeated cooperation), Axelrod when the game is repeated, and Simon bounded-rationality against hyperrationality. It is distinct from decision-under-uncertainty (uncertainty from nature, not from a strategic opponent), cui-bono (interest tracing without modeling interaction), systems-dynamics-causal (feedback structure rather than actor-to-actor), and principled-negotiation (conflict resolution rather than strategic modeling).

**Procedure.**

1. Inventory players and infer payoffs in each player's *actual* value terms — revealed-by-behaviour rather than stated-and-claimed. Name where actual diverges from claimed.
2. Classify the game on all four dimensions — timing (simultaneous / sequential / extensive-form) × information (complete / incomplete; perfect / imperfect) × duration (one-shot / repeated / infinite-horizon) × sum (zero-sum / positive-sum / mixed) — with reasoning per classification.
3. Derive the equilibrium by an explicitly-named method (Nash / subgame-perfect / backward induction / repeated cooperation / Perfect Bayesian) with a trace a reader could reproduce from players + payoffs + method.
4. Audit credibility for each threat and promise — apply the literal `credibility:` label with grounding: `credible` (commitment device, sunk cost, or future-shadow named) vs `cheap talk` (none of these). Announcements without commitment are not threats.
5. Test at least one alternative game classification — alternative move-order, alternative information structure, alternative duration (especially one-shot vs repeated), or alternative sum — with its own equilibrium derivation.
6. Surface missing reactive players whose response would shift the equilibrium; flag the analysis as bounded if any are inferred but unincludable.
7. Pair the rational equilibrium with a bounded-rationality reading where real-actor deviation (cognitive bias, political constraint, incomplete preference orderings) is plausible.
8. Test static-vs-repeated framing where the parties plausibly interact again — one-shot equilibrium is often unstable under repetition (Axelrod).
9. Enforce probability discipline — decision-node edges carry no probabilities (decisions are choices); only chance/nature nodes do.
10. Ground each strategic recommendation in the specific game-structure lever (commitment device, credibility shift, classification-dimension alteration, coalition formation, outside option) — not generic strategic advice.

**Goal.** Produce a structured equilibrium derivation with explicit four-dimensional classification, credibility audit on threats/promises, alternative-structure stress-test, and mechanism-grounded recommendations — reproducible from the components stated.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — classification completeness.** Has the game been classified on all four dimensions (timing, information, duration, sum)? Failure mode if unmet: `classification-incomplete`.
- **CQ2 — method named with derivation.** Has the equilibrium method been named (Nash / subgame-perfect / backward induction / repeated cooperation / Perfect Bayesian) with a traceable derivation? Failure mode if unmet: `method-unnamed`.
- **CQ3 — credibility honesty (load-bearing, Schelling's distinctive move).** Have threats and promises passed the credibility test, or are some cheap talk? Failure mode if unmet: `cheap-talk-treated-as-credible`.
- **CQ4 — alternative-structure breadth.** Has at least one alternative game structure been tested, or is the analysis classification-locked? Failure mode if unmet: `classification-lock`.
- **CQ5 — payoff realism.** Have payoffs been stated in each player's actual value terms, not what they claim to want? Failure mode if unmet: `stated-vs-actual-payoffs`.

A passing output names players with payoffs in actual value terms, completes the four-dimension classification with reasoning, names the equilibrium method with reproducible derivation, applies the `credibility:` label to each threat/promise with commitment-device grounding, tests at least one alternative structure, grounds recommendations in specific mechanisms, and emits no decision-node probabilities (hard verification failure).

**Named failure modes.**

- *hyperrationality-trap* — equilibrium assumes perfect rationality without bounded-rationality assessment.
- *static-frame-trap* — one-shot analysis applied to what is actually a repeated game.
- *classification-lock* — only one game classification tested; no alternative structure considered.
- *missing-player-trap* — only obvious actors modeled; reactive third parties absent.
- *probability-on-decision-trap* — decision-node edges carry probabilities (decisions are choices, not chance outcomes). Hard verification failure.

## REVISION GUIDANCE

Revise to name the equilibrium method where it was asserted without trace. Revise to add the missing classification dimension where one of the four was unaddressed. Revise to add credibility assessment where threats/promises lack the credibility check. Resist revising toward hyperrationality — bounded rationality and political constraints are first-class considerations. If the analysis is locked into one classification, add at least one alternative structure paragraph rather than polishing the locked analysis.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a game-theoretic interaction atom set: player-and-payoff atoms in actual value terms, four-dimensional game-classification atoms (timing × information × duration × sum), equilibrium-derivation atoms with method named, credibility-audit atoms per threat/promise, alternative-structure atoms testing ≥1 alternative classification, and mechanism-grounded strategic-recommendation atoms**. The atoms are:

1. **Player-and-payoff atoms.** Each atom names: one player, payoffs in their *actual* value terms (not what they claim to want). Stated-vs-actual-payoffs is the named failure mode the consolidator watches for; payoffs stated as professed preferences without the value-revealed-by-behaviour check get reshaped.

2. **Game-classification atoms — four dimensions.** Each atom carries a per-dimension classification: `timing` (simultaneous / sequential / extensive-form) × `information` (complete-information / incomplete-information; perfect / imperfect) × `duration` (one-shot / repeated / infinite-horizon) × `sum` (zero-sum / positive-sum / mixed). Classification-incomplete is the named failure mode; missing dimensions get reshaped to fill the four-dimensional grid.

3. **Equilibrium-derivation atoms.** Each atom names: the equilibrium method (`Nash equilibrium` / `subgame-perfect equilibrium` / `backward induction` / `repeated cooperation` / `Perfect Bayesian equilibrium`), the derivation (traceable from players + payoffs + method), and stability (which deviations are profitable, which are not). Method-unnamed is the named failure mode; asserted equilibria without method-name get reshaped.

4. **Credibility-audit atoms — per threat/promise.** Each atom carries the literal prefix `credibility:` and audits one threat or promise: `cheap talk` (no commitment device, no sunk cost, no future-shadow) versus `credible` (commitment device named, sunk cost identified, or repeated-game future-shadow operative). Cheap-talk-treated-as-credible is the named failure mode.

5. **Alternative-structure atoms.** Each atom tests an alternative game classification — alternative move-order, alternative information structure, alternative duration, alternative sum — with its own equilibrium derivation. Classification-lock is the named failure mode; analyses with only one classification tested get reshaped.

6. **Missing-player atoms — when applicable.** Where reactive third parties whose response would change the equilibrium are absent from the player inventory, the missing player surfaces explicitly. Missing-player-trap is the named failure mode.

7. **Hyperrationality-vs-bounded-rationality atoms.** Where the equilibrium assumes perfect rationality without bounded-rationality assessment (Simon, behavioural economics), the deviation from real-actor behaviour is named. Hyperrationality-trap is the named failure mode.

8. **Static-vs-repeated framing atoms.** Where one-shot analysis was applied to what is actually a repeated game, the framing gets reshaped to test the repeated framing. Static-frame-trap is the named failure mode.

9. **Probability-discipline atom.** A standing atom: decision-node edges do *not* carry probabilities (decisions are choices, not chance outcomes); only chance/nature nodes carry probabilities. Probability-on-decision-trap is the named failure mode and a *hard* verification failure if it survives.

10. **Mechanism-grounded recommendation atoms.** Each strategic recommendation references the equilibrium structure that justifies it (which commitment device, which credibility shift, which classification dimension to alter), rather than general strategic advice.

11. **Confidence per finding.** Confidence per equilibrium, per credibility assessment, per alternative-structure result.

**Mode-specific bloat patterns to cut:**

- **Classification incomplete** — fewer than four dimensions populated.
- **Method unnamed** — equilibrium asserted without naming the derivation method.
- **Cheap talk treated as credible** — threats/promises without commitment-device or future-shadow grounding.
- **Classification lock** — only one game structure tested.
- **Missing reactive players** — third parties whose response would change the equilibrium left out.
- **Hyperrationality** — equilibrium derived without bounded-rationality assessment.
- **Static frame on repeated game** — one-shot analysis where repetition is operative.
- **Probability on decision node** — *hard* failure; decisions are choices, not chance outcomes.
- **Stated-payoff naivety** — claimed-to-want preferences without revealed-by-behaviour check.
- **Generic strategic advice** — recommendations not grounded in the game's mechanism.

**What NOT to collapse:**

- **Equilibria across alternative classifications** — when one game classification yields equilibrium A and another classification yields equilibrium B, both survive; the alternative-structure atom is the load-bearing breadth signal.
- **Cheap-talk vs credible labels** — these don't blur; some threats are commitments and some are not.
- **Bounded-rationality deviations** — preserved alongside the rational equilibrium; both readings of player behaviour survive.
- **Stream disagreement about payoffs** — when streams inferred different value terms for the same player, the disagreement surfaces (the player's actual values are themselves uncertain).

## VERIFICATION CRITERIA

Verified means: players named with payoffs in actual value terms; four-dimension classification complete; equilibrium method named with derivation traceable; credibility assessed for ≥ 1 threat/promise; ≥ 1 alternative structure analyzed; strategic recommendations specific. The five critical questions are addressed. A decision-node edge carrying a probability is a hard verification failure (decisions are choices, not chance outcomes).

## OUTPUT FORMAT GUIDANCE

The deliverable is a **game-theoretic strategic-interaction analysis** — a structured equilibrium derivation with explicit four-dimensional classification, credibility audit on threats/promises, alternative-structure stress-test, and mechanism-grounded recommendations. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Players and payoffs.** A table. Each row: `**[Player]** — Actual value terms (not claimed-to-want): [...]. How these were inferred: [revealed-by-behaviour / stated-and-confirmed / structural-position]. Note where actual diverges from claimed: [...].`

2. **Game classification.** A labelled block with all four dimensions. `**Timing:** [simultaneous / sequential / extensive-form]. **Information:** [complete / incomplete; perfect / imperfect]. **Duration:** [one-shot / repeated / infinite-horizon]. **Sum:** [zero-sum / positive-sum / mixed]. **Reasoning per classification:** [...].`

3. **Equilibrium analysis.** One labelled block. `**Equilibrium method:** [Nash / subgame-perfect / backward induction / repeated cooperation / Perfect Bayesian]. **Derivation:** [step-by-step trace from players + payoffs + method]. **Stability:** [which deviations are profitable, which are not]. **Reader-reproducibility check:** [a reader can reconstruct this equilibrium from the components above].`

4. **Credibility assessment.** Bulleted list. Each threat or promise: `**credibility:** [threat or promise] — [cheap talk / credible]. **Commitment device or future-shadow if credible:** [...]. **Why dismissible if cheap talk:** [...].` The literal prefix `credibility:` appears verbatim per item.

5. **Alternative structures.** Bulleted list. Each: `**Alternative classification:** [the alternative on which dimension]. **What changes:** [equilibrium under the alternative]. **Implication for the dominant analysis:** [whether the dominant equilibrium is robust to this re-classification or contingent].` At least one alternative is tested.

6. **Strategic recommendations.** Numbered list. Each: `[N]. **[Recommendation]** — mechanism it leverages: [commitment / credibility shift / classification-dimension alteration / coalition formation / outside option]. Expected equilibrium shift: [...].` Generic advice without mechanism grounding is reshaped at this layer.

**Per-section conventions:**

- Use H2 headings for sections 1 through 6.
- Game-theory vocabulary stays operative: `Nash`, `subgame-perfect`, `backward induction`, `Perfect Bayesian`, `cheap talk`, `commitment device`, `future-shadow`. The vocabulary appears verbatim with operative meanings.
- The four-dimensional classification (timing × information × duration × sum) is *complete*. Missing dimensions are reshaped to filled-and-reasoned.
- The credibility audit (section 4) uses the literal `credibility:` prefix per item.
- Probability-discipline is enforced: decision-node edges do not carry probabilities. Any envelope rendering must satisfy this — decision-node children carry no probability, chance-node children sum to 1.0.
- When the missing-player flag survived consolidation, section 1 closes with: `**Missing-player flag:** [party] is a reactive third party whose response would shift the equilibrium. Their inclusion is recommended if their behaviour is observable; their absence is named here so the equilibrium below is read as bounded-to-the-current-inventory.`
- When the hyperrationality flag survived consolidation, section 3 closes with: `**Bounded-rationality note:** the equilibrium above assumes perfect rationality. Real-actor deviations (cognitive bias, political constraint, incomplete preference orderings) shift expected play [direction]; the recommendation in section 6 accounts for this.`
- Strategic recommendations (section 6) are mechanism-grounded — they reference the specific game-structure lever that produces the recommendation. Generic strategic advice is reshaped.


---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~10min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `requires`, `enables`, `contradicts`, `supports`, `qualifies`
**Deprioritize:** `parent`, `analogous-to`

*Family: stakeholder-strategy. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
