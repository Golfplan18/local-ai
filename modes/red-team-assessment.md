---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Red Team (Assessment)

```yaml
# 0. IDENTITY
mode_id: red-team-assessment
canonical_name: Red Team (Assessment)
suffix_rule: analysis
educational_name: adversarial vulnerability assessment for own decision (red team, assessment stance)

# 1. TERRITORY AND POSITION
territory: T15-artifact-evaluation-by-stance
gradation_position:
  axis: stance
  value: adversarial-actor-modeling-assessment
adjacent_modes_in_territory:
  - mode_id: red-team-advocate
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
    note: "Red Team (Assessment) and T7's pre-mortem-fragility / fragility-antifragility-audit both attack artifacts adversarially, but Red Team models a hostile actor while T7 audits structural fragility regardless of attacker presence. When the user wants 'how could this fail under any pressure' rather than 'how would an adversary defeat this,' route to T7."

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I have a specific named artifact (plan, draft, claim, decision, design, argument) and want it stress-tested adversarially before I commit"
    - "I want to know what I'm missing before I commit or ship"
    - "I need to surface vulnerabilities so I know what to fix"
    - "before-commitment hygiene check on my own decision"
  prompt_shape_signals:
    - "stress-test this"
    - "attack this"
    - "pick this apart"
    - "try to break this"
    - "poke holes in this"
    - "what am I missing"
    - "where is this weak"
    - "how could this fail"
    - "before I ship"
    - "before I commit"
    - "find the holes"
    - "what would a hostile reviewer say"
disambiguation_routing:
  routes_to_this_mode_when:
    - "specific named artifact under hostile-actor stress test for own benefit"
    - "blind-spot seeking before commitment or shipping"
    - "the user owns the decision being stress-tested and wants vulnerabilities ranked by severity for fix-prioritisation"
  routes_away_when:
    - "argue against this for external use" → red-team-advocate (stance-counterpart in same territory)
    - "want strongest case FOR the artifact" → steelman-construction (direct opposite)
    - "want balanced evaluation (positive AND negative AND interesting)" → benefits-analysis
    - "want neutral examination weighing both sides" → balanced-critique
    - "want opposition driven toward synthesis" → dialectical-analysis (T12)
    - "want to choose between alternatives" → constraint-mapping (T3)
    - "want to question the framework the artifact rests on" → paradigm-suspension (T9)
    - "want structural fragility audit (no specific adversary)" → pre-mortem-fragility or fragility-antifragility-audit (T7)
    - "no specific artifact on the table — just stakes-heavy concern" → adversarial catch-all
when_not_to_invoke:
  - "User wants to build a case against the artifact for external use (debate / dissuasion / hostile-review prep)" → red-team-advocate
  - "User wants framework-level critique rather than artifact-level attack" → paradigm-suspension
  - "User wants structural fragility audit independent of adversary modeling" → T7 pre-mortem-fragility
  - "User has not supplied a specific named artifact" → run Input Sufficiency Protocol; offer redirect
  - "User wants forward planning rather than attack" → scenario-planning or consequences-and-sequel (T6)

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
      - sufficient_specificity: "enough detail that vulnerabilities can be specific, not generic"
      - diagram_legibility_and_granularity: "applies only to diagram inputs"
    on_failure: "emit three-part redirect (What I see / What's missing / Three options with override) instead of attacking"

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [named_artifact, decision_context_user_owns, severity_threshold_preference]
    optional: [audience_context, prior_critiques_to_avoid_recapitulating, spatial_representation]
    notes: "Applies when user explicitly names the artifact, names that the decision is theirs to make, and specifies severity threshold for triage."
  accessible_mode:
    required: [artifact_to_stress_test]
    optional: [what_user_is_about_to_decide, audience_context]
    notes: "Default. Mode infers that the artifact is the user's own to decide on; runs Input Sufficiency Protocol before attack."
  detection:
    expert_signals: ["red team this assessment", "severity floor at Major", "stress-test against [adversary type]"]
    accessible_signals: ["attack this", "stress-test this", "what am I missing", "find the holes", "before I ship"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Emit Input Sufficiency redirect (three-part shape: What I see / What's missing / Three options with override). Do not attack thin material without flagging."
    on_underspecified: "Run Input Sufficiency Protocol; if conditions fail, emit redirect rather than attacking."
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Does each vulnerability have artifact-specific grounding (Why this is real with quotes where possible), or are findings manufactured to satisfy the prompt?"
    failure_mode_if_unmet: nitpick-trap
  - cq_id: CQ2
    question: "Is the severity calibration honest, or has severity been inflated to feel productive (or deflated to spare the user)?"
    failure_mode_if_unmet: severity-inflation
  - cq_id: CQ3
    question: "Is each fix recommendation actionable by the user — does the user know what to do next?"
    failure_mode_if_unmet: fix-handwaving
  - cq_id: CQ4
    question: "Has fix-feasibility been assessed per vulnerability, distinguishing fixes the user can implement from those requiring outside resources?"
    failure_mode_if_unmet: fix-handwaving
  - cq_id: CQ5
    question: "Does the Attack-Failure Disclosure section name attack classes attempted that produced no findings, or is it empty?"
    failure_mode_if_unmet: shallow-attack
  - cq_id: CQ6
    question: "Does the attack stay within the artifact's framework, or does it drift into framework-level critique that belongs to paradigm-suspension?"
    failure_mode_if_unmet: framework-attack-trap
  - cq_id: CQ7
    question: "If Input Sufficiency override was invoked, is every finding flagged as low-specificity / generic so the user knows the limitation?"
    failure_mode_if_unmet: fabricated-override-trap

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: pulled-punches
    detection_signal: "Mode avoids hard truths to spare the user; vulnerabilities softened, severity deflated, real risks dressed as 'minor considerations'."
    correction_protocol: re-dispatch
  - name: severity-inflation
    detection_signal: "Severity profile inflated above what artifact's actual flaws warrant; severity-floor declaration skipped despite no Major/Showstopper findings to manufacture a sense of productive attack."
    correction_protocol: re-dispatch
  - name: fix-handwaving
    detection_signal: "Fix recommendations are vague ('improve documentation', 'consider stakeholders') without artifact-specific actionable instructions or feasibility assessment."
    correction_protocol: re-dispatch
  - name: nitpick-trap
    detection_signal: "Findings emitted without artifact-specific grounding; cosmetic-level objections promoted to vulnerability status."
    correction_protocol: re-dispatch
  - name: sycophantic-inverse-trap
    detection_signal: "Performing hostility rather than analysing; inverse of sycophantic affirmation. Findings fail the 'would a committed opponent actually use this' check."
    correction_protocol: flag
  - name: straw-target-trap
    detection_signal: "Attack targets a weakened version of the artifact; doesn't apply to artifact as written."
    correction_protocol: re-dispatch
  - name: framework-attack-trap
    detection_signal: "Attack drifts into critique of the framework the artifact rests on rather than the artifact within it."
    correction_protocol: escalate
  - name: manufacture-on-revise-trap
    detection_signal: "Reviser added findings without new evidence; sycophantic-inverse drift at revision stage."
    correction_protocol: re-dispatch
  - name: fabricated-override-trap
    detection_signal: "Override invoked but findings not flagged as low-specificity / generic; user loses signal that attack was run on thin material."
    correction_protocol: flag
  - name: shallow-attack
    detection_signal: "Attack-Failure Disclosure empty or missing; mode failed to attack thoroughly."
    correction_protocol: re-dispatch

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
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Red Team (Assessment) is the heaviest assessment-stance adversarial mode in T15; for richer integrated analysis escalate cross-territory to wicked-problems."
  sideways:
    target_mode_id: red-team-advocate
    when: "User shifts from own-decision-stress-test framing to building a case against the artifact for external use (debate / dissuasion / hostile review)."
  downward:
    target_mode_id: devils-advocate-lite
    when: "User wants light adversarial pressure rather than full red-team workup; deferred — fall back to balanced-critique with critical lean if devils-advocate-lite not built."
```

## DEPTH ANALYSIS GUIDANCE

Going deeper in Red Team (Assessment) means attacking from inside the artifact for the user's own benefit: hidden assumptions (what does the artifact assume that isn't explicitly stated, and would the artifact survive if that assumption is wrong); understated costs (what costs, risks, or downsides does the artifact name only briefly or not at all); missing stakeholders (whose interests, response, or capacity does the artifact not account for); internal logical gaps (steps that don't follow, claims unsupported by cited evidence, requirements that contradict each other); and steps that assume away the hard part (places where the artifact's structure brushes past the actual difficulty). Apply the sycophantic-inverse self-check before declaring any vulnerability: would a committed opponent actually use this attack, grounded in the artifact's specifics? If the only objection is "but what if X were different" without anchoring in the artifact, drop it. Honest attack failure is more valuable than manufactured findings — and pulled punches (softening real vulnerabilities to spare the user) is a graver failure than over-attack, because the assessment's purpose is to surface what the user needs to fix.

## BREADTH ANALYSIS GUIDANCE

Widening the lens in assessment means attacking from outside the artifact while keeping the operation focused on what the user needs to fix: adversarial use cases (how would a hostile actor exploit this; what abuse vectors did the author not model); failure modes (under what conditions does the artifact break; what operating-envelope boundaries are undocumented); second-order blowback (who or what reacts to deployment in unpredicted ways — counter-moves, displaced costs, regulatory responses, market reactions). Same sycophantic-inverse self-check as Depth: every finding requires artifact-specific grounding, not hypothetical pressure that doesn't anchor in the deployment context. Each external-surface vulnerability also needs a fix-recommendation: surfacing a vulnerability without telling the user what to do about it leaves the assessment incomplete.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Red Team (Assessment) stress-tests a named artifact for the user's own benefit before they commit or ship: vulnerabilities rank by severity (Showstopper / Major / Caveat) for fix-prioritisation, each paired with an actionable fix recommendation and fix-feasibility tag. It is distinct from red-team-advocate (the same territory's counterpart — builds a case for an external audience ranked by persuasive force; assessment is the safer default when external audience is not in the picture), from steelman-construction (direct opposite — strongest case FOR the artifact), and from T7 pre-mortem-fragility (audits structural fragility regardless of adversary presence; assessment models a hostile actor specifically).

**Procedure.**

1. Run the Input Sufficiency Protocol before attacking — identifiable artifact, bounded scope, sufficient specificity; emit a three-part redirect rather than attacking thin material.
2. Declare stance at top: `Stance: assessment.`
3. Restate the artifact in brief with quotes where possible — vulnerabilities anchor here.
4. Attack from inside the artifact (Depth): hidden assumptions, understated costs, missing stakeholders, internal logical gaps, steps that assume away the hard part.
5. Attack from outside the artifact (Breadth): adversarial use cases, failure modes, second-order blowback, regulatory or market responses.
6. Apply the sycophantic-inverse self-check — would a committed opponent actually use this, grounded in the artifact's specifics? Drop attacks that fail.
7. Tag each finding with Severity (Showstopper / Major / Caveat), Surface (Internal / External), and a Why-this-is-real grounding (quoted where possible).
8. Pair every vulnerability with an actionable fix recommendation and a fix-feasibility tag (user-implementable / requires-outside-resources / structural-redesign-needed).
9. Disclose attack classes attempted that produced no findings — empty Attack-Failure Disclosure signals shallow attack.
10. When no Major/Showstopper findings exist, declare the severity floor explicitly — the anti-nitpick guard, not a failure to attack.
11. Flag any framework-level drift and surface paradigm-suspension as the sideways-route.
12. Resist pulled-punches (softening real vulnerabilities to spare the user) and severity-inflation (promoting Caveats to Major to manufacture productive-attack feel).

**Goal.** Produce an adversarial vulnerability assessment — a structured audit of the user's own artifact, ranked by severity for fix-prioritisation, with actionable fixes and fix-feasibility per finding.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — finding grounding.** Does each vulnerability have artifact-specific grounding (Why this is real with quotes where possible), or are findings manufactured? Failure mode if unmet: `nitpick-trap`.
- **CQ2 — severity calibration.** Is severity calibration honest, or has severity been inflated (or deflated)? Failure mode if unmet: `severity-inflation`.
- **CQ3 — fix actionability.** Is each fix recommendation actionable by the user — does the user know what to do next? Failure mode if unmet: `fix-handwaving`.
- **CQ4 — fix-feasibility.** Has fix-feasibility been assessed per vulnerability, distinguishing fixes the user can implement from those requiring outside resources? Failure mode if unmet: `fix-handwaving`.
- **CQ5 — Attack-Failure Disclosure.** Does the section name attack classes attempted that produced no findings, or is it empty? Failure mode if unmet: `shallow-attack`.
- **CQ6 — framework-vs-artifact discipline.** Does the attack stay within the artifact's framework, or drift into framework-level critique? Failure mode if unmet: `framework-attack-trap`.
- **CQ7 — override flag.** If Input Sufficiency override was invoked, is every finding flagged as low-specificity / generic? Failure mode if unmet: `fabricated-override-trap`.

A passing output has stance declared at top ("Stance: assessment"), every vulnerability tagged with severity (Showstopper/Major/Caveat) and surface (Internal/External) and grounded with quotes where possible, every vulnerability paired with an actionable fix recommendation and a fix-feasibility note, residual uncertainties named, Attack-Failure Disclosure present with at least one disclosed attack class, severity-floor declaration when no Major/Showstopper findings exist, and output structure matching the assessment shape throughout.

**Named failure modes.**

- *pulled-punches* — mode avoids hard truths to spare the user; vulnerabilities softened, severity deflated, real risks dressed as "minor considerations".
- *severity-inflation* — severity profile inflated above what artifact's actual flaws warrant; severity-floor declaration skipped despite no Major/Showstopper findings.
- *fix-handwaving* — fix recommendations are vague without artifact-specific actionable instructions or feasibility assessment.
- *nitpick-trap* — findings emitted without artifact-specific grounding; cosmetic-level objections promoted to vulnerability status.
- *sycophantic-inverse-trap* — performing hostility rather than analysing; findings fail the "would a committed opponent actually use this" check.
- *straw-target-trap* — attack targets a weakened version of the artifact; doesn't apply to artifact as written.
- *framework-attack-trap* — attack drifts into critique of the framework the artifact rests on rather than the artifact within it.
- *manufacture-on-revise-trap* — reviser added findings without new evidence; sycophantic-inverse drift at revision stage.
- *fabricated-override-trap* — override invoked but findings not flagged as low-specificity / generic; user loses signal that attack was run on thin material.
- *shallow-attack* — Attack-Failure Disclosure empty or missing; mode failed to attack thoroughly.

## REVISION GUIDANCE

Revise to add artifact-specific grounding (Why this is real with quotes) wherever vulnerabilities lack it; drop findings that fail the grounding check rather than weaken the standard. Revise to declare the severity floor honestly when no Major/Showstopper findings exist — a "the artifact is solid" sentence is the anti-Nitpick guard, not a failure to attack. Revise to pair every vulnerability with an actionable fix recommendation and feasibility note where these are missing. Revise to remove pulled-punch language (softening real risks to spare the user) wherever it has crept in: the assessment's contract is honest vulnerability surfacing for fix-prioritisation, not comfort. Resist revising toward more findings — the mode's purpose is honest adversarial pressure ranked by severity, not finding-quota satisfaction. The reviser may consolidate, clarify, or strengthen existing findings; may NOT manufacture new findings without new evidence (manufacture-on-revise-trap is a Tier A failure).

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **an assessment-stance vulnerability audit: stance declaration, artifact-restatement atom, vulnerability atoms ranked by severity (Showstopper > Major > Caveat) with surface tag (Internal / External), fix-recommendation atoms paired with fix-feasibility notes, residual-uncertainty atoms, Attack-Failure Disclosure atoms naming attack classes attempted that produced nothing, and severity-floor declaration when applicable**. The atoms are:

1. **Stance-declaration atom.** A single line: `Stance: assessment.` The deliverable's posture is surface-vulnerabilities-for-fix, not built-the-case-against-for-external-audience. Mixing in advocate-stance shapes (audience model, persuasive-force ranking, suggested phrasing) is a routing failure.

2. **Artifact-restatement atom.** The artifact in brief, quoted where possible.

3. **Vulnerability atoms — ranked by severity.** Each atom carries: a `Finding [N]` label, a severity tag (`Showstopper` / `Major` / `Caveat`), a surface tag (`Internal` / `External`), a `Why this is real` grounding (with quoted artifact text where possible), and `What breaks if exploited`. Pulled-punches is the named failure mode the consolidator watches for; vulnerabilities softened, severity deflated, or real risks dressed as "minor considerations" get reshaped. Severity-inflation is the mirror failure; severity profile inflated above what artifact flaws warrant gets reshaped. Nitpick-trap, straw-target-trap, sycophantic-inverse-trap, and no-fabrication-violation also apply.

4. **Fix-recommendation atoms — per vulnerability.** Each atom carries: an *actionable* fix (specific change the user could implement), a fix-feasibility note (`user-implementable` / `requires-outside-resources` / `structural-redesign-needed`). Fix-handwaving is the named failure mode; vague fixes ("improve documentation", "consider stakeholders") without artifact-specific instructions get reshaped.

5. **Residual-uncertainty atoms.** Where the assessment depends on facts or framings that may shift, the uncertainty surfaces explicitly.

6. **Attack-Failure Disclosure atoms.** Each atom names: an attack class attempted that produced no findings, and why. Shallow-attack is the named failure mode; empty disclosure indicates the attack was not thorough.

7. **Severity-floor declaration atom — when applicable.** When no Major or Showstopper findings exist, a labelled `**Severity floor:** the artifact is solid at the Major/Showstopper level. Caveats below are surface-level rather than structural.` line is the anti-nitpick guard, not a failure to attack.

8. **Framework-attack-trap flag — when applicable.** Where attacks drifted into critique of the framework the artifact rests on, the flag is preserved and a sideways-route to paradigm-suspension is surfaced.

9. **Override-flag — when applicable.** Where the Input Sufficiency Protocol was overridden, every finding carries an explicit low-specificity / generic flag. Fabricated-override-trap is the named failure mode.

10. **Manufacture-on-revise flag — when applicable.** Where revision added findings without new evidence, the flag is preserved.

11. **Confidence per finding.** Each major claim carries confidence (separate from severity — confidence is about whether the vulnerability is real; severity is about how bad it is if real).

**Mode-specific bloat patterns to cut:**

- **Pulled punches** — hard truths softened to spare the user; severity deflated; real risks dressed as "minor considerations".
- **Severity inflation** — Caveats promoted to Major to manufacture sense of productive attack; severity-floor declaration skipped to avoid honesty about a solid artifact.
- **Fix handwaving** — vague fixes without artifact-specific actionable instructions or feasibility.
- **Nitpick** — cosmetic-level objections promoted to vulnerability status.
- **Sycophantic-inverse** — performing hostility without grounding; would a committed opponent actually use this?
- **Straw-target / fabrication** — attacks on distorted or fabricated artifact-claims.
- **Framework-attack drift** — critiquing the framework rather than the artifact within it.
- **Empty Attack-Failure Disclosure** — shallow attack; the user can't tell what was attempted and didn't land.
- **Advocate-stance bleed** — audience model, persuasive-force ranking, suggested phrasing — these belong in red-team-advocate.

**What NOT to collapse:**

- **Severity tiers** — Showstopper / Major / Caveat distinctions calibrate honestly; the three tiers do not blur into one another.
- **Internal-vs-External surface distinction** — internal-logic vulnerabilities and external (deployment-context, adversarial-use, second-order) vulnerabilities operate differently; both surfaces are scanned.
- **Stream disagreement about severity** — when streams rated the same vulnerability differently, the disagreement is preserved with reasoning for both.
- **Fix-feasibility distinctions** — user-implementable / outside-resources / structural-redesign-needed are not blurred; the user needs to know what they can act on.

## VERIFICATION CRITERIA

Verified means: stance declaration appears in opening line ("Stance: assessment"); artifact restatement quotes where possible; every vulnerability has Finding [N] label, Severity (Showstopper/Major/Caveat), Surface (Internal/External), Why this is real grounded in artifact specifics, What breaks if exploited, Fix recommendation, and Fix feasibility note; vulnerabilities are ranked by severity (worst-first) not by surface or order-of-discovery; residual uncertainties section present; Attack-Failure Disclosure present with at least one disclosed attack class; severity-floor literal sentence present when applicable (no Major/Showstopper found); framework-level critiques flagged out-of-scope and routed to paradigm-suspension; override-flag present on every finding when Input Sufficiency override was invoked; no new findings introduced during revision without new evidence; no advocate-stance shapes (audience-model, persuasive-force ranking, suggested phrasing) present. The seven critical questions are addressable from the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is an **adversarial vulnerability assessment** — a structured audit of the user's own artifact, ranked by severity for fix-prioritisation, with actionable fixes and fix-feasibility per finding. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Stance declaration.** First line: `**Stance: assessment.**` Verbatim; downstream sections honour the assessment-stance contract.

2. **Artifact restatement.** One paragraph restating the artifact in brief, with quoted passages where possible.

3. **Vulnerabilities ranked by severity.** Numbered list, **Showstopper first, then Major, then Caveat**. Each: `**Finding [N]** — Severity: [Showstopper / Major / Caveat]. Surface: [Internal / External]. Why this is real: [grounded in artifact specifics with quote where possible]. What breaks if exploited: [...].`

4. **Fix recommendations per vulnerability.** Per finding, one labelled sub-block: `**Finding [N] — Fix recommendation:** [specific actionable change]. **Fix feasibility:** [user-implementable / requires-outside-resources / structural-redesign-needed]. Tradeoff if implemented: [...].`

5. **Residual uncertainties.** Bulleted list of facts or framings the assessment depends on that may shift.

6. **Attack-Failure Disclosure.** Bulleted list of attack classes attempted that produced no findings. Each: `**Attack class attempted:** [...]. **Why it produced no findings:** [...].` At least one entry; empty disclosures get reshaped to surface what was actually tried.

7. **Severity floor declaration (when applicable).** When no Major or Showstopper findings exist: `**Severity floor:** the artifact is solid at the Major/Showstopper level. The findings above are Caveats — surface-level rather than structural. The assessment did not pull punches; the artifact survived the attack.`

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- Severity vocabulary (`Showstopper` / `Major` / `Caveat`) appears verbatim. Ranking is severity-first: Showstoppers always lead, regardless of whether they are Internal or External.
- Fix-feasibility vocabulary (`user-implementable` / `requires-outside-resources` / `structural-redesign-needed`) appears verbatim — the user needs to know what they can act on.
- The severity-floor declaration (section 7) is *not* a sign of attack failure when honestly applied to a solid artifact. Omitting it to avoid acknowledging a clean assessment is a form of severity-inflation, reshaped at this layer.
- When the framework-attack-trap flag survived, the deliverable closes section 3 with: `**Framework-attack flag:** [N] finding(s) target the framework the artifact rests on rather than the artifact within it. Sideways-route to paradigm-suspension if framework critique is warranted; otherwise these findings get reshaped to stay within-framework.`
- When the override-flag survived, each finding in section 3 carries `**[low-specificity — override invoked]**` so the user knows the limitation.
- When the manufacture-on-revise flag survived, the deliverable carries a top-line note: `**Note: the revision stage added [N] finding(s) without new evidence. These have been flagged or removed.**`
- Advocate-stance shapes (audience model, persuasive-force ranking, suggested phrasing) are reshaped/removed at this layer; they belong in red-team-advocate.

## CAVEATS AND OPEN DEBATES

This mode and its sibling `red-team-advocate` were parsed from the original `red-team` mode per Decision D (parsing principle: when a single mode-id maps to two distinct output contracts with different ranking criteria and different audience modeling, parse into separate modes sharing a foundational lens). The shared lens is `cia-tradecraft-red-team`, which captures the foundational adversarial-actor-modeling discipline both modes draw from. The parse rationale: assessment ranks vulnerabilities by severity for the user's own fix-prioritisation; advocate ranks attacks by persuasive force against an external audience for argument-brief use. These are different operations — different ranking criteria, different audience modelling, different output contracts — so they live as sibling modes in T15 rather than as stances within a single mode. The earlier internal `stance_protocol` (assessment vs advocate dispatch within one mode_id) was retired with this parse: disambiguation now lives between modes, not within. Routing relies on the within-territory tree's secondary branch under "want adversarial — for own decision (assessment) or for external use (advocate)?" with `red-team-assessment` as the default when ambiguous and an escalation hook to `red-team-advocate`.


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
