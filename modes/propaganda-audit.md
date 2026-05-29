---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Propaganda Audit

```yaml
# 0. IDENTITY
mode_id: propaganda-audit
canonical_name: Propaganda Audit
suffix_rule: analysis
educational_name: propaganda audit (Stanley supporting/undermining + flawed-ideology test)

# 1. TERRITORY AND POSITION
territory: T1-argumentative-artifact-examination
gradation_position:
  axis: specificity
  value: specialized-propaganda
  stance_axis_value: adversarial
adjacent_modes_in_territory:
  - mode_id: coherence-audit
    relationship: depth-light + neutral-stance sibling (built Wave 2)
  - mode_id: frame-audit
    relationship: depth-light + stance-suspending sibling (built Wave 2)
  - mode_id: argument-audit
    relationship: depth-molecular sibling (composes coherence + frame + propaganda; Wave 4)
  - mode_id: position-genealogy
    relationship: specificity-sibling (stance-historical; gap-deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "this feels like propaganda but I want to test that"
    - "looks like it presents itself as embodying an ideal but actually erodes it"
    - "want to know what flawed-ideology premises this artifact relies on"
    - "want to surface the not-at-issue content doing the persuasive work"
    - "the artifact is a manifesto, ad campaign, or political broadcast and I want a structured propaganda diagnostic"
  prompt_shape_signals:
    - "propaganda audit"
    - "is this propaganda"
    - "Stanley test"
    - "supporting vs undermining propaganda"
    - "flawed ideology"
    - "not-at-issue content"
    - "engineering of consent"
    - "manufactured doubt"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants Stanley-style diagnostic on a single artifact suspected of propaganda function"
    - "user wants the supporting / undermining distinction applied with flawed-ideology test"
    - "user is willing to accept the adversarial-stance posture (this is the T1 mode that adopts adversarial reading)"
  routes_away_when:
    - "user wants neutral inferential-structure assessment without adversarial framing" → coherence-audit
    - "user wants frame-surfacing without endorsing or attacking the frame" → frame-audit
    - "user wants integrated coherence + frame + propaganda synthesis" → argument-audit (Wave 4)
    - "user wants to attack the artifact as a proposal rather than as a propaganda artifact" → red-team-assessment / red-team-advocate (T15)
    - "user wants to surface whose interests the artifact serves" → cui-bono (T2)
when_not_to_invoke:
  - "Artifact is an ordinary argumentative text without persuasive-campaign characteristics" → coherence-audit or frame-audit
  - "User wants to evaluate the artifact's interest-pattern (who benefits)" → cui-bono (T2)
  - "User wants to model the artifact as part of an adversarial actor's strategy" → red-team-assessment / red-team-advocate (T15)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: adversarial

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [argumentative_artifact, professed_ideal_or_value, suspected_actual_function]
    optional: [author_or_sponsor_inventory, campaign_context, intertextual_lineage, audience_demographic_target]
    notes: "Applies when user supplies the artifact plus the ideal it claims to embody and the function the user suspects it actually performs."
  accessible_mode:
    required: [argumentative_artifact]
    optional: [why_user_suspects_propaganda, sponsor_or_author_if_known, related_artifacts]
    notes: "Default. Mode infers professed ideals from the artifact and elicits suspected function during execution if not specified."
  detection:
    expert_signals: ["Stanley", "How Propaganda Works", "supporting propaganda", "undermining propaganda", "demagoguery", "flawed ideology", "not-at-issue content", "presupposed content", "Bernays", "Ellul", "Manufacturing Consent", "Herman", "Chomsky", "propaganda model"]
    accessible_signals: ["this looks like propaganda", "feels manipulative", "the ideals don't match the effect", "engineered to manipulate"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you paste the artifact (article, ad, manifesto, broadcast transcript) and tell me what ideal it claims to serve and what you suspect it actually does?'"
    on_underspecified: "Ask: 'What about this artifact triggered the propaganda suspicion — the gap between professed and actual, the staging of consent, the not-at-issue content, or something else?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the audit named the professed ideal of the artifact (the freedom / fairness / security / truth it claims to embody) explicitly, before assessing whether the artifact's function aligns with or erodes that ideal?"
    failure_mode_if_unmet: ideal-omission
  - cq_id: CQ2
    question: "Has the supporting / undermining distinction been applied with evidence — does the artifact use non-rational means to advance the professed ideal (supporting), or does it present itself as embodying the ideal while actually eroding it (undermining)?"
    failure_mode_if_unmet: classification-collapse
  - cq_id: CQ3
    question: "If the artifact is classified as undermining, has the audit identified the specific flawed-ideology premise(s) the audience must hold for the contradiction between professed and actual to remain invisible to them?"
    failure_mode_if_unmet: flawed-ideology-omission
  - cq_id: CQ4
    question: "Has the audit catalogued the not-at-issue content (presuppositions, conventional implicatures, lexical activations) doing the persuasive work, given that propaganda often operates through what is assumed rather than asserted?"
    failure_mode_if_unmet: at-issue-only-reading
  - cq_id: CQ5
    question: "Has the audit distinguished 'this artifact is propaganda' from 'I disagree with this artifact's conclusion' — and avoided treating the audit as a refutation of the artifact's claims (the propaganda-charge fallacy)?"
    failure_mode_if_unmet: propaganda-charge-as-refutation

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: ideal-omission
    detection_signal: "Audit assesses propaganda function without naming the specific ideal the artifact professes; supporting/undermining classification is therefore unevaluable."
    correction_protocol: re-dispatch
  - name: classification-collapse
    detection_signal: "Audit names 'propaganda' without distinguishing supporting (non-rational means for worthy ideal) from undermining (presents-as-embodying-ideal-while-eroding-it)."
    correction_protocol: re-dispatch
  - name: flawed-ideology-omission
    detection_signal: "Audit classifies as undermining without identifying the prior flawed beliefs the audience must hold for the contradiction to remain invisible."
    correction_protocol: re-dispatch
  - name: at-issue-only-reading
    detection_signal: "Audit examines only what the artifact asserts; presupposed and conventionally-implicated content is not catalogued."
    correction_protocol: re-dispatch
  - name: propaganda-charge-as-refutation
    detection_signal: "Audit treats the propaganda diagnosis as evidence the artifact's conclusion is false (a meta-level fallacy of fallacy)."
    correction_protocol: flag
  - name: motive-attribution-without-evidence
    detection_signal: "Audit imputes deliberate manipulative intent to the author/sponsor without textual or contextual evidence; the diagnostic should focus on the artifact's structure and effect, not the author's psychology."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - stanley-propaganda
    - walton-schemes-and-critical-questions
  optional:
    - bernays-engineering-of-consent (when artifact is a PR/advertising campaign)
    - ellul-integration-vs-agitation (when artifact is part of ambient media-environment conditioning)
    - herman-chomsky-five-filter-propaganda-model (when structural-institutional situating is in scope)
    - lakoff-conceptual-metaphor (when lexical-metaphor frame activation is central)
    - cda-fairclough-presupposition-and-nominalization (when grammatical mechanisms carry the not-at-issue content)
    - iyengar-episodic-thematic (when attribution-of-responsibility manipulation is a technique)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: argument-audit
    when: "Audit reveals coherence problems and frame-manipulation alongside propaganda diagnosis; molecular synthesis is needed (Wave 4)."
  sideways:
    target_mode_id: red-team-assessment
    when: "User wants to model the artifact as an adversarial actor's strategic move and stress-test against it (T15). Default to red-team-assessment for own-decision use; route to red-team-advocate when the user is preparing a brief against the artifact for an external audience."
  downward:
    target_mode_id: frame-audit
    when: "On reflection the artifact is doing frame work but not propaganda specifically; stance-suspending frame analysis is the right operation."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Propaganda Audit is the precision with which (1) the professed ideal is named and quoted from the artifact, (2) the actual function is inferred from the artifact's structure and predicted audience uptake, (3) the supporting / undermining classification is evidenced, (4) the flawed-ideology premises required for the contradiction to remain invisible to the audience are identified, and (5) the not-at-issue content (presupposition, conventional implicature, lexical activation) doing the persuasive work is catalogued with quoted text. A thin pass declares "propaganda" and lists rhetorical techniques; a substantive pass shows the gap between professed ideal and actual function, names the prior beliefs the audience must hold for the gap to remain invisible, and inventories the assumed-rather-than-asserted content carrying the work. Test depth by asking: could the artifact's defender (or the artifact's author) recognize the audit as accurate while contesting its evaluative classification?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning the propaganda-tradition layers before narrowing: Bernays (engineering-of-consent / PR-as-symbolic-environment-management); Ellul (integration vs. agitation; ambient cumulative narrowing of the conceivable); Herman & Chomsky (five-filter propaganda model — ownership, advertising, official sources, flak, common-enemy); Stanley (supporting / undermining distinction; flawed-ideology precondition; not-at-issue content). Where applicable, scan also: Lakoff (lexical metaphor activation); CDA (presupposition, nominalization, agent deletion, lexicalization choices); Iyengar (episodic vs. thematic framing for attribution manipulation). Breadth markers: the audit has surveyed at least the Stanley diagnostic plus one structural-context layer (Bernays / Ellul / Herman-Chomsky) and one linguistic-mechanism layer (Lakoff / CDA) before producing findings.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Propaganda Audit is a Stanley-style structured diagnostic of a suspected propaganda artifact: it names the ideal the artifact professes, classifies the artifact as supporting (non-rational means for a worthy ideal) or undermining (presents itself as embodying the ideal while actually eroding it), identifies the flawed-ideology premises required for undermining-class artifacts, and inventories the not-at-issue content (presupposition, conventional implicature, lexical activation) doing persuasive work. It is the adversarial-stance specialized variant in T1, distinct from coherence-audit (neutral inferential-structure assessment) and frame-audit (stance-suspending frame surfacing); it is also distinct from cui-bono (T2 — whose interests the artifact serves) and the red-team modes (T15 — attacking the artifact as a proposal).

**Procedure.**

1. Name the professed ideal — the freedom / fairness / security / truth / dignity the artifact claims to embody, with quoted text from the artifact.
2. Hypothesise the actual function — predicted audience uptake, behavioural consequence, attentional or affective effect, inferred from structure and targeting (not from author psychology).
3. Apply the Stanley supporting / undermining distinction with evidence — supporting deploys non-rational means for a worthy ideal; undermining presents itself as embodying the ideal while eroding it.
4. If undermining, identify the flawed-ideology premises — the prior beliefs the audience must hold for the contradiction between professed and actual to remain invisible to them.
5. Inventory the not-at-issue content — presuppositions, conventional implicatures, lexical activations doing persuasive work, with quoted text and the persuasive effect each produces.
6. Catalogue frame-manipulation techniques (responsibility relocation, loaded terms, episodic framing, presupposition smuggling, naturalization, agent deletion, manufactured-doubt) with quoted artifact evidence.
7. When the artifact is mass-media, situate it through the Herman-Chomsky five-filter model (ownership, advertising, official sources, flak, common-enemy); mark not-applicable when not mass-media.
8. Predict audience uptake — cognitive, affective, behavioural shifts with evidence basis.
9. Preserve the diagnosis-vs-conclusion distinction throughout — the propaganda diagnosis is not a refutation of the artifact's claims.
10. Apply symmetry-discipline — would a structurally-equivalent instance on the other political side be flagged? Per Debate D5 sensitivity.

**Goal.** Produce a Stanley-style propaganda diagnostic that names the professed ideal with quoted text, classifies supporting vs. undermining with evidence, identifies flawed-ideology premises if undermining, inventories not-at-issue content, and keeps the diagnosis distinct from rejection of the artifact's conclusion.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — professed ideal named.** Has the audit named the artifact's professed ideal (the freedom / fairness / security / truth it claims to embody) explicitly before assessing function? Failure mode if unmet: `ideal-omission`.
- **CQ2 — supporting vs undermining classification.** Has the Stanley distinction been applied with evidence — non-rational means for a worthy ideal (supporting) versus presents-as-embodying-while-eroding (undermining)? Failure mode if unmet: `classification-collapse`.
- **CQ3 — flawed-ideology premises identified.** If undermining, has the audit identified the prior beliefs the audience must hold for the contradiction to remain invisible? Failure mode if unmet: `flawed-ideology-omission`.
- **CQ4 — not-at-issue content inventoried.** Has the audit catalogued presupposed and conventionally-implicated content doing persuasive work, not just what the artifact asserts? Failure mode if unmet: `at-issue-only-reading`.
- **CQ5 — diagnosis vs conclusion distinction.** Has the audit avoided treating the propaganda charge as evidence that the artifact's conclusion is false? Failure mode if unmet: `propaganda-charge-as-refutation`.

A passing output names the professed ideal with quoted text, classifies supporting vs. undermining with evidence, identifies flawed-ideology premises if undermining, inventories not-at-issue content with quoted text, and distinguishes the propaganda diagnosis from rejection of the artifact's conclusion.

**Named failure modes.**

- *ideal-omission* — audit assesses propaganda function without naming the specific ideal the artifact professes; supporting/undermining classification is therefore unevaluable.
- *classification-collapse* — audit names "propaganda" without distinguishing supporting (non-rational means for worthy ideal) from undermining (presents-as-embodying-ideal-while-eroding-it).
- *flawed-ideology-omission* — audit classifies as undermining without identifying the prior flawed beliefs the audience must hold for the contradiction to remain invisible.
- *at-issue-only-reading* — audit examines only what the artifact asserts; presupposed and conventionally-implicated content is not catalogued.
- *propaganda-charge-as-refutation* — audit treats the propaganda diagnosis as evidence the artifact's conclusion is false (a meta-level fallacy of fallacy).
- *motive-attribution-without-evidence* — audit imputes deliberate manipulative intent to the author/sponsor without textual or contextual evidence; the diagnostic should focus on the artifact's structure and effect, not the author's psychology.

## REVISION GUIDANCE

Revise to name the professed ideal explicitly where the draft has assessed propaganda function without surfacing it. Revise to disambiguate supporting from undermining where the draft asserts "propaganda" without distinguishing the two structures. Revise to identify flawed-ideology premises where the draft classifies as undermining without saying what the audience must believe. Revise to catalogue not-at-issue content where the audit has examined only what is asserted. Revise to separate the propaganda diagnosis from any claim that the artifact's conclusion is false. Resist revising toward neutrality — the mode is adversarial-stance by design (sensitive Debate D5 in CAVEATS); softening the diagnostic to be evenhanded is a failure mode, not a polish. The adversarial stance is structural to the mode and is what distinguishes it from frame-audit.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Stanley-style propaganda diagnostic atom set: professed-ideal atom with quoted text, hypothesised actual-function atom, supporting-vs-undermining classification with evidence, flawed-ideology-premise atoms (if undermining), not-at-issue-content inventory atoms with quoted text, frame-manipulation-technique atoms, five-filter structural atoms where artifact is mass-media, audience-predicted-uptake atom, and a standing distinction between propaganda diagnosis and conclusion-rejection**. The atoms are:

1. **Professed-ideal atom.** The ideal the artifact claims to embody (freedom, fairness, security, truth, dignity, family values, etc.), named with quoted text from the artifact. Ideal-omission is the named failure mode the consolidator watches for; audits that assess propaganda function without surfacing the professed ideal get reshaped to name it before classification.

2. **Hypothesised actual-function atom.** What the artifact actually does — predicted audience uptake, behavioural consequence, attentional or affective effect. Inferred from the artifact's structure and audience targeting, not from author psychology.

3. **Supporting-vs-undermining classification atom.** The Stanley distinction applied with evidence: `supporting` (non-rational means deployed for a worthy ideal) versus `undermining` (presents itself as embodying the ideal while actually eroding it). Classification-collapse is the named failure mode; "propaganda" asserted without the binary distinction gets reshaped.

4. **Flawed-ideology-premise atoms — if undermining.** Each atom names a prior belief the audience must hold for the contradiction between professed ideal and actual function to remain invisible to them. Flawed-ideology-omission is the named failure mode; undermining classification without identifying these premises gets reshaped.

5. **Not-at-issue-content inventory atoms.** Each atom names: a presupposition, conventional implicature, or lexical activation doing persuasive work, with quoted text and the persuasive effect it produces. At-issue-only-reading is the named failure mode; audits examining only what the artifact asserts (rather than what it assumes) get reshaped to inventory the not-at-issue layer.

6. **Frame-manipulation-technique atoms.** Each atom names one operative technique (responsibility relocation, loaded terms, episodic framing, presupposition smuggling, naturalization, agent deletion, manufactured-doubt, etc.) with quoted text from the artifact.

7. **Five-filter structural atoms — when applicable.** When the artifact is a mass-media product, each filter (ownership, advertising, official sources, flak, common-enemy) is applied with situating evidence. When the artifact is not mass-media, this section is marked `not-applicable` rather than padded.

8. **Audience-predicted-uptake atom.** How the propaganda works on its intended target — what cognitive, affective, or behavioural shift it predicts in the audience, with evidence-basis for the prediction.

9. **Diagnosis-vs-conclusion distinction atom.** A standing atom: the propaganda diagnosis is *not* a refutation of the artifact's claims. Propaganda-charge-as-refutation is the named failure mode; the audit holds the distinction throughout.

10. **Motive-attribution-evidence flag — when applicable.** Where deliberate manipulative intent is imputed to author/sponsor without textual or contextual evidence, the flag is preserved. Motive-attribution-without-evidence is the named failure mode; the diagnostic focuses on structure and effect, not author psychology, unless explicit evidence supports the intent claim.

11. **Asymmetric-application flag — when applicable.** Where streams applied Stanley's apparatus differently to structurally-equivalent left vs. right artifacts (Debate D5 sensitivity), the flag surfaces explicitly.

12. **Confidence per finding.** Each major claim carries confidence with grounding (quoted text, structural inference, lens application).

**Mode-specific bloat patterns to cut:**

- **Ideal omission** — propaganda function assessed without naming the professed ideal.
- **Classification collapse** — "propaganda" asserted without distinguishing supporting from undermining.
- **Flawed-ideology omission** — undermining classification without naming the prior beliefs that hide the contradiction.
- **At-issue-only reading** — what's asserted catalogued; what's presupposed or implicated isn't.
- **Propaganda-charge-as-refutation** — propaganda diagnosis treated as evidence the artifact's conclusion is false. Meta-level fallacy.
- **Motive attribution without evidence** — psychological intent imputed without textual or contextual grounding.
- **Asymmetric application** — Stanley's apparatus applied more readily to one political side than to structurally-equivalent instances on the other.
- **Lens-citation without text** — Stanley/Bernays/Ellul/Herman-Chomsky vocabulary deployed without quoted artifact evidence.

**What NOT to collapse:**

- **Stream disagreement about supporting vs. undermining** — when streams classified the same artifact differently, the disagreement is itself a finding about whether the gap between professed and actual is genuine or read-in.
- **Multiple flawed-ideology premises** — when the contradiction requires several prior beliefs to remain invisible, all survive as their own atoms.
- **Diagnostic ambiguity** — when evidence does not cleanly support propaganda diagnosis vs. mere advocacy, the ambiguity surfaces rather than being resolved by force.
- **Asymmetric-application disagreements** — when streams diverged on whether the apparatus is being applied evenly across political orientations, the disagreement is preserved and acknowledged per Debate D5.

## VERIFICATION CRITERIA

Verified means: the professed ideal is named with quoted text; the supporting / undermining classification is evidenced; the flawed-ideology premises are identified if classification is undermining; the not-at-issue content inventory cites quoted presuppositions or implicatures; the five filters are applied if the artifact is mass-media; the propaganda diagnosis has been distinguished from any claim about the truth of the artifact's conclusion. The five critical questions are addressable from the output. Confidence per finding accompanies each major claim.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **propaganda audit** — a Stanley-style structured diagnostic that names the professed ideal with quoted text, classifies supporting vs. undermining with evidence, identifies the flawed-ideology premises (if undermining), inventories not-at-issue content, and distinguishes the diagnosis from rejection of the artifact's conclusion. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Professed ideal named.** One labelled block. `**Professed ideal:** [the ideal the artifact claims to embody]. **Quoted text from artifact:** "[passage that states or implies the ideal]."`

2. **Actual function hypothesised.** One paragraph stating the artifact's predicted audience uptake / behavioural consequence / attentional or affective effect, inferred from the artifact's structure and audience targeting.

3. **Supporting or undermining classification.** One labelled block. `**Classification:** [supporting / undermining]. **Evidence:** [...]. **Stanley distinction applied:** [supporting = non-rational means for worthy ideal; undermining = presents-as-embodying-while-eroding].`

4. **Flawed-ideology premises required.** Where the classification is undermining, a bulleted list. Each: `**Premise N:** [prior belief the audience must hold]. Why the contradiction remains invisible if this is held: [...].` Where the classification is supporting, this section is `Not applicable for supporting-propaganda classification.`

5. **Not-at-issue content inventory.** Bulleted list. Each: `**[Mechanism — presupposition / conventional implicature / lexical activation]** — quoted text: "...". Persuasive effect: [what this content asserts without arguing for it].`

6. **Frame manipulation techniques active.** Bulleted list. Each: `**[Technique — responsibility relocation / loaded terms / episodic framing / presupposition smuggling / naturalization / agent deletion / manufactured-doubt]** — quoted text: "...". How the technique operates: [...].`

7. **Five-filter structural situating.** When the artifact is mass-media: per-filter sub-blocks for `Ownership`, `Advertising`, `Official sources`, `Flak`, `Common-enemy`. When the artifact is not mass-media: `Not applicable — artifact is not a mass-media product. (Author-sponsor context noted in section 2.)`

8. **Audience predicted uptake.** One paragraph. `Target audience: [...]. Predicted cognitive shift: [...]. Predicted affective shift: [...]. Predicted behavioural shift: [...]. Evidence basis for the prediction: [...].`

9. **Confidence per finding.** Bulleted list of confidence assessments per major claim, with grounding (quoted text, structural inference, lens application).

**Per-section conventions:**

- Use H2 headings for sections 1 through 9.
- Stanley vocabulary stays operative: `professed ideal`, `actual function`, `supporting propaganda`, `undermining propaganda`, `flawed ideology`, `not-at-issue content`. The vocabulary appears verbatim with operative meanings preserved.
- Quoted text appears throughout — every claim that the artifact does X is anchored in a quote that shows it. Macro-level claims without textual grounding are reshaped.
- The diagnosis-vs-conclusion distinction (CQ5) is preserved everywhere: the deliverable does not argue that the artifact's conclusion is false because the artifact is propaganda. This is a meta-level discipline; if the deliverable starts arguing against the artifact's conclusion, it has tipped into red-team territory and gets reshaped or rerouted.
- When the motive-attribution-evidence flag survived consolidation, the deliverable opens with: `**Note: the diagnostic below focuses on the artifact's structure and predicted effect. Where deliberate manipulative intent is imputed to author or sponsor, explicit textual or contextual evidence is cited; speculative intent attributions are reshaped to structural-mechanism claims.**`
- When the asymmetric-application flag survived consolidation (Debate D5 sensitivity), the deliverable opens with: `**Note: Stanley's apparatus is contested as potentially applying asymmetrically across political orientations (Debate D5). The diagnostic below has been applied with symmetry-discipline; if the audit would not flag a structurally-equivalent instance on the other side, the diagnosis is reshaped or qualified.**`
- Five-filter situating (section 7) is *only* applied when the artifact is mass-media. Padding the section for non-mass-media artifacts is reshaped to the explicit `not-applicable` marker.
- Confidence (section 9) is per-finding; collapsing to single audit confidence is reshaped at this layer.

## CAVEATS AND OPEN DEBATES

**Debate D5 — Is Stanley's *How Propaganda Works* politically neutral or directional?** The book's diagnostic apparatus (supporting / undermining distinction; flawed-ideology precondition; not-at-issue content) is offered as politically neutral analytical machinery, applicable to any artifact regardless of the artifact's political orientation. Sympathetic readings (e.g., much of the academic philosophy-of-language reception) treat the apparatus as neutral and the case studies as illustrative. Skeptical readings (visible in popular reception, including Goodreads-style criticism and several conservative-tradition reviewers) argue that the apparatus is built around a left-liberal canon of paradigm cases (Birth of a Nation; Fox News; Trump-era discourse) and that this case-base inflects the apparatus toward asymmetric application — i.e., that the diagnostic catches right-wing propaganda more readily than structurally-equivalent left-wing instances. A third reading (Lear and others in epistemology of testimony) treats the apparatus as defensible-but-incomplete: Stanley's framework illuminates one important class of propaganda (undermining demagoguery) without exhausting the propaganda phenomenon. This mode operates without adjudicating the debate: it applies Stanley's distinctions as analytical lens (treating "supporting" and "undermining" as useful descriptors for argumentatively distinct propaganda structures) while remaining agnostic on whether Stanley's case-base inflects the apparatus directionally. The mode's symmetry guardrails (motive-attribution-without-evidence as named failure; propaganda-charge-as-refutation as named failure) are designed to mitigate the asymmetric-application risk regardless of which side of the debate one finds more persuasive. Citations: Stanley 2015 *How Propaganda Works*; Lear 2017 in *Mind*; popular-reception reviews on Goodreads and conservative-tradition outlets surveyed but not adjudicated.

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
