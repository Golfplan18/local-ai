---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Interest Mapping

```yaml
# 0. IDENTITY
mode_id: interest-mapping
canonical_name: Interest Mapping
suffix_rule: analysis
educational_name: interest mapping (Fisher-Ury principled negotiation lighter sibling)

# 1. TERRITORY AND POSITION
territory: T13-negotiation-and-conflict-resolution
gradation_position:
  axis: depth
  value: light
adjacent_modes_in_territory:
  - mode_id: principled-negotiation
    relationship: depth-heavier sibling (full Fisher-Ury — Wave 3)
  - mode_id: third-side
    relationship: stance-counterpart (mediator-stance, multi-party — Wave 3)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I'm about to enter a negotiation and want to understand the interests on both sides"
    - "the parties are stuck on positions and I want to surface what's underneath"
    - "I want to separate what each side is asking for from what they actually need"
    - "I want a quick interest-map before I commit to a strategy"
  prompt_shape_signals:
    - "interest mapping"
    - "interests vs positions"
    - "Fisher Ury"
    - "what does each side really want"
    - "underlying interests"
    - "negotiation interests"
    - "principled negotiation light"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants quick interest-mapping ahead of or alongside an active negotiation"
    - "user wants the interests-vs-positions distinction applied lightly without full Fisher-Ury orchestration"
    - "the negotiation is two-party (or treated as two-party for the purpose of mapping)"
  routes_away_when:
    - "user wants full Fisher-Ury including BATNA, options-for-mutual-gain, objective-criteria" → principled-negotiation
    - "user wants multi-party mediation perspective" → third-side
    - "user wants descriptive interest-power analysis without negotiation framing" → cui-bono (T2)
    - "user wants stakeholder landscape without active negotiation" → stakeholder-mapping (T8)
when_not_to_invoke:
  - "User has time and depth for full Fisher-Ury" → principled-negotiation
  - "Conflict is multi-party and a single mediator-perspective is needed" → third-side
  - "User is post-negotiation and wants retrospective analysis" → other modes per question shape

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [parties, stated_positions, negotiation_context]
    optional: [prior_negotiation_history, known_underlying_interests, cultural_context]
    notes: "Applies when user supplies named parties with stated positions and at least preliminary context."
  accessible_mode:
    required: [negotiation_or_conflict_description]
    optional: [what_each_side_says_they_want, what_user_suspects_each_side_actually_wants]
    notes: "Default. Mode infers parties and positions from the description."
  detection:
    expert_signals: ["the parties are", "stated positions", "BATNA", "Fisher Ury", "interests vs positions"]
    accessible_signals: ["going into a negotiation", "they're saying X but mean Y", "underlying interests", "what each side really wants"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Who are the parties, and what is each one currently saying they want?'"
    on_underspecified: "Ask: 'For each party, what would they need to walk away feeling the negotiation worked for them?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the analysis maintained the Fisher-Ury distinction between positions (what each party is asking for) and interests (what each party actually needs), or has it conflated the two?"
    failure_mode_if_unmet: position-interest-collapse
  - cq_id: CQ2
    question: "Have inferred interests been distinguished from confirmed interests — i.e., flagged as hypotheses to test in the negotiation rather than asserted as known facts?"
    failure_mode_if_unmet: inference-as-fact
  - cq_id: CQ3
    question: "Has the analysis surfaced both shared/compatible interests (where integrative moves are possible) and genuinely opposed interests (where distributive bargaining or value-based difference remains), rather than presenting the situation as either fully integrative or fully zero-sum?"
    failure_mode_if_unmet: integrative-overreach-or-zero-sum-default

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: position-interest-collapse
    detection_signal: "Inferred interests track stated positions too closely, suggesting the analyst restated what each side asked for in interest-language without descending to underlying need."
    correction_protocol: re-dispatch
  - name: inference-as-fact
    detection_signal: "Inferred interests presented without flagging as hypotheses; flagged-unknowns section is empty."
    correction_protocol: re-dispatch
  - name: integrative-overreach-or-zero-sum-default
    detection_signal: "Output presents the negotiation as either fully solvable through integrative moves (no genuinely opposed interests acknowledged) or fully zero-sum (no shared interests surfaced)."
    correction_protocol: flag
  - name: cultural-context-flatness
    detection_signal: "Interest inferences applied without consideration of how cultural, organizational, or relational context shapes which interests are surfaceable in the negotiation."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - fisher-ury-principled-negotiation
  optional:
    - voss-tactical-empathy (when negotiation is high-stakes or adversarial)
    - lewicki-negotiation-frameworks (when context calls for distributive analysis alongside integrative)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: principled-negotiation
    when: "Negotiation requires full Fisher-Ury including BATNA assessment, options-for-mutual-gain generation, objective-criteria selection."
  sideways:
    target_mode_id: third-side
    when: "Negotiation has more than two parties or requires a mediator-stance rather than a party-stance."
  downward:
    target_mode_id: null
    when: "Interest-mapping is already the lightest mode in T13."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Interest Mapping is the rigor of the position-to-interest descent and the honesty about inferential uncertainty. A thin pass restates positions in interest-language; a substantive pass descends from each party's stated position to the underlying need it serves (security, recognition, autonomy, economic interest, identity, relationship, fairness perception), distinguishes inferred-interests-as-hypotheses from confirmed-interests, and surfaces both shared-and-compatible interests (integrative-move candidates) and genuinely-opposed interests (where distributive remains). Test depth by asking: could the analysis tell the user which inferred interest, if confirmed in the negotiation, would unlock an integrative move, and which inferred interest, if disconfirmed, would require pivoting?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means surveying the interest categories per party (substantive economic, procedural, relational, identity-and-recognition, security, fairness-perception, future-relationship), considering interests not visible from each party's own stated position (interests they may not have articulated to themselves), and noting cultural or contextual factors that shape which interests are surfaceable in the negotiation. Breadth markers: at least three interest-category candidates are considered per party; the possibility of unstated or unconscious interests is acknowledged.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Interest Mapping is a light Fisher-Ury reading that walks each party's stated position down to the underlying interest it serves and separates compatible interests (where integrative moves are possible) from genuinely opposed interests (where distributive bargaining or value-difference remains). It is descriptive of the interest landscape, not prescriptive of negotiation strategy — it sits one step before principled-negotiation (its depth-heavier sibling, which adds BATNA, options-for-mutual-gain, and objective-criteria) and is distinct from cui-bono (descriptive interest-power analysis without a negotiation frame) and stakeholder-mapping (landscape view without active negotiation). The mode treats inferred interests as hypotheses to test, not as facts to assert.

**Procedure.**

1. Name parties and stated positions — each party's ask in their own vocabulary or close to it.
2. Descend from each position to the underlying interest categories it may serve (substantive economic, procedural, relational, identity-and-recognition, security, fairness-perception, future-relationship) — symmetric descent across parties.
3. Flag each inferred interest as a hypothesis to test, not a confirmed fact; surface flagged-unknowns the user could probe in the negotiation itself.
4. Survey shared and compatible interests — where both sides could leave better off than under positional bargaining.
5. Survey genuinely-opposed interests — where the parties' satisfaction is structurally in tension and integrative moves cannot dissolve it.
6. Generate candidate integrative moves keyed to interest patterns — each with the interest hypotheses the move depends on and what would invalidate it.
7. Note cultural / organisational / relational context where it shapes which interests are surfaceable.
8. Assign three distinct confidence kinds — high for stated positions (what parties actually said), lower for inferred interests (hypothesis quality), conditional for candidate moves (depends on testing).

**Goal.** Produce an interest map that descends from stated positions to underlying interests, separates compatible from opposed territory, names candidate integrative moves with their dependencies, and surfaces the unknowns to test in the negotiation.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — position vs interest distinction.** Has the analysis maintained the Fisher-Ury distinction between positions (what each party asks for) and interests (what each party needs), or conflated them? Failure mode if unmet: `position-interest-collapse`.
- **CQ2 — inferred vs confirmed.** Have inferred interests been distinguished from confirmed interests — flagged as hypotheses to test rather than asserted as known facts? Failure mode if unmet: `inference-as-fact`.
- **CQ3 — shared and opposed both surfaced.** Has the analysis surfaced both shared/compatible interests (integrative territory) and genuinely opposed interests (distributive territory), rather than presenting the situation as either fully integrative or fully zero-sum? Failure mode if unmet: `integrative-overreach-or-zero-sum-default`.

A passing output names parties and positions, descends to inferred interests symmetrically with explicit hypothesis-flagging, surfaces both compatible and opposed interest territories, names at least one candidate integrative move with its supporting interest-pattern, lists testable flagged-unknowns, and keeps three confidence kinds distinct.

**Named failure modes.**

- *position-interest-collapse* — inferred interests track stated positions too closely; the analyst restated asks in interest-language without descending to underlying need.
- *inference-as-fact* — inferred interests presented without hypothesis flagging; flagged-unknowns section is empty.
- *integrative-overreach-or-zero-sum-default* — output presents the negotiation as either fully solvable through integrative moves (no opposed interests acknowledged) or fully zero-sum (no shared interests surfaced).
- *cultural-context-flatness* — interest inferences applied without considering how cultural, organisational, or relational context shapes which interests are surfaceable in the negotiation.

## REVISION GUIDANCE

Revise to descend from positions to interests where the draft restated positions in interest-language. Revise to flag inferred interests as hypotheses where the draft asserted them as facts. Revise to surface both compatible and opposed interests where the draft defaulted to one or the other. Resist revising toward optimism — the mode's analytical character is descriptive of the interest landscape, including its genuinely-opposed regions. Manufactured integrative possibility is a failure mode, not a polish.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Fisher-Ury position-to-interest descent: parties with stated positions, inferred underlying-interest atoms per party with explicit hypothesis-flagging, shared/compatible-interest atoms, genuinely-opposed-interest atoms, candidate integrative-move atoms keyed to interest patterns, and flagged unknowns testable in negotiation**. The atoms are:

1. **Party-and-stated-position atoms.** Each atom carries: party name and the party's stated position (what they're asking for, in their own vocabulary or close to it). Positions are reported as stated; the interest-descent happens at the next layer.

2. **Inferred-interest atoms per party.** Each atom names one underlying interest (substantive economic, procedural, relational, identity-and-recognition, security, fairness-perception, future-relationship) that the stated position may serve. Each atom carries an explicit hypothesis flag: `inferred — to test` rather than `confirmed`. Position-interest-collapse is the named failure mode the consolidator watches for; atoms where the inferred interest tracks the stated position too closely (restating asks in interest-language) get reshaped to descend further. Inference-as-fact is the named failure mode for missing hypothesis flags.

3. **Shared/compatible-interest atoms.** Each atom names an interest both parties share or that admits compatible satisfaction — where an integrative move is possible because both sides could leave better off than under positional bargaining.

4. **Genuinely-opposed-interest atoms.** Each atom names an interest where the parties' satisfaction is structurally in tension — where distributive bargaining or honest value-difference remains. Integrative-overreach is the named failure mode here; corpus that presents the negotiation as fully solvable through integrative moves (no genuinely opposed interests acknowledged) gets reshaped to surface what does not dissolve.

5. **Candidate integrative-move atoms.** Each atom carries: the proposed move, the underlying-interest pattern that would make the move possible (e.g., "Party A values X highly but B values it low; B values Y highly but A values it low — trade"), and the interest hypotheses the move depends on (which must hold for the move to land).

6. **Flagged-unknown atoms.** Each atom names a question the user could ask or test in the negotiation that would confirm or disconfirm an inferred interest. These are testable, not rhetorical. Inference-as-fact is the named failure mode; corpus that lacks flagged-unknown atoms when inferred-interest atoms are present gets reshaped to surface what to test.

7. **Cultural-and-relational-context flag — when applicable.** When cultural, organisational, or relational context shapes which interests are surfaceable in the negotiation (some interests are face-loss to articulate; some require third-party mediation; some carry historical baggage), the flag is preserved. Cultural-context-flatness is the named failure mode.

8. **Zero-sum-default flag — when applicable.** When streams defaulted to fully-zero-sum framing without surfacing any shared interests, the flag is preserved. Integrative-overreach and zero-sum-default are mirror-image failures; the corpus standard is honest two-territory mapping.

9. **Confidence per finding** — three confidence kinds kept separate: confidence in positions (high — these are what the parties actually said), confidence in inferred interests (often lower — these are hypotheses), confidence in candidate moves (depends on testing the interest hypotheses).

**Mode-specific bloat patterns to cut:**

- **Position-interest-collapse** — interest-language that restates positions without descending to underlying need.
- **Inference-as-fact** — inferred interests presented as known facts without hypothesis flagging.
- **Integrative-overreach** — manufactured shared interests; the corpus invents compatibility that doesn't survive scrutiny.
- **Zero-sum default** — the situation framed as fully distributive without surfacing the integrative territory.
- **Cultural-context flatness** — interest inferences applied without considering whether those interests are surfaceable in this specific cultural/organisational/relational context.
- **Fisher-Ury optimism** — the integrative frame applied dogmatically without acknowledging that some negotiations are adversarial and require tactical-empathy (Voss) or distributive-bargaining (Lewicki) supplementation.
- **Single-party interest analysis** — descending to interests for one party while leaving the other's at the position level. Symmetric descent is the corpus standard.

**What NOT to collapse:**

- **Genuinely opposed interests** — never smoothed over with manufactured integrative possibility. The mode's analytical character includes surfacing what does not dissolve.
- **Multiple plausible underlying interests for the same position** — when a stated position could serve more than one underlying interest (e.g., a price demand could serve economic interest, fairness-perception, or face-saving), all candidate interests survive as competing hypotheses.
- **Stream disagreement about whether an interest is shared or opposed** — when one stream classified an interest as compatible and another as opposed, the disagreement is itself a flagged-unknown to test.
- **Cultural-context-dependent interests** — interests that are surfaceable in one context and not in another stay flagged with their surfaceability conditions; the corpus does not assume a culturally-flat negotiation.

## VERIFICATION CRITERIA

Verified means: parties and stated positions are named; inferred underlying interests are itemized per party with hypothesis-flagging; shared/compatible interests and genuinely-opposed interests are separately surfaced; at least one candidate integrative move is named with its supporting interest-pattern; flagged unknowns are listed as testable in negotiation; the three critical questions are addressable from the output. Confidence per major finding accompanies each claim.

## OUTPUT FORMAT GUIDANCE

The deliverable is an **interest map** — a structured Fisher-Ury reading that walks each party's stated position down to inferred underlying interests, separates compatible from opposed territory, and surfaces both candidate integrative moves and the unknowns to test in the negotiation. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Parties and stated positions.** A table or per-party block. Each: `**[Party]** — stated position: "[what they're asking for, in their own vocabulary or close to it]." Context: [brief note on stakes, time-pressure, or relational standing].`

2. **Inferred underlying interests per party.** Per party, a labelled sub-block listing inferred interests, each tagged as an hypothesis. Each: `**[Interest category — substantive economic / procedural / relational / identity-and-recognition / security / fairness-perception / future-relationship]** — what the interest is: [...]. Inferred from: [evidence in stated position or context]. Status: hypothesis (to test in negotiation).` Symmetric descent across parties; one-sided interest analysis is reshaped at this layer.

3. **Shared or compatible interests.** Bulleted list. Each: `**[Shared interest]** — how it appears for each party: [...]. Why integrative satisfaction is possible: [...].`

4. **Genuinely opposed interests.** Bulleted list. Each: `**[Opposed interest]** — how it appears for each party: [...]. What makes the opposition structural (not merely positional): [...].` This section is never empty when the corpus carried opposed-interest atoms; smoothing over opposition is reshaped at this layer.

5. **Candidate integrative moves.** Numbered list. Each: `[N]. **[Integrative move]** — interest pattern that makes it possible: [...]. Interest hypotheses the move depends on: [...]. What would invalidate the move: [...].`

6. **Flagged unknowns to test.** Bulleted list. Each: `**[Question to test in negotiation]** — what it confirms or disconfirms: [interest hypothesis]. How the answer changes the integrative-move landscape: [...].` These are concrete; rhetorical questions are reshaped at this layer.

7. **Confidence per finding.** Three labelled confidence assessments, kept distinct:
   - `Stated positions: [confidence and basis — typically high].`
   - `Inferred interests: [confidence and basis — typically lower; hypothesis quality].`
   - `Candidate integrative moves: [confidence and basis — depends on testing].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- The Fisher-Ury vocabulary (positions vs. interests, integrative moves, BATNA where it surfaces) is operative; paraphrasing into generic negotiation language is reshaped at this layer.
- Symmetric descent across parties — if Party A has three inferred interests at three depths, Party B does too. Asymmetric descent is reshaped here.
- When the cultural-and-relational-context flag survived consolidation, section 2 closes with: `**Context note:** [which interests may be unsurfaceable in this specific cultural / organisational / relational context, and what that means for the integrative-move feasibility].`
- When the Fisher-Ury frame may be inadequate for an adversarial-stakes negotiation (the Voss critique applies), the deliverable opens with: `**Note: the integrative frame below is Fisher-Ury baseline; in genuinely adversarial high-stakes negotiation, tactical-empathy (Voss) and distributive-bargaining (Lewicki) lenses may be needed in addition. Escalation to principled-negotiation (full Fisher-Ury including BATNA) is the upward route.**`
- When the zero-sum-default flag survived consolidation, section 3 opens with: `**Note: shared interests below are surfaced against an initial framing that read the situation as fully distributive; the integrative territory may be larger than it appeared.**`
- Confidence (section 7) stays as three distinct kinds; blending into a single confidence is reshaped at this layer.

## CAVEATS AND OPEN DEBATES

**Debate D6 — Fisher-Ury sufficiency for adversarial contexts; Voss critique.** Fisher and Ury's *Getting to Yes* (1981, with Patton's later editions) frames negotiation as fundamentally integrative-possible: separate people from problem, focus on interests not positions, generate options for mutual gain, use objective criteria. The framework has been transformative in commercial and diplomatic contexts where the parties share an interest in reaching agreement and where the integrative possibility-space is real. Chris Voss's *Never Split the Difference* (2016) and the broader practitioner literature on hostage negotiation, high-stakes commercial bargaining, and politically adversarial negotiation argue that Fisher-Ury underweights tactical empathy, emotional dynamics, distributive reality, and the role of perceived loss and ego in many real negotiations — and that in genuinely adversarial contexts the integrative frame can be naive or actively counterproductive. This mode does not adjudicate the debate. It uses Fisher-Ury as the primary lens because the position-vs-interest descent is robust across contexts, while flagging that in high-stakes adversarial negotiations the user may need to escalate to principled-negotiation (full Fisher-Ury including BATNA) and may benefit from supplementing with Voss-style tactical-empathy lenses (carried optionally per the lens_dependencies). The integrative-overreach failure mode exists precisely to guard against the Fisher-Ury optimism trap. Citations: Fisher, Ury & Patton 1981/2011 *Getting to Yes*; Voss & Raz 2016 *Never Split the Difference*; Lewicki et al. negotiation textbook tradition for the distributive/integrative distinction.

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

**Prioritize:** `requires`, `enables`, `contradicts`, `supports`, `qualifies`
**Deprioritize:** `parent`, `analogous-to`

*Family: stakeholder-strategy. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
