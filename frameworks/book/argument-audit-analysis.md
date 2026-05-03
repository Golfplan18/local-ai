
# Argument Audit Analysis Framework

*A Framework for Producing an Integrated Argument Audit That Combines Frame-Audit (Lakoff/Goffman/Entman Frame-Surfacing) with Coherence-Audit (Toulmin Reconstruction + Fallacy Taxonomy) Plus Cross-Cutting Integration Surfacing Issues Neither Component Pass Would Catch Alone — Including Frame-Coherence Interactions and Multi-Claim Structural Moves.*

*Version 1.0*

*Bridge Strip: `[AAA — Argument Audit]`*

---

## Architectural Note

This framework supports the `argument-audit` mode, the depth-molecular operation in T1 (argumentative artifact examination). The mode file at `Modes/argument-audit.md` carries the locked spec — molecular_spec.components, critical_questions, output_contract.required_sections — sufficient for the orchestrator to dispatch the two component modes (`frame-audit`, `coherence-audit`) and the three synthesis stages (frame-coherence-merge, cross-cutting-integration, integrated-audit-document). This framework adds the procedural detail the spec does not carry: the elicitation prompts the orchestrator uses, the intermediate output formats, the per-stage quality gates, the worked example showing the framework operating end-to-end, and Debate D2 (motte-and-bailey: fallacy or doctrine?) which this mode carries.

The framework sits in T1's depth ladder above `coherence-audit` (T1-light + neutral-stance, atomic, internal-consistency check) and `frame-audit` (T1-light + suspending-stance, atomic, frame-surfacing) and beside `propaganda-audit` (T1 specificity-specialized + adversarial-stance variant). It composes coherence-audit and frame-audit into a cross-cutting integration that catches issues neither pass detects alone — most notably: arguments whose coherence depends on contested frame-imports, coherence-failures that track frame-substitutions across claims, and motte-and-bailey-style structures that require multi-claim tracking. The territory framework is `Framework — Argumentative Artifact Examination.md`. AAA is the heaviest analytical mode in T1's depth ladder.

---

## How to Use This File

This framework runs when the user has an argumentative artifact (article, op-ed, paper, ad, manifesto, policy document, debate transcript) and wants an integrated audit — both whether the argument coheres internally (Toulmin reconstruction + fallacy check) AND what frame the argument imports (Lakoff metaphor, Goffman frames, Entman functions). AAA's value is in the synthesis stage: cross-cutting issues that single-component passes miss — for example, an argument whose internal coherence is sound but only because contested frame-imports are doing analytical work that pure inferential check would not catch.

AAA differs from coherence-audit (atomic internal-consistency) and from frame-audit (atomic frame-surfacing). Use AAA when the argument is substantial enough to warrant integrated treatment, when the user suspects both inferential and framing-level issues are at play, and when the time investment for molecular pass is warranted.

Three invocation paths supported:

**User invocation:** the user invokes `argument-audit` directly with an argumentative artifact. The framework opens with brief progressive questioning to elicit audit focus (which conclusion or claim cluster to audit support for).

**Pipeline-dispatched:** the four-stage pre-routing pipeline classifies the user's prompt as T1, depth-molecular, and dispatches AAA.

**Handoff from another mode:** coherence-audit or frame-audit has surfaced that the audit warrants integrated treatment (e.g., coherence findings depend on contested frame-imports that the coherence pass identified but didn't audit). The handoff package includes the prior analysis; AAA inherits it as a starting position.

## INPUT CONTRACT

AAA requires:

- **Argumentative artifact** — the text being audited (article, op-ed, paper, ad, manifesto, policy document, debate transcript, etc.). Elicit if missing: *"Could you paste or describe the argument you want audited?"*

AAA optionally accepts:

- **Audit focus** — which conclusion or claim cluster to audit support for. If not provided, infer from the artifact and the user's reason-for-audit. Elicit: *"Which claim or conclusion's support do you want audited?"*
- **Why audit** — what the user suspects is off (frame manipulation / coherence failure / both / general structural sweep).
- **Genre context** — academic paper / op-ed / ad / policy document / debate / political speech (informs Walton dialogue type and frame-typology selection).
- **Prior audits** — if other audits have been performed on the same artifact, the framework integrates rather than regenerates.
- **Contextual background** — surrounding discourse, related artifacts with competing frames, source inventory.

## STAGE PROTOCOL

### Stage 1 — Frame Audit (runs: full)

**Purpose:** Surface the operative frame(s) the argument deploys — Lakoff metaphor inventory, Goffman primary framework and keyings, Entman four functions per frame (problem definition / causal interpretation / moral evaluation / treatment recommendation), selection-and-salience inventory (what included, what excluded), presupposition and nominalization audit, counterframe construction. This is stance-suspending: surface the frame without endorsing or attacking it.

**Elicitation prompt (orchestrator → model):**
> "You are running the `frame-audit` mode (full) as Stage 1 of an Argument Audit pass. The argumentative artifact is: [artifact]. Audit focus: [focal_question]. Produce the full frame-audit output per the mode's contract: operative frames named in alternative-comparable vocabulary (not the artifact's own naturalized terms — frame-naturalization is a failure mode), Lakoff metaphor inventory (with quoted text and source-domain → target-domain mappings), Goffman primary framework and keyings, Entman four functions per frame (problem definition / causal interpretation / moral evaluation / treatment recommendation — populated per frame), selection and salience inventory (both what's included AND what's excluded — silence-blindness is a failure mode), presupposition and nominalization audit (with quoted text), counterframe (what would the issue look like under an alternative frame). Stance: suspending — surface the frame and show its costs, but do not slide into rejection (that's propaganda-audit territory)."

**Intermediate output format:**

```yaml
stage_1_output:
  operative_frames:
    - frame_name: "<named in alternative-comparable vocabulary>"
      one_sentence_characterization: "<>"
      lakoff_metaphor_inventory:
        - metaphor: "<source-domain → target-domain>"
          quoted_text: "<from artifact>"
          inferential_entailments: "<what the metaphor licenses>"
      goffman_primary_framework: natural | social
      goffman_keying: make-believe | contests | ceremonials | technical-redoings | regroundings | none
      goffman_fabrication: true | false (with explanation if true)
      entman_four_functions:
        problem_definition: "<from artifact, quoted or paraphrased>"
        causal_interpretation: "<>"
        moral_evaluation: "<>"
        treatment_recommendation: "<>"
  selection_and_salience_inventory:
    included_and_emphasized: "<list>"
    excluded_or_downplayed: "<list — what's silent>"
  presupposition_and_nominalization_audit:
    - presupposition: "<the claim presupposed>"
      quoted_text: "<from artifact>"
      mechanism: presupposition | nominalization | passivization | lexicalization
  counterframes:
    - counterframe_name: "<>"
      what_issue_looks_like_under: "<one paragraph>"
```

**Quality gates:**
- Operative frames named in alternative-comparable vocabulary (CQ1 of frame-audit: frame-naturalization).
- Entman four functions populated per frame (CQ2: function-collapse).
- Selection-and-silence inventory has entries in both columns (CQ3: silence-blindness).
- Lexical/grammatical mechanisms cited with quoted text (CQ4: macro-frame-only-reading).
- At least one counterframe constructed (CQ5: counterframe-omission).

**Hand-off to Stage 2:** Stage 2 receives the artifact and Stage 1's frame findings. Coherence-audit will assess the inferential structure independently; the synthesis stage will integrate.

---

### Stage 2 — Coherence Audit (runs: full)

**Purpose:** Audit the argument's inferential structure — charitable reconstruction (surfacing implicit premises), Toulmin breakdown per inferential move (claim, data, warrant, backing, qualifier, rebuttal), named fallacies with quoted text + identified inferential move + violated principle + reason-it-fails-here, structural coherence failures not in the named-fallacy taxonomy (premise smuggling, scope shift, definitional drift, enthymeme failure), argument-soundness vs. conclusion-truth separation. Stance: neutral.

**Elicitation prompt (orchestrator → model):**
> "You are running the `coherence-audit` mode (full) as Stage 2 of an Argument Audit pass. The argumentative artifact is: [artifact]. Audit focus: [focal_claim]. Produce the full coherence-audit output per the mode's contract: charitable reconstruction (the strongest version of the argument actually present in the text, with implicit premises surfaced — uncharitable-reconstruction is a failure mode), Toulmin breakdown per inferential move (claim / data / warrant / backing / qualifier / rebuttal — surface the warrants explicitly; warrant-blindness is a failure mode), named fallacies with full structural specification (quoted text + inferential move + violated principle + reason-it-fails-here; name-without-structure is a failure mode), structural coherence failures beyond the named-fallacy taxonomy (premise smuggling, scope shift, definitional drift, unstated load-bearing assumptions, enthymeme failure — named-fallacy-only-reading is a failure mode), argument-holds-or-fails per inferential move, argument-wrong vs. conclusion-wrong separation. Stance: neutral. The verdict is conclusion-agnostic — 'this argument as given does not establish its conclusion; the conclusion may still be true.'"

**Intermediate output format:**

```yaml
stage_2_output:
  charitable_reconstruction: "<strongest version of argument with implicit premises surfaced>"
  toulmin_breakdown:
    - move_id: M1
      claim: "<>"
      data: "<>"
      warrant: "<surfaced explicitly — the inferential rule connecting data to claim>"
      backing: "<support for the warrant>"
      qualifier: "<modal — 'usually', 'in most cases'>"
      rebuttal: "<conditions under which warrant doesn't apply>"
      move_holds_or_fails: holds | fails | partial
      reasoning: "<one-line>"
  named_fallacies:
    - fallacy_name: "<canonical name>"
      quoted_text: "<from artifact>"
      inferential_move: "<which Toulmin move this involves>"
      violated_principle: "<what the move violates>"
      reason_it_fails_here: "<context-specific — not just abstract definition>"
  structural_coherence_failures_not_named_fallacies:
    - failure_id: SF1
      failure_type: premise-smuggling | scope-shift | definitional-drift | unstated-load-bearing-assumption | enthymeme-failure
      description: "<>"
      quoted_text: "<from artifact>"
  argument_wrong_vs_conclusion_wrong:
    argument_assessment: "this argument as given establishes / does not establish its conclusion"
    conclusion_independent_assessment: "the conclusion may still be true / false; that is independent of this audit"
```

**Quality gates:**
- Charitable reconstruction precedes any fallacy claim (CQ1 of coherence-audit: uncharitable-reconstruction).
- Toulmin warrants surfaced per inferential move (CQ2: warrant-blindness).
- Every named fallacy substantiated with quoted text + violated principle + reason-it-fails-here (CQ3: name-without-structure).
- Argument-wrong explicitly separated from conclusion-wrong (CQ4: argument-conclusion-conflation).
- Structural-failure sweep performed beyond named fallacies (CQ5: named-fallacy-only-reading).
- Severity grading symmetric across artifact (no asymmetric-rigor).

**Hand-off to Synthesis Stage 1:** the frame-coherence-merge stage receives Stage 1's frame findings and Stage 2's coherence findings.

---

### Synthesis Stage 1 — Frame-Coherence Merge

**Type:** parallel-merge

**Inputs:** Stage 1 (frame-audit), Stage 2 (coherence-audit)

**Synthesis prompt (orchestrator → model):**
> "Merge the frame-audit and coherence-audit findings. For each inferential move from Stage 2's Toulmin breakdown, identify whether Stage 1's frame findings bear on it: does a warrant depend on a frame-import (a metaphor or presupposition that smuggles in framing-level commitments)? Does a claim's data sit at a level of generality where the frame's selection-and-salience matters (some data included, other data excluded)? For each frame-import in Stage 1, identify which inferential moves in Stage 2 it influences. The output is a merged audit: per-claim coherence findings paired with frame-surfacing findings, with explicit identification of where frame-imports are doing analytical work that coherence-audit alone would miss. Resist concatenation — the integration produces pairings, not parallel sections."

**Output format:**

```yaml
frame_coherence_merge:
  per_inferential_move_with_frame:
    - move_id: M_n
      coherence_finding: holds | fails | partial
      frame_imports_bearing_on_move:
        - frame_import: "<from Stage 1>"
          how_it_bears_on_move: "<one-line>"
          analytical_work_done: "<what the frame-import lets the move conclude that pure inference would not>"
  frame_imports_doing_analytical_work:
    - frame_import: "<>"
      inferential_moves_influenced: "<list of move_ids>"
      coherence_finding_dependence: "<would the move hold if the frame-import were challenged?>"
```

**Quality gates:**
- Output integrates rather than concatenates.
- Per-move pairings of coherence-finding × frame-import are explicit.
- Frame-imports doing analytical work are surfaced (this is the integration's unique product).

---

### Synthesis Stage 2 — Cross-Cutting Integration

**Type:** contradiction-surfacing

**Inputs:** Synthesis Stage 1 (frame-coherence merge)

**Synthesis prompt (orchestrator → model):**
> "Identify cross-cutting issues that NEITHER component pass alone would catch. Three classes of cross-cutting issue: (1) where the argument's coherence depends on frame-imports that are themselves contested (the argument is internally consistent within the frame; the frame is doing load-bearing work that the coherence pass treated as background); (2) where coherence-failures track frame-substitutions across claims (the argument shifts from one frame to another between claims, and the apparent coherence-failure is actually frame-shifting masquerading as inference); (3) where motte-and-bailey-style structure operates across multiple claims (an arguer alternates between a defensible 'motte' claim and a desirable 'bailey' claim — see Caveats and Open Debates §D2 on the Shackel doctrinal usage vs. wider fallacy-label usage). Integration-failure (concatenating findings rather than integrating them) is a failure mode (CQ1 of argument-audit). Where a cross-cutting issue is identified, name it specifically: which inferential moves are involved, which frame-imports, what structural pattern."

**Output format:**

```yaml
cross_cutting_integration:
  coherence_depends_on_contested_frame_imports:
    - issue_id: CI1
      inferential_moves_involved: "<list>"
      frame_imports_involved: "<list>"
      description: "<one paragraph — argument is consistent within frame but frame is doing load-bearing work>"
      what_the_audit_neither_pass_caught_alone: "<the cross-cutting insight>"
  coherence_failures_tracking_frame_substitutions:
    - issue_id: CI2
      claims_involved: "<list>"
      frame_substitution_pattern: "<from frame F1 to frame F2 between claims>"
      apparent_coherence_failure: "<what coherence-audit flagged>"
      reframed_as_frame_shifting: "<what the integration reveals>"
  multi_claim_structural_moves:
    - issue_id: CI3
      structural_move_name: "<motte-and-bailey | other multi-claim move>"
      motte_claim: "<defensible — what the arguer retreats to>"
      bailey_claim: "<desirable — what the arguer wants to establish>"
      alternation_observed: "<where in the artifact the alternation occurs>"
      shackel_or_wider_label: "<see Caveats §D2 — note doctrinal vs. fallacy-label usage>"
      warranted_or_label_only: "<is the structural claim warranted with multi-claim evidence, or label-slapped on a single move>"
```

**Quality gates:**
- At least one cross-cutting issue surfaced (CQ1: integration-failure means none surfaced).
- Cross-cutting issues are integrative (require both frame and coherence findings to detect).
- Where motte-and-bailey is invoked, the structural move is named with multi-claim evidence (Shackel doctrinal usage), not slapped as a label on a single move (CQ4: fallacy-labeling-without-warrant).

---

### Synthesis Stage 3 — Integrated Audit Document

**Type:** dialectical-resolution

**Inputs:** Synthesis Stage 1 (frame-coherence merge), Synthesis Stage 2 (cross-cutting integration)

**Synthesis prompt (orchestrator → model):**
> "Produce the final integrated Argument Audit Report. Structure: (1) argument summary (the artifact's claims and structure, charitably reconstructed). (2) Per-claim coherence findings (from Stage 2 + Synthesis Stage 1). (3) Frame-surfacing findings (from Stage 1 + Synthesis Stage 1). (4) Cross-cutting issues (from Synthesis Stage 2 — the unique product of the molecular pass). (5) Named fallacies and argumentative moves (from Stage 2; for motte-and-bailey or other multi-claim moves, integrate Synthesis Stage 2's structural specification with debate notes per §D2). (6) Overall argument-soundness assessment (argument-wrong vs. conclusion-wrong honored; the audit is conclusion-agnostic). (7) Residual uncertainties (what would change the assessment). (8) Confidence map per finding. The audit's verdict integrates both lenses — sliding into stance-bearing evaluation (advocacy or rejection) is out of scope for this mode; if the audit surfaces something that warrants stance-bearing follow-up, flag the handoff to T15 modes (steelman, balanced-critique, the red-team modes) rather than performing it."

**Output format:** see OUTPUT CONTRACT below.

**Quality gates:**
- Audit integrates four sections, not parallel concatenations.
- Cross-cutting issues are featured (these are what AAA delivers beyond single-component passes).
- Argument-wrong vs. conclusion-wrong honored.
- Stance-bearing follow-up flagged but not performed (mode is neutral).
- Confidence map per finding.
- Where Debate D2 is invoked (motte-and-bailey), the relevant Caveat is referenced.

---

## OUTPUT CONTRACT — Final Artifact Template

```markdown
[AAA — Argument Audit]

# Argument Audit for <artifact title or one-line description>

## Executive Summary
- **Artifact:** <one-sentence — what's being audited>
- **Audit focus:** <focal claim or conclusion>
- **Operative frame(s):** <named in alternative-comparable vocabulary>
- **Argument soundness assessment:** <argument-as-given establishes / does not establish its conclusion>
- **Cross-cutting issue highlight:** <one-sentence — the unique molecular finding>
- **What this audit does NOT do:** Stance-bearing evaluation (steelman or the red-team modes) is out of scope.

## 1. Argument Summary
[Charitable reconstruction of the argument with implicit premises surfaced. Toulmin-structured per inferential move.]

## 2. Per-Claim Coherence Findings
[For each inferential move:]
- **Move M_n:**
  - Claim: <>
  - Data: <>
  - Warrant (surfaced): <>
  - Backing: <>
  - Qualifier: <>
  - Rebuttal: <>
  - Holds or fails: <>
  - Reasoning: <>
  - Frame imports bearing on this move: <from Synthesis 1 — which frame imports are doing analytical work here>

## 3. Frame-Surfacing Findings
- **Operative frame(s):** <named with one-sentence characterizations>
- **Lakoff metaphor inventory:** <quoted text + source-domain → target-domain mappings + entailments>
- **Goffman primary framework and keyings:** <natural/social; keying type; fabrication if applicable>
- **Entman four functions per frame:**
  | Frame | Problem Definition | Causal Interpretation | Moral Evaluation | Treatment Recommendation |
  |-------|---------------------|----------------------|------------------|--------------------------|
  | A | ... | ... | ... | ... |
- **Selection and salience inventory:**
  - Included and emphasized: <list>
  - Excluded or downplayed: <list — what's silent>
- **Presupposition and nominalization audit:** <quoted text per finding>
- **Counterframe:** <what would the issue look like under an alternative frame>

## 4. Cross-Cutting Issues
[The unique product of the molecular pass — issues neither component alone would catch:]

### 4a. Coherence Depends on Contested Frame Imports
- **Issue CI1:** <description — argument is internally consistent within the frame; the frame is doing load-bearing work>
  - Inferential moves involved: <list>
  - Frame imports involved: <list>
  - What this means: the argument's soundness is conditional on accepting the frame; under a counterframe the argument may not hold.

### 4b. Coherence Failures Tracking Frame Substitutions
- **Issue CI2:** <description — argument shifts from frame F1 to frame F2 between claims; apparent coherence-failure is actually frame-shifting>
  - Claims involved: <list>
  - Frame substitution pattern: <>

### 4c. Multi-Claim Structural Moves
- **Issue CI3:** <if motte-and-bailey or other multi-claim move detected — see §6 Caveats §D2>
  - Motte claim (defensible): <>
  - Bailey claim (desirable): <>
  - Alternation observed: <where in the artifact>
  - Doctrinal (Shackel) vs. fallacy-label usage: <which fits this case>

## 5. Named Fallacies and Argumentative Moves
[Each fallacy with full structural specification:]
- **<Fallacy name>:** quoted text / inferential move / violated principle / reason-it-fails-here
  - For motte-and-bailey: see §4c and Caveats §D2.

## 6. Overall Argument Soundness Assessment
- **Argument-as-given assessment:** establishes / does not establish its conclusion because <structural reason>.
- **Conclusion-truth (independent of audit):** the conclusion may still be true; this audit does not adjudicate truth.
- **Where stance-bearing follow-up is warranted:** <flag handoff to T15 modes (steelman / balanced-critique / red-team-assessment / red-team-advocate) — but do not perform here>.

## 7. Residual Uncertainties
- <empirical questions whose answers would shift findings>
- <interpretive questions about what the artifact intends>
- <where the audit's confidence is bounded>

## 8. Confidence Map
| Finding | Confidence | Reason |
|---------|------------|--------|
| Operative frame identification | high / medium / low | <whether frame-imports are explicit in artifact> |
| Toulmin warrant for Move M2 | ... | <whether warrant is explicit or reconstructed> |
| Cross-cutting Issue CI1 | ... | <whether load-bearing claim about frame is well-supported> |
| Motte-and-bailey invocation | ... | <whether multi-claim evidence supports doctrinal claim or only single-move label> |
```

## WORKED EXAMPLE WALKTHROUGH

**Opening prompt (user):** *"I keep encountering arguments in tech policy debates that 'AI is just statistics' to defuse safety concerns about powerful systems. Audit one such argument: [op-ed text where author repeatedly says 'these models are just curve-fitting on patterns' and 'predictions of catastrophe rest on confused metaphysics about computation'].*"*

**Stage 1 output (frame-audit, full):**
- Operative frames:
  - Frame A: "Models-as-statistics" — characterized as a deflationary frame: AI capabilities are the natural and expected consequence of large-scale curve-fitting, with no qualitative novelty requiring new safety frameworks.
  - Frame B (counterframe surfaced for comparison): "Models-as-cognitive-systems" — emergent behaviors warrant analysis at the level of cognitive processes, not just statistical machinery.
- Lakoff metaphor inventory: "MODELS ARE CURVE-FITTERS" (source domain: regression analysis; target domain: AI inference); "PREDICTIONS OF CATASTROPHE ARE METAPHYSICS" (source domain: confused philosophical speculation; target domain: empirical safety arguments).
- Goffman primary framework: technical-redoing — the argument re-keys safety discourse into the technical-statistical frame, treating safety claims as confused category errors when stated in cognitive vocabulary.
- Entman four functions for Frame A:
  - Problem definition: confused public discourse about AI capabilities.
  - Causal interpretation: poor public understanding of how ML actually works.
  - Moral evaluation: clarity is good; speculation is bad.
  - Treatment recommendation: educate the public that "it's just statistics."
- Selection and salience: included = curve-fitting metaphor, references to training data, statistical interpretation of outputs. Excluded = emergent capabilities not predicted by training objective; in-context learning behavior; capability gains from scaling that surprised researchers.
- Presupposition audit: "models are just X" presupposes there is a stable nature of "the model" independent of capability scaling; "confused metaphysics" presupposes safety arguments rest on metaphysical claims rather than empirical observations of model behavior.
- Counterframe: "Models-as-cognitive-systems" — under this frame, the same systems are described in terms of capabilities, generalization, in-context reasoning, and the safety question becomes empirical: do these capabilities scale to dangerous regimes?

**Stage 2 output (coherence-audit, full):**
- Charitable reconstruction: the argument's strongest version: "Concerns about AI catastrophe rest on attributing cognition to systems whose actual operation is statistical pattern-matching; recognizing this dissolves the apparent threat."
- Toulmin breakdown:
  - Move M1: Claim "AI capabilities are statistical pattern-matching." Data: training process is gradient descent on loss function. Warrant: training mechanism determines the nature of the system. Backing: standard ML textbook treatments. Qualifier: implicit (claim is universal). Rebuttal: implicit (none acknowledged). Move holds within frame; warrant is contestable (training mechanism does not necessarily exhaust system properties — the warrant assumes a level-collapse).
  - Move M2: Claim "Catastrophe predictions rest on confused metaphysics about computation." Data: critics use cognitive vocabulary. Warrant: cognitive vocabulary applied to statistical systems is category error. Backing: appeals to common technical understanding. Move fails: the warrant smuggles in the conclusion (that the systems are not appropriately described in cognitive terms is precisely what's at issue).
  - Move M3: Claim "Therefore safety concerns are misplaced." Data: M1 + M2. Warrant: clarifying the nature of systems dissolves safety concerns about them. Move fails partially: even granting M1 and M2, safety-relevant capabilities can exist independent of how the underlying mechanism is characterized.
- Named fallacies:
  - Begging the question (Move M2): the warrant ("cognitive vocabulary applied to statistical systems is category error") presupposes the conclusion (the systems are not cognitive in any safety-relevant sense).
  - Genetic fallacy (implicit across moves): inferring properties of the system from properties of the training process; the system's properties at inference time are not exhaustively determined by the training mechanism.
- Structural coherence failures not in named-fallacy taxonomy:
  - Premise smuggling: the implicit premise "if a system can be described statistically, it cannot have cognitive capabilities" is load-bearing but unstated.
  - Scope shift: between Move M1 (technical claim about mechanism) and Move M3 (safety claim about consequences) the scope shifts from mechanism to capability without acknowledgment.
- Argument-wrong vs. conclusion-wrong: this argument does not establish its conclusion (safety concerns are misplaced); the conclusion may still be true (perhaps safety concerns ARE misplaced for independent reasons), but this argument's structure does not warrant the conclusion.

**Synthesis Stage 1 (frame-coherence merge):**
- Move M1's warrant ("training mechanism determines nature of system") is doing analytical work that the "models-as-statistics" frame supports but is not independently justified. Under the counterframe ("models-as-cognitive-systems"), the same data (training is gradient descent) does not warrant the same claim (capabilities are nothing but pattern-matching).
- Move M2's warrant ("cognitive vocabulary is category error") is the frame itself, deployed inside the argument to defeat the alternative frame.
- Frame import "MODELS ARE CURVE-FITTERS" influences M1, M2, M3 — it is the load-bearing frame doing most of the argumentative work; the inferential moves are largely vehicles for frame-deployment rather than independent inferences.

**Synthesis Stage 2 (cross-cutting integration):**
- **CI1: Coherence depends on contested frame import.** Argument's internal consistency holds within the "models-as-statistics" frame; under the counterframe, M1's warrant fails and the argument collapses. The coherence-audit alone would flag M2 and M3 as fallacious; it would not articulate that M1's apparent soundness is frame-conditional.
- **CI2: No clear frame-substitution across claims** in this artifact (the frame is consistent throughout); this cross-cutting issue does not apply here.
- **CI3: Motte-and-bailey-style structure detected.**
  - Motte claim (defensible): "Training is gradient descent on a loss function" (true; uncontroversial; technical).
  - Bailey claim (desirable): "Therefore safety concerns about advanced model capabilities are confused metaphysics" (substantive; contested; carries policy implications).
  - Alternation observed: when challenged on the bailey, the argument retreats to the motte ("we're just describing how the systems work"); when extending the argument's reach, it advances to the bailey ("therefore safety concerns are misplaced").
  - Per Caveats §D2: this fits Shackel's doctrinal usage — the argumentative position is a structure of motte-and-bailey, not a single inferential move. Multi-claim evidence (the alternation pattern across the op-ed) supports the doctrinal characterization. The wider fallacy-label usage would also apply to a single-move retreat under challenge, but that is not the analysis here.

**Synthesis Stage 3 (integrated audit document):**

[Final Argument Audit Report follows OUTPUT CONTRACT template.]

Key integrated findings:
- The argument's coherence is frame-conditional — it holds within the "models-as-statistics" frame but does not hold under the "models-as-cognitive-systems" counterframe. This is the central cross-cutting issue.
- The argument exhibits motte-and-bailey doctrinal structure (per Shackel) — the defensible motte (training is gradient descent) is repeatedly used to defend the substantive bailey (safety concerns are confused metaphysics).
- Specific named fallacies (begging the question on M2, genetic fallacy across moves) are real but secondary to the cross-cutting frame-coherence issue.
- Argument-as-given does not establish its conclusion. Conclusion-truth (whether safety concerns are well-founded) is independent of this audit and would require T15 stance-bearing analysis (steelman of the frame; red-team-assessment of the counterframe) to address.
- Stance-bearing follow-up is warranted but out of AAA scope: route to balanced-critique or steelman in T15.

## CAVEATS AND OPEN DEBATES

### D2 — Motte-and-Bailey: Fallacy or Doctrine? (Mode-Carried Debate)

Shackel (2005, "The Vacuity of Postmodernist Methodology") introduced the term *motte-and-bailey* as a **doctrinal characterization** — a structural feature of certain argumentative positions in which an arguer alternates between a defensible "motte" (modest claim) and a desirable "bailey" (ambitious claim) when challenged. Shackel's preferred usage frames motte-and-bailey as a *characterization of a doctrine's structure*, not as a fallacy committed in a single inferential step.

In wider usage (online discourse, popular argumentation guides), the term has come to function as a **fallacy label** applied to single moves where an arguer retreats from an ambitious claim under pressure.

This mode operates without adjudicating the debate. When motte-and-bailey is invoked by AAA:

- The audit names the structural move in the argument's terms — which claim is motte, which is bailey, where the alternation occurs (if observed across multiple claims).
- The audit notes whether Shackel's doctrinal usage (multi-claim alternation pattern) or the wider fallacy-label usage (single-move retreat) best fits the case.
- Consumers seeking a stricter Shackel-aligned reading should treat motte-and-bailey invocations as doctrinal characterizations requiring multi-claim evidence; consumers using the wider sense may accept single-move applications.

The framework's CQ4 (fallacy-labeling-without-warrant) requires that any motte-and-bailey invocation specify the structural move, not just attach the label. When multi-claim evidence is available, the doctrinal usage is preferred; when only single-move evidence is available, the audit should explicitly note that the wider fallacy-label usage is being applied and that the doctrinal usage would require additional evidence.

Citations: Shackel 2005; cf. wider discussion in popular argumentation literature.

### Composition limit — stance integrity

AAA is stance-suspending (frame-audit) + stance-neutral (coherence-audit). Sliding into stance-bearing evaluation (advocacy, attack, recommendation) is out of scope. When the audit surfaces something that warrants stance-bearing follow-up, flag the handoff (to T15 steelman / balanced-critique / red-team-assessment / red-team-advocate) rather than performing it. This is honored in the OUTPUT CONTRACT § 6 ("where stance-bearing follow-up is warranted") rather than producing the follow-up here.

### Composition limit — propaganda boundary

Where the artifact is propaganda or persuasion-engineered (Stanley-style strategic deployment of frames + intentional inferential trickery), AAA's stance-suspending posture may be insufficient. The escalation_signals.sideways in the mode spec routes such cases to `propaganda-audit`, the T1 specificity-specialized + adversarial-stance variant. AAA should flag the routing recommendation when propaganda indicators are present rather than producing a stance-suspending audit on a stance-bearing object.

### When to escalate sideways or de-escalate

- **Sideways to propaganda-audit:** artifact is propaganda or persuasion-engineered; Stanley-influenced specialized variant applies.
- **Sideways to T9 modes:** if the audit reveals the dispute is really about which paradigm is correct (rather than which argument coheres), route to frame-comparison or worldview-cartography.
- **Downward to coherence-audit or frame-audit:** if user has time pressure or the audit can be productively narrowed (internal-consistency only or frame-surfacing only).

## QUALITY GATES (overall)

- Both component passes ran (frame-audit and coherence-audit).
- Cross-cutting integration surfaces issues neither component caught alone (CQ1: integration-failure prevented).
- Frame-imports identified concretely with which premise carries which import (CQ2: frame-import-vagueness prevented).
- Coherence findings grounded in specific claim-pairs and inference steps (CQ3: coherence-impressionism prevented).
- Named fallacies (especially motte-and-bailey) warranted with structural specificity (CQ4: fallacy-labeling-without-warrant prevented; debate D2 referenced where applicable).
- Argument-wrong vs. conclusion-wrong honored.
- Stance-bearing follow-up flagged but not performed.
- Confidence map populated per finding.
- The four critical questions of `argument-audit` are addressed.

## RELATED MODES AND CROSS-REFERENCES

- **Paired mode file:** `Modes/argument-audit.md`
- **Component mode files:**
  - `Modes/frame-audit.md` (Stage 1)
  - `Modes/coherence-audit.md` (Stage 2)
- **Sibling Wave 4 modes:** `Modes/decision-architecture.md` (T3), `Modes/worldview-cartography.md` (T9) — share the depth-molecular composition pattern.
- **Sideways escalation target:** `Modes/propaganda-audit.md` (T1 specificity-specialized + adversarial-stance).
- **Stance-bearing follow-up modes (T15):** steelman, balanced-critique, the red-team modes (for evaluation downstream of AAA).
- **Territory framework:** `Framework — Argumentative Artifact Examination.md`
- **Lens dependencies:** walton-argumentation-schemes (required), lakoff-framing (optional), shackel-motte-and-bailey (optional, when motte-and-bailey is in play; carries Debate D2), toulmin-model (via coherence-audit), entman-framing-functions (via frame-audit), goffman-frame-analysis (via frame-audit), kahneman-tversky-bias-catalog (foundational).

*End of Argument Audit Analysis Framework.*
