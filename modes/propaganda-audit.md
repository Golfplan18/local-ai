---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
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
output_contract:
  artifact_type: audit
  required_sections:
    - professed_ideal_named
    - actual_function_hypothesized
    - supporting_or_undermining_classification
    - flawed_ideology_premises_required
    - not_at_issue_content_inventory
    - frame_manipulation_techniques_active
    - five_filter_structural_situating_if_applicable
    - audience_predicted_uptake
    - confidence_per_finding
  format: structured

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

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) professed ideal named; (CQ2) supporting / undermining classification with evidence; (CQ3) flawed-ideology premises identified if undermining; (CQ4) not-at-issue content inventoried; (CQ5) propaganda diagnosis distinguished from conclusion-rejection. The named failure modes (ideal-omission, classification-collapse, flawed-ideology-omission, at-issue-only-reading, propaganda-charge-as-refutation, motive-attribution-without-evidence) are the evaluation checklist. A passing Propaganda Audit names the professed ideal, classifies supporting vs. undermining with evidence, identifies flawed-ideology premises if undermining, inventories not-at-issue content with quoted text, and distinguishes the propaganda diagnosis from rejection of the artifact's conclusion.

## REVISION GUIDANCE

Revise to name the professed ideal explicitly where the draft has assessed propaganda function without surfacing it. Revise to disambiguate supporting from undermining where the draft asserts "propaganda" without distinguishing the two structures. Revise to identify flawed-ideology premises where the draft classifies as undermining without saying what the audience must believe. Revise to catalogue not-at-issue content where the audit has examined only what is asserted. Revise to separate the propaganda diagnosis from any claim that the artifact's conclusion is false. Resist revising toward neutrality — the mode is adversarial-stance by design (sensitive Debate D5 in CAVEATS); softening the diagnostic to be evenhanded is a failure mode, not a polish. The adversarial stance is structural to the mode and is what distinguishes it from frame-audit.

## CONSOLIDATION GUIDANCE

Consolidate as a structured audit with the nine required sections. The professed ideal is quoted from the artifact. The actual function is hypothesized with predicted-audience-uptake evidence. The supporting / undermining classification cites the Stanley distinction explicitly. Flawed-ideology premises are listed (the prior beliefs the audience must hold for the gap between professed and actual to remain invisible). Not-at-issue content inventory cites quoted presuppositions, conventional implicatures, and lexical activations per finding. Frame-manipulation techniques active (responsibility relocation, loaded terms, episodic framing, presupposition smuggling, naturalization, etc.) are named per the Frame-Manipulation taxonomy. Five-filter structural situating is included when the artifact is a mass-media product. Audience-predicted-uptake explains how the propaganda works on its target. Confidence per finding accompanies each major claim.

## VERIFICATION CRITERIA

Verified means: the professed ideal is named with quoted text; the supporting / undermining classification is evidenced; the flawed-ideology premises are identified if classification is undermining; the not-at-issue content inventory cites quoted presuppositions or implicatures; the five filters are applied if the artifact is mass-media; the propaganda diagnosis has been distinguished from any claim about the truth of the artifact's conclusion. The five critical questions are addressable from the output. Confidence per finding accompanies each major claim.

## CAVEATS AND OPEN DEBATES

**Debate D5 — Is Stanley's *How Propaganda Works* politically neutral or directional?** The book's diagnostic apparatus (supporting / undermining distinction; flawed-ideology precondition; not-at-issue content) is offered as politically neutral analytical machinery, applicable to any artifact regardless of the artifact's political orientation. Sympathetic readings (e.g., much of the academic philosophy-of-language reception) treat the apparatus as neutral and the case studies as illustrative. Skeptical readings (visible in popular reception, including Goodreads-style criticism and several conservative-tradition reviewers) argue that the apparatus is built around a left-liberal canon of paradigm cases (Birth of a Nation; Fox News; Trump-era discourse) and that this case-base inflects the apparatus toward asymmetric application — i.e., that the diagnostic catches right-wing propaganda more readily than structurally-equivalent left-wing instances. A third reading (Lear and others in epistemology of testimony) treats the apparatus as defensible-but-incomplete: Stanley's framework illuminates one important class of propaganda (undermining demagoguery) without exhausting the propaganda phenomenon. This mode operates without adjudicating the debate: it applies Stanley's distinctions as analytical lens (treating "supporting" and "undermining" as useful descriptors for argumentatively distinct propaganda structures) while remaining agnostic on whether Stanley's case-base inflects the apparatus directionally. The mode's symmetry guardrails (motive-attribution-without-evidence as named failure; propaganda-charge-as-refutation as named failure) are designed to mitigate the asymmetric-application risk regardless of which side of the debate one finds more persuasive. Citations: Stanley 2015 *How Propaganda Works*; Lear 2017 in *Mind*; popular-reception reviews on Goodreads and conservative-tradition outlets surveyed but not adjudicated.
</content>
</invoke>