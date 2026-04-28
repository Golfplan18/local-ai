---
nexus: obsidian
type: mode
date created: 2026/03/24
date modified: 2026/04/18
rebuild_phase: 3
---

# MODE: Strategic Interaction

## TRIGGER CONDITIONS

Positive:
1. Game-theoretic framing: two or more actors making choices that affect each other's outcomes.
2. "What will they do if we do X"; credibility of threats or promises at issue; deterrence / compellence dynamics.
3. Negotiation or bargaining strategy; competitive or cooperative dynamics between identifiable actors.
4. Signalling and screening; auction design.
5. Request language: "game theory", "what's their best move", "payoff matrix", "Nash", "deterrence", "bargaining".

Negative:
- IF tracing whose interests a position serves without modelling interaction → **Cui Bono**.
- IF choosing between own alternatives without modelling opponent response → **Constraint Mapping** or **Decision Under Uncertainty**.
- IF understanding feedback structure rather than actor-to-actor dynamics → **Systems Dynamics**.

Tiebreakers:
- SI vs DUU: **opponent responds strategically** → SI; **uncertainty from nature** → DUU.
- SI vs Cui Bono: **interaction dynamics** → SI; **interest tracing** → CB.

## EPISTEMOLOGICAL POSTURE

Outcomes emerge from the interaction of multiple actors' strategies, not from any single actor's choice. Each actor is rational within their own value system — they pursue their goals given beliefs and constraints. Rationality is not omniscience; bounded rationality, incomplete information, and misperception are modelled explicitly. The game's structure (who moves when, who knows what, whether it repeats) determines outcomes more than intentions. Changing the game's structure changes the outcome more reliably than appealing to goodwill.

## DEFAULT GEAR

Gear 4. Independent analysis is the minimum.

## RAG PROFILE

**Retrieve (prioritise):** domain-specific strategic analyses, historical precedents of similar strategic interactions, game-theoretic case studies; IF geopolitical, deterrence theory, crisis bargaining, historical analogues; IF market competition, industrial organisation and co-opetition.

**Deprioritise:** purely normative analysis in favour of positive analysis of strategic structure.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `enables`, `requires`, `produces`, `contradicts`
**Deprioritise:** `analogous-to`, `parent`, `child`
**Rationale:** Game-theoretic analysis tracks strategic dependencies, payoff production, and conflicts between actor strategies.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The players, moves, and payoffs the user sees |
| `conversation_rag` | Prior turns' game classifications and equilibria |
| `concept_rag` | Game-theoretic mental models (Nash, subgame perfect, Schelling, mechanism design) |
| `relationship_rag` | Actors linked by `enables`/`contradicts` |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat:
1. Identify players, strategies, and payoffs in each actor's own value terms. **For sequential games, actors become decision nodes in the game tree (a `decision_tree` with nodes alternating between players).**
2. Classify the game on four dimensions: timing (sequential / simultaneous), information (complete / incomplete; perfect / imperfect), duration (one-shot / repeated), sum (zero-sum / non-zero-sum).
3. Identify the equilibrium / equilibria. Sequential → backward induction, subgame perfect. Simultaneous → Nash (pure + mixed). Repeated → cooperation sustainability conditions.

Black Hat:
1. Stress-test equilibrium robustness — stable, fragile, or knife-edge?
2. Assess credibility of threats / promises (Schelling).
3. Identify information asymmetries and their strategic implications.
4. Challenge rationality — where might bounded rationality or political constraints cause deviation?

### Cascade — what to leave for the evaluator

- Classify the game on four dimensions explicitly with literal labels `Timing:`, `Information:`, `Duration:`, `Sum:` in the Game-classification paragraph. Supports M2.
- Name the equilibrium method with one of the literal labels `Backward induction`, `Nash`, `Subgame perfect`, `Repeated cooperation`, `Perfect Bayesian`. Supports M3.
- For decision_tree as game tree, alternate decision node labels with acting-player names (e.g. "Firm A pricing move", "Firm B response"). Supports C1.
- State `utility_units` verbatim in prose before the envelope. Supports C3.
- Assess credibility with the literal phrase "credibility:" per threat/promise. Supports M4.
- **short_alt discipline — IMPORTANT (Phase 5 iteration).** Emit `spec.semantic_description.short_alt` in Cesal form: for `decision_tree` — `"Sequential game — <Player A> <move type> vs <Player B> response."`; for `influence_diagram` — `"Influence diagram of <game name>."`. TARGET ≤ 100 chars. HARD MAX 150 chars — exceeding rejects the envelope with `E_SCHEMA_INVALID`. Do NOT enumerate branches, payoffs, or arc types inside short_alt. Good: `"Sequential game — Firm A pricing vs Firm B response."` (52 chars). Bad: `"Sequential game tree where Firm A chooses price first, Firm B responds with match or undercut, terminals hold joint payoffs, backward-induction path leads to..."` (180+ chars — rejected).

### Consolidator guidance

Applies at this mode's default gear (Gear 4). Both streams independently develop equilibria and alternative structures.

- **Reference frame for the envelope:** Depth's equilibrium analysis is canonical. If streams disagree on equilibrium selection (multiple Nash equilibria exist), emit Depth's preferred equilibrium in the envelope and surface Breadth's alternative equilibrium in the "Alternative structures" prose section.
- **Payoff disagreement:** if streams assign different payoffs, emit the midpoint in `spec` and declare the range in prose — never silently pick one.
- **Credibility disagreement:** if streams disagree on threat credibility, surface both readings in prose; the envelope reflects the equilibrium under each credibility assumption with the less-credible case in "Alternative structures".

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. Map alternative game structures — one alternative move-order, information assumption, or strategy set.
2. Identify less-obvious strategies: commitment devices, game-changing moves, coalition possibilities, outside options.
3. Assess whether the game is better modelled as part of a larger repeated interaction.

Yellow Hat:
1. Identify the most favourable feasible outcome for each actor.
2. Identify mutual gains vs barriers to reaching them.
3. Assess strategic recommendations — specific options, leverage points, recognition of game type.

### Cascade — what to leave for the evaluator

- Use the literal label `Alternative structure:` when describing ≥ 1 alternative framing. Supports M5.
- Name commitment devices with the literal label `Commitment device:` when proposing them.
- State each actor's payoffs in joint format (A=X, B=Y) in prose and match the terminal labels in envelope.

## EVALUATION CRITERIA

5. **Game Classification Accuracy.** 5=classified on all four dimensions + alternative structure tested. 3=one dimension unaddressed. 1=not classified.
6. **Equilibrium Identification.** 5=equilibria identified with method, stability assessed, credibility evaluated. 3=equilibrium but stability/credibility missing. 1=asserted without method.
7. **Strategic Actionability.** 5=specific recommendations from game structure including commitment devices, game-changing moves, contingent strategies. 3=general implications without mechanisms. 1=description without recommendations.

### Focus for this mode

A strong SI evaluator prioritises:

1. **Probability-on-decision-edge trap (S8).** Decision edges must not carry probabilities; validator rejects. Mandate removal.
2. **Two-value-nodes trap (S9, for influence_diagram).** Exactly one `value` node.
3. **Four-dimension classification (M2).** All of timing/information/duration/sum present.
4. **Equilibrium method named (M3).** Backward induction / Nash / subgame perfect / etc.
5. **Players-match-envelope (C1).** Decision-node labels name the acting player.
6. **Short_alt (S11).** Name the game's players and move type.

### Suggestion templates per criterion

- **S11 (short_alt):** `suggested_change`: "Rewrite short_alt as: 'Sequential game tree — <Player A> <move type> vs <Player B> response.' (or 'Influence diagram of <game name>' for influence_diagram). Target ≤ 100 chars."
- **S7/S8 (probability on decision edges):** `suggested_change`: "Remove `probability` from decision-node children. Probabilities belong only on chance-node edges (nature's moves). If the player's choice has uncertain outcome, wrap it in a chance node."
- **S9 (two value nodes):** `suggested_change`: "Merge to exactly one `value` node representing the focal outcome. Secondary outcomes become functional children."
- **M2 (dimensions missing):** `suggested_change`: "Classify the game on all four dimensions using literal labels `Timing:`, `Information:`, `Duration:`, `Sum:` before presenting equilibrium analysis."
- **M3 (method unnamed):** `suggested_change`: "Name the solution method explicitly — `Backward induction` for sequential complete information, `Nash` for simultaneous, `Subgame perfect` for sequential with credibility screen, `Repeated cooperation` for repeated games."
- **M5 (no alternative structure):** `suggested_change`: "Add at least one `Alternative structure:` paragraph testing whether the game changes with different timing, information, or duration assumptions."

### Known failure modes to call out

- **Probability-on-Decision-Edge Trap** → open: "Decision-node edge carries `probability`. Mandate removal — decisions are choices, not chance outcomes."
- **Hyperrationality Trap** → surface as SUGGESTED: "Equilibrium assumes perfect rationality; assess deviation from real-actor behaviour."
- **Classification Lock Trap** → open: "Only one game classification tested. Mandate ≥ 1 alternative structure."
- **Static Frame Trap** → surface as SUGGESTED: "One-shot analysis of what may be a repeated game. Test repeated framing."
- **Missing Player Trap** → surface as SUGGESTED: "Only obvious actors modelled. Identify whose reaction would change the equilibrium."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-SI-1 — Probability-edge preservation.** No revised decision-node edge carries `probability`.
- **V-SI-2 — Value-node count preservation.** Revised influence_diagram has exactly one `value` node.
- **V-SI-3 — Equilibrium-method trace.** Revised prose names an equilibrium method; revised `level_2_statistical` states the arithmetic (backward-induction payoffs, Nash-profile payoffs, etc.).
- **V-SI-4 — Player-node label preservation.** Revised decision-node labels still carry acting-player names; silent label stripping during revision is a FAIL.

## CONTENT CONTRACT

In order:

1. **Players and payoffs** — all actors with their actual objectives.
2. **Game classification** — timing / information / duration / sum structure with reasoning.
3. **Equilibrium analysis** — method, identified equilibria, stability.
4. **Credibility assessment** — threats and promises; cheap talk vs commitment.
5. **Alternative structures** — ≥ 1 alternative framing and its equilibrium.
6. **Strategic recommendations** — specific options.

After your analysis, emit exactly one fenced `ora-visual` block per EMISSION CONTRACT.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S2:** `E_PROB_SUM` → probabilities on decision edges or non-summing chance nodes; apply probability templates. `E_GRAPH_CYCLE` on functional arcs → restructure; most often a functional arc runs backward.
- **S7:** apply probability-on-decision-edge template.
- **S8:** ensure chance-node probabilities sum to 1.0 (± 1e-6); decision-node edges have no `probability`.
- **S9:** apply two-value-nodes template.
- **S10 (functional-arc DAG):** if a cycle exists, reverse or retype one arc as `informational`.
- **S11:** apply short_alt template.
- **M1 (players named with payoffs):** state each player's actual value-terms and utility units in prose.
- **M2:** apply four-dimension classification template.
- **M3:** apply equilibrium-method template.
- **M4 (credibility):** assess credibility with the literal phrase "credibility:" for each threat/promise.
- **M5:** apply alternative-structure template.
- **C1-C3:** sync player names, equilibrium trace, and units between prose and envelope.

## EMISSION CONTRACT

### Envelope type selection

- **`decision_tree`** with `mode: "decision"` — for sequential games. Players take turns; decision nodes alternate between players. Terminals carry payoffs (in whatever units — `utility_units` required).
- **`influence_diagram`** — for games with information asymmetries and dependencies that don't reduce to a sequence. Decision nodes for each player, chance nodes for nature, exactly one value node (the focal outcome).

Selection rule: sequential with clear move order → `decision_tree`; dependency / information structure dominates → `influence_diagram`. Default: `decision_tree`.

### Canonical envelope (decision_tree as game tree)

```ora-visual
{
  "schema_version": "0.2",
  "id": "si-fig-1",
  "type": "decision_tree",
  "mode_context": "strategic-interaction",
  "relation_to_prose": "integrated",
  "title": "Pricing game — Firm A vs Firm B",
  "canvas_action": "replace",
  "spec": {
    "mode": "decision",
    "utility_units": "USD millions (annual profit)",
    "root": {
      "kind": "decision",
      "label": "Firm A pricing move",
      "children": [
        {
          "edge_label": "High price",
          "node": {
            "kind": "decision",
            "label": "Firm B response",
            "children": [
              { "edge_label": "Match high",  "node": { "kind": "terminal", "label": "Both soft (A=8, B=8)", "payoff": 8 } },
              { "edge_label": "Undercut",    "node": { "kind": "terminal", "label": "A loses share (A=2, B=10)", "payoff": 2 } }
            ]
          }
        },
        {
          "edge_label": "Low price",
          "node": {
            "kind": "decision",
            "label": "Firm B response",
            "children": [
              { "edge_label": "Match low",   "node": { "kind": "terminal", "label": "Price war (A=4, B=4)", "payoff": 4 } },
              { "edge_label": "Stay high",   "node": { "kind": "terminal", "label": "A gains share (A=10, B=3)", "payoff": 10 } }
            ]
          }
        }
      ]
    }
  },
  "semantic_description": {
    "level_1_elemental": "Sequential game tree where Firm A chooses price first, Firm B responds, and terminals hold joint payoffs.",
    "level_2_statistical": "Firm A's backward-induction payoff: low-price + B-stay-high dominates (A=10), but B's best response to A=low is match-low (both at 4); so subgame-perfect equilibrium has both low.",
    "level_3_perceptual": "The tree exposes the classic price-war trap: A's unilateral temptation to undercut produces mutual low pricing under rational B response.",
    "short_alt": "Sequential game tree — Firm A pricing vs Firm B response with joint payoffs."
  }
}
```

### Emission rules

1. **`type ∈ {"decision_tree", "influence_diagram"}`.**
2. **`mode_context = "strategic-interaction"`. `canvas_action = "replace"`. `relation_to_prose = "integrated"`.**
3. **For `decision_tree` as game tree:** `mode = "decision"` with `utility_units` declared. Alternating decision nodes labelled with the acting player. Terminals have `payoff`. Chance nodes used for nature's moves only.
4. **For `influence_diagram`:** exactly one `value` node (the focal outcome); `temporal_order` reflects the sequence; arcs typed as `informational` / `functional` / `relevance`.
5. **`semantic_description` required; `short_alt ≤ 150`. Level 2 should state the backward-induction / EV arithmetic so the equilibrium is traceable.**
6. **One envelope.**

### What NOT to emit

- A `decision_tree` with `probability` on decision-node edges (validator rejects with `E_PROB_SUM`).
- An `influence_diagram` with more than one value node.
- A simultaneous-move game rendered as a sequential tree without signalling the simultaneity.
- `canvas_action: "annotate"`.

## GUARD RAILS

**Solution Announcement Trigger.** WHEN recommending a strategy, verify robustness to alternative game classifications.

**Rationality check guard rail.** After every equilibrium, ask if real actors would actually play it.

**Structure-over-preferences guard rail.** Focus on game structure over actor preferences.

**Credibility guard rail.** Every threat / promise passes the credibility test.

## SUCCESS CRITERIA

Structural:
- S1-S6: standard preamble.
- S7: for `decision_tree`: `mode` ∈ {"decision", "probability"}; if `"decision"` then `utility_units` non-empty; all terminals have `payoff`.
- S8: for `decision_tree`: chance-node probabilities sum to 1.0; decision-node edges have no `probability`.
- S9: for `influence_diagram`: exactly one `value` node.
- S10: for `influence_diagram`: functional-arc subgraph is a DAG.
- S11: `semantic_description` complete; `short_alt ≤ 150`.

Semantic:
- M1: players named with their actual value-terms (not what they claim to want).
- M2: game classified on all four dimensions.
- M3: equilibrium method named (backward induction / Nash / repeated cooperation).
- M4: credibility assessment addresses at least one threat or promise.
- M5: ≥ 1 alternative structure analysed.

Composite:
- C1: players named in prose correspond to decision-node labels in the envelope.
- C2: envelope's equilibrium (backward-induction path or Nash profile) maps to prose's "Equilibrium analysis" conclusion.
- C3: units in prose match `utility_units`.

```yaml
success_criteria:
  mode: strategic-interaction
  version: 1
  structural:
    - { id: S1-S6, check: standard_preamble }
    - { id: S7,  check: decision_tree_shape, applies_to: decision_tree }
    - { id: S8,  check: probability_constraints, applies_to: decision_tree }
    - { id: S9,  check: exactly_one_value_node, applies_to: influence_diagram }
    - { id: S10, check: functional_arc_dag, applies_to: influence_diagram }
    - { id: S11, check: semantic_description_complete }
  semantic:
    - { id: M1, check: players_named_with_payoffs }
    - { id: M2, check: four_dimensions_classified }
    - { id: M3, check: equilibrium_method_named }
    - { id: M4, check: credibility_assessed }
    - { id: M5, check: alternative_structure_present }
  composite:
    - { id: C1, check: players_match_envelope }
    - { id: C2, check: equilibrium_trace }
    - { id: C3, check: units_agreement }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8, composite_min_pass: 0.75 }
```

## KNOWN FAILURE MODES

**The Hyperrationality Trap.** Assuming perfect rationality. Correction: assess deviation from game-theoretic prediction.

**The Static Frame Trap.** Analysing one shot in a repeated game. Correction: ask whether embedded in a longer relationship.

**The Classification Lock Trap.** Committing to one classification. Correction: ≥ 1 alternative.

**The Missing Player Trap.** Modelling only obvious actors. Correction: ask whose reactions would change the equilibrium.

**The Probability-on-Decision-Edge Trap (inverse of S8).** Putting probabilities on a player's move. Correction: decision edges are choices; probabilities belong only on chance/nature nodes.

## TOOLS

Tier 1: OPV, FGL, C&S, Challenge.
Tier 2: Political and Social Analysis Module; Engineering and Technical Analysis Module.

## TRANSITION SIGNALS

- IF interaction embeds distributional choices beyond game structure → propose **Cui Bono**.
- IF game involves deep uncertainty rather than strategic uncertainty → propose **Scenario Planning** or **Decision Under Uncertainty**.
- IF user wants the strongest version of an opponent's position → propose **Steelman Construction**.
- IF feedback structure dominates → propose **Systems Dynamics**.
- IF user begins a deliverable → propose **Project Mode**.
- IF multiple explanations for an actor's behaviour → propose **Competing Hypotheses**.
