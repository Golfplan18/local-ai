---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

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

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Red Team (Advocate) builds the strongest case AGAINST a named artifact for an external audience — debate prep, hostile-review prep, dissuasion brief. Attacks rank by *persuasive force* with the named audience (Devastating / Strong / Plausible), not by severity for the user's own fix; suggested phrasing per attack lands in the audience's idiom; concessions preempt the audience's strongest counter-moves. It is distinct from red-team-assessment (the same territory's counterpart — ranks vulnerabilities by severity for the user's own fix-prioritisation; assessment is the safer default when ambiguous), from steelman-construction (direct opposite — strongest case FOR the artifact), and from T7 pre-mortem-fragility (audits structural fragility regardless of adversary presence; advocate models a hostile actor for a specific audience).

**Procedure.**

1. Run the Input Sufficiency Protocol before attacking — identifiable artifact, bounded scope, sufficient specificity, audience identifiable; emit a three-part redirect rather than attacking thin material.
2. Declare stance at top: `Stance: advocate.`
3. Model the named external audience — frame, priorities, persuasion pathways; suggested phrasing reads in their idiom, not the analyst's voice.
4. Restate the artifact in brief with quotes where possible — attacks anchor here.
5. Build attacks grounded in the artifact's actual content (no-fabrication discipline) — hidden assumptions the audience would reject, understated costs they care about, missing stakeholders they will notice, internal logical gaps, steps that assume away the hard part.
6. Apply the sycophantic-inverse self-check — would a committed opponent actually argue this in front of the named audience? Drop attacks that fail.
7. Calibrate persuasive force honestly (Devastating > Strong > Plausible) — deflate cynical overreach; a brief built on inflated claims will fail and erode the user's credibility.
8. Tag each attack with Surface (Internal — logic flaw; External — empirical / optical / strategic) and a "lands hardest with [audience] because…" annotation.
9. Generate suggested phrasing per attack in the audience's idiom.
10. Preempt the strongest counter-moves with concessions — a brief without concessions gets ambushed by the audience's obvious reply.
11. Surface strategic considerations — political, reputational, coalitional dimensions the audience cares about.
12. When framework-level critique drifts in, flag it and surface paradigm-suspension as the sideways-route.

**Goal.** Produce an adversarial advocate brief — a structured case AGAINST the artifact, ranked by persuasive force for the named external audience, with suggested phrasing in the audience's idiom and concessions preempting the strongest counter-moves.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — audience-model accuracy.** Does the audience model capture the audience's actual frame, priorities, and persuasion pathways, or is it a generic "critic" construct? Failure mode if unmet: `audience-misalignment`.
- **CQ2 — persuasive-force calibration.** Is persuasive-force calibration honest, or have weak attacks been promoted to "devastating" to inflate the brief's apparent power? Failure mode if unmet: `cynical-overreach`.
- **CQ3 — no fabrication.** Does every attack stay grounded in the artifact's actual content — no fabrication, no straw-target distortion? Failure mode if unmet: `straw-target-trap`.
- **CQ4 — framework-vs-artifact discipline.** Does the brief stay within the artifact's framework, or drift into framework-level critique that belongs to paradigm-suspension? Failure mode if unmet: `framework-attack-trap`.
- **CQ5 — concession honesty.** Are concessions honestly named (preempting the strongest counter-moves) rather than omitted to make the brief look one-sided? Failure mode if unmet: `cynical-overreach`.
- **CQ6 — override flag.** If Input Sufficiency override was invoked, is every attack flagged as low-specificity / generic? Failure mode if unmet: `fabricated-override-trap`.

A passing output has stance declared at top ("Stance: advocate"), audience model named in opening section, every attack tagged with Persuasive Force (Devastating/Strong/Plausible) and Surface (Internal/External) and grounded in the artifact's actual content, suggested phrasing per attack in the audience's idiom, residual uncertainties named, concessions section preempting the strongest counter-moves, and strategic considerations naming political/reputational/coalitional dimensions the audience cares about.

**Named failure modes.**

- *cynical-overreach* — weak attacks framed as "devastating" to inflate the brief; persuasive-force calibration dishonest; concessions omitted to make the brief look one-sided.
- *straw-target-trap* — attack targets a weakened version of the artifact; doesn't apply to artifact as written. Critical failure for advocate stance.
- *audience-misalignment* — attacks ranked by what would persuade a generic "critic" rather than the named audience; phrasing in analyst voice rather than audience idiom.
- *no-fabrication-violation* — attack rests on a claim the artifact does not actually make, or on capabilities/intentions the artifact does not actually have.
- *sycophantic-inverse-trap* — performing hostility rather than analysing; attacks fail the "would a committed opponent actually use this" check.
- *framework-attack-trap* — brief drifts into critique of the framework the artifact rests on rather than the artifact within it.
- *manufacture-on-revise-trap* — reviser added attacks without new evidence; sycophantic-inverse drift at revision stage.
- *fabricated-override-trap* — override invoked but attacks not flagged as low-specificity / generic; user loses signal that the brief was built on thin material.

## REVISION GUIDANCE

Revise to add audience-grounding ("lands hardest with [audience] because…") wherever attacks lack it; drop attacks that fail the audience-fit check rather than retain them as filler. Revise to ground every attack in the artifact's actual content with quotes where possible; drop attacks that rest on fabricated claims (no-fabrication-violation is a Tier A failure regardless of how strong the attack would be if true). Revise to deflate persuasive force from "devastating" to "plausible" or lower wherever cynical-overreach has crept in — a brief built on inflated claims will fail in front of a prepared audience, undermining the user's credibility along with the brief. Revise to add concessions where they have been omitted: a brief that omits the artifact's strongest defence will be ambushed by it. Resist revising toward more attacks — the mode's purpose is high-leverage advocate ammunition ranked by what lands hardest, not a quota of objections. The reviser may consolidate, clarify, or strengthen existing attacks; may NOT manufacture new attacks without new evidence (manufacture-on-revise-trap is a Tier A failure).

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **an advocate-stance adversarial brief: stance declaration, audience-model atom, artifact-restatement atom, attack atoms ranked by persuasive force (Devastating > Strong > Plausible), suggested-phrasing atoms per attack in the audience's idiom, residual-uncertainty atoms, concession atoms preempting the strongest counter-moves, and strategic-consideration atoms naming political / reputational / coalitional dimensions**. The atoms are:

1. **Stance-declaration atom.** A single line: `Stance: advocate.` This is operative; the deliverable's posture is built-the-case-against, not surface-vulnerabilities-for-fix. Mixing in assessment-stance shapes (severity-ranked vulnerabilities, fix recommendations) is a routing failure.

2. **Audience-model atom.** The named external audience the brief will be argued in front of, their frame, their priorities, their persuasion pathways. Audience-misalignment is the named failure mode the consolidator watches for; attacks ranked by what would persuade a generic "critic" rather than the named audience get reshaped, and suggested-phrasing in analyst voice rather than audience idiom gets reshaped.

3. **Artifact-restatement atom.** The artifact in brief, quoted where possible, so attacks anchor in what the artifact actually says.

4. **Attack atoms — ranked by persuasive force.** Each atom carries: an `Attack [N]` label, a persuasive-force tag (`Devastating` / `Strong` / `Plausible`), a surface tag (`Internal` — internal-logic flaw / `External` — empirical, optical, strategic), grounding in quoted artifact content, and a `Why this lands with [audience]` annotation. Cynical-overreach is the named failure mode; weak attacks promoted to `Devastating` to inflate the brief get reshaped (deflated to honest tier). Straw-target-trap and no-fabrication-violation are also named failure modes; attacks resting on distorted or fabricated artifact-claims get reshaped or removed. Sycophantic-inverse-trap is named: attacks that perform hostility but a committed opponent would not actually use get reshaped.

5. **Suggested-phrasing atoms per attack.** Each atom carries the attack expressed in the audience's idiom, ready to deploy — not in the analyst's voice.

6. **Residual-uncertainty atoms.** Where the brief depends on facts or framings that may shift, the uncertainty surfaces explicitly.

7. **Concession atoms.** Each atom names a counter-move the audience will recognise as the artifact's strongest defence, with a pre-emptive handling. Concessions are part of the brief's strength, not its weakness; omitting them lets the audience ambush the user with the obvious reply.

8. **Strategic-consideration atoms.** Each atom names a political / reputational / coalitional dimension the audience cares about, with how the brief should leverage or avoid it.

9. **Framework-attack-trap flag — when applicable.** Where the brief drifted into critique of the framework the artifact rests on (rather than the artifact within it), the flag is preserved and a sideways-route to paradigm-suspension is surfaced.

10. **Override-flag — when applicable.** Where the Input Sufficiency Protocol was overridden (artifact thin, audience under-specified), every attack carries an explicit low-specificity / generic flag so the user knows the limitation when arguing it. Fabricated-override-trap is the named failure mode.

11. **Manufacture-on-revise flag — when applicable.** Where revision added attacks without new evidence (sycophantic-inverse drift at revision stage), the flag is preserved. Manufacture-on-revise-trap is the named failure mode.

12. **Confidence per finding.** Each major claim carries a confidence (separate from persuasive force — confidence is about whether the attack is correct; persuasive force is about whether it lands).

**Mode-specific bloat patterns to cut:**

- **Cynical overreach** — weak attacks framed as Devastating to inflate apparent power.
- **Straw-target attacks** — attacks on distorted versions of the artifact; the audience can read the artifact themselves and the attack collapses.
- **Fabrication** — claims about what the artifact says, intends, or implies that are not actually in the artifact.
- **Audience misalignment** — attacks calibrated to a generic critic rather than the named audience; phrasing in analyst voice rather than audience idiom.
- **Sycophantic-inverse performance** — performing hostility without committed-opponent grounding; the attack fails the "would a committed opponent actually use this" check.
- **Framework-attack drift** — critiquing the framework the artifact rests on rather than the artifact within it (sideways-route to paradigm-suspension if framework is genuinely the issue).
- **Assessment-stance bleed** — severity rankings, fix recommendations, fix-feasibility — these belong in red-team-assessment, not here.
- **Manufacture-on-revise** — new attacks added during revision without new evidence.
- **Concession omission** — leaving out the artifact's strongest defence to make the brief look one-sided.
- **Attack-quota inflation** — adding objections to hit a count rather than because they land. The mode is high-leverage ammunition, not exhaustive critique.

**What NOT to collapse:**

- **Devastating-vs-Strong-vs-Plausible distinctions** — these calibrate honestly; persuasive-force tiers do not blur.
- **Stream disagreement about audience model** — when streams modeled the audience differently (different priorities or persuasion pathways), both models survive with their respective attack rankings.
- **Internal-vs-External attack-surface distinction** — internal-logic flaws and external (empirical, optical, strategic) attacks operate differently in front of an audience; they stay distinguished.
- **Concession entries** — never deleted for one-sidedness; they are part of the brief's structural integrity.

## VERIFICATION CRITERIA

Verified means: stance declaration appears in opening line ("Stance: advocate"); audience model section present with named audience, frame, priorities, and persuasion pathways; artifact restatement quotes where possible; every attack has Attack [N] label, Persuasive Force (Devastating/Strong/Plausible), Surface (Internal/External), Why this lands with [audience], and Suggested phrasing in the audience's idiom; attacks are ranked by persuasive force (worst-for-the-artifact first) not by surface or order-of-discovery; residual uncertainties section present; concessions section present with at least one preempted counter-move; strategic considerations section present; framework-level attacks flagged out-of-scope and routed to paradigm-suspension; override-flag present on every attack when Input Sufficiency override was invoked; no new attacks introduced during revision without new evidence; no assessment-stance shapes (severity-ranked vulnerabilities, fix recommendations, fix-feasibility) present. The six critical questions are addressable from the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is an **adversarial advocate brief** — a structured case AGAINST the artifact, ranked by persuasive force for the named external audience, with suggested phrasing in the audience's idiom and concessions preempting the strongest counter-moves. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Stance declaration.** First line: `**Stance: advocate.**` This appears verbatim; downstream sections honour the advocate-stance contract.

2. **Audience model.** One labelled block. `**Named audience:** [...]. **Their frame:** [...]. **Their priorities:** [...]. **Their persuasion pathways:** [what arguments and tones move them].`

3. **Artifact restatement.** One paragraph restating the artifact in brief, with quoted passages where possible. Attacks in the next section anchor here.

4. **Attacks ranked by persuasive force.** Numbered list, **Devastating first, then Strong, then Plausible**. Each: `**Attack [N]** — Persuasive Force: [Devastating / Strong / Plausible]. Surface: [Internal / External]. Why this lands with [audience]: [...]. Grounded in artifact: [quote or specific reference].`

5. **Suggested phrasing per attack.** Per attack, one labelled sub-block: `**Attack [N] — Suggested phrasing (in [audience]'s idiom):** "[the attack expressed in language the audience would actually respond to]."`

6. **Residual uncertainties.** Bulleted list of facts or framings the brief depends on that may shift, with implications for the brief's deployment.

7. **Concessions.** Bulleted list. Each: `**Counter-move the audience will recognise:** [the artifact's strongest defence]. **Pre-emptive handling:** [how the brief addresses this head-on rather than ignoring it].` At least one concession appears.

8. **Strategic considerations.** Bulleted list of political / reputational / coalitional dimensions the audience cares about, with brief leverage notes.

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- Persuasive-force vocabulary (`Devastating` / `Strong` / `Plausible`) appears verbatim. The ranking discipline is persuasive force first — what lands hardest with the named audience — not severity, not order-of-discovery, not internal-then-external.
- Suggested-phrasing (section 5) is in the audience's idiom, not analyst voice. Phrasing that reads in analyst voice is reshaped at this layer.
- Concessions (section 7) are first-class. A brief without concessions will be ambushed by the audience's obvious reply. Omitting them for one-sidedness is reshaped.
- When the framework-attack-trap flag survived consolidation, the deliverable carries a labelled note at the end of section 4: `**Framework-attack flag:** [N] attack(s) target the framework the artifact rests on rather than the artifact within it. If the audience would not accept the framework either, paradigm-suspension is the appropriate sideways-route; otherwise these attacks should be reshaped to stay within-framework.`
- When the override-flag survived consolidation, each attack in section 4 carries an explicit `**[low-specificity — override invoked]**` annotation so the user knows when the attack is built on thin material.
- When the manufacture-on-revise flag survived, the deliverable carries a top-line note: `**Note: the revision stage added [N] attack(s) without new evidence. These have been flagged or removed; the brief below reflects the analyst's first-pass evidence-grounded attacks plus revision-strengthening only.**`
- Assessment-stance shapes (severity rankings, fix recommendations, fix-feasibility, vulnerabilities-for-own-fix) are reshaped or removed at this layer; they belong in red-team-assessment.

## CAVEATS AND OPEN DEBATES

This mode and its sibling `red-team-assessment` were parsed from the original `red-team` mode per Decision D (parsing principle: when a single mode-id maps to two distinct output contracts with different ranking criteria and different audience modeling, parse into separate modes sharing a foundational lens). The shared lens is `cia-tradecraft-red-team`, which captures the foundational adversarial-actor-modeling discipline both modes draw from. The parse rationale: assessment ranks vulnerabilities by severity for the user's own fix-prioritisation; advocate ranks attacks by persuasive force against an external audience for argument-brief use. These are different operations — different ranking criteria (severity vs. persuasive force), different audience modelling (the user themselves vs. a named external audience), different output contracts (vulnerabilities + fixes vs. attacks + suggested phrasing + concessions) — so they live as sibling modes in T15 rather than as stances within a single mode. The earlier internal `stance_protocol` (assessment vs advocate dispatch within one mode_id) was retired with this parse: disambiguation now lives between modes, not within. Routing relies on the within-territory tree's secondary branch under "want adversarial — for own decision (assessment) or for external use (advocate)?" — `red-team-advocate` requires explicit advocate signal because assessment is the safer default when ambiguous.


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

**Prioritize:** `supports`, `contradicts`, `qualifies`, `extends`
**Deprioritize:** `precedes`, `parent`

*Family: argument-evaluation. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
