---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Process Tracing

```yaml
# 0. IDENTITY
mode_id: process-tracing
canonical_name: Process Tracing
suffix_rule: analysis
educational_name: process tracing (Bennett-Checkel hoop / smoking-gun / doubly-decisive tests)

# 1. TERRITORY AND POSITION
territory: T4-causal-investigation
gradation_position:
  axis: specificity
  value: historical-event
  secondary_axis: depth
  secondary_value: thorough
adjacent_modes_in_territory:
  - mode_id: root-cause-analysis
    relationship: complexity-lighter sibling (single cause-chain, no evidence-test framework)
  - mode_id: systems-dynamics-causal
    relationship: complexity-counterpart (feedback structure rather than historical-event)
  - mode_id: causal-dag
    relationship: specificity-counterpart (general formal causal-graph rather than historical-event-specific)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want to know what actually caused this specific historical event"
    - "I need to test competing causal explanations of a single case"
    - "I have evidence and want to know which causal story it actually supports"
    - "I want to assess the strength of causal evidence rigorously"
  prompt_shape_signals:
    - "process tracing"
    - "Bennett Checkel"
    - "smoking gun"
    - "hoop test"
    - "doubly decisive"
    - "straw in the wind"
    - "what really happened"
    - "trace the causal chain"
    - "case study causal inference"
disambiguation_routing:
  routes_to_this_mode_when:
    - "specific historical event or single case where evidence is available"
    - "user wants to evaluate competing causal hypotheses against observable evidence"
    - "user wants explicit evidence-test framework (necessary, sufficient, both, neither)"
    - "user wants causal certainty calibrated to the diagnostic strength of available evidence"
  routes_away_when:
    - "general causal structure, not tied to a specific historical event" → causal-dag
    - "system has ongoing feedback dynamics" → systems-dynamics-causal
    - "single cause-chain with no need for evidence-test calibration" → root-cause-analysis
    - "evaluating multiple hypotheses with formal Bayesian diagnosticity matrix" → competing-hypotheses (T5)
when_not_to_invoke:
  - "User wants to map how a process currently works" → T17
  - "User wants to forecast a future event" → T6 modes
  - "Question is about an argument's soundness, not a historical cause" → T1

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [historical_event_or_case, candidate_causal_hypotheses, evidence_inventory]
    optional: [hypothesis_priors, evidence_provenance_notes, prior_process-tracing_analyses]
    notes: "Applies when user supplies a structured case, named competing hypotheses, and an explicit evidence inventory."
  accessible_mode:
    required: [event_or_case_description]
    optional: [what_user_thinks_caused_it, available_evidence_sources]
    notes: "Default. Mode elicits competing hypotheses and evidence inventory during execution."
  detection:
    expert_signals: ["process tracing", "hoop test", "smoking gun", "doubly decisive", "straw in the wind", "Bennett", "Checkel"]
    accessible_signals: ["what really caused", "trace what happened", "what evidence supports", "case causal inference"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What event or case are you trying to explain, and what are the competing causal stories you want to test?'"
    on_underspecified: "Ask: 'What evidence do you have access to (documents, testimony, records, observations) that could discriminate between the hypotheses?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have at least two genuinely competing causal hypotheses been named, or has the analysis privileged one explanation by failing to construct alternatives?"
    failure_mode_if_unmet: hypothesis-monoculture
  - cq_id: CQ2
    question: "Has each piece of evidence been classified by test type (hoop / smoking-gun / doubly-decisive / straw-in-the-wind), with the classification justified rather than asserted?"
    failure_mode_if_unmet: test-misclassification
  - cq_id: CQ3
    question: "Has the analysis updated each hypothesis's status appropriately given the test outcomes (failed-hoop eliminates, passed-smoking-gun strongly confirms, etc.), or has it overweighted weak evidence?"
    failure_mode_if_unmet: evidence-overreach
  - cq_id: CQ4
    question: "Has the provenance and reliability of each evidence piece been assessed, or has the analysis treated all sources as equally credible?"
    failure_mode_if_unmet: source-naivety
  - cq_id: CQ5
    question: "Has the causal chain been reconstructed in temporal sequence with explicit links, or have intermediate steps been elided?"
    failure_mode_if_unmet: chain-elision

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: hypothesis-monoculture
    detection_signal: "Only one causal hypothesis tested; no genuinely competing alternative considered."
    correction_protocol: re-dispatch
  - name: test-misclassification
    detection_signal: "Evidence treated as smoking-gun (sufficient) when its absence would not eliminate the hypothesis (only hoop), or vice versa."
    correction_protocol: re-dispatch
  - name: evidence-overreach
    detection_signal: "Hypothesis declared confirmed on straw-in-the-wind evidence, or eliminated on weak negative evidence."
    correction_protocol: flag
  - name: source-naivety
    detection_signal: "All evidence pieces treated as equally credible; no provenance assessment."
    correction_protocol: flag
  - name: chain-elision
    detection_signal: "Causal chain skips intermediate steps without justification (e.g., 'X led to Z' with Y unexplained)."
    correction_protocol: re-dispatch
  - name: presentism
    detection_signal: "Hypotheses constructed from present knowledge that actors at the time could not have held; counterfactual reasoning anachronistic."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - bennett-checkel-process-tracing-tests
    - pearl-causal-graphs
  optional:
    - pearl-do-calculus (when intervention or counterfactual reasoning is central)
    - tetlock-superforecasting (when evidence is partly forward-looking and probability matters)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Process Tracing is the heaviest specificity-historical mode in T4 at thorough tier; molecular escalation deferred."
  sideways:
    target_mode_id: causal-dag
    when: "Question generalizes beyond the specific historical event into structural causal reasoning."
  downward:
    target_mode_id: root-cause-analysis
    when: "Evidence is sparse or single-cause-chain suffices without formal test framework."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Process Tracing is the explicitness of (a) competing causal hypotheses constructed before evidence is considered, (b) per-evidence-piece test classification (hoop / smoking-gun / doubly-decisive / straw-in-the-wind), and (c) update of hypothesis status given test outcomes. A thin pass narrates what happened; a substantive pass names competing hypotheses, classifies each evidence piece by what its presence-or-absence would do to each hypothesis, applies the tests, updates hypothesis status, and reconstructs the causal chain in temporal sequence with explicit links. Test depth by asking: could a reader reproduce the verdict from the artifact, including which evidence pieces did the heavy lifting and which would have changed the conclusion if absent?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for additional plausible causal hypotheses (especially ones favored by different theoretical traditions or stakeholder perspectives), surfacing evidence the analyst lacks but could obtain, and noting which evidence-piece-not-yet-found would be doubly-decisive (eliminate one hypothesis and confirm another). Breadth markers: the analysis names at least three plausible hypotheses (even if only two are seriously tested), and identifies the most diagnostic evidence-piece that does not currently exist in the inventory.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Process Tracing is Bennett-Checkel-style historical causal inference: a single case is analyzed against ≥2 competing causal hypotheses using the four diagnostic-test framework (hoop, smoking-gun, doubly-decisive, straw-in-the-wind) to calibrate confidence to the diagnostic strength of available evidence. It is distinct from root-cause-analysis (which traces a single chain backward without a formal evidence-test framework), from causal-dag (which builds general formal structures rather than case-specific reconstruction), and from systems-dynamics-causal (which investigates feedback structure rather than historical event-causation).

**Procedure.**

1. Lock the case and the causal question — the specific historical event and what is being explained.
2. Construct at least two genuinely competing causal hypotheses before evidence is considered; flag presentism if hypotheses require knowledge actors at the time could not have held.
3. Inventory available evidence with provenance assessment (primary / secondary / tertiary; contemporaneous / retrospective; partisan / disinterested; documentary / testimonial; reliability tier).
4. Classify each evidence piece by test type — hoop (necessary not sufficient), smoking-gun (sufficient not necessary), doubly-decisive (both), straw-in-the-wind (neither) — with justification for the classification.
5. Apply tests to each hypothesis and update status (eliminated on failed-hoop; weakly supported on passed-straw-in-the-wind; strongly supported on passed-smoking-gun; confirmed on passed-doubly-decisive).
6. Reconstruct the causal chain in temporal sequence with each link's mechanism explicit; no "X led to Z" with Y elided.
7. Name diagnostic evidence not yet available — the most consequential absent piece is the next investigation step.
8. Assign confidence per causal claim with grounding in test outcomes and provenance.

**Goal.** Produce a Bennett-Checkel process-tracing synthesis where competing causal hypotheses have been tested against classified evidence, hypothesis status is calibrated to test outcomes, and the causal chain is reconstructed in temporal sequence with explicit mechanisms.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — competing hypotheses.** Have at least two genuinely competing causal hypotheses been named, or has the analysis privileged one explanation by failing to construct alternatives? Failure mode if unmet: `hypothesis-monoculture`.
- **CQ2 — test classification.** Has each evidence piece been classified by test type (hoop / smoking-gun / doubly-decisive / straw-in-the-wind) with justification? Failure mode if unmet: `test-misclassification`.
- **CQ3 — appropriate updating.** Has hypothesis status been updated appropriately given test outcomes, or has weak evidence been overweighted? Failure mode if unmet: `evidence-overreach`.
- **CQ4 — provenance assessment.** Has the provenance and reliability of each evidence piece been assessed, or are all sources treated as equally credible? Failure mode if unmet: `source-naivety`.
- **CQ5 — causal chain reconstruction.** Has the causal chain been reconstructed in temporal sequence with explicit links, or have intermediate steps been elided? Failure mode if unmet: `chain-elision`.

A passing output names competing hypotheses, classifies each evidence piece by test type with justification, updates hypothesis status appropriately, assesses source provenance, and reconstructs the causal chain with explicit intermediate links.

**Named failure modes.**

- *hypothesis-monoculture* — only one causal hypothesis tested; no genuinely competing alternative considered.
- *test-misclassification* — evidence treated as smoking-gun (sufficient) when its absence would not eliminate the hypothesis (only hoop), or vice versa.
- *evidence-overreach* — hypothesis declared confirmed on straw-in-the-wind evidence, or eliminated on weak negative evidence.
- *source-naivety* — all evidence pieces treated as equally credible; no provenance assessment.
- *chain-elision* — causal chain skips intermediate steps without justification (e.g., "X led to Z" with Y unexplained).
- *presentism* — hypotheses constructed from present knowledge that actors at the time could not have held; counterfactual reasoning anachronistic.

## REVISION GUIDANCE

Revise to add competing hypotheses where the draft tests only one. Revise to reclassify test types where the draft asserts smoking-gun status without checking sufficiency, or hoop status without checking necessity. Revise to downgrade conclusions where evidence overreach has occurred. Revise to add provenance notes where sources were treated as equally credible. Resist revising toward narrative coherence at the expense of test discipline — the mode's analytical character is calibrated evidence-driven inference, not satisfying storytelling. If sources are weak, the conclusion must reflect that weakness rather than smoothing it over.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Bennett-Checkel process-tracing atom set: case-and-question lock, competing-hypothesis atoms (≥2), evidence atoms with provenance, per-evidence test-classification atoms (hoop / smoking-gun / doubly-decisive / straw-in-the-wind) with per-hypothesis implication, post-test hypothesis-status atoms, temporal causal-chain reconstruction with explicit links, and residual-uncertainty atoms naming diagnostic evidence not yet available**. The atoms are:

1. **Case-and-question lock atom.** The historical event or case under analysis and the specific causal question. One short paragraph; subsequent atoms reference this lock.

2. **Competing-hypothesis atoms.** Each atom names one candidate causal hypothesis — at least two genuinely competing. Hypothesis-monoculture is the named failure mode the consolidator watches for; analyses that test only one hypothesis get reshaped to surface at least one rival. Presentism is also flagged here: hypotheses constructed from present knowledge that actors at the time could not have held get reshaped.

3. **Evidence atoms with provenance.** Each atom carries: the evidence item, its source, and a provenance/reliability assessment (primary / secondary / tertiary; contemporaneous / retrospective; partisan / disinterested; documentary / testimonial). Source-naivety is the named failure mode; evidence treated as uniformly credible gets reshaped.

4. **Test-classification atoms — per evidence piece.** Each atom carries: the test type (`hoop` — necessary but not sufficient; `smoking-gun` — sufficient but not necessary; `doubly-decisive` — both necessary and sufficient; `straw-in-the-wind` — neither necessary nor sufficient), the justification for the classification, and the per-hypothesis implication (what the evidence's presence or absence does to each hypothesis). Test-misclassification is the named failure mode; smoking-gun status without sufficiency check, or hoop status without necessity check, gets reshaped.

5. **Hypothesis-status atoms — post-test.** Each hypothesis carries a verdict: `eliminated` (failed-hoop), `weakly supported` (passed-straw-in-the-wind), `strongly supported` (passed-smoking-gun), `confirmed` (passed-doubly-decisive). The test outcomes that drove the verdict are named explicitly. Evidence-overreach is the named failure mode; hypotheses declared confirmed on straw-in-the-wind evidence, or eliminated on weak negative evidence, get reshaped.

6. **Causal-chain atoms.** Each atom traces one link in the temporal sequence — `X happened at time T1, which produced effect E1 at time T2 via mechanism M, which produced effect E2 at time T3`. Chain-elision is the named failure mode; jumps from cause to effect with intermediate steps unexplained get reshaped to surface the missing links.

7. **Residual-uncertainty atoms.** Each atom names: an evidence piece not yet available, what it would test, and how it would change the verdict. The most diagnostic evidence-piece-not-yet-found (the doubly-decisive test that hasn't been run) surfaces explicitly.

8. **Confidence per finding.** Each causal claim carries confidence with explicit grounding in the test outcomes and evidence provenance.

**Mode-specific bloat patterns to cut:**

- **Hypothesis monoculture** — only one hypothesis tested; rival hypotheses elided.
- **Test misclassification** — smoking-gun asserted without sufficiency; hoop asserted without necessity.
- **Evidence overreach** — confirmation declared on weak evidence; elimination declared on incomplete negative evidence.
- **Source naivety** — provenance unassessed; partisan and disinterested sources treated alike.
- **Chain elision** — intermediate steps skipped; "X led to Z" without naming the Y in between.
- **Presentism** — hypotheses anachronistic to the actors' knowledge horizon.
- **Narrative coherence over test discipline** — smooth story preferred to honest weakness-acknowledgment.
- **Straw-in-the-wind smuggled as smoking-gun** — weak evidence framed as strong; verdicts not calibrated to test type.

**What NOT to collapse:**

- **Multiple surviving hypotheses** — when evidence does not discriminate cleanly, multiple hypotheses can survive at `weakly supported` or `strongly supported` status simultaneously. Forcing a single winner is over-reach.
- **Stream disagreement about test classification** — when streams diverged on whether a piece of evidence is hoop or smoking-gun, the disagreement is preserved as a per-evidence flag and resolved (or kept open) explicitly.
- **Provenance disagreements** — when streams assigned different reliability to the same source, the disagreement surfaces in the evidence-atom rather than being smoothed.
- **Counterfactual disagreements** — when streams reconstructed different causal chains because they implicitly assumed different counterfactual baselines, both reconstructions survive with their counterfactual premises named.

## VERIFICATION CRITERIA

Verified means: at least two competing hypotheses were tested; each evidence piece is classified by test type with justification; hypothesis status reflects appropriate Bayesian updating given test outcomes; source provenance is assessed; the causal chain is reconstructed in temporal sequence with explicit intermediate links; residual uncertainty names diagnostic evidence not yet available. The five critical questions are addressable from the output. Confidence per finding accompanies every causal claim.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **process-tracing synthesis** — a structured Bennett-Checkel analysis that tests competing causal hypotheses against evidence using the four-test framework, updates hypothesis status appropriately, and reconstructs the causal chain in temporal sequence. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Case and question locked.** One paragraph stating the historical event or case and the specific causal question. Brief context but not exposition; subsequent sections reference this lock.

2. **Competing hypotheses inventory.** Numbered list. Each: `**H[N]: [hypothesis label]** — causal claim: [...]. Mechanism asserted: [...]. Theoretical tradition or stakeholder vantage (if relevant): [...].` At least two genuinely competing hypotheses appear; analyses with only one are reshaped.

3. **Evidence inventory with provenance.** A table. Each row: `**[Evidence item]** — source: [...]. Type: [primary / secondary / tertiary; contemporaneous / retrospective; partisan / disinterested; documentary / testimonial]. Reliability: [high / medium / low — with reasoning].`

4. **Test classification per evidence piece.** A table. Each row: `**[Evidence item]** — test type: [hoop / smoking-gun / doubly-decisive / straw-in-the-wind]. Justification: [why this classification — what would presence and absence imply]. Per-hypothesis implication: H1: [...]; H2: [...]; H3: [...].` Test-type vocabulary appears verbatim.

5. **Hypothesis status after tests.** Per hypothesis: `**H[N]:** verdict: [eliminated / weakly supported / strongly supported / confirmed]. Driving test outcomes: [which evidence pieces, with which results, drove the verdict]. What would change this verdict: [...].`

6. **Causal chain reconstruction.** Numbered temporal sequence. Each step: `[N]. **[Event / state at time T]** → produced [effect at time T+]: via mechanism [...]. Evidence supporting this link: [reference to evidence inventory].` Chain-elision is reshaped here; missing intermediate steps are surfaced.

7. **Residual uncertainty.** Bulleted list. Each: `**[Evidence piece not yet available]** — what it would test: [...]. How verdict would change if available: [...]. Where to look: [...].` The most diagnostic absent evidence appears first.

8. **Confidence per finding.** Bulleted list of confidence assessments per major causal claim, with grounding in test outcomes and evidence provenance.

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- Bennett-Checkel vocabulary stays operative: the four test types (`hoop`, `smoking-gun`, `doubly-decisive`, `straw-in-the-wind`) appear verbatim with their distinguishing meanings — necessary/sufficient/both/neither — preserved.
- Test classifications (section 4) include the *justification* — what would presence and absence imply. Bare classifications without justification get reshaped to flagged classifications.
- Hypothesis verdicts (section 5) calibrate to test outcome: passed-doubly-decisive → confirmed; passed-smoking-gun → strongly supported; passed-straw-in-the-wind → weakly supported; failed-hoop → eliminated. Verdicts that overshoot the test result get reshaped.
- When multiple hypotheses survive at comparable status (evidence does not discriminate), the deliverable carries an explicit note in section 5: `**Note: evidence does not discriminate cleanly between H[X] and H[Y]; both retain [status]. Resolution requires the diagnostic evidence named in section 7.**`
- When the presentism flag survived consolidation, section 2 closes with: `**Anachronism check:** the hypotheses below are constructed from knowledge available to actors at the time. If hypothesis H[X] requires present-day knowledge the actors lacked, it is flagged here and not tested against contemporaneous evidence.`
- When provenance disagreements survived, section 3 carries explicit flags inline: `**Contested reliability:** [source] — assessed differently across streams: [...] vs [...].`
- Causal chain (section 6) is temporal and link-explicit. Jumps from cause to effect without naming the intermediate step are reshaped at this layer.


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
