---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-24

---

# MODE: Cui Bono

```yaml
# 0. IDENTITY
mode_id: cui-bono
canonical_name: Cui Bono
suffix_rule: analysis
educational_name: who-benefits analysis (cui bono)

# 1. TERRITORY AND POSITION
territory: T2-interest-and-power
gradation_position:
  axis: complexity
  value: simple
adjacent_modes_in_territory:
  - mode_id: stakeholder-mapping
    relationship: complexity-heavier sibling (multi-party-descriptive — lives in T8)
  - mode_id: boundary-critique
    relationship: stance-critical counterpart (Ulrich CSH)
  - mode_id: wicked-problems
    relationship: complexity-molecular sibling
  - mode_id: decision-clarity
    relationship: depth-molecular sibling (decision-maker-output)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "trying to understand who's behind this"
    - "want to know who benefits from"
    - "feels like someone's pushing this for a reason"
    - "this policy or standard sounds objective but I suspect it isn't"
  prompt_shape_signals:
    - "who benefits"
    - "cui bono"
    - "whose interests"
    - "who's pushing this"
    - "trace the interests"
    - "who gains from X"
disambiguation_routing:
  routes_to_this_mode_when:
    - "this one situation, single set of beneficiaries"
    - "quick read on who gains from this state of affairs"
    - "policy or institutional position with distributional consequences"
  routes_away_when:
    - "landscape of multiple parties with different stakes" → stakeholder-mapping
    - "tangled / wicked / many systems interacting" → wicked-problems
    - "voices being left out of the picture entirely" → boundary-critique
    - "produce a decision document for a decision-maker" → decision-clarity
    - "questioning the empirical foundations of a position" → paradigm-suspension
when_not_to_invoke:
  - "User is evaluating an argument's soundness, not its sponsoring interests" → T1
  - "User is asking about active negotiation strategy" → T13
  - "Multiple competing explanations for the same evidence — adjudicate via diagnosticity" → T5 competing-hypotheses

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [situation_or_artifact, optional_actor_inventory]
    optional: [historical_context, prior_interest_analyses, distributional_parameters]
    notes: "Applies when user explicitly references actors by name or supplies an actor inventory or named institutional parameters."
  accessible_mode:
    required: [situation_or_artifact]
    optional: [related_context]
    notes: "Default. Mode infers actor inventory and parameters from the situation."
  detection:
    expert_signals: ["actor inventory", "stakeholders are X, Y, Z", "interest groups include", "policy text", "regulatory framework"]
    accessible_signals: ["who benefits", "whose interests", "who's behind this", "trace the interests"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe the situation, decision, or paste the article/document you want me to look at?'"
    on_underspecified: "Ask: 'What's the situation, decision, or text you want a who-benefits read on?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the identified beneficiaries actually positioned to benefit, or is the inference symbolic?"
    failure_mode_if_unmet: symbolic-inference (mistaking narrative resonance for actual benefit)
  - cq_id: CQ2
    question: "Are there beneficiaries the analysis is missing because they are not visible from the artifact's frame?"
    failure_mode_if_unmet: frame-bounded-blindness
  - cq_id: CQ3
    question: "Are the costs identified actually borne by the parties named, or is incidence misattributed?"
    failure_mode_if_unmet: cost-incidence-error
  - cq_id: CQ4
    question: "Has FGL (Fear, Greed, Laziness) been applied symmetrically across constituencies, or only against the disfavoured side?"
    failure_mode_if_unmet: asymmetric-fgl

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: symbolic-inference
    detection_signal: "Beneficiary identified by ideological alignment rather than concrete benefit pathway."
    correction_protocol: flag
  - name: frame-bounded-blindness
    detection_signal: "All identified parties share the artifact's frame; no parties from outside the frame appear."
    correction_protocol: escalate
  - name: cost-incidence-error
    detection_signal: "Costs are attributed to a party without a concrete payment, time, or freedom-loss pathway."
    correction_protocol: flag
  - name: conspiracy-trap
    detection_signal: "Distributional outcomes attributed to deliberate coordination without explicit evidence; intent assumed where structural incentives suffice."
    correction_protocol: flag
  - name: cynicism-trap
    detection_signal: "Position concluded to have no legitimate basis; legitimate value collapsed into distributional overlay."
    correction_protocol: flag
  - name: mirror-trap
    detection_signal: "Alternative design reflects analyst's preference rather than the disadvantaged constituency's interests."
    correction_protocol: re-dispatch
  - name: asymmetric-fgl
    detection_signal: "FGL applied to only one constituency; opposing party's motives uninspected."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - rumelt-strategy-kernel
    - ulrich-csh-boundary-categories
    - public-choice-theory
    - fgl-fear-greed-laziness
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: stakeholder-mapping
    when: "Beneficiary inventory exceeds 5 parties or interest structure is multi-layered."
  sideways:
    target_mode_id: boundary-critique
    when: "Most identified parties are inside one frame; boundary-critique surfaces parties outside it."
  downward:
    target_mode_id: null
    when: "Cui Bono is already the lightest mode in T2."
```

## DEPTH ANALYSIS GUIDANCE

Going deeper in Cui Bono means tracing concrete benefit pathways (money flows, power-position changes, time-and-attention captures, narrative-control gains) rather than asserting alignment-based benefit. A thin pass names parties; a substantive pass names the institutional author, the specific parameters or definitional choices that drive distribution, and the counterparty's loss-pathway. Apply FGL (Fear, Greed, Laziness) explicitly per constituency. Test depth by asking: could the analysis predict how each beneficiary would behave if the situation changed, and could it name the parameter whose alteration would shift the distribution?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for parties not visible from the artifact's own frame: parties who would benefit if the situation were framed differently; parties who pay costs the artifact treats as natural; parties absent from the discussion whose voices would change the analysis. Construct the alternative design that would emerge from the opposite constituency's interests, with equal technical sophistication. Identify the legitimate value the current position serves, separate from its distributional overlay. Breadth markers: the analysis surveys the boundary of who is and isn't being asked, and offers an alternative as well-formed as the original.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Cui Bono — "who benefits" — traces incidence: who captures the residual benefit from a state of affairs and who bears the cost. The analytical move is identifying who has the leverage to change the situation and chose not to. It is distinct from conspiracy analysis (which requires evidence of intent) and from ideological-alignment analysis (which mistakes affinity for benefit). The mode is descriptive of interest structure, not neutralizing of it: when real power asymmetries surface they should be named, not softened toward false balance.

**Procedure.**

1. Verify the premise — confirm the situation, decision, or artifact being analyzed actually holds before building a beneficiary map on top of it.
2. Identify institutional authorship — who authored, sponsored, or otherwise issued the situation, including named individuals or sub-units when known.
3. Capture the stated rationale — the reason given by the author for the situation, in the author's own framing. Descriptive, not evaluative.
4. Map beneficiaries — for each: concrete pathway (money flow, power-position change, time-and-attention capture, narrative-control gain — not ideological alignment) and the specific parameter or definitional choice that drives the distribution.
5. Map cost-bearers — for each: concrete cost pathway (payment, time, freedom-loss, displacement) and the parameter that drives it.
6. Apply FGL (Fear, Greed, Laziness) symmetrically — same treatment for the analytically sympathetic side and the analytically suspect side.
7. Construct alternative design from the disadvantaged constituency's interests, with technical sophistication equal to the original. Not a cosmetic re-framing.
8. Separate legitimate value from distributional overlay — what the current position gets right (coordination problem solved, safety concern addressed) independent of who benefits.
9. Surface frame-bounded blindness when all identified parties share the artifact's frame; flag rather than present the inventory as complete.
10. Assign confidence per finding with explicit basis (named evidence, structural inference, speculation).

**Goal.** Produce a row-auditable analysis where each benefit, cost, and causal parameter is traceable to a named party, a concrete pathway, and a specific causal lever — distinguishing structural incidence from intentional coordination.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — symbolic vs concrete benefit.** Are identified beneficiaries actually positioned to benefit through a named pathway, or is the inference symbolic (alignment-based, ideological)? Failure mode if unmet: `symbolic-inference`.
- **CQ2 — frame-bounded blindness.** Are there beneficiaries the analysis is missing because they are not visible from the artifact's frame? Failure mode if unmet: `frame-bounded-blindness`.
- **CQ3 — cost-incidence accuracy.** Are the costs identified actually borne by the parties named, with concrete pathways? Failure mode if unmet: `cost-incidence-error`.
- **CQ4 — FGL symmetry.** Has Fear/Greed/Laziness been applied symmetrically across constituencies, or only against the disfavoured side? Failure mode if unmet: `asymmetric-fgl`.

A passing output names institutional author, names benefit pathways concretely with specific parameters, surfaces an alternative design from the disadvantaged constituency, applies FGL symmetrically, separates legitimate value from distributional overlay, and assigns confidence per finding.

**Named failure modes.**

- *symbolic-inference* — beneficiary identified by ideological alignment rather than concrete benefit pathway.
- *frame-bounded-blindness* — all identified parties share the artifact's frame; no parties from outside the frame appear.
- *cost-incidence-error* — costs attributed to a party without a concrete payment, time, or freedom-loss pathway.
- *conspiracy-trap* — distributional outcomes attributed to deliberate coordination without explicit evidence; intent assumed where structural incentives suffice.
- *cynicism-trap* — position concluded to have no legitimate basis; legitimate value collapsed into distributional overlay.
- *mirror-trap* — alternative design reflects analyst's preference rather than the disadvantaged constituency's interests.
- *asymmetric-fgl* — FGL applied to only one constituency; opposing party's motives uninspected.

## REVISION GUIDANCE

Revise to add concrete pathways where the draft asserts benefit without mechanism. Revise to add specific parameters where vague "incentive structure" language sits unanchored. Revise to add boundary-cases (parties absent or marginalized). Revise to make the alternative design technically sophisticated rather than cosmetic, and to ground it in the disadvantaged constituency's interests rather than the analyst's preferences. Resist revising toward neutrality if the analysis surfaces real power-asymmetries — the mode is descriptive of interest structure, not neutralizing of it. Silent upgrade from structural incentive attribution to intent-attribution during revision is a failure unless new evidence is explicitly cited.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **an interest-structure mapping: institutional-author identification, stated-rationale capture, distributional-impact atoms per constituency, alternative-design construction from the opposite constituency, motivational atoms via FGL applied symmetrically, legitimate-value separation, and confidence per finding**. The atoms are:

1. **Institutional-author atom.** Who authored, sponsored, or otherwise issued the situation/artifact. One short atom naming the authoring institution and (where relevant) the named individuals or sub-units that drove it. If authorship is contested or unclear, the contest is itself the atom — collapsing to a single attribution is bloat.

2. **Stated-rationale atom.** The reason given by the author for the situation, in the author's own framing. The corpus preserves the author's framing here even where streams disagree with it — this atom is descriptive, not evaluative.

3. **Distributional-impact atoms per beneficiary.** Each atom carries: party who benefits, the concrete benefit pathway (money flow, power-position change, time-and-attention capture, narrative-control gain — not ideological alignment), the specific parameter or definitional choice that drives the distribution, and a magnitude estimate where streams produced one. Symbolic-inference is the named failure mode; atoms that name benefit without pathway get reshaped or flagged.

4. **Distributional-impact atoms per cost-bearer.** Each atom carries: party who pays, the concrete cost pathway (payment, time, freedom-loss, displacement), and the parameter that drives the cost. Cost-incidence-error is the named failure mode; costs asserted without a concrete bearer get flagged.

5. **Alternative-design atom.** The design that would emerge from the disadvantaged constituency's interests, constructed with equal technical sophistication to the original. This atom is grounded in the absent constituency's interests, not in the analyst's preferences. Mirror-trap is the named failure mode; analyst-preference alternatives get reshaped.

6. **FGL atoms per constituency.** Fear, Greed, Laziness motivational analysis applied symmetrically. Each constituency named in atoms 3 or 4 carries an FGL atom — including the side the analysis treats sympathetically. Asymmetric-fgl is the named failure mode; one-sided FGL gets reshaped to symmetric.

7. **Legitimate-value atom.** The non-distributional value the current position serves (what it gets right, what concern it answers, what coordination problem it solves), kept separate from the distributional overlay. Cynicism-trap is the named failure mode; positions concluded to have zero legitimate basis get reshaped.

8. **Frame-bounded-blindness flag — when applicable.** When all identified parties share the artifact's frame and no parties from outside the frame appear, the corpus surfaces this as a flag rather than presenting the inventory as complete. Sideways-escalation to boundary-critique may be the right move.

9. **Confidence per finding.** Each major claim (beneficiary, cost-bearer, parameter, alternative-design element) carries a confidence and the basis for that confidence (named evidence, structural inference, speculation).

**Mode-specific bloat patterns to cut:**

- **Alignment-based benefit attribution** — "X benefits because they support this ideologically" without a concrete pathway.
- **Intent attribution where structural incentives suffice** — conspiracy-trap. The corpus retains structural-incentive language and only carries explicit intent when streams pointed to named evidence.
- **One-sided FGL** — Fear/Greed/Laziness applied only to the disfavoured side. Symmetric application is the corpus standard.
- **Mirror-trap alternatives** — alternative designs that reflect the analyst's preferences rather than the disadvantaged constituency's interests.
- **Legitimate value collapsed into distributional overlay** — language that treats the position as having no defensible basis. The corpus separates the two.
- **Vague "incentive structure" language** — unanchored references to incentives without naming the specific parameter or definitional choice that drives them.

**What NOT to collapse:**

- **Competing beneficiary inventories** — when streams identified different primary beneficiaries (e.g., one stream named the regulating institution, another named a third-party beneficiary), preserve both with their respective pathways. The user, not the consolidator, adjudicates which reading is load-bearing.
- **Structural-incentive vs. intent disagreement** — when one stream attributes an outcome to structural incentives and another to deliberate coordination, preserve the disagreement explicitly. Collapsing toward intent is conspiracy-trap; collapsing toward structure is incumbent-laundering.
- **Alternative-design disagreements** — when streams constructed different alternative designs from the same disadvantaged constituency, both designs survive; the disagreement reveals what's contested about that constituency's interests.

## VERIFICATION CRITERIA

Verified means: the institutional author is named explicitly; at least two specific parameters driving distribution are stated; the alternative design is constructed with equal technical rigor and from the disadvantaged constituency's interests; FGL is applied to at least two constituencies; legitimate value is separated from distributional overlay; every named beneficiary has a concrete benefit pathway; every named cost has a concrete bearer; the analysis has surfaced absent voices or explicitly noted that boundary-critique was deferred. Confidence per finding accompanies every claim. The four critical questions are addressable from the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structured who-benefits mapping** — a row-auditable analysis where each benefit and cost is traceable to a named party, a concrete pathway, and the parameter that drives it. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Institutional authorship.** One paragraph naming the authoring institution and any sub-units or named individuals that drove the situation. When authorship is contested, the contest is reported here rather than smoothed.

2. **Stated rationale.** One short paragraph presenting the author's own framing of why the situation exists, in the author's vocabulary. The deliverable does not editorialise here — the next section opens the evaluation.

3. **Distributional impact.** A table or per-party block with paired beneficiary and cost-bearer rows. Each row: `**[Party]** — role: [beneficiary / cost-bearer]. Pathway: [concrete money / power / time / narrative pathway]. Parameter: [the specific parameter or definitional choice driving this]. Magnitude: [if estimable].` Beneficiaries and cost-bearers may be presented as two adjacent tables or as a single annotated table with a Role column.

4. **Alternative design from the opposite constituency.** One paragraph framing the alternative, then a bulleted list of its components. Each component: `**[Component]** — what it changes: [...]. How it serves the disadvantaged constituency's interests: [...].` The alternative is constructed with technical sophistication equal to the original; it is not a cosmetic re-framing.

5. **Motivational analysis (FGL).** Per-constituency block. Each constituency: `**[Constituency]** — Fear: [...]. Greed: [...]. Laziness: [...].` Apply FGL symmetrically — the analytically sympathetic side gets the same treatment as the analytically suspect side.

6. **Legitimate value.** One paragraph naming the non-distributional value the current position serves: what concern it answers, what coordination problem it solves, what it gets right independent of the distributional overlay.

7. **Confidence per finding.** Bulleted list of confidence assessments for each major claim, with the basis (named evidence / structural inference / speculation). At minimum: confidence in the authorship attribution, confidence in the beneficiary inventory, confidence in the parameter identification, confidence in the alternative-design fidelity.

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- Parameters driving distribution are named in section 3 with the specificity an audit would require — not "the regulatory framework" but the specific clause, threshold, definitional choice, or eligibility rule.
- The alternative design (section 4) is grounded in the disadvantaged constituency's interests, not the analyst's preferences. Designs that fail this test get reshaped or flagged at this layer.
- FGL (section 5) is applied symmetrically across constituencies; if FGL only appears for one side, the deliverable is failing its own format guidance.
- When frame-bounded-blindness is flagged in the corpus, the deliverable opens (before section 1) with a brief escalation note: `**Note: all identified parties may share the artifact's frame; parties outside the frame are not visible from this analysis. Boundary-critique is the appropriate sideways-route if frame-completeness is the operative question.**`
- The institutional-author claim and the intent-attribution language stay separated — structural incentives are the default explanatory frame; intent attribution requires named evidence and appears with explicit confidence labelling.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~10min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- OPV
- KVI

Mental models (always loaded):
- nash-equilibrium
- batna
- cooperation

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `requires`, `enables`, `contradicts`, `supports`, `qualifies`
**Deprioritize:** `parent`, `analogous-to`

*Family: stakeholder-strategy. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
