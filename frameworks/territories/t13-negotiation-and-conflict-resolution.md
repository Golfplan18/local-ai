# Framework — Negotiation and Conflict Resolution

*Self-contained framework for active negotiation guidance — interest-mapping, BATNA assessment, integrative-option generation, third-side analysis. Compiled 2026-05-01.*

---

## Territory Header

- **Territory ID:** T13
- **Name:** Negotiation and Conflict Resolution
- **Super-cluster:** D (Position, Stakeholder, and Strategy)
- **Characterization:** Operations that take a negotiation or active conflict and produce guidance — interest-mapping, BATNA assessment, integrative-option generation, third-side analysis.
- **Boundary conditions:** Input is an active negotiation or conflict where guidance for the user (or for a mediator) is sought. Excludes descriptive stakeholder mapping (T8 — pre-active) and pure interest-power analysis (T2 — descriptive without negotiation framing).
- **Primary axis:** Depth (light Interest Mapping → full Principled Negotiation).
- **Secondary axes:** Complexity (Third-Side adds multi-party mediator stance).
- **Coverage status:** Strong after Wave 3.

---

## When to use this framework

Use T13 when the user is in or about to be in an active negotiation or conflict and wants guidance for it — either as a party (their own preparation) or as a third party (mediating or facilitating). T13 produces actionable guidance: the position-vs-interest descent, BATNA development, options for mutual gain, objective-criteria selection, mediator-role analysis. T13 answers questions like "I'm walking into this negotiation tomorrow — help me prepare", "what does each side really want", "as a mediator, how should I structure this conflict?", and "what's my BATNA?".

T13 does NOT do descriptive stakeholder mapping without active-negotiation framing (that is T8), pure interest-power analysis (T2), or strategic-game analysis with formal payoffs (that is T18).

---

## Within-territory disambiguation

```
[Territory identified: active negotiation or conflict resolution]

Q1 (depth): "Want a quick interest-mapping pass to see what each side actually wants,
             or the full structured walk through interests, options,
             and objective criteria (sometimes called principled negotiation)?"
  ├─ "quick interest-mapping" → interest-mapping (Tier-1, Fisher/Ury light)
  ├─ "full structured walk" → principled-negotiation (Tier-2, Fisher/Ury full)
  └─ ambiguous → principled-negotiation (the Tier-2 default per §5.6)

Q2 (specificity, optional): "Are you a party to this negotiation,
                              or are you advising as a neutral third side
                              (mediator stance)?"
  ├─ "I'm a party" → use the mode selected in Q1 (party stance)
  └─ "third side / mediator" → third-side (Ury, multi-party mediator stance)
```

**Default route.** `principled-negotiation` at Tier-2 when ambiguous (the central full-Fisher/Ury treatment; interest-mapping is the lighter sibling, third-side is the mediator-stance variant).

**Escalation hooks.**
- After `interest-mapping` Tier-1: if the mapped interests reveal substantial integrative possibilities, hook upward to `principled-negotiation`.
- After `principled-negotiation`: if the user's role is more facilitator than party, hook sideways to `third-side`.
- After any T13 mode: if the question is really descriptive stakeholder mapping rather than active negotiation, hook sideways to T8.
- After any T13 mode: if the negotiation is best modeled as a strategic-interaction game with formal payoffs, hook sideways to T18.

---

## Mode entries

### `interest-mapping` — Interest Mapping

**Educational name:** interest mapping (Fisher-Ury principled negotiation lighter sibling).

**Plain-language description.** Quick (~1-5 min) pass that surfaces the position-vs-interest distinction for a negotiation. Names parties and stated positions; descends to inferred underlying interests per party (with hypothesis-flagging — these are testable in the negotiation, not asserted as known facts); identifies shared/compatible interests (where integrative moves are possible) and genuinely-opposed interests (where distributive bargaining or value-based difference remains); names candidate integrative moves; flags unknowns the user could test in the negotiation.

**Critical questions.**
- CQ1: Has the analysis maintained the Fisher-Ury distinction between positions and interests, or conflated the two?
- CQ2: Have inferred interests been distinguished from confirmed interests — flagged as hypotheses to test?
- CQ3: Has the analysis surfaced both shared/compatible interests AND genuinely opposed interests, rather than defaulting to fully integrative or fully zero-sum?

**Per-pipeline-stage guidance.**
- **Analyst.** Name parties and positions; descend to inferred interests; flag inferences as hypotheses; surface both shared and opposed interests; name candidate integrative moves.
- **Evaluator.** Verify position-vs-interest distinction maintained; verify hypothesis-flagging on inferred content; verify shared and opposed both surfaced.
- **Reviser.** Descend further from positions where draft restated positions in interest-language; flag inferences where asserted as facts; surface both compatible and opposed where draft defaulted to one.
- **Verifier.** Confirm seven required sections (parties_and_stated_positions, inferred_underlying_interests_per_party, shared_or_compatible_interests, genuinely_opposed_interests, candidate_integrative_moves, flagged_unknowns_to_test, confidence_per_finding).
- **Consolidator.** Merge as a structured mapping with hypothesis-flagging on inferred content.

**Source tradition.** Fisher-Ury principled negotiation (the position-vs-interest descent is the load-bearing operation).

**Lens dependencies.**
- Required: fisher-ury-principled-negotiation.
- Optional: voss-tactical-empathy (when negotiation is high-stakes or adversarial), lewicki-negotiation-frameworks (when context calls for distributive analysis alongside integrative).
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

### `principled-negotiation` — Principled Negotiation

**Educational name:** principled negotiation (Fisher-Ury full method).

**Plain-language description.** The full Fisher-Ury treatment: all four elements (separate people from problem, focus on interests not positions, generate options for mutual gain, insist on objective criteria) plus BATNA (best alternative to negotiated agreement) for both the user and the counterparty (inferred). Twelve required sections cover parties and positions, people-problem diagnosis, inferred interests, shared and opposed interests, options for mutual gain, objective-criteria candidates, user BATNA, inferred counterparty BATNA, recommended opening-and-fallback pattern, flagged unknowns, and confidence-per-finding. The mode includes the Voss-warning flag for high-stakes adversarial contexts (Debate D6).

**Critical questions.**
- CQ1: Position-vs-interest distinction maintained?
- CQ2: Inferred-vs-confirmed flagged across interests, BATNAs, and motivations?
- CQ3: Shared and opposed both surfaced?
- CQ4: BATNA assessed concretely (alternative described, costed, walked-through), not asserted abstractly?
- CQ5: Objective criteria genuinely third-party-acceptable, not the user's preferences in objective-sounding language?
- CQ6: People-problem separation diagnosis specific (perception, emotion, communication issues identified), not slogan?

**Per-pipeline-stage guidance.**
- **Analyst.** Apply all four Fisher-Ury elements plus BATNA for both parties; produce people-problem diagnosis specific to context; generate options for mutual gain keyed to interest patterns; name objective criteria with counterparty-acceptance reasoning; describe user BATNA concretely; infer counterparty BATNA with hypothesis-flagging; recommend opening-and-fallback pattern; flag Voss-warning if context warrants.
- **Evaluator.** Apply six critical questions; verify BATNA concrete not placeholder; verify objective criteria third-party-defensible; verify people-problem diagnosis specific; verify Voss-warning present when high-stakes adversarial.
- **Reviser.** Descend further from positions; concretize BATNA where placeholder; find genuinely third-party-acceptable criteria where draft offered preferences; diagnose specific people-problem issues where gestural; add Voss-warning where context warrants.
- **Verifier.** Confirm twelve required sections present with hypothesis-flagging on inferred content.
- **Consolidator.** Merge as a structured synthesis with the twelve sections; opening-and-fallback recommendation specific (opening move, expected counter, fallback options keyed to BATNA).

**Source tradition.** Fisher-Ury principled negotiation full method (Getting to Yes); BATNA development as load-bearing for negotiating power.

**Lens dependencies.**
- Required: fisher-ury-principled-negotiation.
- Optional: voss-tactical-empathy (when high-stakes adversarial), lewicki-negotiation-frameworks (distributive alongside integrative), raiffa-art-and-science-of-negotiation (ZOPA / reservation-price modeling), thompson-mind-and-heart-of-the-negotiator (cross-cultural / emotional dimensions).
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

### `third-side` — Third Side

**Educational name:** third-side mediation (Ury ten roles).

**Plain-language description.** The mediator/facilitator/ombuds/community-member perspective on a multi-party conflict. Maps the surrounding community/network as a social fact; surveys the ten Ury roles in their three clusters — **prevention** (provider, teacher, bridge-builder), **resolution** (mediator, arbiter, equalizer, healer), **containment** (witness, referee, peacekeeper); identifies which roles are active, needed, or not-yet-relevant; names candidate bearers from the surrounding community; recommends specific interventions keyed to role gaps; acknowledges intervention limits (power asymmetry, party agency, situations requiring confrontation rather than mediation).

**Critical questions.**
- CQ1: Has the analysis maintained third-side stance, not slipped into party-side advocacy?
- CQ2: Have the ten Ury roles been considered as a checklist rather than collapsing into generic mediator?
- CQ3: Have the three role-clusters (prevention, resolution, containment) all been considered?
- CQ4: Have role assignments been linked to actual people / institutions / norms?
- CQ5: Have the limits of third-side intervention been acknowledged?

**Per-pipeline-stage guidance.**
- **Analyst.** Map surrounding community in two-or-more rings; survey ten roles across three clusters; identify active/needed/not-yet-relevant per role; name bearers per role; recommend specific interventions keyed to role gaps; acknowledge limits.
- **Evaluator.** Verify third-side stance not party-creep; verify all ten roles surveyed; verify all three clusters addressed; verify roles tied to bearers; verify limits acknowledged.
- **Reviser.** Restore third-side stance where draft slipped; expand role survey beyond mediator; address prevention and containment where draft addressed only resolution; name bearers where roles asserted abstractly; acknowledge limits.
- **Verifier.** Confirm ten required sections (parties_and_conflict_summary, surrounding_community_or_network, prevention_roles_active_or_needed, resolution_roles_active_or_needed, containment_roles_active_or_needed, role_assignment_candidates, escalation_signals_to_watch, candidate_third_side_interventions, flagged_unknowns_to_test, confidence_per_finding).
- **Consolidator.** Merge as a structured mapping; surrounding community appears before role assignment; the three clusters appear as separate sections.

**Source tradition.** Ury third-side framework (ten roles, three clusters); Lederach conflict-transformation (when conflict is identity-based or community-rooted); Kriesberg constructive-conflicts (when historical trajectory matters).

**Lens dependencies.**
- Required: ury-third-side.
- Optional: fisher-ury-principled-negotiation (when third-side coaches parties on principled-negotiation method), lederach-conflict-transformation (deep identity conflicts), kriesberg-constructive-conflicts (historical trajectory analysis), voss-tactical-empathy (when third-side coaches one party in adversarial-context dynamics).
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

---

## Cross-territory adjacencies

### T2 ↔ T13 (Interest and Power ↔ Negotiation)

**Disambiguating question.** "Are you mapping the interest landscape, or are you about to negotiate (or advise a negotiation)?"

**Routing.** Mapping → T2. Active negotiation guidance → T13.

### T8 ↔ T13 (Stakeholder Conflict ↔ Negotiation)

**Disambiguating question.** "Mapping the conflict structure, or guiding active negotiation?"

**Routing.** Mapping → T8. Active → T13.

**Sequential dispatch.** When active negotiation guidance is needed but the conflict structure is not yet mapped, T8 runs first; T13 follows.

### T13 ↔ T18 (Negotiation ↔ Strategic Interaction)

**Disambiguating question.** Active negotiation guidance with integrative possibility (T13), or game-theoretic equilibrium analysis with formal payoffs (T18)?

**Routing.** Active negotiation guidance → T13. Strategic-game equilibrium analysis → T18.

---

## Lens references (Core Structure embedded)

### Fisher-Ury Principled Negotiation (required for all three T13 modes)

**Core Structure.** Four principles plus BATNA.

1. **Separate the People from the Problem.** Treat the substantive dispute (the problem) as a different object from the relationship between the parties. Negotiate the problem hard while preserving the working relationship. The discipline: run two tracks decoupled — substantive track addresses the problem, relational track addresses the working relationship. "Hard on the problem, soft on the people."

2. **Focus on Interests, Not Positions.** A *position* is what a party says it wants. An *interest* is the underlying need or concern that produces the position. Positions are typically singular and incompatible; interests are typically multiple and have substantial overlap with the other party's interests, opening room for trades. The test for an interest is whether removing the position would leave the interest intact and seeking other satisfaction.

3. **Invent Options for Mutual Gain.** Before deciding, generate a wide set of possible agreements that meet both parties' interests. Defer judgment during option-generation; the goal is volume and variety. Look explicitly for options that *enlarge the pie* (create joint value) before negotiating how to divide it. The four obstacles Fisher and Ury name: premature judgment, single-answer search, fixed-pie assumption, "their problem is theirs to solve."

4. **Insist on Objective Criteria.** Frame the negotiation as a joint search for the standard that should govern the outcome — market price, expert opinion, precedent, scientific finding, legal standard, equal treatment, reciprocity — rather than a contest of wills. The criterion's authority comes from being legitimate (defensible to a third party) and applicable to both sides.

**Source of Power — BATNA.** A party's BATNA is the best outcome that party can secure without reaching agreement with the other side. The strength of a party's negotiating position is determined not by what it demands but by how good its BATNA is. The reservation point (the worst agreement the party should accept) is set by the BATNA: do not accept any agreement worse than your BATNA. BATNA must be developed concretely (what specific alternative deal, what specific course of action) and tested for realism.

**Voss caveat (Debate D6).** Principled negotiation assumes a counterparty willing to negotiate on the merits. When the counterparty is adversarial, manipulative, or operating in bad faith, the framework's prescriptions can leave the principled negotiator exposed. Voss's *Never Split the Difference* argues that high-stakes negotiation often requires tactical empathy, calibrated questions, and accusation audits beyond the Fisher-Ury repertoire.

### Ury Third-Side Framework (required for third-side mode)

**Core Structure.** The "third side" is the surrounding community/network that contains a conflict — the people, institutions, and norms that affect a conflict whether they intend to or not. Ten roles span three clusters:

**Prevention (addressing tensions before they erupt):**
- **Provider** — addresses frustrated needs that drive conflict (resources, opportunity, security).
- **Teacher** — gives skills for conflict-handling (negotiation method, communication training).
- **Bridge-builder** — develops relationships that pre-empt conflict (cross-group ties, communication channels).

**Resolution (engaging conflicts as they emerge):**
- **Mediator** — facilitates communication between parties.
- **Arbiter** — judges when self-resolution fails.
- **Equalizer** — democratizes power asymmetry that prevents fair negotiation.
- **Healer** — addresses injured emotions and broken relationships.

**Containment (when prevention and resolution have failed, prevent escalation):**
- **Witness** — pays attention so escalation has consequences.
- **Referee** — establishes rules for fair fight.
- **Peacekeeper** — interposes when violence threatens.

The framework's discipline: name each role's status (active, well-filled / active but poor / needed but unfilled / not-yet-relevant) and link active and needed roles to actual bearers (named people, institutions, norms) in the surrounding community. Limits: power asymmetry that makes mediation cover for coercion, parties' agency that makes intervention intrusive, situations requiring confrontation rather than mediation.

### Voss Tactical Empathy (optional for high-stakes adversarial contexts)

**Core Structure.** Tools for negotiating when the counterparty is operating outside the Fisher-Ury cooperative-default assumption:
- **Calibrated questions** — open-ended questions starting with "what" or "how" that invite the counterparty to solve the user's problem.
- **Mirroring** — repeating the last few words of what the counterparty said, inviting elaboration.
- **Labeling** — naming the counterparty's emotions ("It seems like you're frustrated by..."), defusing them.
- **The "no" that opens engagement** — Voss's claim that getting the counterparty to say "no" is more productive than getting them to "yes" because "no" preserves their sense of agency.
- **Accusation audit** — preempting the counterparty's worst possible characterization of the user's position.

The Voss tools supplement Fisher-Ury rather than replacing it; the integrative possibility-space remains the goal where it exists, but the tools acknowledge that emotional dynamics, perceived loss, ego, and information asymmetry often dominate late-stage bargaining.

---

## Open debates

### Debate D6 — Fisher-Ury sufficiency for adversarial contexts; Voss critique

Fisher and Ury's *Getting to Yes* (1981) frames negotiation as fundamentally integrative-possible: separate people from problem, focus on interests not positions, generate options for mutual gain, use objective criteria. The framework has been transformative in commercial and diplomatic contexts where the parties share an interest in reaching agreement and where the integrative possibility-space is real.

Chris Voss's *Never Split the Difference* (2016) and the broader practitioner literature on hostage negotiation, high-stakes commercial bargaining, and politically adversarial negotiation argue that Fisher-Ury underweights tactical empathy, emotional dynamics, distributive reality, and the role of perceived loss and ego in many real negotiations — and that in genuinely adversarial contexts the integrative frame can be naive or actively counterproductive. Voss-derived practice emphasizes calibrated questions, mirroring, labeling emotions, the "no" that opens engagement, the late-stage "Black Swan" information asymmetries, and the recognition that distribution, not integration, often dominates the late-game bargaining. Lewicki and others document the distributive/integrative continuum and warn against assuming integrative possibility where it is absent.

T13 modes do not adjudicate the debate. They use Fisher-Ury as the primary lens because the four-element method plus BATNA is the most-tested integrative framework available, and because the position-vs-interest descent is robust across contexts. The modes flag adversarial-context limitations explicitly when the situation warrants — the `voss-warning-unflagged` failure mode in `principled-negotiation` and the `voss-tactical-empathy` optional lens are the structural mechanisms. The integrative-overreach failure mode exists precisely to guard against the Fisher-Ury optimism trap. In genuinely adversarial contexts, the user may need to supplement the T13 modes with Voss-style tactical-empathy lenses, or to recognize that the analysis is offering an integrative-possibility-space the situation may not contain.

---

## Citations and source-tradition attributions

- Fisher, R., Ury, W. & Patton, B. (1981/2011). *Getting to Yes: Negotiating Agreement Without Giving In*. Houghton Mifflin / Penguin. Foundational.
- Ury, W. (1991). *Getting Past No: Negotiating with Difficult People*. Bantam. Adversarial-counterparty extension.
- Ury, W. (2000). *The Third Side: Why We Fight and How We Can Stop*. Penguin. Operational basis for `third-side` mode.
- Voss, C. & Raz, T. (2016). *Never Split the Difference: Negotiating As If Your Life Depended On It*. HarperBusiness. Tactical-empathy critique.
- Lax, D. A. & Sebenius, J. K. (1986). *The Manager as Negotiator: Bargaining for Cooperation and Competitive Gain*. Free Press. Integrative-distributive framework.
- Lewicki, R. J. et al. (Various editions). *Negotiation*. McGraw-Hill. Standard textbook treatment of distributive/integrative continuum.
- Raiffa, H. (1982). *The Art and Science of Negotiation*. Harvard University Press. ZOPA / reservation-price modeling.
- Thompson, L. (2020). *The Mind and Heart of the Negotiator* (7th ed.). Pearson. Cross-cultural and emotional dimensions.
- Lederach, J. P. (2003). *The Little Book of Conflict Transformation*. Good Books. Identity-rooted conflict tradition.
- Kriesberg, L. & Dayton, B. W. (2017). *Constructive Conflicts: From Escalation to Resolution* (5th ed.). Rowman & Littlefield. Trajectory analysis.
- Kahneman, D. & Tversky, A. (Various). Heuristics-and-biases catalog (foundational substrate).

*End of Framework — Negotiation and Conflict Resolution.*
