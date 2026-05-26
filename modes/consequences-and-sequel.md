---
nexus:
  - ora
type: mode
tags:
  - framework/instruction
  - architecture
date created: 2026-04-17
date modified: 2026-05-24

---

# MODE: Consequences and Sequel

```yaml
# 0. IDENTITY
mode_id: consequences-and-sequel
canonical_name: Consequences and Sequel
suffix_rule: analysis
educational_name: forward causal-cascade tracing (de Bono C&S, second-and-third-order effects)

# 1. TERRITORY AND POSITION
territory: T6-future-exploration
gradation_position:
  axis: depth
  value: light
  stance_axis_value: forward
adjacent_modes_in_territory:
  - mode_id: probabilistic-forecasting
    relationship: depth-thorough sibling (probability-output)
  - mode_id: scenario-planning
    relationship: depth-thorough sibling (narrative-output)
  - mode_id: pre-mortem-action
    relationship: stance-adversarial sibling (forward-on-plan)
  - mode_id: wicked-future
    relationship: depth-molecular sibling
  - mode_id: backcasting
    relationship: stance-constructive counterpart (gap-deferred)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "what would happen if we did X"
    - "what are the downstream effects"
    - "what are the second-order consequences"
    - "if we ship this, what does it lead to"
  prompt_shape_signals:
    - "consequences"
    - "sequel"
    - "second-order"
    - "third-order"
    - "cascade forward"
    - "what does this lead to"
disambiguation_routing:
  routes_to_this_mode_when:
    - "forward-from-action question, light pass to map immediate-through-third-order effects"
    - "linear cascade (may fork but not loop) — want a quick look at what propagates from a decision"
    - "willing to spend ~5 minutes for a focused cascade rather than a full scenario set"
  routes_away_when:
    - "circular feedback is the defining structure" → systems-dynamics-causal
    - "want probability-weighted forecasts" → probabilistic-forecasting
    - "want narrative scenario explorations" → scenario-planning
    - "specifically asking what could go wrong with this plan" → pre-mortem-action
    - "tracing backward from a symptom" → root-cause-analysis (T4)
when_not_to_invoke:
  - "User is choosing among options with risk as one input among several" → T3 (decision-under-uncertainty)
  - "User is evaluating a single proposal's benefit/risk envelope" → benefits-analysis (T15)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: generative

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [proposed_action, time_horizon_of_interest, domain_context]
    optional: [historical_analogues, prior_cascade_attempts]
    notes: "Applies when user supplies a clearly stated action with relevant time horizon and domain context."
  accessible_mode:
    required: [proposed_action_or_event]
    optional: [related_context, what_user_cares_about]
    notes: "Default. Mode infers time horizon from the action's nature."
  detection:
    expert_signals: ["second-order effects", "downstream cascade", "sequel analysis", "policy impact"]
    accessible_signals: ["what would happen if", "what does this lead to", "if we do X then what"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the action or event you want me to trace forward consequences for?'"
    on_underspecified: "Ask: 'How far forward do you want to look — immediate effects only, or out to second and third order?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the cascade reached at least third order on at least one branch, or has it stopped at first-order effects?"
    failure_mode_if_unmet: first-order-stop
  - cq_id: CQ2
    question: "Does every causal link state a mechanism, or are some links assertions of association without explanation?"
    failure_mode_if_unmet: association-without-mechanism
  - cq_id: CQ3
    question: "Are effects distributed across time horizons (immediate / short / medium / long), or are they all at one horizon?"
    failure_mode_if_unmet: single-horizon
  - cq_id: CQ4
    question: "Are unintended consequences — effects outside the proposer's stated goal — surfaced and distinguished from intended effects?"
    failure_mode_if_unmet: intended-effects-only
  - cq_id: CQ5
    question: "If any link returns influence to an earlier node, has the analysis flagged the feedback loop and proposed handoff to systems-dynamics-causal (T4) or systems-dynamics-structural (T17) per parse, rather than masquerading the cycle as a DAG?"
    failure_mode_if_unmet: feedback-collapse

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: first-order-stop
    detection_signal: "Cascade names immediate effects only; no second- or third-order branch is traced."
    correction_protocol: re-dispatch (extend at least one branch to third order)
  - name: association-without-mechanism
    detection_signal: "Causal links assert X → Y without naming the mechanism by which X produces Y."
    correction_protocol: flag (request mechanism per link)
  - name: single-horizon
    detection_signal: "All effects sit at one time horizon (e.g., everything is immediate or everything is long-term)."
    correction_protocol: re-dispatch (redistribute across at least three horizons)
  - name: intended-effects-only
    detection_signal: "Cascade traces only the proposer's stated goals; no effect outside the goal frame is named."
    correction_protocol: re-dispatch (add at least one unintended consequence)
  - name: feedback-collapse
    detection_signal: "Cycle present in the cascade but emitted as if linear; no SD handoff proposed."
    correction_protocol: escalate (suppress envelope, route to systems-dynamics-causal)
  - name: reinforcing-counteracting-collapse
    detection_signal: "All branches are amplifying or all dampening; no distinction drawn between the two."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - de-bono-consequence-and-sequel
  optional:
    - reinforcing-counteracting-distinction
    - cross-domain-cascade-patterns (when the cascade traverses multiple domains)
    - leading-indicators-methodology (when distant effects need near-term proxies)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: probabilistic-forecasting
    when: "Cascade reveals enough structure that probability weights would clarify which paths matter."
  sideways:
    target_mode_id: scenario-planning
    when: "Cascade branches diverge enough that narrative scenarios would carry the analysis better than a DAG."
  downward:
    target_mode_id: null
    when: "Consequences and Sequel is already the lightest forward-exploration mode in T6."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Consequences and Sequel is the cascade's depth in causal levels — first-order, second-order, third-order — and the rigour of mechanism statement at each link. A thin pass names immediate effects of the action; a substantive pass continues each first-order effect into its second-order consequences and at least one third-order consequence on a leading branch, with the mechanism for each link stated explicitly. Each effect is tagged with a time horizon (immediate / short / medium / long), and reinforcing branches (amplification) are distinguished from counteracting branches (dampening). Test depth by asking: could the analysis predict which specific signal would appear first if the cascade is unfolding as projected?

## BREADTH ANALYSIS GUIDANCE

Breadth in Consequences and Sequel is the catalog of branches considered — including branches the proposer would not name. Widen the lens by scanning: which domains the cascade crosses (an action in one domain often produces effects in others); which constituencies experience effects the proposer has not framed as effects; which feedback loops appear (and trigger SD handoff); which unintended consequences emerge from the structure rather than from the action's intent. Breadth markers: at least one cross-domain effect is named, at least one unintended consequence is surfaced, and time horizons span at least three of the four bands.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Consequences and Sequel applies de Bono's C&S — forward causal-cascade tracing from an action or event through immediate-through-third-order effects, with mechanism-per-link discipline, time-horizon distribution, and explicit distinction between intended and unintended consequences. It is distinct from probabilistic-forecasting (probability-weighted depth-thorough sibling), scenario-planning (narrative-output depth-thorough sibling), pre-mortem-action (stance-adversarial, forward-on-plan), and systems-dynamics-causal (circular feedback is the defining structure). The mode's load-bearing constraint is acyclicity — when a cycle appears, hand off to systems-dynamics rather than force the cycle into a DAG.

**Procedure.**

1. State the action or event being traced forward once at the root.
2. Enumerate first-order consequences — direct effects of the action; each carries time-horizon tag (immediate / short / medium / long), reinforcing-vs-counteracting tag, and intent tag (intended-by-proposer / unintended).
3. Extend each first-order effect into second-order — each effect becomes a cause; what does it then produce?
4. Continue at least one branch into third-order — the third-order discipline distinguishes a real cascade from an enumeration of immediate effects.
5. State a mechanism per link — every edge from parent to child carries an explicit `mechanism:` phrase. Links without mechanism are association-without-mechanism residue and do not survive.
6. Distribute effects across time horizons — at least three of the four bands (immediate / short / medium / long); single-horizon analyses miss the cascade's temporal structure.
7. Distinguish reinforcing (amplifying) from counteracting (dampening) branches — uniform direction is reinforcing-counteracting-collapse.
8. Surface unintended consequences — effects outside the proposer's stated goal frame.
9. Name cross-domain crossings — when the cascade traverses domains (technical → economic → social), the crossing itself is an atom with mechanism.
10. Identify leading indicators per major branch — the near-term signal that would reveal the cascade is unfolding as projected.
11. When a cycle is detected, suppress the DAG emission and propose handoff to systems-dynamics-causal rather than falsifying the structure.

**Goal.** Produce a directed acyclic cascade map rooted at the action or event, with mechanism-per-edge, time-horizon-per-node, third-order reach on at least one branch, surfaced unintended consequences, and explicit cycle-handoff when feedback is detected.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — third-order reach.** Has the cascade reached at least third order on at least one branch, or has it stopped at first-order effects? Failure mode if unmet: `first-order-stop`.
- **CQ2 — mechanism per link.** Does every causal link state a mechanism, or are some links assertions of association without explanation? Failure mode if unmet: `association-without-mechanism`.
- **CQ3 — time-horizon distribution.** Are effects distributed across time horizons (immediate / short / medium / long), or are they all at one horizon? Failure mode if unmet: `single-horizon`.
- **CQ4 — unintended consequences.** Are unintended consequences — effects outside the proposer's stated goal — surfaced and distinguished from intended effects? Failure mode if unmet: `intended-effects-only`.
- **CQ5 — feedback handoff.** If any link returns influence to an earlier node, has the analysis flagged the feedback loop and proposed handoff to systems-dynamics-causal/structural rather than masquerading the cycle as a DAG? Failure mode if unmet: `feedback-collapse`.

A passing output reaches third order on at least one branch with mechanism per link, distributes effects across at least three time horizons, names at least one unintended consequence, distinguishes reinforcing from counteracting branches, identifies leading indicators per major branch, and either contains no cycles or has flagged the cycle and proposed SD handoff.

**Named failure modes.**

- *first-order-stop* — cascade names immediate effects only; no second- or third-order branch is traced.
- *association-without-mechanism* — causal links assert X → Y without naming the mechanism by which X produces Y.
- *single-horizon* — all effects sit at one time horizon.
- *intended-effects-only* — cascade traces only the proposer's stated goals; no effect outside the goal frame is named.
- *feedback-collapse* — cycle present in the cascade but emitted as if linear; no SD handoff proposed.
- *reinforcing-counteracting-collapse* — all branches are amplifying or all dampening; no distinction drawn.

## REVISION GUIDANCE

Revise to extend any branch that stops at first-order by asking: each effect becomes a cause — what does this then produce? Revise to add a mechanism sentence to any link that asserts X → Y without explaining how. Revise to redistribute effects across time horizons when one horizon dominates. If a cycle is discovered during revision, suppress the envelope entirely and propose handoff to `systems-dynamics-causal` — Consequences and Sequel cannot emit cycles, and forcing a cycle into a DAG misrepresents the structure.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a directed acyclic causal cascade rooted at the action/event**, with each node carrying time-horizon, order-depth, and intent tags, and each edge carrying an explicit mechanism. The DAG is the load-bearing structure; cycles are forbidden — if one is detected, the corpus carries a feedback-handoff atom rather than a falsified DAG. The atoms are:

1. **Action/event root atom.** The proposed action or event being traced forward, stated once at the corpus root. Cross-stream paraphrase collapses to one canonical statement.

2. **Cascade-node atoms.** Each effect is a node carrying: effect statement, time-horizon tag (immediate / short / medium / long), order-depth tag (first / second / third), reinforcing-or-counteracting tag (amplifying / dampening), intent tag (intended-by-proposer / unintended), and parent-node reference. At least one branch must reach order-depth third or CQ1 fails.

3. **Causal-link atoms.** Each edge from parent to child carries an explicit mechanism phrase — the named process by which parent produces child. Edges without mechanism phrases are association-without-mechanism residue and do not survive into the corpus; the consolidator marks them as gaps requiring mechanism, not as accepted edges.

4. **Cross-domain-crossing atoms.** When the cascade crosses a domain boundary (e.g., a technical action producing economic, then social, effects), an explicit crossing atom names: the source domain, the target domain, and the mechanism by which the crossing occurs. At least one cross-domain crossing must be named or the breadth marker is unmet.

5. **Unintended-consequence atoms.** Effects outside the proposer's stated goal frame, surfaced and flagged distinctly from intended effects. Intended-effects-only is the named failure mode; at least one unintended atom must survive or the corpus fails CQ4.

6. **Reinforcing-vs-counteracting distribution atom.** A corpus-level atom names the branches as amplifying or dampening with at least one of each — uniform direction is reinforcing-counteracting-collapse residue.

7. **Leading-indicator atoms.** Near-term proxies for distant effects, per major branch — what signal would appear first if the cascade is unfolding as projected.

8. **Feedback-loop flag — when a cycle is detected.** When any link returns influence to an earlier node, the corpus suppresses the cascade emission and carries instead a feedback-handoff atom naming: the detected cycle, the structural reason it cannot be represented as a DAG, and the SD-handoff proposal (systems-dynamics-causal for "why" loops; systems-dynamics-structural for "how" loops). Feedback-collapse is the named failure mode; a cycle masqueraded as DAG is its corpus signature.

9. **Confidence per branch atom.** Confidence markers attach to entire branches (high for well-precedented cascades; lower for novel territory). When the two streams assigned different confidences to the same branch, audit conservatism applies (the lower confidence survives).

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Effect-statement paraphrase** — same effect under different wordings across streams. Single canonical statement survives, with the more precise mechanism phrase carried forward.
- **Mechanism-paraphrase loops** — same mechanism phrase under different wordings ("by reducing X" vs "through lower X"). One mechanism phrase survives per link.
- **Time-horizon-restatement** — both streams may tag the same effect with the same horizon in different language ("near-term" vs "short-horizon"). One canonical tag per node.
- **Cross-domain-restatement** — same domain crossing identified twice under different domain labels. One crossing atom survives with canonical domain identifiers.
- **Implicit-association links** — links stated as X → Y with no mechanism. Association-without-mechanism residue; the link does not survive into the corpus as an edge — either a mechanism is found or the edge is dropped and the cascade branch terminates at the parent.
- **Order-depth-marker restatement** — both streams may say "this is a second-order effect" in different framings. Order-depth is a tag, not a sentence; the tag survives, restatements do not.

**What NOT to collapse:**

- **Diverging cascade branches** — when the two streams extended different branches to order-depth three (each branch genuine, just different focal paths), preserve both branches. The cascade is intentionally generative; multiple deep branches are evidence of breadth, not redundancy.
- **Mechanism disagreement for the same link** — when one stream claimed mechanism M1 for the X→Y link and the other claimed M2, preserve both mechanisms as parallel link-atoms. The disagreement is a finding about which causal pathway dominates; the consolidator must not silently pick.
- **Feedback-loop disagreement** — when one stream detected a cycle and the other did not, the cycle-detecting stream's finding governs. Cycles are asymmetric: a missed cycle is more dangerous than a false-positive cycle, since the latter produces a flag and SD handoff (recoverable), while the former produces a falsified DAG.

## VERIFICATION CRITERIA

Verified means: at least one path reaches length 3 (third order); every link in the cascade has a stated mechanism; effects span at least three of the four time-horizon bands; at least one unintended consequence is named; at least one reinforcing branch and at least one counteracting branch are distinguished; if any cycle appears, it is flagged and SD handoff is proposed. Confidence per major branch is stated (high for well-precedented cascades; lower for novel territory).

## OUTPUT FORMAT GUIDANCE

The deliverable is a **directed acyclic cascade map** rooted at the action or event, rendered as a hierarchical tree with mechanism-per-edge and time-horizon tags per node. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Action or event.** The proposed action or event at the corpus root, stated once in one sentence. Frame as "Action being traced forward:"

2. **First-order consequences.** Bulleted list of direct effects. Each bullet renders: `**[Effect statement]** — mechanism: [how the action produces this effect]. Time horizon: [immediate / short / medium / long]. Branch: [reinforcing / counteracting]. Intent: [intended-by-proposer / unintended].`

3. **Second-order consequences.** Same template, nested under each first-order parent. Each bullet states the parent (e.g., "From first-order effect 1.2:") then the second-order effect with full tag set.

4. **Third-order consequences (where tractable).** Same template, extending the deepest branch(es) to depth 3. At minimum one third-order branch is rendered or CQ1 fails (first-order-stop). When third-order tracing becomes speculative for some branches, render: "Branch [N]: third-order not traced (confidence too low for projection)" rather than fabricating depth.

5. **Time-horizon classification.** A small summary table or list: which effects sit at which horizon (immediate / short / medium / long). Verify distribution across at least three of the four bands.

6. **Reinforcing and counteracting branches.** Two short blocks (one per direction): which branches amplify the action's effect, which counteract or dampen it. At minimum one branch in each direction, or the corpus carries the imbalance as a finding.

7. **Cross-domain effects.** Bulleted list of effects that cross domain boundaries (e.g., technical → economic → social). Each bullet names: source domain, target domain, mechanism of crossing, and which cascade-node the crossing originated from.

8. **Unintended consequences.** Bulleted list of effects outside the proposer's stated goal frame. Each bullet: `**[Effect]** — emerges from [structural source, not from action intent]. Affected: [parties]. Intent tag: unintended.` At minimum one unintended consequence atom.

9. **Leading indicators.** Per major branch, the near-term proxy signal that would reveal the cascade is unfolding as projected. Each bullet: `Branch [N]: leading indicator — [observable signal that would appear before downstream effects materialize].`

10. **Feedback-loop flag — when cycle detected.** When the cascade contains a cycle (any link returning influence to an earlier node), this section replaces the rest of the deliverable from this point and renders: "**Feedback loop detected.** This analysis cannot be represented as a DAG. Handoff: [systems-dynamics-causal for 'why' loops / systems-dynamics-structural for 'how' loops]. The detected cycle: [nodes and arcs]. Structural reason DAG representation fails: [reason]." Cascade emission is suppressed for the cycle-containing branch.

11. **Confidence per major branch.** Bulleted list of confidence markers per branch (high for well-precedented cascades; lower for novel territory).

**Per-section conventions:**

- Use H2 headings for sections 1 through 11.
- Cascade nodes use a consistent numbering scheme: first-order = 1.1, 1.2, ...; second-order = 1.1.1, 1.1.2, ...; third-order = 1.1.1.1, etc. Numbering makes parent-child relationships explicit.
- Mechanism phrases use the literal `mechanism:` label per edge.
- Time-horizon tags use the canonical four labels (immediate / short / medium / long) — not "near-term" or other variations.
- When section 10 fires (cycle detected), it replaces sections 2 through 9 for the affected branch rather than appearing alongside them.


## CAVEATS AND OPEN DEBATES

Consequences and Sequel operates as the Tier-1 light variant in the T6 future-exploration ladder; it complements but does not substitute for the heavier modes — `probabilistic-forecasting` (when probability weights matter), `scenario-planning` (when divergent narratives carry the analysis better than a single cascade), `wicked-future` (the molecular variant for tangled forward problems). The mode's load-bearing constraint is acyclicity: when a cycle appears in the cascade, the right move is handoff to `systems-dynamics-causal`, not forcing the cycle into a DAG that misrepresents the structure. The third-order discipline (extend at least one branch to depth 3) is the discipline that distinguishes a real cascade from an enumeration of immediate effects.


---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `contradicts`, `qualifies`, `produces`, `precedes`
**Deprioritize:** `parent`, `analogous-to`

*Family: hypothesis-future. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
