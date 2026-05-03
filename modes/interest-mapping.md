---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
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
output_contract:
  artifact_type: mapping
  required_sections:
    - parties_and_stated_positions
    - inferred_underlying_interests_per_party
    - shared_or_compatible_interests
    - genuinely_opposed_interests
    - candidate_integrative_moves
    - flagged_unknowns_to_test
    - confidence_per_finding
  format: structured

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

## EVALUATION CRITERIA

Evaluate against the three critical questions: (CQ1) position-vs-interest distinction maintained; (CQ2) inferred vs. confirmed flagged; (CQ3) shared and opposed both surfaced. The named failure modes (position-interest-collapse, inference-as-fact, integrative-overreach-or-zero-sum-default, cultural-context-flatness) are the evaluation checklist. A passing Interest Mapping output names parties and positions, descends to inferred interests with hypothesis-flagging, and surfaces both compatible and opposed interest territories.

## REVISION GUIDANCE

Revise to descend from positions to interests where the draft restated positions in interest-language. Revise to flag inferred interests as hypotheses where the draft asserted them as facts. Revise to surface both compatible and opposed interests where the draft defaulted to one or the other. Resist revising toward optimism — the mode's analytical character is descriptive of the interest landscape, including its genuinely-opposed regions. Manufactured integrative possibility is a failure mode, not a polish.

## CONSOLIDATION GUIDANCE

Consolidate as a structured mapping with the seven required sections. Parties and stated positions appear first. Inferred underlying interests are listed per party with hypothesis-flagging. Shared/compatible interests and genuinely-opposed interests appear as separate sections. Candidate integrative moves appear with the underlying-interest pattern that would make each move possible. Flagged unknowns are presented as questions the user could test in the negotiation. Confidence-per-finding distinguishes confidence in positions (high) from confidence in inferred interests (often lower) from confidence in candidate moves (depends on testing).

## VERIFICATION CRITERIA

Verified means: parties and stated positions are named; inferred underlying interests are itemized per party with hypothesis-flagging; shared/compatible interests and genuinely-opposed interests are separately surfaced; at least one candidate integrative move is named with its supporting interest-pattern; flagged unknowns are listed as testable in negotiation; the three critical questions are addressable from the output. Confidence per major finding accompanies each claim.

## CAVEATS AND OPEN DEBATES

**Debate D6 — Fisher-Ury sufficiency for adversarial contexts; Voss critique.** Fisher and Ury's *Getting to Yes* (1981, with Patton's later editions) frames negotiation as fundamentally integrative-possible: separate people from problem, focus on interests not positions, generate options for mutual gain, use objective criteria. The framework has been transformative in commercial and diplomatic contexts where the parties share an interest in reaching agreement and where the integrative possibility-space is real. Chris Voss's *Never Split the Difference* (2016) and the broader practitioner literature on hostage negotiation, high-stakes commercial bargaining, and politically adversarial negotiation argue that Fisher-Ury underweights tactical empathy, emotional dynamics, distributive reality, and the role of perceived loss and ego in many real negotiations — and that in genuinely adversarial contexts the integrative frame can be naive or actively counterproductive. This mode does not adjudicate the debate. It uses Fisher-Ury as the primary lens because the position-vs-interest descent is robust across contexts, while flagging that in high-stakes adversarial negotiations the user may need to escalate to principled-negotiation (full Fisher-Ury including BATNA) and may benefit from supplementing with Voss-style tactical-empathy lenses (carried optionally per the lens_dependencies). The integrative-overreach failure mode exists precisely to guard against the Fisher-Ury optimism trap. Citations: Fisher, Ury & Patton 1981/2011 *Getting to Yes*; Voss & Raz 2016 *Never Split the Difference*; Lewicki et al. negotiation textbook tradition for the distributive/integrative distinction.
