---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Balanced Critique

```yaml
# 0. IDENTITY
mode_id: balanced-critique
canonical_name: Balanced Critique
suffix_rule: analysis
educational_name: balanced critique (neutral stance, multi-perspective)

# 1. TERRITORY AND POSITION
territory: T15-artifact-evaluation-by-stance
gradation_position:
  axis: stance
  value: neutral
adjacent_modes_in_territory:
  - mode_id: steelman-construction
    relationship: stance-counterpart (constructive-strong; lives primarily in T15 with cross-reference to T1)
  - mode_id: benefits-analysis
    relationship: stance-counterpart (constructive-balanced)
  - mode_id: red-team-assessment
    relationship: stance-counterpart (adversarial-actor-modeling, assessment)
  - mode_id: red-team-advocate
    relationship: stance-counterpart (adversarial-actor-modeling, advocate)
  - mode_id: devils-advocate-lite
    relationship: stance-counterpart (adversarial-light; gap-deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "give me a balanced read on this"
    - "I want both sides — strengths and weaknesses, not advocacy"
    - "what holds up and what doesn't"
    - "neutral assessment of this proposal"
    - "I don't want a steelman or a teardown — I want a fair evaluation"
  prompt_shape_signals:
    - "balanced critique"
    - "balanced assessment"
    - "balanced evaluation"
    - "fair evaluation"
    - "strengths and weaknesses"
    - "what holds up"
    - "what doesn't"
    - "neutral read"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants the artifact (plan, proposal, idea) evaluated with neutral stance"
    - "user explicitly rejects advocacy framing in either direction"
    - "user wants strengths AND weaknesses surfaced with comparable rigor"
  routes_away_when:
    - "user wants the strongest possible case for the artifact" → steelman-construction
    - "user wants advantages and minor risks but not adversarial teardown" → benefits-analysis
    - "user wants adversarial-actor stress test for own decision" → red-team-assessment
    - "user wants adversarial argument brief for external use" → red-team-advocate
    - "user wants light contrarian sanity check" → devils-advocate-lite (when built)
when_not_to_invoke:
  - "User wants soundness audit of an argument-as-argument" → T1 modes (Coherence Audit, Frame Audit, Argument Audit)
  - "User wants structural fragility analysis of a system" → pre-mortem-fragility (T7)
  - "User has not provided an artifact to evaluate" → degrade to elicitation

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: neutral

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [artifact, evaluation_criteria, intended_audience_or_purpose]
    optional: [comparable_alternatives, stakeholder_perspectives, prior_evaluations]
    notes: "Applies when user supplies the artifact along with criteria for evaluation."
  accessible_mode:
    required: [artifact_or_proposal]
    optional: [what_user_cares_about_in_evaluation]
    notes: "Default. Mode infers evaluation criteria from the artifact's stated purpose."
  detection:
    expert_signals: ["evaluation criteria", "intended audience", "compare against alternatives", "prior evaluations"]
    accessible_signals: ["balanced read", "fair evaluation", "strengths and weaknesses", "what holds up"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you share the proposal or plan you want evaluated, and what matters to you about it?'"
    on_underspecified: "Ask: 'Roughly what should this proposal accomplish, so I can weigh strengths and weaknesses against that purpose?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have strengths and weaknesses been surfaced with comparable rigor, or has one side been treated more thoroughly than the other?"
    failure_mode_if_unmet: stance-tilt
  - cq_id: CQ2
    question: "Have findings that are perspective-dependent (true from one stakeholder vantage, false from another) been flagged as such, rather than asserted as universal?"
    failure_mode_if_unmet: false-universality
  - cq_id: CQ3
    question: "Have residual tensions been named in the net assessment, or has the synthesis collapsed them into a tidy verdict?"
    failure_mode_if_unmet: premature-resolution
  - cq_id: CQ4
    question: "Are claims of strength and weakness backed by specific evidence from the artifact (or absence thereof), rather than asserted by analyst preference?"
    failure_mode_if_unmet: opinion-as-evaluation

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: stance-tilt
    detection_signal: "Strengths and weaknesses sections are asymmetric in length, specificity, or evidence depth; the analysis has slipped into advocacy or critique."
    correction_protocol: re-dispatch
  - name: false-universality
    detection_signal: "Findings that depend on stakeholder perspective are stated as universal; perspective-dependent section is empty or trivial."
    correction_protocol: re-dispatch
  - name: premature-resolution
    detection_signal: "Net assessment delivers a verdict without naming the residual tensions; the strengths and weaknesses are silently overridden by the synthesis."
    correction_protocol: flag
  - name: opinion-as-evaluation
    detection_signal: "Claims of strength or weakness are unbacked by specific evidence; the analysis reads as the analyst's preferences."
    correction_protocol: re-dispatch
  - name: bothsidesism
    detection_signal: "Strengths and weaknesses are forced into balance even when the artifact is genuinely strong (or weak); the mode's neutrality has become artificial symmetry."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - rumelt-strategy-kernel (when artifact is a strategy document)
    - debono-pmi (Plus-Minus-Interesting as light scaffolding)
    - ulrich-csh-boundary-categories (when boundary-critique surfaces in the perspective-dependent section)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Balanced Critique is the heaviest neutral-stance mode in T15; deeper evaluation routes sideways to molecular composites in adjacent territories."
  sideways:
    target_mode_id: steelman-construction
    when: "User shifts to wanting the strongest case for the artifact rather than balanced read."
  downward:
    target_mode_id: benefits-analysis
    when: "User wants lighter constructive-balanced read rather than full strengths-and-weaknesses synthesis."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Balanced Critique is the rigor with which strengths and weaknesses are evidenced from the artifact itself rather than from analyst preference. A thin pass produces a list of pros and cons; a substantive pass cites the specific element of the artifact that constitutes each strength or weakness, names the conditions under which the strength would fail to hold or the weakness would not bite, and surfaces assumptions whose alteration would shift the assessment. Test depth by asking: could the user trace each strength/weakness claim back to a specific feature of the artifact?

## BREADTH ANALYSIS GUIDANCE

Widening the lens in Balanced Critique means deliberate scanning across stakeholder perspectives — what looks like a strength from the user's vantage may be a weakness from another's; what looks settled may be contested. The breadth pass surfaces perspective-dependent findings and flags them as such rather than asserting universal evaluations. Adjacent considerations (comparable alternatives, opportunity costs, downstream consequences) are scanned as inputs to the assessment even when they are not the primary focus.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Balanced Critique is a neutral-stance evaluation that surfaces strengths and weaknesses of an artifact with comparable rigor, flags perspective-dependent findings, and resists collapse into a single verdict. It is distinct from steelman-construction (which advocates the strongest version of the artifact), benefits-analysis (constructive-balanced PMI envelope), and the red-team modes (adversarial-actor stress testing). Its neutrality is in evaluative method — symmetric depth of evidence — not in forced symmetry of conclusions; honest asymmetry survives into the output.

**Procedure.**

1. Restate the artifact under evaluation in one neutral paragraph at the head — no advocacy lean, no teardown framing.
2. Identify evaluation criteria from the artifact's stated purpose (or elicited purpose) before surfacing claims.
3. Surface strengths — each one tied to a specific element of the artifact, with evidence basis, conditions under which the strength would fail to hold, and a qualifier-depth tag (load-bearing / moderate / minor).
4. Surface weaknesses at parallel depth — same structural template, same evidence-citation density. Asymmetry between Strengths and Weaknesses sections is a stance-tilt signal.
5. Scan across stakeholder vantages — findings whose valence depends on whose seat one inhabits are tagged as perspective-dependent and named with the constituency on each side, not asserted as universal.
6. Surface load-bearing assumptions whose alteration would shift the evaluation, and the uncertainties whose resolution would settle open disagreements.
7. Build a net assessment that explicitly names the residual tensions surviving the synthesis — the assessment is allowed to be qualified; single-verdict endings are premature-resolution.
8. Report the honest distribution — N strengths to N weaknesses — and name asymmetry where it exists, rather than padding the weaker side.
9. Assign confidence per finding with explicit basis (training-grounded, RAG-grounded, user-supplied, analyst inference).

**Goal.** Produce a structured neutral-stance evaluation with paired strength/weakness atoms rendered at parallel depth, perspective-tagged findings, residual tensions surfaced, and honest distribution reported rather than padded.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — symmetric rigor.** Have strengths and weaknesses been surfaced with comparable rigor, or has one side been treated more thoroughly? Failure mode if unmet: `stance-tilt`.
- **CQ2 — perspective-dependence flagged.** Have findings that hold from one stakeholder vantage and not another been flagged as such rather than asserted as universal? Failure mode if unmet: `false-universality`.
- **CQ3 — residual tensions named.** Have residual tensions been named in the net assessment, or has the synthesis collapsed them into a tidy verdict? Failure mode if unmet: `premature-resolution`.
- **CQ4 — evidence-grounded claims.** Are claims of strength and weakness backed by specific evidence from the artifact rather than analyst preference? Failure mode if unmet: `opinion-as-evaluation`.

A passing output presents strengths and weaknesses with comparable evidence depth tied to specific artifact elements, flags perspective-dependence with named stakeholder vantages, names residual tensions in the synthesis, reports honest distribution rather than padded balance, and assigns confidence per finding.

**Named failure modes.**

- *stance-tilt* — strengths and weaknesses sections asymmetric in length, specificity, or evidence depth; analysis has slipped into advocacy or critique.
- *false-universality* — findings dependent on stakeholder perspective stated as universal; perspective-dependent section empty or trivial.
- *premature-resolution* — net assessment delivers a verdict without naming residual tensions; synthesis silently overrides surfaced strengths and weaknesses.
- *opinion-as-evaluation* — claims unbacked by specific evidence; analysis reads as analyst preferences.
- *bothsidesism* — strengths and weaknesses forced into balance even when the artifact is genuinely strong or weak; neutrality has become artificial symmetry.

## REVISION GUIDANCE

Revise to restore symmetric rigor where the draft has tilted toward advocacy or teardown. Revise to flag perspective-dependent findings where universal claims have been made. Revise to surface residual tensions where the net assessment has collapsed them. Resist revising toward an artificial 50/50 balance when the artifact is genuinely strong or genuinely weak — the mode's neutrality is in evaluative method, not in forced symmetry of conclusions. Resist revising toward a single-verdict ending; net assessment is allowed to be qualified.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **paired strength/weakness atoms with parallel evidence depth and explicit perspective-tagging**. The neutrality of balanced critique is in evaluative method, not in forced symmetry of conclusions; the corpus carries the honest distribution. The atoms are:

1. **Artifact-summary atom.** One-paragraph neutral summary of the artifact under evaluation, stated once at the corpus head. Cross-stream paraphrase collapses to one canonical version.

2. **Strength atoms.** Each carries: claim, specific artifact-element citation (the precise feature constituting the strength), evidence basis (training / RAG / user-supplied / inference), conditions-under-which-strength-fails-to-hold (the qualifier on the strength), and qualifier-depth tag (load-bearing / moderate / minor). Generic strengths that could apply to any artifact of this type do not survive — opinion-as-evaluation; the mode's posture is evidence-grounded specificity.

3. **Weakness atoms.** Parallel structure to strength atoms — claim, artifact-element citation, evidence basis, conditions-under-which-weakness-does-not-bite, qualifier-depth tag. The structural parallelism between strength and weakness atom shape is load-bearing: stance-tilt is the named failure mode, and structurally asymmetric atom shape is its detection signal.

4. **Assumption-and-uncertainty atoms.** Each names an assumption load-bearing on the artifact (or on the evaluation) whose alteration would shift the assessment. Uncertainty atoms name what additional information would resolve open questions.

5. **Perspective-dependent atoms.** Each carries: finding, stakeholder vantage from which it holds, stakeholder vantage from which it does not, and the structural reason for the perspective-dependence. False-universality is the named failure mode here; findings that are perspective-dependent must be tagged as such, not asserted as universal.

6. **Net-assessment atom with residual tensions.** A single corpus-level synthesis atom carries: the qualified net assessment (allowed to be qualified, not forced to a single verdict), and the residual tensions that survive the synthesis. Premature-resolution is the named failure mode — collapse of residual tensions into a tidy verdict is the corpus's failure, not its closure.

7. **Honest-distribution atom.** The raw count after dedup: N strength atoms, N weakness atoms, with explicit acknowledgement when N differs substantially. Bothsidesism is the named failure mode; the corpus carries the actual distribution rather than padded symmetry. When the artifact is genuinely 5-strengths-1-weakness or 1-strength-5-weaknesses, that asymmetry survives into the corpus.

8. **Confidence per finding.** Confidence markers attach to individual atoms. When the two streams assigned different confidences to the same finding, audit conservatism applies (the lower confidence survives).

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Strength-paraphrase / weakness-paraphrase** — both streams may state the same finding in slightly different language. Single canonical statement survives with the most precise artifact-element citation.
- **Opinion-language residue** — phrasings like "I think", "this seems", "appears to be", "in my view" not backed by evidence basis. Opinion-as-evaluation is the named failure mode; opinion-language survives only when paired with concrete evidence (in which case the evidence statement survives and the opinion-framing is cut).
- **Bothsidesism padding** — phrasings like "for every strength there's a corresponding weakness", "the strengths and weaknesses balance out", "both sides have merit". Forced-symmetry language does not survive; the honest-distribution atom carries the actual count.
- **Universal-claim residue** — claims that are perspective-dependent but appear unqualified in the streams. Either the claim is tagged with stakeholder vantage and migrates to perspective-dependent atoms, or it does not survive.
- **Verdict-shaped synthesis residue** — phrasings like "on balance", "overall the artifact is", "weighing the considerations". The net-assessment atom is allowed to be qualified, but verdict-collapse language that elides residual tensions is premature-resolution bloat.
- **Assumption-paraphrase loops** — same assumption named under different framings. Single assumption atom survives.

**What NOT to collapse:**

- **Real strength-weakness asymmetry** — when the artifact is genuinely strong-asymmetric (5 strengths, 1 weakness) or weak-asymmetric (1 strength, 5 weaknesses) and the asymmetry survives both streams' independent evaluations, that asymmetry is the finding. Padding to forced 50-50 is bothsidesism; the corpus carries the actual distribution and the net-assessment atom names it explicitly.
- **Cross-stream perspective disagreement** — when one stream applied a different stakeholder vantage than the other and produced different findings, preserve both as parallel perspective-dependent atoms (each tagged with its vantage). The disagreement is itself a finding about whose perspective the evaluation privileges.
- **Qualifier-strength disagreement** — when the two streams disagreed on whether a strength or weakness is load-bearing vs minor, preserve both qualifier-depth tags as a tension atom. The disagreement is a finding about the artifact's robustness to evaluative framing.

## VERIFICATION CRITERIA

Verified means: strengths and weaknesses sections are comparable in length, specificity, and evidence depth; every strength and weakness is tied to a specific element of the artifact; perspective-dependent findings are flagged with stakeholder vantage; residual tensions are named explicitly in the net assessment; the analysis is not artificially balanced when the artifact is genuinely asymmetric in quality; the four critical questions are addressable from the output. Confidence per finding accompanies each major claim.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structured neutral-stance evaluation with paired strength/weakness atoms rendered at parallel depth, perspective-tagged findings, and honest distribution**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Artifact summary.** One-paragraph neutral summary of the artifact under evaluation. Frame as "Artifact under evaluation:" — no advocacy lean.

2. **Strengths.** Bulleted list of strength atoms. Each bullet renders in this exact shape: `**[Claim]** — artifact element: [the specific feature constituting the strength]. Evidence: [basis]. Conditions under which it would not hold: [qualifier]. Qualifier depth: [load-bearing / moderate / minor].` Bulleted to make parallelism visible.

3. **Weaknesses.** **Identical structural template to Strengths.** Each bullet: `**[Claim]** — artifact element: [specific feature]. Evidence: [basis]. Conditions under which it would not bite: [qualifier]. Qualifier depth: [load-bearing / moderate / minor].` Visual and structural parity with Strengths is load-bearing for the neutral-stance posture; stance-tilt detection signals fire when the Weaknesses bullets read shallower or shorter than Strengths bullets without honest reason.

4. **Assumptions and uncertainties.** Two short subsections:
   - **Assumptions:** numbered list of load-bearing assumptions the artifact rests on; each assumption notes how it would shift the evaluation if altered.
   - **Uncertainties:** numbered list of open questions where additional information would resolve disagreements between strengths and weaknesses.

5. **Perspective-dependent findings.** Bulleted list. Each bullet: `**[Finding]** — holds from [stakeholder vantage A]; does not hold from [stakeholder vantage B]. Structural reason for perspective-dependence: [reason].` These atoms are not strengths or weaknesses — they are findings whose valence depends on whose vantage one inhabits.

6. **Net assessment with residual tensions.** A short prose block (not a verdict). Frame as: "On the case as evaluated, [qualified net characterization]. The tensions that survive the evaluation: [tension 1]; [tension 2]; …" The net assessment is allowed to be qualified — single-verdict ending is premature-resolution.

7. **Honest distribution.** One sentence: `Distribution: N strengths, N weaknesses.` When asymmetric (e.g., 5 strengths to 1 weakness), name the asymmetry explicitly: "Distribution is asymmetric: [reason — the artifact is genuinely strong/weak in this direction]." Do not pad weaker side to balance the count; bothsidesism is the named failure mode.

8. **Confidence per finding.** Bulleted list of major claims with confidence markers (high / moderate / low). One bullet per major finding.

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- Sections 2 and 3 (Strengths, Weaknesses) render at parallel depth — same bullet template, similar length per bullet, matching evidence-citation density. Visual asymmetry between these two sections is a stance-tilt detection signal.
- Stakeholder vantages in section 5 are named (e.g., "from the customer's vantage", "from the regulator's vantage"), not abstracted ("from some perspectives").
- Avoid verdict-collapse phrasings in the net assessment: "on balance", "overall", "in conclusion the artifact is" — keep the qualified characterization with residual tensions named.
- Avoid bothsidesism padding: do not write "for every strength there is a corresponding weakness" or similar forced-symmetry framings.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- OPV
- CAF
- Challenge
- Concept Fan
- FIP
- PMI

Mental models (always loaded):
- bayesian-reasoning
- confirmation-bias
- devils-advocacy
- walton-schemes-and-critical-questions
- occams-razor
- narrative-instinct

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `contradicts`, `qualifies`, `extends`
**Deprioritize:** `precedes`, `parent`

*Family: argument-evaluation. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
