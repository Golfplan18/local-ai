---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Principled Negotiation

```yaml
# 0. IDENTITY
mode_id: principled-negotiation
canonical_name: Principled Negotiation
suffix_rule: analysis
educational_name: principled negotiation (Fisher-Ury full method)

# 1. TERRITORY AND POSITION
territory: T13-negotiation-and-conflict-resolution
gradation_position:
  axis: depth
  value: thorough
adjacent_modes_in_territory:
  - mode_id: interest-mapping
    relationship: depth-lighter sibling (Fisher-Ury position-vs-interest descent only; built Wave 2)
  - mode_id: third-side
    relationship: stance-counterpart (mediator-stance + complexity-multi-party; Ury; Wave 3)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I'm preparing for a substantive negotiation and want the full Fisher-Ury treatment"
    - "I need BATNA, options-for-mutual-gain, and objective-criteria worked out together"
    - "the parties are stuck on positions and I need a structured way to get to interests, options, and a defensible standard"
    - "want to walk into the room with my best alternative clear and integrative options ready"
    - "want a thorough negotiation prep, not a quick interest scan"
  prompt_shape_signals:
    - "principled negotiation"
    - "Fisher Ury"
    - "Getting to Yes"
    - "BATNA"
    - "best alternative to negotiated agreement"
    - "options for mutual gain"
    - "objective criteria"
    - "separate the people from the problem"
    - "negotiation prep"
    - "full negotiation analysis"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants the full four-element Fisher-Ury method (people/problem separation, interests-not-positions, mutual-gain options, objective criteria) plus BATNA"
    - "user has time and depth for a thorough negotiation analysis (~5min)"
    - "negotiation is two-party (or treated as two-party from the user's vantage) and the user is a party"
  routes_away_when:
    - "user wants only quick interest-mapping without full method" → interest-mapping
    - "user wants multi-party mediator perspective rather than party perspective" → third-side
    - "user wants descriptive interest-power analysis without negotiation framing" → cui-bono (T2)
    - "user wants stakeholder landscape without active negotiation" → stakeholder-mapping (T8)
    - "user wants strategic-game analysis (equilibria, signaling, mechanism design)" → strategic-interaction (T18)
when_not_to_invoke:
  - "User wants only the position-to-interest descent" → interest-mapping
  - "Conflict is multi-party and a single mediator-perspective is needed" → third-side
  - "User is post-negotiation and wants retrospective forensic analysis" → other modes per question shape
  - "User has no time for thorough analysis" → interest-mapping

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: constructive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [parties, stated_positions, negotiation_context, user_party_role, current_batna_estimate]
    optional: [prior_negotiation_history, known_underlying_interests, cultural_context, available_objective_standards, time_pressure, relational_history]
    notes: "Applies when user supplies named parties with stated positions, identifies their own role, and offers at least a preliminary BATNA estimate."
  accessible_mode:
    required: [negotiation_or_conflict_description, user_role_in_negotiation]
    optional: [what_each_side_says_they_want, what_user_suspects_each_side_actually_wants, what_user_would_do_if_no_deal, time_or_relational_pressure]
    notes: "Default. Mode infers parties, positions, and BATNA from the description."
  detection:
    expert_signals: ["BATNA", "ZOPA", "objective criteria", "options for mutual gain", "Fisher Ury full", "principled negotiation", "Getting to Yes", "reservation price"]
    accessible_signals: ["preparing for a negotiation", "what's my best alternative", "how do I get to a deal", "we're stuck on positions"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Who are the parties, what is each one currently saying they want, and what is your role in the negotiation?'"
    on_underspecified: "Ask: 'What would you do if no agreement is reached — that is your best alternative, and we need at least a preliminary version of it?'"
output_contract:
  artifact_type: synthesis
  required_sections:
    - parties_and_stated_positions
    - people_problem_separation_diagnosis
    - inferred_underlying_interests_per_party
    - shared_or_compatible_interests
    - genuinely_opposed_interests
    - options_for_mutual_gain
    - objective_criteria_candidates
    - user_batna_assessment
    - inferred_counterparty_batna
    - recommended_opening_and_fallback_pattern
    - flagged_unknowns_to_test
    - confidence_per_finding
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the analysis maintained the Fisher-Ury distinction between positions (what each party is asking for) and interests (what each party actually needs), or has it conflated the two?"
    failure_mode_if_unmet: position-interest-collapse
  - cq_id: CQ2
    question: "Have inferred interests, BATNAs, and counterparty motivations been distinguished from confirmed ones — i.e., flagged as hypotheses to test rather than asserted as known facts?"
    failure_mode_if_unmet: inference-as-fact
  - cq_id: CQ3
    question: "Has the analysis surfaced both shared/compatible interests (where integrative moves are possible) and genuinely opposed interests (where distributive bargaining or value-based difference remains), rather than presenting the situation as either fully integrative or fully zero-sum?"
    failure_mode_if_unmet: integrative-overreach-or-zero-sum-default
  - cq_id: CQ4
    question: "Is the user's BATNA assessed concretely (with the actual alternative described, costed, and walked-through), or is it asserted abstractly as a placeholder?"
    failure_mode_if_unmet: batna-as-placeholder
  - cq_id: CQ5
    question: "Are the proposed objective criteria genuinely objective (third-party standards, market data, precedent, expert opinion that both parties could plausibly accept), or are they the user's preferences in objective-sounding language?"
    failure_mode_if_unmet: pseudo-objective-criteria
  - cq_id: CQ6
    question: "Has the people-problem separation diagnosis identified specific perception, emotion, and communication issues that would benefit from separate handling, rather than treating people-problem separation as a slogan?"
    failure_mode_if_unmet: people-problem-conflation

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: position-interest-collapse
    detection_signal: "Inferred interests track stated positions too closely, suggesting the analyst restated what each side asked for in interest-language without descending to underlying need."
    correction_protocol: re-dispatch
  - name: inference-as-fact
    detection_signal: "Inferred interests, BATNAs, or counterparty motivations presented without flagging as hypotheses; flagged-unknowns section is empty or thin."
    correction_protocol: re-dispatch
  - name: integrative-overreach-or-zero-sum-default
    detection_signal: "Output presents the negotiation as either fully solvable through integrative moves (no genuinely opposed interests acknowledged) or fully zero-sum (no shared interests surfaced or no options-for-mutual-gain generated)."
    correction_protocol: flag
  - name: batna-as-placeholder
    detection_signal: "User BATNA section asserts an alternative without describing it concretely, costing it, or walking through what would actually happen if the negotiation fails."
    correction_protocol: re-dispatch
  - name: pseudo-objective-criteria
    detection_signal: "Proposed objective criteria align suspiciously well with the user's preferred outcome; no third-party-acceptable standards are surfaced."
    correction_protocol: re-dispatch
  - name: people-problem-conflation
    detection_signal: "People-problem separation section is a generic gesture rather than diagnosing specific perception, emotion, and communication issues to handle separately."
    correction_protocol: flag
  - name: cultural-context-flatness
    detection_signal: "Interest inferences, BATNA assessments, and recommended openings applied without consideration of how cultural, organizational, or relational context shapes which moves are available in the negotiation."
    correction_protocol: flag
  - name: voss-warning-unflagged
    detection_signal: "Negotiation context is high-stakes adversarial (hostage-style, deeply distributive, or strongly asymmetric power) and the analysis applies Fisher-Ury without flagging the limitations the Voss critique surfaces (tactical empathy, emotional dynamics, perceived loss, ego); see Debate D6."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - fisher-ury-principled-negotiation
  optional:
    - voss-tactical-empathy (when negotiation is high-stakes or adversarial)
    - lewicki-negotiation-frameworks (when context calls for distributive analysis alongside integrative)
    - raiffa-art-and-science-of-negotiation (when ZOPA / reservation-price modeling is needed)
    - thompson-mind-and-heart-of-the-negotiator (when emotional dynamics or cross-cultural framing matters)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Principled Negotiation is the deepest single-party negotiation mode in T13; further depth comes from iterating with new information or escalating to multi-party mediation."
  sideways:
    target_mode_id: third-side
    when: "Negotiation has more than two parties or requires a mediator-stance rather than a party-stance."
  downward:
    target_mode_id: interest-mapping
    when: "User has time pressure or wants only the position-to-interest descent without full BATNA / options / objective-criteria work."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Principled Negotiation is the rigor of all four Fisher-Ury elements *plus* BATNA, treated as load-bearing rather than decorative. A thin pass restates positions in interest-language and lists generic options. A substantive pass: (1) diagnoses specific people-problem issues (perception gaps, emotional triggers, communication failures) that need separate handling from substantive bargaining; (2) descends from each party's stated position to the underlying need it serves (security, recognition, autonomy, economic interest, identity, relationship, fairness perception), distinguishing inferred-from-confirmed; (3) generates options for mutual gain that respond to the interest pattern (not generic compromise positions but moves that satisfy more interest on more sides); (4) names objective criteria (third-party-acceptable standards: market data, precedent, expert opinion, principle) for evaluating proposals without contest of will; (5) assesses the user's BATNA concretely (the actual alternative described, costed, walked-through, with its weaknesses surfaced); (6) infers the counterparty's BATNA with explicit hypothesis-flagging. Test depth by asking: could the analysis tell the user which inferred interest, if confirmed in the negotiation, would unlock an integrative move; which objective criterion the counterparty is most likely to accept; and at what point the user should walk away to their BATNA?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means surveying the interest categories per party (substantive economic, procedural, relational, identity-and-recognition, security, fairness-perception, future-relationship); considering BATNA categories beyond the obvious (no-deal-and-walk-away, partial-deal, deal-with-a-different-party, deal-deferred, regulatory-or-legal-alternative, public-pressure-route); scanning objective-criteria categories (market value, precedent, expert opinion, scientific judgment, professional standards, efficiency, costs, what-a-court-would-decide, moral standards, equal treatment, tradition); and noting cultural or contextual factors that shape which moves are available. Breadth markers: at least three interest-category candidates per party; at least two BATNA candidates for the user (sometimes the second is the strongest); at least three objective-criteria candidates with reasoning about counterparty acceptance. The Voss critique scan (Debate D6) is part of breadth: where adversarial dynamics dominate, surface them rather than papering over with integrative framing.

## EVALUATION CRITERIA

Evaluate against the six critical questions: (CQ1) position-vs-interest distinction maintained; (CQ2) inferred-vs-confirmed flagged across interests, BATNAs, and motivations; (CQ3) shared and opposed both surfaced; (CQ4) BATNA concrete not placeholder; (CQ5) objective criteria genuinely third-party-acceptable; (CQ6) people-problem separation specific not slogan. The named failure modes are the evaluation checklist. A passing Principled Negotiation output has all twelve required sections populated, with hypothesis-flagging on inferred content, concrete BATNA description (the alternative is walkable-through), and at least one Voss-style adversarial-context flag if context warrants it.

## REVISION GUIDANCE

Revise to descend from positions to interests where the draft restated positions. Revise to flag inferences where the draft asserted facts. Revise to surface both compatible and opposed interests where the draft defaulted to one. Revise to make BATNA concrete where it is placeholder. Revise to find genuinely third-party-acceptable criteria where the draft offered the user's preferences in objective-sounding language. Revise to diagnose specific people-problem issues where the draft gestured generically. Resist revising toward optimism — the mode's character is constructive (it generates options, recommends openings) but honest about the interest landscape, including its genuinely-opposed regions and adversarial-context limitations. Manufactured integrative possibility is a failure mode, not a polish. The Voss-warning flag (Debate D6) is part of honest revision when context warrants it.

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the twelve required sections. Parties and stated positions appear first. People-problem diagnosis follows (specific perception/emotion/communication issues to handle separately). Inferred interests are listed per party with hypothesis-flagging; shared/compatible and genuinely-opposed appear as separate sections. Options for mutual gain appear with the underlying interest-pattern that would make each option possible. Objective criteria are listed with reasoning about counterparty acceptance. User BATNA is described concretely (the alternative, its cost, what would actually happen). Inferred counterparty BATNA is hypothesis-flagged. Recommended opening-and-fallback pattern is specific (opening move, expected counter, fallback options keyed to BATNA). Flagged unknowns are testable in the negotiation. Confidence per finding distinguishes positions (high confidence) from inferred interests/BATNAs/motivations (often lower) from candidate moves (depends on testing).

## VERIFICATION CRITERIA

Verified means: parties and stated positions named; people-problem diagnosis specific; inferred interests itemized per party with hypothesis-flagging; shared/compatible and genuinely-opposed interests separately surfaced; at least two options-for-mutual-gain named with supporting interest-pattern; at least three objective-criteria candidates with counterparty-acceptance reasoning; user BATNA described concretely (described, costed, walked-through); counterparty BATNA hypothesis-flagged; opening-and-fallback recommendation specific; flagged unknowns listed as testable; the six critical questions are addressable from the output. Confidence per major finding accompanies each claim. If context is high-stakes adversarial, the Voss-critique flag (Debate D6) is present.

## CAVEATS AND OPEN DEBATES

**Debate D6 — Fisher-Ury sufficiency for adversarial contexts; Voss critique.** Fisher and Ury's *Getting to Yes* (1981, with Patton's later editions) frames negotiation as fundamentally integrative-possible: separate people from problem, focus on interests not positions, generate options for mutual gain, use objective criteria. The framework has been transformative in commercial and diplomatic contexts where the parties share an interest in reaching agreement and where the integrative possibility-space is real. Chris Voss's *Never Split the Difference* (2016) and the broader practitioner literature on hostage negotiation, high-stakes commercial bargaining, and politically adversarial negotiation argue that Fisher-Ury underweights tactical empathy, emotional dynamics, distributive reality, and the role of perceived loss and ego in many real negotiations — and that in genuinely adversarial contexts the integrative frame can be naive or actively counterproductive. Voss-derived practice emphasizes calibrated questions, mirroring, labeling emotions, the "no" that opens engagement, the late-stage "Black Swan" information asymmetries, and the recognition that distribution, not integration, often dominates the late-game bargaining. Lewicki and others document the distributive/integrative continuum and warn against assuming integrative possibility where it is absent.

This mode does not adjudicate the debate. It uses Fisher-Ury as the primary lens because the four-element method (people-problem separation, interests-not-positions, options-for-mutual-gain, objective-criteria) plus BATNA is the most-tested integrative framework available, and because the position-vs-interest descent is robust across contexts. The mode flags adversarial-context limitations explicitly when the situation warrants — the `voss-warning-unflagged` failure mode and the `voss-tactical-empathy` optional lens are the structural mechanisms. The integrative-overreach failure mode exists precisely to guard against the Fisher-Ury optimism trap. In genuinely adversarial contexts, the user may need to supplement this mode with Voss-style tactical-empathy lenses (carried optionally), or to recognize that the analysis is offering the integrative-possibility-space the situation may not contain. Citations: Fisher, Ury & Patton 1981/2011 *Getting to Yes*; Voss & Raz 2016 *Never Split the Difference*; Lewicki et al. negotiation textbook tradition for the distributive/integrative distinction; Raiffa 1982 *The Art and Science of Negotiation* for ZOPA / reservation-price modeling; Thompson 2020 *The Mind and Heart of the Negotiator* for cross-cultural and emotional dimensions.
