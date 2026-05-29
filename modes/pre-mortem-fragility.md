---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Pre-Mortem (Fragility)

```yaml
# 0. IDENTITY
mode_id: pre-mortem-fragility
canonical_name: Pre-Mortem (Fragility)
suffix_rule: analysis
educational_name: pre-mortem on structural fragilities (Klein, Taleb adjacent)

# 1. TERRITORY AND POSITION
territory: T7-risk-and-failure-analysis
gradation_position:
  axis: stance
  value: adversarial-future
adjacent_modes_in_territory:
  - mode_id: pre-mortem-action
    relationship: parsed-sibling (stance-counterpart on plan rather than system; lives in T6; shares klein-pre-mortem lens)
  - mode_id: fragility-antifragility-audit
    relationship: depth-heavier sibling (Talebian asymmetry-focused; built Wave 3)
  - mode_id: failure-mode-scan
    relationship: depth-light sibling (gap-deferred per CR-6)
  - mode_id: fault-tree
    relationship: depth-thorough sibling (gap-deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "where could this design break"
    - "what failure modes does this system exhibit"
    - "which parts of this structure are load-bearing single points"
    - "if I were stress-testing this architecture, where would I look"
    - "before we ship this design, what fragilities exist"
  prompt_shape_signals:
    - "pre-mortem this design"
    - "pre-mortem this system"
    - "structural fragilities"
    - "where will this break"
    - "single points of failure"
    - "Klein pre-mortem on this architecture"
disambiguation_routing:
  routes_to_this_mode_when:
    - "the artifact under analysis is a system, design, structure, architecture, or institution"
    - "user wants prospective-hindsight failure narration of structural breakage"
    - "the relevant failures are about how the structure responds to stress, not about how a team executes"
  routes_away_when:
    - "the artifact is an action plan or course of action rather than a structure" → pre-mortem-action (T6)
    - "user wants Talebian asymmetry analysis (fragile / robust / antifragile)" → fragility-antifragility-audit
    - "user wants adversarial-actor stress test (someone is trying to defeat this)" → red-team-assessment / red-team-advocate (T15)
    - "user wants exhaustive structured fault decomposition" → fault-tree (when built)
when_not_to_invoke:
  - "User is post-failure and wants backward causal trace" → root-cause-analysis (T4)
  - "User wants to evaluate the design as an argument or proposal" → balanced-critique or steelman-construction (T15)
  - "Design is so under-specified that no failure narrative is possible — degrade to elicitation"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: adversarial

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [system_or_design, structural_components, intended_function]
    optional: [stress_envelope, known_load_assumptions, prior_failures_in_class]
    notes: "Applies when user supplies a structured design with named components, dependencies, or operating envelope."
  accessible_mode:
    required: [system_description]
    optional: [why_user_wants_fragility_check, intended_use_context]
    notes: "Default. Mode infers components and intended function from the description and elicits stress envelope during execution if absent."
  detection:
    expert_signals: ["the architecture", "the design", "the system has", "components include", "dependencies are", "operating envelope"]
    accessible_signals: ["where will this break", "structural fragilities", "pre-mortem this design", "what's the weak point"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe the system or design and what it's meant to do under what conditions?'"
    on_underspecified: "Ask: 'What range of conditions is this meant to operate within, so I can imagine the conditions in which it breaks?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the analysis genuinely adopted prospective-hindsight stance on the system (writing as though the breakage has already occurred), or has it slipped into hedged forward-projection?"
    failure_mode_if_unmet: stance-slippage
  - cq_id: CQ2
    question: "Are the named fragilities specific to this structure's components and dependencies, or are they generic system-failure tropes (single point of failure, cascading failure) without structural specificity?"
    failure_mode_if_unmet: generic-fragility-trope
  - cq_id: CQ3
    question: "Have load pathways been traced from operating-envelope stresses to specific structural elements that yield, or do the breakages appear without mechanism?"
    failure_mode_if_unmet: mechanism-gap
  - cq_id: CQ4
    question: "Have structural mitigations been distinguished from operational workarounds, given that fragility is a property of the structure rather than its operation?"
    failure_mode_if_unmet: structure-operation-conflation

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: stance-slippage
    detection_signal: "Output uses forward conditional language ('this might fail under load') rather than retrospective ('the system broke when load exceeded X because component Y could not...')."
    correction_protocol: re-dispatch
  - name: generic-fragility-trope
    detection_signal: "Fragilities named are pattern-matched abstractions (single point of failure, cascading failure, brittle dependency) without naming the specific component, link, or interface."
    correction_protocol: re-dispatch
  - name: mechanism-gap
    detection_signal: "A fragility is asserted without naming the load condition that triggers it or the structural property that yields under that load."
    correction_protocol: flag
  - name: structure-operation-conflation
    detection_signal: "Mitigations include operational practices (better monitoring, more careful operators) rather than structural changes."
    correction_protocol: flag
  - name: actor-modeling-drift
    detection_signal: "Failure narratives invoke an adversarial actor trying to defeat the system; this is Red Team's territory, not structural fragility."
    correction_protocol: re-dispatch (or escalate to red-team-assessment / red-team-advocate)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - klein-pre-mortem
  optional:
    - taleb-fragile-robust-antifragile (when Talebian framing fits)
    - perrow-normal-accidents (when system is tightly coupled)
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~1min
escalation_signals:
  upward:
    target_mode_id: fragility-antifragility-audit
    when: "Analysis needs Talebian asymmetry framing (fragile vs. robust vs. antifragile) or formal stress-envelope decomposition."
  sideways:
    target_mode_id: pre-mortem-action
    when: "On reflection the artifact is a plan to execute rather than a structure; the relevant failures are about action execution rather than structural breakage."
  downward:
    target_mode_id: null
    when: "Pre-Mortem (Fragility) is the lightest stance-adversarial-future entry in T7; downward routing is to a lighter-depth mode within T7 once Failure Mode Scan is built."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Pre-Mortem (Fragility) is the specificity with which the breakage narrative is bound to *this structure's components and load pathways*. A thin pass names abstract fragility patterns; a substantive pass writes the post-incident report as though the breakage happened, names the specific component or interface that yielded, traces the load condition that exceeded the structural property, and identifies leading indicators (drift, saturation, latency increase, error rate climb) that would have shown the structure approaching failure. Test depth by asking: could this fragility narrative only be written about this design, or would it read identically for any system of comparable architecture?

## BREADTH ANALYSIS GUIDANCE

Widening the lens in Pre-Mortem (Fragility) means scanning the structural-fragility landscape: load fragilities (the structure breaks under unusual but specifiable load), dependency fragilities (a component depends on a fragile-or-absent counterpart), interface fragilities (the joint between components is the failure surface), state fragilities (the structure breaks when accumulated state crosses a threshold), and emergent fragilities (the structure exhibits a failure mode that no single component shows). A breadth-passing analysis surveys all five classes before narrowing to the two-or-three most plausible breakage narratives for the prospective-hindsight pass.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Pre-Mortem (Fragility) is Klein's prospective-hindsight method applied to a system, design, structure, architecture, or institution — writing the post-incident report before deployment to surface the structural fragilities that would yield under stress. The mode is parsed from a plan/action counterpart (pre-mortem-action in T6 — same Klein lens, different artifact shape); it sits in T7's risk-and-failure territory with adversarial-future stance toward the structure. It is distinct from fragility-antifragility-audit (depth-heavier Talebian asymmetry framing), red-team-assessment / red-team-advocate (adversarial-actor stress test — structural fragility has no actor), failure-mode-scan (lighter sibling, deferred), and fault-tree (heavier sibling, deferred). The mode targets structural mechanism, not operator behavior — recommending "more careful monitoring" instead of structural change is collapsing fragility into operation.

**Procedure.**

1. Anchor the system, its components, its dependencies, its interfaces, and the operating envelope it's intended to function within.
2. Write the imagined breakage narrative in past tense — "The system broke under [load condition]. Here is what yielded." The grammar stays retrospective; forward conditional language is stance slippage.
3. Survey the structural-fragility landscape across the five classes — load (the structure breaks under unusual but specifiable load), dependency (a component depends on a fragile-or-absent counterpart), interface (the joint between components is the failure surface), state (the structure breaks when accumulated state crosses a threshold), emergent (the structure exhibits a failure mode no single component shows).
4. Name each fragility with structure-specific mechanism — the actual component, link, or interface where it sits and the structural property that yields; never generic tropes like "single point of failure" without naming the point.
5. Trace the load pathway per fragility — operating-envelope condition that triggered the breakage, structural property that yielded, immediate consequence, cascade through dependencies.
6. Identify leading indicators per fragility — observable signals approaching failure (drift, saturation, latency increase, error rate climb, queue depth, retry rate, accumulated state crossing threshold), signal-acquisition cost, lead time.
7. Generate structural mitigations — component replacement, interface hardening, dependency removal, state-bound enforcement, redundancy with independence, decoupling. Never operational workarounds (better monitoring, more careful operators).
8. Surface residual unmitigated fragilities that survive the structural mitigations, with the operating-envelope conditions under which they would yield.
9. Resist actor-modeling drift — if the narrative becomes about someone trying to defeat the system, escalate to red-team modes; structural fragility has no actor.

**Goal.** Produce a prospective-hindsight structural-fragility analysis where each fragility is structure-specific, each has a load-pathway mechanism, each has at least one leading indicator the team could observe pre-failure, and each mitigation is a structural change — delivered as past-tense post-incident report the team can read before deployment.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — stance integrity.** Has the analysis genuinely adopted prospective-hindsight stance on the system (writing as though the breakage has already occurred), or slipped into hedged forward-projection? Failure mode if unmet: `stance-slippage`.
- **CQ2 — structure-specific vs generic.** Are the named fragilities specific to this structure's components and dependencies, or generic system-failure tropes (single point of failure, cascading failure) without structural specificity? Failure mode if unmet: `generic-fragility-trope`.
- **CQ3 — load pathway mechanism.** Have load pathways been traced from operating-envelope stresses to specific structural elements that yield, or do the breakages appear without mechanism? Failure mode if unmet: `mechanism-gap`.
- **CQ4 — structural vs operational mitigations.** Have structural mitigations been distinguished from operational workarounds, given that fragility is a property of the structure rather than its operation? Failure mode if unmet: `structure-operation-conflation`.

A passing output narrates structure-specific yield mechanisms in past tense throughout, cites observable leading indicators per fragility, offers structural mitigations rather than operational workarounds, and surveys the fragility landscape across the five classes rather than concentrating in one (typically load).

**Named failure modes.**

- *stance-slippage* — output uses forward conditional language ("this might fail under load") rather than retrospective ("the system broke when load exceeded X because component Y could not...").
- *generic-fragility-trope* — fragilities named are pattern-matched abstractions (single point of failure, cascading failure, brittle dependency) without naming the specific component, link, or interface.
- *mechanism-gap* — fragility asserted without naming the load condition that triggers it or the structural property that yields under that load.
- *structure-operation-conflation* — mitigations include operational practices (better monitoring, more careful operators) rather than structural changes.
- *actor-modeling-drift* — failure narratives invoke an adversarial actor trying to defeat the system; that's Red Team's territory, not structural fragility.

## REVISION GUIDANCE

Revise to restore prospective-hindsight stance where the draft has slipped into hedged forward-projection. Revise to replace generic fragility tropes with structure-specific mechanisms tied to named components, interfaces, or dependencies. Revise to add load pathways where the breakage appears without mechanism. Resist revising toward operational fixes — the mode's analytical character is adversarial-future on the structure; recommending "more careful monitoring" instead of structural change collapses fragility into operation. Resist drift into adversarial-actor framing; if the analysis is really about an attacker, escalate to the red-team modes rather than revise.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Klein prospective-hindsight structural-fragility analysis: past-tense imagined-breakage narrative, structural-fragility atoms by class (load / dependency / interface / state / emergent), load-pathway atoms tied to specific components and operating-envelope conditions, leading-indicator atoms, structural-mitigation atoms (not operational workarounds), and residual-unmitigated-fragility atoms**. The atoms are:

1. **Imagined-breakage narrative atom.** The post-incident report the team would have written after the structural failure, in past tense. The system broke. Here is what yielded. Stance-slippage is the named failure mode the consolidator watches for; forward-conditional language gets reshaped to retrospective.

2. **Structural-fragility atoms — by class.** Each atom carries: the fragility, its class (`load` / `dependency` / `interface` / `state` / `emergent`), and the specific component, link, or interface where it sits. Generic-fragility-trope is the named failure mode; "single point of failure" or "cascading failure" without naming the component / link / interface get reshaped to structure-specific atoms.

3. **Load-pathway atoms.** Each atom traces: the operating-envelope condition that triggered the breakage (load level, frequency, duration, environmental shift), the structural property that yielded under it, and the immediate consequence. Mechanism-gap is the named failure mode; fragilities asserted without the load-trigger or yield-mechanism get reshaped.

4. **Leading-indicator atoms — per fragility.** Each atom names: the observable signal (drift, saturation, latency increase, error rate climb, queue depth, retry rate, accumulated state crossing threshold) that would have shown the structure approaching failure pre-breakage, the signal-acquisition cost, and the lead time.

5. **Structural-mitigation atoms.** Each atom names: a *structural* change (component replacement, interface hardening, dependency removal, state-bound enforcement, redundancy with independence, decoupling) that addresses the fragility. Structure-operation-conflation is the named failure mode; mitigations framed as operational practices (better monitoring, more careful operators, alerting tuning) get reshaped or flagged.

6. **Residual-unmitigated-fragility atoms.** Each atom names: a fragility that survives the structural mitigations, and the operating-envelope conditions under which it would yield.

7. **Actor-modeling-drift flag — when applicable.** Where streams invoked an adversarial actor trying to defeat the system, the flag is preserved and the deliverable surfaces a sideways-route note. Actor-modeling-drift is the named failure mode; that's red-team territory, not structural fragility.

8. **Confidence per finding.** Each major claim carries a confidence with explicit grounding.

**Mode-specific bloat patterns to cut:**

- **Stance slippage** — forward conditional language. The structure *broke*; the narrative is past-tense.
- **Generic fragility tropes** — `single point of failure`, `cascading failure`, `brittle dependency` without naming the specific component / link / interface.
- **Mechanism gap** — fragility asserted without load condition or structural yield-mechanism.
- **Structure-operation conflation** — mitigations that change how operators behave rather than what the structure is. Fragility is a property of the structure.
- **Adversarial-actor drift** — narratives where someone is *trying* to defeat the system; that's red-team-assessment / red-team-advocate territory.
- **Class-imbalanced inventory** — fragilities all in one class (typically load) when dependency, interface, state, emergent classes were also plausible.
- **Architecture-agnostic narrative** — the fragility narrative could describe any system of comparable architecture; nothing in it is specific to *this* design.

**What NOT to collapse:**

- **Multiple breakage scenarios under different load conditions** — when streams traced different breakages under different operating-envelope shifts, both survive; the architecture has multiple yield surfaces.
- **Stream disagreement about fragility class** — when one stream classified a fragility as load and another as state (accumulation across time), the disagreement reveals what's contested about the structure's response model.
- **Mitigation alternatives** — when streams proposed different structural changes for the same fragility, both survive with their respective tradeoffs and side-effects.
- **Residual fragilities the mitigations cannot reach** — preserved at full salience; this is the load-bearing finding for the ship-or-not decision.

## VERIFICATION CRITERIA

Verified means: the breakage narrative is in past-tense prospective-hindsight stance throughout; every named fragility has a structure-specific mechanism (no generic tropes); every fragility has at least one leading indicator observable pre-failure; every mitigation is a structural change (not an operational workaround); no narrative is actually about an adversarial actor; the four critical questions are addressable from the output. Confidence per finding accompanies each major claim.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **prospective-hindsight structural-fragility analysis** — a structured pre-mortem on the system/design, written in past tense, with structure-specific fragilities, load-pathway mechanism, leading indicators, and structural (not operational) mitigations. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Imagined breakage narrative.** One to two paragraphs of past-tense post-incident prose. `The system broke under [load condition]. Here is what yielded: [...]. Here is what happened next: [...].` The grammar stays retrospective throughout.

2. **Structural fragility inventory.** Bulleted list grouped by class. Each: `**[Fragility]** — class: [load / dependency / interface / state / emergent]. Located in: [specific component, link, or interface]. Yield mechanism: [the structural property that fails].`

3. **Load pathways to breakage.** Per fragility, one labelled sub-block: `**[Fragility]** — operating-envelope condition that triggered it: [load level / frequency / duration / environmental shift]. Structural property that yielded: [...]. Immediate consequence: [...]. Cascade through dependencies: [...].`

4. **Leading indicators per fragility.** Per fragility, one labelled sub-block: `**[Fragility]** — observable signals approaching failure: [drift / saturation / latency increase / error rate / queue depth / retry rate / state accumulation]. Signal-acquisition cost: [...]. Lead time before yield: [...].`

5. **Structural mitigations.** Numbered list of structural changes. Each: `[N]. **[Structural change — component replacement / interface hardening / dependency removal / state-bound enforcement / redundancy-with-independence / decoupling]** — fragility it addresses: [...]. Tradeoffs introduced: [...]. Implementation cost: [...].` Operational workarounds (more monitoring, more careful operators) are reshaped here — they are not structural mitigations.

6. **Residual unmitigated fragilities.** Bulleted list. Each: `**[Residual fragility]** — why structural mitigations don't reach it: [...]. Operating-envelope conditions under which it would yield: [...]. Whether this should warrant rethinking the design: [...].`

7. **Confidence per finding.** Bulleted list of confidence assessments per major claim, with grounding.

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- The prospective-hindsight vocabulary stays operative — past-tense `broke`, `yielded`, `exceeded`, `accumulated past threshold`. Forward-conditional grammar gets reshaped at this layer.
- The five-class taxonomy (load / dependency / interface / state / emergent) appears verbatim. Class-imbalanced inventories are reshaped when other classes were plausible.
- Fragility mechanisms (section 2) are *structure-specific* — they name the actual component, link, or interface in *this* design. A breakage narrative substitutable into any system of comparable architecture is reshaped.
- Structural mitigations (section 5) change the structure itself. Operator-behaviour changes, monitoring upgrades, and alerting tuning are reshaped — they may belong in an operations runbook, but they are not fragility mitigations.
- When the actor-modeling-drift flag survived consolidation, the deliverable opens with: `**Note: portions of the consolidated corpus invoked an adversarial actor trying to defeat the system. That is red-team-assessment / red-team-advocate (T15) territory, not structural fragility. The deliverable below restricts itself to structural mechanisms; the actor-modeling material has been excluded with a sideways-route flag for separate dispatch.**`
- When the artifact is plan-shaped rather than system-shaped (sideways-route to pre-mortem-action), the deliverable opens with: `**Note: on reflection the analytical object may be a plan to execute rather than a system / design; pre-mortem-action (T6) is the appropriate sideways-route.**`
- Confidence (section 7) is per-finding; collapsing into overall pre-mortem confidence is reshaped at this layer.

## CAVEATS AND OPEN DEBATES

**Parsing rationale (Decision D).** This mode is one of two parsed from the historical "Pre-Mortem" candidate that appeared to fit two territories. Per the parsing principle, dual-citizenship is rejected: the operation on an action plan (T6, future exploration with adversarial-future stance) and the operation on a system/design (T7, risk and failure analysis) are different operations sharing a name. Both modes share the `klein-pre-mortem` lens (Klein 2007 *HBR*; Mitchell, Russo & Pennington 1989 on prospective hindsight), but their input contracts, output contracts, and critical questions diverge. When in doubt about whether the artifact is plan-shaped or system-shaped, route via the disambiguating question: "Is this about an action plan that could fail, or about a system or design with structural fragilities?" Sibling: `pre-mortem-action` (T6).

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~1min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- Challenge
- Provocation
- C&S
- FIP
- CAF
- PMI

Mental models (always loaded):
- klein-pre-mortem
- premortem-analysis
- swiss-cheese-model
- normal-accident-theory
- taleb-fragility-antifragility
- normalization-of-deviance
- margin-of-safety

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `requires`, `enables`, `qualifies`, `supports`, `contradicts`
**Deprioritize:** `analogous-to`, `parent`

*Family: decision-risk. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
