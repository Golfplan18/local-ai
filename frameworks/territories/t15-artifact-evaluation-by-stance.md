# Framework — Artifact Evaluation by Stance

*Self-contained framework for evaluating a plan, proposal, idea, or course of action by adopting a defined stance — constructive (Steelman, Benefits), neutral (Balanced Critique), or adversarial (Red Team). Compiled 2026-05-01.*

---

## Territory Header

- **Territory ID:** T15
- **Name:** Artifact Evaluation by Stance
- **Super-cluster:** D (Position, Stakeholder, and Strategy)
- **Characterization:** Operations that take a plan, proposal, idea, or course of action and evaluate it by adopting a defined stance — constructive (Steelman, Benefits), adversarial (Red Team), or neutral (Balanced Critique).
- **Boundary conditions:** Input is a plan, proposal, idea, or argument-as-proposal. The user wants the artifact evaluated *as a proposal*. Excludes evaluating an argument *as an argument for soundness* (T1 — Coherence Audit, Frame Audit, Argument Audit). Excludes structural-fragility audits with no adversary (T7).
- **Primary axis:** Stance (constructive-strong → constructive-balanced → neutral → adversarial-light → adversarial-actor-modeling).
- **Secondary axes:** Depth (atomic across the stance gradient).
- **Coverage status:** Strong after Wave 1 (Devil's Advocate Lite deferred per CR-6).

---

## When to use this framework

Use T15 when the user has an artifact (plan, proposal, idea, design, argument-as-proposal) and wants it evaluated *as a proposal* with a particular stance. T15 answers questions like "make the strongest case for this", "stress-test this adversarially", "give me a balanced read", "what are the pros and cons", and "argue against this for me".

T15 does NOT do soundness audit of an argument-as-argument (that is T1), structural-fragility audit independent of any adversary (that is T7), nor frame-of-the-issue analysis (that is T9).

---

## Within-territory disambiguation

```
[Territory identified: evaluating a plan, proposal, idea, or course of action]

Q1 (stance): "Want the strongest case for it, the strongest case against it,
              a balanced look weighted toward positives,
              a neutral look at both sides,
              or a quick devil's advocate (not a full hostile-actor stress test)?"
  ├─ "for it / strongest possible case" → steelman-construction
                                           (cross-reference: T1 if the artifact
                                            is itself an argument)
  ├─ "against it / hostile actor stress test" →
       Q1a (red-team operation): "for own decision (assessment) or for external use (advocate)?"
         ├─ "own decision / fix list" → red-team-assessment (default)
         ├─ "argue against / ammunition / debate prep" → red-team-advocate
         └─ ambiguous → red-team-assessment with escalation hook to red-team-advocate
  ├─ "balanced (positives weighted)" → benefits-analysis
  ├─ "balanced (neutral)" → balanced-critique
  ├─ "quick devil's advocate, not full hostile actor" → devils-advocate-lite
                                                          (deferred per CR-6)
  └─ ambiguous → balanced-critique (the neutral Tier-2 default per §5.6)
```

**Default route.** `balanced-critique` at Tier-2 when ambiguous (per §5.6 the neutral stance is the default when the user has not signaled).

**Escalation hooks.**
- After `steelman-construction`: if the user wants the opposite-stance counterpoint, hook sideways to `red-team-assessment` (own decision) or `red-team-advocate` (external use).
- After `red-team-assessment`: if the user wants the constructive counterpoint, hook sideways to `steelman-construction`. If the user shifts from own-decision framing to building a brief for external use, hook sideways to `red-team-advocate`.
- After `red-team-advocate`: if the user wants the constructive counterpoint, hook sideways to `steelman-construction`. If the user shifts back to wanting their own vulnerabilities surfaced for fix-prioritisation, hook sideways to `red-team-assessment`.
- After `benefits-analysis`: if drawbacks need fuller treatment, hook sideways to `balanced-critique` or `red-team-assessment` / `red-team-advocate`.
- After `balanced-critique`: if the user wants either pole pushed harder, hook sideways to `steelman-construction` or `red-team-assessment` / `red-team-advocate`.
- After any T15 mode: if the artifact is itself an argument and the question becomes argument-soundness rather than proposal-evaluation, hook sideways to T1.
- After either red-team mode: if the question is really about structural fragility rather than adversary trying to defeat, hook sideways to T7 (`fragility-antifragility-audit`).

---

## Steelman cross-reference note (Decision G)

**Steelman Construction's home is T15** (its primary work is stance-bearing artifact evaluation — constructing the strongest version of a proposal). When the artifact under steelmanning is itself an argument, the **T1 cross-reference** activates so that argument-coherence considerations inform the steelmanned reconstruction. The mode is *not* dual-citizened — home is T15; T1 is consulted as cross-reference.

Disambiguating question for the T1↔T15 Steelman case: "Want me to evaluate the argument's *soundness* (does it hold up?), or *evaluate the proposal* with a particular stance (steelman / push back / weigh both)?"
- Soundness evaluation → T1 (Coherence Audit / Frame Audit / Argument Audit).
- Stance-bearing evaluation → T15 (Steelman / Benefits / Balanced Critique / Red Team).
- "Steelman this argument." → T15 (home), with T1 cross-reference active because the artifact is an argument.

---

## Mode entries

### `steelman-construction` — Steelman Construction

**Educational name:** strongest-case construction (steelman) (stance-constructive-strong).

**Plain-language description.** Reconstructs a position at its logical best — surfacing hidden premises that would make the argument stronger, filling logical gaps with the most charitable inferences, marshalling the best available evidence. The mirror test governs: would a thoughtful proponent endorse the reconstruction, or recognize their argument weakened? Construction completes fully before critique begins; critique addresses only the strongest version (no retreat to the weaker original); at least two points of agreement with the user's own view are surfaced.

**Critical questions.**
- CQ1: Would a thoughtful proponent endorse the reconstruction (mirror test), or recognize their argument weakened?
- CQ2: Is the steelman recognizably the same argument strengthened, or has it drifted into a different argument the analyst prefers?
- CQ3: Does the critique address only the steelmanned version, or does it retreat to the weaker original at any point?
- CQ4: Was the steelman built fully before critique began, or were construction and critique entangled?

**Per-pipeline-stage guidance.**
- **Analyst.** Reconstruct the position at its logical best; pass the mirror test; identify ≥2 points of agreement with the user's stated view; produce the critique addressing only the steelman; conclude with survival assessment.
- **Evaluator.** Apply mirror test; verify identity preservation; verify critique-targets-steelman-only; verify construction-before-critique; flag tinman-trap, identity-loss, retreat-to-original, steel-strawman, projection-trap, entangled-construction.
- **Reviser.** Strengthen reconstruction wherever a thoughtful proponent would recognize weakness; re-anchor to original claim where steelman drifted; rewrite critique passages that retreat to weaker original; resist "balanced" presentation (the mode is asymmetric by design).
- **Verifier.** Confirm six required sections (original_position, steelmanned_reconstruction, strength_identification, points_of_agreement, critique_of_the_steelman, survival_assessment); confirm prose-only (no envelope).
- **Consolidator.** Merge as prose with original-position paragraph bounded (≤ ⅓ of total steelman section length).

**Source tradition.** Rapoport rules of engagement (steelman before critique); Dennett charitable interpretation.

**Lens dependencies.**
- Required: none.
- Optional: rapoport-rules-of-engagement, dennett-charitable-interpretation.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

### `benefits-analysis` — Benefits Analysis

**Educational name:** balanced benefits-and-strengths analysis (PMI — plus, minus, interesting) (stance-constructive-balanced).

**Plain-language description.** Three-column de Bono PMI (Plus, Minus, Interesting) on a single proposal. Plus column lists benefits with mechanism per claim; Minus column lists costs/risks with specifics; Interesting column captures non-obvious second-order implications (precedent, signaling, path-dependency). An affected-parties map surfaces asymmetries (Plus for one party, Minus for another). Evidence quality is noted. Most-consequential per column is annotated. Recommendation field is empty by default — Benefits Analysis presents the envelope; the user decides.

**Critical questions.**
- CQ1: Are all three PMI columns populated, or has the analysis collapsed into Plus/Minus only?
- CQ2: Are claims grounded in the user's specific case, or generic boilerplate?
- CQ3: Has the Interesting column captured at least one second-order implication, or explicitly noted that none was identified?
- CQ4: Have asymmetries (Plus for one party, Minus for another) been surfaced via the affected-parties map?
- CQ5: Has the analysis avoided unsolicited recommendation — presenting the envelope rather than rendering a verdict?

**Per-pipeline-stage guidance.**
- **Analyst.** Populate three columns; ground each claim in user's specifics; capture ≥1 second-order implication in Interesting; map affected parties; surface ≥1 asymmetry; do NOT recommend unless user asked.
- **Evaluator.** Apply five critical questions; verify Verdict Trap not triggered (the load-bearing failure mode for this stance).
- **Reviser.** Add specificity where claims are generic; populate Interesting column where missing; remove recommendation language where user did not ask; resist false symmetry.
- **Verifier.** Confirm seven required sections (proposal_stated_precisely, plus_column, minus_column, interesting_column, affected_parties_map, evidence_quality_note, most_consequential_per_column).
- **Consolidator.** Merge as a structured three-column output with affected-parties map and most-consequential annotations.

**Source tradition.** de Bono PMI (Plus / Minus / Interesting); stakeholder incidence analysis.

**Lens dependencies.**
- Required: debono-pmi.
- Optional: stakeholder-incidence-analysis, second-order-effects-catalog (precedent / signaling / path-dependency).
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

### `balanced-critique` — Balanced Critique

**Educational name:** balanced critique (neutral stance, multi-perspective) (stance-neutral).

**Plain-language description.** Neutral evaluation with comparable rigor on strengths and weaknesses. Strengths-with-evidence and weaknesses-with-evidence are emitted as comparable structures (matching depth, matching evidence-citation conventions). Perspective-dependent findings are flagged with stakeholder vantage. Residual tensions are named in the net assessment rather than collapsed into a tidy verdict. Claims are backed by specific evidence from the artifact, not by analyst preference. The mode's neutrality is in evaluative method, not in artificial 50/50 symmetry.

**Critical questions.**
- CQ1: Have strengths and weaknesses been surfaced with comparable rigor?
- CQ2: Have findings that are perspective-dependent been flagged as such, rather than asserted as universal?
- CQ3: Have residual tensions been named in the net assessment, or has synthesis collapsed them into a tidy verdict?
- CQ4: Are claims of strength and weakness backed by specific evidence from the artifact, rather than asserted by analyst preference?

**Per-pipeline-stage guidance.**
- **Analyst.** Survey strengths and weaknesses with matching evidence depth; flag perspective-dependent findings with stakeholder vantage; name residual tensions in net assessment; back every claim with artifact-specific evidence.
- **Evaluator.** Verify symmetric rigor on strengths and weaknesses; verify perspective-dependence flagged; verify residual tensions named; verify evidence-backed claims; flag stance-tilt, false-universality, premature-resolution, opinion-as-evaluation, bothsidesism.
- **Reviser.** Restore symmetric rigor where draft tilted; flag perspective-dependent findings where universal claims made; surface residual tensions where collapsed; resist artificial 50/50 balance when artifact is genuinely asymmetric.
- **Verifier.** Confirm seven required sections (artifact_summary_one_paragraph, strengths_with_evidence, weaknesses_with_evidence, assumptions_and_uncertainties, perspective_dependent_findings, net_assessment_with_residual_tensions_named, confidence_per_finding).
- **Consolidator.** Merge as a structured synthesis with comparable-depth strengths and weaknesses sections.

**Source tradition.** Rumelt strategy kernel (when artifact is a strategy document); de Bono PMI (Plus-Minus-Interesting as light scaffolding); Ulrich CSH boundary categories (when boundary-critique surfaces in perspective-dependent section).

**Lens dependencies.**
- Required: none.
- Optional: rumelt-strategy-kernel, de-bono-pmi, ulrich-csh-boundary-categories.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

### `red-team-assessment` — Red Team (Assessment)

**Educational name:** adversarial vulnerability assessment for own decision (red team, assessment stance) (stance-adversarial-actor-modeling-assessment).

**Plain-language description.** Adversarial stress test ranking vulnerabilities by severity for the user's own fix-prioritisation. The mode answers: "What's wrong with this artifact, ranked by severity, so I know what to fix before I commit?" Input Sufficiency Protocol runs first: identifiable artifact, bounded scope, sufficient specificity, diagram legibility — if conditions fail, emit three-part redirect (What I see / What's missing / Three options with override) instead of attacking. Each vulnerability requires artifact-specific grounding (Why this is real with quotes where possible), severity (Showstopper/Major/Caveat), surface (Internal/External), an actionable fix recommendation, and a fix-feasibility note (user-implementable / requires-outside-resources / structural-redesign-needed). Attack-Failure Disclosure names attack classes attempted that produced no findings — honest attack failure is more valuable than manufactured findings. Severity-floor declaration when no Major/Showstopper findings surface. The mode's signature failure is "pulled punches" — softening real vulnerabilities to spare the user.

**Critical questions.**
- CQ1: Does each vulnerability have artifact-specific grounding, or are findings manufactured?
- CQ2: Is severity calibration honest (no inflation to feel productive, no deflation to spare the user)?
- CQ3: Is each fix recommendation actionable by the user?
- CQ4: Has fix-feasibility been assessed per vulnerability?
- CQ5: Does the Attack-Failure Disclosure name attack classes attempted that produced no findings?
- CQ6: Does the attack stay within the artifact's framework, or drift into framework-level critique?
- CQ7: If Input Sufficiency override was invoked, is every finding flagged as low-specificity?

**Per-pipeline-stage guidance.**
- **Analyst.** Run Input Sufficiency Protocol; emit redirect if fails; declare "Stance: assessment"; restate artifact with quotes; produce vulnerability findings with severity, surface, fix recommendation, and fix-feasibility; produce Attack-Failure Disclosure; declare severity-floor when no Major/Showstopper findings.
- **Evaluator.** Apply seven critical questions; verify finding grounding (sycophantic-inverse self-check); verify severity calibration honesty; verify fix-actionability and fix-feasibility per vulnerability; verify Attack-Failure Disclosure presence; verify pulled-punches absence.
- **Reviser.** Add artifact-specific grounding; pair every vulnerability with actionable fix and feasibility note; declare severity floor honestly; add Attack-Failure Disclosure entries; remove pulled-punch language; resist manufacturing new findings without new evidence.
- **Verifier.** Confirm assessment-stance output shape; confirm vulnerability labels (Finding [N] / Severity / Surface / Why this is real / What breaks if exploited / Fix recommendation / Fix feasibility); confirm Attack-Failure Disclosure; confirm no advocate-stance shapes present.
- **Consolidator.** Merge as a structured audit ranked by severity (worst-first) with paired fix recommendations.

**Source tradition.** CIA Tradecraft Primer (2009); Zenko 2015 *Red Team*; Hoffman 2017 *Red Teaming*; Ipcha Mistabra Israeli intelligence tradition; devil's advocacy practice. Klein pre-mortem (prospective hindsight technique); failure-mode literature; post-mortem analyses; adversarial case studies; FGL (fear-greed-laziness) attack vectors; OPV (other points of view) as supplementary catalogues.

**Lens dependencies.**
- Required: cia-tradecraft-red-team (foundational shared lens).
- Optional: klein-pre-mortem, failure-mode-literature, post-mortem-analyses, adversarial-case-studies, fgl-fear-greed-laziness, opv-other-points-of-view.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

### `red-team-advocate` — Red Team (Advocate)

**Educational name:** adversarial argument brief for external use (red team, advocate stance) (stance-adversarial-actor-modeling-advocate).

**Plain-language description.** Argument brief providing ammunition against the artifact for an external purpose. The mode answers: "What's the strongest case I can make against this artifact for debate / dissuasion / hostile review prep?" Input Sufficiency Protocol runs first and additionally requires audience identifiable: identifiable artifact, bounded scope, sufficient specificity, audience identifiable, diagram legibility — if conditions fail, emit three-part redirect instead of attacking. Each attack requires artifact-specific grounding (no fabrication — attacks must rest on what the artifact actually says), persuasive force (Devastating/Strong/Plausible), surface (Internal/External), suggested phrasing in the audience's idiom, and a "lands hardest with [audience] because…" annotation. Concessions section preempts the strongest counter-moves the audience would raise. Strategic considerations section names political/reputational/coalitional dimensions. The mode's signature failure is "cynical overreach" — promoting weak attacks to "devastating" and omitting concessions to make the brief look one-sided, which collapses on first contact with a prepared audience.

**Critical questions.**
- CQ1: Is the audience model accurate (named audience's actual frame, priorities, persuasion pathways)?
- CQ2: Is persuasive-force calibration honest, or have weak attacks been promoted to "devastating"?
- CQ3: Does every attack stay grounded in the artifact's actual content (no fabrication, no straw-target)?
- CQ4: Does the brief stay within the artifact's framework?
- CQ5: Are concessions honestly named, preempting the strongest counter-moves?
- CQ6: If Input Sufficiency override was invoked, is every attack flagged as low-specificity?

**Per-pipeline-stage guidance.**
- **Analyst.** Run Input Sufficiency Protocol (with audience-identifiable check); emit redirect if fails; declare "Stance: advocate"; produce audience model section; restate artifact with quotes; produce attacks with persuasive force, surface, audience-fit annotation, and suggested phrasing.
- **Evaluator.** Apply six critical questions; verify audience-model accuracy; verify persuasive-force calibration; verify no-fabrication discipline (Tier A — an attack on what the artifact does not say collapses on first counter-move); verify concession presence; verify no assessment-stance shapes (severity-ranked vulnerabilities, fix recommendations).
- **Reviser.** Drop attacks resting on fabricated claims; deflate inflated persuasive-force ratings; add audience-fit annotations; add concessions section; resist manufacturing new attacks without new evidence.
- **Verifier.** Confirm advocate-stance output shape with audience-model section; confirm attack labels (Attack [N] / Persuasive Force / Surface / Why this lands with [audience] / Suggested phrasing); confirm concessions section; confirm strategic considerations section; confirm no assessment-stance shapes present.
- **Consolidator.** Merge as a structured argument brief ranked by persuasive force (worst-for-the-artifact first) with paired suggested phrasing.

**Source tradition.** CIA Tradecraft Primer (2009); Zenko 2015 *Red Team*; Hoffman 2017 *Red Teaming*; Ipcha Mistabra Israeli intelligence tradition; devil's advocacy practice. Same supplementary catalogues as assessment, plus Rapoport rules of engagement (preempting concessions before attacking).

**Lens dependencies.**
- Required: cia-tradecraft-red-team (foundational shared lens).
- Optional: klein-pre-mortem, failure-mode-literature, post-mortem-analyses, adversarial-case-studies, fgl-fear-greed-laziness, opv-other-points-of-view, rapoport-rules-of-engagement.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

**T7 cross-reference (both red-team modes).** Red Team Assessment / Red Team Advocate and T7's pre-mortem-fragility / fragility-antifragility-audit all attack artifacts adversarially, but Red Team models a hostile actor while T7 audits structural fragility regardless of attacker presence. When the user wants "how could this fail under any pressure" rather than "how would an adversary defeat this," route to T7.

**Parse note (Decision D, 2026-05-01).** `red-team-assessment` and `red-team-advocate` were parsed from a single legacy `red-team` mode per Decision D's parsing principle: when a single mode-id maps to two distinct output contracts with different ranking criteria (severity vs. persuasive force) and different audience modeling (the user's own decision vs. a named external audience), parse into separate modes sharing a foundational lens. The shared lens is `cia-tradecraft-red-team`. The earlier internal `stance_protocol` (assessment vs advocate dispatch within one mode_id) was retired with this parse — disambiguation now lives between modes, not within.

---

## Cross-territory adjacencies

### T1 ↔ T15 (Argumentative Artifact ↔ Artifact Evaluation by Stance — Steelman case)

**Why adjacent.** Both can evaluate an argument. T1 evaluates the argument *as an argument* for soundness; T15 evaluates it *as a proposal* by adopting a defined stance.

**Disambiguating question.** "Want me to evaluate the argument's *soundness* (does it hold up?), or *evaluate the proposal* with a particular stance (steelman / push back / weigh both)?"

**Routing.** Soundness → T1. Stance-bearing → T15. Steelman cross-territory: home is T15, with T1 cross-reference activated when artifact is an argument.

### T7 ↔ T15 (Risk and Failure ↔ Red Team)

**Disambiguating question.** "Adversarial-actor stress test (someone is trying to defeat this), or structural-fragility audit (where could this break under any pressure)?"

**Routing.** Actor-modeling → T15 (`red-team-assessment` / `red-team-advocate` — both). Within T15, secondary disambiguator: own-decision (assessment, default) vs external-use (advocate). Structural fragility → T7 Fragility Audit.

---

## Lens references (Core Structure embedded)

### Rapoport Rules of Engagement (optional for steelman-construction)

**Core Structure.** Anatol Rapoport's four rules for productively criticizing another's view:
1. **Restate the opposing position so accurately that the opponent says: "Thanks, I wish I'd thought of putting it that way."** (The mirror test.)
2. **List points of agreement** (especially if they aren't matters of general or widespread agreement).
3. **Acknowledge what you've learned** from the opposing view.
4. **Then, and only then, are you permitted to say a word of rebuttal or criticism.**

The rules enforce construction-before-critique discipline: any rebuttal that would not survive the opposing party's endorsement of the reconstruction is targeted at a strawman. Steelman Construction operationalizes Rapoport's rules: rule 1 is the mirror test (CQ1), rule 2 is the points-of-agreement requirement (≥2), rules 3-4 are the construction-before-critique sequencing (CQ4) and critique-addresses-steelman-only discipline (CQ3).

### Dennett Charitable Interpretation (optional for steelman-construction)

**Core Structure.** Daniel Dennett's variant of the principle of charity: when an interpretation makes the speaker's position look irrational, look harder for the interpretation that makes it look rational. The discipline applies even where the speaker's position seems clearly wrong; the question is what is the most defensible version of what they meant. Charitable interpretation is not advocacy; it is a precondition for genuine engagement, because critique that lands only on the uncharitable version of a view fails to land on the position the proponent actually holds.

### de Bono PMI (required for benefits-analysis)

**Core Structure.** Edward de Bono's "Plus, Minus, Interesting" thinking tool. Three explicit columns:
- **Plus** — the positive aspects of the proposal.
- **Minus** — the negative aspects.
- **Interesting** — what is interesting about the proposal that is neither plus nor minus — the second-order implications, precedent effects, signaling, path-dependency, things to watch for, things that depend on context.

The discipline: all three columns must be populated (or one explicitly marked "none identified"). The Interesting column carries particular analytical weight because second-order effects are where motivated optimism most often underperforms — they are easy to miss when reasoning forward from the proposal's stated goal. PMI's structural separation of the three columns prevents the common failure of collapsing into Plus-vs-Minus advocacy.

### Klein Pre-Mortem (optional for red-team)

**Core Structure.** Gary Klein's prospective hindsight technique: imagine the future state in which the proposal has failed catastrophically, then reason backward to identify what failure modes would have produced that state. The technique exploits the asymmetry between forward planning (where motivated optimism suppresses failure modes) and backward narration from a failure (where the mind constructs causal stories more readily).

The protocol: assume the failure has happened; generate the specific narrative of how it failed (not "it didn't work" but "the regulator filed a complaint in week 3 because we hadn't anticipated X"); extract the failure modes that would have produced that narrative; surface them as findings the present plan must address. Klein-pre-mortem operates at the level of plans and actions; the structural-fragility variant in T7 operates at the level of systems and designs.

### FGL Fear-Greed-Laziness (optional for red-team)

**Core Structure.** A heuristic catalog of attack vectors against any artifact involving humans:
- **Fear** — what fears does the artifact create or fail to address; how would adversaries exploit fear to attack it.
- **Greed** — what does the artifact promise; how would adversaries exploit greed-like motivations to corrupt or bypass it.
- **Laziness** — what does the artifact assume about effort/diligence on the part of users or operators; how would adversaries exploit laziness.

The catalog is not exhaustive but is empirically productive for surfacing attack vectors that purely structural-analysis red-teaming misses. Used in conjunction with Klein-pre-mortem and post-mortem analyses of comparable failures.

### OPV Other Points of View (optional for red-team)

**Core Structure.** Edward de Bono's "Other Points of View" tool. The discipline of explicitly enumerating who else has a stake in the artifact and what their vantage produces. For Red Team, OPV surfaces adversarial vantages: not just "the obvious adversary" but the regulator who could intervene, the ally whose support could be lost, the journalist who could re-frame the story, the bystander whose perception matters. OPV broadens the attack surface beyond the most-anticipated adversary.

---

## Open debates

T15 carries no territory-level open debates at present. Mode-level debates do not currently apply (Devil's Advocate Lite, deferred per CR-6, would carry a debate on light-vs-full adversarial pressure if promoted).

---

## Citations and source-tradition attributions

- Rapoport, A. (1960). *Fights, Games, and Debates*. University of Michigan Press. The Rapoport rules of engagement.
- Dennett, D. C. (2013). *Intuition Pumps and Other Tools for Thinking*. W. W. Norton. The four-step charity protocol (citing Rapoport).
- de Bono, E. (1982). *de Bono's Thinking Course*. BBC Books. PMI tool.
- de Bono, E. (1985). *Six Thinking Hats*. Little, Brown. Companion thinking-tool framework.
- Klein, G. (2007). "Performing a Project Premortem." *Harvard Business Review*. Klein pre-mortem technique.
- Tetlock, P. E. & Gardner, D. (2015). *Superforecasting: The Art and Science of Prediction*. Crown. Calibration discipline (background for evidence-based critique).
- Mitnick, K. (2002). *The Art of Deception*. Wiley. Adversarial case studies for FGL-style attack vectors.
- Rumelt, R. P. (2011). *Good Strategy/Bad Strategy*. Crown Business. The strategy kernel (used optionally in balanced-critique).
- Ulrich, W. (2003). "Beyond Methodology Choice: Critical Systems Thinking as Critically Systemic Discourse." CSH boundary categories (used optionally in balanced-critique perspective-dependent section).
- Kahneman, D. & Tversky, A. (Various). Heuristics-and-biases catalog (foundational substrate).

*End of Framework — Artifact Evaluation by Stance.*
