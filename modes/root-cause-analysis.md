---
nexus:
  - ora
type: mode
tags:
  - framework/instruction
  - architecture
date created: 2026-03-23
date modified: 2026-05-01
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
output_contract:
  artifact_type: mapping
  required_sections:
    - presented_problem
    - chosen_framework_and_rationale
    - category_analysis
    - root_causes
    - evidence_assessment
    - recommendations
    - confidence_and_alternative_framings
  format: structured

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

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) genuine root vs premature stop; (CQ2) process-not-people terminal; (CQ3) evidence per link with correlation-causation distinguished; (CQ4) framework coherence with canonical category names. The named failure modes are the evaluation checklist. A passing Root Cause Analysis output declares its framework before naming categories, reaches sub-cause depth 2 on at least one branch, terminates no chain at human error without a process sub-cause, supports each causal link with evidence, and distinguishes root causes from contributing factors with explicit reasoning.

## REVISION GUIDANCE

Revise to deepen any branch that stops at an intermediate cause when one more "why" would yield non-trivial structure. Revise to add the process or incentive sub-cause beneath any human-error leaf — this is load-bearing, not optional. Revise to align category names with the declared framework's canonical set. Resist revising toward a single tidy causal chain when the analysis surfaced contributing factors or alternative chains — the residual complexity is a feature, not noise.

## CONSOLIDATION GUIDANCE

Consolidate as a structured mapping with the seven required sections in order: presented problem (phrased as observed failure, not as solution); chosen framework and rationale; category analysis (one paragraph per category); root cause(s) (explicitly distinguished from contributing factors); evidence assessment (with correlation-causation called out on at least one link); recommendations (corrective and preventive distinguished); confidence and alternative framings (with at least one alternative considered and deprioritised). Format: structured. Each leaf cause is auditable to a category, an evidence claim, and an actionability assessment.

## VERIFICATION CRITERIA

Verified means: presented problem is phrased as a failure, not as a target state; the declared framework's canonical category names are used throughout; at least one branch reaches sub-cause depth 2; no chain terminates at human error without a process sub-cause; correlation-versus-causation is addressed on at least one link in the evidence assessment; at least one alternative causal framing was considered. Confidence in the dominant chain is stated explicitly (low / moderate / high) with reasoning.

## CAVEATS AND OPEN DEBATES

Root Cause Analysis applies most cleanly to problems with bounded causal histories — failures in well-instrumented systems where evidence is recoverable. For systems exhibiting feedback dynamics where corrective interventions keep being counteracted, the mode should escalate to `systems-dynamics-causal`; the boundary is that Root Cause Analysis traces a chain backward whereas systems-dynamics-causal investigates how feedback structures generate recurring symptoms. Where the historical record is the load-bearing evidence (a specific past event), `process-tracing` may be the better tool. Where the formal causal-inference question is which conditional independencies are implied by the structure, `causal-dag` applies.
