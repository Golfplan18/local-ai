---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-24

---

# MODE: Paradigm Suspension

```yaml
# 0. IDENTITY
mode_id: paradigm-suspension
canonical_name: Paradigm Suspension
suffix_rule: analysis
educational_name: paradigm suspension and assumption surfacing

# 1. TERRITORY AND POSITION
territory: T9-paradigm-and-assumption-examination
gradation_position:
  axis: stance
  value: suspending
adjacent_modes_in_territory:
  - mode_id: frame-comparison
    relationship: stance counterpart (comparing rather than suspending)
  - mode_id: worldview-cartography
    relationship: depth-molecular sibling (deeper synthesis across paradigms)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "what if X is wrong"
    - "evidence contradicts the accepted explanation"
    - "I want to question the standard view"
    - "why does this consensus exist"
  prompt_shape_signals:
    - "suspend the paradigm"
    - "question the frame"
    - "what if the consensus is wrong"
    - "heterodox exploration"
disambiguation_routing:
  routes_to_this_mode_when:
    - "challenge the foundational assumptions a single consensus depends on"
    - "evaluate evidence without the interpretive overlay of the dominant frame"
  routes_away_when:
    - "compare two or more paradigms side by side" → frame-comparison
    - "build a synthesis across worldviews" → worldview-cartography
    - "challenge a single argument's coherence within its own frame" → coherence-audit (T1)
    - "trace institutional interests behind the position" → cui-bono (T2)
when_not_to_invoke:
  - "User accepts the consensus and wants to work within it" → Project Mode or Constraint Mapping
  - "Question targets a specific claim's truth, not the framework that gives it sense" → Deep Clarification
  - "User wants to push back against observation rather than against authority — Einstein guard rail violation"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: suspending

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [paradigm_or_consensus_position, contesting_evidence_or_alternative]
    optional: [historical_paradigm_revision_analogue, foundational_papers_of_consensus]
    notes: "Applies when user explicitly names the paradigm and supplies the contesting evidence or alternative."
  accessible_mode:
    required: [situation_or_claim_under_question]
    optional: [hint_at_user_unease_or_anomaly]
    notes: "Default. Mode infers the load-bearing consensus and surfaces alternatives."
  detection:
    expert_signals: ["Lakatosian", "Kuhnian", "hard core", "protective belt", "paradigm shift", "anomaly"]
    accessible_signals: ["what if X is wrong", "the standard view", "this can't be the whole story"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the consensus position or accepted explanation you want to question?'"
    on_underspecified: "Ask: 'Are you challenging the evidence behind a position, or the interests pushing it? If interests, route to Cui Bono.'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have foundational assumptions been stated as testable propositions, or are they smuggled in as conclusions?"
    failure_mode_if_unmet: assumption-as-conclusion
  - cq_id: CQ2
    question: "Is observational evidence cleanly separated from interpretive evidence, with the same standard applied to consensus and alternatives?"
    failure_mode_if_unmet: asymmetric-evidence-standard
  - cq_id: CQ3
    question: "Is the Einstein guard rail honoured — push back against authority, never against observation?"
    failure_mode_if_unmet: einstein-guard-rail-violation
  - cq_id: CQ4
    question: "Are alternatives genuinely distinct from the consensus and grounded in observational evidence, not strawmen?"
    failure_mode_if_unmet: false-equivalence

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: contrarianism-trap
    detection_signal: "Mode concludes the consensus is wrong without evidential grounding for the rejection."
    correction_protocol: flag
  - name: false-equivalence
    detection_signal: "Fringe alternative treated as equally supported by the same kind of evidence the consensus rests on."
    correction_protocol: flag
  - name: interpretive-evidence-trap
    detection_signal: "Alternative's evidence accepted uncritically while consensus evidence is held to a higher standard (or vice versa)."
    correction_protocol: re-dispatch (apply observational/interpretive distinction symmetrically)
  - name: einstein-guard-rail-violation
    detection_signal: "An observation is dismissed in order to favour a preferred alternative."
    correction_protocol: flag
  - name: assumption-as-conclusion
    detection_signal: "A foundational assumption is stated in conclusion form ('therefore X') rather than testable form ('it is claimed that X')."
    correction_protocol: re-dispatch (rewrite as testable proposition)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - lakatos-hard-core-protective-belt
  optional:
    - kuhn-anomaly-and-paradigm-revision
    - hermeneutic-circle
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: worldview-cartography
    when: "Suspension reveals multiple paradigms in genuine tension that warrant integrative synthesis."
  sideways:
    target_mode_id: frame-comparison
    when: "Suspension surfaces two or more paradigms; user wants comparative reading rather than single-frame suspension."
  downward:
    target_mode_id: null
    when: "Paradigm Suspension is the lightest stance position in T9."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Paradigm Suspension is the degree to which foundational assumptions are surfaced as testable propositions and traced through the framework's logical scaffolding. A thin pass names assumptions; a substantive pass identifies which assumptions are load-bearing (the framework collapses if suspended) versus peripheral (the framework adapts), and tests each assumption against observational rather than interpretive evidence. Test depth by asking: would the analysis predict which observations would falsify each load-bearing assumption?

## BREADTH ANALYSIS GUIDANCE

Breadth in Paradigm Suspension is the catalog of alternative interpretations consistent with the same observational evidence. Widen the lens by generating ≥2 alternatives per load-bearing assumption, looking for structural similarities to historical paradigm revisions (Copernican, plate tectonics, prion theory), and surveying what the domain looks like under each alternative. Breadth markers: alternatives are genuinely distinct (not paraphrases of consensus), each grounded in observation, with at least one historical analogue noted.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Paradigm Suspension is the suspending-stance reading of a consensus position — surfacing the foundational assumptions a single dominant framework depends on, restating them as testable propositions, auditing evidence symmetrically across consensus and alternatives, and landing an honest verdict (supported / weakened / indeterminate on current evidence) without collapsing into contrarianism. The mode is read in Lakatosian research-programme vocabulary (hard core / protective belt; progressive vs degenerating programmes) with Kuhnian anomaly-and-revision as the historical-pattern layer. It is distinct from frame-comparison (comparing two paradigms side by side rather than suspending one), worldview-cartography (deeper integrative synthesis across paradigms), and cui-bono (tracing institutional interests rather than challenging foundational assumptions). The Einstein guard rail — push back against authority, never against observation — is the methodology's load-bearing commitment and is what separates suspension from contrarianism.

**Procedure.**

1. Identify the consensus position and surface its foundational assumptions — restate each as a testable proposition ("it is claimed that X"), never as a conclusion ("therefore X"); at least three.
2. Classify each assumption as load-bearing (Lakatos hard core — framework collapses if suspended) or peripheral (protective belt — framework adapts).
3. Audit the evidence — tag every item as `[observational]` (direct measurement, replicable observation, raw datum) or `[interpretive]` (theory-laden reading, model-mediated inference); apply tagging symmetrically across consensus and alternative.
4. Generate at least two genuinely distinct alternative interpretations of the same observational evidence base — each grounded in observation, each with predictive content the consensus would not produce.
5. Hold the Einstein guard rail through every move — no observation dismissed in order to favour a preferred alternative; observations that bear against alternatives are engaged with the same seriousness as observations that bear against consensus.
6. Where the suspension pattern resembles a historical paradigm revision (Copernican, plate tectonics, prion theory, ulcer-as-bacterial), name the analogue with the specific structural parallel — what assumption was load-bearing, what observation forced revision.
7. Land the verdict honestly — `supported by observation`, `weakened by observation`, or `indeterminate on current evidence`. Indeterminacy is a first-class outcome.
8. Calibrate confidence per finding — Einstein-guard-rail preservation is itself a corpus-level confidence factor.

**Goal.** Produce a paradigm-suspension audit that surfaces foundational assumptions as testable propositions, audits evidence symmetrically across consensus and alternatives, identifies which assumptions are load-bearing, and lands an honest evaluation — preserving indeterminacy where the evidence does not warrant a verdict.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — assumption form.** Have foundational assumptions been stated as testable propositions, or are they smuggled in as conclusions? Failure mode if unmet: `assumption-as-conclusion`.
- **CQ2 — symmetric evidence standards (load-bearing).** Is observational evidence cleanly separated from interpretive evidence, with the same standard applied to consensus and alternatives? Asymmetric standards are how contrarianism smuggles itself past the evidence check. Failure mode if unmet: `asymmetric-evidence-standard` / `interpretive-evidence-trap`.
- **CQ3 — Einstein guard rail (highest-stakes, load-bearing).** Is the Einstein guard rail honoured — push back against authority, never against observation? Failure mode if unmet: `einstein-guard-rail-violation`.
- **CQ4 — alternative quality.** Are alternatives genuinely distinct from the consensus and grounded in observational evidence, not strawmen or fringe positions framed as evidentially equivalent? Failure mode if unmet: `false-equivalence`.

A passing output states ≥3 foundational assumptions as testable propositions, tags every evidence item observational or interpretive with symmetric application across consensus and alternative, assigns load-bearing vs peripheral classification to each assumption, surfaces ≥2 genuinely distinct alternatives with observational grounding and predictive content, holds the Einstein guard rail throughout, names a historical analogue with structural parallel where applicable, and lands the verdict honestly — including "indeterminate on current evidence" as a first-class outcome when warranted.

**Named failure modes.**

- *contrarianism-trap* — mode concludes the consensus is wrong without evidential grounding for the rejection.
- *false-equivalence* — fringe alternative treated as equally supported by the same kind of evidence the consensus rests on.
- *interpretive-evidence-trap* — alternative's evidence accepted uncritically while consensus evidence is held to a higher standard, or vice versa.
- *einstein-guard-rail-violation* — an observation is dismissed in order to favour a preferred alternative.
- *assumption-as-conclusion* — foundational assumption stated in conclusion form ("therefore X") rather than testable form ("it is claimed that X").
- *asymmetric-evidence-standard* — consensus held to one bar, alternative to another, for the same evidential role.

## REVISION GUIDANCE

Revise to convert assumptions stated as conclusions into testable propositions. Revise to add load-bearing assessment where missing. Revise to apply observational/interpretive labelling symmetrically. Resist revising toward neutrality if the analysis surfaces a genuinely weakened paradigm — the mode is suspending, not endorsing. Resist revising toward contrarian conclusions if observation supports the consensus — observation wins. Never collapse the suspension into a verdict the evidence does not warrant.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Lakatosian suspension audit: foundational assumptions stated as testable propositions, evidence atoms tagged observational vs. interpretive, load-bearing-vs-peripheral assessments, alternative-interpretation atoms grounded in observational evidence, and the Einstein guard rail honoured throughout**. The atoms are:

1. **Foundational-assumption atoms.** Each atom states one assumption underlying the consensus position, phrased as a *testable proposition* (`it is claimed that X`) rather than as a conclusion (`therefore X`). Assumption-as-conclusion is the named failure mode the consolidator watches for; assumptions stated in conclusion-form get reshaped.

2. **Evidence-audit atoms — per evidence item.** Each atom carries: the evidence item, the source, and an explicit tag — `[observational]` (direct measurement, replicable observation, raw datum) vs. `[interpretive]` (theory-laden reading, model-mediated inference). Interpretive-evidence-trap is the named failure mode; evidence used asymmetrically (consensus held to one standard, alternative to another) gets reshaped to symmetric tagging.

3. **Load-bearing assessment atoms.** For each foundational-assumption atom, an explicit assessment: `load-bearing` (the framework collapses if this assumption is suspended) or `peripheral` (the framework adapts). At least three assumptions carry this assessment.

4. **Alternative-interpretation atoms.** Each atom names one alternative interpretation of the same observational evidence base, with the alternative's grounding in observation (not interpretive overlay). False-equivalence is the named failure mode; fringe alternatives treated as equally supported by the same kind of evidence the consensus rests on get reshaped. At least two genuinely distinct alternatives appear.

5. **Einstein-guard-rail atom.** A standing commitment in the corpus: push back against authority, never against observation. Einstein-guard-rail-violation is the named failure mode; any atom where an observation is dismissed in order to favour a preferred alternative gets reshaped or the entire alternative gets de-weighted.

6. **Historical-analogue atoms — when applicable.** Where the suspension pattern resembles a historical paradigm revision (Copernican, plate tectonics, prion theory, ulcer-as-bacterial, etc.), the analogue is named with the specific structural parallel — what assumption was load-bearing, what observation forced revision, how long the revision took.

7. **Evaluation atom.** The honest reading: is the paradigm `supported by observation`, `weakened by observation`, or `indeterminate on current evidence`. Contrarianism-trap is the named failure mode; concluding the consensus is wrong without evidential grounding gets reshaped.

8. **Asymmetric-standard flag — when applicable.** When streams applied evidence standards asymmetrically across consensus and alternative, the flag is preserved.

9. **Confidence per finding.** Each major claim carries a confidence with explicit basis.

**Mode-specific bloat patterns to cut:**

- **Assumption-as-conclusion** — foundational assumptions stated as `therefore X` rather than `it is claimed that X`.
- **Untagged evidence** — items presented as evidence without the observational/interpretive label, hiding the distinction the mode depends on.
- **Asymmetric evidence standard** — consensus held to one bar, alternative to another. The corpus standard is symmetric application.
- **Strawman alternatives** — alternatives weaker than the consensus presents itself, set up to be dismissed.
- **Einstein-guard-rail violation** — observation dismissed to favour a preferred alternative.
- **Contrarianism** — rejection of consensus without evidential grounding.
- **False equivalence** — fringe positions framed as if they shared the consensus's evidential standing.
- **Verdict-collapse** — the suspension prematurely closed into a verdict the evidence does not warrant.

**What NOT to collapse:**

- **Indeterminate verdicts** — when the evidence honestly does not warrant supporting or rejecting the consensus, the indeterminacy is the finding and survives.
- **Multiple genuinely distinct alternatives** — when streams produced more than one alternative interpretation grounded in observation, all survive; the corpus does not pick a single rival.
- **Observation-vs-authority disagreements** — when streams diverged on whether an item is observational or interpretive, the disagreement is itself a finding about what the field treats as bedrock.
- **Stream disagreement about load-bearing status** — when one stream classified an assumption as load-bearing and another as peripheral, both readings survive with their respective collapse-scenarios.

## VERIFICATION CRITERIA

Verified means: ≥3 foundational assumptions stated as testable propositions (not conclusions); every evidence item carries an observational/interpretive tag; load-bearing assessment present for ≥3 assumptions; ≥2 genuinely distinct alternatives with observational grounding; Einstein guard rail honoured throughout (no observation dismissed to favour an alternative); evaluation states honestly whether the paradigm is supported, weakened, or indeterminate. The four critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **paradigm suspension audit** — a prose analysis that surfaces foundational assumptions as testable propositions, audits evidence symmetrically across consensus and alternatives, identifies which assumptions are load-bearing, and lands an honest evaluation (supported / weakened / indeterminate). Place the consolidated-corpus atoms into the following sections, in this order:

1. **Foundational assumptions.** A numbered list. Each: `**Assumption N (testable):** [statement in the form "It is claimed that X" — never "Therefore X"].` Three or more assumptions appear; assumptions stated as conclusions are reshaped at this layer.

2. **Evidence audit — observational vs. interpretive.** A table or two-column block. Each evidence item: `**[Item]** — source: [...]. Tag: [observational / interpretive]. Bears on assumption(s): [N1, N2 ...].` Every item carries a tag; symmetric application across consensus and alternative.

3. **Load-bearing assessment.** Per assumption from section 1: `**Assumption N:** [load-bearing — framework collapses if suspended / peripheral — framework adapts]. Reasoning: [why this assumption holds the role it does in the framework].`

4. **Alternative interpretations.** Per alternative, one labelled sub-block: `**Alternative N:** [interpretation in plain terms]. Observational grounding: [...]. How it differs structurally from the consensus: [...]. What it would predict that the consensus would not: [...].` Two or more genuinely distinct alternatives appear; strawman alternatives are reshaped at this layer.

5. **Evaluation.** One paragraph stating honestly: `The paradigm is [supported / weakened / indeterminate] on current evidence because [reasoning]. The Einstein guard rail held throughout: no observation was dismissed to favour a preferred alternative.` When historical analogues apply, a labelled `**Historical analogue:** [Copernican / plate-tectonics / prion / ulcer-as-bacterial / other] — the structural parallel here is [...].` line surfaces them.

**Per-section conventions:**

- Use H2 headings for sections 1 through 5.
- Format is **prose only — no diagram**. A diagram would freeze the paradigm's structure, contradicting the mode's commitment to holding interpretive frames provisional. If visualisation is essential to the user's downstream work, the deliverable surfaces a sideways-route note (`**If a bilateral map across two paradigms is wanted, frame-comparison is the appropriate alternative; if integrative synthesis is wanted, worldview-cartography is the upward route.**`) rather than producing one in-mode.
- Literal label prefixes appear verbatim: `**Assumption N (testable):**`, `[observational]` / `[interpretive]`, `**load-bearing:**` / `**peripheral:**`, `**Alternative N:**`. These are operative axis markers, not decoration.
- Evidence tagging (section 2) is symmetric. If consensus evidence is tagged interpretive while alternative evidence is tagged observational without reasoning, the asymmetry is reshaped or flagged.
- When the indeterminate verdict survived consolidation, section 5 carries it explicitly — "indeterminate on current evidence" is a first-class outcome, never collapsed into a forced verdict.
- When streams diverged on observational/interpretive tagging or on load-bearing status, the disagreement surfaces inside the relevant section as `**Contested tagging:** [item] — stream A: observational; stream B: interpretive. [What this reveals about field's bedrock commitments].`


---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~10min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `contradicts`, `qualifies`, `analogous-to`, `extends`, `supersedes`
**Deprioritize:** `precedes`, `produces`

*Family: frame-paradigm. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
