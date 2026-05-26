---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Coherence Audit

```yaml
# 0. IDENTITY
mode_id: coherence-audit
canonical_name: Coherence Audit
suffix_rule: analysis
educational_name: argument coherence audit (Toulmin model + fallacy taxonomy)

# 1. TERRITORY AND POSITION
territory: T1-argumentative-artifact-examination
gradation_position:
  axis: depth
  value: light
  stance_axis_value: neutral
adjacent_modes_in_territory:
  - mode_id: frame-audit
    relationship: depth-light + stance-suspending sibling (built Wave 2)
  - mode_id: propaganda-audit
    relationship: specificity-specialized + adversarial-stance sibling (built Wave 2)
  - mode_id: argument-audit
    relationship: depth-molecular sibling (composes coherence + frame + propaganda; Wave 4)
  - mode_id: position-genealogy
    relationship: specificity-sibling (stance-historical; gap-deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "want to know whether this argument actually holds together"
    - "the conclusion sounds right but I can't tell if the reasoning supports it"
    - "want a structural check on premises-to-conclusion inferential moves"
    - "suspect there's a coherence gap somewhere but don't want a propaganda or frame reading"
    - "want a neutral inferential audit, not an attack"
  prompt_shape_signals:
    - "coherence audit"
    - "fallacy check"
    - "fallacy detection"
    - "inferential audit"
    - "Toulmin"
    - "warrant"
    - "premises and conclusion"
    - "does this argument hold up"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants neutral structural assessment of premises-to-conclusion inferential moves on a single argumentative artifact"
    - "user wants Toulmin reconstruction (claim, data, warrant, backing, qualifier, rebuttal) plus fallacy-taxonomy check"
    - "user wants the audit conclusion-agnostic (the argument fails, but the conclusion may still be true)"
  routes_away_when:
    - "user wants frame-surfacing rather than inferential check" → frame-audit
    - "user suspects propaganda specifically" → propaganda-audit
    - "user wants integrated coherence + frame + propaganda synthesis" → argument-audit (Wave 4)
    - "user wants to weigh competing hypotheses against evidence (ACH-style)" → competing-hypotheses (T5)
    - "user wants steelman or red-team-assessment / red-team-advocate evaluation of the artifact as a proposal" → T15 modes
when_not_to_invoke:
  - "Artifact is not argumentative (raw data, narrative, instructions without claims)" → other territory
  - "User wants to evaluate competing hypotheses against evidence" → competing-hypotheses (T5)
  - "User wants to evaluate the artifact as a proposal with adopted stance" → T15 modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: neutral

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [argumentative_artifact, focal_claim_or_conclusion]
    optional: [reconstruction_charity_level, dialogue_type_walton, suspected_fallacy_classes, prior_audit_reports]
    notes: "Applies when user supplies the artifact plus the focal conclusion and optionally the dialogue context (persuasion / inquiry / negotiation / deliberation)."
  accessible_mode:
    required: [argumentative_artifact]
    optional: [what_seems_off, the_part_user_wants_focused_on]
    notes: "Default. Mode identifies the focal claim from the artifact and applies dialectical-charity reconstruction before audit."
  detection:
    expert_signals: ["Toulmin", "warrant", "backing", "qualifier", "rebuttal", "fallacy", "Walton", "argumentation scheme", "critical questions", "pragma-dialectics", "enthymeme", "modus tollens", "affirming the consequent", "begging the question"]
    accessible_signals: ["does this hold up", "is the reasoning sound", "what's wrong with this argument", "fallacy check"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you paste the argument and tell me roughly which conclusion you want me to audit the support for?'"
    on_underspecified: "Ask: 'Are you noticing something specific that doesn't follow, or do you want a structural sweep across all the inferential moves?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the audit performed charitable reconstruction first — surfacing implicit premises (enthymemes), resolving textual ambiguity in the speaker's favor, and identifying the strongest version of the argument actually present — before flagging any fallacy?"
    failure_mode_if_unmet: uncharitable-reconstruction
  - cq_id: CQ2
    question: "Has the audit decomposed the argument into Toulmin elements (claim, data, warrant, backing, qualifier, rebuttal) per inferential move, surfacing the warrants explicitly so that the inferential move can be examined?"
    failure_mode_if_unmet: warrant-blindness
  - cq_id: CQ3
    question: "When fallacies are named, has each been substantiated with (a) the specific quoted text, (b) the inferential move identified, (c) the principle the move violates, and (d) the reason the move fails *here* (not just in the abstract) — to prevent name-without-structure misapplication?"
    failure_mode_if_unmet: name-without-structure
  - cq_id: CQ4
    question: "Has the audit clearly separated 'this argument as given does not establish its conclusion' from 'the conclusion is false' — refusing to make the latter claim absent independent grounds (the fallacy fallacy / argumentum ad logicam)?"
    failure_mode_if_unmet: argument-conclusion-conflation
  - cq_id: CQ5
    question: "Has the audit looked beyond named fallacies for structural coherence failures (premise smuggling, scope shift, definitional drift, unstated load-bearing assumptions, enthymeme failure) — given that most actual argumentative weakness lives in unnamed structural failures rather than in the named-fallacy taxonomy?"
    failure_mode_if_unmet: named-fallacy-only-reading

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: uncharitable-reconstruction
    detection_signal: "Audit flags fallacies in the surface text without first attempting a charitable reconstruction that surfaces implicit premises and resolves textual ambiguity in the speaker's favor."
    correction_protocol: re-dispatch
  - name: warrant-blindness
    detection_signal: "Audit examines premises and conclusion without surfacing the warrant (Toulmin) that connects them; inferential failure cannot be examined without the warrant in view."
    correction_protocol: re-dispatch
  - name: name-without-structure
    detection_signal: "Fallacy claim invokes a label without specifying which inferential move fails, the principle it violates, and why it fails here."
    correction_protocol: re-dispatch
  - name: argument-conclusion-conflation
    detection_signal: "Audit treats demonstrating the argument as fallacious as evidence the conclusion is false (the fallacy fallacy / argumentum ad logicam)."
    correction_protocol: flag
  - name: named-fallacy-only-reading
    detection_signal: "Audit checks against the named-fallacy taxonomy but does not look for unnamed structural failures (premise smuggling, scope shift, definitional drift, unstated load-bearing assumptions, enthymeme failure)."
    correction_protocol: re-dispatch
  - name: asymmetric-rigor
    detection_signal: "Audit applies different standards to comparable inferential moves; severity grading is uneven across the artifact in ways not justified by the moves' structures."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - toulmin-model
    - walton-schemes-and-critical-questions
  optional:
    - hamblin-fallacies-standard-treatment-critique (when named-fallacy invocations require theoretical situating)
    - pragma-dialectics-rules-for-critical-discussion (when the failure mode is rule-violation rather than form-violation)
    - copi-informal-fallacy-taxonomy (when the artifact maps cleanly to canonical named fallacies)
    - alexander-isolated-demands-for-rigor (when asymmetric standards are at issue)
    - shackel-motte-and-bailey (when multi-turn commitment-tracking is in scope; default home for D2 is argument-audit Wave 4)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: argument-audit
    when: "Audit reveals coherence problems but also frame-manipulation and possible propaganda function; molecular synthesis is needed (Wave 4)."
  sideways:
    target_mode_id: frame-audit
    when: "On reflection the coherence problems are downstream of frame work; surfacing the frame is the right operation."
  downward:
    target_mode_id: null
    when: "Coherence Audit is already the lightest atomic mode in T1 for inferential-structure assessment."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Coherence Audit is the precision with which (1) charitable reconstruction surfaces implicit premises and resolves textual ambiguity in the speaker's favor, (2) Toulmin elements (claim, data, warrant, backing, qualifier, rebuttal) are decomposed per inferential move, (3) fallacy claims (when made) are substantiated with quoted text + identified inferential move + violated principle + reason-it-fails-here, and (4) unnamed structural coherence failures (premise smuggling, scope shift, definitional drift, unstated load-bearing assumptions, enthymeme failure) are surfaced beyond the named-fallacy taxonomy. A thin pass produces a fallacy-list against surface text; a substantive pass reconstructs the strongest reading of the argument, surfaces warrants, and audits the strongest version's inferential structure with both named-fallacy and structural-failure lenses. Test depth by asking: would a defender of the argument recognize the audit as auditing the argument they actually made, rather than a weaker straw version?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning across the three traditions of fallacy theory before narrowing: (a) Walton's pragmatic / dialectical theory (fallacy depends on dialogue type — persuasion, inquiry, negotiation, deliberation, information-seeking, eristic); (b) pragma-dialectics (fallacies as violations of rules for critical discussion); (c) Hintikka's question-dialogue (fallacies as illegitimate moves in question-answer games). Scan also: formal vs. informal fallacy taxonomy (formal is rare in natural discourse; informal dominates); informal-fallacy families (relevance / presumption / ambiguity / rhetorical-strategic); structural failures not named in the taxonomy (premise smuggling, scope shift, definitional drift). Breadth markers: the audit has surveyed at least the formal/informal/structural cleavages and has applied the dialogue-type lens (Walton) to dialectical context before producing findings.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Coherence Audit is a neutral inferential audit of an argumentative artifact — does the argument as given actually establish its conclusion? It applies Toulmin reconstruction (claim, grounds, warrant, backing, qualifier, rebuttal per inferential move) and Walton's argumentation-scheme critical questions, layers fallacy-taxonomy and structural-failure lenses, and produces a verdict that separates argument-soundness from conclusion-truth. It is distinct from frame-audit (frame-surfacing rather than inferential check), propaganda-audit (specifically adversarial-stance, Stanley-influenced), and argument-audit (molecular composition of coherence + frame + propaganda). It is conclusion-agnostic by design — the argument may fail while the conclusion remains true.

**Procedure.**

1. Open with a charitable reconstruction — surface implicit premises (enthymemes), resolve textual ambiguity in the speaker's favor, identify the strongest version of the argument actually present.
2. Decompose each inferential move into Toulmin elements — claim, grounds, warrant (explicit or reconstructed), backing, qualifier, rebuttal conditions. Render implicit-component absences explicitly ("no rebuttal conditions considered") as findings.
3. Classify moves that instantiate Walton schemes (Expert Opinion, Position to Know, Cause to Effect, Sign, Analogy, Practical Reasoning, Slippery Slope, etc.) and audit each scheme's critical questions with verdicts (satisfied / defeated / unaddressed).
4. Substantiate any named fallacy with all four parts — quoted text, identified inferential move, violated principle, reason it fails *here* (not just in the abstract). Bare labels do not survive.
5. Sweep for structural coherence failures beyond the named-fallacy taxonomy — premise smuggling, scope shift, definitional drift, unstated load-bearing assumption, enthymeme failure.
6. Verdict per inferential move — holds / fails / partially-holds, with the load-bearing structural reason.
7. Separate argument-wrong from conclusion-wrong explicitly — "this argument as given does not establish its conclusion because [structural reason]; the conclusion may still be true." This is the mode's signature posture; it lands once at the corpus level.
8. Check symmetric rigor — apply the same standards to comparable inferential moves across the artifact; asymmetric severity grading is a quality-gate failure.
9. Assign confidence per finding (warrant reconstruction, fallacy claim, structural failure) with explicit basis.

**Goal.** Produce a structured coherence audit organized per inferential move with Toulmin decomposition, Walton-scheme critical-question audit, fallacy substantiation, structural-failure sweep, and the argument-wrong-vs-conclusion-wrong verdict separated cleanly.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — charitable reconstruction first.** Has the audit performed charitable reconstruction first — surfacing implicit premises, resolving textual ambiguity in the speaker's favor — before flagging any fallacy? Failure mode if unmet: `uncharitable-reconstruction`.
- **CQ2 — Toulmin warrants surfaced.** Has the audit decomposed the argument into Toulmin elements per inferential move, surfacing the warrants explicitly so the inferential move can be examined? Failure mode if unmet: `warrant-blindness`.
- **CQ3 — fallacy substantiation.** When fallacies are named, has each been substantiated with quoted text, inferential move, violated principle, and reason it fails *here*? Failure mode if unmet: `name-without-structure`.
- **CQ4 — argument vs conclusion separated.** Has the audit clearly separated "this argument as given does not establish its conclusion" from "the conclusion is false," refusing the latter absent independent grounds? Failure mode if unmet: `argument-conclusion-conflation`.
- **CQ5 — structural-failure sweep.** Has the audit looked beyond named fallacies for structural coherence failures (premise smuggling, scope shift, definitional drift, unstated load-bearing assumptions, enthymeme failure)? Failure mode if unmet: `named-fallacy-only-reading`.

A passing output reconstructs charitably, decomposes by Toulmin per move with warrants surfaced, substantiates any named fallacy with the four-part structure, separates argument-soundness from conclusion-truth at the corpus level, surveys both named-fallacy and structural-failure lenses, and applies standards symmetrically across the artifact.

**Named failure modes.**

- *uncharitable-reconstruction* — audit flags fallacies in surface text without first attempting a charitable reconstruction.
- *warrant-blindness* — audit examines premises and conclusion without surfacing the warrant (Toulmin) that connects them.
- *name-without-structure* — fallacy claim invokes a label without specifying which inferential move fails, the principle it violates, and why it fails here.
- *argument-conclusion-conflation* — audit treats demonstrating the argument as fallacious as evidence the conclusion is false (the fallacy fallacy / argumentum ad logicam).
- *named-fallacy-only-reading* — audit checks against the named-fallacy taxonomy but does not look for unnamed structural failures.
- *asymmetric-rigor* — audit applies different standards to comparable inferential moves; severity grading is uneven across the artifact.

## REVISION GUIDANCE

Revise to perform charitable reconstruction first where the draft has flagged fallacies in surface text without surfacing implicit premises. Revise to surface Toulmin warrants where the draft examines premises-and-conclusion without the warrant in view. Revise to substantiate any fallacy claim with quoted text + inferential move + violated principle + reason-it-fails-here. Revise to separate argument-soundness from conclusion-truth where the draft slides between them. Revise to add the structural-failure sweep (premise smuggling, scope shift, definitional drift, enthymeme failure) where the audit operates only against the named-fallacy list. Resist revising toward decisive verdicts on the conclusion's truth — the mode is conclusion-agnostic by design; the appropriate verdict is "this argument as given does not establish its conclusion; the conclusion may still be true."

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **atoms grouped per inferential move**, with Toulmin slots filled and Walton scheme classifications attached where the move maps to a named presumptive scheme. The structure is:

1. **Charitable reconstruction.** The agreed-on strongest version of the argument actually present in the text, with implicit premises surfaced. If the two streams produced different reconstructions, surface the disagreement as a real tension — the corpus carries both reconstructions with the disagreement named, not a blended compromise.

2. **Per inferential move** (sequenced as the argument unfolds), the surviving atoms are:
   - **Toulmin slots** — claim, grounds, warrant (explicit or reconstructed), backing (present or absent atom), qualifier (present or absent atom), rebuttal conditions (considered or unconsidered atom). Implicit-component absences are themselves atoms — "the warrant is implicit; reconstructed as X" or "no rebuttal conditions are stated; the inference is being treated as universal" are findings, not gaps.
   - **Walton scheme classification** when the move instantiates a named scheme (Expert Opinion, Position to Know, Cause to Effect, Sign, Slippery Slope, Analogy, Practical Reasoning, etc.) — the scheme name plus the per-critical-question audit (satisfied / defeated / unaddressed).
   - **Named-fallacy atoms** when fallacy claims are made — each carries the four-part substantiation: quoted text, identified inferential move, violated principle, reason-it-fails-here. Bare fallacy labels without all four components do not survive into the corpus.
   - **Structural-failure atoms** for failures beyond the named-fallacy taxonomy — premise smuggling, scope shift, definitional drift, unstated load-bearing assumption, enthymeme failure. Each carries the quoted text and the reason the move fails *here*.

3. **Cross-cutting findings:**
   - **Argument-holds-or-fails per inferential move** — a verdict atom per move, summarizing the audit's structural finding.
   - **Argument-wrong vs conclusion-wrong separation** — the conclusion-agnostic verdict stated once at the corpus level: "this argument as given does not establish its conclusion because [structural reason]; the conclusion may still be true; it is simply not supported by this argument." A single load-bearing atom; it does not appear multiple times in the corpus.
   - **Symmetric-rigor check** — an atom flagging whether the audit applied the same standards to comparable moves, or whether severity-grading is asymmetric.
   - **Confidence per finding** — confidence markers attach to individual atoms (warrant reconstruction, fallacy claim, structural failure). When the two streams assigned different confidences to the same finding, audit conservatism applies — the corpus carries the lower of the two.

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Warrant-paraphrase loops** — both streams reconstruct the same implicit warrant in slightly different wordings. The warrant survives once, in the most precise form.
- **Fallacy-claim duplication with surface-different substantiation** — both streams flag the same fallacy with overlapping evidence quotes and overlapping principle articulations. Union the evidence quotes; pick the most precise principle statement; a single fallacy atom survives.
- **Toulmin-absence restatement** — both streams may note "warrant is implicit, reconstructed as X" or "backing is absent" in slightly different phrasings. A single absence-atom per Toulmin slot per move.
- **Argument-wrong vs conclusion-wrong meta-restatement** — coherence-audit's signature posture surfaces across multiple passages in both streams. Cut to one corpus-level verdict atom; do not preserve every reiteration.
- **Charitable-reconstruction restatement** — when the streams agree, the reconstruction collapses to one atom. When they disagree, the disagreement is a tension, not a duplication.

## VERIFICATION CRITERIA

Verified means: charitable reconstruction precedes any fallacy claim; Toulmin warrants are surfaced per inferential move; every named fallacy is substantiated with quoted text + violated principle + reason-it-fails-here; argument-wrong is explicitly separated from conclusion-wrong; the structural-failure sweep has been performed beyond the named-fallacy taxonomy; severity grading is symmetric across the artifact. The five critical questions are addressable from the output. Confidence per finding accompanies each major claim.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structured coherence audit organized per inferential move**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Charitable reconstruction.** Open with the strongest version of the argument actually present in the text, with implicit premises surfaced. One paragraph of prose, framed as "the argument, as charitably reconstructed:" — the user must see what is being audited before the audit findings.

2. **Per inferential move — Toulmin breakdown.** For each inferential move in the argument (sequenced as the argument unfolds), render a block with these fields:
   - **Claim** — what this move asserts
   - **Grounds** — the data or evidence offered
   - **Warrant** — the inferential rule, explicit or reconstructed (label reconstructed warrants as "warrant (implicit, reconstructed): ...")
   - **Backing** — support for the warrant, or "no backing offered" / "no backing identifiable" when absent
   - **Qualifier** — the strength claimed, or "no qualifier stated; argument offered as certain" when absent
   - **Rebuttal conditions** — circumstances that would defeat the inference, or "no rebuttal conditions considered" when absent

   Render each move's Toulmin block as a small table or as a clean tagged list — whichever the medium supports better. Implicit-component absences are themselves findings; do not omit the "no X offered" lines.

3. **Walton scheme classification — where applicable.** For inferential moves that instantiate a named presumptive scheme (Expert Opinion, Position to Know, Cause to Effect, Sign, Slippery Slope, Analogy, Practical Reasoning, etc.), follow the Toulmin block with the scheme name and the per-critical-question audit. Render each critical question with a verdict tag: **satisfied** / **defeated** / **unaddressed**.

4. **Named fallacies — when present.** Each named fallacy carries the four-part substantiation in this exact shape:
   - **Quoted text:** the specific passage where the fallacy occurs
   - **Inferential move:** which move in the Toulmin breakdown
   - **Violated principle:** what the move does wrong
   - **Reason it fails here:** why this case (not just the abstract pattern) is a fallacy

   Do not label fallacies without all four fields. When there are no named fallacies, write "No named fallacies identified."

5. **Structural coherence failures (beyond the named-fallacy taxonomy).** Each structural failure (premise smuggling, scope shift, definitional drift, unstated load-bearing assumption, enthymeme failure, etc.) carries quoted text and the structural reason for the failure. Render as a list. When none are identified, write "No structural failures identified beyond the named-fallacy sweep."

6. **Argument-holds-or-fails per inferential move.** A summary list keyed to the moves from section 2: for each move, **holds** / **fails** / **partially-holds**, with the load-bearing reason.

7. **Argument-wrong vs conclusion-wrong separation.** The verdict, stated once. When the argument fails, render in this framing: "This argument as given does not establish its conclusion because [structural reason]. The conclusion may still be true — it is simply not supported by this argument." When the argument holds, render as: "This argument as given establishes its conclusion, supported by [specific Toulmin elements]." This section is load-bearing; the mode's conclusion-agnostic posture lands here.

8. **Confidence per finding.** A bulleted list of major claims with confidence markers (high / moderate / low). One bullet per major finding; do not pad with confidence-on-every-sentence.

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- Use code-block, table, or tagged-list format for the Toulmin breakdowns and Walton scheme audits where the medium supports it.
- Quoted passages get inline quotation marks; passage citations get the source phrase verbatim.
- Implicit-component absences are rendered explicitly — not omitted.

## CAVEATS AND OPEN DEBATES

**Debate D1 — Is "fallacy" a property of the argument, or a property of the dialogue in which the argument is made?** The classical (Aristotelian, Copi-textbook) tradition treats fallacy as a property of the argument: an inferential move fails because of its form or because its premises do not support its conclusion, independently of dialogue context. The pragma-dialectical tradition (van Eemeren & Grootendorst) treats fallacy as a violation of rules for critical discussion: the same inferential move can be a legitimate strategic manoeuvre in one dialogue type and a fallacy in another. Walton's pragmatic / dialectical theory occupies a middle position: argumentation schemes carry critical questions whose negative answers can defeat the argument, and the dialogue type (persuasion, inquiry, negotiation, deliberation, information-seeking, eristic) determines which critical questions are in scope. Hamblin's *Fallacies* (1970) opened the debate by exposing the textbook tradition as theoretically degenerate, and the debate has not been settled in the literature. This mode operates without adjudicating: it applies Toulmin reconstruction (warrant-based, neutral on dialogue type) as the primary lens, layers Walton's argumentation-scheme critical questions on top (which carry the dialogue-type sensitivity implicitly), and flags fallacy claims as "the argument as given does not establish its conclusion via this inferential move" rather than as "the speaker has committed [named fallacy] in absolute terms." This treatment is compatible with both the property-of-argument and property-of-dialogue readings while remaining noncommittal about which is correct. Citations: Hamblin 1970 *Fallacies*; Walton 1995 *A Pragmatic Theory of Fallacy*; van Eemeren & Grootendorst 2004 *A Systematic Theory of Argumentation*; Hansen, "Fallacies," *Stanford Encyclopedia of Philosophy*.


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
