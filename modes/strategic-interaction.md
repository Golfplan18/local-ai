---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-24
date modified: 2026-05-01
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
output_contract:
  artifact_type: synthesis
  required_sections:
    - players_and_payoffs
    - game_classification
    - equilibrium_analysis
    - credibility_assessment
    - alternative_structures
    - strategic_recommendations
  format: structured

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

## EVALUATION CRITERIA

Evaluate against CQ1–CQ5. The named failure modes are the evaluation checklist. A passing Strategic Interaction output (a) names players with payoffs in their actual value terms; (b) classifies the game on all four dimensions; (c) identifies equilibrium with method named and stability assessed; (d) audits credibility of threats/promises; (e) tests ≥ 1 alternative structure; (f) produces specific strategic recommendations grounded in game structure rather than general advice.

## REVISION GUIDANCE

Revise to name the equilibrium method where it was asserted without trace. Revise to add the missing classification dimension where one of the four was unaddressed. Revise to add credibility assessment where threats/promises lack the credibility check. Resist revising toward hyperrationality — bounded rationality and political constraints are first-class considerations. If the analysis is locked into one classification, add at least one alternative structure paragraph rather than polishing the locked analysis.

## CONSOLIDATION GUIDANCE

Consolidate as a structured analysis with the six required sections. Players and payoffs are stated in actual value terms (not claimed-to-want terms). Game classification covers all four dimensions explicitly. Equilibrium analysis names method and stability. Credibility section assesses threats/promises. Alternative structures section tests at least one alternative framing. Strategic recommendations are mechanism-grounded. Format is structured (decision-tree-friendly when sequential; matrix-friendly when simultaneous).

## VERIFICATION CRITERIA

Verified means: players named with payoffs in actual value terms; four-dimension classification complete; equilibrium method named with derivation traceable; credibility assessed for ≥ 1 threat/promise; ≥ 1 alternative structure analyzed; strategic recommendations specific. The five critical questions are addressed. A decision-node edge carrying a probability is a hard verification failure (decisions are choices, not chance outcomes).
