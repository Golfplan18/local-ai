
# Framework — Conceptual Clarification

*Self-contained framework for taking a concept, term, or definitional disagreement as input and resolving, sharpening, engineering, or genealogically tracing it. Compiled 2026-05-01 from territory entry, member mode specs, lens dependencies, and open debates.*

---

## Territory Header

- **Territory ID:** T10
- **Name:** Conceptual Clarification
- **Super-cluster:** A (Argument and Reasoning)
- **Characterization:** Operations that take a concept, term, or definitional disagreement as input and resolve, sharpen, engineer, or genealogically trace it.
- **Boundary conditions:** Input is a concept whose meaning, scope, or normative status is in question. Excludes ordinary-language exposition where the concept is uncontested.
- **Primary axis:** Stance (descriptive vs. ameliorative vs. essentially-contested).
- **Secondary axes:** Depth (light Deep Clarification → Conceptual Engineering thorough).

## When to use this framework

Use when the question is what a concept means, how it should be revised, or whether the dispute is essentially contested. Plain-language triggers:

- "Why does X work that way?" / "Explain the mechanics of."
- "What's really going on underneath?"
- "I want depth, not orientation."
- "The current definition of this concept isn't doing the work it should."
- "I want to redesign what this term means for our purposes."
- "The inherited concept is causing problems and we should engineer a better one."
- "The word is being used in incompatible ways and we need to choose."
- "What does the author even mean by 'freedom' here?"

Do not route here when the user is unfamiliar with a domain and needs orientation (T14 — Quick Orientation / Terrain Mapping); when the concept is embedded in a specific argument whose soundness is at issue (T1); when the concept is embedded in a paradigm whose framing is at issue (T9); when the concept is technical with a settled stipulative definition (no engineering needed).

## Within-territory disambiguation

```
Q1 (stance): "Are you trying to clarify what the concept already means in current usage,
              or trying to engineer the concept toward what it should mean
              (sometimes called ameliorative work)?"
  ├─ "clarify current usage" → deep-clarification (Tier-2, ordinary-language)
  ├─ "engineer toward what it should mean" → conceptual-engineering
                                              (Tier-2, Cappelen/Plunkett)
  ├─ "the concept is essentially contested across users / no single right meaning" →
        definitional-dispute (deferred per CR-6, Gallie)
  └─ ambiguous → deep-clarification with escalation hook to conceptual-engineering
```

**Default route.** `deep-clarification` at Tier-2 when ambiguous (the descriptive baseline; ameliorative and essentially-contested variants are stance escalations).

**Escalation hooks.**
- After `deep-clarification`: if clarification reveals the concept is doing normative work that needs revision, hook sideways to `conceptual-engineering`.
- After `conceptual-engineering`: if the engineered version cannot be agreed because users' values diverge, hook sideways to `definitional-dispute` (deferred — surface the flag).
- After any T10 mode: if the concept-clarification is a precursor to argument evaluation, hook sideways to T1.
- After any T10 mode: if the concept is embedded in a paradigm dispute, hook sideways to T9.

## Mode entries

### Mode — deep-clarification

- **Educational name:** deep conceptual clarification (ordinary-language tradition)
- **Plain-language description:** A descriptive thorough clarification of what a concept currently means, pushed two levels deeper than the user's starting depth. The mode begins with a surface explanation, then provides mechanistic clarification two levels deeper (each level a genuine mechanism beneath, not horizontal detail at the same level), marks the epistemic boundary (where settled knowledge ends and current-best-understanding begins), and identifies practical implications (the deeper understanding changes what the user would do or conclude).

- **Critical questions:**
  1. Is each successive level a genuine mechanism beneath, or is it horizontal detail at the same level?
  2. Has the epistemic boundary been marked — where settled knowledge ends and current-best-understanding begins?
  3. Does the deeper understanding change what the user would do or conclude — is there a practical implication?

- **Per-pipeline-stage guidance:**
  - **Depth.** Each successive level a genuine mechanism beneath; depth is vertical, not horizontal; ≥2 levels beneath user's starting depth.
  - **Breadth.** Survey the concept's neighborhood — adjacent concepts, alternative formulations, the concept's history of refinement.
  - **Evaluation.** Three critical questions plus failure modes (lateral-drift-trap, elaboration-trap, jargon-trap, false-certainty, academic-drift).
  - **Consolidation.** Four required sections in prose: surface explanation; mechanistic clarification two levels deeper; epistemic boundary; practical implications.
  - **Verification.** Each level a genuine mechanism beneath the previous; epistemic boundary marked; practical implication identified.

- **Source tradition:** Ordinary-language philosophy tradition (Wittgenstein, Austin, Ryle); first-principles reasoning (Aristotle, Descartes, Feynman); Feynman technique for explanation (explain to a novice level by level).

- **Lens dependencies:**
  - `ordinary-language-clarification`: Begin with how the concept is actually used; resist premature stipulation; trace the concept's grammar (in Wittgenstein's sense — the patterns of legitimate use); distinguish the concept from its applications.
  - `first-principles-decomposition`: Decompose the concept into its constituent commitments; identify what is taken as given vs. what is derived; rebuild the concept from primitives where derivation has obscured structure.

### Mode — conceptual-engineering

- **Educational name:** conceptual engineering (Cappelen-Plunkett ameliorative analysis)
- **Plain-language description:** An ameliorative pass that takes a concept failing to do what it should and proposes a revision. The mode names the target concept, maps the current usage descriptive baseline (so revision is responsive to actual usage rather than a strawman), itemizes function failures, articulates the ameliorative purpose as a *function* the revised concept should serve (not as a stipulation that smuggles in conclusions), proposes candidate revisions with rationale, acknowledges the implementation problem (the gap between proposing a revision and getting communities to adopt it — Cappelen 2018's challenge), and surfaces revision costs (what current uses, distinctions, or commitments would be lost or displaced). The mode does not pretend that proposal equals adoption.

- **Critical questions:**
  1. Has the ameliorative purpose been articulated as something the revised concept should *do* (a function it should serve), rather than as a stipulation that smuggles in conclusions?
  2. Has the current concept's descriptive baseline been mapped before the ameliorative move, so the revision is responsive to actual usage rather than to a strawman?
  3. Has the implementation problem been acknowledged — i.e., the gap between proposing a revision and actually getting communities to adopt it (Cappelen 2018's challenge) — rather than treating the proposal as if proposal-equals-adoption?
  4. Have revision costs been surfaced — what current uses, distinctions, or commitments would be lost or displaced by the proposed engineering?

- **Per-pipeline-stage guidance:**
  - **Depth.** Function-articulated purpose (not stipulation); descriptive baseline mapped; implementation problem acknowledged; revision costs surfaced.
  - **Breadth.** Survey the conceptual landscape around the target — adjacent concepts that would shift under revision; alternative engineering moves the same problem might admit; prior engineering attempts; normative frameworks that motivate or resist revision.
  - **Evaluation.** Four critical questions plus failure modes (stipulation-smuggle, baseline-skip, implementation-blindness, cost-blindness, ameliorative-overreach).
  - **Consolidation.** Eight required sections: target concept named; current usage descriptive baseline; identified function failures; ameliorative purpose; candidate revisions with rationale; implementation problem acknowledgment; revision costs and displacement; confidence per finding.
  - **Verification.** Target concept named; current usage baseline mapped; function failures itemized; ameliorative purpose function-shaped; ≥1 candidate revision proposed with rationale; implementation problem acknowledged; revision costs surfaced.

- **Source tradition:** Cappelen *Fixing Language* (2018); Plunkett & Sundell "Disagreement and the Semantics of Normative and Evaluative Terms" *Philosophers' Imprint* (2013); Haslanger *Resisting Reality* (2012) for ameliorative analysis with social-political engagement; Burgess & Plunkett "Conceptual Ethics" *Philosophy Compass* (2013).

- **Lens dependencies:**
  - `cappelen-plunkett-conceptual-engineering`: Three-step structure — (1) descriptive analysis of how the concept currently functions; (2) normative analysis of what function the concept should serve; (3) prescriptive proposal for revision. Implementation problem (Cappelen 2018): even if a philosopher correctly identifies a needed revision, there is no clear mechanism by which the revision is taken up by language users.
  - `haslanger-ameliorative-analysis`: Ameliorative analysis as continuous with social and political contestation. Concept revision happens through use in argument, education, legislation, and movement-building rather than philosopher-fiat. More optimistic about implementation than Cappelen, with the optimism conditional on engagement with social-political mechanisms.
  - Optional: `gallie-essentially-contested-concepts` (when the concept's contestation is essential rather than resolvable).

## Cross-territory adjacencies

**T10 ↔ T1 (Argumentative Artifact).** "Is the issue with how the argument deploys a specific concept (clarify the concept first), or with how the argument coheres given any reasonable reading of the concept?" Concept-precision issue → T10; argument-coherence issue → T1. When concept clarification is needed before argument audit can proceed, T10 runs first; T1 follows on the now-clarified version.

**T10 ↔ T9 (Paradigm Examination).** When the concept is embedded in a paradigm dispute (the concept's contestation is paradigm-level), route to T9.

## Lens references

### ordinary-language-clarification

**Core insight.** Begin with how the concept is actually used in everyday and technical practice. The concept's *meaning* is constituted by its patterns of use — its grammar, in Wittgenstein's sense. Premature stipulation (defining the concept top-down before observing its use) often produces a definition that misses what is actually doing the conceptual work.

**Operational protocol.**
1. Survey the concept's actual uses in relevant contexts (everyday, technical, philosophical, professional).
2. Identify the patterns of legitimate use — what the concept is doing, what distinctions it draws, what work it accomplishes for its users.
3. Distinguish the concept from its applications — the concept of *justice* is not the same as the application of justice in particular cases.
4. Resist the urge to define the concept until usage has been mapped.
5. When defining, define in terms that respect the patterns of use rather than stipulating a definition that overrides them.

**Tradition.** Wittgenstein *Philosophical Investigations* (1953); Austin *How to Do Things with Words* (1962); Ryle *The Concept of Mind* (1949); Cavell *The Claim of Reason* (1979).

### first-principles-decomposition

**Core insight.** When a concept has accumulated derivations, applications, and overlays, the structure beneath may be obscured. First-principles decomposition rebuilds the concept from its constituent commitments — what is taken as given, what is derived, and how the derivations connect.

**Operational protocol.**
1. Identify the concept's stated definition and its surface components.
2. Distinguish *primitives* (what is taken as given, not further analyzed within this concept) from *derivations* (what is constructed from the primitives).
3. Trace each derivation to its primitive grounds.
4. Audit the primitives — are they themselves stable, or do they admit further decomposition?
5. Rebuild the concept from primitives, surfacing dependencies that the surface definition obscured.

**Tradition.** Aristotle on first principles; Descartes *Meditations* (clear and distinct ideas); Feynman on the explanation test (if you can't explain it from first principles to a novice, you don't understand it).

### cappelen-plunkett-conceptual-engineering

**Core structure.** Three-step ameliorative analysis:
1. *Descriptive.* How does the concept currently function in actual usage?
2. *Normative.* What function should the concept serve, given our purposes?
3. *Prescriptive.* What revision would make the concept better serve the normative function?

**The implementation problem (Cappelen 2018, *Fixing Language*).** Even if the philosopher correctly identifies that a concept should be revised and articulates a better one, there is no clear mechanism by which the revision is taken up by language users. Concepts are decentralized, distributed across speakers and contexts, and resistant to top-down redesign. The engineering move risks being academically satisfying but practically inert.

**Application.** Revision proposals must acknowledge the implementation problem rather than treat proposal-as-adoption. The acknowledgment may take different forms depending on whether the user is engineering for their own work (where the user is the adopter and implementation is straightforward) or proposing for a wider community (where coordination problems loom).

**Common misapplications.** Stipulation-smuggle (treating "the concept should classify X as Y" as a function rather than as a desired conclusion); baseline-skip (proposing revision without mapping current usage); implementation-blindness (treating proposal-as-adoption); cost-blindness (dismissing current uses without analysis).

### haslanger-ameliorative-analysis

**Core structure.** Ameliorative analysis as continuous with social and political contestation. Concepts are not just objects of philosophical analysis; they are tools deployed in argument, education, legislation, and movement-building. Revision happens through use in these contexts rather than through philosopher-fiat.

**Worked example.** Haslanger's analysis of *gender* and *race* as ameliorative concepts — the question is not "what does 'gender' currently mean?" (descriptive) but "what should the concept of gender do, for the purposes of political and analytical work, given the social structures of gender oppression?" (ameliorative). The revision is not adopted by stipulation; it is adopted (or resisted) through political contestation.

**Implementation orientation.** More optimistic than Cappelen's pessimism, but the optimism is conditional on engagement with social-political mechanisms. Engineers who treat their proposals as merely linguistic recommendations will see them ignored; engineers who treat their proposals as moves in social-political contestation may see uptake through contestation.

**Tradition.** Haslanger *Resisting Reality* (2012); Haslanger "Going on, not in the same way" (2020); MacKinnon's earlier critical work on the politics of definition.

### gallie-essentially-contested-concepts

**Core insight.** Some concepts are *essentially contested* — their proper application is genuinely disputed, the disputes are not resolvable by appeal to evidence or reason, and the contestation is essential to the concept's role in social-political life. Gallie's examples include *art*, *democracy*, *Christian doctrine*, *social justice*.

**Necessary characteristics of essential contestation.** (1) The concept is *appraisive* (its application implies endorsement or condemnation). (2) The concept is *internally complex* (multiple criteria contribute to application). (3) The concept admits *multiple competing weightings* of its component criteria. (4) The concept's exemplars are open to *modification under changing circumstances*. (5) Each user *acknowledges* that other users contest the concept's application. (6) The contestation is *socially productive* — it supports the kind of debate the concept exists to make possible.

**Application.** When a concept resists both descriptive clarification (different users mean different things) and ameliorative engineering (proposed revisions face contestation rather than uptake), the essential-contestation diagnosis applies. The mode does not adjudicate the contestation but documents its structure: which criteria each user weights, which exemplars each user emphasizes, why the contestation is socially productive.

**Tradition.** Gallie *Philosophical Papers* (1956) for the originating article; Connolly *The Terms of Political Discourse* (1974) for political-theoretic application; Waldron *Law and Disagreement* (1999) for the legal-philosophical extension.

## Open debates

### Debate D7 — The implementation problem (Cappelen 2018 vs. Haslanger)

Cappelen's *Fixing Language* (2018) argues that conceptual engineering faces a fundamental implementation problem: even if a philosopher correctly identifies that a concept should be revised and articulates a better one, there is no clear mechanism by which the revision is taken up by language users. Concepts are decentralized, distributed across speakers and contexts, and resistant to top-down redesign; the engineering move risks being academically satisfying but practically inert.

Haslanger's earlier ameliorative analysis (2012, 2020) is more optimistic about implementation: she treats ameliorative analysis as continuous with social and political contestation, where revised concepts gain uptake through use in argument, education, legislation, and movement-building rather than through philosopher-fiat.

**Disposition.** The `conceptual-engineering` mode does not adjudicate the debate. It requires acknowledgment of the implementation problem (per the implementation-blindness failure mode) without prescribing the Cappelen-pessimist or Haslanger-engaged response. When the user is doing engineering for use within their own work or organization, the implementation problem may shrink (the user is the adopter); when proposing revision for a wide community, the problem looms larger and should be foregrounded.

**Note on D7's territory location.** D7 lives in the `conceptual-engineering` mode spec but is territory-relevant: the implementation problem is relevant whenever ameliorative work is in scope, including in border cases where the deep-clarification mode surfaces a normative tension that suggests escalation to conceptual-engineering.

**Citations.** Cappelen 2018 *Fixing Language*; Haslanger 2012 *Resisting Reality*; Haslanger 2020 "Going on, not in the same way" *Aristotelian Society Supplementary Volume*.

## Citations and source-tradition attributions

**Ordinary-language tradition.**
- Wittgenstein, Ludwig (1953). *Philosophical Investigations*. Blackwell.
- Austin, J.L. (1962). *How to Do Things with Words*. Oxford University Press.
- Ryle, Gilbert (1949). *The Concept of Mind*. Hutchinson.
- Cavell, Stanley (1979). *The Claim of Reason*. Oxford University Press.

**Conceptual engineering and ameliorative analysis.**
- Cappelen, Herman (2018). *Fixing Language: An Essay on Conceptual Engineering*. Oxford University Press.
- Cappelen, Herman, David Plunkett, and Alexis Burgess, eds. (2020). *Conceptual Engineering and Conceptual Ethics*. Oxford University Press.
- Plunkett, David, and Tim Sundell (2013). "Disagreement and the Semantics of Normative and Evaluative Terms." *Philosophers' Imprint* 13(23):1–37.
- Haslanger, Sally (2012). *Resisting Reality: Social Construction and Social Critique*. Oxford University Press.
- Haslanger, Sally (2020). "Going on, not in the same way." *Aristotelian Society Supplementary Volume* 94(1):37–72.
- Burgess, Alexis, and David Plunkett (2013). "Conceptual Ethics I & II." *Philosophy Compass* 8(12):1091–1110.

**Essentially contested concepts.**
- Gallie, W.B. (1956). "Essentially Contested Concepts." *Proceedings of the Aristotelian Society* 56:167–198.
- Connolly, William E. (1974/1993). *The Terms of Political Discourse* (3rd ed.). Princeton University Press.
- Waldron, Jeremy (1999). *Law and Disagreement*. Oxford University Press.

*End of Framework — Conceptual Clarification.*
