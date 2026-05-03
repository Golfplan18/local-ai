
# Wicked-Future Analysis Framework

*A Framework for Producing an Integrated Forward Analysis with Probability-Weighted Scenarios, Adversarial-Future Stress-Test Findings, Divergence Points to Monitor, and Explicit Gap-Flagging Where Constructive-Future (Backcasting) Analysis Has Been Deferred.*

*Version 1.0*

*Bridge Strip: `[WFA — Wicked-Future Analysis]`*

---

## Architectural Note

This framework supports the `wicked-future` mode, the depth-molecular operation in T6 (future exploration). The mode file at `Modes/wicked-future.md` carries the locked spec — molecular_spec.components, critical_questions, output_contract.required_sections — sufficient for the orchestrator to dispatch the three component modes (`scenario-planning`, `pre-mortem-action`, `probabilistic-forecasting`) and the three synthesis stages (scenario-probability-overlay, failure-pathway-stress-test, integrated-future-architecture). This framework adds the procedural detail the spec does not carry: the elicitation prompts the orchestrator uses, the intermediate output formats, the per-stage quality gates, and the worked example showing the framework operating end-to-end.

The framework sits in T6's depth ladder above `consequences-and-sequel` (T6-light, atomic, forward projection), `scenario-planning` (T6-thorough, atomic, narrative-output), `probabilistic-forecasting` (T6-thorough, atomic, probability-output), and `pre-mortem-action` (T6 stance-counterpart, atomic, adversarial-future). It composes those siblings into an integrated forward analysis. The territory framework is `Framework — Future Exploration.md`. WFA is the heaviest analytical mode in T6 currently buildable; the constructive-future stance (backcasting) is gap-deferred per CR-6 and the framework documents the deferred-component handling explicitly rather than substituting.

---

## How to Use This File

This framework runs when the user has a forward-looking question that resists single-method analysis: scenarios alone don't carry calibrated probabilities, probability-forecasting alone misses the divergence narratives, pre-mortem alone evaluates one plan rather than the broader future. WFA's value is in the integration: scenarios with probability bands, scenarios stress-tested against pre-mortem failure pathways, divergence points to monitor.

WFA differs from scenario-planning (atomic narrative scenarios) and probabilistic-forecasting (atomic calibrated estimates). Use WFA when the question is genuinely tangled, the time horizon is long enough that single-method analysis is insufficient, and the user wants integrated output rather than three separate reads.

Three invocation paths supported:

**User invocation:** the user invokes `wicked-future` directly with a forward question. The framework opens with brief progressive questioning to confirm the question warrants the molecular pass and to elicit time horizon and key uncertainties.

**Pipeline-dispatched:** the four-stage pre-routing pipeline classifies the user's prompt as T6-future-exploration, depth-molecular, and dispatches WFA.

**Handoff from another mode:** scenario-planning or probabilistic-forecasting has surfaced that the question warrants integrated treatment. The handoff package includes the prior analysis; WFA inherits it as a starting position for the relevant component.

## INPUT CONTRACT

WFA requires:

- **Forward question** — the future-shaped question being explored ("what will the AI agent ecosystem look like in 5 years," "how will Brexit reshape financial services in a decade," "what could disrupt our supply chain over the next 3 years"). Elicit if missing: *"What's the forward-looking question, and over what time horizon?"*

WFA optionally accepts:

- **Time horizon** — if the user has named a horizon, use it. Otherwise elicit.
- **Key uncertainties** — if the user has identified the driving forces or critical uncertainties, the framework uses them in Stage 1's scenario construction. If not, surface during execution.
- **Prior scenarios** — if the user has done preliminary scenario thinking, the framework uses it as a seed.
- **Prior forecasts** — if the user has probability estimates on key outcomes, the framework uses them in Stage 3.
- **Intervention candidates** — if the user has named possible actions or strategies they're considering, the framework includes them in Stage 2's pre-mortem-action stress test.

## STAGE PROTOCOL

### Stage 1 — Scenario Planning (runs: full)

**Purpose:** Construct narrative scenarios spanning the realistic future range — at minimum a 2×2 matrix from two genuinely independent critical uncertainties, plus at least one wild-card scenario outside the matrix. Each scenario has distinct causal logic (not magnitude variants), leading indicators, and strategic implications. No scenario is designated "most likely."

**Elicitation prompt (orchestrator → model):**
> "You are running the `scenario-planning` mode (full) as Stage 1 of a Wicked-Future pass. The forward question is: [forward_question]. Time horizon: [time_horizon or 'elicit']. Produce the full output per the mode's contract: focal question, driving forces classified (predetermined vs. critical uncertainties — STEEP categorization), critical uncertainties as axes (two genuinely independent uncertainties), 2×2 scenario matrix (four scenarios with distinct causal logic, not magnitude variants), leading indicators per scenario, strategic implications, at least one wild-card scenario in prose. Do NOT designate any scenario 'most likely' — this is the official-future-trap. Axes-independence rationale must be ≥40 chars (not trivial)."

**Intermediate output format:**

```yaml
stage_1_output:
  focal_question: "<one-sentence>"
  time_horizon: "<years>"
  driving_forces:
    predetermined: "<list — forces happening regardless>"
    critical_uncertainties: "<list — forces that could go either way>"
  axes:
    x_axis:
      label: "<axis>"
      low: "<one-line>"
      high: "<one-line>"
    y_axis:
      label: "<axis>"
      low: "<one-line>"
      high: "<one-line>"
    independence_rationale: "<≥40 chars explaining why axes are independent>"
  scenarios:
    - quadrant: TL | TR | BL | BR
      name: "<distinct causal logic name, not 'optimistic'>"
      narrative: "<coherent causal sequence — how this future arrives>"
      leading_indicators: "<≥1 observable signal>"
      strategic_implication: "<actionable>"
  wild_card_scenario:
    name: "<low-probability/high-impact future outside the 2×2>"
    narrative: "<one paragraph>"
    why_outside_matrix: "<one-line>"
  strategic_implications:
    robust_strategies: "<work across scenarios>"
    scenario_dependent_strategies: "<require correctly identifying which scenario>"
```

**Quality gates:**
- Four scenarios with distinct causal logic (CQ1 of scenario-planning: good-bad-medium-trap).
- Axes independence rationale ≥40 chars (CQ2: correlated-axes-trap).
- No scenario designated "most likely" (CQ3: official-future-trap).
- Driving forces honestly classified predetermined vs. critical uncertainty (CQ4).
- Each scenario has at least one leading indicator (CQ5: story-without-strategy-trap).
- Wild card present in prose, not in matrix.

**Hand-off to Stage 2:** the scenario set becomes the substrate for probabilistic-forecasting in parallel and pre-mortem-action in sequence.

---

### Stage 2 — Probabilistic Forecasting (runs: full)

**Purpose:** Produce calibrated probability bands over the scenarios from Stage 1 (and over key outcomes within scenarios) using base-rate-anchored reference classes, inside-vs-outside view separation, and ranges rather than point estimates.

**Elicitation prompt (orchestrator → model):**
> "You are running the `probabilistic-forecasting` mode (full) as Stage 2 of a Wicked-Future pass. The scenarios from Stage 1 are: [list]. For each scenario, produce a probability band (range, not point). For each scenario, produce the full forecasting output per the mode's contract: resolution criteria locked (operationally — what would count as this scenario materializing), reference class and base rate, inside-view drivers (what's specific to this scenario in this domain), outside-view adjustment (how this case compares to the reference class — show the math), probability estimate with range, leading indicators and update triggers, confidence in estimate. Where scenarios have shared outcomes, also produce probability bands on key cross-scenario outcomes (e.g., 'AI agents reach X capability level' may cross scenarios)."

**Intermediate output format:**

```yaml
stage_2_output:
  per_scenario_forecasts:
    - scenario_name: "<from Stage 1>"
      resolution_criteria: "<operational — what would count as this materializing>"
      reference_class: "<historical analogue>"
      base_rate: "<number from reference class>"
      inside_view_drivers:
        - driver: "<this case's specifics>"
          direction: up | down
          magnitude: "<percentage points or qualitative>"
      outside_view_adjustment: "<show the math: base 15%, drivers shift +10pp → 25-30%>"
      probability_range: "<e.g., 0.20-0.35>"
      leading_indicators:
        - indicator: "<observable>"
          threshold: "<specific>"
          update_direction: "<if observed, posterior shifts toward/away>"
      confidence_in_estimate: high | medium | low
  cross_scenario_outcome_forecasts:
    - outcome: "<outcome that crosses scenarios>"
      probability_range: "<e.g., 0.40-0.60 within 5 years>"
      depends_on_scenarios: "<which Stage 1 scenarios this is sensitive to>"
```

**Quality gates:**
- Resolution criteria operational, not vague (CQ1 of probabilistic-forecasting: unresolvable-question).
- Reference class and base rate explicit (CQ2: base-rate-neglect).
- Inside-view and outside-view separated with shown adjustment (CQ3: view-collapse).
- Probability ranges, not points (CQ4: false-precision).
- Leading indicators with update triggers.

**Hand-off to Synthesis Stage 1:** the scenario-probability-overlay stage receives Stage 1's scenarios and Stage 2's probability bands.

---

### Synthesis Stage 1 — Scenario-Probability Overlay

**Type:** parallel-merge

**Inputs:** Stage 1 (scenario-planning), Stage 2 (probabilistic-forecasting)

**Synthesis prompt (orchestrator → model):**
> "Integrate Stage 1's scenarios with Stage 2's probability bands. For each scenario, present the narrative paired with the probability range. Identify divergence points: the moments in the next [time_horizon/3] timeframe at which the scenarios branch — what specific events or developments would tell us which scenario is materializing. Resist concatenating the two outputs; the integration should produce divergence points the probability formalism alone cannot price (because divergence is narrative-shaped) and probability bands that constrain narrative speculation. If Stage 2's probability bands collide with Stage 1's scenario coherence (e.g., a scenario that requires conditions Stage 2 forecasts as <5% probable), surface the tension. Do NOT designate any scenario 'most likely' even if its probability band is highest — preserve the equal-standing-of-scenarios commitment."

**Output format:**

```yaml
scenario_probability_overlay:
  per_scenario_integrated:
    - scenario_name: "<>"
      narrative_summary: "<from Stage 1>"
      probability_range: "<from Stage 2>"
      coherence_check: scenarios-and-probability-cohere | tension-noted
      tension_note: "<if scenario requires conditions Stage 2 forecasts as low>"
  divergence_points:
    - timeframe: "<e.g., '6-12 months'>"
      observable_event: "<what would distinguish scenarios>"
      scenarios_distinguished: "<which scenarios this divergence selects between>"
  monitoring_priorities:
    - "<observable signal that updates probability bands>"
```

**Quality gates:**
- Output integrates rather than concatenates (CQ2 of wicked-future: silo-aggregation).
- Divergence points named (these are the unique product of the synthesis).
- No scenario designated "most likely" preserved.
- Tensions between scenario coherence and probability bands surfaced explicitly.

---

### Stage 3 — Pre-Mortem (Action) (runs: full)

**Purpose:** Stress-test the scenarios for failure pathways. The pre-mortem-action mode normally targets a specific action plan; in WFA composition it targets the scenarios themselves and any intervention candidates the user has named. For each scenario, imagine the "failure" is that this future arrives unprepared or with worst-case dynamics — what failure modes activate? For each intervention candidate, run the standard pre-mortem.

**Elicitation prompt (orchestrator → model):**
> "You are running the `pre-mortem-action` mode (full) as Stage 3 of a Wicked-Future pass. The scenarios from Stage 1 are: [list]. Intervention candidates from input (if any): [list]. For each scenario, imagine it is now [time horizon] in the future and this scenario has materialized in its worst-case form. Produce the prospective-hindsight failure narrative: what failed, why, what leading indicators were missed. For each intervention candidate, also run the standard pre-mortem. Failure modes must be plan-specific or scenario-specific (not generic tropes); each must have leading indicators; mitigations must be pre-commitment. Per the mode's contract: imagined failure narrative, failure mode inventory (organized by execution / assumption / context-shift / interaction / motivational classes), causal pathways, leading indicators, pre-commitment mitigations, residual unmitigated risks."

**Intermediate output format:**

```yaml
stage_3_output:
  per_scenario_pre_mortem:
    - scenario_name: "<>"
      worst_case_failure_narrative: "<past-tense prose>"
      failure_modes:
        - failure_id: F1
          class: execution | assumption | context-shift | interaction | motivational
          scenario_specific_mechanism: "<not generic>"
          causal_pathway: "<from breakage to visible failure>"
          leading_indicator: "<observable, with threshold>"
          pre_commitment_mitigation: "<action to lock in BEFORE scenario materializes>"
      residual_unmitigated_risks: "<list>"
  per_intervention_pre_mortem:
    - intervention_name: "<>"
      imagined_failure_narrative: "<past-tense prose>"
      failure_modes: "<same structure as scenario pre-mortems>"
```

**Quality gates:**
- Failure narratives in past-tense prospective hindsight (CQ1 of pre-mortem-action: stance-slippage).
- Failure modes scenario-specific or plan-specific, not generic tropes (CQ2).
- Each failure mode has at least one leading indicator (CQ3).
- Mitigations are pre-commitment, not post-hoc (CQ4).

**Hand-off to Synthesis Stage 2:** the failure-pathway-stress-test stage receives Synthesis Stage 1's overlay and Stage 3's pre-mortem findings.

---

### Synthesis Stage 2 — Failure-Pathway Stress Test

**Type:** contradiction-surfacing

**Inputs:** Synthesis Stage 1 (scenario-probability overlay), Stage 3 (pre-mortem-action)

**Synthesis prompt (orchestrator → model):**
> "Stress-test the scenarios against the pre-mortem failure pathways. For each scenario, identify which pre-mortem failure modes activate within it — and identify scenarios that contain failure modes Stage 1's narrative did not surface. Where a scenario's probability band is high but its pre-mortem reveals catastrophic failure pathways, the integrated forward analysis must name that as a high-impact concern even when the probability is below the leading scenario. Identify which divergence points (from Synthesis 1) also serve as leading indicators for failure modes (from Stage 3) — these are the highest-leverage monitoring priorities. Surface contradictions: e.g., a scenario whose narrative is coherent but whose pre-mortem reveals load-bearing assumptions that Stage 1's scenario logic took for granted."

**Output format:**

```yaml
failure_pathway_stress_test:
  per_scenario_failure_pathway_check:
    - scenario_name: "<>"
      failure_modes_activated: "<list of failure_ids from Stage 3>"
      scenario_narrative_inconsistencies: "<contradictions between Stage 1 narrative and Stage 3 failure analysis>"
      stress_test_finding: "<one paragraph integrating the pair>"
  divergence_points_serving_double_duty:
    - point: "<from Synthesis 1>"
      also_leading_indicator_for: "<failure_ids from Stage 3>"
      monitoring_priority: high | medium | low
  highest_leverage_signals:
    - signal: "<observable>"
      what_it_distinguishes: "<scenarios + failure modes>"
```

**Quality gates:**
- Pre-mortem ran against leading scenarios (CQ3 of wicked-future: pre-mortem-omission).
- Contradictions surfaced where they exist (silo-aggregation is a failure mode).
- Divergence-points-as-leading-indicators identified (highest-leverage monitoring).

---

### Synthesis Stage 3 — Integrated Future Architecture

**Type:** dialectical-resolution

**Inputs:** Synthesis Stage 1 (scenario-probability overlay), Synthesis Stage 2 (failure-pathway stress test)

**Synthesis prompt (orchestrator → model):**
> "Produce the final Integrated Future Architecture. Structure: (1) forward question and time horizon. (2) Scenario set with probability bands (from Synthesis 1). (3) Divergence points (from Synthesis 1). (4) Failure-pathway stress test findings (from Synthesis 2). (5) Integrated forward architecture — the synthesis of probability-weighted scenarios with named failure pathways and divergence-points-to-monitor. (6) Constructive-future gap-flag — a mandatory visible section noting that backcasting (constructive-future stance) was deferred per CR-6 and consumers requiring constructive-future framing should compose WFA with downstream goal-articulation work. (7) Residual uncertainties. (8) Confidence map per finding. The integrated architecture should produce forecast-claims that no single component could have produced — the dialectical product of scenarios × probabilities × failure pathways. The constructive-future gap-flag is mandatory and visible — not buried in the confidence map."

**Output format:** see OUTPUT CONTRACT below.

**Quality gates:**
- Output integrates four lenses, not three concatenations.
- Constructive-future gap-flag visible and explicit (CQ4 of wicked-future: silent-gap).
- Confidence map per finding.
- Forecast-claims include at least one that no single component could have produced.

---

## OUTPUT CONTRACT — Final Artifact Template

```markdown
[WFA — Wicked-Future Analysis]

# Wicked-Future Architecture for <forward question>

## Executive Summary
- **Forward question:** <one-sentence>
- **Time horizon:** <years>
- **Scenarios:** <count> + 1 wild card — <one-line characterizations>
- **Highest-leverage monitoring signal:** <observable>
- **Constructive-future gap:** Backcasting deferred — see §6 below.

## 1. Forward Question and Horizon
[Statement of the forward question; time horizon; key uncertainties.]

## 2. Scenario Set with Probability Bands
[For each scenario:]
- **Scenario <Name>** (probability range: <range>)
  - Narrative: <one-paragraph causal sequence>
  - Driving forces: <which critical uncertainties resolve to which axis position>
  - Leading indicators: <observable signals>
  - Strategic implications: <robust + scenario-dependent strategies>

[Wild card:]
- **Wild Card: <Name>** — outside the 2×2; probability low, impact high.
  - Narrative: <one paragraph>

## 3. Divergence Points
[Specific events or developments in the next [horizon/3] that distinguish which scenario is materializing:]
- **Divergence Point 1:** <observable event> — distinguishes <scenarios> by <month / quarter>.
- **Divergence Point 2:** ...
- **Divergence Point 3:** ...

## 4. Failure-Pathway Stress Test Findings
[For each scenario:]
- **Scenario <Name> worst-case failure pathway:**
  - Imagined failure narrative (past tense): <prose>
  - Failure modes activated: <list with class>
  - Leading indicators: <observable signals>
  - Pre-commitment mitigations: <list>

[For intervention candidates if user supplied them:]
- **Intervention <Name> pre-mortem:** <same structure>

## 5. Integrated Forward Architecture
- **Most-likely cluster:** <if scenarios cluster around a probability range; not a "most likely" designation>
- **Scenarios with high impact and non-trivial probability:** <list with reasoning>
- **Scenarios where coherent narrative meets catastrophic failure pathway:** <list — these are the overlooked-risk scenarios>
- **Highest-leverage monitoring priorities:** <signals that serve double duty as scenario-distinguishers AND failure-mode leading indicators>
- **Recommended preparation posture:** <robust strategies + contingent strategies tied to specific divergence-point observations>

## 6. Constructive-Future Gap-Flag (Mandatory)
**This analysis does NOT include backcasting (constructive-future stance).** The `backcasting` mode is gap-deferred per CR-6 (Phase 2 architectural decision). WFA composes around its absence by anchoring scenario-planning (neutral-future), probabilistic-forecasting (probability-output), and pre-mortem-action (adversarial-future). The constructive-future stance — working backward from a desired future to identify the chain of events that would produce it — is not substituted in this analysis. Consumers requiring constructive-future framing should compose WFA with downstream goal-articulation work or with the eventual `backcasting` mode when built.

## 7. Residual Uncertainties
[Things this analysis does not resolve; what would change the analysis:]
- <uncertainty>
- <uncertainty>
- <empirical question whose answer would materially shift the architecture>

## 8. Confidence Map
| Finding | Confidence | Reason |
|---------|------------|--------|
| Probability band for Scenario A | high / medium / low | <base-rate quality, reference class confidence> |
| Divergence Point 2 distinguishability | ... | <how observable the signal is> |
| Pre-mortem failure mode F3 leading indicator | ... | <signal precision> |
| Wild card scenario probability | ... | <by definition low confidence — name the structural reason> |
```

## WORKED EXAMPLE WALKTHROUGH

**Opening prompt (user):** *"What does the agent ecosystem look like in 5 years? I keep getting fragmentary takes — labs racing to capability, regulators racing to governance, infra costs unclear. I want a real architecture I could use to plan a multi-year product strategy."*

**Stage 1 output (scenario-planning, full):**
- Focal question: "What is the dominant agent ecosystem structure in 2031?"
- Time horizon: 5 years.
- Driving forces:
  - Predetermined: rising compute investment ($X billion across labs); growing developer interest; persistent capability scaling within current paradigms.
  - Critical uncertainties: regulatory regime (laissez-faire vs. licensing-required), capability ceiling (continuing capability gains vs. plateau on current methods).
- Axes:
  - X-axis: Regulatory regime — low: laissez-faire / high: licensing-required.
  - Y-axis: Capability trajectory — low: plateau on current methods / high: continued capability gains.
  - Independence rationale: regulatory choice depends on political coalitions and incident-driven public reaction; capability trajectory depends on methods research, scaling, and data availability — different causal mechanisms with no historical correlation in software regulation vs. capability progress (>40 chars).
- Scenarios:
  - TR (high reg + high capability): "Licensed Ecosystem" — incumbents licensed, fast capability progress, high barrier to entry, agent infrastructure consolidated under top 5 firms.
  - TL (low reg + high capability): "Open Cambrian" — fast capability progress, low regulatory barrier, exuberant fragmentation across thousands of agent products, quality variance high.
  - BR (high reg + plateau): "Bureaucratic Stasis" — capability gains slow, regulation locks in current architectures, agent ecosystem ossifies around licensed incumbents.
  - BL (low reg + plateau): "Diffusion at Scale" — capability gains slow, no regulatory barrier, agent products spread to existing software workflows but no transformative leap.
- Wild card: "Capability cliff event" — major incident (jailbreak, misuse, failure mode) triggers emergency global regulation within 18 months, jumping regulatory axis to licensing-required regardless of capability trajectory.
- Strategic implications:
  - Robust strategies: investment in agent reliability tooling (valuable in all four scenarios).
  - Scenario-dependent: bet-on-licensing (Bureaucratic Stasis path), bet-on-fragmentation (Open Cambrian path).

**Stage 2 output (probabilistic-forecasting, full):**
- Per scenario:
  - Licensed Ecosystem (TR): resolution criteria = top 5 firms account for >70% of agent inference compute; reference class = past licensed-tech regimes (telecom, broadcasting); base rate of "concentrated incumbents" 5 years post-regulation: ~40% for analogous tech transitions; inside-view drivers (positive: incumbent infrastructure advantage; negative: open-source momentum) → adjustment net ~+5pp; estimate 0.30-0.45; leading indicators: licensing legislation introduced in EU/US within 18 months, top-5 lobbying spend doubles.
  - Open Cambrian (TL): base rate of "fragmented ecosystem" post-tech-revolution (early web, app stores) ~35%; inside-view drivers shift +5pp; estimate 0.25-0.45.
  - Bureaucratic Stasis (BR): base rate of "regulation + plateau" ~15% (rare combination); inside-view drivers (current methods may be approaching limits) shift +5pp; estimate 0.10-0.25.
  - Diffusion at Scale (BL): base rate of "tech diffusion without leap" ~30%; inside-view drivers neutral; estimate 0.20-0.35.
- Cross-scenario outcome forecasts:
  - "Agent products integrated into >50% of enterprise software workflows by 2031" — probability range 0.55-0.75; depends on Open Cambrian or Diffusion at Scale.
  - "Major agent-driven incident triggering emergency regulation" — probability range 0.20-0.35; activates wild card.

**Synthesis Stage 1 (scenario-probability overlay):**
- Scenarios paired with probability bands:
  - Licensed Ecosystem: 0.30-0.45 (leading band).
  - Open Cambrian: 0.25-0.45.
  - Bureaucratic Stasis: 0.10-0.25.
  - Diffusion at Scale: 0.20-0.35.
- Coherence check: all scenarios cohere with their probability bands; no internal tensions.
- Divergence points:
  - 6-12 months: EU AI Act enforcement actions vs. light-touch — distinguishes licensing-required vs. laissez-faire.
  - 12-18 months: capability benchmarks (whether published frontier model performance plateaus or continues exponential) — distinguishes capability axis.
  - 18-24 months: market structure of agent inference — concentration ratio of top-5 inference compute share.
- Note: probability bands cluster — Licensed Ecosystem and Open Cambrian both 0.30+. The framework refuses to designate one "most likely"; both are equally plausible and distinguished by divergence points to monitor.

**Stage 3 output (pre-mortem-action, full):**
- Per scenario worst-case pre-mortems:
  - Licensed Ecosystem failure: "It's 2031; licensing was implemented but compliance burden squashed innovation rather than just gating it; agent capability advanced overseas in unlicensed jurisdictions; US/EU lost competitive position." Failure mode F1 (assumption): assumed licensing would be calibrated; was actually punitive. Leading indicator: enforcement actions against research-stage models in first 12 months of regime.
  - Open Cambrian failure: "It's 2031; fragmented ecosystem produced repeated catastrophic incidents (bio agents, financial fraud at scale); public backlash triggered draconian retroactive regulation worse than Licensed Ecosystem would have been; many agent businesses shut down overnight." Failure mode F2 (interaction): assumed market would self-regulate; correlated incidents overwhelmed self-regulation capacity.
  - Bureaucratic Stasis failure: "It's 2031; capability plateaued in mainstream paradigms but breakthrough emerged in unlicensed-jurisdiction research; incumbents discovered capability arbitrage too late." Failure mode F3 (context-shift).
  - Diffusion at Scale failure: "It's 2031; agent diffusion proceeded but value capture concentrated in software incumbents that had distribution; agent-native firms struggled despite technical capability." Failure mode F4 (motivational): assumed technical capability was decisive; was actually distribution.

**Synthesis Stage 2 (failure-pathway stress test):**
- Open Cambrian's F2 (catastrophic-incident → backlash → draconian regulation) is the highest-impact failure pathway across the architecture; it is also the trigger for the wild-card scenario from Stage 1 (capability cliff event). The wild card is structurally a failure mode of Open Cambrian, not an independent scenario.
- Divergence-points-serving-double-duty:
  - "EU AI Act enforcement actions in first 12 months" distinguishes licensing-required vs. laissez-faire AND is leading indicator for F1 (Licensed Ecosystem failure).
  - "Number of agent-driven incidents in 2026-2027 exceeding $X damage" distinguishes Open Cambrian vs. Bureaucratic Stasis AND is leading indicator for F2 (Open Cambrian failure → wild card).
- Highest-leverage signals:
  - Frontier model capability benchmarks (distinguishes capability axis + leads F3/F4).
  - Enforcement intensity in first 18 months of AI Act (distinguishes regulatory axis + leads F1).
  - Cumulative agent-driven incident damage in 2026-2027 (distinguishes Open Cambrian survival + leads F2).

**Synthesis Stage 3 (integrated future architecture):**

[Final Decision Architecture document follows the OUTPUT CONTRACT template above. Key claims that no single component could have produced:]
- The wild card from Stage 1 is structurally a failure pathway of one of the matrix scenarios (Open Cambrian's F2), not an independent fifth scenario — Stage 3's pre-mortem revealed this; Stage 1's wild-card framing did not.
- Open Cambrian and Licensed Ecosystem have overlapping probability bands but radically different preparation postures; the architecture's recommendation is to invest in agent reliability tooling (robust across both) and to monitor the divergence points that distinguish them, rather than to bet on either.
- Bureaucratic Stasis, despite being the lowest-probability scenario, has the most asymmetric preparation cost: easy to prepare for, expensive to be caught unprepared in. The integrated architecture surfaces this; the probability formalism alone would have de-prioritized.

Constructive-future gap-flag: the analysis tells the user what futures are plausible and how to monitor for them; it does NOT tell the user what desired future to work backward from. If the user wants to choose a target future and reverse-engineer the path, that is backcasting work, currently gap-deferred per CR-6.

## CAVEATS AND OPEN DEBATES

**Composition limit — backcasting deferred.** The mode-spec explicitly defers backcasting per CR-6. This framework documents the deferral handling: the constructive-future-gap-flag section is mandatory and visible (not buried). Consumers who require constructive-future analysis should compose WFA with downstream goal-articulation work, or wait for the eventual `backcasting` mode build.

**No scenario "most likely" designation.** Even when probability bands cluster (e.g., two scenarios both at 0.30+), the framework refuses to designate one as most likely. This preserves scenario-planning's anti-prediction stance and forces the user to monitor divergence points rather than commit prematurely.

**Long-horizon humility.** Probability bands beyond 5-year horizons are intrinsically wider than they look in the artifact. Consumers should treat 0.30-0.45 ranges as "non-trivial probability with substantial uncertainty about the range itself" rather than as if 0.40 were a calibrated central estimate.

**When to escalate sideways:** if during execution the question turns out to be about a specific plan's failure pathways (rather than open future exploration), route to `pre-mortem-action` directly. WFA's molecular pass is wasted on plan-bounded analysis.

## QUALITY GATES (overall)

- All three components ran (or were flagged as proceeded-with-gap with reason).
- All three synthesis stages integrated rather than concatenated.
- Pre-mortem stress-test ran against leading scenarios.
- Constructive-future gap-flag visible and explicit (not buried).
- Divergence points serve double duty as scenario-distinguishers and failure-mode leading indicators where possible.
- Confidence map populated per finding.
- The four critical questions of `wicked-future` (trend-extrapolation-bias, silo-aggregation, pre-mortem-omission, silent-gap) are addressed.
- Forecast-claims include at least one that no single component could have produced.

## RELATED MODES AND CROSS-REFERENCES

- **Paired mode file:** `Modes/wicked-future.md`
- **Component mode files:**
  - `Modes/scenario-planning.md` (Stage 1)
  - `Modes/probabilistic-forecasting.md` (Stage 2)
  - `Modes/pre-mortem-action.md` (Stage 3)
- **Deferred component:** `backcasting` (gap-deferred per CR-6) — constructive-future stance not substituted.
- **Sibling Wave 4 modes (related operations):** `Modes/decision-architecture.md` (T3 — uses pre-mortem-action as Stage 4), `Modes/wicked-problems.md` (T2 — uses scenario-planning at Stage 3) — share the multi-future treatment.
- **Territory framework:** `Framework — Future Exploration.md`
- **Lens dependencies:** klein-pre-mortem (required), shell-scenario-method (via scenario-planning), tetlock-superforecasting (required via probabilistic-forecasting), taleb-extremistan-mediocristan (optional, when discontinuity scenarios in play), kahneman-tversky-bias-catalog (foundational), knightian-risk-uncertainty-ambiguity (foundational).

*End of Wicked-Future Analysis Framework.*
