# Reference — Within-Territory Disambiguation Trees

*This file holds the within-territory disambiguation trees consulted by Stage 2 of the pre-routing pipeline. Stage 1 identifies the territory; Stage 2 (this file) disambiguates among modes within the territory once the territory is known. Cross-territory disambiguation — selecting between two adjacent territories that both fit the prompt — lives in `Reference — Cross-Territory Adjacency.md`. The style guide for branch questions is in `Reference — Architecture of Analytical Territories and Modes.md` §5.1–§5.7; this file applies it. Trees reflect the post-Wave-4 mode roster per `Reference — Analytical Territories.md`.*

---

## How to read each tree

Every tree has three parts:

1. **The branching diagram** — ASCII-style branches (`├─`, `└─`) where each branch is a plain-language question and each leaf is a `mode_id`. Branch questions use only the permitted vocabulary in §5.1 (situation, goal, stance-in-plain-words, concrete artifact, time-budget). Mode names never appear in branch questions; they appear only at leaves and in optional parenthetical educational labels per §5.4.
2. **The axis note** — which gradation axis (depth, complexity, stance, specificity) the tree uses, since axis is the structural backbone per Reframe 3.
3. **The default route** — what happens when the user gives an ambiguous answer or no answer. Per §5.6: Tier-2 thorough atomic, neutral stance, general specificity. Never Tier-1 by default; never Tier-3 by default.
4. **The escalation hooks** — what fires after the chosen mode completes per §5.7 if the output detects conditions warranting heavier or sibling analysis.

For singleton territories (one resident mode at current population), the tree is just the route. The note acknowledges the singleton state and points to the territory's deferred candidates per CR-6.

---

## T1 — Argumentative Artifact Examination

```
[Territory identified: argumentative artifact]

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
  ├─ "tracing where this position came from over time" → position-genealogy (deferred per CR-6)
  └─ default → standard mode selected in Q1
```

**Axes used.** Depth (Q1: light coherence/frame vs. molecular argument-audit) + specificity (Q2: general vs. propaganda vs. genealogy).

**Default route.** `coherence-audit` at Tier-2 when ambiguous, with frame-audit available as an escalation hook (very common pairing — coherence often surfaces a hidden frame question).

**Escalation hooks.**
- After `coherence-audit` Tier-2: if the audit surfaces a frame-dependent inconsistency, hook upward to `frame-audit` (sideways/sibling escalation).
- After `frame-audit` Tier-2: if multiple competing frames surface and the question is which to adopt, hook upward to `frame-comparison` in T9 (cross-territory escalation).
- After either `coherence-audit` or `frame-audit`: if both findings interact non-trivially, hook upward to `argument-audit` molecular (Tier-3, depth escalation).
- After any T1 mode: if the question becomes "should we accept this proposal?", hook sideways to T15 (`steelman-construction` or `red-team`).

---

## T2 — Interest and Power Analysis

```
[Territory identified: interest and power]

Q1 (complexity): "Are you trying to figure out who benefits from this single situation,
                  or map out a landscape of multiple parties with different stakes,
                  or work through something that feels tangled across many dimensions?"
  ├─ "this one situation" → cui-bono (Tier-2)
  ├─ "landscape of parties" → stakeholder-mapping (Tier-2; cross-territory dispatch into T8)
  ├─ "tangled / wicked / many interacting interests" → wicked-problems molecular
                                                       (Tier-3 — confirm runtime)
  └─ ambiguous → cui-bono with escalation hook to stakeholder-mapping

Q2 (stance, optional): "Are you also asking about whose voices are being left out
                         of the picture entirely?"
  └─ yes → boundary-critique (Ulrich CSH, sideways/stance variant)

Q3 (output, optional): "Are you producing a decision-clarity document for someone else
                         (you're the analyst, they're the decision-maker)?"
  └─ yes → decision-clarity molecular (Tier-3)
```

**Axes used.** Complexity (Q1: simple → multi-party → systemic) + stance (Q2: descriptive vs. critical) + specificity (Q3: analyst output vs. decision-maker output).

**Default route.** `cui-bono` at Tier-2 when ambiguous, with stakeholder-mapping as the most common upward hook.

**Escalation hooks.**
- After `cui-bono` Tier-2: if more than two stakeholder groups surface, hook upward to `stakeholder-mapping` (cross-territory into T8).
- After `stakeholder-mapping`: if interactions among parties surface feedback structure, hook upward to `wicked-problems` molecular.
- After any T2 mode: if the user signals voices may be missing, hook sideways to `boundary-critique`.
- After `cui-bono` or `stakeholder-mapping`: if the user is producing analysis for a third-party decision-maker, hook upward to `decision-clarity`.

---

## T3 — Decision-Making Under Uncertainty

```
[Territory identified: decision under uncertainty]

Q1 (situation): "Is the environment basically known and you're picking from clear options,
                 or are there real unknowns about how things will play out,
                 or are you weighing several criteria that don't reduce to one number,
                 or are values in tension where the choice is partly about what you stand for?"
  ├─ "known environment" → constraint-mapping (Tier-2)
  ├─ "real unknowns / probability matters" → decision-under-uncertainty (Tier-2)
  ├─ "many criteria pulling different ways" → multi-criteria-decision (Tier-2)
  ├─ "values in tension" → ethical-tradeoff (deferred per CR-6)
  └─ ambiguous → decision-under-uncertainty with escalation hook to multi-criteria-decision

Q2 (specificity, optional): "Is this a one-shot choice, or staged where you can learn
                              between steps?"
  └─ "staged" → real-options-decision (deferred per CR-6)

Q3 (depth, optional): "Want me to bring it all together into a decision architecture
                        that tracks the constraints, uncertainties, and criteria
                        in one integrated frame?"
  └─ yes → decision-architecture molecular (Tier-3)
```

**Axes used.** All three: depth (Q3: thorough atomic vs. molecular), complexity (Q1: single criterion vs. multi-criteria), stance (Q1: optimization vs. normative), specificity (Q2: one-shot vs. staged).

**Default route.** `decision-under-uncertainty` at Tier-2 when ambiguous (the central mode of the territory; constraint-mapping is the lighter sibling, decision-architecture the molecular sibling).

**Escalation hooks.**
- After `constraint-mapping` Tier-2: if real unknowns surface that change the option set, hook upward to `decision-under-uncertainty`.
- After `decision-under-uncertainty` Tier-2: if multiple non-commensurable criteria are in play, hook sideways to `multi-criteria-decision`.
- After any Tier-2 T3 mode: if the user wants a single integrated artifact tracking all dimensions, hook upward to `decision-architecture` molecular.
- After any T3 mode: if the question shifts from "what should I do" to "how could this fail", hook sideways to T7 (`pre-mortem-action` or `pre-mortem-fragility`).

---

## T4 — Causal Investigation

```
[Territory identified: causal investigation]

Q1 (complexity): "Is the question more like 'what one thing went wrong here',
                  or more like 'what set of things keep producing this',
                  or do you want a formal causal model with arrows you can reason over,
                  or are you tracing how a specific historical event actually unfolded?"
  ├─ "one thing / chain back to root" → root-cause-analysis (Tier-2)
  ├─ "feedback / things reinforcing each other" → systems-dynamics-causal (Tier-2)
  ├─ "formal causal model with arrows" → causal-dag (Tier-3, Pearl-style)
  ├─ "specific historical event, step by step" → process-tracing (Tier-3, Bennett/Checkel)
  └─ ambiguous → root-cause-analysis with escalation hook to systems-dynamics-causal
```

**Axes used.** Complexity (single chain → feedback structure) + specificity (general vs. historical-event) + depth (light vs. formal DAG).

**Default route.** `root-cause-analysis` at Tier-2 when ambiguous; this is the lightest path and surfaces feedback signals naturally.

**Escalation hooks.**
- After `root-cause-analysis` Tier-2: if the analysis surfaces reinforcing loops or competing causes that interact, hook upward to `systems-dynamics-causal` (the canonical "the structure here looks like there are competing causes that interact" hook from §5.7).
- After `systems-dynamics-causal`: if formalism is needed to share with others, hook upward to `causal-dag`.
- After any T4 mode: if the framing itself appears to be generating the problem, hook sideways to T9 (`paradigm-suspension` or `frame-comparison`).
- After any T4 mode: if the question shifts to "how do the parts produce the whole's behavior", hook sideways to T16 (`mechanism-understanding`).

---

## T5 — Hypothesis Evaluation

```
[Territory identified: hypothesis evaluation, two-or-more competing explanations]

Q1 (depth): "Quick read on which explanation fits best,
             or do you want me to lay out evidence systematically against each candidate,
             or do you want a probabilistic model with priors?"
  ├─ "quick" → differential-diagnosis (Tier-1)
  ├─ "systematic" → competing-hypotheses (Tier-2, Heuer ACH)
  ├─ "probabilistic model with priors" → bayesian-hypothesis-network (Tier-3)
  └─ ambiguous → competing-hypotheses (the Tier-2 default)
```

**Axes used.** Depth — the territory's primary axis. The three resident modes form a clean depth ladder.

**Default route.** `competing-hypotheses` at Tier-2 when ambiguous (the canonical Heuer ACH operation; both the quick and the formal are siblings of this baseline).

**Escalation hooks.**
- After `differential-diagnosis` Tier-1: if more than two hypotheses survive the quick read, hook upward to `competing-hypotheses` ("Quick read complete — there's more here than one mode can disentangle, want the longer route?").
- After `competing-hypotheses` Tier-2: if priors materially shift the diagnosis, hook upward to `bayesian-hypothesis-network`.
- After any T5 mode: if the disagreement is really about how to frame the issue rather than which hypothesis fits the evidence, hook sideways to T9 (`paradigm-suspension` or `frame-comparison`).
- After any T5 mode: if each hypothesis is itself a complete argument-as-artifact, hook sideways to T1 (audit each).

---

## T6 — Future Exploration

```
[Territory identified: future exploration]

Q1 (stance): "Mostly looking forward to anticipate likely consequences,
              wanting probability estimates,
              wanting alternative future stories,
              stress-testing a plan against how it could go wrong,
              or imagining the success and working backward to today?"
  ├─ "likely consequences" → consequences-and-sequel (Tier-2)
  ├─ "probabilities" → probabilistic-forecasting (Tier-2, Tetlock-style)
  ├─ "alternative stories" → scenario-planning (Tier-2, Wack-style)
  ├─ "what could go wrong with the plan" → pre-mortem-action
                                            (cross-territory note: parsed from
                                             pre-mortem; structural-fragility
                                             variant lives in T7)
  ├─ "imagining the success and working backward" → backcasting (deferred per CR-6)
  └─ ambiguous → consequences-and-sequel with escalation to scenario-planning

Q2 (depth, optional): "Want me to bring it all together — multiple scenarios,
                        probability estimates, and pre-mortems composed into
                        a wicked-future analysis?"
  └─ yes → wicked-future molecular (Tier-3)
```

**Axes used.** Stance (Q1: neutral forecasting vs. adversarial pre-mortem vs. constructive backcasting) + depth (Q2: thorough atomic vs. molecular).

**Default route.** `consequences-and-sequel` at Tier-2 when ambiguous (the lightest forward-projection mode; scenario-planning is the most common upward hook).

**Escalation hooks.**
- After `consequences-and-sequel` Tier-2: if multiple plausible futures diverge, hook upward to `scenario-planning`; if probabilities can be quantified usefully, hook sideways to `probabilistic-forecasting`.
- After `scenario-planning`: if the user wants stress-testing of a chosen path, hook sideways to `pre-mortem-action`; if integrated with probabilities and pre-mortem, hook upward to `wicked-future` molecular.
- After `pre-mortem-action`: if the failure modes are structural rather than action-specific, hook sideways to T7 `pre-mortem-fragility` (cross-territory parse).
- After any T6 mode: if the question is really about choosing among options now rather than exploring futures, hook sideways to T3.

---

## T7 — Risk and Failure Analysis

```
[Territory identified: risk and failure]

Q1 (specificity): "Is the question about an action plan that could fail,
                   or about a system or design with structural fragilities
                   (where could it break under any pressure)?"
  ├─ "action plan, what could go wrong before we commit" → pre-mortem-fragility
                                                            (cross-territory note:
                                                             parsed from pre-mortem;
                                                             action-plan variant
                                                             lives in T6)
  ├─ "system or design — structural fragility, asymmetric exposure" →
        fragility-antifragility-audit (Talebian)
  └─ ambiguous → pre-mortem-fragility with escalation to fragility-antifragility-audit

Q2 (depth, optional): "Want a quick scan for failure modes, or a thorough fault-tree
                        that traces how component failures propagate?"
  ├─ "quick scan" → failure-mode-scan (deferred per CR-6)
  ├─ "thorough fault tree" → fault-tree (deferred per CR-6)
  └─ ambiguous → use the mode selected in Q1

Q3 (stance, optional): "Are you specifically modeling an adversary trying to defeat this,
                         or asking where it could break under any pressure
                         (no adversary required)?"
  ├─ "adversary modeling" → cross-territory dispatch to T15 red-team
  └─ "any pressure / no adversary needed" → stay in T7
```

**Axes used.** Specificity (Q1: action-plan vs. structural-system) + depth (Q2: light scan vs. thorough fault tree) + stance (Q3: adversarial-actor vs. structural-fragility — also the T7↔T15 cross-territory disambiguator).

**Default route.** `pre-mortem-fragility` at Tier-2 when ambiguous (the lighter atomic mode; `fragility-antifragility-audit` is the heavier sibling with the full Talebian asymmetry treatment).

**Escalation hooks.**
- After `pre-mortem-fragility` Tier-2: if the failure modes surfaced are structural and asymmetric rather than action-specific, hook upward to `fragility-antifragility-audit`.
- After either T7 mode: if an adversary is genuinely in the picture, hook sideways to T15 `red-team` per the §5.6 stance disambiguator.
- After either T7 mode: if the failure has already happened and the question is now causal, hook sideways to T4.
- After either T7 mode: if the failure is a strategic-interaction failure, hook sideways to T18.

---

## T8 — Stakeholder Conflict

```
[Territory identified: stakeholder conflict, multiple parties with divergent interests]

Q1 (situation): "Are you mapping the parties and how their interests align or diverge,
                  or is the conflict structure itself wicked
                  (parties, sub-parties, shifting coalitions)?"
  ├─ "mapping parties and interests" → stakeholder-mapping (Tier-2)
  ├─ "wicked / shifting / sub-coalitions" → conflict-structure (deferred per CR-6)
  └─ ambiguous → stakeholder-mapping (singleton mode at current population)
```

**Axes used.** Complexity (single mapping vs. systemic conflict structure) — partial because the second mode is deferred.

**Default route.** `stakeholder-mapping` at Tier-2 — this is effectively the territory founder; `conflict-structure` is deferred per CR-6.

**Escalation hooks.**
- After `stakeholder-mapping` Tier-2: if the user is moving from descriptive mapping into active negotiation guidance, hook sideways to T13 (`interest-mapping` or `principled-negotiation`).
- After `stakeholder-mapping`: if the question is fundamentally about who benefits and where power sits rather than about the conflict shape, hook sideways to T2 (`cui-bono` or `boundary-critique`).
- After `stakeholder-mapping`: if the conflict has feedback structure across multiple sub-coalitions and the deferred `conflict-structure` mode is needed, surface the deferred-mode flag rather than substituting `wicked-problems` from T2 (different operations).

**Singleton note.** T8 currently has one resident mode (`stakeholder-mapping`). Expansion candidate `conflict-structure` is deferred per CR-6. If T8 invocations consistently produce composition-with-T13 patterns, that suggests `conflict-structure` should be promoted ahead of CR-6 review.

---

## T9 — Paradigm and Assumption Examination

```
[Territory identified: paradigm and assumption examination]

Q1 (stance): "Are you trying to suspend the current frame to see what it's hiding,
              compare two or more frames against each other,
              or build out the full landscape of how different worldviews see this?"
  ├─ "suspend the current frame" → paradigm-suspension (Tier-2)
  ├─ "compare frames" → frame-comparison (Tier-2)
  ├─ "full worldview landscape" → worldview-cartography molecular
                                   (Tier-3 — confirm runtime)
  └─ ambiguous → paradigm-suspension with escalation hook to frame-comparison

Q2 (depth, optional): "Want a single-frame surfacing on this one artifact (atomic),
                        or a sustained walk through how multiple frames build
                        and constrain each other (molecular)?"
  ├─ "single-frame on one artifact" → use the mode selected in Q1
  └─ "sustained molecular walk" → worldview-cartography
```

**Axes used.** Stance (Q1: suspending vs. comparing vs. mapping) + depth (Q2: atomic surfacing vs. molecular cartography).

**Default route.** `paradigm-suspension` at Tier-2 when ambiguous (the lightest atomic; the comparing and cartography variants are sideways/upward escalations).

**Escalation hooks.**
- After `paradigm-suspension` Tier-2: if multiple frames surface that need explicit comparison, hook upward to `frame-comparison`.
- After `frame-comparison`: if the comparison expands into a full landscape of worldviews, hook upward to `worldview-cartography` molecular.
- After any T9 mode: if the question collapses back into within-frame argumentation, hook sideways to T1 (`frame-audit` for a single-artifact frame surface).
- After any T9 mode: if the question becomes "integrate across these paradigms" rather than "examine the differences", hook sideways to T12 (`synthesis` or `dialectical-analysis`).

---

## T10 — Conceptual Clarification

```
[Territory identified: conceptual clarification, definitional dispute]

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

**Axes used.** Stance — the territory's primary axis (descriptive vs. ameliorative vs. essentially-contested).

**Default route.** `deep-clarification` at Tier-2 when ambiguous (the descriptive baseline; ameliorative and essentially-contested variants are stance escalations).

**Escalation hooks.**
- After `deep-clarification` Tier-2: if clarification reveals the concept is doing normative work that needs revision, hook sideways to `conceptual-engineering`.
- After `conceptual-engineering`: if the engineered version cannot be agreed because users' values diverge, hook sideways to `definitional-dispute` (deferred — surface the flag).
- After any T10 mode: if the concept-clarification is a precursor to argument evaluation, hook sideways to T1.
- After any T10 mode: if the concept is embedded in a paradigm dispute, hook sideways to T9.

---

## T11 — Structural Relationship Mapping

```
[Territory identified: structural relationship mapping]

Q1 (specificity): "Is your input a textual description of entities and their relationships,
                    or a visual diagram, network, or schema where the question is
                    what relations the picture asserts (or where relations are missing)?"
  ├─ "textual description / list of entities and relations" → relationship-mapping (Tier-2)
  ├─ "visual diagram / network / schema" → spatial-reasoning
                                            (Tier-2, specificity-visual-input)
  └─ ambiguous → relationship-mapping with escalation hook to spatial-reasoning
```

**Axes used.** Specificity — the territory's primary axis (general vs. visual-input).

**Default route.** `relationship-mapping` at Tier-2 when ambiguous (the general atomic; `spatial-reasoning` is the visual-input specificity variant doing the same operation on diagrammatic input).

**Escalation hooks.**
- After `relationship-mapping` Tier-2: if the input becomes visual mid-conversation, switch sideways to `spatial-reasoning`.
- After `spatial-reasoning`: if the question shifts from "what relations does this diagram assert" to "what is the layout itself doing", hook sideways to T19 (`compositional-dynamics` or `ma-reading`) — this is the canonical T11↔T19 cross-territory disambiguator.
- After either T11 mode: if the question becomes "how does this work" rather than "how are the parts related", hook sideways to T16 (`mechanism-understanding`).
- After either T11 mode: if the question becomes "how does this flow over time", hook sideways to T17 (`process-mapping`).

---

## T12 — Cross-Domain and Knowledge Synthesis

```
[Territory identified: cross-domain or knowledge synthesis]

Q1 (stance): "Are you trying to integrate two or more bodies of knowledge into
              a unified picture, or hold a thesis and an antithesis in productive
              tension to see what new understanding emerges?"
  ├─ "integrate into unified picture" → synthesis (Tier-2)
  ├─ "thesis and antithesis in tension" → dialectical-analysis (Tier-2)
  ├─ "find a structural analogy across very different domains" →
        cross-domain-analogical (deferred per CR-6)
  └─ ambiguous → synthesis with escalation hook to dialectical-analysis
```

**Axes used.** Stance — the territory's primary axis (integrative vs. thesis-antithesis vs. analogical).

**Default route.** `synthesis` at Tier-2 when ambiguous (the integrative baseline; dialectical is the productive-tension variant).

**Escalation hooks.**
- After `synthesis` Tier-2: if irreducible tensions remain that resist integration, hook sideways to `dialectical-analysis` (the productive-tension variant is appropriate when integration is forced).
- After `dialectical-analysis`: if a synthesis emerges from the tension and can be articulated, loop back to `synthesis` for the unified output.
- After either T12 mode: if the analysis is really about which paradigm to adopt rather than how to integrate them, hook sideways to T9 (`frame-comparison` or `worldview-cartography`).
- After either T12 mode: if the work is generative rather than integrative, hook sideways to T20 (`passion-exploration`).

---

## T13 — Negotiation and Conflict Resolution

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

**Axes used.** Depth (Q1: light interest-mapping vs. thorough principled-negotiation) + specificity (Q2: negotiation-as-party vs. negotiation-as-mediator).

**Default route.** `principled-negotiation` at Tier-2 when ambiguous (the central full-Fisher/Ury treatment; interest-mapping is the lighter sibling, third-side is the mediator-stance variant).

**Escalation hooks.**
- After `interest-mapping` Tier-1: if the mapped interests reveal substantial integrative possibilities, hook upward to `principled-negotiation` ("Quick interest-mapping complete; the structure here looks like there's room for an integrative option, want the longer route?").
- After `principled-negotiation`: if the user's role is more facilitator than party, hook sideways to `third-side`.
- After any T13 mode: if the question is really about descriptive stakeholder mapping rather than active negotiation, hook sideways to T8.
- After any T13 mode: if the negotiation is best modeled as a strategic-interaction game with formal payoffs, hook sideways to T18 (`strategic-interaction`).

---

## T14 — Orientation in Unfamiliar Territory

```
[Territory identified: orientation in unfamiliar territory]

Q1 (depth): "Want a quick lay of the land — main landmarks, common pitfalls,
             where to start — or a thorough terrain map with the major sub-areas
             and their relationships, or a full induction that walks you in
             from first principles?"
  ├─ "quick lay of the land" → quick-orientation (Tier-1)
  ├─ "thorough terrain map" → terrain-mapping (Tier-2)
  ├─ "full induction from first principles" → domain-induction molecular
                                                (Tier-3 — confirm runtime)
  └─ ambiguous → terrain-mapping (the Tier-2 default per §5.6)
```

**Axes used.** Depth — the territory's primary axis. The three modes form a clean depth ladder (light triplet pattern per the spec note).

**Default route.** `terrain-mapping` at Tier-2 when ambiguous (the central thorough mode; quick-orientation is the lighter sibling, domain-induction the heavier molecular).

**Escalation hooks.**
- After `quick-orientation` Tier-1: if the user wants to actually settle into the domain rather than just reconnoiter, hook upward to `terrain-mapping`.
- After `terrain-mapping` Tier-2: if the user wants induction into the domain's reasoning patterns rather than just its layout, hook upward to `domain-induction` molecular.
- After any T14 mode: if orientation surfaces a generative interest the user wants to explore, hook sideways to T20 (`passion-exploration`).
- After any T14 mode: if the orientation produces a relationship map as a side-effect that the user wants to elaborate, hook sideways to T11 (`relationship-mapping`).

---

## T15 — Artifact Evaluation by Stance

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
       Q1a (red-team operation): "want adversarial — for own decision (assessment) or for external use (advocate)?"
         ├─ "for own decision / what's wrong / fix list" → red-team-assessment (default)
         ├─ "argue against / ammunition / debate prep" → red-team-advocate
         └─ ambiguous → red-team-assessment with escalation hook to red-team-advocate
  ├─ "balanced (positives weighted)" → benefits-analysis
  ├─ "balanced (neutral)" → balanced-critique
  ├─ "quick devil's advocate, not full hostile actor" → devils-advocate-lite
                                                          (deferred per CR-6)
  └─ ambiguous → balanced-critique (the neutral Tier-2 default per §5.6)
```

**Axes used.** Stance — the territory's primary and defining axis (constructive-strong → constructive-balanced → neutral → adversarial-light → adversarial-actor-modeling).

**Default route.** `balanced-critique` at Tier-2 when ambiguous (per §5.6 the neutral stance is the default when the user has not signaled).

**Escalation hooks.**
- After `steelman-construction`: if the user wants the opposite-stance counterpoint, hook sideways to `red-team-assessment` (own-decision) or `red-team-advocate` (external-use).
- After `red-team-assessment`: if the user wants the constructive counterpoint, hook sideways to `steelman-construction`. If the user shifts from own-decision framing to building a case against the artifact for external use, hook sideways to `red-team-advocate`.
- After `red-team-advocate`: if the user wants the constructive counterpoint, hook sideways to `steelman-construction`. If the user shifts back to wanting their own vulnerabilities surfaced for fix-prioritisation, hook sideways to `red-team-assessment`.
- After `benefits-analysis`: if drawbacks need fuller treatment, hook sideways to `balanced-critique` or `red-team-assessment` (default) / `red-team-advocate` (external use).
- After `balanced-critique`: if the user wants either pole pushed harder, hook sideways to `steelman-construction` or `red-team-assessment` / `red-team-advocate`.
- After any T15 mode: if the artifact is itself an argument and the question becomes argument-soundness rather than proposal-evaluation, hook sideways to T1 (`coherence-audit` or `frame-audit`).
- After either red-team mode: if the question is really about structural fragility rather than an adversary trying to defeat this, hook sideways to T7 (`fragility-antifragility-audit`) per the §5.6 T7↔T15 disambiguator.

---

## T16 — Mechanism Understanding

```
[Territory identified: mechanism understanding — how does this work?]

Route: mechanism-understanding (Tier-2, territory founder)
```

**Axes used.** Depth (founder mode at thorough atomic depth). Specificity axis grows as domain-specific mechanism modes are added (currently none).

**Default route.** `mechanism-understanding` at Tier-2 — singleton at current population. No within-territory disambiguation needed.

**Escalation hooks.**
- After `mechanism-understanding`: if the question becomes "why does this happen" (causal investigation) rather than "how does it work", hook sideways to T4 (`root-cause-analysis` or `systems-dynamics-causal`).
- After `mechanism-understanding`: if the question becomes "how does this flow over time as a process", hook sideways to T17 (`process-mapping`).
- After `mechanism-understanding`: if the question becomes "how do the parts relate structurally" (topology rather than working-principle), hook sideways to T11 (`relationship-mapping`).

**Singleton note.** T16 currently has one resident mode (`mechanism-understanding`, Wave 3 founder). Domain-specific mechanism variants are deferred per CR-6 — they would expand the specificity axis as Ora encounters domain-specific mechanism work that the founder mode handles inadequately.

---

## T17 — Process and System Analysis

```
[Territory identified: process or system mapping, current state]

Q1 (specificity): "Is the system you're mapping fundamentally a feedback structure
                    (loops, reinforcing or balancing dynamics),
                    or fundamentally a process flow
                    (sequenced steps, inputs producing outputs)?"
  ├─ "feedback structure / loops / reinforcing or balancing dynamics" →
        systems-dynamics-structural (Tier-2; cross-territory note: causal variant
                                      lives in T4, parsed per Decision D)
  ├─ "process flow / sequenced steps" → process-mapping (Tier-2)
  ├─ "organizational structure (formal reporting and roles)" →
        organizational-structure (deferred per CR-6)
  └─ ambiguous → process-mapping with escalation hook to systems-dynamics-structural
```

**Axes used.** Specificity — the territory's primary axis (process flow vs. feedback structure vs. organizational structure).

**Default route.** `process-mapping` at Tier-2 when ambiguous (the lightest of the resident modes; systems-dynamics-structural is the feedback-specific sibling).

**Escalation hooks.**
- After `process-mapping` Tier-2: if the process map surfaces feedback loops that account for the system's behavior, hook sideways to `systems-dynamics-structural`.
- After `systems-dynamics-structural`: if the question becomes "why does this keep happening" (causal rather than structural), hook sideways to T4 `systems-dynamics-causal` (the parsed sibling per Decision D).
- After either T17 mode: if the question becomes "how do the parts produce the whole's behavior at the principle level", hook sideways to T16 (`mechanism-understanding`).
- After either T17 mode: if the question becomes "what relations does the system assert among its parts", hook sideways to T11 (`relationship-mapping`).

---

## T18 — Strategic Interaction

```
[Territory identified: strategic interaction, situation modelable as a game]

Route: strategic-interaction (Tier-2, territory founder)
```

**Axes used.** Complexity (founder mode at 2-to-n-player complexity). Mechanism-design and signaling-game variants are deferred per CR-6.

**Default route.** `strategic-interaction` at Tier-2 — singleton at current population. No within-territory disambiguation needed.

**Escalation hooks.**
- After `strategic-interaction`: if the question becomes about designing rules under which agents will produce a desired equilibrium, hook upward to `mechanism-design` (deferred — surface the flag).
- After `strategic-interaction`: if the question becomes specifically about signaling-game dynamics (asymmetric information, costly signals), hook sideways to `signaling` (deferred — surface the flag).
- After `strategic-interaction`: if the question shifts from analyzing the game to actually negotiating it, hook sideways to T13 (`principled-negotiation` or `third-side`).
- After `strategic-interaction`: if the question shifts to "where could this strategic structure fail", hook sideways to T7 (`pre-mortem-fragility` or `fragility-antifragility-audit`).
- After `strategic-interaction`: if the question is really about who benefits and who has power rather than equilibrium analysis, hook sideways to T2 (`cui-bono`).

**Singleton note.** T18 currently has one resident mode (`strategic-interaction`). Expansion candidates `mechanism-design` and `signaling` are deferred per CR-6.

---

## T19 — Spatial Composition

```
[Territory identified: spatial composition, layout-as-primary-content]

Q1 (stance + specificity): "Is this a contemplative reading of a composition
                             where what matters is what the empty spaces and the
                             still moments do (often aesthetic input — painting,
                             garden, room, page),
                             or an analytical reading of a composition where the
                             question is what the layout's structure makes possible
                             or impossible (often applied input — dashboard, urban
                             scene, information graphic),
                             or a deep place-reading where the question is what the
                             place itself is (genius loci, image of the place),
                             or specifically about how densely the composition packs
                             information without losing legibility?"
  ├─ "contemplative reading, aesthetic, what the voids and stillness do" →
        ma-reading (Wave 2, Japanese aesthetics)
  ├─ "universal compositional principles, what the layout does" →
        compositional-dynamics (Wave 2, Gestalt + Arnheim)
  ├─ "deep place-reading, what the place itself is" →
        place-reading-genius-loci (Wave 3, Alexander + Norberg-Schulz)
  ├─ "information density, how densely the composition packs information" →
        information-density (Wave 3, Tufte + Bertin)
  └─ ambiguous → compositional-dynamics (the universal-principle Tier-2 default
                  when the input doesn't signal aesthetic-vs.-applied clearly)
```

**Axes used.** Stance (contemplative vs. analytical-applied vs. deep-evaluative) + specificity (aesthetic-experiential vs. universal-perceptual vs. operational-applied vs. information-graphic). T19 carries five open debates at the territory level per Decision G — see `Reference — Analytical Territories.md` T19 entry.

**Default route.** `compositional-dynamics` at Tier-2 when ambiguous (the universal-perceptual mode that applies across both aesthetic and applied inputs; ma-reading is the contemplative-aesthetic sibling, place-reading-genius-loci the deep-place sibling, information-density the applied-information-graphic sibling).

**Escalation hooks.**
- After `compositional-dynamics`: if the input is genuinely aesthetic and the user wants the contemplative mode that articulates what the voids and stillness do, hook sideways to `ma-reading`.
- After `ma-reading`: if the user wants an analytical/predictive complement to the contemplative reading, hook sideways to `compositional-dynamics`.
- After any of {`ma-reading`, `compositional-dynamics`}: if the question is fundamentally about *what this place is* (deep place-character), hook sideways to `place-reading-genius-loci`.
- After any T19 mode on a dashboard or chart: if the question is specifically chart-encoding-misfit rather than generic compositional critique, hook sideways to `information-density`.
- After any T19 mode on a network diagram: if the question is "what relations does this assert" rather than "what is the layout doing", hook sideways to T11 `spatial-reasoning` per the canonical T11↔T19 disambiguator.
- After any T19 mode: if the prompt is really open-ended exploration of what the composition opens up rather than analytical reading, hook sideways to T20 (`passion-exploration`).

**Reserved-mode note.** A fifth candidate — Information-Graphic Visual-Hierarchy Analysis — is held in reserve. Promotion threshold is recorded in `Reference — Analytical Territories.md` T19 entry. Below threshold, route information-graphic inputs through `compositional-dynamics` with Tufte/Bertin/Cleveland citations.

---

## T20 — Open Exploration (Generative)

```
[Territory identified: open exploration, generative work on an open prompt]

Route: passion-exploration (Tier-2, territory founder)
```

**Axes used.** Specificity (founder mode at personal-interest specificity). Idea-development and research-question-generation variants are deferred per CR-6.

**Default route.** `passion-exploration` at Tier-2 — singleton at current population. No within-territory disambiguation needed.

**Escalation hooks.**
- After `passion-exploration`: if the exploration crystallizes into a creative work the user wants to actually develop, hook upward to `idea-development` (deferred — surface the flag).
- After `passion-exploration`: if the exploration crystallizes into a research question the user wants to pursue, hook upward to `research-question-generation` (deferred — surface the flag).
- After `passion-exploration`: if the exploration crystallizes into a specifiable project (Crystallization Detection per Decision M), hand off to T21 (`project-mode`).
- After `passion-exploration`: if the exploration is really an orientation question in an unfamiliar space, hook sideways to T14 (`quick-orientation` or `terrain-mapping`).
- After `passion-exploration`: if the exploration is really a synthesis-across-domains operation, hook sideways to T12 (`synthesis` or `dialectical-analysis`).

**Singleton note.** T20 currently has one resident mode (`passion-exploration`). Expansion candidates `idea-development` and `research-question-generation` are deferred per CR-6. Crystallization Detection lives within this territory's documentation and within `passion-exploration`'s mode spec rather than as a separate meta-architectural mode (per Decision M).

---

## T21 — Execution / Project Mode (Non-Analytical)

```
[Territory identified: execution or formatting, non-analytical]

Q1 (situation): "Are you executing a defined project (walk through the steps),
                  or formatting material under a structural template?"
  ├─ "execute a defined project" → project-mode
  ├─ "format material under a template" → structured-output
  └─ ambiguous → project-mode (the more common path; structured-output is
                  invoked when explicitly formatting)
```

**Axes used.** Specificity — the territory's primary axis (per execution type).

**Default route.** `project-mode` when ambiguous and the input has any project-execution shape; `structured-output` when the input is explicitly material to be formatted.

**Escalation hooks.** None within the analytical routing tree — T21 sits outside it. T21 modes do not escalate into analytical territories; if analytical work is needed, that surfaces as a new top-level routing decision.

**Singleton-style note.** T21 has two resident modes but they are non-analytical (no "— Analysis" suffix per Decision L). The territory exists for completeness and to mark execution as outside the analytical routing tree.

---

*End of Reference — Within-Territory Disambiguation Trees.*
