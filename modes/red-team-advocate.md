---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Red Team (Advocate)

```yaml
# 0. IDENTITY
mode_id: red-team-advocate
canonical_name: Red Team (Advocate)
suffix_rule: analysis
educational_name: adversarial argument brief for external use (red team, advocate stance)

# 1. TERRITORY AND POSITION
territory: T15-artifact-evaluation-by-stance
gradation_position:
  axis: stance
  value: adversarial-actor-modeling-advocate
adjacent_modes_in_territory:
  - mode_id: red-team-assessment
    relationship: stance-counterpart (operation-counterpart in same territory; assessment vs. advocate)
  - mode_id: steelman-construction
    relationship: stance-counterpart (constructive-strong — direct opposite)
  - mode_id: benefits-analysis
    relationship: stance-counterpart (constructive-balanced)
  - mode_id: balanced-critique
    relationship: stance-counterpart (neutral)
  - mode_id: devils-advocate-lite
    relationship: stance-lighter sibling (adversarial-light — gap-deferred)
cross_territory_reference:
  - territory: T7-risk-and-failure-analysis
    note: "Red Team (Advocate) and T7's pre-mortem-fragility / fragility-antifragility-audit both attack artifacts adversarially, but Red Team models a hostile actor while T7 audits structural fragility regardless of attacker presence. When the user wants 'how could this fail under any pressure' rather than 'how do I argue against this for an audience,' route to T7."

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I need to prepare for hostile review or debate against this artifact"
    - "I want ammunition to dissuade someone from this course of action"
    - "I need to make the case against this for an external audience"
    - "comprehensive critique with no severity triage — every angle, including weak ones"
  prompt_shape_signals:
    - "argue against this"
    - "make the case against"
    - "give me ammunition"
    - "I need to dissuade"
    - "talk them out of it"
    - "prep me for debate"
    - "prep me for hostile review"
    - "every angle including weak ones"
    - "comprehensive critique"
    - "no triage"
    - "I'm presenting against this"
disambiguation_routing:
  routes_to_this_mode_when:
    - "specific named artifact, advocate-stance argument brief for debate / dissuasion / hostile-review prep"
    - "user is building a case AGAINST the artifact for external use"
    - "audience-modelling matters: the brief will be argued in front of someone whose persuasion is the goal"
  routes_away_when:
    - "stress-test for own decision / what's wrong / fix list" → red-team-assessment (stance-counterpart in same territory)
    - "want strongest case FOR the artifact" → steelman-construction (direct opposite)
    - "want balanced evaluation (positive AND negative AND interesting)" → benefits-analysis
    - "want neutral examination weighing both sides" → balanced-critique
    - "want opposition driven toward synthesis" → dialectical-analysis (T12)
    - "want to choose between alternatives" → constraint-mapping (T3)
    - "want to question the framework the artifact rests on" → paradigm-suspension (T9)
    - "want structural fragility audit (no specific adversary)" → pre-mortem-fragility or fragility-antifragility-audit (T7)
when_not_to_invoke:
  - "User wants to know what to fix in their own artifact" → red-team-assessment
  - "User wants framework-level critique rather than artifact-level attack" → paradigm-suspension
  - "User wants structural fragility audit independent of adversary modeling" → T7 pre-mortem-fragility
  - "User has not supplied a specific named artifact" → run Input Sufficiency Protocol; offer redirect
  - "No external audience is in the picture — the user owns the decision" → red-team-assessment

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: adversarial
  input_sufficiency_protocol:
    runs: first stage of execution, before attack
    conditions:
      - identifiable_artifact: "specific named thing under attack, not a domain or area"
      - bounded_scope: "clear edges; in vs out of attack range knowable"
      - sufficient_specificity: "enough detail that attacks can be specific, not generic"
      - audience_identifiable: "the external audience for the brief is named or inferable"
      - diagram_legibility_and_granularity: "applies only to diagram inputs"
    on_failure: "emit three-part redirect (What I see / What's missing / Three options with override) instead of attacking"

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [named_artifact, named_external_audience, brief_purpose]
    optional: [audience_model_provided, prior_critiques_to_avoid_recapitulating, spatial_representation, persuasive_force_threshold]
    notes: "Applies when user explicitly names artifact, names the external audience the brief will be argued in front of, and names the brief's purpose (debate / dissuasion / hostile-review prep)."
  accessible_mode:
    required: [artifact_to_argue_against]
    optional: [audience_or_use_context]
    notes: "Default. Mode infers external audience from the user's framing; runs Input Sufficiency Protocol before attack."
  detection:
    expert_signals: ["red team this advocate", "audience model is X", "persuasive-force threshold at devastating", "brief is for hostile review by Y"]
    accessible_signals: ["argue against this", "make the case against", "give me ammunition", "I need to dissuade", "prep me for debate"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Emit Input Sufficiency redirect (three-part shape: What I see / What's missing / Three options with override). Do not attack thin material without flagging."
    on_underspecified: "If audience is missing, ask one clarifying question via clarification panel: 'Who is the brief argued in front of?' If artifact is missing, run Input Sufficiency Protocol redirect."
output_contract:
  artifact_type: audit
  required_sections:
    - stance_declaration
    - audience_model
    - artifact_restatement
    - attacks_ranked_by_persuasive_force
    - suggested_phrasing_per_attack
    - residual_uncertainties
    - concessions
    - strategic_considerations
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Is the audience model accurate — does it capture the audience's actual frame, priorities, and persuasion pathways, or is it a generic 'critic' construct?"
    failure_mode_if_unmet: audience-misalignment
  - cq_id: CQ2
    question: "Is persuasive-force calibration honest, or have weak attacks been promoted to 'devastating' to inflate the brief's apparent power?"
    failure_mode_if_unmet: cynical-overreach
  - cq_id: CQ3
    question: "Does every attack stay grounded in the artifact's actual content — no fabrication, no straw-target distortion?"
    failure_mode_if_unmet: straw-target-trap
  - cq_id: CQ4
    question: "Does the brief stay within the artifact's framework, or does it drift into framework-level critique that belongs to paradigm-suspension?"
    failure_mode_if_unmet: framework-attack-trap
  - cq_id: CQ5
    question: "Are concessions honestly named (preempting the strongest counter-moves) rather than omitted to make the brief look one-sided?"
    failure_mode_if_unmet: cynical-overreach
  - cq_id: CQ6
    question: "If Input Sufficiency override was invoked, is every attack flagged as low-specificity / generic so the user knows the limitation when arguing it?"
    failure_mode_if_unmet: fabricated-override-trap

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: cynical-overreach
    detection_signal: "Weak attacks framed as 'devastating' to inflate the brief; persuasive-force calibration dishonest; concessions omitted to make the brief look one-sided."
    correction_protocol: re-dispatch
  - name: straw-target-trap
    detection_signal: "Attack targets a weakened version of the artifact; doesn't apply to artifact as written. Critical failure for advocate stance — a brief built on straw-targets will collapse on first counter-move from anyone who has actually read the artifact."
    correction_protocol: re-dispatch
  - name: audience-misalignment
    detection_signal: "Attacks ranked by what would persuade a generic 'critic' rather than the named audience. Suggested phrasing reads in the analyst's voice, not in language the audience would respond to."
    correction_protocol: re-dispatch
  - name: no-fabrication-violation
    detection_signal: "Attack rests on a claim the artifact does not actually make, or on capabilities/intentions the artifact does not actually have. Indistinguishable from straw-target if undetected; detected separately because fabrication can survive even when the attacked claim is verbatim."
    correction_protocol: re-dispatch
  - name: sycophantic-inverse-trap
    detection_signal: "Performing hostility rather than analysing; inverse of sycophantic affirmation. Attacks fail the 'would a committed opponent actually use this' check."
    correction_protocol: flag
  - name: framework-attack-trap
    detection_signal: "Brief drifts into critique of the framework the artifact rests on rather than the artifact within it. Often indicates the audience would not accept the framework either, in which case route to paradigm-suspension."
    correction_protocol: escalate
  - name: manufacture-on-revise-trap
    detection_signal: "Reviser added attacks without new evidence; sycophantic-inverse drift at revision stage."
    correction_protocol: re-dispatch
  - name: fabricated-override-trap
    detection_signal: "Override invoked but attacks not flagged as low-specificity / generic; user loses signal that the brief was built on thin material."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - cia-tradecraft-red-team
  optional:
    - klein-pre-mortem
    - failure-mode-literature
    - post-mortem-analyses
    - adversarial-case-studies
    - fgl-fear-greed-laziness
    - opv-other-points-of-view
    - rapoport-rules-of-engagement
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Red Team (Advocate) is the heaviest advocate-stance adversarial mode in T15; for richer integrated analysis, escalate cross-territory to wicked-problems."
  sideways:
    target_mode_id: red-team-assessment
    when: "User shifts from external-audience-brief framing to wanting their own vulnerabilities surfaced for fix-prioritisation."
  downward:
    target_mode_id: devils-advocate-lite
    when: "User wants light adversarial pressure rather than full advocate-brief workup; deferred — fall back to balanced-critique with critical lean if devils-advocate-lite not built."
```

## DEPTH ANALYSIS GUIDANCE

Going deeper in Red Team (Advocate) means building the strongest case AGAINST the artifact for the named audience: hidden assumptions the artifact rests on (which the audience would reject); understated costs (which the audience cares about disproportionately); missing stakeholders (whose absence the audience will notice); internal logical gaps (which the audience will be primed to spot); steps that assume away the hard part (which the audience has experience with). Apply the no-fabrication discipline before declaring any attack: the attack must rest on what the artifact actually says, not what the analyst wishes it said. The sycophantic-inverse self-check applies — would a committed opponent actually argue this in front of the named audience? If the only objection is hypothetical pressure that doesn't anchor in the artifact's real content, drop it. The advocate-stance failure mode that kills the brief on first contact with a prepared audience is straw-target attack: an attack on a distorted version of the artifact collapses the moment the audience can see the artifact themselves.

## BREADTH ANALYSIS GUIDANCE

Widening the lens in advocate stance means scanning attack vectors the named audience would find compelling: optics and narrative angles (how would this look to someone primed to find fault); strategic considerations (what political, reputational, or coalitional damage is plausible); second-order blowback the audience cares about (who or what reacts to the artifact's deployment in ways the audience would weigh); abuse vectors that resonate with the audience's prior concerns. Audience-modelling is load-bearing here: every attack carries a "lands hardest with [audience] because…" annotation. Same no-fabrication discipline as Depth — every attack requires artifact-specific grounding, not hypothetical pressure that doesn't anchor in what the artifact actually says. The breadth pass also surfaces the concessions the advocate must preempt: what the audience will recognise as the artifact's strongest defence, which the brief must address head-on rather than ignore.

## EVALUATION CRITERIA

Evaluate against the six critical questions: (CQ1) audience-model accuracy; (CQ2) persuasive-force calibration; (CQ3) no-fabrication discipline; (CQ4) framework-vs-artifact discipline; (CQ5) concession honesty; (CQ6) override-flag presence when override invoked. The named failure modes (cynical-overreach, straw-target-trap, audience-misalignment, no-fabrication-violation, sycophantic-inverse-trap, framework-attack-trap, manufacture-on-revise-trap, fabricated-override-trap) are the evaluation checklist. A passing Red Team (Advocate) output has stance declared at top ("Stance: advocate"), audience model named in opening section, every attack tagged with Persuasive Force (Devastating/Strong/Plausible) and Surface (Internal/External) and grounded in the artifact's actual content, suggested phrasing per attack in the audience's idiom, residual uncertainties named, concessions section preempting the strongest counter-moves, and strategic considerations naming political/reputational/coalitional dimensions the audience cares about.

## REVISION GUIDANCE

Revise to add audience-grounding ("lands hardest with [audience] because…") wherever attacks lack it; drop attacks that fail the audience-fit check rather than retain them as filler. Revise to ground every attack in the artifact's actual content with quotes where possible; drop attacks that rest on fabricated claims (no-fabrication-violation is a Tier A failure regardless of how strong the attack would be if true). Revise to deflate persuasive force from "devastating" to "plausible" or lower wherever cynical-overreach has crept in — a brief built on inflated claims will fail in front of a prepared audience, undermining the user's credibility along with the brief. Revise to add concessions where they have been omitted: a brief that omits the artifact's strongest defence will be ambushed by it. Resist revising toward more attacks — the mode's purpose is high-leverage advocate ammunition ranked by what lands hardest, not a quota of objections. The reviser may consolidate, clarify, or strengthen existing attacks; may NOT manufacture new attacks without new evidence (manufacture-on-revise-trap is a Tier A failure).

## CONSOLIDATION GUIDANCE

Consolidate as a structured audit with advocate-specific output shape: stance declaration ("Stance: advocate") → audience model (named audience, their frame, their priorities, their persuasion pathways) → artifact restatement → attacks ranked by persuasive force (Devastating > Strong > Plausible) → suggested phrasing per attack in the audience's idiom → residual uncertainties → concessions (preempting the strongest counter-moves the audience would raise) → strategic considerations (political / reputational / coalitional). Each attack carries Attack [N] / Persuasive Force / Surface / Why this lands with [audience] / Suggested phrasing. Ranking discipline is persuasive force (what lands hardest first), not severity for own-fix and not surface order. Stance is the advocate stance; mixing in assessment-stance shapes (severity-ranked vulnerabilities, fix recommendations, fix-feasibility) is a routing failure — those belong in red-team-assessment.

## VERIFICATION CRITERIA

Verified means: stance declaration appears in opening line ("Stance: advocate"); audience model section present with named audience, frame, priorities, and persuasion pathways; artifact restatement quotes where possible; every attack has Attack [N] label, Persuasive Force (Devastating/Strong/Plausible), Surface (Internal/External), Why this lands with [audience], and Suggested phrasing in the audience's idiom; attacks are ranked by persuasive force (worst-for-the-artifact first) not by surface or order-of-discovery; residual uncertainties section present; concessions section present with at least one preempted counter-move; strategic considerations section present; framework-level attacks flagged out-of-scope and routed to paradigm-suspension; override-flag present on every attack when Input Sufficiency override was invoked; no new attacks introduced during revision without new evidence; no assessment-stance shapes (severity-ranked vulnerabilities, fix recommendations, fix-feasibility) present. The six critical questions are addressable from the output.

## CAVEATS AND OPEN DEBATES

This mode and its sibling `red-team-assessment` were parsed from the original `red-team` mode per Decision D (parsing principle: when a single mode-id maps to two distinct output contracts with different ranking criteria and different audience modeling, parse into separate modes sharing a foundational lens). The shared lens is `cia-tradecraft-red-team`, which captures the foundational adversarial-actor-modeling discipline both modes draw from. The parse rationale: assessment ranks vulnerabilities by severity for the user's own fix-prioritisation; advocate ranks attacks by persuasive force against an external audience for argument-brief use. These are different operations — different ranking criteria (severity vs. persuasive force), different audience modelling (the user themselves vs. a named external audience), different output contracts (vulnerabilities + fixes vs. attacks + suggested phrasing + concessions) — so they live as sibling modes in T15 rather than as stances within a single mode. The earlier internal `stance_protocol` (assessment vs advocate dispatch within one mode_id) was retired with this parse: disambiguation now lives between modes, not within. Routing relies on the within-territory tree's secondary branch under "want adversarial — for own decision (assessment) or for external use (advocate)?" — `red-team-advocate` requires explicit advocate signal because assessment is the safer default when ambiguous.
