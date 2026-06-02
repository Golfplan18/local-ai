---
nexus:
  - ora
type: mode
tags:
  - framework/instruction
  - architecture
date created: 2026-06-01
date modified: 2026-06-01

---

# MODE: Mechanism and Incentive Analysis

```yaml
# 0. IDENTITY
mode_id: mechanism-design
canonical_name: Mechanism and Incentive Analysis
suffix_rule: analysis
educational_name: mechanism design and information-economics analysis (adverse-selection / moral-hazard / auction lineage)

# 1. TERRITORY AND POSITION
territory: T18-strategic-interaction
gradation_position:
  axis: complexity
  value: mechanism-design
adjacent_modes_in_territory:
  - mode_id: strategic-interaction
    relationship: complexity sibling (analyze the game as given vs. analyze/design the information-and-incentive structure that shapes the game)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "why is this market full of lemons / low-quality options"
    - "will this scheme collapse because only the high-risk people opt in"
    - "people take more risk when shielded from the consequences"
    - "why does the auction winner systematically overpay"
    - "design the contract / auction / incentive scheme so people behave honestly"
  prompt_shape_signals:
    - "adverse selection"
    - "moral hazard"
    - "winner's curse"
    - "mechanism design / incentive-compatible / screening / signaling"
    - "principal-agent / hidden information / hidden action"
disambiguation_routing:
  routes_to_this_mode_when:
    - "the outcome is driven by hidden information (who knows what) or hidden action (who does what unseen) and the incentive structure"
    - "the task is to analyze an information-asymmetry market failure (adverse selection, moral hazard) or to design a mechanism/contract/auction that aligns incentives"
    - "signaling, screening, or incentive-compatibility is the operative structure"
  routes_away_when:
    - "the situation is a game with observable moves and no information asymmetry (equilibrium analysis)" → strategic-interaction (T18 sibling)
    - "the question is how a market's prices/quantities behave, not its information structure" → market-dynamics (T17)
    - "the question is who benefits and who holds power" → cui-bono (T2)
    - "the task is to negotiate the deal rather than design the mechanism" → principled-negotiation (T13)
when_not_to_invoke:
  - "User wants the observable-move game analyzed without information asymmetry" → strategic-interaction (T18)
  - "User wants market price/quantity behavior, not the incentive/information structure" → market-dynamics (T17)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: analytical-and-design

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [interaction_or_market, information_structure, parties_and_their_private_info_or_action]
    optional: [existing_contract_or_rules, desired_outcome, payoff_or_value_terms]
    notes: "Applies when the user names the parties, what each privately knows or does, and (for design) the outcome the mechanism should produce."
  accessible_mode:
    required: [situation_description]
    optional: [desired_outcome, related_context]
    notes: "Default. Mode elicits who-knows-what and whether the goal is to analyze or to design during execution."
  detection:
    expert_signals: ["incentive-compatibility constraint", "individual-rationality constraint", "revelation principle", "optimal auction", "Bayesian Nash", "incentive compatible mechanism"]
    accessible_signals: ["adverse selection", "moral hazard", "winner's curse", "why is this market full of lemons", "only the risky people sign up", "they overpaid at auction", "screening", "principal-agent", "hidden information", "design a contract so people behave"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Who are the parties, and what does each one privately know or privately do that the others can't see? That hidden information or hidden action is what this analysis turns on.'"
    on_underspecified: "Ask: 'Are you trying to ANALYZE why an existing arrangement misfires (adverse selection, moral hazard), or to DESIGN a mechanism/contract/auction that fixes it? Either is in scope — I just need to know which.'"

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Is the information asymmetry named explicitly — who holds private information or takes hidden action, and who cannot observe it?"
    failure_mode_if_unmet: asymmetry-unnamed
  - cq_id: CQ2
    question: "Is hidden information (adverse selection — type is private before contracting) distinguished from hidden action (moral hazard — effort is private after contracting)?"
    failure_mode_if_unmet: selection-hazard-conflation
  - cq_id: CQ3
    question: "For a designed mechanism, are participation (individual-rationality) and incentive-compatibility constraints both addressed — will the parties join, and will they behave as intended once in?"
    failure_mode_if_unmet: constraint-omission
  - cq_id: CQ4
    question: "When a named mechanism concept is invoked (winner's curse, screening, signaling), is its actual mechanism shown to operate here, or is it a name-drop?"
    failure_mode_if_unmet: mechanism-name-drop
  - cq_id: CQ5
    question: "Is the analytical-vs-design posture explicit — is the output explaining why an arrangement misfires, or proposing a mechanism, rather than silently sliding between the two?"
    failure_mode_if_unmet: posture-drift

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: asymmetry-unnamed
    detection_signal: "Analysis proceeds without naming who holds private information or takes unobserved action."
    correction_protocol: re-dispatch (name the asymmetry first)
  - name: selection-hazard-conflation
    detection_signal: "Adverse selection and moral hazard used interchangeably; pre-contract type and post-contract effort conflated."
    correction_protocol: flag (mandatory)
  - name: constraint-omission
    detection_signal: "A proposed mechanism addresses incentive-compatibility but not participation (or vice versa) — parties either won't join or will game it."
    correction_protocol: re-dispatch
  - name: mechanism-name-drop
    detection_signal: "A mechanism concept invoked in prose without its mechanism shown operating on the specific situation."
    correction_protocol: re-dispatch
  - name: posture-drift
    detection_signal: "Output slides between explaining a failure and proposing a fix without marking which it is doing."
    correction_protocol: flag
  - name: assume-away-asymmetry
    detection_signal: "Analysis quietly assumes full information, dissolving the very problem the mode exists to handle."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - adverse-selection
    - moral-hazard
  optional:
    - winners-curse
    - signaling
    - principal-agent-problem
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~10min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Mechanism and Incentive Analysis is the information-and-incentive-structure mode of T18."
  sideways:
    target_mode_id: strategic-interaction
    when: "The situation is actually a full-information game of observable moves — switch to equilibrium analysis."
  downward:
    target_mode_id: null
    when: "n/a"
```

## DEPTH ANALYSIS GUIDANCE

Depth in Mechanism and Incentive Analysis is the rigor of the information-structure account: exactly who holds what private information or takes what unobserved action, when (before or after contracting), and how that asymmetry distorts the outcome. A thin pass says "there's an incentive problem"; a substantive pass names the asymmetry precisely, classifies it as adverse selection (hidden type, pre-contract) or moral hazard (hidden action, post-contract), traces the distortion (which good actors exit, which risks get taken), and — when designing — states both the participation constraint (will the party join?) and the incentive-compatibility constraint (will truth-telling or effort be the party's best response?). Test depth by asking: could another analyst predict who gets selected in or out, and what behavior the incentives actually produce, rather than the behavior the designer hoped for?

## BREADTH ANALYSIS GUIDANCE

Breadth in Mechanism and Incentive Analysis is the catalog of information-and-incentive failure modes scanned before the read is committed. Widen the lens across: adverse selection (the informed side self-selects, good types exit — the lemons dynamic), moral hazard (the insured/agent takes hidden risk), the winner's curse (the winner overpays because winning is itself bad news about value), signaling (the informed side spends to credibly reveal type), screening (the uninformed side designs choices that separate types), and the principal-agent split (the agent's interests diverge from the principal's). Breadth markers: at least one alternative asymmetry is named and ruled in or out, and for a design, at least one way the mechanism could be gamed is surfaced.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Mechanism and Incentive Analysis examines situations where hidden information, hidden action, and incentive structure determine the outcome — and, when asked, designs the rules, contract, or auction that aligns incentives. It is the information-and-incentive-structure mode of T18 (Strategic Interaction), the complexity-axis sibling of `strategic-interaction`: where strategic-interaction analyzes a game of observable moves, this mode handles the case where what the parties privately know or privately do is the crux. It is distinct from `market-dynamics` (T17), which describes market price/quantity behavior rather than its information structure, and from `cui-bono` (T2), which asks who benefits and who holds power rather than how incentives are structured.

**Procedure.**

1. Name the parties and the asymmetry — who holds private information, who takes unobserved action, and who cannot see it.
2. Classify it — adverse selection (hidden *type*, known before contracting) vs. moral hazard (hidden *action/effort*, exercised after contracting); name both if both are present.
3. Trace the distortion — which good actors exit, which hidden risks get taken, who overpays, what the pooling/separating outcome is.
4. Scan named mechanisms — winner's curse, signaling, screening, principal-agent — and rule each in or out with a mechanism, not a name-drop.
5. For an analysis, state why the arrangement misfires; for a design, propose the mechanism and check BOTH constraints — participation (will they join?) and incentive-compatibility (is honesty/effort their best response?).
6. Surface how the mechanism could be gamed — the cleverest defection the incentives still permit.
7. Mark the posture explicitly — explaining a failure vs. proposing a fix — and don't slide between them silently.
8. State confidence with the load-bearing assumptions about what each party knows.

**Goal.** Produce an information-and-incentive read: the asymmetry named and classified, the distortion traced, named mechanisms grounded, and — for a design — a mechanism that satisfies both participation and incentive-compatibility, with its remaining gaming surface surfaced.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — asymmetry named.** Is it explicit who holds private information / takes hidden action, and who can't observe it? Failure mode if unmet: `asymmetry-unnamed`.
- **CQ2 — selection vs hazard.** Is adverse selection (hidden type, pre-contract) distinguished from moral hazard (hidden action, post-contract)? Failure mode if unmet: `selection-hazard-conflation`.
- **CQ3 — both constraints.** For a design, are participation AND incentive-compatibility both addressed? Failure mode if unmet: `constraint-omission`.
- **CQ4 — mechanisms grounded.** Is each invoked mechanism shown operating here, not name-dropped? Failure mode if unmet: `mechanism-name-drop`.
- **CQ5 — posture explicit.** Is analysis-vs-design marked rather than blurred? Failure mode if unmet: `posture-drift`.

A passing output names the asymmetry, classifies selection vs. hazard, traces the distortion, grounds any named mechanism, and — for a design — satisfies both participation and incentive-compatibility while surfacing the residual gaming surface.

**Named failure modes.**

- *asymmetry-unnamed* — analysis without naming who knows/does what unseen.
- *selection-hazard-conflation* — pre-contract type and post-contract effort conflated.
- *constraint-omission* — a mechanism missing the participation or the incentive-compatibility constraint.
- *mechanism-name-drop* — a concept invoked without its mechanism shown operating here.
- *posture-drift* — sliding between explaining a failure and proposing a fix unmarked.
- *assume-away-asymmetry* — quietly assuming full information, dissolving the problem.

## REVISION GUIDANCE

Revise to name the asymmetry first for any analysis that proceeded without it. Revise to separate adverse selection from moral hazard wherever they were conflated — the pre-contract/post-contract distinction is the parse-preserving core. For any proposed mechanism, revise to add the missing constraint: a mechanism that is incentive-compatible but that no one will join (participation fails), or that people join but then game (incentive-compatibility fails), is not yet a mechanism. Ground every named concept (winner's curse, screening, signaling) in its operation here or cut the name. Mark analysis vs. design explicitly.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **an information-and-incentive atom set: party-and-asymmetry lock, selection-vs-hazard classification atoms, distortion-trace atoms, named-mechanism atoms grounded in operation, design-constraint atoms (participation + incentive-compatibility), gaming-surface atoms, and confidence with information-assumption caveats**. The atoms are:

1. **Party-and-asymmetry atom.** Who holds private information or takes hidden action, and who cannot observe it; asymmetry-unnamed and assume-away-asymmetry are the named failure modes.
2. **Selection-vs-hazard atoms.** Each asymmetry classified as adverse selection (hidden type, pre-contract) or moral hazard (hidden action, post-contract); selection-hazard-conflation is the named failure mode.
3. **Distortion-trace atoms.** Which good actors exit, which hidden risks are taken, who overpays, what pooling/separating outcome results.
4. **Named-mechanism atoms — when applicable.** Each names a concept (winner's curse, signaling, screening, principal-agent) and how it operates here; mechanism-name-drop is the named failure mode.
5. **Design-constraint atoms — for a design.** Participation (will they join?) and incentive-compatibility (is honest/effortful behavior their best response?), both present; constraint-omission is the named failure mode.
6. **Gaming-surface atoms.** The cleverest defection the proposed incentives still permit.
7. **Confidence and information-assumption atoms.** Confidence per claim plus what each party is assumed to know; posture-drift (analysis vs. design) is reshaped to an explicit marker.

**Mode-specific bloat patterns to cut:** unnamed asymmetries, selection/hazard conflation, single-constraint mechanisms, mechanism name-drops, posture blur, and full-information assumptions that dissolve the problem.

**What NOT to collapse:** the selection-vs-hazard distinction, the participation-and-incentive-compatibility pair (both constraints), and the analysis-vs-design posture marker.

## VERIFICATION CRITERIA

Verified means: the information asymmetry is named (who knows/does what unseen); adverse selection is distinguished from moral hazard; for a design, both participation and incentive-compatibility constraints are addressed; any named mechanism corresponds to an operation shown on this situation; the analysis-vs-design posture is explicit; and confidence is stated with the information-assumptions named. Confidence is high only when depth and breadth converged on the classification of the asymmetry.

## OUTPUT FORMAT GUIDANCE

The deliverable is an **information-and-incentive read** (and, when asked, a mechanism). Place the consolidated atoms into these sections, in order:

1. **Parties and the asymmetry.** `**Parties:** [...]. **Private information / hidden action:** [who knows or does what, unobserved by whom]. **When:** [before contracting → type; after → action].`
2. **Selection vs. hazard.** `**Adverse selection (hidden type):** [...]` and/or `**Moral hazard (hidden action):** [...]` — name both if both operate.
3. **The distortion.** Bulleted: which good actors exit, which risks are taken, who overpays, pooling vs. separating outcome.
4. **Named mechanisms in play.** Per concept: `**[winner's curse / signaling / screening / principal-agent]:** operation here [...]. Ruled in/out because [...].`
5. **Mechanism (for a design).** `**Proposal:** [...]. **Participation constraint:** [why parties join]. **Incentive-compatibility:** [why honest/effortful behavior is their best response]. **Residual gaming surface:** [...].` Omit this section for a pure analysis and say so.
6. **Read.** Bulleted: the conclusion (why it misfires / what the mechanism achieves), with the posture (analysis vs. design) marked.
7. **Confidence and assumptions.** Per-claim confidence plus the information-assumptions each party's behavior rests on.

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- Section 2 keeps adverse selection and moral hazard distinct; conflation is reshaped.
- Section 5 appears only for a design and must carry BOTH constraints; a single-constraint mechanism is reshaped.
- The analysis-vs-design posture (section 6) is marked explicitly; silent sliding is reshaped.
- A game tree, signaling diagram, or screening menu is diagram-friendly and welcome when it carries the argument.

## CAVEATS AND OPEN DEBATES

Mechanism and Incentive Analysis is a new T18 resident (2026-06-01), un-deferring the `mechanism-design` expansion candidate the territory had flagged (CR-6). It is the complexity-axis sibling of `strategic-interaction`: that mode analyzes games of observable moves; this one handles the case where hidden information (adverse selection), hidden action (moral hazard), and incentive structure are the crux, and extends to designing mechanisms that align incentives. The parse-preserving boundary against `market-dynamics` (T17) is information vs. price: this mode is about who-knows-what and how incentives are structured; market-dynamics is about how prices and quantities behave. The standing debate is how far the design end should go before it becomes a full formal mechanism-design exercise (revelation principle, optimal-auction derivation); v1 keeps designs at the structural level — constraints named and satisfied qualitatively — and flags when a problem genuinely needs formal optimization.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~10min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- CAF
- C&S
- APC
- Challenge
- OPV

Mental models (always loaded):
- adverse-selection
- moral-hazard
- winners-curse
- signaling
- principal-agent-problem

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `produces`, `enables`, `requires`
**Deprioritize:** `precedes`, `parent`

*Family: strategic-analysis. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
