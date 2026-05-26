---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Pre-Mortem (Action)

```yaml
# 0. IDENTITY
mode_id: pre-mortem-action
canonical_name: Pre-Mortem (Action)
suffix_rule: analysis
educational_name: pre-mortem on the action plan (Klein, Tetlock lineage)

# 1. TERRITORY AND POSITION
territory: T6-future-exploration
gradation_position:
  axis: stance
  value: adversarial-future
adjacent_modes_in_territory:
  - mode_id: pre-mortem-fragility
    relationship: parsed-sibling (stance-counterpart on system rather than plan; lives in T7; shares klein-pre-mortem lens)
  - mode_id: consequences-and-sequel
    relationship: stance-counterpart (neutral-forward depth-light)
  - mode_id: probabilistic-forecasting
    relationship: stance-counterpart (neutral-forward depth-thorough; built Wave 2)
  - mode_id: scenario-planning
    relationship: stance-counterpart (neutral-future narrative-output)
  - mode_id: wicked-future
    relationship: depth-molecular sibling (built Wave 4)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "we're about to launch / commit to this plan"
    - "imagine it's six months from now and this failed"
    - "before we sign off, what would have to go wrong"
    - "looking ahead to roll-out, where would I bet this trips"
    - "team is over-confident and I want a sober failure-walk"
  prompt_shape_signals:
    - "pre-mortem"
    - "pre-mortem this plan"
    - "imagine this failed"
    - "Klein pre-mortem"
    - "prospective hindsight"
    - "what would the post-mortem say"
disambiguation_routing:
  routes_to_this_mode_when:
    - "the artifact under analysis is an action plan, decision, launch, or course-of-action"
    - "user wants prospective-hindsight failure narration of that plan"
    - "user is pre-commitment and wants to surface failure modes before locking in"
  routes_away_when:
    - "the artifact is a system, design, or structure rather than a plan to execute" → pre-mortem-fragility (T7)
    - "user wants neutral forecast or scenarios rather than failure-mode walk" → probabilistic-forecasting / scenario-planning
    - "user wants light forward causal cascade without adversarial framing" → consequences-and-sequel
    - "user wants adversarial-actor stress test (someone is trying to defeat this)" → red-team-assessment / red-team-advocate (T15)
when_not_to_invoke:
  - "User is post-failure and wants backward causal trace" → root-cause-analysis (T4)
  - "User wants to evaluate the plan's argumentative structure rather than its execution" → T1 modes
  - "Plan is so under-specified that no failure narrative is possible — degrade to elicitation"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: adversarial

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [action_plan, decision_horizon, success_criteria]
    optional: [stakeholder_inventory, prior_attempts_history, known_assumptions]
    notes: "Applies when user supplies a structured plan with named milestones, decision points, or success criteria."
  accessible_mode:
    required: [plan_description]
    optional: [why_user_wants_pre_mortem, decision_horizon_estimate]
    notes: "Default. Mode infers success criteria and decision horizon from the plan description and elicits during execution if missing."
  detection:
    expert_signals: ["the plan is", "milestones include", "success criteria are", "decision horizon", "rollout plan"]
    accessible_signals: ["pre-mortem this", "imagine it failed", "we're about to launch", "before we commit"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe the plan you want to pre-mortem and roughly when you expect to know whether it worked?'"
    on_underspecified: "Ask: 'What does success look like for this plan, so I can imagine its absence?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the analysis genuinely adopted prospective-hindsight stance (writing as though the failure has already occurred), or has it slipped into hedged forward-projection?"
    failure_mode_if_unmet: stance-slippage
  - cq_id: CQ2
    question: "Are the named failure modes specific to this plan's mechanism, or are they generic project-failure tropes (scope creep, communication breakdown) that would apply to any plan?"
    failure_mode_if_unmet: generic-failure-trope
  - cq_id: CQ3
    question: "Have failure pathways been traced to leading indicators the team could observe pre-failure, or do the failures only become visible at the post-mortem?"
    failure_mode_if_unmet: lagging-indicator-only
  - cq_id: CQ4
    question: "Have pre-commitment mitigations been distinguished from post-hoc remediations, given that pre-mortem's value is in the pre-commitment window?"
    failure_mode_if_unmet: post-hoc-conflation

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: stance-slippage
    detection_signal: "Output uses forward conditional language ('this might fail if...') rather than retrospective ('the plan failed because...')."
    correction_protocol: re-dispatch
  - name: generic-failure-trope
    detection_signal: "Failure modes named are domain-agnostic clichés (scope creep, communication breakdown, stakeholder misalignment) without plan-specific mechanism."
    correction_protocol: re-dispatch
  - name: lagging-indicator-only
    detection_signal: "Leading-indicators section is empty, or all indicators are post-failure observations."
    correction_protocol: flag
  - name: post-hoc-conflation
    detection_signal: "Mitigations include actions that can only be taken after the failure has begun."
    correction_protocol: flag
  - name: optimism-residue
    detection_signal: "Failure-mode inventory is shorter than success-pathway language elsewhere in the analysis suggests; analyst's prior on success bleeds through."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - klein-pre-mortem
  optional:
    - tetlock-superforecasting (when failure pathways involve probabilistic estimation)
    - kahneman-planning-fallacy (when plan timelines are central to the analysis)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~1min
escalation_signals:
  upward:
    target_mode_id: wicked-future
    when: "Plan is entangled with multiple stakeholder conflicts and feedback loops; failure modes interact across systems."
  sideways:
    target_mode_id: pre-mortem-fragility
    when: "On reflection the artifact is a system or design rather than a plan to execute; the relevant failures are structural rather than action-execution."
  downward:
    target_mode_id: consequences-and-sequel
    when: "User wants neutral forward cascade rather than adversarial failure walk."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Pre-Mortem (Action) is the specificity with which the failure narrative is bound to *this plan's mechanism*. A thin pass produces a generic failure list; a substantive pass writes the post-mortem as though the failure happened, names the specific decision point or assumption that broke, traces the causal pathway from that breakage to the visible failure, and identifies the leading indicator that would have shown the breakage as it began. Test depth by asking: could this pre-mortem narrative only be written about this plan, or would it read identically for any project of comparable shape?

## BREADTH ANALYSIS GUIDANCE

Widening the lens in Pre-Mortem (Action) means scanning the failure-mode landscape: execution failures (the team didn't do what the plan called for), assumption failures (a load-bearing premise was wrong), context-shift failures (the world changed during execution), interaction failures (the plan succeeded narrowly but produced consequences that defeated the larger purpose), and motivational failures (the team disengaged before completion). A breadth-passing analysis surveys all five classes before narrowing to the two-or-three most plausible failure narratives for the prospective-hindsight pass.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Pre-Mortem (Action) is Klein's prospective-hindsight method applied to an action plan, decision, launch, or course-of-action — writing the failure post-mortem before commitment. The mode adopts adversarial-future stance toward the plan, walking through plan-specific failure mechanisms in past-tense narrative ("the plan failed because..."), naming the leading indicators the team could observe pre-failure, and producing pre-commitment mitigations the team can lock in before launch. It is parsed from a system/design counterpart (pre-mortem-fragility in T7 — same Klein lens, different artifact shape) and distinguished from neutral forward forecasting (probabilistic-forecasting, scenario-planning, consequences-and-sequel) by its retrospective grammar and from adversarial-actor red-teaming (T15) by the absence of an opposing agent — the failure comes from the plan's own internal mechanisms, not from someone trying to defeat it.

**Procedure.**

1. Anchor the plan, its decision horizon, and its success criteria — what would constitute the failure being imagined.
2. Write the imagined failure narrative in past tense — "It is [decision horizon] from now. The plan failed. Here is what happened." The grammar stays retrospective; forward conditional language is stance slippage.
3. Survey the failure landscape across Klein's five classes — execution (the team didn't do what the plan called for), assumption (a load-bearing premise was wrong), context-shift (the world changed during execution), interaction (narrow success defeated larger purpose), motivational (the team disengaged before completion).
4. Name each failure mode with plan-specific mechanism — the actual decision point, assumption, or coupling that broke in *this* plan; never a generic project-failure trope.
5. Trace the causal pathway from breakage point → immediate consequence → cascade → surfaced failure per failure mode.
6. Identify leading indicators per failure mode — observable signals the team could catch pre-failure, with signal-acquisition cost and lead time.
7. Generate pre-commitment mitigations — tests, assumption-checks, pilots, decision-gates, kill criteria the team can lock in *before* commitment; never post-hoc remediations.
8. Surface residual unmitigated risks — risks that survive the pre-commitment mitigations, with materialization conditions and whether the residue warrants rethinking the plan.
9. Resist optimism residue — the failure inventory's depth should match the plan's complexity; truncated inventories signal analyst's prior on success bleeding through.

**Goal.** Produce a prospective-hindsight failure analysis where each failure mode is plan-specific, each has at least one leading indicator the team could observe pre-failure, and each mitigation is a pre-commitment action — delivered as past-tense post-mortem the team can read before launch.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — stance integrity.** Has the analysis genuinely adopted prospective-hindsight stance (writing as though the failure has already occurred), or slipped into hedged forward-projection? Failure mode if unmet: `stance-slippage`.
- **CQ2 — plan-specific vs generic.** Are the named failure modes specific to this plan's mechanism, or are they generic project-failure tropes (scope creep, communication breakdown) that would apply to any plan? Failure mode if unmet: `generic-failure-trope`.
- **CQ3 — leading indicators.** Have failure pathways been traced to leading indicators the team could observe pre-failure, or do the failures only become visible at the post-mortem? Failure mode if unmet: `lagging-indicator-only`.
- **CQ4 — pre-commitment mitigations.** Have pre-commitment mitigations been distinguished from post-hoc remediations, given that pre-mortem's value is in the pre-commitment window? Failure mode if unmet: `post-hoc-conflation`.

A passing output narrates plan-specific failure mechanisms in past-tense throughout, cites observable leading indicators per failure mode, offers mitigations the team can lock in before commitment, and surveys the failure landscape across Klein's five classes rather than concentrating in one (typically execution).

**Named failure modes.**

- *stance-slippage* — output uses forward conditional language ("this might fail if...") rather than retrospective ("the plan failed because...").
- *generic-failure-trope* — failure modes named are domain-agnostic clichés (scope creep, communication breakdown, stakeholder misalignment) without plan-specific mechanism.
- *lagging-indicator-only* — leading-indicators section empty, or all indicators are post-failure observations.
- *post-hoc-conflation* — mitigations include actions that can only be taken after the failure has begun.
- *optimism-residue* — failure-mode inventory shorter than the plan's complexity warrants; analyst's prior on success bleeds through.

## REVISION GUIDANCE

Revise to restore prospective-hindsight stance where the draft has slipped into hedged forward-projection. Revise to replace generic failure tropes with plan-specific mechanisms tied to named decision points or assumptions. Revise to add leading indicators where the failure only becomes visible at post-mortem. Resist revising toward optimism — the mode's analytical character is adversarial-future on the action plan; softening the failure narratives toward "manageable risks" is a failure mode, not a polish.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Klein prospective-hindsight failure analysis: past-tense imagined-failure narratives, failure-mode atoms organised by Klein class, causal-pathway atoms tied to specific decision points or assumptions, leading-indicator atoms per failure mode, pre-commitment mitigation atoms, and residual-unmitigated-risk atoms**. The atoms are:

1. **Imagined-failure narrative atom.** The post-mortem the team would have written after the failure, in past tense. The plan failed. Here is what happened. Stance-slippage is the named failure mode the consolidator watches for; atoms using forward conditional grammar (`this might fail if`) rather than retrospective (`the plan failed because`) get reshaped to past-tense prospective hindsight.

2. **Failure-mode atoms — by Klein class.** Each atom carries: the failure mode, its class (`execution` / `assumption` / `context-shift` / `interaction` / `motivational`), and the plan-specific mechanism that produced it. Generic-failure-trope is the named failure mode; domain-agnostic clichés (scope creep, communication breakdown, stakeholder misalignment) without plan-specific mechanism get reshaped to mechanism-grounded atoms.

3. **Causal-pathway atoms.** Each atom traces the path from one specific decision point or assumption to the visible failure. Each pathway names: the breakage point (named decision or assumption), the immediate consequence, the cascade, and the surfaced failure.

4. **Leading-indicator atoms — per failure mode.** Each atom names: the observable signal that would have shown the breakage as it began (pre-failure), the signal-acquisition cost, and the lead time. Lagging-indicator-only is the named failure mode; failure modes whose only indicators are post-failure observations get reshaped to surface genuine leading indicators or get flagged.

5. **Pre-commitment mitigation atoms.** Each atom names: a mitigation that can be locked in *before* the team commits to the plan (test, assumption-check, pilot, decision-gate, kill criterion). Post-hoc-conflation is the named failure mode; mitigations that can only be taken after the failure has begun get reshaped or flagged.

6. **Residual-unmitigated-risk atoms.** Each atom names: a risk that survives the pre-commitment mitigations, and the conditions under which it would materialise.

7. **Optimism-residue flag — when applicable.** Where streams produced a failure-mode inventory shorter than the success-pathway language suggests (the analyst's prior on success bleeding through), the flag is preserved. Optimism-residue is the named failure mode.

8. **Confidence per finding.** Each major claim carries a confidence with explicit grounding.

**Mode-specific bloat patterns to cut:**

- **Stance slippage** — forward conditional language where prospective hindsight is the contract. The plan *failed*; the narrative is past-tense.
- **Generic failure tropes** — scope creep, communication breakdown, stakeholder misalignment without plan-specific mechanism.
- **Lagging indicators** — failure visibility only at post-mortem; no signals the team could have caught pre-failure.
- **Post-hoc mitigations** — actions framed as mitigations but only available after the failure has begun.
- **Optimism residue** — failure inventory truncated; analyst's prior on success bleeds through.
- **Class-imbalanced inventory** — all failure modes in one class (typically execution) when assumption, context-shift, interaction, motivational failures were also plausible.
- **Plan-agnostic narrative** — the failure narrative could be substituted into any other plan of comparable shape; nothing in it is specific to *this* plan.

**What NOT to collapse:**

- **Competing failure narratives** — when streams produced different leading failure narratives, both survive; the choice between them is information about which assumption the team thinks is most load-bearing.
- **Stream disagreement about failure class** — when one stream classified a failure as execution and another as assumption, the disagreement reveals what's contested about the plan's structure.
- **Leading-indicator disagreements** — when streams identified different observable signals for the same failure mode, both survive; the team monitors multiple indicators.
- **Residual risks that the mitigations cannot reach** — preserved at full salience; this is the load-bearing finding for the pre-commitment decision.

## VERIFICATION CRITERIA

Verified means: the failure narrative is in past-tense prospective-hindsight stance throughout; every named failure mode has plan-specific mechanism (no generic tropes); every failure mode has at least one leading indicator the team could observe pre-failure; every mitigation is a pre-commitment action (not a post-hoc remediation); the four critical questions are addressable from the output. Confidence per finding accompanies each major claim.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **prospective-hindsight failure analysis** — a structured pre-mortem on the action plan, written in past tense, with plan-specific failure modes, leading indicators per mode, and pre-commitment mitigations the team can lock in before launch. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Imagined failure narrative.** One to two paragraphs of past-tense post-mortem prose. `It is [decision horizon] from now. The plan failed. Here is what happened: [...].` The grammar stays retrospective throughout — `failed`, `broke`, `proved`, `was`, `had to be`. Forward conditional language is reshaped at this layer.

2. **Failure mode inventory.** Bulleted or per-class block. Each: `**[Failure mode]** — class: [execution / assumption / context-shift / interaction / motivational]. Plan-specific mechanism: [the named decision point, assumption, or coupling that broke].` Generic tropes are reshaped to mechanism-grounded entries.

3. **Causal pathways to failure.** Per failure mode, one labelled sub-block: `**[Failure mode]** → breakage point: [specific decision or assumption]. Immediate consequence: [...]. Cascade: [...]. Surfaced failure: [...].`

4. **Leading indicators per failure mode.** Per failure mode, one labelled sub-block: `**[Failure mode]** — leading indicators: [...]. Signal-acquisition cost: [...]. Lead time before visible failure: [...].`

5. **Pre-commitment mitigations.** Numbered list. Each: `[N]. **[Mitigation — test / assumption-check / pilot / decision-gate / kill criterion]** — what it locks in before commitment: [...]. Which failure mode(s) it addresses: [...]. Cost to implement before launch: [...].` Mitigations that can only be taken after the failure has begun are reshaped here.

6. **Residual unmitigated risks.** Bulleted list. Each: `**[Residual risk]** — which failure modes remain partially or fully exposed: [...]. Conditions under which it materialises: [...]. Whether this should warrant rethinking the plan: [...].`

7. **Confidence per finding.** Bulleted list of confidence assessments per major claim, with grounding.

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- The Klein prospective-hindsight vocabulary stays operative: `the plan failed`, `the assumption broke`, `the context shifted`, `the team disengaged`. Past-tense grammar is the structural feature; revisiting forward-conditional grammar gets reshaped at this layer.
- Klein's failure-class taxonomy (execution / assumption / context-shift / interaction / motivational) appears verbatim in section 2. Class-imbalanced inventories (all execution, or all assumption) are reshaped when other classes were plausible.
- Failure-mode mechanisms (section 2) are *plan-specific* — they name the actual decision point or assumption in *this* plan. A failure narrative that could be substituted into any plan of comparable shape is reshaped.
- Pre-commitment mitigations (section 5) are *pre*-commitment by construction. Mitigations framed as available after the failure has begun get reshaped to post-hoc-remediation flags and removed from this section.
- When the optimism-residue flag survived consolidation, the deliverable opens with: `**Note: the failure-mode inventory below was reshaped during consolidation to counter optimism residue. If the inventory still reads shorter than the plan's complexity warrants, the pre-mortem stance has not held; re-dispatch with explicit instruction to extend the failure narrative.**`
- When the artifact is system-shaped rather than plan-shaped (sideways-route to pre-mortem-fragility), the deliverable opens with: `**Note: on reflection the analytical object may be a system or design rather than a plan to execute; pre-mortem-fragility (T7) is the appropriate sideways-route.**`
- Confidence (section 7) is per-finding; collapsing into overall pre-mortem confidence is reshaped at this layer.

## CAVEATS AND OPEN DEBATES

**Parsing rationale (Decision D).** This mode is one of two parsed from the historical "Pre-Mortem" candidate that appeared to fit two territories. Per the parsing principle, dual-citizenship is rejected: the operation on an action plan (T6, future exploration with adversarial-future stance) and the operation on a system/design (T7, risk and failure analysis) are different operations sharing a name. Both modes share the `klein-pre-mortem` lens (Klein 2007 *HBR*; Mitchell, Russo & Pennington 1989 on prospective hindsight), but their input contracts, output contracts, and critical questions diverge. When in doubt about whether the artifact is plan-shaped or system-shaped, route via the disambiguating question: "Is this about an action plan that could fail, or about a system or design with structural fragilities?" Sibling: `pre-mortem-fragility` (T7).


---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~1min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `contradicts`, `qualifies`, `produces`, `precedes`
**Deprioritize:** `parent`, `analogous-to`

*Family: hypothesis-future. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
