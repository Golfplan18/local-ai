
# Bayesian Hypothesis Network Analysis Framework

*A Framework for Producing a Probabilistic Posterior over Competing Hypotheses with Explicit Priors, Evidential Likelihoods, Conditional Dependencies, and Sensitivity Analysis Identifying Which Evidence Items Most Shift the Posterior.*

*Version 1.0*

*Bridge Strip: `[BHN — Bayesian Hypothesis Network]`*

---

## Architectural Note

This framework supports the `bayesian-hypothesis-network` mode, the depth-molecular operation in T5 (hypothesis evaluation). The mode file at `Modes/bayesian-hypothesis-network.md` carries the locked spec — molecular_spec.components, critical_questions, output_contract.required_sections — sufficient for the orchestrator to dispatch the two component operations (`differential-diagnosis` as fragment, `competing-hypotheses` as full ACH) and the three synthesis stages (prior-elicitation, Bayesian-network-construction, posterior-update). This framework adds the procedural detail the spec does not carry: the elicitation prompts the orchestrator uses, the intermediate output formats, the per-stage quality gates, and the worked example showing the framework operating end-to-end.

The framework sits in T5's depth ladder above `differential-diagnosis` (T5-light, atomic, medical-tradition triage) and `competing-hypotheses` (T5-thorough, atomic, full Heuer ACH). It composes those siblings into a Bayesian network with explicit priors, likelihood structure, and conditional dependencies. The territory framework is `Framework — Hypothesis Evaluation.md`. BHN is the heaviest analytical mode in T5; it produces a probabilistic posterior with sensitivity analysis, not a flat ranking.

---

## How to Use This File

This framework runs when the user wants a probabilistic read on competing explanations — not just a ranked list, not just a matrix of consistency assessments. The framework's value is in the synthesis stages: priors elicited from base rates rather than fabricated, conditional dependencies between hypotheses surfaced explicitly (when one hypothesis's truth affects another's prior), and sensitivity analysis identifying which evidence items most shift the posterior.

BHN differs from competing-hypotheses (which produces a qualitative ACH matrix without probabilities) and from differential-diagnosis (which produces a quick triage). Use BHN when the user has priors and likelihood intuitions to anchor, hypotheses are interdependent, and calibrated probability output is the goal.

Three invocation paths supported:

**User invocation:** the user invokes `bayesian-hypothesis-network` directly with a phenomenon to explain. The framework opens with brief progressive questioning to confirm priors are anchorable and the user wants the molecular pass.

**Pipeline-dispatched:** the four-stage pre-routing pipeline classifies the user's prompt as T5-hypothesis-evaluation, depth-molecular, and dispatches BHN.

**Handoff from competing-hypotheses:** an ACH analysis has surfaced that the hypothesis structure has conditional dependencies the qualitative matrix cannot capture. The handoff package includes the ACH matrix; BHN inherits it as Stage 2's input rather than regenerating.

## INPUT CONTRACT

BHN requires:

- **Phenomenon or question to explain** — the observable pattern, event, or anomaly the hypotheses are competing to explain. Elicit if missing: *"What's the phenomenon you're trying to explain, and what candidate explanations are on the table?"*

BHN optionally accepts:

- **Hypothesis set** — if the user has named hypotheses, the framework uses them as a seed and tests breadth (Stage 1's differential-diagnosis fragment generates additional candidates including a null hypothesis).
- **Evidence inventory** — observations bearing on the hypotheses, with credibility/relevance ratings if available.
- **Prior estimates** — if the user has prior probabilities anchored in base rates, the framework uses them in Synthesis Stage 1. If not, the framework elicits during execution (or documents flat-prior as explicit assumption rather than fabricating).
- **Conditional dependency map** — if the user has named which hypotheses' truths affect which others' priors, the framework uses it. If not, surfaces dependencies during Stage 2.

If priors cannot be anchored to base rates or named domain knowledge, document this explicitly as a flat-prior assumption — fabricating point estimates is a failure mode (CQ1 of bayesian-hypothesis-network: prior-fabrication).

## STAGE PROTOCOL

### Stage 1 — Differential Diagnosis (runs: fragment, hypothesis-list-with-priors-only)

**Purpose:** Generate the candidate hypothesis set widely (including unlikely-but-possible explanations and a null hypothesis), serving as breadth seed for the Bayesian network. This is a fragment run — produce the hypothesis list with rough prior anchoring, not the full diagnostic triage with rankings and disconfirming tests.

**Elicitation prompt (orchestrator → model):**
> "You are running the `differential-diagnosis` mode in fragment mode (hypothesis-list-with-priors-only) as Stage 1 of a Bayesian Hypothesis Network pass. The phenomenon is: [phenomenon]. Generate a wide candidate hypothesis set: include the dominant-narrative hypothesis, at least one orthogonal hypothesis (different mechanism), at least one combination hypothesis (multiple mechanisms together), and the null hypothesis (the phenomenon is noise or self-resolving). For each hypothesis, attach a rough prior probability anchored in base rate or domain knowledge — name the anchor explicitly. If no anchor exists, mark the prior as 'flat-prior assumption' rather than fabricating a number. Do NOT produce the full diagnostic triage with ranking and disconfirming tests; that's Stage 2's work. Output is a hypothesis list with priors and base-rate anchors."

**Intermediate output format:**

```yaml
stage_1_output:
  candidate_hypotheses:
    - hyp_id: H1
      description: "<one-line>"
      class: dominant-narrative | orthogonal-mechanism | combination | null
      prior_probability: "<number or range>"
      base_rate_anchor: "<source — e.g., 'base rate of phenomenon class is 12% per BLS occupational data 2024' or 'no anchor — flat prior'>"
    - hyp_id: H2
      ...
  breadth_check:
    dominant_present: true | false
    orthogonal_present: true | false
    combination_present: true | false
    null_present: true | false
```

**Quality gates:**
- Hypothesis set includes at least one analyst-generated alternative beyond user-proposed (CQ1 of differential-diagnosis: hypothesis-collapse).
- Null hypothesis present (CQ4: missing-zebra applies to absent rare-but-serious; here also requires null).
- Each prior carries a base-rate anchor or is explicitly flagged as flat-prior assumption.
- Hypotheses are genuinely distinct (no two make identical predictions).

**Hand-off to Stage 2:** the hypothesis list with priors becomes the column structure for the ACH matrix in Stage 2.

---

### Stage 2 — Competing Hypotheses (runs: full)

**Purpose:** Produce the full Heuer ACH matrix — evidence inventory with credibility/relevance ratings, consistency matrix (every cell populated using Heuer vocabulary CC/C/N/I/II/NA), diagnosticity assessment per evidence item, tentative conclusions via elimination, sensitivity analysis. The matrix becomes the likelihood structure feeding the Bayesian network.

**Elicitation prompt (orchestrator → model):**
> "You are running the `competing-hypotheses` mode (full ACH) as Stage 2 of a Bayesian Hypothesis Network pass. Hypotheses inherited from Stage 1: [list with priors]. Produce the full ACH output per the mode's contract: hypothesis list (use Stage 1's), evidence inventory (with credibility/relevance ratings — elicit if user hasn't supplied), consistency matrix (every cell populated with CC/C/N/I/II/NA — never leave cells absent), diagnosticity assessment per evidence row, tentative conclusions via elimination (surviving hypothesis = fewest I+II cells), sensitivity analysis (which evidence items, if reversed, would change the ranking), monitoring priorities. Work ACROSS the matrix (one evidence item against all hypotheses), not DOWN it (collecting evidence for a favored hypothesis)."

**Intermediate output format:**

```yaml
stage_2_output:
  evidence_inventory:
    - ev_id: E1
      description: "<one-line>"
      credibility: high | medium | low
      relevance: high | medium | low
  consistency_matrix:
    # rows = evidence items; columns = hypotheses
    # cells use Heuer vocabulary: CC (very consistent), C (consistent), N (neutral), I (inconsistent), II (very inconsistent), NA (not applicable)
    rows:
      - ev_id: E1
        cells: { H1: CC, H2: I, H3: N, H4: NA }
        diagnosticity: high | medium | low
        diagnosticity_reasoning: "<one-line — does this row vary sharply?>"
      - ev_id: E2
        ...
  tentative_conclusions:
    surviving_hypothesis: H_n
    elimination_arithmetic: "<count of I+II per hypothesis, tie-broken by II>"
    high_diagnosticity_items: [E1, E5]
  sensitivity_analysis:
    - reversal_scenario: "<what if E1 is wrong?>"
      effect_on_ranking: "<which hypothesis would survive>"
  monitoring_priorities:
    - "<observable signal>"
```

**Quality gates:**
- Every (evidence × hypothesis) cell populated with Heuer vocabulary (no absent cells — CQ2 of competing-hypotheses).
- At least one high-diagnosticity row (cells not all equal — CQ4).
- Conclusion phrased as elimination, not confirmation (CQ3).
- Sensitivity analysis names at least one reversal that would change ranking.
- If adversarial actors plausible, deception assessment present (CQ5).

**Hand-off to Synthesis Stage 1:** the prior-elicitation stage receives Stage 1's hypothesis list with priors and Stage 2's full ACH matrix.

---

### Synthesis Stage 1 — Prior Elicitation

**Type:** parallel-merge

**Inputs:** Stage 1 (differential-diagnosis fragment), Stage 2 (competing-hypotheses)

**Synthesis prompt (orchestrator → model):**
> "Consolidate the hypothesis set with elicited prior probabilities. For each hypothesis from Stage 1's candidate list, ensure the prior is either anchored to a stated base rate or domain knowledge OR explicitly marked as flat-prior assumption. Where Stage 2's ACH matrix surfaced additional hypotheses (analyst-generated during ACH), add them with elicited priors. Resolve any prior assignments that came from Stage 1 with vague anchoring by either strengthening the anchor citation or downgrading to flat-prior assumption. Surface any priors that look fabricated (round numbers, no anchor, no domain reasoning) and document the lack of anchor. The output is the consolidated hypothesis-set with explicit priors that the Bayesian network construction stage will use as P(H) inputs."

**Output format:**

```yaml
prior_elicitation_output:
  consolidated_hypotheses:
    - hyp_id: H1
      description: "<one-line>"
      prior_probability: "<number or range>"
      anchor_quality: well-anchored | weakly-anchored | flat-prior-assumption
      anchor_source: "<base rate, domain knowledge citation, or 'no anchor'>"
  flagged_concerns:
    - hyp_id: H_n
      concern: "<e.g., 'prior 0.5 with no anchor — likely fabricated'>"
      treatment: "<reanchor or downgrade to flat-prior>"
  mece_check:
    mutually_exclusive: true | false | partial
    collectively_exhaustive: true | false | partial
    notes: "<if non-MECE, name the structure explicitly per CQ4>"
```

**Quality gates:**
- All priors carry anchor quality label.
- Fabricated priors (round numbers, no anchor) flagged and reanchored or downgraded.
- MECE check performed (CQ4 of bayesian-hypothesis-network: mece-violation-unnamed is a failure mode).

---

### Synthesis Stage 2 — Bayesian Network Construction

**Type:** sequenced-build

**Inputs:** Synthesis Stage 1 (prior elicitation), Stage 2 (competing-hypotheses)

**Synthesis prompt (orchestrator → model):**
> "Construct the Bayesian hypothesis network. Hypotheses are nodes with priors P(H) from Synthesis Stage 1. Evidence items are nodes with likelihoods P(E|H) for each hypothesis — derive likelihoods from Stage 2's consistency matrix (CC = high P(E|H); C = moderate; N = ~base rate; I = low; II = very low; NA = excluded from this hypothesis). Surface conditional dependencies between hypotheses explicitly: if H1's truth changes H2's prior (because they share a mechanism, or H1 is a precondition for H2, or they're mutually exclusive), name the dependency. Independence is the default; if hypotheses share underlying mechanism, naming independence as the explicit assumption is required (CQ2: independence-assumption-collapse is a failure mode). The output is the network structure: nodes, arcs, conditional probability tables. Render as a structured table when the network is small; as a diagram-friendly description when complex."

**Output format:**

```yaml
bayesian_network:
  hypothesis_nodes:
    - hyp_id: H1
      prior: "<P(H1) from Synthesis Stage 1>"
  evidence_nodes:
    - ev_id: E1
      likelihoods:
        - hyp_id: H1
          P_E_given_H: "<derived from Stage 2's E1×H1 cell — e.g., CC → 0.8>"
          derivation_note: "<one-line>"
        - hyp_id: H2
          P_E_given_H: "<...>"
  conditional_dependencies:
    - dependency: "H1 truth implies P(H2) shifts from prior X to conditional Y"
      mechanism: "<one-line>"
      source: "<shared mechanism, mutual exclusion, precondition>"
  independence_assumptions:
    - "H3 and H4 assumed independent because <reasoning>"
  network_diagram_or_table: "<structured representation>"
```

**Quality gates:**
- Likelihood derivation from ACH matrix is explicit (no silent guesses).
- Conditional dependencies surfaced (or independence named as explicit assumption — CQ2).
- Likelihoods cohere with consistency-matrix cells from Stage 2.

---

### Synthesis Stage 3 — Posterior Update

**Type:** dialectical-resolution

**Inputs:** Synthesis Stage 2 (Bayesian network)

**Synthesis prompt (orchestrator → model):**
> "Compute the posterior probability distribution P(H|E) over hypotheses after evidence integration, using the Bayesian network from Synthesis Stage 2. For each hypothesis, P(H|E) ∝ P(H) × P(E|H), normalized over the hypothesis set. Where conditional dependencies are present, propagate updates through the network. Express posteriors as ranges or distributions with confidence — false precision (single point estimate without range) is a failure mode (CQ4: false-precision in source mode language). Then perform sensitivity analysis: for each evidence item, calculate how much the posterior would shift if that evidence were inverted or removed. Identify the evidence items that DOMINATE the update (the posterior is highly sensitive to them) — these are the items to monitor or to verify with greater rigor. Name the leading hypothesis with residual uncertainty made explicit."

**Output format:**

```yaml
posterior_distribution:
  per_hypothesis:
    - hyp_id: H1
      posterior_range: "<e.g., 0.45-0.60>"
      posterior_central_estimate: "<e.g., 0.52>"
      reasoning: "<prior × likelihood-product summary>"
  sensitivity_analysis:
    - ev_id: E1
      shift_if_reversed: "<e.g., 'posterior on H1 drops 0.20'>"
      dominant: true | false
    - ev_id: E2
      ...
  leading_hypothesis: H_n
  posterior_for_leading: "<range>"
  residual_uncertainty: "<prose — why posterior isn't 1.0; what would push it higher or lower>"
  evidence_items_to_monitor: "<dominant items from sensitivity analysis>"
```

**Quality gates:**
- Posterior expressed as range or distribution, not single point estimate (CQ3 of bayesian-hypothesis-network: sensitivity-omission related; also avoid false-precision).
- Sensitivity analysis identifies dominant evidence (CQ3).
- Leading hypothesis named with residual uncertainty explicit.
- If priors were flat-prior assumptions, posterior carries that uncertainty forward (no false confidence).

---

## OUTPUT CONTRACT — Final Artifact Template

```markdown
[BHN — Bayesian Hypothesis Network]

# Bayesian Hypothesis Network for <phenomenon>

## Executive Summary
- **Phenomenon:** <one-sentence description>
- **Hypotheses evaluated:** <count> — <one-line characterizations>
- **Leading hypothesis:** <H_n with posterior range>
- **Most diagnostic evidence:** <E_n — what makes it dominant>
- **Residual uncertainty:** <one-line — what would change the leading hypothesis>

## 1. Hypothesis Set with Priors
| Hyp ID | Description | Prior | Anchor Quality | Anchor Source |
|--------|-------------|-------|----------------|---------------|
| H1 | <description> | <range> | well-anchored | <citation> |
| H2 | ... | ... | flat-prior-assumption | no anchor — explicit assumption |
| ... | ... | ... | ... | ... |

[MECE check note: <whether hypothesis set is mutually exclusive and collectively exhaustive; if not, name the structure>]

## 2. Evidence Inventory with Likelihoods
| Ev ID | Description | Credibility | Relevance | Likelihood per hypothesis |
|-------|-------------|-------------|-----------|---------------------------|
| E1 | <description> | high | high | H1: 0.8 / H2: 0.2 / H3: 0.5 / H4: NA |
| E2 | ... | ... | ... | ... |

## 3. Conditional Dependencies
- **H1 → H2:** <description of how H1's truth affects H2's prior>
- **H3 ⊥ H4:** independence assumed because <reasoning>
- ...

## 4. Bayesian Network Diagram or Table
[Structured representation of nodes (hypothesis nodes + evidence nodes) and arcs (likelihoods + conditional dependencies). For small networks: table. For larger: diagram-friendly description with explicit P(H), P(E|H), and conditional CPTs.]

## 5. Posterior Distribution
| Hyp ID | Description | Prior | Posterior range | Reasoning summary |
|--------|-------------|-------|-----------------|-------------------|
| H1 | ... | <prior> | <range> | <prior × likelihoods> |
| H2 | ... | <prior> | <range> | ... |
| ... | ... | ... | ... | ... |

## 6. Sensitivity Analysis
| Ev ID | Shift if reversed | Dominant? |
|-------|-------------------|-----------|
| E1 | Posterior on H1 drops 0.20 | yes |
| E2 | Posterior on H1 drops 0.05 | no |
| ... | ... | ... |

## 7. Leading Hypothesis with Residual Uncertainty
- **Leading:** H_n — <description>
- **Posterior:** <range>
- **Residual uncertainty:** <prose — why the posterior isn't higher; what evidence would push it up; what would flip the ranking>
- **Evidence items to monitor or verify with greater rigor:** <dominant items from sensitivity analysis>

## 8. Confidence Map
| Finding | Confidence | Reason |
|---------|------------|--------|
| Prior on H1 | high / medium / low | <base-rate quality> |
| Likelihood P(E2|H3) | ... | <derivation rigor> |
| Conditional dependency H1→H2 | ... | <mechanism strength> |
| Posterior range for leading hypothesis | ... | <robustness across reasonable input variation> |
```

## WORKED EXAMPLE WALKTHROUGH

**Opening prompt (user):** *"Our service's p99 latency has degraded from 80ms to 220ms over the past six weeks. We've changed code, infrastructure, and traffic mix in that window. Help me figure out what's most likely causing it — I want a probabilistic read, not just a list."*

**Stage 1 output (differential-diagnosis fragment):**
- H1 (dominant narrative): recent code change introduced inefficient query — prior ~0.45 (anchored: this team's last 12 latency regressions, 5 traced to query changes).
- H2 (orthogonal): infrastructure change (Kubernetes node pool migration) caused noisy-neighbor — prior ~0.20 (anchored: industry surveys show ~20% of latency regressions trace to infra).
- H3 (orthogonal): traffic mix shift (new customer segment with different query shape) — prior ~0.15 (anchored: weakly — traffic shifts caused 2 of last 12 regressions).
- H4 (combination): query inefficiency × infra noisy-neighbor compounding — prior ~0.10 (no direct anchor, derived from H1×H2 joint probability if independent).
- H5 (null): no real regression, observed degradation is monitoring artifact — prior ~0.05 (anchored: 1 of last 12 reported regressions was monitoring artifact).
- H6 (zebra): downstream dependency degraded silently — prior ~0.05 (rare; surfaced by analyst).

**Stage 2 output (competing-hypotheses, full ACH):**
- Evidence inventory:
  - E1: latency regression coincides with code-change-X deployment (high credibility, high relevance).
  - E2: latency regression isolated to query type Q4 (high cred, high rel).
  - E3: K8s node pool migration completed two weeks before regression (high cred, medium rel).
  - E4: new customer segment onboarded mid-regression-window (medium cred, medium rel).
  - E5: monitoring instrumentation unchanged across window (high cred, high rel — bears on H5).
  - E6: downstream service A's p99 stable in same window (high cred, high rel — bears on H6).
- Consistency matrix (Heuer vocabulary):
  - E1 × H1=CC, H2=N, H3=N, H4=CC, H5=I, H6=N
  - E2 × H1=CC, H2=I, H3=C, H4=CC, H5=I, H6=N
  - E3 × H1=N, H2=C, H3=N, H4=C, H5=N, H6=N
  - E4 × H1=N, H2=N, H3=CC, H4=N, H5=N, H6=N
  - E5 × H1=N, H2=N, H3=N, H4=N, H5=II, H6=N
  - E6 × H1=N, H2=N, H3=N, H4=N, H5=N, H6=II
- Surviving hypothesis (fewest I+II): H1 with 1 (E5 inconsistency), H4 with 0, H3 with 0.
- High-diagnosticity items: E1 (sharply varies between H1/H4 vs others), E2 (sharply discriminates Q4-bound hypotheses), E5 (rules out H5), E6 (rules out H6).
- Sensitivity: if E1 reversed (latency regression does not coincide with code change), H1 collapses to ~0.05; H4 also weakens.

**Synthesis Stage 1 (prior elicitation):**
- All priors carry anchors except H4 (derived from joint) and H6 (analyst-generated).
- H4 and H6 priors flagged as weakly-anchored.
- MECE check: hypotheses are not strictly mutually exclusive (H4 = H1∧H2). This is named explicitly: H1, H2, H3 are competing single-cause; H4 represents the conjunction; H5 is null; H6 is alternative cause. Posterior interpretation must account for non-MECE structure.

**Synthesis Stage 2 (Bayesian network construction):**
- Nodes: H1-H6 (hypothesis nodes with priors), E1-E6 (evidence nodes with likelihoods).
- Likelihoods derived from consistency matrix:
  - P(E1|H1) ≈ 0.80 (CC → high), P(E1|H4) ≈ 0.80 (CC), P(E1|H5) ≈ 0.10 (I → low), others ~0.40 (N → moderate).
  - Similar derivations for E2-E6.
- Conditional dependencies:
  - H1 ∧ H2 → H4: H4's prior is a function of H1 and H2. If H1 and H2 are independent: P(H4) = P(H1) × P(H2) ≈ 0.09. Observed prior 0.10 is approximately consistent.
  - Independence assumption: H3 (traffic mix) and H1 (code change) assumed independent because they trace to different mechanisms.
- Network diagram-friendly description: H1, H2, H3, H5, H6 are independent root hypotheses; H4 is a conjunction node; E1-E6 are evidence nodes with likelihoods to each H.

**Synthesis Stage 3 (posterior update):**
- Computing P(H|E) ∝ P(H) × ∏_i P(E_i|H):
  - H1 (code change): posterior range 0.40-0.55, central 0.48 — leading hypothesis.
  - H4 (combination): posterior range 0.20-0.30, central 0.25 — second.
  - H2 (infra alone): posterior range 0.10-0.18, central 0.14.
  - H3 (traffic alone): posterior range 0.08-0.15, central 0.11.
  - H5, H6: posterior < 0.02 each (ruled out by E5/E6 II cells).
- Sensitivity: if E1 reversed, H1 posterior drops to ~0.10, H4 drops to ~0.10; H2 and H3 rise to ~0.30 each. E1 is the dominant evidence item.
- Leading hypothesis: H1 (code change introduced inefficient query) with posterior 0.40-0.55. But H4 (combination) is non-trivial at 0.20-0.30 — the right action may be to investigate both H1 and H2 in parallel, since H4 reveals their conjunction is plausible enough that fixing only one may leave residual regression.
- Residual uncertainty: posterior is not above 0.55 for any single hypothesis because H4's conjunction is plausible. The ranking would flip if E1 is wrong (e.g., the deployment timing was misread); verifying E1 with greater rigor (re-checking deployment logs against latency timestamps) is the highest-leverage next step.

## CAVEATS AND OPEN DEBATES

**Composition limit — false-precision avoidance.** Bayesian Hypothesis Network produces probabilistic output. The temptation to report posteriors as single point estimates is strong; resist it. The mode's CQ3 (sensitivity-omission) and the source-mode probabilistic-forecasting's CQ4 (false-precision) both target this failure. Posteriors are ranges. Sensitivity analysis is not optional.

**Prior fabrication risk.** The framework's most fragile stage is prior elicitation. When base rates are unavailable, the honest move is to document flat-prior assumption and let the posterior reflect that uncertainty, rather than to fabricate point estimates that look like rigor (CQ1 of bayesian-hypothesis-network: prior-fabrication).

**MECE violation handling.** Real-world hypothesis sets are often non-MECE (hypotheses overlap; conjunction hypotheses exist). The framework does not require forcing hypotheses into MECE structure; it requires naming the non-MECE structure explicitly (CQ4: mece-violation-unnamed). When non-MECE, posterior interpretation must account for the structure (e.g., H4 = H1∧H2 means the user should not double-count H1 and H4 evidence).

**When to escalate sideways:** if during execution the dispute is really about which paradigm is correct (different mechanisms invoking different theoretical frames), route to T9 frame-comparison or worldview-cartography. BHN operates within a frame, weighing within-frame hypotheses.

## QUALITY GATES (overall)

- Differential-diagnosis fragment ran (hypothesis breadth seed, including null hypothesis).
- Competing-hypotheses full ACH ran with every cell populated using Heuer vocabulary.
- Priors anchored to base rates or named domain knowledge, OR explicitly flagged as flat-prior assumption (no fabricated point estimates).
- Conditional dependencies surfaced explicitly, OR independence named as explicit assumption.
- Posterior expressed as range or distribution (no false precision).
- Sensitivity analysis identifies dominant evidence items.
- MECE check performed (or non-MECE structure named).
- Confidence map populated per finding.
- The four critical questions of `bayesian-hypothesis-network` (prior-fabrication, independence-assumption-collapse, sensitivity-omission, mece-violation-unnamed) are addressed.

## RELATED MODES AND CROSS-REFERENCES

- **Paired mode file:** `Modes/bayesian-hypothesis-network.md`
- **Component mode files:**
  - `Modes/differential-diagnosis.md` (Stage 1, fragment)
  - `Modes/competing-hypotheses.md` (Stage 2, full ACH)
- **Sibling Wave 4 modes (related operations):** `Modes/decision-architecture.md` (T3), `Modes/wicked-future.md` (T6) — share probabilistic uncertainty regime.
- **Territory framework:** `Framework — Hypothesis Evaluation.md`
- **Lens dependencies:** heuer-ach-diagnosticity (required), pearl-do-calculus (optional, when network has causal interpretation), tetlock-superforecasting (optional, when long-horizon hypotheses), kahneman-tversky-bias-catalog (foundational), knightian-risk-uncertainty-ambiguity (foundational).

*End of Bayesian Hypothesis Network Analysis Framework.*
