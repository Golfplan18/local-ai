
# Decision Architecture Analysis Framework

*A Framework for Producing a Decision Architecture Document for a High-Stakes Decision Where the Decision-Maker Is the User and Wants Constraints, Probability-Weighted Outcomes, Stakeholder Impacts, and Failure Pathways Integrated into a Single Architecture Rather Than a Bare Recommendation.*

*Version 1.0*

*Bridge Strip: `[DAA — Decision Architecture Analysis]`*

---

## Architectural Note

This framework supports the `decision-architecture` mode, the depth-molecular operation in T3 (decision-making under uncertainty). The mode file at `Modes/decision-architecture.md` carries the locked spec — molecular_spec.components, critical_questions, output_contract.required_sections — sufficient for the orchestrator to dispatch the four component modes (`decision-under-uncertainty`, `constraint-mapping`, `stakeholder-mapping`, `pre-mortem-action`) and the four synthesis stages. This framework adds the procedural detail the spec does not carry: the elicitation prompts the orchestrator uses to invoke each component at this molecular stage, the intermediate output formats the synthesis stages consume, the per-stage quality gates, and the worked example showing the framework operating end-to-end.

The framework sits in T3's depth ladder above `constraint-mapping` (T3-light, atomic, deterministic-tradeoffs) and `decision-under-uncertainty` (T3-thorough, atomic, probability-weighted), and beside `multi-criteria-decision` (T3 complexity sibling). It composes those siblings with `stakeholder-mapping` (T8) and `pre-mortem-action` (T6) into a single integrated decision architecture. The territory framework is `Framework — Decision-Making Under Uncertainty.md`. Decision Architecture is the heaviest analytical mode in T3; it does NOT recommend a bare "do X" answer — it produces an architecture in which a recommendation, residual risks, and decision-conditions-to-monitor are presented together so the decision-maker can act with eyes open.

---

## How to Use This File

This framework runs when the user has a high-stakes decision to make, holds decision authority themselves, and wants the integrated architecture rather than a single dimension's analysis (constraints alone, probabilities alone, stakeholders alone, or failure pathways alone). The framework's value is in the synthesis stages: tensions surfaced where probability-weighted outcomes clash with binding constraints, where stakeholder impacts contradict the leading alternative, where pre-mortem failure modes invalidate the top-ranked option. A passing Decision Architecture output contains a recommendation that no single component could have produced.

DAA differs from the Decision Clarity Framework (which produces a Decision Clarity Document for a third-party decision-maker, refusing to recommend) and from constraint-mapping or decision-under-uncertainty (which produce single-dimension reads). Use DAA when the decision is yours, the stakes warrant 10+ minutes of analysis, and you want one document that integrates four analytical lenses rather than four separate reads to mentally combine.

Three invocation paths supported:

**User invocation:** the user invokes `decision-architecture` directly with a decision statement. The framework opens with brief progressive questioning to confirm the decision is stakeholder-laden, uncertainty-laden, and warrants the molecular pass (rather than constraint-mapping or decision-under-uncertainty alone).

**Pipeline-dispatched:** the four-stage pre-routing pipeline classifies the user's prompt as T3-decision-making, depth-molecular position, and dispatches DAA. The framework acknowledges the dispatch and proceeds.

**Handoff from another mode:** a sibling mode (constraint-mapping, decision-under-uncertainty) has surfaced that the decision warrants the full molecular pass. The handoff package includes whatever analysis the prior mode produced; DAA inherits it as a starting position for the relevant component rather than regenerating.

## INPUT CONTRACT

DAA requires:

- **Decision statement** — the choice being made, framed as a question the decision-maker must answer ("should I accept this offer," "should we sunset product X," "should we rebuild the system or refactor"). If the user provides a decision in vague terms, elicit: *"What's the decision, and what are the alternatives you're choosing among?"*
- **Decision-maker identity** — confirm the user holds decision authority (not a third party). If the user is producing a document for someone else's decision, route to `decision-clarity` instead.

DAA optionally accepts:

- **Alternatives** — if the user has named alternatives, the framework uses them as a seed and tests breadth (per Stage 1 below). If not, the framework elicits: *"What alternatives are on the table — including the do-nothing option and any creative third options?"*
- **Criteria** — if the user has named decision criteria, the framework uses them in the constraint-mapping stage. If not, elicits during execution.
- **Stakeholder inventory** — if the user has named stakeholders, the framework uses them as a seed and tests breadth (absent voices). If not, elicits during execution.
- **Time pressure** — if the decision must be made by a specific date, the framework adjusts depth (warns if molecular pass exceeds the time budget).

## STAGE PROTOCOL

### Stage 1 — Decision Under Uncertainty (runs: full)

**Purpose:** Produce the probability-weighted outcomes per alternative under the relevant uncertainty regime (risk vs. uncertainty vs. deep uncertainty), surface defer/sequence/hedge/buy-information alternatives the framing might exclude, and assess value of information against cost of delay.

**Elicitation prompt (orchestrator → model):**
> "You are running the `decision-under-uncertainty` mode as Stage 1 of a Decision Architecture pass. The decision is: [decision_statement]. Alternatives initially named: [alternatives or 'none — elicit']. Produce the full output per the mode's contract: decision framing, uncertainty identification (classify each critical variable as risk / uncertainty / deep uncertainty), consequence analysis (probability-weighted outcomes per alternative), value-of-information analysis, recommendation with conditions-it-would-change-under, and non-quantifiable factors. Surface at least one defer / sequence / hedge / buy-information alternative if the user has framed the decision as binary. Probabilities should be ranges or qualitative bands — flag any point estimate without base-rate grounding."

**Intermediate output format:**

```yaml
stage_1_output:
  decision_framing: "<one-paragraph statement>"
  alternatives:
    - alt_id: A1
      description: "<one-line description>"
      includes_defer_or_hedge: true | false
    - alt_id: A2
      ...
  uncertainty_classification:
    - variable: "<name>"
      regime: risk | uncertainty | deep-uncertainty
      probability: "<range or qualitative band>"
      base_rate_anchor: "<source or 'no anchor — flagged as judgment'>"
  probability_weighted_outcomes:
    - alt_id: A1
      best_case: "<outcome>"
      modal_case: "<outcome>"
      worst_case: "<outcome>"
      expected_value: "<value if quantifiable, qualitative if not>"
  value_of_information:
    - candidate_information: "<what could be learned>"
      cost_of_acquisition: "<time/money/effort>"
      probability_it_changes_decision: "<range>"
      cost_of_delay: "<what's lost by waiting>"
  recommendation:
    leading_alt: A_n
    conditions_to_revisit: "<what would change the recommendation>"
  non_quantifiable_factors:
    - factor: "<name>"
      relevance: "<one-line>"
```

**Quality gates:**
- At least one defer / sequence / hedge / buy-information alternative present (CQ2 of decision-under-uncertainty).
- Each critical variable carries explicit risk/uncertainty/deep-uncertainty label.
- Probabilities are ranges or qualitative bands; point estimates flagged.
- Non-quantifiable factors named alongside quantitative framework.

**Hand-off to next stage:** Stage 2 receives the alternatives list, the probability-weighted outcomes, and the leading alternative. Constraint-mapping will check whether the leading alternative is bounded by binding constraints.

---

### Stage 2 — Constraint Mapping (runs: full)

**Purpose:** Map the deterministic tradeoff structure across alternatives — hard constraints (must satisfy or alternative is invalid), soft constraints (cost of violation), and no-lose elements (actions valuable regardless of which alternative is chosen).

**Elicitation prompt (orchestrator → model):**
> "You are running the `constraint-mapping` mode as Stage 2 of a Decision Architecture pass. Decision: [decision_statement]. Alternatives from Stage 1: [list]. Produce the full output per the mode's contract: decision context and constraints, ≥3 alternatives mapped (use Stage 1's alternatives as seed; add any the user has not named including a do-nothing baseline if absent), per-alternative analysis (success conditions / failure conditions / uniquely gained / forfeited — symmetric depth across alternatives), cross-alternative comparison, no-lose elements. Hard constraints invalidate alternatives; soft constraints are tradeoffs. Test whether each Stage 1 alternative survives the hard constraints; flag any that don't."

**Intermediate output format:**

```yaml
stage_2_output:
  hard_constraints:
    - constraint: "<name>"
      threshold: "<observable>"
      reasoning: "<why this is hard, not soft>"
  soft_constraints:
    - constraint: "<name>"
      cost_of_violation: "<characterization>"
  per_alternative_analysis:
    - alt_id: A1
      survives_hard_constraints: true | false
      success_conditions: "<testable propositions>"
      failure_conditions: "<testable propositions>"
      uniquely_gained: "<what only this alternative provides>"
      forfeited: "<what this alternative gives up>"
  no_lose_elements:
    - element: "<action>"
      value_regardless_of_alternative: "<one-line>"
  cross_alternative_comparison:
    differentiating_factors: "<list>"
    invalidated_alternatives: "<from Stage 1 — alternatives that fail hard constraints>"
```

**Quality gates:**
- ≥3 alternatives mapped (per CQ1 of constraint-mapping).
- Symmetric analytical depth across alternatives (no advocacy asymmetry).
- Each success/failure condition is testable, not vague.
- At least one no-lose element surfaced.
- Hard-constraint check applied to Stage 1's alternatives.

**Hand-off to Synthesis Stage 1:** the integrated decision frame stage receives Stage 1's probability-weighted outcomes and Stage 2's binding constraints together.

---

### Synthesis Stage 1 — Decision-Frame Integration

**Type:** parallel-merge

**Inputs:** Stage 1 (decision-under-uncertainty), Stage 2 (constraint-mapping)

**Synthesis prompt (orchestrator → model):**
> "Integrate the decision-under-uncertainty output and the constraint-mapping output into a single decision frame. For each alternative, present probability-weighted outcomes alongside binding constraint status. Surface any tensions: alternatives whose probability-weighted outcomes look attractive but are invalidated by hard constraints; alternatives whose hard-constraint pass is clean but whose probability-weighted outcomes are weak; the leading alternative under combined evaluation (probability-weighted outcome × constraint compliance). Resist concatenating the two outputs — produce one integrated frame in which each alternative carries both lenses."

**Output format:**

```yaml
decision_frame_integration:
  per_alternative_integrated:
    - alt_id: A1
      probability_weighted_summary: "<from Stage 1>"
      constraint_compliance: passes_all_hard | violates: [list]
      integrated_assessment: "<one paragraph integrating both lenses>"
  tensions_surfaced:
    - tension: "<description — e.g., 'A2 has highest expected value but violates hard constraint H3'>"
  leading_alternative_under_integration: A_n
  reasoning: "<why this alternative leads when probability-weighted outcomes and constraints are integrated>"
```

**Quality gates:**
- Output integrates rather than concatenates (per CQ2 of decision-architecture: silo-aggregation is a failure mode).
- At least one tension surfaced if probability-weighted ranking and constraint-compliance disagree.
- Leading alternative is named and reasoned.

---

### Stage 3 — Stakeholder Mapping (runs: full)

**Purpose:** Map the parties affected by each alternative, their stakes (concrete interests, not role-labels), salience along Mitchell-Agle-Wood dimensions (power × legitimacy × urgency), absent or marginalized parties, and relationships among parties.

**Elicitation prompt (orchestrator → model):**
> "You are running the `stakeholder-mapping` mode as Stage 3 of a Decision Architecture pass. Decision: [decision_statement]. Alternatives carried from Synthesis Stage 1: [list]. Produce the full output per the mode's contract: stakeholder inventory (including parties from outside the user's initial frame), power-interest positioning (Bryson grid), Mitchell-Agle-Wood salience classification on all three dimensions for each party, stake-per-party as concrete interests, relationships among parties, absent or marginalized parties named explicitly. The output will feed Synthesis Stage 2, which overlays per-alternative stakeholder impact onto the decision frame."

**Intermediate output format:**

```yaml
stage_3_output:
  stakeholder_inventory:
    - party_id: P1
      name: "<party>"
      from_user_frame: true | false
      role: "<role-label>"
      concrete_stake: "<what the party wants and could lose>"
      bryson_position: "high-power-high-interest | high-power-low-interest | low-power-high-interest | low-power-low-interest"
      mitchell_agle_wood:
        power: high | medium | low
        legitimacy: high | medium | low
        urgency: high | medium | low
        classification: "definitive | dominant | dangerous | dependent | dormant | discretionary | demanding"
  relationships_among_parties:
    - pair: [P1, P2]
      relationship: ally | opposition | dependency | broker
  absent_or_marginalized:
    - party_id: P_n
      reason_for_absence: "<one-line>"
```

**Quality gates:**
- At least one party from outside user's initial frame (CQ1 of stakeholder-mapping).
- Stakes named as concrete interests, not role-labels (CQ2).
- Salience populated on all three Mitchell-Agle-Wood dimensions (CQ3).
- At least one absent/marginalized party named, or explicit "none identified" with reason (CQ4).

**Hand-off to Synthesis Stage 2:** the stakeholder-impact-overlay stage receives the integrated decision frame from Synthesis 1 and the stakeholder inventory from Stage 3.

---

### Synthesis Stage 2 — Stakeholder Impact Overlay

**Type:** sequenced-build

**Inputs:** Synthesis Stage 1 (integrated decision frame), Stage 3 (stakeholder mapping)

**Synthesis prompt (orchestrator → model):**
> "Take the integrated decision frame from Synthesis Stage 1 and overlay per-alternative stakeholder impact. For each alternative, name which stakeholders benefit (with their values honored), which stakeholders bear costs (with their values subordinated), and identify power-asymmetries that would shape the decision's reception. Critically: stakeholder impacts must be mapped per alternative, NOT aggregated into a generic stakeholder list disconnected from the choice (failure mode: stakeholder-disconnection). If the leading alternative under Synthesis Stage 1 produces severe impact on a high-salience stakeholder, surface this tension."

**Output format:**

```yaml
stakeholder_impact_overlay:
  per_alternative_stakeholder_impact:
    - alt_id: A1
      beneficiaries:
        - party_id: P_n
          interest_honored: "<concrete interest from Stage 3>"
      cost_bearers:
        - party_id: P_n
          interest_subordinated: "<concrete interest from Stage 3>"
      power_asymmetries: "<who has leverage to push back, who lacks leverage>"
      overall_stakeholder_judgment: "<acceptable to high-salience parties | severe impact on H/L/U party | mixed>"
  revised_leading_alternative: A_n
  reasoning_for_revision: "<if leading alternative changes after stakeholder overlay>"
  tensions: "<list any tensions between integrated decision frame's leading alt and stakeholder-impact-overlay's leading alt>"
```

**Quality gates:**
- Stakeholder impacts mapped PER alternative (not generic list — CQ3 of decision-architecture).
- High-salience stakeholders' impacts surfaced explicitly.
- Power asymmetries named.
- If leading alternative shifts after overlay, the shift is reasoned.

---

### Stage 4 — Pre-Mortem (Action) (runs: full)

**Purpose:** Stress-test the leading alternative (and one runner-up if available) using prospective hindsight: imagine it's six-to-twelve months from now and the chosen alternative has failed; produce the failure narrative, name failure modes specific to this plan's mechanism (not generic project tropes), trace causal pathways to failure, identify leading indicators per failure mode, distinguish pre-commitment mitigations from post-hoc remediations, and name residual unmitigated risks.

**Elicitation prompt (orchestrator → model):**
> "You are running the `pre-mortem-action` mode as Stage 4 of a Decision Architecture pass. The leading alternative under integrated decision frame + stakeholder impact overlay is: [A_n description]. The runner-up alternative is: [A_m description]. For each, run the pre-mortem in past-tense prospective hindsight: write the post-mortem the team would produce after the failure. Failure modes must be plan-specific (not generic tropes like 'scope creep'); each failure mode must have at least one leading indicator the team could observe pre-failure; mitigations must be pre-commitment actions only. Produce the full output per the mode's contract: imagined failure narrative, failure mode inventory (organized by execution / assumption / context-shift / interaction / motivational classes), causal pathways, leading indicators, pre-commitment mitigations, residual unmitigated risks."

**Intermediate output format:**

```yaml
stage_4_output:
  per_alternative_pre_mortem:
    - alt_id: A_n
      imagined_failure_narrative: "<past-tense post-mortem prose>"
      failure_modes:
        - failure_id: F1
          class: execution | assumption | context-shift | interaction | motivational
          plan_specific_mechanism: "<not generic — specific to this alternative>"
          causal_pathway: "<from breakage to visible failure>"
          leading_indicator: "<observable signal, with threshold>"
          pre_commitment_mitigation: "<action team can lock in BEFORE commitment>"
      residual_unmitigated_risks:
        - risk: "<description>"
          why_unmitigated: "<reason>"
```

**Quality gates:**
- Failure narrative in past-tense prospective hindsight (no hedged forward conditional).
- Each failure mode plan-specific (no generic tropes — CQ2 of pre-mortem-action).
- Each failure mode has at least one leading indicator (CQ3).
- Mitigations are pre-commitment actions only, not post-hoc (CQ4).

**Hand-off to Synthesis Stage 3:** the failure-mode-stress-test stage receives the integrated decision frame, the stakeholder impact overlay, and the pre-mortem findings.

---

### Synthesis Stage 3 — Failure-Mode Stress Test

**Type:** contradiction-surfacing

**Inputs:** Synthesis Stage 2 (stakeholder impact overlay), Stage 4 (pre-mortem-action)

**Synthesis prompt (orchestrator → model):**
> "Stress-test the leading alternative against the pre-mortem failure pathways. For each named failure mode, ask: would this failure mode change which alternative leads? If a leading indicator fires, would the runner-up become superior? If a residual unmitigated risk lands, does the alternative remain net-positive? Produce a revised alternative ranking that incorporates failure-pathway resilience — an alternative whose probability-weighted outcomes are slightly weaker but whose pre-mortem reveals fewer plan-specific failure modes may be the better integrated choice. If the leading alternative's pre-mortem reveals catastrophic failure modes the runner-up does not share, the runner-up may rise."

**Output format:**

```yaml
failure_mode_stress_test:
  leading_alternative_under_stress_test: A_n
  failure_modes_examined:
    - failure_id: F1
      severity_if_realized: high | medium | low
      reversibility: reversible | partially-reversible | irreversible
      changes_alternative_ranking: true | false
      reasoning: "<why this failure mode does/does not flip ranking>"
  revised_alternative_ranking:
    - alt_id: A_n
      rank: 1
      reasoning: "<why this alternative leads after stress test>"
  residual_risks_accepted: "<list>"
```

**Quality gates:**
- At least one failure mode examined for "would this flip the ranking" (CQ4 of decision-architecture: pre-mortem-omission is a failure mode).
- Revised ranking is reasoned, not arbitrary.
- Residual risks named explicitly (not papered over).

---

### Synthesis Stage 4 — Integrated Decision Architecture

**Type:** dialectical-resolution

**Inputs:** Synthesis Stage 1 (decision frame integration), Synthesis Stage 2 (stakeholder impact overlay), Synthesis Stage 3 (failure-mode stress test)

**Synthesis prompt (orchestrator → model):**
> "Produce the final integrated Decision Architecture Document. Structure: (1) decision frame — what's being decided, alternatives, criteria. (2) Probability-weighted outcomes and binding constraints (from Synthesis 1). (3) Stakeholder impact per alternative (from Synthesis 2). (4) Failure-mode stress test findings (from Synthesis 3). (5) Recommended alternative with residual risks named explicitly. (6) Decision-conditions-to-monitor — concrete observable signals that would trigger reconsideration of the recommendation. (7) Confidence map per finding. The recommendation should be one no single component could have produced — the dialectical product of probability-weighted outcomes × constraints × stakeholder impact × failure pathways. Resist a clean-recommendation framing that omits residual risks. Decision-conditions-to-monitor must be concrete enough to be falsifiable (no 'watch how things develop')."

**Output format:** see OUTPUT CONTRACT below.

**Quality gates:**
- Recommendation integrates all four lenses (no concatenation).
- Residual risks named explicitly (not minimized).
- Decision-conditions-to-monitor are concrete observable signals (CQ5 of decision-architecture: monitoring-vagueness is a failure mode).
- Confidence map per finding.

---

## OUTPUT CONTRACT — Final Artifact Template

```markdown
[DAA — Decision Architecture Analysis]

# Decision Architecture for <decision name>

## Executive Summary
- **Decision:** <one-sentence statement>
- **Alternatives evaluated:** <count> — <one-line characterizations>
- **Recommended alternative:** <name + one-line rationale>
- **Top residual risk:** <one-line>
- **Top decision-condition to monitor:** <observable signal>

## 1. Decision Frame
[Statement of the decision being made; decision-maker is the user; time horizon; criteria.]

## 2. Alternatives with Probability-Weighted Outcomes
[For each alternative:]
- **Alternative <N>: <name>**
  - Description: <one paragraph>
  - Best case / modal case / worst case (probability-weighted): <table>
  - Uncertainty regime per critical variable: <risk / uncertainty / deep-uncertainty per variable>

## 3. Binding Constraints
- **Hard constraints:** <list with thresholds>
- **Soft constraints:** <list with costs of violation>
- **Alternatives invalidated by hard constraints:** <list with reasoning>
- **No-lose elements:** <actions valuable regardless of choice>

## 4. Stakeholder Impact per Alternative
[For each alternative:]
- **Alternative <N>:**
  - Beneficiaries: <party + interest honored>
  - Cost-bearers: <party + interest subordinated>
  - Power asymmetries: <who can push back, who cannot>
  - Salience-weighted impact summary: <one paragraph>

[Cross-cutting:]
- **Absent or marginalized parties:** <named with reason>
- **High-salience parties whose impact differs sharply across alternatives:** <list>

## 5. Failure-Mode Stress Test Findings
[For the leading alternative and one runner-up:]
- **Alternative <N> imagined failure narrative (past tense):**
  <prose>
- **Failure modes inventoried:**
  - F1: class / mechanism / leading indicator / pre-commitment mitigation
  - F2: ...
- **Residual unmitigated risks:**
  - <list with why-unmitigated reason>

## 6. Recommended Alternative with Residual Risks
- **Recommendation:** <Alternative N — name>
- **Reasoning (integrating probability-weighted outcomes × constraints × stakeholder impact × failure pathways):** <one to two paragraphs>
- **Why no single component could have produced this:** <one paragraph naming the integrative work>
- **Residual risks accepted by this recommendation:** <list — explicit, not minimized>

## 7. Decision-Conditions-to-Monitor
[Concrete observable signals that would trigger reconsideration:]
- **Signal 1:** <observable> — threshold: <specific> — what it would mean: <one-line>
- **Signal 2:** ...
- **Signal 3:** ...

## 8. Confidence Map
[Per finding:]
| Finding | Confidence | Reason |
|---------|------------|--------|
| Probability-weighted outcomes for Alt 1 | high / medium / low | <reason — base rate quality, evidence available> |
| Stakeholder salience for Party P3 | ... | ... |
| Pre-mortem failure mode F2 leading indicator | ... | ... |
```

## WORKED EXAMPLE WALKTHROUGH

**Opening prompt (user):** *"I'm trying to decide whether to accept a senior engineering role at a Series B startup that's offered me a 60% pay raise plus equity, or stay at my current FAANG job with a path to staff in 18 months. I want the full architecture — there are family considerations, the startup might fail, and I'm worried about regretting either choice."*

**Stage 1 output (decision-under-uncertainty):**
- Alternatives initially: A1 = take startup offer, A2 = stay at FAANG.
- Surfaced via defer-prompt: A3 = ask FAANG to accelerate timeline (defer alternative); A4 = take startup but negotiate cliff/buyout terms (hedge alternative).
- Uncertainty classification: startup survives 18 months = uncertainty (range 50-70% based on Series B base rates); FAANG path-to-staff materializes = uncertainty (60-75% based on org culture).
- Probability-weighted outcomes:
  - A1: 60% pay raise realized × 60% survival = expected value depends on liquidity event (deep uncertainty).
  - A2: staff promotion modal case is +30% TC + safer career, low variance.
  - A3: low downside, may not be granted.
  - A4: cushions startup downside.
- VOI: waiting 60 days to see startup's Q3 hiring results would update survival probability — cost of delay is offer expiry (probability offer remains open in 60 days: 30%).
- Recommendation: A4 (startup with hedged terms) leads on EV, but flag non-quantifiable factors (family, identity).
- Non-quantifiable: spouse's career mobility constrained by startup's location; identity tied to FAANG role.

**Stage 2 output (constraint-mapping):**
- Hard constraints: family income floor ($X/month for mortgage); spouse's job within commuting distance.
- Soft constraints: equity vesting alignment with kids' school timing; visa/immigration if applicable.
- Per-alternative analysis (symmetric):
  - A1: survives hard constraints if startup pays cash component matching floor; uniquely gained = founder-stage learning, equity upside; forfeited = stability, FAANG brand.
  - A2: survives all hard constraints; uniquely gained = stability, brand; forfeited = startup-equity upside.
  - A3: survives all; uniquely gained = retains both options briefly; forfeited = signals to current employer.
  - A4: survives all if cliff/buyout negotiated; uniquely gained = optionality.
- No-lose elements: prepare departure logistics regardless (8 hours work valuable for any alternative).

**Synthesis Stage 1 (decision frame integration):**
- A1 fails one hard constraint if cash component ≤ floor — the EV story collapses.
- A2's probability-weighted outcomes are weakest but constraint-compliance is cleanest.
- A4 leads under integration: hedges both probability-weighted EV and constraint compliance.
- Tension surfaced: A1's EV is highest only conditional on cash floor met — verify before integration ranks A4.

**Stage 3 output (stakeholder mapping):**
- P1: User — high power, high legitimacy, high urgency (definitive).
- P2: Spouse — high power (veto on relocation), high legitimacy, high urgency.
- P3: Kids — low power (cannot decide), high legitimacy, medium urgency.
- P4: Current FAANG manager — medium power (can accelerate path-to-staff), medium legitimacy, low urgency.
- P5: Startup founders — medium power, medium legitimacy, high urgency (need decision).
- P6: Future-self at year 5 — surfaced as absent party; not represented in current consultation.

**Synthesis Stage 2 (stakeholder impact overlay):**
- A1: severe impact on P2 if relocation; P5 wins; P3 mixed.
- A2: P2 unaffected; P3 stable; P5 disappointed but no severe impact (they can hire elsewhere).
- A3: P4 may interpret as disloyalty (signals leaving) — soft cost.
- A4: optionality protects P2 partially; P5 may decline hedged terms.
- Power asymmetry: P2 holds veto on A1; P5 holds time pressure that constrains A3.
- Revised leading: A4 still leads if P5 accepts hedged terms; otherwise A2.

**Stage 4 output (pre-mortem-action) on A4 and A2:**
- A4 imagined failure narrative: "Eighteen months in, the startup pivoted twice and burned cash; cliff acceleration kicked in but equity proved illiquid; spouse's career suffered from relocation; user took FAANG re-entry role at lower level than starting point."
  - F1 (assumption): assumed pivots would be product pivots; were actually market pivots requiring new hires not new code → leading indicator: hiring profile shifts in next two quarterly all-hands.
  - F2 (interaction): assumed cliff terms protected user; protected only against involuntary departure, not against sustained underperformance → leading indicator: performance review framing language at 6-month mark.
- A2 imagined failure narrative: "User stayed at FAANG; staff promotion delayed by reorganization; startup that user declined IPO'd at 6× and former classmates retired at 35; user developed quiet resentment; left FAANG at year 4 in worse market conditions."
  - F1 (context-shift): assumed FAANG org structure stable; reorg delayed promotion → leading indicator: skip-level changes within 6 months.
  - F2 (motivational): assumed staying-out-of-startups-was-permanent-decision; counterfactual envy is a real failure mode → leading indicator: mental health check-ins, frequency of "what if" rumination.

**Synthesis Stage 3 (failure-mode stress test):**
- A4's F1 (market pivots) + F2 (cliff insufficient) jointly catastrophic if realized; reversibility low.
- A2's F1 (reorg) is recoverable; F2 (counterfactual envy) is partially mitigated by knowing A4 was on offer and was hedged.
- Revised ranking: A2 rises if A4's F1+F2 joint probability is ≥ 30%; otherwise A4 leads.
- Decision turns on: P5's openness to hedged terms × user's actual estimate of joint F1+F2 probability.

**Synthesis Stage 4 (integrated decision architecture):**

Recommendation: A4 (startup with hedged terms) IF P5 accepts cliff acceleration AND cash floor exceeds family income threshold AND user estimates joint F1+F2 probability ≤ 25%. Otherwise A2 (stay at FAANG with explicit conversation about path-to-staff timeline). Decision is conditional on P5's response and on the user's honest probability estimate of joint F1+F2.

Decision-conditions-to-monitor (post-decision):
- Signal 1: Hiring-profile shift at startup all-hands at 3-month mark — if engineering hiring pace drops below 1 hire/month, F1 leading indicator fired.
- Signal 2: Performance review framing language at 6-month mark — if review uses "potential" rather than "delivered," F2 leading indicator fired.
- Signal 3: Spouse career satisfaction self-assessment at 9-month mark — if self-rating drops by ≥2 points on a 10-point scale, P2 impact materializing.
- Signal 4 (for A2 if chosen): skip-level org structure changes within 6 months — if skip-level reorganized, path-to-staff timeline at risk; renegotiate.

Residual risks accepted: deep uncertainty in startup liquidity event; counterfactual envy in either choice; spouse's career mobility constrained in either case.

Confidence map: probability-weighted outcomes for A1/A4 = medium (Series B base rates well-documented); stakeholder salience for P2 = high; pre-mortem F2 for A4 = medium (cliff terms commonly insufficient, but specific terms vary); decision-conditions-to-monitor = high (concrete signals).

## CAVEATS AND OPEN DEBATES

**Composition limit — recommendation honesty.** Decision Architecture produces a recommendation, unlike Decision Clarity which refuses to. The recommendation is honest only when residual risks are named explicitly and decision-conditions-to-monitor are concrete enough to be falsifiable. The framework's analytical character is "integrated decision-making with eyes open"; sliding into clean-recommendation framing that omits residual risks is a failure mode (per CQ5 of decision-architecture: monitoring-vagueness).

**When to escalate sideways to decision-clarity:** if during execution it emerges that the user is producing the document for a third-party decision-maker rather than themselves, halt DAA and route to `decision-clarity`. The two modes share component modes but their output contracts and synthesis stances differ — DAA recommends, DCA does not.

**When to de-escalate downward:** if during Stage 1 it emerges the decision is constraint-bounded only (no real probability arithmetic) or stakeholder-light, route downward to `constraint-mapping` or `decision-under-uncertainty`. The molecular pass is wasted on under-spec'd decisions.

## QUALITY GATES (overall)

- All four components ran (or were flagged as proceeded-with-gap with reason).
- All four synthesis stages integrated rather than concatenated.
- The leading alternative carries a pre-mortem stress test.
- Decision-conditions-to-monitor are concrete observable signals.
- Confidence map populated per finding.
- The five critical questions of `decision-architecture` (option-set-poverty, silo-aggregation, stakeholder-disconnection, pre-mortem-omission, monitoring-vagueness) are addressed.
- Recommendation is one no single component could have produced.

## RELATED MODES AND CROSS-REFERENCES

- **Paired mode file:** `Modes/decision-architecture.md`
- **Component mode files:**
  - `Modes/decision-under-uncertainty.md` (Stage 1)
  - `Modes/constraint-mapping.md` (Stage 2)
  - `Modes/stakeholder-mapping.md` (Stage 3)
  - `Modes/pre-mortem-action.md` (Stage 4)
- **Sibling Wave 4 mode (related operation, different output):** `Modes/decision-clarity.md` and `Framework — Decision Clarity Analysis.md`
- **Territory framework:** `Framework — Decision-Making Under Uncertainty.md`
- **Lens dependencies:** kahneman-tversky-bias-catalog (foundational), knightian-risk-uncertainty-ambiguity (optional), expected-utility-theory (via decision-under-uncertainty), klein-pre-mortem (via pre-mortem-action), stakeholder-analysis-frameworks (via stakeholder-mapping).

*End of Decision Architecture Analysis Framework.*
