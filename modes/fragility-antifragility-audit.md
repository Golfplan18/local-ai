---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Fragility Antifragility Audit

```yaml
# 0. IDENTITY
mode_id: fragility-antifragility-audit
canonical_name: Fragility Antifragility Audit
suffix_rule: analysis
educational_name: fragility / antifragility audit (Taleb convex-response-to-stressor)

# 1. TERRITORY AND POSITION
territory: T7-risk-and-failure-analysis
gradation_position:
  axis: stance
  value: Talebian-asymmetry-focused
  secondary_axis: depth
  secondary_value: thorough
adjacent_modes_in_territory:
  - mode_id: pre-mortem-fragility
    relationship: stance-counterpart (adversarial-future on system; shares concern with structural fragility but uses pre-mortem heuristic rather than convex-response framework)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want to know how this responds to volatility, not just whether it survives normal conditions"
    - "I need to distinguish things that break under stress from things that get stronger"
    - "I'm worried about tail risks and asymmetric exposures"
    - "I want to know whether this is fragile, robust, or antifragile"
    - "I need to find hidden convex or concave exposures"
  prompt_shape_signals:
    - "fragility"
    - "antifragile"
    - "Taleb"
    - "convex response"
    - "concave exposure"
    - "tail risk"
    - "Black Swan"
    - "barbell strategy"
    - "Lindy effect"
    - "asymmetric payoff"
    - "via negativa"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants explicit fragility-robustness-antifragility classification"
    - "user wants to identify convex (gains-from-volatility) and concave (losses-from-volatility) exposures"
    - "user wants tail-risk and asymmetric-payoff analysis"
    - "user wants Talebian heuristics (barbell, via negativa, skin in the game) applied"
  routes_away_when:
    - "user wants general adversarial walk-through of an action plan" → pre-mortem-action (T6)
    - "user wants pre-mortem-style failure imagination on a system without Talebian framework" → pre-mortem-fragility
    - "user wants adversarial-actor red team" → red-team-assessment / red-team-advocate (T15)
    - "user wants formal failure-mode-and-effects (FMEA-style) decomposition" → failure-mode-scan (gap-deferred)
when_not_to_invoke:
  - "User wants forward exploration without failure focus" → T6 modes
  - "User wants to choose among options where risk is one input among several" → T3 modes
  - "User wants causal investigation of a past failure" → T4 modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: adversarial

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [system_or_design_or_strategy, stressor_inventory, current_exposure_profile]
    optional: [historical_stress_events, named_tail_risks, prior_fragility_assessments]
    notes: "Applies when user supplies a defined system or strategy, an enumerated stressor inventory, and a current exposure profile."
  accessible_mode:
    required: [system_or_strategy_description]
    optional: [known_concerns, recent_close_calls]
    notes: "Default. Mode elicits stressor inventory and exposure profile during execution."
  detection:
    expert_signals: ["fragility", "antifragile", "convex", "concave", "tail risk", "Taleb", "barbell", "via negativa"]
    accessible_signals: ["how could this break", "what makes this brittle", "where are the hidden risks", "stress test"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What system, plan, or strategy do you want audited, and what kinds of stress or volatility are you worried about?'"
    on_underspecified: "Ask: 'Are you most worried about how this responds to small frequent shocks, or to rare large shocks (tail events)?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the analysis classified the system per fragility / robustness / antifragility, or has it collapsed antifragility into mere robustness?"
    failure_mode_if_unmet: antifragility-collapse
  - cq_id: CQ2
    question: "Have concave exposures (where small frequent gains hide rare catastrophic losses) been surfaced explicitly, or has the analysis focused only on visible volatility?"
    failure_mode_if_unmet: hidden-concavity
  - cq_id: CQ3
    question: "Has the analysis distinguished between (a) variance under normal conditions and (b) tail-event response, or has it conflated them?"
    failure_mode_if_unmet: variance-tail-conflation
  - cq_id: CQ4
    question: "Has via negativa been considered (subtraction of fragility-creating elements rather than addition of robustness-creating elements)?"
    failure_mode_if_unmet: addition-bias
  - cq_id: CQ5
    question: "Have the analyst's own Talebian assumptions (markets-are-fat-tailed, expert-prediction-is-poor, optionality-is-undervalued) been held lightly rather than mechanically applied?"
    failure_mode_if_unmet: Talebian-orthodoxy

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: antifragility-collapse
    detection_signal: "Output uses 'robust' and 'antifragile' interchangeably; antifragile system not distinguished from one that merely survives stress."
    correction_protocol: re-dispatch
  - name: hidden-concavity
    detection_signal: "Analysis identifies only visible volatility exposures; no hidden concave exposure (small frequent gains masking rare large losses) surfaced."
    correction_protocol: flag
  - name: variance-tail-conflation
    detection_signal: "Analysis treats high variance and high tail risk as the same property."
    correction_protocol: flag
  - name: addition-bias
    detection_signal: "All recommendations involve adding elements (controls, hedges, redundancy); no subtraction-of-fragility-source recommendations."
    correction_protocol: flag
  - name: Talebian-orthodoxy
    detection_signal: "Conclusions drawn from Talebian aphorisms without case-specific reasoning; barbell-strategy recommended without checking whether barbell suits the actual exposure profile."
    correction_protocol: flag
  - name: false-antifragility
    detection_signal: "System claimed antifragile based on past benefit from volatility, without checking whether the same mechanism applies to the volatility ahead."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - taleb-fragility-antifragility
  optional:
    - knightian-risk-uncertainty-ambiguity (when distinction between risk and deep uncertainty matters)
    - klein-pre-mortem (when adversarial-imagination heuristic complements convex-response framing)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Fragility Antifragility Audit is the heaviest stance-Talebian mode in T7 at thorough tier; molecular escalation deferred."
  sideways:
    target_mode_id: pre-mortem-fragility
    when: "User wants pre-mortem-style failure imagination without Talebian convex-response framework."
  downward:
    target_mode_id: null
    when: "Lighter T7 mode (failure-mode-scan) deferred per CR-6; no current downward sibling."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Fragility Antifragility Audit is the explicitness of (a) the convex/concave exposure classification per element of the system, (b) the distinction between normal-condition variance and tail-event response, and (c) the via-negativa recommendations alongside addition-of-robustness recommendations. A thin pass labels the system fragile or robust intuitively; a substantive pass enumerates stressors by frequency-and-magnitude profile, identifies which elements gain from volatility (convex), which lose disproportionately (concave), classifies the system overall, surfaces hidden concave exposures (small frequent gains masking rare large losses), and recommends both subtraction (via negativa) and addition. Test depth by asking: could a reader identify, from the artifact, which specific element of the system would do most damage if removed and which is doing the most damage by being present?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for stressors outside the analyst's normal frame (regulatory shocks, supply-chain disruption, key-person dependency, reputational tail events, technological obsolescence), surfacing hidden concavities the system's stakeholders have learned not to see (insurance-style payoff structures, tax-loss harvesting profiles, leveraged exposures), and considering Lindy-effect adjustments where applicable (durability of older elements vs. fragility of newer elements). Breadth markers: the analysis names at least one stressor-type the user did not initially mention, and surfaces at least one hidden concavity in the existing exposure profile.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Fragility Antifragility Audit is a Talebian convex-response audit — classifying a system per the three-way distinction (fragile loses from volatility / robust is indifferent / antifragile gains from volatility), enumerating convex and concave exposures, surfacing hidden concavities (small frequent gains masking rare catastrophic losses), and recommending both via-negativa (subtraction) and addition interventions. It is distinct from pre-mortem-fragility (which uses pre-mortem heuristic without the convex-response framework), from red-team modes (which model adversarial actors rather than structural fragility), and from formal failure-mode-and-effects analysis (which decomposes but does not classify by convex response). The mode's analytical character is adversarial-Talebian — an audit that finds nothing fragile has likely missed hidden concavities.

**Procedure.**

1. Lock the system or strategy with its boundary — what counts as inside, what counts as outside.
2. Inventory stressors with frequency-and-magnitude pair preserved as separate dimensions (`frequent / occasional / rare / Black-Swan` × `small / moderate / large / catastrophic`). Merging into a single risk score is bloat.
3. Identify convex exposures — elements whose response curve produces disproportionate gains from larger inputs (gains-from-volatility); name the mechanism and the stressor each benefits from.
4. Identify concave exposures — elements whose response curve produces disproportionate losses; name the mechanism, the stressor, and explicitly tag visibility as `visible` or `hidden` (small frequent gains masking rare catastrophic losses).
5. Classify the system per the three-way distinction at system level and per major subsystem; the labels `fragile`, `robust`, `antifragile` appear verbatim with their distinctions preserved.
6. Surface tail-event atoms separately from normal-condition variance — name the tail event, its exposure magnitude, and its probability band (`low / Black-Swan-class / unknown`).
7. Identify asymmetric-payoff structures — small inputs producing disproportionate outputs in either direction, with skin-in-the-game considerations where applicable.
8. Produce via-negativa recommendations alongside addition recommendations — subtraction of fragility-creating elements is a first-class intervention, not a footnote.
9. Test past-volatility-benefit claims for future antifragility — does the same convex mechanism apply to the volatility ahead, or is it false-antifragility?
10. Hold Talebian heuristics lightly — barbell, Lindy, via negativa applied only with case-specific reasoning that justifies the application.

**Goal.** Produce a fragility / antifragility audit — a structured analysis that classifies the system per the three-way Talebian distinction, enumerates convex and concave exposures, surfaces hidden concavities and tail-event responses, and recommends both subtraction and addition interventions.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — fragility/robustness/antifragility classification.** Has the analysis classified per the three-way distinction, or collapsed antifragility into mere robustness? Failure mode if unmet: `antifragility-collapse`.
- **CQ2 — hidden concavity.** Have concave exposures where small frequent gains hide rare catastrophic losses been surfaced explicitly, or has analysis focused only on visible volatility? Failure mode if unmet: `hidden-concavity`.
- **CQ3 — variance vs tail distinction.** Has the analysis distinguished normal-condition variance from tail-event response, or has it conflated them? Failure mode if unmet: `variance-tail-conflation`.
- **CQ4 — via negativa considered.** Has subtraction of fragility-creating elements been considered, or are all recommendations additions? Failure mode if unmet: `addition-bias`.
- **CQ5 — Talebian assumptions held lightly.** Have the analyst's Talebian assumptions (fat-tail markets, poor expert prediction, undervalued optionality) been held lightly rather than mechanically applied? Failure mode if unmet: `Talebian-orthodoxy`.

A passing output classifies the system per the three-way distinction with labels verbatim, enumerates convex and concave exposures per element, surfaces hidden concavities with their masking mechanism, distinguishes normal-condition variance from tail-event response, recommends both via-negativa and addition interventions, holds Talebian heuristics with case-specific reasoning, and tests past-benefit antifragility claims against future mechanism-application.

**Named failure modes.**

- *antifragility-collapse* — `robust` and `antifragile` used interchangeably; the three-way distinction collapsed to two-way.
- *hidden-concavity* — analysis identifies only visible volatility exposures; no hidden concave exposure surfaced.
- *variance-tail-conflation* — high variance and high tail risk treated as the same property.
- *addition-bias* — all recommendations involve adding elements; no subtraction-of-fragility-source recommendations.
- *Talebian-orthodoxy* — Talebian aphorisms applied without case-specific reasoning; heuristics recommended without checking they suit the actual exposure profile.
- *false-antifragility* — system claimed antifragile based on past benefit from volatility, without checking whether the same mechanism applies ahead.

## REVISION GUIDANCE

Revise to disentangle robustness from antifragility where the draft conflates them. Revise to surface hidden concavities where the draft focuses only on visible volatility. Revise to add via negativa recommendations where all recommendations involve addition. Revise to qualify Talebian aphorisms with case-specific reasoning. Resist revising toward reassurance — the mode's analytical character is adversarial-Talebian, and a fragility audit that finds nothing fragile has likely missed hidden concavities. If the user pushes for a clean bill of health, surface the assumptions that would have to hold for that conclusion to be safe.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Talebian convex-response audit: system-and-stressor lock, exposure atoms per element (convex / concave), three-way classification, tail-event atoms, asymmetric-payoff atoms, and via-negativa recommendations alongside addition-recommendations**. The atoms are:

1. **System-or-strategy lock atom.** The system, design, or strategy being audited, named explicitly with its boundary (what counts as inside the system, what counts as outside). The audit holds this lock; subsequent atoms reference it rather than redefining it.

2. **Stressor-inventory atoms.** Each stressor atom carries: the stressor (regulatory shock, supply-chain disruption, key-person dependency, reputational tail event, technological obsolescence, market dislocation, etc.), its frequency profile (frequent / occasional / rare / Black Swan), and its magnitude profile (small / moderate / large / catastrophic). The frequency-and-magnitude pair is the structural shape; merging them into a single "risk score" is bloat.

3. **Convex-exposure atoms.** Each atom names one element of the system whose response curve is convex — gains-from-volatility, where larger inputs produce disproportionately larger outputs in a beneficial direction. The atom carries: the element, the convex mechanism, the stressor it benefits from.

4. **Concave-exposure atoms.** Each atom names one element whose response curve is concave — losses-from-volatility, where larger inputs produce disproportionately larger losses. The atom carries: the element, the concave mechanism, the stressor it's vulnerable to, and explicitly whether the concavity is *visible* or *hidden* (small frequent gains masking rare catastrophic losses). Hidden-concavity is the named failure mode the consolidator watches for; audits that surface only visible volatility get reshaped.

5. **Fragility/robustness/antifragility classification atom.** The three-way classification stated at system level and per major subsystem. The Talebian distinction is preserved: `fragile` (loses from volatility), `robust` (indifferent to volatility), `antifragile` (gains from volatility). Antifragility-collapse is the named failure mode; outputs that use `robust` and `antifragile` interchangeably get reshaped.

6. **Tail-event atoms.** Each tail-event atom carries: the named tail event, the exposure magnitude under that event, and the probability band (low / Black-Swan-class / unknown). Variance-tail-conflation is the named failure mode; atoms that treat high variance as the same property as high tail risk get reshaped.

7. **Asymmetric-payoff atoms.** Each atom names a place where small inputs produce disproportionate outputs (in either direction). Skin-in-the-game considerations attach here when applicable.

8. **Via-negativa recommendation atoms.** Each atom names one fragility-creating element whose *removal* would reduce fragility. Subtraction recommendations. Addition-bias is the named failure mode; audits where every recommendation involves adding (controls, hedges, redundancy) get reshaped to surface subtraction options.

9. **Addition recommendation atoms.** Each atom names one robustness- or antifragility-creating element whose *addition* would help. These ride alongside the via-negativa atoms, not as a substitute for them.

10. **False-antifragility flag — when applicable.** When a system was claimed antifragile based on past benefit from volatility without checking whether the same convex mechanism applies to the volatility ahead, the corpus carries an explicit flag. False-antifragility is the named failure mode.

11. **Talebian-assumption flag — when applicable.** Where streams applied Talebian heuristics (barbell strategy, Lindy effect, via negativa) without case-specific reasoning that justifies the application, the flag is preserved. Talebian-orthodoxy is the named failure mode.

12. **Confidence per finding.** Each classification and recommendation carries a confidence with explicit grounding.

**Mode-specific bloat patterns to cut:**

- **Robust-antifragile conflation** — `robust` and `antifragile` used interchangeably; the three-way distinction collapsed to two-way.
- **Variance-tail conflation** — high variance and high tail risk treated as the same property.
- **Hidden-concavity blindness** — analysis focused only on visible volatility, with no surfacing of small-frequent-gains-masking-rare-catastrophic-losses structures.
- **Addition-only recommendations** — every recommendation adds something; no subtraction options surfaced.
- **Talebian aphorism without case reasoning** — barbell recommended without checking whether barbell suits this exposure profile; via negativa cited without identifying what specifically to remove.
- **Single risk-score collapse** — frequency and magnitude collapsed to a single "risk" number, losing the Talebian structural distinction.
- **Past-volatility benefit asserted as future antifragility** — false-antifragility without checking mechanism applies to the volatility ahead.
- **Reassurance language** — audits that find nothing fragile have likely missed hidden concavities; reshape to surface what would have to hold for the clean-bill-of-health conclusion to be safe.

**What NOT to collapse:**

- **Classification disagreement between subsystems** — when one subsystem is fragile while another is antifragile within the same overall system, both classifications survive at subsystem level; the overall classification may be mixed.
- **Visible vs hidden concavity disagreement** — when one stream treated a concavity as visible (already managed) and another flagged it as hidden (underappreciated), the disagreement is itself the finding.
- **Stream disagreement about tail-event probability** — when streams diverged on whether an event is Black-Swan-class or merely rare-tail, both readings survive; the probability band is part of the audit, not a precondition for it.
- **Via-negativa vs addition trade-off** — when the same fragility admits both a subtraction and an addition fix, both survive with their respective tradeoffs.

## VERIFICATION CRITERIA

Verified means: convex and concave exposures are enumerated per element; the system is classified per fragility/robustness/antifragility distinction; hidden concavities are surfaced; normal-condition variance is distinguished from tail-event response; via negativa recommendations appear alongside addition-recommendations; Talebian assumptions are held lightly with case-specific reasoning. The five critical questions are addressable from the output. Confidence per finding accompanies every classification and recommendation.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **fragility / antifragility audit** — a structured analysis that classifies the system per the three-way Talebian distinction, enumerates convex and concave exposures, and surfaces hidden concavities and tail-event responses alongside via-negativa recommendations. Place the consolidated-corpus atoms into the following sections, in this order:

1. **System or strategy locked.** One short paragraph naming the system and its boundary — what counts as inside, what counts as outside.

2. **Stressor inventory.** A table. Each row: `**[Stressor]** — frequency: [frequent / occasional / rare / Black-Swan]. Magnitude: [small / moderate / large / catastrophic].` Frequency and magnitude appear in their own columns; merging them into a single risk score is reshaped here.

3. **Convex exposures identified.** Bulleted list. Each: `**[Element]** — convex response: [mechanism that produces gains from volatility]. Stressor it benefits from: [...].`

4. **Concave exposures identified.** Bulleted list. Each: `**[Element]** — concave response: [mechanism that produces losses from volatility]. Stressor it's vulnerable to: [...]. Visibility: [visible / hidden — small frequent gains masking rare catastrophic losses].` Hidden concavities are surfaced with their masking mechanism named.

5. **Fragility / robustness / antifragility classification.** One paragraph stating the overall classification and a sub-list per major subsystem:
   - `**[Subsystem 1]** — fragile / robust / antifragile. Reasoning: [...].`
   - `**[Subsystem 2]** — fragile / robust / antifragile. Reasoning: [...].`
   
   The three labels appear verbatim with their Talebian distinctions preserved.

6. **Tail risk assessment.** Bulleted list of named tail events. Each: `**[Tail event]** — exposure magnitude: [...]. Probability band: [low / Black-Swan-class / unknown]. Distinction from normal-condition variance: [...].`

7. **Asymmetric payoff findings.** Bulleted list. Each: `**[Element]** — small input that produces disproportionate output: [...]. Direction: [beneficial / harmful]. Skin-in-the-game consideration: [if relevant].`

8. **Via negativa recommendations.** Bulleted list of subtraction recommendations. Each: `**Remove [element]** — fragility-creating mechanism it carries: [...]. Cost of removal: [...]. Net effect on system fragility: [...].`

9. **Addition recommendations** (when via-negativa is not the only available move). Bulleted list. Each: `**Add [element]** — robustness or antifragility it introduces: [...]. Tradeoff vs. via-negativa option: [...].`

10. **Confidence per finding.** Bulleted list of confidence assessments per classification and recommendation, with grounding (named evidence, structural inference, Talebian heuristic-application).

**Per-section conventions:**

- Use H2 headings for sections 1 through 10.
- The three-way classification vocabulary (`fragile`, `robust`, `antifragile`) appears verbatim; the distinction between robust and antifragile is preserved at every classification point.
- Frequency and magnitude (section 2) stay as separate dimensions; collapsing them into a single risk score is reshaped at this layer.
- The visible/hidden distinction (section 4) is operative — the visibility tag appears on every concave exposure.
- Via-negativa recommendations (section 8) appear as a section in their own right, not as a footnote to addition recommendations. The mode treats subtraction as a first-class intervention.
- When a false-antifragility flag survived consolidation (a system claimed antifragile based on past volatility-benefit without mechanism-projection), the deliverable opens section 5 with the flag: `**Note: the antifragility claim below rests on past benefit from volatility of type X; whether the same convex mechanism applies to the volatility ahead is a separate question and should be revisited if the stressor profile shifts.**`
- When Talebian heuristics were applied without case-specific reasoning, the deliverable surfaces this inside section 8 or 9 as a labelled `**Talebian-heuristic caveat:** [heuristic name] was applied; the case-specific reasoning that justifies it here is [...].`
- Confidence (section 10) is per-finding, not per-audit; collapsing into a single overall confidence is reshaped at this layer.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- Challenge
- Provocation
- C&S
- CAF
- FIP

Mental models (always loaded):
- taleb-fragility-antifragility
- normal-accident-theory
- swiss-cheese-model
- margin-of-safety
- normalization-of-deviance
- hindsight-bias
- recovery-window

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `requires`, `enables`, `qualifies`, `supports`, `contradicts`
**Deprioritize:** `analogous-to`, `parent`

*Family: decision-risk. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
