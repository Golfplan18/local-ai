---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Wicked Problems

```yaml
# 0. IDENTITY
mode_id: wicked-problems
canonical_name: Wicked Problems
suffix_rule: analysis
educational_name: integrated multi-perspective analysis of tangled problems (wicked problems analysis, Rittel-Webber lineage)

# 1. TERRITORY AND POSITION
territory: T2-interest-and-power
gradation_position:
  axis: complexity
  value: systemic
  depth_axis_value: molecular
adjacent_modes_in_territory:
  - mode_id: cui-bono
    relationship: complexity-lighter sibling (simple)
  - mode_id: stakeholder-mapping
    relationship: complexity-mid sibling (multi-party-descriptive — note: lives in T8)
  - mode_id: decision-clarity
    relationship: depth-molecular sibling (decision-maker-output operation; built Wave 4)
  - mode_id: boundary-critique
    relationship: stance counterpart (critical/Ulrich CSH)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "this feels tangled"
    - "every solution we try makes it worse somewhere else"
    - "the problem itself keeps shifting as we try to define it"
    - "stakeholders disagree about what the problem even is"
  prompt_shape_signals:
    - "wicked problem"
    - "everything is connected"
    - "no clean solution"
    - "tradeoffs across multiple dimensions"
disambiguation_routing:
  routes_to_this_mode_when:
    - "tangled / wicked, want full integrated analysis with stakeholder + systems + scenario + adversarial views"
    - "willing to spend 10+ minutes for the deep version"
  routes_away_when:
    - "this one situation, who benefits" → cui-bono
    - "landscape of parties, descriptive" → stakeholder-mapping
    - "produce a decision document for a decision-maker" → decision-clarity
    - "want feedback dynamics analysis specifically" → systems-dynamics-causal
when_not_to_invoke:
  - "User has time pressure (Wicked Problems is Tier-3 ~10+ min)" → cui-bono or wicked-future light variant
  - "Problem is decision-shaped (single decision-maker, defined options)" → decision-clarity or decision-architecture

# 3. EXECUTION STRUCTURE
composition: molecular
molecular_spec:
  components:
    - mode_id: competing-hypotheses
      runs: fragment
      fragment_spec: "hypothesis-list-with-diagnosticity-only (matrix output, no full ACH report)"
    - mode_id: cui-bono
      runs: full
    - mode_id: steelman-construction
      runs: fragment
      fragment_spec: "steelman of two leading framings of the problem"
    - mode_id: systems-dynamics-causal
      runs: full
    - mode_id: scenario-planning
      runs: full
    - mode_id: red-team-assessment
      runs: fragment
      fragment_spec: "adversarial-stress-test of the leading intervention candidate (assessment stance — vulnerabilities ranked by severity for the user's own intervention-design fix-prioritisation)"
  synthesis_stages:
    - name: framing-reconciliation
      type: dialectical-resolution
      input: [competing-hypotheses-fragment, steelman-construction-fragment, cui-bono]
      output: "reconciled framing with named tensions and dominant-frame note"
    - name: dynamic-projection
      type: sequenced-build
      input: [framing-reconciliation, systems-dynamics-causal, scenario-planning]
      output: "dynamic projection of the problem under multiple framings and scenarios"
    - name: intervention-stress-test
      type: contradiction-surfacing
      input: [dynamic-projection, red-team-fragment]
      output: "candidate-intervention catalog with stress-test findings"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; do not aggregate over low-confidence findings

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [problem_statement, stakeholder_inventory, prior_intervention_history]
    optional: [domain_briefing, prior_systems_analyses]
    notes: "Applies when user supplies stakeholder inventory or prior analyses."
  accessible_mode:
    required: [problem_description]
    optional: [contextual_background]
    notes: "Default. Mode elicits stakeholder inventory and prior interventions during execution."
  detection:
    expert_signals: ["stakeholder inventory", "prior interventions", "intervention history"]
    accessible_signals: ["this is wicked", "everything is connected", "solutions keep failing"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe the problem and any history of attempts to address it?'"
    on_underspecified: "Ask the user whether they want to spend the time on a full Wicked Problems pass, or a lighter Cui Bono / Stakeholder Mapping read."
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have all major framings been steelmanned, or has the analysis privileged one frame?"
    failure_mode_if_unmet: frame-privileging
  - cq_id: CQ2
    question: "Do the systems-dynamics findings actually integrate with the cui-bono findings, or do they sit in separate silos?"
    failure_mode_if_unmet: silo-aggregation
  - cq_id: CQ3
    question: "Have candidate interventions been stress-tested against the leading adversarial scenarios, or only against neutral projections?"
    failure_mode_if_unmet: stress-test-omission
  - cq_id: CQ4
    question: "Are the residual tensions named explicitly, or has the synthesis collapsed them prematurely?"
    failure_mode_if_unmet: premature-resolution

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: frame-privileging
    detection_signal: "Steelman-construction-fragment surfaces only one framing."
    correction_protocol: re-dispatch (to second steelman pass)
  - name: silo-aggregation
    detection_signal: "Synthesis stage outputs concatenate component outputs without integration."
    correction_protocol: re-dispatch (synthesis stage with explicit integration prompt)
  - name: stress-test-omission
    detection_signal: "red-team-fragment did not run against the leading intervention."
    correction_protocol: flag and re-dispatch
  - name: premature-resolution
    detection_signal: "Output presents a single recommended intervention without residual tensions."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - rittel-webber-wicked-characteristics
    - meadows-twelve-leverage-points
    - senge-system-archetypes
  optional:
    - ulrich-csh-boundary-categories
    - tetlock-superforecasting (when scenarios extend beyond ~5 years)
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Wicked Problems is the heaviest mode in T2's complexity ladder."
  sideways:
    target_mode_id: decision-clarity
    when: "Output should be a decision-clarity document for a decision-maker rather than an integrated analysis."
  downward:
    target_mode_id: cui-bono
    when: "User has time pressure or scope is narrower than initially estimated."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Wicked Problems Analysis is the degree to which framing-reconciliation, dynamic-projection, and intervention-stress-test stages actually integrate their component outputs rather than concatenating them. A thin molecular pass runs each component and aggregates; a substantive pass surfaces the tensions between components and resolves them dialectically. Test depth by asking: does the synthesis output contain claims that no single component could have produced?

## BREADTH ANALYSIS GUIDANCE

Breadth in Wicked Problems Analysis is the catalog of framings considered before the steelman fragment narrows to two leading framings. Widen the lens to scan: dominant-paradigm framing; stakeholder-position framing; historical-genealogy framing; cross-domain analogical framing. Even when only two framings are steelmanned, breadth is documented in the framing-reconciliation stage.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Wicked Problems is a depth-molecular, complexity-systemic T2 mode in the Rittel-Webber tradition that composes competing-hypotheses (fragment — diagnosticity matrix), cui-bono (full), steelman-construction (fragment — two leading framings), systems-dynamics-causal (full), scenario-planning (full), and red-team-assessment (fragment — intervention stress-test) into an integrated analysis of a tangled problem. Read with Meadows twelve-leverage-points and Senge system-archetypes as the systems-dynamics layer, plus Ulrich CSH boundary-categories where boundary-critique cross-cuts. The mode is distinct from cui-bono (T2 simple/lighter — single situation, who benefits), stakeholder-mapping (T8 multi-party-descriptive), decision-clarity (T2 depth-molecular — decision-maker-output operation), boundary-critique (T2 stance counterpart — Ulrich CSH), and systems-dynamics-causal (feedback-dynamics-only). The mode's posture is anti-resolution: it honors irresolvability where the wicked characteristics demand it; collapsing tensions is a failure mode, not a polish.

**Procedure.**

1. State the problem once and tag which Rittel-Webber wicked characteristics actually apply (undefinability / no-stopping-rule / no-right-answer / irreversibility / every-attempt-counts / no-enumerable-solution-set / sui-generis), naming characteristics that do not apply explicitly.
2. Steelman at least two leading framings of the problem at comparable depth — each with worldview, account of the problem under this framing, and stakeholders who hold it.
3. Run cui-bono on the problem — stakeholder-interest atoms distinguish beneficiaries of the problem's current state from beneficiaries of its resolution; each stakeholder cross-referenced to a framing.
4. Run competing-hypotheses fragment — diagnosticity matrix on candidate framings, naming the evidence that would differentiate them.
5. Run systems-dynamics-causal — feedback loops and causal mechanisms, each with polarity (R/B) and Meadows leverage-point tag (12 constants → 1 transcending-paradigm); name Senge archetype signatures where present (limits-to-growth, shifting-the-burden, tragedy-of-the-commons, fixes-that-fail, escalation, success-to-the-successful, eroding-goals, accidental-adversaries, growth-and-underinvestment).
6. Run scenario-planning — scenarios under multiple framings with driving uncertainties; preserve scenarios that diverge across framings (their frame-dependence is the finding).
7. Surface candidate interventions, each tagged with target Meadows leverage-point and the framing's account it addresses.
8. Run red-team-assessment fragment on the leading interventions — vulnerability statements with severity, mechanism by which the intervention fails, stakeholder dynamics emerging under stress. Interventions without attached stress-test atoms do not survive.
9. Integrate dialectically — framing-reconciliation (named tensions, dominant-frame note), dynamic-projection (frame-dependent dynamics), intervention-stress-test (interventions whose outcome flips under a different framing). Synthesis-stage outputs must contain claims no single component could have produced.
10. Preserve residual tensions explicitly — each tension naming which wickedness characteristic makes resolution unavailable and what the user lives with rather than resolves. Premature-resolution is a load-bearing failure mode.
11. Calibrate confidence per finding; synthesis-stage atoms inherit lower confidence from component aggregation and the deliverable surfaces this rather than presenting synthesized findings at component-level confidence.

**Goal.** Produce a structured wicked-problems analysis — problem statement with wickedness-characteristics tags, multiple steelmanned framings with named tensions, stakeholder-interest map, causal dynamics with Meadows leverage-point tags, scenario projections under multiple framings, candidate interventions with red-team stress-test findings, and preserved residual tensions that the user lives with rather than resolves.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — multi-frame analysis.** Have all major framings been steelmanned, or has the analysis privileged one frame? Failure mode if unmet: `frame-privileging`.
- **CQ2 — molecular integration.** Do the systems-dynamics findings actually integrate with the cui-bono findings, or do they sit in separate silos? Failure mode if unmet: `silo-aggregation`.
- **CQ3 — adversarial stress test.** Have candidate interventions been stress-tested against the leading adversarial scenarios, or only against neutral projections? Failure mode if unmet: `stress-test-omission`.
- **CQ4 — residual tensions preserved.** Are the residual tensions named explicitly, or has the synthesis collapsed them prematurely? Failure mode if unmet: `premature-resolution`.

All four CQs are load-bearing — Wicked Problems is the deepest analytical mode and the standards are concurrent rather than ranked. A passing output tags applicable Rittel-Webber characteristics, steelmans at least two framings, surfaces stakeholder-interest distinctions, tags each causal mechanism with a Meadows leverage-point, projects scenarios under multiple framings, attaches red-team findings to every surviving intervention candidate, preserves residual tensions in their own structurally prominent section, and never collapses to a single recommendation.

**Named failure modes.**

- *frame-privileging* — steelman-construction fragment surfaces only one framing.
- *silo-aggregation* — synthesis stage outputs concatenate component outputs without integration.
- *stress-test-omission* — red-team-fragment did not run against the leading intervention.
- *premature-resolution* — output presents a single recommended intervention without residual tensions.

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates. Revise to surface residual tensions where the draft has resolved them. Resist revising toward clean-recommendation framing — Wicked Problems Analysis honors irresolvability; collapsing tensions is a failure mode, not a polish.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **multiple steelmanned framing atoms with attached stakeholder-interest, causal-dynamics, scenario, leverage-point, and stress-test atoms, with residual tensions preserved**. Three synthesis stages drive the corpus: framing-reconciliation, dynamic-projection, intervention-stress-test. The Rittel-Webber wicked-characteristics lens anchors what counts as "wicked" — undefinability, no-stopping-rule, no-right-answer, irreversibility, every-attempt-counts, no-enumerable-solution-set, sui-generis. The atoms are:

1. **Problem-statement atom with wickedness-characteristics tags.** The problem stated once at the corpus head, with explicit tagging of which Rittel-Webber wicked characteristics apply (and which do not — not every "tangled" problem is genuinely wicked across all characteristics). This atom anchors the corpus's analytical posture: the analysis honors irresolvability where the characteristics demand it.

2. **Framing atoms — multiple, steelmanned.** Each framing atom carries: framing name, the worldview that produces it, its account of the problem (what the problem IS under this framing), its steelmanned strongest version (from steelman-construction fragment), and the stakeholders who hold this framing. Frame-privileging is the named failure mode; corpus with only one framing surfaced is its signature. At least two framings must survive cross-stream dedup, both steelmanned. The framing-reconciliation atom (item 9) names the tensions between them.

3. **Stakeholder-interest atoms (cui-bono provenance).** Each carries: stakeholder, their interest in the problem persisting / resolving / shifting, their position in the power asymmetry, and which framing they hold (cross-reference to framing atoms). Beneficiaries of the problem's current state are surfaced distinctly from beneficiaries of its resolution.

4. **Hypothesis-diagnosticity atoms (competing-hypotheses fragment provenance).** Hypothesis-list-with-diagnosticity-only — which candidate framings of the problem are most diagnostically distinguishable, with the evidence that would differentiate them. Carries the matrix-fragment structure from competing-hypotheses.

5. **Causal-dynamics atoms (systems-dynamics-causal provenance).** Each carries: feedback loop or causal mechanism, polarity (reinforcing / balancing), and **Meadows leverage-point tag** — which of the twelve leverage points the mechanism operates at (lowest: constants and parameters; highest: paradigms and goals of the system). The leverage-point tag is operative — it determines where intervention candidates apply.

6. **System-archetype atoms (Senge provenance) — when applicable.** When the causal-dynamics show a recognizable archetype signature (limits-to-growth, shifting-the-burden, tragedy-of-the-commons, success-to-the-successful, fixes-that-fail, eroding-goals, escalation, accidental-adversaries, growth-and-underinvestment), name the archetype atom. The archetype gives a discriminating shape to the dynamics that bare causal mechanisms do not.

7. **Scenario atoms (scenario-planning provenance).** Each carries: scenario narrative, time horizon, driving uncertainties, which framings produce this scenario, and which stakeholders benefit / lose. Scenarios that are variations of the same framing collapse during dedup; scenarios from different framings preserve as parallel atoms because they reveal frame-dependence of the problem's trajectory.

8. **Intervention-candidate atoms with stress-test findings.** Each intervention atom carries: intervention statement, which framing's account it addresses, target leverage-point (per Meadows), and red-team stress-test findings (vulnerability statement, severity, mechanism by which the intervention fails). Stress-test-omission is the named failure mode; intervention candidates without attached stress-test atoms do not survive corpus assembly. The leading intervention(s) must carry red-team stress-test atoms.

9. **Reconciled-framing atom with named tensions and dominant-frame note.** A corpus-level synthesis atom names: which framings the analysis reconciles, which it leaves in tension (because the tension is the finding), and which framing — if any — appears dominant in the user's situation (with the structural reason for dominance). The reconciliation does not pick one framing as correct; it names the relationships among framings.

10. **Residual-tensions atoms.** Each names a tension that survives the synthesis — a place where the wicked characteristics make resolution unavailable. Premature-resolution is the named failure mode; corpus with a single recommended intervention and no residual tensions is its signature. The corpus carries multiple residual-tension atoms when the problem is genuinely wicked, with explicit acknowledgment that the user lives with the tensions rather than resolves them.

11. **Component-provenance tags.** Each atom in items 3–8 carries an explicit provenance tag (cui-bono / competing-hypotheses-fragment / systems-dynamics-causal / scenario-planning / red-team-fragment / steelman-fragment). Silo-aggregation is the named failure mode; the provenance tags make integration auditable — when two atoms from different components attach to the same finding, that's integration; when atoms sit in single-component clusters, that's concatenation.

12. **Confidence map per finding.** Confidence markers attach to individual atoms. Synthesis-stage atoms inherit lower confidence from component aggregation; the corpus flags this explicitly rather than presenting synthesized findings at component-level confidence.

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Single-framing residue** — corpus material that elaborates one framing while neglecting alternatives. Frame-privileging residue; the corpus carries at least two steelmanned framings, and single-framing material either gets paired with the alternative steelmanning or is downgraded.
- **Component-output transcription** — prose that re-states cui-bono's output, then systems-dynamics-causal's output, then scenario-planning's output without integration. Silo-aggregation residue; component-output transcription does not survive the integration discipline.
- **Stress-test-absent intervention candidates** — interventions named without attached red-team findings. Stress-test-omission residue; the intervention atom is incomplete and either earns a stress-test atom or migrates to "candidate-considered-not-stress-tested" with explicit reason.
- **Recommendation-collapse residue** — phrases like "the best approach is", "the recommended intervention is" without residual tensions surfaced. Premature-resolution residue; wicked problems do not collapse to clean recommendations — corpus carries the candidate-intervention-catalog with stress-test findings AND the residual tensions, not a single recommendation.
- **Wickedness-language without characteristics** — "this is a wicked problem" stated without tagging which Rittel-Webber characteristics actually apply. Either the characteristics are tagged or the wickedness claim is unsupported residue.
- **Leverage-point-untagged dynamics** — causal mechanisms named without Meadows leverage-point tagging. The tag is operative for intervention design; mechanisms without tags survive only when leverage-point cannot be assigned (with reason).

**What NOT to collapse:**

- **Genuinely different framings** — preserve all surviving steelmanned framings as parallel atoms. The wicked-problems methodology requires multi-frame analysis; merging non-overlapping framings is frame-privileging residue.
- **Intervention-candidate disagreement** — when streams proposed different leading interventions, preserve all candidates with their stress-test findings. The corpus is a catalog, not a recommendation.
- **Residual-tension content** — never reconcile residual tensions during consolidation. The tensions are the finding; the corpus's value is naming them so the user can live with them deliberately rather than be surprised by their persistence.
- **Framing-vs-framing causal-dynamics disagreement** — when systems-dynamics-causal analysis under framing A produced different feedback loops than under framing B, preserve both as frame-dependent-dynamics atoms. The frame-dependence is itself a finding about wickedness.

## VERIFICATION CRITERIA

Verified means: every component ran (or was flagged as proceeded-with-gap); synthesis stages integrated rather than concatenated; residual tensions are named; confidence map is populated. The four critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structured wicked-problems analysis: problem statement with wickedness-characteristics tags, multiple steelmanned framings, causal dynamics with leverage-point tags, candidate interventions with stress-test findings, and preserved residual tensions**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Problem with wickedness characteristics.** Two blocks:
   - **Problem statement:** one or two sentences naming the problem.
   - **Wickedness characteristics that apply:** numbered list of which Rittel-Webber characteristics obtain (undefinability / no-stopping-rule / no-right-answer / irreversibility / every-attempt-counts / no-enumerable-solution-set / sui-generis), with a one-line reason for each. Characteristics that do not apply: noted explicitly (`Characteristic [N]: does not apply because [...]`).

2. **Reconciled framing — multiple steelmanned framings with named tensions.** For each surviving framing F1, F2, F3, …, render an H3 sub-section:
   - **Framing name** — the worldview that produces it
   - **Account of the problem:** what the problem IS under this framing
   - **Steelmanned strongest version:** one paragraph
   - **Stakeholders who hold this framing:** [list]

   At minimum two framings, both steelmanned. After the per-framing blocks, render: `**Reconciliation notes:** [which framings the analysis reconciles; which it leaves in tension because the tension is the finding]. Dominant frame in the user's situation: [framing X — with the structural reason for dominance, OR "no single dominant frame"].`

3. **Competing-framing diagnosticity matrix (competing-hypotheses provenance).** Render as a distinct table — one row per candidate framing/hypothesis; columns `Framing | Evidence that would confirm it | Evidence that would disconfirm it`. This is the diagnosticity-atom corpus from the competing-hypotheses fragment, surfaced as its own structure: it is structurally distinct from the framing narrative (section 2) and the confidence map (section 10), and is never merged into either. When local data can't weight the matrix (the evidence to differentiate framings is not available in context), note that beneath the table rather than omitting the section.

4. **Stakeholder-interest map (cui-bono provenance).** Numbered list of stakeholders. Each: `**[Stakeholder]** — interest in problem [persisting / resolving / shifting]. Position in power asymmetry: [...]. Framing they hold: [F_n cross-reference].` Beneficiaries of the problem's current state are distinguished from beneficiaries of its resolution.

5. **Dynamic projection — causal dynamics with leverage-point tags (systems-dynamics-causal provenance).** Numbered list of feedback loops / causal mechanisms. Each: `**[Loop or mechanism]** — polarity: [reinforcing / balancing]. **Meadows leverage-point tag:** [one of the twelve levels — constants, buffers, stock-and-flow, delays, balancing loops, reinforcing loops, information flows, rules, self-organization, goals, paradigms, transcending-paradigms]. Mechanism: [how the dynamic operates].`

6. **System archetype atoms (Senge provenance) — when applicable.** Bulleted list of recognized archetype signatures (limits-to-growth / shifting-the-burden / tragedy-of-the-commons / success-to-the-successful / fixes-that-fail / eroding-goals / escalation / accidental-adversaries / growth-and-underinvestment). When no archetype signatures are present, write "No recognized system-archetype signatures in the dynamics."

7. **Scenario projections (scenario-planning provenance).** Bulleted list of scenarios under multiple framings. Each: `**[Scenario]** — time horizon: [...]. Driving uncertainties: [...]. Under which framings: [F_n cross-references]. Which stakeholders benefit/lose: [...].`

8. **Candidate intervention catalog with stress-test findings (red-team provenance).** For each candidate intervention I1, I2, I3, …, render:
   - **Intervention:** statement
   - **Which framing's account it addresses:** F_n
   - **Target Meadows leverage point:** [tag from section 5]
   - **Red-team stress-test findings:** numbered list of vulnerabilities, each: `**[Vulnerability]** — severity: [high / moderate / low]. Mechanism by which the intervention fails: [...].`

   Interventions without attached stress-test findings do not appear — stress-test-omission is the named failure mode.

9. **Residual tensions — never resolved.** Numbered list of tensions that survive the analysis. Each: `**[Tension]** — why irreducible: [which wickedness characteristic makes resolution unavailable]. What the user lives with: [the specific trade-off or open question that persists].` Premature-resolution is the named failure mode; corpus with a single recommended intervention and no residual tensions is its signature.

10. **Confidence map.** Bulleted list of confidence markers per major finding. Synthesis-stage atoms inherit lower confidence from component aggregation; flag this explicitly rather than presenting synthesized findings at component-level confidence.

**Per-section conventions:**

- Use H2 headings for sections 1 through 10.
- Framing IDs (F1, F2, ...), stakeholder IDs, intervention IDs (I1, I2, ...) are referenced consistently throughout once introduced.
- Section 3's diagnosticity matrix is a standalone table, never dissolved into the framing narrative (section 2) or the confidence map (section 10).
- Section 5's leverage-point tags use Meadows' canonical twelve-level vocabulary; do not invent intermediate levels.
- Avoid recommendation-collapse phrasings: "the best approach is", "the recommended intervention is" — wicked problems do not collapse to clean recommendations.
- Section 9's residual tensions are visibly load-bearing — do not hide them in a final footnote or confidence map.

## CAVEATS AND OPEN DEBATES

**Debate D3 — Wicked problems: sui generis or extreme cases of complex problems?** Rittel & Webber (1973) treat wickedness as intrinsic and distinct from ordinary complexity. Later scholarship (Pesch & Vermaas 2020; some complexity-science readings) treats wicked problems as extreme cases along the complexity gradient rather than as a separate category. This mode operates without adjudicating the debate: it applies the Rittel-Webber characteristics as analytical lens (treating "wickedness" as a useful descriptor for problems exhibiting the ten characteristics) while remaining agnostic on whether wickedness is a category or a degree. Citations: Rittel & Webber 1973; Pesch & Vermaas 2020; Conklin 2006 (*Dialogue Mapping*).

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~10+min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- OPV
- KVI
- CAF
- C&S
- FIP
- Concept Fan
- APC
- RAD

Mental models (always loaded):
- nash-equilibrium
- batna
- cooperation
- prisoners-dilemma
- tragedy-of-the-commons
- bounded-rationality
- schelling-point

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `requires`, `enables`, `contradicts`, `supports`, `qualifies`
**Deprioritize:** `parent`, `analogous-to`

*Family: stakeholder-strategy. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
