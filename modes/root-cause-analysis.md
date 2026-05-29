---
nexus:
  - ora
type: mode
tags:
  - framework/instruction
  - architecture
date created: 2026-03-23
date modified: 2026-05-24

---

# MODE: Root Cause Analysis

```yaml
# 0. IDENTITY
mode_id: root-cause-analysis
canonical_name: Root Cause Analysis
suffix_rule: analysis
educational_name: backward causal-chain tracing for failure diagnosis (5 Whys / Ishikawa)

# 1. TERRITORY AND POSITION
territory: T4-causal-investigation
gradation_position:
  axis: complexity
  value: single-cause-chain
adjacent_modes_in_territory:
  - mode_id: systems-dynamics-causal
    relationship: complexity-heavier sibling (feedback-structure)
  - mode_id: causal-dag
    relationship: depth-thorough sibling (formalism-explicit, Pearl)
  - mode_id: process-tracing
    relationship: specificity-historical-event sibling (Bennett/Checkel)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "something has gone wrong and we don't know why"
    - "a problem has recurred despite attempts to fix it"
    - "the presented issue feels like a symptom, not the real problem"
    - "diagnostic investigation is needed before any fix"
  prompt_shape_signals:
    - "what are the root causes of"
    - "why does this keep happening"
    - "draw a fishbone"
    - "give me an Ishikawa"
    - "what's the real problem here"
    - "we tried X but it didn't work"
disambiguation_routing:
  routes_to_this_mode_when:
    - "specific failure or symptom whose causes need to be traced backward"
    - "single causal chain, no declared feedback loops"
    - "want a fishbone-style decomposition with category structure"
  routes_away_when:
    - "ongoing counterintuitive behaviour driven by feedback loops" → systems-dynamics-causal
    - "multiple competing explanations to adjudicate against evidence" → competing-hypotheses
    - "want a formal DAG with conditional independence reasoning" → causal-dag
    - "specific historical event needing trace evidence" → process-tracing
    - "forward-looking question (what could go wrong if we ship X)" → consequences-and-sequel
when_not_to_invoke:
  - "User is mapping how a system currently works (process map, no failure trace)" → T17 (process-mapping or systems-dynamics-structural)
  - "User is choosing between solutions and the diagnosis is settled" → T3 (constraint-mapping or decision-under-uncertainty)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [observed_failure, prior_fix_history, framework_preference]
    optional: [domain_briefing, prior_incident_reports, evidence_inventory]
    notes: "Applies when user supplies a structured incident description with prior fix attempts and may name a preferred Ishikawa framework (6M / 4P / 4S / 8P)."
  accessible_mode:
    required: [observed_failure_description]
    optional: [related_context, fix_attempts_so_far]
    notes: "Default. Mode infers framework choice from the failure domain."
  detection:
    expert_signals: ["incident report", "post-mortem", "6M / 4P / 4S / 8P", "prior fix attempts include"]
    accessible_signals: ["why does this keep happening", "what's the real problem", "we tried fixing X"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe what happened — the observable symptom, when it happens, and anything you've tried to fix it?'"
    on_underspecified: "Ask: 'What is the specific failure or symptom you want me to trace causes for?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the chain reached a genuine root cause, or has it stopped at an intermediate cause that itself has deeper causes beneath it?"
    failure_mode_if_unmet: premature-stop
  - cq_id: CQ2
    question: "Has any branch terminated at human error, bad judgment, or insufficient effort without naming the process that permitted or incentivised the behaviour?"
    failure_mode_if_unmet: human-error-terminal
  - cq_id: CQ3
    question: "Are causal claims supported by evidence, with correlation explicitly distinguished from causation on at least one link?"
    failure_mode_if_unmet: correlation-causation-conflation
  - cq_id: CQ4
    question: "Is the declared categorisation framework used coherently — every category populated by causes that genuinely belong, every category name canonical for the framework?"
    failure_mode_if_unmet: framework-incoherence

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: premature-stop
    detection_signal: "Chain accepts an intermediate cause as root because it is satisfying or actionable; one more 'why' would yield non-trivial deeper cause."
    correction_protocol: re-dispatch (ask one more 'why' on each candidate root)
  - name: human-error-terminal
    detection_signal: "Leaf cause names a person's mistake or judgment without a sub-cause naming the process, policy, or incentive structure that permitted it."
    correction_protocol: flag (mandatory fix — process-not-people is load-bearing)
  - name: correlation-causation-conflation
    detection_signal: "Causal links asserted without evidence of mechanism; co-occurrence treated as causation."
    correction_protocol: flag
  - name: framework-incoherence
    detection_signal: "Categories named before framework declared, or non-canonical category names within a declared canonical framework, or causes mixed across multiple frameworks."
    correction_protocol: re-dispatch (declare framework first, then re-categorise)
  - name: linear-chain-isolation
    detection_signal: "Single causal chain investigated without considering whether multiple chains converge on the same symptom."
    correction_protocol: flag (request second alternative chain)
  - name: restatement-as-cause
    detection_signal: "Cause paraphrases the effect ('deployments fail' → cause 'deployments are unreliable') rather than naming a deeper mechanism."
    correction_protocol: re-dispatch (rewrite at one level deeper)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - ishikawa-fishbone-frameworks
    - five-whys-protocol
  optional:
    - reason-swiss-cheese-model (when failure crosses multiple defensive layers)
    - dekker-just-culture (when human-error terminal needs process re-framing)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: systems-dynamics-causal
    when: "Causal analysis reveals feedback loops — corrective measures keep being counteracted by the system's own dynamics."
  sideways:
    target_mode_id: competing-hypotheses
    when: "Multiple plausible causal chains exist and the diagnostic question is which to credit, not how to deepen one."
  downward:
    target_mode_id: null
    when: "Root Cause Analysis is the lightest causal-investigation mode in T4."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Root Cause Analysis is the number of genuine causal levels traversed beneath the presented symptom. A thin pass names first-order causes within a category framework; a substantive pass continues the "why" chain to at least sub-cause depth 2 on at least one branch, distinguishes root causes (whose removal prevents recurrence) from contributing factors (which amplify probability), and surfaces the process or incentive structure beneath any human-error candidate. Test depth by asking: could the analysis predict whether a proposed fix targeting the named root cause would actually prevent recurrence?

## BREADTH ANALYSIS GUIDANCE

Breadth in Root Cause Analysis is the catalog of categories considered before the fishbone is committed and the alternative causal chains scanned before the dominant chain is locked. Widen the lens by considering: which canonical Ishikawa framework (6M, 4P, 4S, 8P) best matches the failure domain; whether two or more chains converge on the same symptom such that the actual cause is their interaction; whether contributing factors not on the dominant chain amplify the failure. Breadth markers: at least two alternative causal chains have been generated (even if only one ships), and contributing factors are recorded distinctly from root-cause leaves.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Root Cause Analysis is fishbone-structured backward causal-chain tracing (5 Whys / Ishikawa): the observed failure is decomposed by a declared canonical framework (6M / 4P / 4S / 8P), candidate causes within each category are descended through the why-chain to at least sub-cause depth 2, and human-error leaves are followed to the process / policy / incentive structure that permitted them. It is distinct from systems-dynamics-causal (the complexity-heavier sibling — feedback structures rather than single chains), from causal-dag (depth-thorough sibling — Pearl-style formal causal graphs), and from process-tracing (specificity-historical sibling — Bennett-Checkel evidence-test framework for a specific past event).

**Procedure.**

1. Phrase the presented problem as a failure (not as a desired target state) — "X currently exhibits failure mode Y," not "we need X to work better."
2. Declare the Ishikawa framework (6M / 4P / 4S / 8P) with rationale tying it to the failure domain — before naming categories, not after.
3. Populate canonical categories from the declared framework; non-canonical category names or mixing across frameworks is framework-incoherence.
4. Apply the 5-whys descent — reach sub-cause depth 2 on at least one branch; chains that stop at intermediate-and-actionable causes get one more "why" applied.
5. Wherever a leaf names human error, attach the process / policy / incentive sub-cause that permitted or incentivised the behaviour — process-not-people is load-bearing, not optional.
6. Distinguish root causes (removal prevents recurrence) from contributing factors (amplify probability but don't by themselves prevent recurrence).
7. Assess evidence per causal link — `mechanism`, `correlation`, `inference`; on at least one link, address correlation-vs-causation explicitly.
8. Consider whether multiple chains converge on the same symptom; surface alternative chains rather than smoothing for tidiness.
9. Translate to recommendations tagged `corrective` (addresses surfaced failure) or `preventive` (addresses root condition).
10. State confidence in the dominant chain (`low` / `moderate` / `high`) with reasoning.

**Goal.** Produce a fishbone-structured root-cause analysis that declares its Ishikawa framework, populates canonical categories, descends through 5-whys to genuine root causes (process-not-people), and distinguishes corrective from preventive recommendations.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — genuine root vs premature stop.** Has the chain reached a genuine root cause, or stopped at an intermediate cause that itself has deeper causes? Failure mode if unmet: `premature-stop`.
- **CQ2 — process-not-people terminal.** Has any branch terminated at human error, bad judgment, or insufficient effort without naming the process that permitted or incentivised the behaviour? Failure mode if unmet: `human-error-terminal`.
- **CQ3 — evidence per link.** Are causal claims supported by evidence, with correlation explicitly distinguished from causation on at least one link? Failure mode if unmet: `correlation-causation-conflation`.
- **CQ4 — framework coherence.** Is the declared categorisation framework used coherently — every category populated by causes that genuinely belong, every category name canonical for the framework? Failure mode if unmet: `framework-incoherence`.

A passing output declares its framework before naming categories, reaches sub-cause depth 2 on at least one branch, terminates no chain at human error without a process sub-cause, supports each causal link with evidence, and distinguishes root causes from contributing factors with explicit reasoning.

**Named failure modes.**

- *premature-stop* — chain accepts an intermediate cause as root because it is satisfying or actionable; one more "why" would yield non-trivial deeper cause.
- *human-error-terminal* — leaf cause names a person's mistake or judgment without a sub-cause naming the process, policy, or incentive structure that permitted it.
- *correlation-causation-conflation* — causal links asserted without evidence of mechanism; co-occurrence treated as causation.
- *framework-incoherence* — categories named before framework declared, or non-canonical category names within a declared canonical framework, or causes mixed across multiple frameworks.
- *linear-chain-isolation* — single causal chain investigated without considering whether multiple chains converge on the same symptom.
- *restatement-as-cause* — cause paraphrases the effect ("deployments fail" → cause "deployments are unreliable") rather than naming a deeper mechanism.

## REVISION GUIDANCE

Revise to deepen any branch that stops at an intermediate cause when one more "why" would yield non-trivial structure. Revise to add the process or incentive sub-cause beneath any human-error leaf — this is load-bearing, not optional. Revise to align category names with the declared framework's canonical set. Resist revising toward a single tidy causal chain when the analysis surfaced contributing factors or alternative chains — the residual complexity is a feature, not noise.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a backward-traced causal-chain atom set: presented-problem lock, declared Ishikawa framework with rationale, per-category cause atoms, root-cause atoms distinguished from contributing-factor atoms, per-link evidence atoms with correlation-vs-causation flagged, corrective-vs-preventive recommendation atoms, and alternative-framing atoms**. The atoms are:

1. **Presented-problem atom.** The observed failure, phrased as a failure (not as a desired target state). Subsequent atoms trace backward from this lock.

2. **Framework-declaration atom.** The Ishikawa framework chosen — `6M` (Manufacturing) / `4P` (Marketing) / `4S` (Service) / `8P` (Project) — with rationale tying the framework to the failure domain. Framework-incoherence is the named failure mode the consolidator watches for; categories named before framework declared, non-canonical names within a declared framework, or causes mixed across frameworks get reshaped.

3. **Per-category cause atoms.** Each atom names: the category from the declared framework, the candidate causes within it, and which causes survived the five-whys descent.

4. **Sub-cause depth atoms — five-whys descent.** Each chain reaches at least sub-cause depth 2 on at least one branch. Premature-stop is the named failure mode; chains that accept intermediate causes as root because they are satisfying or actionable get reshaped by asking one more "why".

5. **Root-cause atoms.** Each atom names a root cause (whose removal prevents recurrence), distinguished from contributing factors (which amplify probability). Restatement-as-cause is the named failure mode; causes that paraphrase the effect (`deployments fail` → cause `deployments are unreliable`) get reshaped one level deeper.

6. **Contributing-factor atoms.** Each atom names a factor that amplifies probability but whose removal would not by itself prevent recurrence.

7. **Process-not-people atoms.** Where a leaf cause names human error, an explicit sub-cause atom names the process, policy, or incentive structure that permitted or incentivised the behaviour. Human-error-terminal is the named failure mode; leaves terminating at human error without a process sub-cause get reshaped — this is load-bearing, not optional.

8. **Per-link evidence atoms with correlation-vs-causation flag.** Each causal link carries an evidence basis (`mechanism`, `correlation`, `inference`) and an explicit correlation-vs-causation note on at least one link. Correlation-causation-conflation is the named failure mode; causal links asserted from co-occurrence without mechanism get reshaped.

9. **Alternative-chain atoms — when applicable.** Where breadth surfaced a second causal chain converging on the same symptom, both survive. Linear-chain-isolation is the named failure mode; single-chain analyses without considering convergent chains get reshaped.

10. **Recommendation atoms — corrective vs. preventive.** Each atom is tagged: `corrective` (addresses the surfaced failure) or `preventive` (addresses the root condition that produced it).

11. **Confidence atom.** Confidence in the dominant causal chain (`low` / `moderate` / `high`) with reasoning explicit.

**Mode-specific bloat patterns to cut:**

- **Premature stop** — chain ends at intermediate cause that has deeper structure.
- **Human-error terminal** — leaf names a person's mistake without naming the process that permitted it.
- **Correlation-causation conflation** — causal links asserted without mechanism.
- **Framework incoherence** — non-canonical category names; categories mixed across frameworks.
- **Restatement-as-cause** — cause that paraphrases the effect.
- **Linear-chain isolation** — single chain without considering convergent alternatives.
- **Solution-phrased problem** — problem stated as desired target state instead of observed failure.
- **Tidy-chain bias** — alternative chains and contributing factors smoothed away for narrative cleanliness.

**What NOT to collapse:**

- **Alternative chains** — when streams identified different causal paths to the same symptom, both survive; the convergence is itself a finding.
- **Stream disagreement about root vs. contributing** — when one stream treated X as root and another as contributing, the disagreement reveals what's contested about preventability.
- **Multiple sub-causes beneath the same human-error leaf** — process, policy, incentive layers can all contribute; the corpus preserves all that survived.
- **Stream disagreement about framework choice** — when streams chose different Ishikawa frameworks for the same failure, both readings survive with their domain-fit reasoning.

## VERIFICATION CRITERIA

Verified means: presented problem is phrased as a failure, not as a target state; the declared framework's canonical category names are used throughout; at least one branch reaches sub-cause depth 2; no chain terminates at human error without a process sub-cause; correlation-versus-causation is addressed on at least one link in the evidence assessment; at least one alternative causal framing was considered. Confidence in the dominant chain is stated explicitly (low / moderate / high) with reasoning.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **fishbone-structured root-cause analysis** — a backward-traced diagnosis that declares its Ishikawa framework, populates canonical categories, descends through five-whys to genuine root causes (process-not-people), and distinguishes corrective from preventive recommendations. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Presented problem.** One paragraph stating the observed failure as a failure (not as a target state). Phrasings like `we need X to work better` get reshaped to `X currently exhibits failure mode Y`.

2. **Chosen framework and rationale.** One labelled block. `**Framework:** [6M — Manufacturing / 4P — Marketing / 4S — Service / 8P — Project / other declared]. **Rationale:** [why this framework fits the failure domain].`

3. **Category analysis.** Per category in the declared framework, one labelled sub-block listing candidate causes, with five-whys descent on the survivors. Canonical category names from the declared framework appear verbatim.

4. **Root causes.** Bulleted list of root causes, each: `**[Root cause]** — category: [...]. Depth reached: [2 / 3 / 4 levels beneath symptom]. Why this is root: [removal would prevent recurrence]. Process / policy / incentive sub-cause (if human-error leaf): [...].`

5. **Evidence assessment.** A table or per-link list. Each row: `**[Cause A → Effect B]** — evidence: [mechanism / correlation / inference]. Correlation-vs-causation: [evidenced as causal because: ... / correlational only].` At least one link carries an explicit correlation-vs-causation note.

6. **Recommendations.** Two labelled sub-blocks:
   - `**Corrective recommendations:** [actions addressing the surfaced failure].`
   - `**Preventive recommendations:** [actions addressing the root condition that produced the failure].`

7. **Confidence and alternative framings.** One labelled block. `**Confidence in dominant chain:** [low / moderate / high]. **Reasoning:** [...]. **Alternative causal framing considered:** [...]. **Why dominant chain was preferred:** [...].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- Ishikawa-framework category names appear verbatim from the declared framework (6M canonicals: Manpower / Method / Machine / Material / Measurement / Mother Nature; 4P canonicals; 4S canonicals; 8P canonicals). Renamed or mixed categories are reshaped at this layer.
- Five-whys descent depth is *visible* — each root cause notes how many "why" levels beneath the symptom it sits.
- Process-not-people discipline is *visible* — human-error leaves carry an explicit process / policy / incentive sub-cause beneath them. Without it, the leaf gets reshaped.
- Corrective vs. preventive distinction (section 6) appears as two labelled sub-blocks; mixing them into one undifferentiated list is reshaped.
- When linear-chain-isolation was flagged in the corpus (single chain when convergent chains were plausible), section 7 closes with: `**Convergence flag:** alternative chain [described] also produces the surfaced symptom. If the dominant chain's fix proves insufficient, the convergent chain is the next investigation.`
- When framework-disagreement survived, section 2 carries: `**Framework alternatives considered:** stream A chose [framework X] for [reason]; stream B chose [framework Y] for [reason]. The deliverable uses [chosen] because [...].`

## CAVEATS AND OPEN DEBATES

Root Cause Analysis applies most cleanly to problems with bounded causal histories — failures in well-instrumented systems where evidence is recoverable. For systems exhibiting feedback dynamics where corrective interventions keep being counteracted, the mode should escalate to `systems-dynamics-causal`; the boundary is that Root Cause Analysis traces a chain backward whereas systems-dynamics-causal investigates how feedback structures generate recurring symptoms. Where the historical record is the load-bearing evidence (a specific past event), `process-tracing` may be the better tool. Where the formal causal-inference question is which conditional independencies are implied by the structure, `causal-dag` applies.

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

**Prioritize:** `precedes`, `enables`, `requires`, `produces`, `derived-from`
**Deprioritize:** `analogous-to`, `parent`

*Family: causal. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
