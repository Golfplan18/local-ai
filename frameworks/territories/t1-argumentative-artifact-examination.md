
# Framework — Argumentative Artifact Examination

*Self-contained framework for evaluating an existing argument, claim-set, position, or text-as-argument for its internal soundness, framing structure, rhetorical mechanisms, and propaganda function. Compiled 2026-05-01 from territory entry, member mode specs, lens dependencies, and open debates.*

---

## Territory Header

- **Territory ID:** T1
- **Name:** Argumentative Artifact Examination
- **Super-cluster:** A (Argument and Reasoning)
- **Characterization:** Operations that take an existing argument, claim-set, position, or text-as-argument as input and evaluate its internal soundness, coherence, framing, or rhetorical structure.
- **Boundary conditions:** Input must be a structured or semi-structured argumentative artifact (article, memo, policy, debate transcript, stated position). Excludes evaluating the *interests behind* the argument (T2 — Interest and Power Analysis) or evaluating *empirical claims* against external evidence (T5 — Hypothesis Evaluation).
- **Primary axis:** Depth (Coherence Audit and Frame Audit at light atomic; Argument Audit at molecular).
- **Secondary axes:** Specificity (general argument vs. propaganda-specific vs. position-genealogy variants); stance is weak in T1.

## When to use this framework

Use this framework when the work in front of you is an existing argument and the question is whether it holds up — structurally, framingly, or as a piece of persuasion. Plain-language triggers:

- "Want to know whether this argument actually holds together."
- "The conclusion sounds right but I can't tell if the reasoning supports it."
- "Want a structural check on the premises-to-conclusion moves."
- "Want to see how this artifact frames the issue."
- "The framing here is doing more work than the argument."
- "The metaphors here may be carrying the argument."
- "This feels like propaganda but I want to test that."
- "Looks like the artifact presents itself as embodying an ideal but actually erodes it."
- "I want a full audit — both whether the argument coheres and what frame it imports."

Do not route here when: the question is who benefits from the argument's acceptance (that is T2 — Interest and Power); when the question is which of several competing hypotheses fits the evidence best (T5 — Hypothesis Evaluation); when the question is how to *evaluate* the artifact as a *proposal* by adopting a stance (T15 — Artifact Evaluation by Stance: Steelman, Balanced Critique, Red Team).

## Within-territory disambiguation

Once the territory is known, the disambiguation questions select which mode does the work.

```
Q1 (situation): "Is the question about whether the argument holds together internally,
                 or about the frame/lens it's using to see the issue,
                 or about both at once?"
  ├─ "internal logic" → coherence-audit (default Tier-2)
  ├─ "frame / lens / framing" → frame-audit (default Tier-2)
  ├─ "both" → argument-audit molecular (Tier-3 — confirm given runtime)
  └─ ambiguous → default to coherence-audit, with escalation hook to frame-audit

Q2 (specificity, optional): "Is this an everyday argument, or does it look like
                              rhetoric/propaganda where the moves are themselves the issue?"
  ├─ "rhetoric / propaganda / messaging" → propaganda-audit
  ├─ "tracing where this position came from over time" → position-genealogy (deferred)
  └─ default → standard mode selected in Q1
```

**Default route.** `coherence-audit` at Tier-2 when ambiguous, with frame-audit available as an escalation hook (very common pairing — coherence often surfaces a hidden frame question).

**Escalation hooks.**
- After `coherence-audit` Tier-2: if the audit surfaces a frame-dependent inconsistency, hook upward to `frame-audit`.
- After `frame-audit` Tier-2: if multiple competing frames surface and the question is which to adopt, hook upward to `frame-comparison` in T9.
- After either light atomic mode: if both findings interact non-trivially, hook upward to `argument-audit` molecular.
- After any T1 mode: if the question becomes "should we accept this proposal?", hook sideways to T15 (`steelman-construction` or `red-team-assessment` / `red-team-advocate`).

## Mode entries

### Mode — coherence-audit

- **Educational name:** argument coherence audit (Toulmin model + fallacy taxonomy)
- **Plain-language description:** A neutral structural assessment of whether the premises support the conclusion. The audit charitably reconstructs the strongest version of the argument actually present in the text, breaks each inferential move into its Toulmin components (claim, data, warrant, backing, qualifier, rebuttal), names any fallacies with quoted text plus the reason the move fails *here*, and surfaces structural failures (premise smuggling, scope shift, definitional drift) that live outside the named-fallacy taxonomy. The audit is conclusion-agnostic by design: "this argument as given does not establish its conclusion" is a different verdict from "the conclusion is false."

- **Critical questions:**
  1. Has the audit performed charitable reconstruction first — surfacing implicit premises (enthymemes), resolving textual ambiguity in the speaker's favor, and identifying the strongest version of the argument actually present — before flagging any fallacy?
  2. Has the audit decomposed the argument into Toulmin elements (claim, data, warrant, backing, qualifier, rebuttal) per inferential move, surfacing the warrants explicitly so that the inferential move can be examined?
  3. When fallacies are named, has each been substantiated with (a) the specific quoted text, (b) the inferential move identified, (c) the principle the move violates, and (d) the reason the move fails *here* (not just in the abstract) — to prevent name-without-structure misapplication?
  4. Has the audit clearly separated 'this argument as given does not establish its conclusion' from 'the conclusion is false' — refusing to make the latter claim absent independent grounds (the fallacy fallacy / argumentum ad logicam)?
  5. Has the audit looked beyond named fallacies for structural coherence failures (premise smuggling, scope shift, definitional drift, unstated load-bearing assumptions, enthymeme failure) — given that most actual argumentative weakness lives in unnamed structural failures rather than in the named-fallacy taxonomy?

- **Per-pipeline-stage guidance:**
  - **Depth.** Depth is the precision with which charitable reconstruction surfaces implicit premises, Toulmin elements are decomposed per move, fallacy claims are substantiated with quoted text + violated principle + reason-it-fails-here, and unnamed structural failures are surfaced beyond the taxonomy. A thin pass produces a fallacy-list against surface text; a substantive pass reconstructs the strongest reading and audits *that*.
  - **Breadth.** Scan three traditions of fallacy theory before narrowing: Walton's pragmatic / dialectical theory (fallacy depends on dialogue type — persuasion, inquiry, negotiation, deliberation, information-seeking, eristic); pragma-dialectics (fallacies as violations of rules for critical discussion); Hintikka's question-dialogue theory (fallacies as illegitimate moves in question-answer games). Also scan formal vs. informal fallacy taxonomy and structural failures not named in the taxonomy.
  - **Evaluation.** Evaluate against the five critical questions; the named failure modes (uncharitable-reconstruction, warrant-blindness, name-without-structure, argument-conclusion-conflation, named-fallacy-only-reading, asymmetric-rigor) are the checklist.
  - **Revision.** Revise to perform charitable reconstruction first; surface Toulmin warrants; substantiate fallacy claims; separate argument-soundness from conclusion-truth; add the structural-failure sweep. Resist revising toward decisive verdicts on the conclusion's truth.
  - **Consolidation.** Structured audit with seven required sections: charitable reconstruction; Toulmin breakdown per inferential move; named fallacies (if present) with quoted text; structural coherence failures (not named fallacies); argument-holds-or-fails per move; argument-wrong vs. conclusion-wrong separation; confidence per finding.
  - **Verification.** Charitable reconstruction precedes any fallacy claim; warrants surfaced per move; every named fallacy substantiated with quoted text + violated principle + reason-it-fails-here; argument-wrong explicitly separated from conclusion-wrong; structural-failure sweep performed; severity grading symmetric across the artifact.

- **Source tradition:** Toulmin's *The Uses of Argument* (1958/2003) for the six-component decomposition; Walton's argumentation-scheme + critical-questions apparatus (Walton, Reed, Macagno 2008) for dialectical context; Hamblin's *Fallacies* (1970) and the post-Hamblin theoretical critique of the textbook taxonomy.

- **Lens dependencies:**
  - `toulmin-model`: Decomposes a single argument into claim, grounds, warrant, backing, qualifier, rebuttal — exposing the inferential moves and the implicit warrant that connects grounds to claim.
  - `walton-schemes-and-critical-questions`: Catalogue of presumptive argument forms (expert opinion, position to know, popular opinion, cause to effect, sign, slippery slope, ad hominem, analogy, ignorance, practical reasoning, commitment) each with its scheme-specific critical questions whose negative answers defeat the argument.
  - Optional: `hamblin-fallacies-standard-treatment-critique`, `pragma-dialectics-rules-for-critical-discussion`, `copi-informal-fallacy-taxonomy`, `alexander-isolated-demands-for-rigor`, `shackel-motte-and-bailey`.

### Mode — frame-audit

- **Educational name:** frame audit (Lakoff + Goffman + Entman)
- **Plain-language description:** A stance-suspending surfacing of how the artifact frames the issue. The audit names the operative frame in vocabulary that allows comparison with alternatives (not in the artifact's own naturalized terms), populates Entman's four functions per frame (problem definition / causal interpretation / moral evaluation / treatment recommendation), inventories selection-and-salience including what is omitted or downplayed, catalogues the linguistic mechanisms (Lakoff metaphors, CDA presuppositions, nominalizations) by which the frame travels at the word and grammar level, and constructs at least one counterframe to make the operative frame visible *as* a frame.

- **Critical questions:**
  1. Has the audit named the operative frame(s) explicitly, in vocabulary that allows comparison with alternative frames, rather than treating the artifact's framing as the natural way to see the issue?
  2. Has the analysis applied the four Entman functions (problem definition / causal interpretation / moral evaluation / treatment recommendation) per frame, or has it surfaced the frame without showing what each function is doing?
  3. Has the audit surfaced selection and salience explicitly — what the artifact includes and excludes, what it emphasizes and downplays — given that frames work as much by what they leave silent as by what they assert?
  4. Has the audit catalogued the linguistic mechanisms (metaphor activation per Lakoff; presupposition, nominalization, passivization, lexicalization choices per CDA) by which the frame travels at the word and grammar level?
  5. Has the audit constructed at least one counterframe (what would the issue look like under an alternative frame), to test whether the operative frame is doing analytical work or just describing the topic?

- **Per-pipeline-stage guidance:**
  - **Depth.** Precision in naming the frame in alternative-comparable vocabulary (not the artifact's own terms), populating Entman's four functions per frame, inventorying mechanisms with quoted text, and constructing at least one counterframe.
  - **Breadth.** Scan the seven framing-tradition layers: cognitive linguistic (Lakoff); sociological (Goffman); media studies (Entman / Gitlin / Tuchman); CDA (Fairclough, van Dijk, Wodak); propaganda analysis (Bernays, Ellul, Herman/Chomsky, Stanley); political communication (Iyengar; Chong/Druckman); social-movement framing (Snow/Benford). Survey at least four before producing findings.
  - **Evaluation.** The five critical questions plus the named failure modes (frame-naturalization, function-collapse, silence-blindness, macro-frame-only-reading, counterframe-omission, stance-slippage-into-attack).
  - **Revision.** Extract the frame to alternative-comparable vocabulary; populate the four functions; add the silence inventory; add lexical-grammatical mechanisms; construct the counterframe. Resist revising toward attack — the mode is stance-suspending; rejecting the frame belongs in propaganda-audit (if propaganda is suspected) or the red-team modes (if evaluating as proposal).
  - **Consolidation.** Eight required sections: operative frames named; Lakoff metaphor inventory; Goffman primary framework + keyings; Entman four functions per frame; selection-and-salience inventory (both columns); presupposition + nominalization audit; counterframe; confidence per finding.
  - **Verification.** Frames named in alternative-comparable vocabulary; four functions populated with quoted evidence; silence inventory has entries; mechanisms cited with quoted text; counterframe constructed; no stance-slippage into attack.

- **Source tradition:** Lakoff & Johnson *Metaphors We Live By* (1980), Lakoff *Moral Politics* (1996/2002); Goffman *Frame Analysis* (1974); Entman 1993 *Journal of Communication* "Framing: Toward Clarification of a Fractured Paradigm"; Fairclough/van Dijk Critical Discourse Analysis tradition.

- **Lens dependencies:**
  - `lakoff-conceptual-metaphor`: Source-to-target mappings (ARGUMENT IS WAR, NATION IS FAMILY) carry inferential entailments below conscious attention; surfacing them exposes commitments that are doing inferential work without being argued for.
  - `goffman-frame-analysis`: Primary frameworks (natural vs. social), keyings (make-believe / contests / ceremonials / technical redoings / regroundings), fabrications, frame-breaks — the structural account of how frames organize subjective involvement.
  - `entman-framing-functions`: The operational complement — what frames *do* in communication via four functions (define problems, diagnose causes, make moral judgments, suggest remedies) plus selection and salience as the underlying mechanism.
  - Optional: `cda-fairclough-presupposition-and-nominalization`, `iyengar-episodic-thematic`, `chong-druckman-emphasis-equivalence`, `snow-benford-frame-alignment`.

### Mode — propaganda-audit

- **Educational name:** propaganda audit (Stanley supporting/undermining + flawed-ideology test)
- **Plain-language description:** An adversarial-stance diagnostic on a single artifact suspected of propaganda function. The audit names the professed ideal of the artifact (the freedom / fairness / security / truth it claims to embody), hypothesizes the actual function, classifies as supporting (non-rational means for worthy ideal) or undermining (presents-as-embodying-ideal-while-eroding-it), identifies the flawed-ideology premises the audience must hold for the contradiction to remain invisible to them, inventories the not-at-issue content (presuppositions, conventional implicatures, lexical activations) doing the persuasive work, and distinguishes the propaganda diagnosis from rejection of the artifact's conclusion.

- **Critical questions:**
  1. Has the audit named the professed ideal of the artifact (the freedom / fairness / security / truth it claims to embody) explicitly, before assessing whether the artifact's function aligns with or erodes that ideal?
  2. Has the supporting / undermining distinction been applied with evidence — does the artifact use non-rational means to advance the professed ideal (supporting), or does it present itself as embodying the ideal while actually eroding it (undermining)?
  3. If the artifact is classified as undermining, has the audit identified the specific flawed-ideology premise(s) the audience must hold for the contradiction between professed and actual to remain invisible to them?
  4. Has the audit catalogued the not-at-issue content (presuppositions, conventional implicatures, lexical activations) doing the persuasive work, given that propaganda often operates through what is assumed rather than asserted?
  5. Has the audit distinguished 'this artifact is propaganda' from 'I disagree with this artifact's conclusion' — and avoided treating the audit as a refutation of the artifact's claims (the propaganda-charge fallacy)?

- **Per-pipeline-stage guidance:**
  - **Depth.** Precision in naming and quoting the professed ideal, inferring actual function from artifact structure, evidencing the supporting / undermining classification, identifying flawed-ideology premises, and inventorying not-at-issue content with quoted text.
  - **Breadth.** Scan: Bernays (engineering of consent); Ellul (integration vs. agitation; ambient cumulative narrowing); Herman & Chomsky (five-filter propaganda model); Stanley (supporting / undermining; flawed ideology; not-at-issue). Where applicable, add Lakoff (lexical metaphor activation), CDA (presupposition, nominalization, agent deletion), and Iyengar (episodic vs. thematic). Survey at least the Stanley diagnostic plus one structural-context layer and one linguistic-mechanism layer before producing findings.
  - **Evaluation.** The five critical questions plus the named failure modes (ideal-omission, classification-collapse, flawed-ideology-omission, at-issue-only-reading, propaganda-charge-as-refutation, motive-attribution-without-evidence).
  - **Revision.** Name the professed ideal; disambiguate supporting from undermining; identify flawed-ideology premises; catalogue not-at-issue content; separate propaganda diagnosis from rejection of conclusion. Resist revising toward neutrality — the mode is adversarial-stance by design; softening to be evenhanded is a failure mode, not a polish.
  - **Consolidation.** Nine required sections: professed ideal named; actual function hypothesized; supporting/undermining classification; flawed-ideology premises required; not-at-issue content inventory; frame-manipulation techniques active; five-filter situating (if mass-media); audience predicted uptake; confidence per finding.
  - **Verification.** Professed ideal named with quoted text; supporting/undermining classification evidenced; flawed-ideology premises identified if undermining; not-at-issue content inventory cites quoted text; five filters applied if mass-media; propaganda diagnosis distinguished from any claim about truth of conclusion.

- **Source tradition:** Stanley *How Propaganda Works* (2015) and *How Fascism Works* (2018) for the supporting/undermining distinction and flawed-ideology mechanism; Bernays *Propaganda* (1928) for engineering-of-consent; Ellul *Propaganda* (1965) for integration vs. agitation; Herman & Chomsky *Manufacturing Consent* (1988) for the five-filter model.

- **Lens dependencies:**
  - `stanley-propaganda`: The supporting/undermining distinction; flawed-ideology mechanism (the audience supplies the inferential connection); concept-substitution (using normatively-loaded terms while substituting different content); in-group/out-group exploitation. Diagnostic apparatus for propaganda artifacts.
  - `walton-schemes-and-critical-questions`: The dialectical surface through which propagandistic content is delivered — appeal to popular opinion, ad hominem, slippery slope, ad ignorantiam often work in conjunction with the deeper propaganda mechanism.
  - Optional: `bernays-engineering-of-consent`, `ellul-integration-vs-agitation`, `herman-chomsky-five-filter-propaganda-model`, `lakoff-conceptual-metaphor`, `cda-fairclough-presupposition-and-nominalization`, `iyengar-episodic-thematic`.

### Mode — argument-audit

- **Educational name:** argument audit (Frame Audit + Coherence Audit integrated)
- **Plain-language description:** Molecular composition that runs Frame Audit and Coherence Audit in full, then synthesizes their outputs to surface cross-cutting issues neither pass would catch alone. The synthesis stages are: (1) frame-coherence merge — pair per-claim coherence findings with frame-surfacing findings, identifying where frame-imports do analytical work coherence-audit alone would miss; (2) cross-cutting integration — surface where the argument's coherence depends on contested frame-imports, where coherence-failures track frame-substitutions, and where motte-and-bailey-style structure operates across claims; (3) integrated-audit document — per-claim findings + frame-level findings + cross-cutting issues + named fallacies (with debate notes) + overall argument-soundness assessment.

- **Critical questions:**
  1. Does the cross-cutting-integration stage actually surface issues that neither component pass would catch alone, or does it merely concatenate them?
  2. Are frame-imports identified concretely (which premises smuggle in which framings), or are they noted vaguely?
  3. Are coherence findings grounded in specific claim-pairs and inference steps, or are they stated as general impressions?
  4. Where named fallacies are invoked (motte-and-bailey, equivocation, etc.), is the invocation specific and warranted, or is it a label slapped on a contested move?

- **Per-pipeline-stage guidance:**
  - **Composition.** Molecular: full coherence-audit and full frame-audit run, then synthesis stages (parallel-merge → contradiction-surfacing → dialectical-resolution).
  - **Breadth.** Catalogue frames considered before frame-audit narrows: dominant-paradigm, minority-tradition, rhetorical-genre, historical-genealogy. Documented in frame-surfacing-findings section.
  - **Evaluation.** CQ1–CQ4 plus named failure modes (integration-failure, frame-import-vagueness, coherence-impressionism, fallacy-labeling-without-warrant).
  - **Consolidation.** Eight required sections: argument summary; per-claim coherence findings; frame-surfacing findings; cross-cutting issues; named fallacies and argumentative moves; overall argument-soundness assessment; residual uncertainties; confidence map. Each finding carries provenance to its component source.
  - **Verification.** Both component passes ran (or were flagged as proceeded-with-gap); cross-cutting-integration surfaces issues neither component caught alone; frame-imports and coherence findings concretely grounded; named fallacies warranted; confidence map populated.

- **Source tradition:** Inherits from Toulmin (Coherence Audit substrate) and Lakoff/Goffman/Entman (Frame Audit substrate); adds Shackel 2005 *Motte-and-Bailey* for the canonical motte-and-bailey treatment relevant to cross-cutting fallacy detection (Debate D2).

- **Lens dependencies:**
  - `walton-argumentation-schemes`: Provides the dialectical-classification overlay across both component passes.
  - Optional: `lakoff-framing` (extends frame-audit's metaphor reading); `shackel-motte-and-bailey` (carries Debate D2 — fallacy or doctrine).
  - Foundational: `kahneman-tversky-bias-catalog`.

- **For molecular modes:** Composition specified above. Paired execution framework: this framework — `Framework — Argumentative Artifact Examination.md` — supplies the synthesis-stage scaffolding directly; no separate execution framework is required.

## Cross-territory adjacencies

Use these pointers to navigate to adjacent territories when the question shifts mid-conversation.

**T1 ↔ T2 (Argumentative Artifact ↔ Interest and Power).** Disambiguating question: "Are you mostly asking whether the argument itself holds up, or who benefits if people accept it?" Argument-soundness focus → T1; interest-pattern focus → T2; both → sequential dispatch, T1 first (foundational evaluation), T2 layers interest analysis on the audited artifact.

**T1 ↔ T5 (Argumentative Artifact ↔ Hypothesis Evaluation).** Disambiguating question: "Are the competing positions each a complete argument you want me to audit, or are they propositions you want weighed against evidence?" Argument-as-artifact (each side is itself a structured argument) → T1 (Argument Audit on each); proposition-against-evidence (each side is a candidate explanation) → T5 (Differential Diagnosis / Competing Hypotheses / Bayesian Hypothesis Network).

**T1 ↔ T9 (Argumentative Artifact ↔ Paradigm Examination).** Disambiguating question: "Are you evaluating this single argument's frame, or comparing different paradigms that frame the issue differently?" Single-artifact frame surfacing → T1 (Frame Audit); multi-paradigm comparison → T9 (Frame Comparison or Worldview Cartography).

**T1 ↔ T10 (Argumentative Artifact ↔ Conceptual Clarification).** Disambiguating question: "Is the issue with how the argument deploys a specific concept (clarify the concept first), or with how the argument coheres given any reasonable reading of the concept?" Concept-precision issue → T10 (Deep Clarification / Conceptual Engineering); argument-coherence issue → T1.

**T1 ↔ T15 (Argumentative Artifact ↔ Artifact Evaluation by Stance — Steelman cross-territory case).** Disambiguating question: "Want me to evaluate the argument's *soundness* (does it hold up?), or *evaluate the proposal* with a particular stance (steelman it / push back hard / weigh both)?" Soundness evaluation → T1 (Coherence/Frame/Argument Audit); stance-bearing evaluation → T15 (Steelman / Benefits / Balanced Critique / Red Team). Steelman cross-territory disposition: home is T15; T1 cross-reference activates when the artifact under steelmanning is itself an argument.

## Lens references

The required lens content embedded below is sufficient for self-contained execution.

### toulmin-model

**Core insight.** An argument is not a single proposition but a structured movement from data to claim, mediated by an inferential rule (warrant) that is itself supported by a body of background reasons (backing), constrained by a strength qualifier, and exposed to specified rebuttal conditions. Most arguments expose only the claim and the grounds; warrant, backing, qualifier, and rebuttal remain implicit. Auditing an argument means making each component explicit and testing whether each holds.

**Mechanism.** The model treats argumentation as a rule-governed inference. Six components, each with an operational test:
- **Claim.** The proposition the arguer wants the audience to accept. Test: extract the claim by asking "what is the arguer ultimately asking me to believe or do?" A well-formed claim is a single proposition (not a cluster) and is stated declaratively.
- **Grounds (Data).** The facts, evidence, observations, or already-accepted propositions offered in support. Test: ask "what does the arguer point to as the basis for the claim?" Grounds must be of a kind whose accuracy can be checked independently of the claim itself.
- **Warrant.** The inferential rule that licenses moving from grounds to claim. Typically implicit; reconstruct by asking "what general rule, if true, would make these grounds support this claim?" State as a hypothetical: "if grounds of type G obtain, then claims of type C are warranted." Field-dependent (legal warrants differ from scientific differ from moral).
- **Backing.** The body of evidence, established practice, or theoretical support behind the warrant. Answers "why should we accept the warrant in this field?" A warrant without backing is bare appeal.
- **Qualifier.** The word or phrase indicating the strength claimed: certainly, probably, presumably, in most cases. Identify the qualifier the arguer used (or did not use); arguments with weak warrants stated without qualifier are over-claiming.
- **Rebuttal.** The conditions under which the claim would fail despite the grounds being satisfied. Acknowledges the warrant's defeasibility. An argument that names no rebuttal conditions is treating its warrant as universal.

**Applicability conditions.** Argument has a single identifiable claim or can be decomposed into multiple single-claim arguments; host mode needs to surface implicit inferential moves rather than classify by named scheme; audit purpose is structural test of the argument, not comparison of competing arguments.

**Common misapplications.** Treating the model as a deductive validity test (Toulmin developed it precisely to capture *non-formal* argument); conflating warrant and backing (the warrant is the rule; backing supports the rule); strawman warrant reconstruction; omitting qualifier and rebuttal because the arguer omitted them.

### walton-schemes-and-critical-questions

**Core structure.** A presumptive argument scheme is an argument form that is defeasibly valid: when its premise pattern is satisfied, the conclusion is plausibly supported, but the conclusion can be defeated by a negative answer to any of the scheme's critical questions. Highest-frequency schemes by family:

**Source-Based Schemes:**
- *Argument from Expert Opinion.* Premise: E is an expert in domain D; E asserts A; A is in D. Conclusion: A is plausibly true. Critical questions: (1) Is E a genuine expert in D? (2) Did E actually assert A? (3) Is A within D? (4) Is E reliable and free of conflicts? (5) Do other experts agree? (6) Is the assertion grounded in evidence E can produce?
- *Argument from Position to Know.* Premise: P is in a position to know about A; P asserts A. CQs: Is P actually in the position claimed? Is P honest? Did P actually assert A in the form reported?
- *Argument from Popular Opinion.* Premise: A large majority accepts A. CQs: Is the popular acceptance accurately reported? Is the relevant population the right one? Is there independent evidence the popular view tracks truth here?
- *Argument from Commitment.* Premise: P committed to A earlier; the present situation is relevantly similar. CQs: Did P actually make the commitment? Is the situation similar? Has P retracted? Are there overriding considerations?

**Causal and Sign Schemes:**
- *Argument from Cause to Effect.* Premise: Generally C produces E; C occurred (or will). CQs: Is the causal generalization well-established? Are there intervening or counteracting causes? Are conditions in this case those under which the generalization holds? Forward or backward inference, and is that direction warranted?
- *Argument from Sign.* Premise: O is typically a sign of S; O is observed. CQs: Is O really a reliable sign? Are there alternative states that would also produce O? Could O be produced by manipulation rather than the genuine underlying state?
- *Slippery Slope.* Premise: A initiates a sequence leading to undesirable Z. CQs: Is each step actually likely to follow? Are there points where the sequence can be halted? Is Z genuinely undesirable? Causal, logical, or sociological slope?

**Schemes Targeting Persons and Knowledge:**
- *Ad Hominem.* Premise: P has bad character; P asserts A. CQs: Is the character claim accurate? Is the defect relevant to A's credibility? Is there independent evidence about A? Is the attack legitimate or fallacious?
- *Argument from Analogy.* Premise: C1 has properties P1..Pn and outcome O; C2 has properties P1..Pn. Conclusion: C2 plausibly has outcome O. CQs: Are C1 and C2 actually similar in P1-Pn? Are there relevant disanalogies? Is O in C1 actually produced by P1-Pn?
- *Argument from Ignorance.* Premise: A has not been proven false. CQs: Has there been a serious effort to find evidence against A? Domain where evidence-of-absence is reasonable? Is the burden of proof properly allocated?

**Practical Reasoning:**
- *Practical Reasoning.* Premise: A has goal G; doing M is a means to G; A is in a position to do M. CQs: Are there alternative means to G? Are alternatives more efficient, less costly, less risky? Does M have side-effects defeating G? Is G itself the right goal?

**Application steps.** (1) Receive argument; (2) identify which named scheme(s) it instantiates; (3) list the scheme-specific critical questions; (4) audit by checking each CQ against available evidence (supported / defeated / unaddressed); (5) return scheme classification + per-question audit + overall verdict (presumptively supported / defeated / under-determined).

### lakoff-conceptual-metaphor

**Core insight.** Conceptual metaphor is not decorative language but cognitive structure: human reasoning about abstract or unfamiliar domains (the *target*) is largely structured by mappings from more concrete domains (the *source*). Metaphors like ARGUMENT IS WAR, TIME IS MONEY, NATION IS A FAMILY shape what counts as sensible inference, what is salient, what is foregrounded, and what is hidden. Because metaphors operate below conscious attention most of the time, they exert framing power that conscious deliberation does not check.

**Mechanism.** A conceptual metaphor is a systematic mapping from source to target carrying structure (entities, relations, inferential patterns). ARGUMENT IS WAR maps combatants to disputants, attacks to objections, defenses to responses. The mapping licenses certain inferences ("she demolished his argument") and obscures others (collaborative arguing as joint inquiry). Three load-bearing properties:
- **Foregrounding and backgrounding.** Every metaphor highlights some features of the target and hides others. Often best diagnosed by what it makes invisible.
- **Inferential transfer.** Inferences valid in the source are imported to the target without explicit argument. If WAR is zero-sum, ARGUMENT IS WAR makes argument zero-sum without anyone arguing the case.
- **Multiple available mappings.** Most target domains can be structured by multiple alternatives, each foregrounding different aspects. The choice is rarely innocent.

Lakoff's *Moral Politics* applies this to two competing metaphorical models of NATION IS A FAMILY: the **strict-father model** (hierarchical, discipline, children become moral by internalizing punishment) and the **nurturant-parent model** (egalitarian, care and empathy, children become moral by extending care). *This is one application of the methodology, not the methodology itself.* The conceptual-metaphor apparatus applies far more generally; lenses should not collapse "conceptual metaphor analysis" into "strict-father vs. nurturant-parent."

**Application steps.** (1) Identify the target domain(s); (2) identify source domain(s) — concrete vocabulary in abstract contexts, inferential moves explicable only by source-domain entailments; (3) make the mapping explicit (entities, relations, transferred inferences); (4) identify what the mapping foregrounds and backgrounds; (5) identify alternative metaphorical mappings; (6) note what each alternative would foreground and background.

**Common misapplications.** Treating every metaphor as politically loaded; treating the strict-father / nurturant-parent analysis *as* the apparatus; decorative-metaphor confusion; reading entailments mechanically (mappings are partial).

### goffman-frame-analysis

**Core insight.** A frame is a *principle of organization* governing the subjective involvement of participants in an event. The same physical sequence ("a man strikes another man") can be a fight, a play rehearsal, a self-defense demonstration, a film scene, a ritual reenactment, or an act of abuse — each is a different *frame*, and the frame, not the physical sequence, determines what the event *is* for participants. Frames are tacit answers to "what is going on here?" and are typically taken for granted until something breaks them.

**Mechanism.**
- **Primary frameworks** organize experience without reference to prior framing. *Natural frameworks* treat events as undirected occurrences (a leaf falling). *Social frameworks* treat events as guided doings — actions with an agent who is responsible. The choice is consequential: natural absolves agents; social makes responsibility intelligible.
- **Keyings** transform a primary framework into something patterned on it but understood as quite else: *make-believe* (play, fantasy, theatrical performance), *contests* (sport as ritualized fighting), *ceremonials* (weddings re-keying acts as official versions), *technical redoings* (rehearsals, demonstrations, drills), *regroundings* (acts redone for ulterior motives — fundraising galas re-keying socializing as charitable work).
- **Fabrications** are intentional efforts to manage the activity so another participant is induced to hold a *false* belief about what is going on. Two forms: *benign* (surprise parties, harmless practical jokes) and *exploitative* (cons, frauds, manipulations). Asymmetric — the contained party doesn't know the frame the containing parties operate in.
- **Frame breaks** occur when the established frame collapses: an actor breaks character, a confidence game is exposed. Diagnostically valuable — they reveal the frame retrospectively.

**Application steps.** (1) Identify primary framework (natural vs. social); (2) detect keyings; (3) detect fabrications and their containing/contained parties; (4) identify frame breaks; (5) surface alternative frames; (6) note the stakes in the frame choice.

**Common misapplications.** Frame-as-perspective collapse (frame is structural, not cognitive stance); single-frame foreclosure; keying-fabrication conflation (asymmetry test: is any party being deceived?); reductive natural-framing (treating social events as natural to absolve agents).

### entman-framing-functions

**Core insight.** To frame is "to select some aspects of a perceived reality and make them more salient in a communicating text, in such a way as to promote a particular problem definition, causal interpretation, moral evaluation, and/or treatment recommendation." A frame performs (up to) four functions: it **defines problems**, **diagnoses causes**, **makes moral judgments**, and **suggests remedies**. The diagnostic task is to identify which functions are present, which are absent, and what alternative functions could have been performed.

**Mechanism.** Frames operate through **selection** (what aspects of reality are mentioned) and **salience** (how prominently — placement, repetition, association with culturally resonant symbols, vivid detail). *Omission* is as much a framing operation as inclusion. The four functions interact systemically:
- A frame that defines a problem without diagnosing causes typically directs attention to *symptoms* and forecloses structural analysis.
- A frame that diagnoses causes without making moral judgments presents the situation as technical and apolitical.
- A frame that makes moral judgments without suggesting remedies generates outrage without action.
- The most consequential political frames perform all four functions in tight integration: problem defined, cause named, moral judgment made, remedy suggested — producing a self-reinforcing whole that closes the analytical space.

Frames operate outside the awareness of audiences and often outside the awareness of communicators. Detecting frames requires attention not to communicator intent but to the *structure of selection and salience* in the artifact.

**Application steps.** (1) Identify what aspects have been *selected* and which *omitted*; (2) identify *salience* devices (placement, repetition, vivid detail, source-of-quote); (3) for each of the four functions, ask what the artifact does (problem? cause? judgment? remedy?); (4) surface *alternative framings* per function; (5) return the four-function audit + alternative-framing inventory.

**Common misapplications.** Function-tally substitution (counting how many functions are present); omission-blindness; intent-as-frame (frames operate via institutional defaults regardless of intent); single-frame description.

### stanley-propaganda

**Core insight.** Propaganda is not best characterized as lying or as overt manipulation. The most powerful propaganda works by *appearing* to argue for a goal — often couched in democratic, liberal, or otherwise widely-endorsed vocabulary — while actually undermining the conditions for the kind of public reasoning that vocabulary presupposes. Stanley distinguishes *supporting propaganda* (advances a goal by methods consistent with the ideals invoked) from *undermining propaganda* (advances a goal by methods that erode the very ideals invoked). Undermining propaganda is more dangerous because diagnosis requires examining the conditions for reasoning, not just the propositional content.

**Mechanism.**
- **Flawed ideology.** A body of beliefs an audience already holds, often unconsciously, that systematically distorts perception or reasoning about a domain. When the propagandist constructs a message that activates the flawed ideology, the message does not need to assert the ideology's content explicitly — the audience supplies that content from existing belief structure. *You don't have to lie if the audience already has the flawed belief.* A speech invoking "law and order" need not assert any group is criminal; if the audience holds a flawed ideology associating that group with criminality, the inference is supplied automatically. Deniability is built into the mechanism.
- **Concept substitution.** The propagandist takes a term whose received meaning carries normative weight (freedom, democracy, justice, security) and uses it in a way that substitutes different (often opposing) content while retaining the term's normative endorsement. "Freedom" comes to mean freedom from regulation that protects others; "democracy" comes to mean rule by the propagandist's faction. Concept substitution is undermining propaganda's principal mechanism for using democratic vocabulary against democratic content.
- **In-group/out-group exploitation.** Stanley's later work emphasizes that fascist propaganda activates and intensifies pre-existing group hierarchies rather than creating them de novo. The hierarchies provide the ready-made flawed ideology the propagandist activates.

**Application steps.** (1) Identify the goal the artifact appears to advance and the vocabulary used; (2) test for concept substitution; (3) test for flawed-ideology activation (identify audience, identify what flawed ideologies that audience plausibly holds, check if artifact activates them through associations rather than explicit claims); (4) test for in-group/out-group exploitation; (5) distinguish supporting from undermining; (6) return the audit with directionality caveat (Debate D5) noted.

**Common misapplications.** Universal-propaganda inflation (treating all persuasion as propaganda); analyst-ideology import (identifying flawed ideology by analyst preference rather than audience belief); directionality blindness (applying only to artifacts on one political side); substitution overreach (treating ordinary semantic evolution as substitution); mechanism-blind classification (verdict tracking the analyst's evaluation of the conclusion).

### walton-argumentation-schemes

(See `walton-schemes-and-critical-questions` above — this lens is the same canonical compendium, invoked specifically as the dialectical-classification overlay across both component passes of Argument Audit.)

## Open debates

T1 carries three debates that the modes engage analytically without adjudication.

### Debate D1 — Is "fallacy" a property of the argument, or a property of the dialogue?

The classical (Aristotelian, Copi-textbook) tradition treats fallacy as a property of the argument: an inferential move fails because of its form or because its premises do not support its conclusion, independently of dialogue context. The pragma-dialectical tradition (van Eemeren & Grootendorst) treats fallacy as a violation of rules for critical discussion: the same inferential move can be a legitimate strategic manoeuvre in one dialogue type and a fallacy in another. Walton's pragmatic / dialectical theory occupies a middle position: argumentation schemes carry critical questions whose negative answers can defeat the argument, and the dialogue type (persuasion, inquiry, negotiation, deliberation, information-seeking, eristic) determines which critical questions are in scope. Hamblin's *Fallacies* (1970) opened the debate by exposing the textbook tradition as theoretically degenerate, and the debate has not been settled.

**Disposition.** Coherence Audit operates without adjudicating: it applies Toulmin reconstruction (warrant-based, neutral on dialogue type) as the primary lens, layers Walton's argumentation-scheme critical questions on top (which carry dialogue-type sensitivity implicitly), and flags fallacy claims as "the argument as given does not establish its conclusion via this inferential move" rather than as "the speaker has committed [named fallacy] in absolute terms." Compatible with both readings while remaining noncommittal.

**Citations.** Hamblin 1970 *Fallacies*; Walton 1995 *A Pragmatic Theory of Fallacy*; van Eemeren & Grootendorst 2004 *A Systematic Theory of Argumentation*; Hansen, "Fallacies," *Stanford Encyclopedia of Philosophy*.

### Debate D2 — Motte-and-bailey: fallacy or doctrine?

Shackel (2005, "The Vacuity of Postmodernist Methodology") introduced the term as a *doctrine* — a structural feature of certain argumentative positions in which an arguer alternates between a defensible "motte" (modest claim) and a desirable "bailey" (ambitious claim) when challenged. Shackel's preferred usage frames motte-and-bailey as a *characterization of a doctrine's structure*, not as a fallacy committed in a single inferential step. In wider usage (online discourse, popular argumentation guides), the term has come to function as a *fallacy label* applied to single moves where an arguer retreats from an ambitious claim under pressure.

**Disposition.** Argument Audit operates without adjudicating: when motte-and-bailey is invoked, the audit names the structural move in the argument's terms (which claim is motte, which is bailey, where the alternation occurs) rather than relying on the label alone, and notes whether Shackel's doctrinal usage or the wider fallacy-label usage best fits the case. Stricter Shackel-aligned reading treats motte-and-bailey invocations as doctrinal characterizations requiring multi-claim evidence; wider sense may accept single-move applications.

**Citations.** Shackel 2005; cf. wider discussion in popular argumentation literature.

### Debate D5 — Is Stanley's *How Propaganda Works* politically neutral or directional?

The book's diagnostic apparatus (supporting / undermining distinction; flawed-ideology precondition; not-at-issue content) is offered as politically neutral analytical machinery, applicable to any artifact regardless of political orientation. Sympathetic readings (much of the academic philosophy-of-language reception) treat the apparatus as neutral and the case studies as illustrative. Skeptical readings (visible in popular reception, including conservative-tradition reviewers) argue that the apparatus is built around a left-liberal canon of paradigm cases (Birth of a Nation; Fox News; Trump-era discourse) and that this case-base inflects the apparatus toward asymmetric application — i.e., that the diagnostic catches right-wing propaganda more readily than structurally-equivalent left-wing instances. A third reading (Lear and others in epistemology of testimony) treats the apparatus as defensible-but-incomplete: Stanley's framework illuminates one important class of propaganda (undermining demagoguery) without exhausting the propaganda phenomenon.

**Disposition.** Propaganda Audit operates without adjudicating the debate: it applies Stanley's distinctions as analytical lens (treating "supporting" and "undermining" as useful descriptors for argumentatively distinct propaganda structures) while remaining agnostic on whether Stanley's case-base inflects the apparatus directionally. The mode's symmetry guardrails (motive-attribution-without-evidence as named failure; propaganda-charge-as-refutation as named failure) are designed to mitigate the asymmetric-application risk regardless of which side of the debate one finds more persuasive.

**Citations.** Stanley 2015 *How Propaganda Works*; Lear 2017 in *Mind*; popular-reception reviews on Goodreads and conservative-tradition outlets surveyed but not adjudicated.

## Citations and source-tradition attributions

Aggregated from member mode specs and lens files.

**Argumentation theory.**
- Toulmin, Stephen (1958/2003). *The Uses of Argument*. Cambridge University Press.
- Toulmin, Stephen, Richard Rieke, and Allan Janik (1979). *An Introduction to Reasoning*. Macmillan.
- Walton, Douglas, Chris Reed, and Fabrizio Macagno (2008). *Argumentation Schemes*. Cambridge University Press.
- Walton, Douglas (1995). *A Pragmatic Theory of Fallacy*. University of Alabama Press.
- Walton, Douglas (1996). *Argumentation Schemes for Presumptive Reasoning*. Lawrence Erlbaum.
- Hamblin, C.L. (1970). *Fallacies*. Methuen.
- van Eemeren, Frans H., and Rob Grootendorst (2004). *A Systematic Theory of Argumentation*. Cambridge University Press.
- Shackel, Nicholas (2005). "The Vacuity of Postmodernist Methodology." *Metaphilosophy* 36(3):295–320.
- Hitchcock, David, and Bart Verheij, eds. (2006). *Arguing on the Toulmin Model*. Springer.
- Macagno, Fabrizio, and Douglas Walton (2014). *Emotive Language in Argumentation*. Cambridge University Press.

**Frame analysis and cognitive linguistics.**
- Lakoff, George, and Mark Johnson (1980). *Metaphors We Live By*. University of Chicago Press.
- Lakoff, George (1987). *Women, Fire, and Dangerous Things*. University of Chicago Press.
- Lakoff, George, and Mark Johnson (1999). *Philosophy in the Flesh*. Basic Books.
- Lakoff, George (1996/2002). *Moral Politics*. University of Chicago Press.
- Lakoff, George (2004). *Don't Think of an Elephant!*. Chelsea Green.
- Fillmore, Charles J. (1982). "Frame semantics." In *Linguistics in the Morning Calm*. Hanshin Publishing.
- Kövecses, Zoltán (2010). *Metaphor: A Practical Introduction* (2nd ed.). Oxford University Press.
- Goffman, Erving (1974). *Frame Analysis*. Harvard University Press.
- Goffman, Erving (1959). *The Presentation of Self in Everyday Life*. Doubleday.
- Bateson, Gregory (1955/1972). "A Theory of Play and Fantasy." In *Steps to an Ecology of Mind*.
- Tannen, Deborah (1993). *Framing in Discourse*. Oxford University Press.
- Snow, David A. & Benford, Robert D. (1988). "Ideology, Frame Resonance, and Participant Mobilization." *International Social Movement Research* 1:197–217.
- Entman, Robert M. (1993). "Framing: Toward Clarification of a Fractured Paradigm." *Journal of Communication* 43(4):51–58.
- Entman, Robert M. (2004). *Projections of Power*. University of Chicago Press.
- Iyengar, Shanto (1991). *Is Anyone Responsible?* University of Chicago Press.
- Reese, Stephen D., Gandy, Oscar H. & Grant, August E. (eds.) (2001). *Framing Public Life*. Lawrence Erlbaum.

**Propaganda theory.**
- Stanley, Jason (2015). *How Propaganda Works*. Princeton University Press.
- Stanley, Jason (2018). *How Fascism Works*. Random House.
- Stanley, Jason (2011). *Knowledge and Practical Interests*. Oxford University Press.
- Bernays, Edward L. (1928). *Propaganda*. Horace Liveright.
- Ellul, Jacques (1962/1965). *Propaganda: The Formation of Men's Attitudes*. Knopf.
- Herman, Edward S., and Noam Chomsky (1988). *Manufacturing Consent*. Pantheon.
- Khoo, Justin (2017). "Code words in political discourse." *Philosophical Topics* 45(2):33–64.
- Mendelberg, Tali (2001). *The Race Card*. Princeton University Press.
- Lear, J. (2017). Review essay in *Mind* (engagement with Stanley *How Propaganda Works*).

**Reference works.**
- Hansen, Hans. "Fallacies." *Stanford Encyclopedia of Philosophy* (continuously revised).

*End of Framework — Argumentative Artifact Examination.*
