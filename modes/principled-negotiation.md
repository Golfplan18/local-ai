---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

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

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Principled Negotiation is the full Fisher-Ury method — people-problem separation, interests-not-positions, options-for-mutual-gain, objective-criteria — plus BATNA assessment on both sides plus a specific opening-and-fallback pattern. The mode is constructive (it generates options and recommends openings) but honest about the interest landscape, including its genuinely-opposed regions. It is the depth-thorough position in T13's negotiation territory, sitting above interest-mapping (depth-lighter; position-to-interest descent only), distinct from third-side (stance-counterpart; mediator perspective in multi-party conflicts), and parallel to cui-bono (descriptive interest-power analysis without negotiation framing). The Voss critique applies in genuinely adversarial contexts where tactical-empathy lenses may need to supplement the integrative frame.

**Procedure.**

1. Name parties and stated positions in each party's own vocabulary; identify the user's role.
2. Diagnose people-problem separation specifics — particular perception gaps, emotional triggers, communication failures that need separate handling from the substantive bargaining; not generic gestures.
3. Descend from each position to the underlying interests it serves (substantive economic, procedural, relational, identity-and-recognition, security, fairness-perception, future-relationship) with symmetric descent across parties and explicit hypothesis-flagging on inferred interests.
4. Separate shared/compatible interests from genuinely-opposed interests — surface both territories without smoothing one into the other.
5. Generate options for mutual gain keyed to the interest pattern — differential valuation, contingency, dovetailing of differences, shared cost reduction — that satisfy more interest on more sides, not generic compromise.
6. Surface objective-criteria candidates (market data, precedent, expert opinion, scientific judgment, professional standards, efficiency, costs, court-decision, moral standards, equal-treatment, tradition) with reasoning about why the counterparty could plausibly accept each.
7. Assess the user's BATNA concretely — the actual alternative described, costed, walked-through, with its weaknesses surfaced.
8. Infer the counterparty's BATNA with explicit hypothesis-flagging and the evidence basis.
9. Generate a specific opening-and-fallback pattern — opening move, expected counter, fallback options keyed to BATNA, walk-away threshold.
10. Surface flagged-unknowns the user could test in the negotiation.
11. Scan for Voss-warning conditions — high-stakes adversarial, hostage-style, deeply distributive, strongly asymmetric power — and flag where Fisher-Ury alone may be insufficient.
12. Hold three confidence kinds distinct — high for stated positions, lower for inferred interests/BATNAs/motivations, conditional for candidate moves.

**Goal.** Produce a principled negotiation preparation covering all four Fisher-Ury elements plus BATNA on both sides plus a specific opening-and-fallback pattern, with hypothesis-flagging on inferred content, walkable-through BATNA description, and a Voss-warning flag where context warrants.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — position vs interest distinction.** Has the analysis maintained the Fisher-Ury distinction between positions (what each party asks for) and interests (what each party needs), or conflated them? Failure mode if unmet: `position-interest-collapse`.
- **CQ2 — inferred vs confirmed.** Have inferred interests, BATNAs, and counterparty motivations been distinguished from confirmed ones — flagged as hypotheses to test rather than asserted as known facts? Failure mode if unmet: `inference-as-fact`.
- **CQ3 — shared and opposed both surfaced.** Has the analysis surfaced both shared/compatible interests (integrative) and genuinely-opposed interests (distributive), rather than presenting the situation as fully integrative or fully zero-sum? Failure mode if unmet: `integrative-overreach-or-zero-sum-default`.
- **CQ4 — BATNA concreteness.** Is the user's BATNA assessed concretely (the actual alternative described, costed, walked-through), or asserted abstractly as a placeholder? Failure mode if unmet: `batna-as-placeholder`.
- **CQ5 — objective criteria.** Are the proposed objective criteria genuinely objective (third-party standards both parties could plausibly accept), or the user's preferences in objective-sounding language? Failure mode if unmet: `pseudo-objective-criteria`.
- **CQ6 — people-problem specificity.** Has the people-problem separation diagnosis identified specific perception, emotion, and communication issues that would benefit from separate handling, rather than treating people-problem separation as a slogan? Failure mode if unmet: `people-problem-conflation`.

A passing output populates all twelve required sections — parties, people-problem diagnosis, inferred interests per party with hypothesis flags, shared/opposed interests both surfaced, ≥2 options-for-mutual-gain with supporting interest-pattern, ≥3 objective-criteria with counterparty-acceptance reasoning, walkable-through user-BATNA, hypothesis-flagged counterparty-BATNA, specific opening-and-fallback pattern with walk-away threshold, testable flagged-unknowns, three distinct confidence kinds, and a Voss-warning flag if context warrants.

**Named failure modes.**

- *position-interest-collapse* — inferred interests track stated positions too closely; the analyst restated asks in interest-language without descending to underlying need.
- *inference-as-fact* — inferred interests, BATNAs, or counterparty motivations presented without hypothesis flags; flagged-unknowns section empty or thin.
- *integrative-overreach-or-zero-sum-default* — negotiation framed as either fully solvable through integrative moves (no opposed interests acknowledged) or fully zero-sum (no shared interests or mutual-gain options generated).
- *batna-as-placeholder* — user BATNA asserted abstractly without concrete description, cost, or walk-through.
- *pseudo-objective-criteria* — proposed criteria align suspiciously with the user's preferred outcome; no third-party-acceptable standards surfaced.
- *people-problem-conflation* — people-problem separation section is a generic gesture rather than diagnosing specific perception, emotion, and communication issues.
- *cultural-context-flatness* — interest inferences, BATNA assessments, and recommended openings applied without considering how cultural, organisational, or relational context shapes which moves are available.
- *voss-warning-unflagged* — high-stakes adversarial context with Fisher-Ury applied uncritically; Voss-critique limitations not flagged where they apply.

## REVISION GUIDANCE

Revise to descend from positions to interests where the draft restated positions. Revise to flag inferences where the draft asserted facts. Revise to surface both compatible and opposed interests where the draft defaulted to one. Revise to make BATNA concrete where it is placeholder. Revise to find genuinely third-party-acceptable criteria where the draft offered the user's preferences in objective-sounding language. Revise to diagnose specific people-problem issues where the draft gestured generically. Resist revising toward optimism — the mode's character is constructive (it generates options, recommends openings) but honest about the interest landscape, including its genuinely-opposed regions and adversarial-context limitations. Manufactured integrative possibility is a failure mode, not a polish. The Voss-warning flag (Debate D6) is part of honest revision when context warrants it.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a full Fisher-Ury negotiation atom set: parties and positions, people-problem-separation diagnosis, position-to-interest descent atoms per party with hypothesis flags, shared and opposed interest atoms separated, options-for-mutual-gain atoms keyed to interest patterns, objective-criteria atoms with counterparty-acceptance reasoning, user-BATNA atoms described concretely, counterparty-BATNA hypothesis atoms, opening-and-fallback pattern atoms, flagged-unknown atoms, and Voss-warning flag where context warrants**. The atoms are:

1. **Party-and-stated-position atoms.** Each atom carries: party name and stated position (in the party's own vocabulary or close to it). Positions are reported as stated; the descent happens at the next layer.

2. **People-problem-separation diagnosis atoms.** Each atom names: a specific perception gap, emotional trigger, or communication failure that needs separate handling from the substantive bargaining. People-problem-conflation is the named failure mode the consolidator watches for; generic gestures about "separating the people from the problem" without diagnosed specifics get reshaped.

3. **Inferred-interest atoms per party.** Each atom names one underlying interest (substantive economic / procedural / relational / identity-and-recognition / security / fairness-perception / future-relationship) plus an explicit hypothesis flag (`inferred — to test`). Position-interest-collapse and inference-as-fact are the named failure modes; restatements of positions in interest-language and missing hypothesis flags get reshaped.

4. **Shared/compatible-interest atoms.** Where parties share an interest or admit compatible satisfaction.

5. **Genuinely-opposed-interest atoms.** Where parties' satisfaction is structurally in tension. Integrative-overreach is the named failure mode; negotiations framed as fully integrative without surfacing what doesn't dissolve get reshaped.

6. **Options-for-mutual-gain atoms.** Each atom names: the option, the underlying interest pattern (e.g., differential valuation, contingency, dovetailing of differences) that makes it possible, and what could invalidate it. Options that respond to *more* interest on *more* sides — not generic compromise.

7. **Objective-criteria atoms.** Each atom names a third-party-acceptable standard (market data, precedent, expert opinion, scientific judgment, professional standards, efficiency, costs, court-decision, moral standards, equal treatment, tradition) with reasoning about why the counterparty could plausibly accept it. Pseudo-objective-criteria is the named failure mode; criteria that align suspiciously with the user's preferred outcome get reshaped.

8. **User-BATNA atoms.** Each atom describes the user's best alternative concretely — the actual alternative, what it would cost (time, money, opportunity, relationship), what would happen step-by-step if the negotiation fails. BATNA-as-placeholder is the named failure mode; abstract "I'd walk away" without walkable-through specifics gets reshaped.

9. **Counterparty-BATNA hypothesis atoms.** Each atom names: the inferred counterparty BATNA, the evidence-basis, and an explicit hypothesis flag. These are inferences, not facts.

10. **Opening-and-fallback-pattern atoms.** Each atom names: the recommended opening move, the expected counterparty response, the fallback options keyed to the user's BATNA, and the walk-away threshold (the point at which BATNA dominates the offered deal).

11. **Flagged-unknown atoms.** Each atom names: a question the user could test in the negotiation, what it confirms or disconfirms, how the answer changes the strategy.

12. **Voss-warning flag — when applicable.** Where context is high-stakes adversarial (hostage-style, deeply distributive, strongly asymmetric power), the flag is preserved with note that Fisher-Ury alone may be insufficient. Voss-warning-unflagged is the named failure mode.

13. **Cultural-and-relational-context flag — when applicable.** Where culture, organisation, or relational history shapes which moves are available.

14. **Confidence per finding** — three confidence kinds kept separate: confidence in positions (typically high), confidence in inferred interests/BATNAs/motivations (typically lower), confidence in candidate moves (depends on testing).

**Mode-specific bloat patterns to cut:**

- **Position-interest-collapse** — interests that restate positions.
- **Inference-as-fact** — inferred content presented without hypothesis flags.
- **BATNA-as-placeholder** — abstract walk-away without walkable-through specifics.
- **Pseudo-objective criteria** — user preferences in objective-sounding language.
- **People-problem slogan** — generic gestures rather than diagnosed perception/emotion/communication issues.
- **Integrative overreach** — negotiation framed as fully solvable through integrative moves.
- **Zero-sum default** — negotiation framed as fully distributive without integrative territory.
- **Generic options** — compromise positions rather than mutual-gain options keyed to interest pattern.
- **Voss-warning suppression** — adversarial high-stakes context without acknowledging Fisher-Ury limitations.
- **Cultural-context flatness** — moves applied without consideration of context-dependent availability.

**What NOT to collapse:**

- **Genuinely opposed interests** — never smoothed with manufactured integrative possibility.
- **Multiple plausible BATNAs** — sometimes the second BATNA is the strongest; both survive.
- **Multiple plausible underlying interests for the same position** — preserved as competing hypotheses to test.
- **Stream disagreement about counterparty BATNA** — the BATNA is inferred; disagreement reveals what's uncertain about the counterparty.
- **Voss-vs-Fisher-Ury disagreement** — when context falls in the contested middle ground (commercial but emotionally loaded, partner-with-history negotiation), both readings survive with their guidance.

## VERIFICATION CRITERIA

Verified means: parties and stated positions named; people-problem diagnosis specific; inferred interests itemized per party with hypothesis-flagging; shared/compatible and genuinely-opposed interests separately surfaced; at least two options-for-mutual-gain named with supporting interest-pattern; at least three objective-criteria candidates with counterparty-acceptance reasoning; user BATNA described concretely (described, costed, walked-through); counterparty BATNA hypothesis-flagged; opening-and-fallback recommendation specific; flagged unknowns listed as testable; the six critical questions are addressable from the output. Confidence per major finding accompanies each claim. If context is high-stakes adversarial, the Voss-critique flag (Debate D6) is present.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **principled negotiation preparation** — a full Fisher-Ury synthesis covering all four elements (people-problem separation, interests-not-positions, options-for-mutual-gain, objective-criteria) plus BATNA on both sides plus a specific opening-and-fallback pattern. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Parties and stated positions.** A table. Each row: `**[Party]** — stated position: "[in party's own vocabulary]." Role in negotiation: [...]. User-party flag: [yes if this party is the user; no otherwise].`

2. **People-problem separation diagnosis.** Bulleted list. Each: `**[Specific issue — perception gap / emotional trigger / communication failure]** — manifestation: [...]. Separate-handling move: [...].` Generic gestures are reshaped at this layer.

3. **Inferred underlying interests per party.** Per party, one labelled sub-block listing inferred interests. Each: `**[Interest category]** — what the interest is: [...]. Inferred from: [...]. Status: hypothesis (to test).` Symmetric descent across parties.

4. **Shared or compatible interests.** Bulleted list. Each: `**[Shared interest]** — appears for each party as: [...]. Integrative path: [...].`

5. **Genuinely opposed interests.** Bulleted list. Each: `**[Opposed interest]** — structural opposition: [...]. What makes the opposition not merely positional: [...].`

6. **Options for mutual gain.** Numbered list. Each: `[N]. **[Option]** — interest pattern that makes it possible: [differential valuation / contingency / dovetailing of differences / shared cost reduction]. Interest hypotheses the option depends on: [...]. What could invalidate it: [...].`

7. **Objective criteria candidates.** Numbered list. Each: `[N]. **[Standard — market data / precedent / expert opinion / scientific / professional / efficiency / cost / court-decision / moral / equal-treatment / tradition]** — why the counterparty could plausibly accept it: [...]. How the user could deploy it without contest of will: [...].`

8. **User BATNA assessment.** One labelled block. `**User BATNA:** [the actual alternative, concretely described]. **Cost:** [time / money / opportunity / relationship]. **What would actually happen if no deal:** [step-by-step walk-through]. **Weaknesses surfaced:** [where the BATNA is weaker than it looks].`

9. **Inferred counterparty BATNA.** One labelled block. `**Counterparty BATNA (hypothesis):** [the inferred alternative]. **Evidence basis:** [...]. **Status:** hypothesis — to test or signal-search in negotiation.`

10. **Recommended opening and fallback pattern.** One labelled block. `**Opening move:** [specific opening]. **Expected counter:** [...]. **Fallback options keyed to BATNA:** [N1] / [N2] / [N3]. **Walk-away threshold:** [the point at which BATNA dominates].`

11. **Flagged unknowns to test.** Bulleted list. Each: `**[Question]** — what it confirms or disconfirms: [...]. How it changes the strategy: [...].`

12. **Confidence per finding.** Three labelled confidence assessments, kept distinct:
    - `Stated positions: [confidence and basis — typically high].`
    - `Inferred interests / BATNAs / motivations: [confidence and basis — typically lower].`
    - `Candidate moves and recommendations: [confidence and basis — depends on testing].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 12.
- Fisher-Ury vocabulary stays operative — `interests`, `positions`, `options for mutual gain`, `objective criteria`, `BATNA`, `people / problem separation`. Paraphrasing into generic negotiation language is reshaped at this layer.
- BATNA (sections 8–9) is *walkable-through*. The user could step through what their alternative actually looks like. Placeholder BATNAs are reshaped at this layer.
- Objective criteria (section 7) are genuinely third-party-acceptable. Criteria that align suspiciously with the user's preferred outcome are reshaped or flagged as `**Pseudo-objective flag:** this standard may be the user's preference in objective-sounding language; counterparty acceptance is uncertain.`
- When the Voss-warning flag survived consolidation, the deliverable opens with: `**Note: this negotiation context exhibits adversarial / high-stakes / distributive characteristics that Fisher-Ury alone may not fully address. Tactical-empathy (Voss), calibrated questions, mirroring, and emotion-labeling lenses may complement the analysis below; see Debate D6 for the framing.**`
- When the cultural-and-relational-context flag survived consolidation, section 3 closes with a context note about which interests may be unsurfaceable.
- Confidence (section 12) stays as three distinct kinds.

## CAVEATS AND OPEN DEBATES

**Debate D6 — Fisher-Ury sufficiency for adversarial contexts; Voss critique.** Fisher and Ury's *Getting to Yes* (1981, with Patton's later editions) frames negotiation as fundamentally integrative-possible: separate people from problem, focus on interests not positions, generate options for mutual gain, use objective criteria. The framework has been transformative in commercial and diplomatic contexts where the parties share an interest in reaching agreement and where the integrative possibility-space is real. Chris Voss's *Never Split the Difference* (2016) and the broader practitioner literature on hostage negotiation, high-stakes commercial bargaining, and politically adversarial negotiation argue that Fisher-Ury underweights tactical empathy, emotional dynamics, distributive reality, and the role of perceived loss and ego in many real negotiations — and that in genuinely adversarial contexts the integrative frame can be naive or actively counterproductive. Voss-derived practice emphasizes calibrated questions, mirroring, labeling emotions, the "no" that opens engagement, the late-stage "Black Swan" information asymmetries, and the recognition that distribution, not integration, often dominates the late-game bargaining. Lewicki and others document the distributive/integrative continuum and warn against assuming integrative possibility where it is absent.

This mode does not adjudicate the debate. It uses Fisher-Ury as the primary lens because the four-element method (people-problem separation, interests-not-positions, options-for-mutual-gain, objective-criteria) plus BATNA is the most-tested integrative framework available, and because the position-vs-interest descent is robust across contexts. The mode flags adversarial-context limitations explicitly when the situation warrants — the `voss-warning-unflagged` failure mode and the `voss-tactical-empathy` optional lens are the structural mechanisms. The integrative-overreach failure mode exists precisely to guard against the Fisher-Ury optimism trap. In genuinely adversarial contexts, the user may need to supplement this mode with Voss-style tactical-empathy lenses (carried optionally), or to recognize that the analysis is offering the integrative-possibility-space the situation may not contain. Citations: Fisher, Ury & Patton 1981/2011 *Getting to Yes*; Voss & Raz 2016 *Never Split the Difference*; Lewicki et al. negotiation textbook tradition for the distributive/integrative distinction; Raiffa 1982 *The Art and Science of Negotiation* for ZOPA / reservation-price modeling; Thompson 2020 *The Mind and Heart of the Negotiator* for cross-cultural and emotional dimensions.


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
