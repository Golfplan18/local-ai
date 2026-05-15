---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-01

---

# MODE: Argument Audit

```yaml
# 0. IDENTITY
mode_id: argument-audit
canonical_name: Argument Audit
suffix_rule: analysis
educational_name: argument audit (Frame Audit + Coherence Audit integrated)

# 1. TERRITORY AND POSITION
territory: T1-argumentative-artifact-examination
gradation_position:
  axis: depth
  value: molecular
adjacent_modes_in_territory:
  - mode_id: coherence-audit
    relationship: depth-light sibling (internal-consistency)
  - mode_id: frame-audit
    relationship: depth-light sibling (frame-surfacing + suspending)
  - mode_id: propaganda-audit
    relationship: specificity-specialized sibling (Stanley-influenced, adversarial-stance variant)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want a full audit of this argument: both whether it coheres and what frame it imports"
    - "the standard light passes each catch part of what's wrong; I want them integrated"
    - "willing to spend the time on a thorough integrated audit, not just a quick coherence or frame check"
    - "I want cross-cutting issues that neither the coherence pass nor the frame pass would catch alone"
  prompt_shape_signals:
    - "argument audit"
    - "full audit of this argument"
    - "coherence and frame check"
    - "thorough argument analysis"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants integrated audit spanning frame-audit + coherence-audit + cross-cutting synthesis"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "want only internal-consistency check" → coherence-audit
    - "want only frame-surfacing" → frame-audit
    - "argument is propaganda or persuasion-engineered" → propaganda-audit
    - "want to evaluate the argument as a proposal with stance" → T15 modes (steelman, balanced-critique, red-team-assessment / red-team-advocate)
when_not_to_invoke:
  - "User has time pressure" → coherence-audit or frame-audit
  - "User is asking who benefits from the argument's acceptance, not whether it holds" → cui-bono (T2)
  - "User wants paradigm-level comparison rather than single-artifact audit" → frame-comparison or worldview-cartography (T9)

# 3. EXECUTION STRUCTURE
composition: molecular
# NOTE: Decision N — Wave 4 build at depth-molecular position completing T1 depth ladder
# (coherence-audit → frame-audit → argument-audit). Carries Debate D2 (motte-and-bailey:
# fallacy or doctrine? Shackel preference vs. common usage).
molecular_spec:
  components:
    - mode_id: frame-audit
      runs: full
    - mode_id: coherence-audit
      runs: full
  synthesis_stages:
    - name: frame-coherence-merge
      type: parallel-merge
      input: [frame-audit, coherence-audit]
      output: "merged audit: per-claim coherence findings paired with frame-surfacing findings; identification of where frame-imports do analytical work coherence-audit alone would miss"
    - name: cross-cutting-integration
      type: contradiction-surfacing
      input: [frame-coherence-merge]
      output: "cross-cutting issues: where the argument's coherence depends on frame-imports that are themselves contested; where coherence-failures track frame-substitutions; where motte-and-bailey-style structure (or other frame-shifting fallacies) operates across claims"
    - name: integrated-audit-document
      type: dialectical-resolution
      input: [frame-coherence-merge, cross-cutting-integration]
      output: "integrated argument audit: per-claim findings, frame-level findings, cross-cutting issues, named fallacies (with debate notes where applicable), and overall argument-soundness assessment"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; do not aggregate over low-confidence frame or coherence findings

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [argumentative_artifact, audit_focus]
    optional: [prior_audits, contextual_background]
    notes: "Applies when user supplies the artifact plus a stated audit focus."
  accessible_mode:
    required: [argumentative_artifact]
    optional: [why_audit, contextual_background]
    notes: "Default. Mode elicits audit focus during execution."
  detection:
    expert_signals: ["audit this argument", "frame and coherence", "thorough audit"]
    accessible_signals: ["does this hold up", "something feels off", "check this argument"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you paste or describe the argument you want audited?'"
    on_underspecified: "Ask the user whether they want the full Argument Audit molecular pass or a lighter Coherence Audit / Frame Audit read."
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Does the cross-cutting-integration stage actually surface issues that neither component pass would catch alone, or does it merely concatenate them?"
    failure_mode_if_unmet: integration-failure
  - cq_id: CQ2
    question: "Are frame-imports identified concretely (which premises smuggle in which framings), or are they noted vaguely?"
    failure_mode_if_unmet: frame-import-vagueness
  - cq_id: CQ3
    question: "Are coherence findings grounded in specific claim-pairs and inference steps, or are they stated as general impressions?"
    failure_mode_if_unmet: coherence-impressionism
  - cq_id: CQ4
    question: "Where named fallacies are invoked (motte-and-bailey, equivocation, etc.), is the invocation specific and warranted, or is it a label slapped on a contested move?"
    failure_mode_if_unmet: fallacy-labeling-without-warrant

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: integration-failure
    detection_signal: "Cross-cutting-issues section restates per-claim and frame findings without identifying interactions between them."
    correction_protocol: re-dispatch (synthesis stage with explicit interaction prompt)
  - name: frame-import-vagueness
    detection_signal: "Frame findings refer to 'the frame' or 'the assumption' without naming which premise carries which import."
    correction_protocol: re-dispatch
  - name: coherence-impressionism
    detection_signal: "Coherence findings cite no specific claim-pair or inference step."
    correction_protocol: re-dispatch
  - name: fallacy-labeling-without-warrant
    detection_signal: "Named fallacies (motte-and-bailey, etc.) are invoked without showing the specific structural move."
    correction_protocol: flag and re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - walton-argumentation-schemes
  optional:
    - lakoff-framing
    - shackel-motte-and-bailey (when motte-and-bailey is in play; carries Debate D2)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Argument Audit is the heaviest mode in T1's depth ladder."
  sideways:
    target_mode_id: propaganda-audit
    when: "Artifact is propaganda or persuasion-engineered; Stanley-influenced specialized variant applies."
  downward:
    target_mode_id: coherence-audit
    when: "User has time pressure or scope is narrower (internal-consistency only)."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Argument Audit is the degree to which the cross-cutting-integration stage produces issues that no single component pass would catch alone. A thin molecular pass concatenates frame-audit and coherence-audit outputs; a substantive pass identifies where coherence depends on contested frame-imports, where coherence-failures track frame-substitutions across claims, and where motte-and-bailey-style structure operates across an argument's parts. Test depth by asking: does the audit name a structural move that requires both frame-perception and coherence-tracking to detect?

## BREADTH ANALYSIS GUIDANCE

Breadth in Argument Audit is the catalog of frames considered before frame-audit narrows. Widen the lens to scan: dominant-paradigm frame; minority-tradition frame; rhetorical-genre frame; historical-genealogy frame. Even when the cross-cutting-integration narrows to specific cross-cutting issues, breadth is documented in the frame-surfacing-findings section. Note: alternative compositions considered included adding propaganda-audit; current composition stays neutral and routes to propaganda-audit when artifact is propaganda-engineered.

## EVALUATION CRITERIA

Argument Audit's evaluation surface is bifurcated because the mode is molecular: per-component quality (frame-audit and coherence-audit each performed substantively) and synthesis quality (cross-cutting integration producing findings neither component would have produced alone). Synthesis is load-bearing — CQ1 (integration vs concatenation) is the critical question whose negative answer most directly invalidates the output, and integration-failure is the failure mode that distinguishes a successful Argument Audit from a stapling of two sub-audits. CQ2–CQ4 act as quality gates on the underlying components.

The evaluator works in Walton-scheme, Toulmin, and Lakoff vocabulary, with Shackel checks when motte-and-bailey is invoked. Five checks:

1. **Cross-cutting integration (CQ1, load-bearing).** For each cross-cutting atom, ask: could frame-audit alone have produced this finding? Could coherence-audit alone? If yes to either, the atom is mis-routed. Genuine cross-cutting findings name a structural interaction — a frame-import doing inferential work coherence alone misses, a coherence-failure tracking a frame-substitution across claims, motte-and-bailey-style alternation operating across multiple claims. No atoms meeting this test means integration-failure: the audit is a concatenation, not a molecular pass.

2. **Frame-import specificity (CQ2).** Each frame-surfacing atom must name the specific premise carrying the import. References to "the X frame" without locating the importing premise are frame-import-vagueness. The reading is Lakoff — surface frame, deep frame, framing presupposition — applied to specific premises.

3. **Coherence grounding (CQ3).** Each coherence finding must cite the specific claim-pair or inference step at issue. The Toulmin decomposition (claim / grounds / warrant / backing / qualifier / rebuttal) is the evaluator's reading vocabulary; verdicts of "the reasoning is shaky" or "something feels off" without claim-pair citations are coherence-impressionism.

4. **Fallacy and scheme warrant (CQ4).** Where a Walton scheme is named (expert opinion, position to know, cause to effect, analogy, etc.), the audit's premise pattern must match the argument's actual structure, and the scheme's critical questions must be applied to the argument's actual premises rather than to a reconstructed strawman. Where motte-and-bailey is invoked, the motte claim, the bailey claim, and the alternation point must each be named. Bare labels are fallacy-labeling-without-warrant.

5. **Stance neutrality.** Argument Audit is descriptive of argument structure, not evaluative of conclusion-truth. Verdicts that step beyond soundness ("the argument is dishonest," "the conclusion is wrong") are out-of-scope and route to T15 (steelman, balanced-critique, the red-team modes). The evaluator flags such residue rather than smoothing it.

Confidence is calibrated separately: synthesis-stage atoms inherit lower confidence than component-stage atoms; uniform confidence across both surfaces is miscalibrated. Where Debate D2 (motte-and-bailey doctrine vs. fallacy) applies, the evaluator confirms the audit named the structural move in the argument's terms rather than relying on the label alone.

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates. Revise to add specificity to vague frame-imports or impressionistic coherence findings. Revise to warrant named fallacies with structural detail. Resist revising toward stance-bearing evaluation — Argument Audit is neutral; stance-bearing evaluation belongs in T15 (steelman, the red-team modes, balanced-critique). Stop at the audit. Do not announce, flag, or recommend stance-bearing follow-up in the output.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **integrated argument-audit atoms with explicit cross-cutting findings**: per-claim coherence atoms from coherence-audit, frame-surfacing atoms from frame-audit, cross-cutting integration atoms (the molecular value), named-fallacy atoms with structural warrant, and articulation-script atoms. The atoms are:

1. **Argument-summary atom.** The argument under audit stated once at the corpus head — claim, supporting moves, conclusion.

2. **Per-claim coherence atoms (coherence-audit provenance).** Each carries: claim being audited, Toulmin-decomposed elements (claim / grounds / warrant / backing / qualifier / rebuttal), and the coherence verdict (holds / fails / partially-holds) with structural reason. Coherence-impressionism is the named failure mode; impressionistic verdicts without claim-pair or inference-step citations do not survive.

3. **Frame-surfacing atoms (frame-audit provenance).** Each carries: frame name, the specific premise or claim that imports it, the alternative frames it displaces, what is hidden by the frame. Frame-import-vagueness is the named failure mode; "the argument operates within X frame" without naming the importing premise does not survive.

4. **Cross-cutting integration atoms.** The molecular value — each atom names a structural issue requiring BOTH frame-perception and coherence-tracking to detect (a frame-import doing load-bearing inferential work coherence-audit alone misses; a coherence-failure that tracks a frame-substitution across claims; motte-and-bailey-style structure operating across the argument). At minimum one cross-cutting atom; integration-failure is the named failure mode (cross-cutting section concatenating component findings without identifying interactions).

5. **Named-fallacy atoms with structural warrant.** Each carries: the named fallacy (motte-and-bailey, equivocation, composition, etc.), the specific structural move (which claim is motte, which is bailey, where the alternation occurs), and the warrant for the label. Fallacy-labeling-without-warrant is the named failure mode; bare labels do not survive.

6. **Argument-soundness assessment atom.** A single corpus-level verdict integrating frame and coherence findings (not single-component): `the argument as given [holds / fails / partially-holds] because [structural reason that integrates both component findings]`.

7. **Articulation-script atoms.** Per surfaced issue, a usable line for the user to deploy in conversation. Each carries: the surfaced issue (cross-reference to atoms 2-5), a one-to-three-sentence usable line, and the context where it applies.

8. **Component-provenance tags.** Each atom in items 2-5 carries `[from frame-audit]` / `[from coherence-audit]` / `[cross-cutting]`. Tags make integration auditable; silo-aggregation is visible when atoms cluster within single-component tags rather than interleaving.

9. **Residual uncertainties + confidence per finding.** Confidence markers attach to findings; synthesis-stage atoms inherit lower confidence than component-stage atoms.

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Per-claim restatement across components** — when frame-audit and coherence-audit both surfaced findings about the same claim with parallel framings, collapse to single atoms with both components' insights merged.
- **Vague frame-imports** — "the argument operates within X frame" without naming which specific premise imports it.
- **Coherence-impressionism** — "the reasoning is shaky" / "something feels off" without claim-pairs or inference-step citations.
- **Bare fallacy labels** — invoking motte-and-bailey, equivocation, etc. without the structural move that warrants the label.
- **Integration-failure residue** — cross-cutting-issues section restating per-claim and frame findings without identifying the inter-component interactions.
- **Stance-bearing evaluative language** — "the argument is wrong / bad / dishonest" residue. Argument Audit is neutral; stance-bearing evaluation belongs in T15 modes.

**What NOT to collapse:**

- **Cross-stream cross-cutting-interpretation differences** — when streams identified different structural cross-cutting issues, preserve both as parallel atoms.
- **Frame-vs-coherence interpretation disagreement for the same finding** — when one stream read a finding as primarily frame-based and the other as primarily coherence-based, preserve both interpretations as parallel atoms (the disagreement is itself an integration finding).
- **Articulation-script variations** — when streams produced different usable lines for the same surfaced issue, preserve both. Multiple scripts is breadth.

## VERIFICATION CRITERIA

Verified means: both component passes ran (or were flagged as proceeded-with-gap); cross-cutting integration surfaces issues neither component caught alone; frame-imports and coherence findings are concretely grounded; named fallacies are warranted with structural specificity; user-facing articulation scripts are present and usable; the four critical questions are addressed in the response. The response is conversational prose addressed to the user — verification does not require any specific section structure, only that the content contract is satisfied.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **conversational audit addressed to the user, lead-with-the-flaw, with articulation scripts at the end**. The audit's findings reach the user via flowing prose, not via numbered methodology sections. Place the consolidated-corpus atoms into the deliverable in this order:

1. **Lead H2 heading — name the central flaw.** The first line of the deliverable is an H2 heading naming the integrated finding in plain language. Examples: `## The argument relies on a hidden premise about agency`, `## Your friend is doing a frame swap, not an argument`, `## The "just statistics" move is doing all the work`. The heading IS the lead — no preamble before it. The heading is conversational, not academic; do not name analytical methods in it.

2. **Body — flowing prose, integrated findings.** Walk through the supporting findings as paragraphs in this order:
   - The framing move the argument relies on (from frame-surfacing atoms, in plain language — "the argument frames X as Y", not "the Lakoff frame here")
   - The hidden premise or inferential gap the argument needs to work (from per-claim coherence atoms, in plain language)
   - The cross-cutting issue — where frame-import and coherence-failure interact (the molecular value, surfaced as the audit's distinctive contribution that single-component audits would miss)
   - Named fallacies (motte-and-bailey, composition / reductionist fallacy, straw man, equivocation) in plain language with structural detail — name the specific move, not just the label

   No numbered section headers (`### 1. Charitable Reconstruction`, `### 2. Toulmin Decomposition`). No methodology labels (Toulmin Decomposition, Mereological Audit, Audit Summary). Paragraphs only in the body.

3. **Articulation scripts — register-change transition.** After the analytical findings, transition with a single second H2: `## Here's what you can say back` or similar. This is one of the few times a second H2 is appropriate — a real change of register from analysis to deployment.

   Render each script as: a short setup ("when your friend says X..."), the usable line ("you can say back: …"), and a one-sentence why ("this works because it points to the structural move you surfaced above"). Three to five scripts is typical.

4. **Where Debate D2 (motte-and-bailey) is invoked.** Name the structural move in the argument's terms — which claim is the motte (defensible / modest), which is the bailey (ambitious / desired), where the alternation occurs. Do not rely on the label alone. Note in passing whether Shackel's doctrinal usage or the wider fallacy-label usage best fits ("this looks like a doctrine-level alternation, not just a single move").

5. **Confidence inline only where meaningful.** Use natural confidence language inline ("almost certainly", "probably", "I'm less sure about this part") only where confidence varies meaningfully across findings. Do NOT emit a standalone Confidence Map, Provenance Attribution, Content Contract Checklist, or Continuity Prompt — those belong in orchestrator metadata.

**Per-section conventions:**

- The deliverable's first character is `#` (the lead H2). No preamble of any kind.
- Use H2 only for the lead heading and the articulation-scripts transition. No other section headers in the body.
- Avoid pipeline-machinery vocabulary throughout: "frame-audit findings", "coherence-audit findings", "the cross-cutting integration stage", "Stream A vs Stream B" — those belong inside the orchestrator.
- Avoid methodology badges: do not label what you're doing as "Toulmin decomposition" or "Walton scheme classification" — let the analysis land as substance.
- The deliverable ends when the substance ends. No decorative close, no aphoristic signature line.

## CAVEATS AND OPEN DEBATES

**Debate D2 — Motte-and-bailey: fallacy or doctrine?** Shackel (2005, "The Vacuity of Postmodernist Methodology") introduced the term as a *doctrine* — a structural feature of certain argumentative positions in which an arguer alternates between a defensible "motte" (modest claim) and a desirable "bailey" (ambitious claim) when challenged. Shackel's preferred usage frames motte-and-bailey as a *characterization of a doctrine's structure*, not as a fallacy committed in a single inferential step. In wider usage (online discourse, popular argumentation guides), the term has come to function as a *fallacy label* applied to single moves where an arguer retreats from an ambitious claim under pressure. This mode operates without adjudicating the debate: when motte-and-bailey is invoked, the audit names the structural move in the argument's terms (which claim is motte, which is bailey, where the alternation occurs) rather than relying on the label alone, and notes whether Shackel's doctrinal usage or the wider fallacy-label usage best fits the case. Consumers seeking a stricter Shackel-aligned reading should treat motte-and-bailey invocations as doctrinal characterizations requiring multi-claim evidence; consumers using the wider sense may accept single-move applications. Citations: Shackel 2005; cf. wider discussion in popular argumentation literature.


---

## DEFAULT GEAR

Gear 4

Argument Audit's molecular composition (parallel frame-audit + coherence-audit with three synthesis stages) is a Gear 4 workload. Gear 4 runs Depth and Breadth in parallel, then composes through Steps 5–7 (cross-eval, revise, consolidate). The consolidator's role is exactly the role this mode's synthesis stages require.

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `contradicts`, `qualifies`, `extends`
**Deprioritize:** `precedes`, `parent`

*Family: argument-evaluation. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
