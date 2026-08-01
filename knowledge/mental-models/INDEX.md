---
nexus:
  - ora
type: reference
tags:
  - reference
  - index
  - lenses
  - mental-models
date created: 2026-05-04
date modified: 2026-06-17
---

# Lenses — Index

*Per-lens index for the mental-model files in `Lenses/`. 240 lens files currently. Each lens is one mental model — first principles, OODA loop, loss aversion, etc. — formatted as an atomic note for ChromaDB ingestion. Modes reference lenses to declare their epistemic dependencies; lenses surface via Step 2 concept RAG when classified-relevant to the analysis.*

*Authoritative spec for lens structure:* `Reference — Lens Library Specification.md`.
*Lens-to-mode mapping:* the `Lens Dependencies` section in each mode spec under `Modes/`.

---

## Cognitive biases and heuristics

- **`affect-heuristic.md`** — Decisions driven by the emotional resonance of options rather than analysis.
- **`anchoring.md`** — Disproportionate weight on the first piece of information encountered.
- **`availability-heuristic.md`** — Estimating likelihood by how easily examples come to mind.
- **`base-rate-neglect.md`** — Ignoring background frequencies when evaluating specific cases.
- **`confirmation-bias.md`** — Preferentially noticing evidence that confirms existing beliefs.
- **`decoy-effect.md`** — Adding a third option shifts preference between the original two.
- **`endowment-effect.md`** — Valuing what you own more than what you don't.
- **`framing-effect.md`** — Same content, different presentation, different decisions.
- **`fundamental-attribution-error.md`** — Attributing others' behavior to character, our own to circumstance.
- **`hindsight-bias.md`** — Perceiving past events as more predictable than they were.
- **`hyperbolic-discounting.md`** — Disproportionately discounting near-term vs. far-term value.
- **`kahneman-tversky-bias-catalog.md`** — Cross-mode catalog of core judgment biases and debiasing checks.
- **`loss-aversion.md`** — Losses weighted ~2x gains in subjective utility.
- **`mental-accounting.md`** — Treating money differently based on its source or designated category.
- **`narrative-instinct.md`** — Compulsion to organize disconnected facts into a story.
- **`prospect-theory.md`** — Kahneman-Tversky's S-curve over outcomes; underlies loss aversion + framing.
- **`representativeness-heuristic.md`** — Judging probability by similarity to a stereotype.
- **`status-quo-bias.md`** — Default-toward-current-state preference.
- **`sunk-cost-fallacy.md`** — Continuing investment because of prior commitment, not future value.
- **`survivorship-bias.md`** — Inferring from survivors while ignoring those who didn't.
- **`system-one-system-two.md`** — Kahneman's dual-process theory: fast intuitive vs. slow deliberative.

## Decision-making and judgment

- **`backward-induction.md`** — Solving sequential decisions by reasoning from the endpoint backward.
- **`bayesian-reasoning.md`** — Updating belief in proportion to the evidence's diagnostic strength.
- **`bounded-rationality.md`** — Simon: rationality constrained by information, time, cognitive capacity.
- **`circle-of-competence.md`** — Buffett's principle: act inside what you genuinely understand.
- **`decision-trees.md`** — Branching analysis of choice nodes and probability nodes.
- **`falsifiability.md`** — Popper: a claim's scientific status depends on what could prove it wrong.
- **`first-principles.md`** — Decompose to fundamentals, rebuild from there.
- **`inversion.md`** — Solve forward problems by working backward from the failure mode.
- **`map-territory.md`** — The model is not the modeled thing; conflating them produces errors.
- **`occams-razor.md`** — Prefer the simpler explanation that accounts for the evidence.
- **`probabilistic-thinking.md`** — Reason in distributions, not point estimates.
- **`rumelt-strategy-kernel.md`** — Diagnosis / guiding policy / coherent action as the kernel of real strategy.
- **`satisficing.md`** — Accept the first option meeting threshold criteria; don't optimize.
- **`second-order-thinking.md`** — Ask "and then what?" through multiple consequence layers.
- **`thought-experiments.md`** — Test claims by imagining controlled hypothetical scenarios.

## Game theory and strategic interaction

- **`asymmetric-warfare.md`** — Strategic patterns when adversaries have very different capabilities.
- **`brinkmanship.md`** — Pushing a confrontation to the edge to force concession.
- **`game-theory-equilibrium-concepts.md`** — Dominant strategy, Nash, mixed, subgame-perfect, coordination, and efficiency concepts.
- **`mutually-assured-destruction.md`** — Stable deterrence through equal capacity for retaliation.
- **`nash-equilibrium.md`** — A strategy profile where no player benefits from unilateral deviation.
- **`prisoners-dilemma.md`** — Canonical case where individual rationality produces collective bad outcome.
- **`schelling-strategy-of-conflict.md`** — Commitment, threats, focal points, brinkmanship, and mixed-motive conflict.
- **`schelling-point.md`** — Focal point coordinating expectations without communication.
- **`signaling.md`** — Costly action used to communicate information credibly.
- **`tit-for-tat.md`** — Iterated-game strategy: cooperate, then mirror the opponent's last move.
- **`cooperation.md`** — Conditions under which cooperation emerges and stabilizes.

## Negotiation and conflict

- **`batna.md`** — Best Alternative to a Negotiated Agreement; defines walk-away threshold.
- **`fisher-ury-principled-negotiation.md`** — Separate people from problem; interests not positions; objective criteria.
- **`lewicki-negotiation-frameworks.md`** — Distributive/integrative negotiation, ZOPA, reservation points, and concession dynamics.
- **`ury-third-side.md`** — The community surrounding a conflict has an active role in transforming it.
- **`voss-tactical-empathy.md`** — Tactical empathy, labels, mirrors, calibrated questions, and Black Swan search for hard negotiations.
- **`procedural-justice.md`** — Perceived fairness of process drives acceptance more than outcome.

## Probability, statistics, prediction

- **`expected-utility-theory.md`** — Probability-weighted utility model for comparing risky options.
- **`pearl-causal-graphs.md`** — DAG-based causal modeling; distinguishes correlation, confounding, intervention.
- **`pearl-do-calculus.md`** — Pearl's algebra for reasoning about interventions on causal graphs.
- **`knightian-risk-uncertainty-ambiguity.md`** — Distinguishes measurable risk, ambiguity, Knightian uncertainty, and unknown unknowns.
- **`regression-to-mean.md`** — Extreme observations tend to be followed by less-extreme ones.
- **`tetlock-superforecasting.md`** — Calibration practices distinguishing accurate from overconfident forecasters.
- **`wisdom-of-crowds.md`** — Aggregated independent estimates often beat individual experts.

## Causal inference and process tracing

- **`bennett-checkel-process-tracing-tests.md`** — Hoop / smoking-gun / straw-in-the-wind tests for causal claims.
- **`five-whys.md`** — Toyota's iterative "why" question to surface root cause.
- **`fishbone-diagram.md`** — Ishikawa cause-categorization (people / process / equipment / environment / measurement / materials).
- **`force-field-analysis.md`** — Lewin: forces driving change vs. forces resisting change.

## Argumentation and rhetoric

- **`cda-fairclough-presupposition-and-nominalization.md`** — Critical Discourse Analysis scan for presupposition, nominalization, passives, and agency deletion.
- **`toulmin-model.md`** — Claim / data / warrant / backing / rebuttal / qualifier as argument anatomy.
- **`walton-schemes-and-critical-questions.md`** — Pragmatic argumentation schemes with explicit critical questions per scheme.
- **`devils-advocacy.md`** — Designated dissenter role in deliberation.
- **`stanley-propaganda.md`** — Jason Stanley's analysis of propaganda mechanisms in democracy.
- **`goffman-frame-analysis.md`** — Goffman: experience organized into interpretive frames.
- **`entman-framing-functions.md`** — Entman's four framing functions (define problem / diagnose cause / make moral judgment / suggest remedy).
- **`iyengar-episodic-thematic.md`** — Episodic vs. thematic issue framing and responsibility attribution.
- **`lakoff-conceptual-metaphor.md`** — Lakoff: thought structured by source-domain → target-domain metaphor mappings.
- **`rapoport-rules-of-engagement.md`** — Construction-before-critique protocol for fair steelmanning and useful red-team critique.
- **`shackel-motte-and-bailey.md`** — Tracks modest "motte" claims shielding stronger "bailey" claims.

## Systems thinking

- **`bottlenecks.md`** — System throughput limited by the slowest constraint (Theory of Constraints).
- **`emergence.md`** — System-level properties not reducible to component properties.
- **`equilibrium.md`** — A state in which forces balance and the system is stable absent perturbation.
- **`feedback-loops.md`** — Reinforcing loops amplify; balancing loops stabilize.
- **`forrester-industrial-dynamics.md`** — Managerial feedback-system lens for policies, information delays, and industrial-system behavior.
- **`leverage.md`** — Small inputs producing disproportionate outputs at the right system point.
- **`meadows-twelve-leverage-points.md`** — Ordered system-intervention points from parameters to paradigms.
- **`practical-drift.md`** — Snook: gradual divergence between formal procedure and actual practice.
- **`scale.md`** — Behavior changes qualitatively as a system scales up or down.
- **`senge-system-archetypes.md`** — Recurring feedback-loop patterns such as limits to growth, fixes that fail, and escalation.
- **`niches.md`** — Resource-and-constraint configurations that select for certain strategies.
- **`evolution-natural-selection.md`** — Variation + selection + heritability produces adaptation over generations.
- **`creative-destruction.md`** — Schumpeter: incumbents displaced as new productive forms emerge.
- **`diminishing-returns.md`** — Marginal output declines as input grows past a threshold.
- **`critical-mass.md`** — The threshold beyond which a self-sustaining process can begin.
- **`sterman-system-dynamics-modelling.md`** — Stock-and-flow modelling discipline for behavior over time, delays, and policy resistance.

## Failure modes and risk

- **`adversarial-case-studies.md`** — Transfer protocol for extracting attack paths from real adversarial precedents.
- **`failure-mode-literature.md`** — Catalog of component, interface, process, human, organizational, detection, and recovery failures.
- **`normal-accident-theory.md`** — Perrow: tightly coupled, complex systems make catastrophic failures inevitable.
- **`normalization-of-deviance.md`** — Vaughan: small acceptable violations accumulate into systemic risk.
- **`post-mortem-analyses.md`** — Reads comparable failures for causal pathways, warning signs, and decision-point lessons.
- **`swiss-cheese-model.md`** — Reason: accidents pass through aligned holes in successive defensive layers.
- **`taleb-fragility-antifragility.md`** — Taleb: fragile / robust / antifragile responses to volatility.
- **`black-swan` (see `taleb-fragility-antifragility.md`)** — Rare high-impact events that ex-post are rationalized as predictable.
- **`premortem-analysis.md`** — Klein: imagine the project has failed and explain why.
- **`recovery-window.md`** — Time available between failure onset and unrecoverability.
- **`margin-of-safety.md`** — Buffer between operating point and the failure threshold.
- **`reward-undermining.md`** — Extrinsic rewards displacing intrinsic motivation.

## Behavioral economics and incentives

- **`adverse-selection.md`** — Information asymmetry causes the worst types to self-select into a market.
- **`moral-hazard.md`** — Insulation from consequence changes behavior at the margin.
- **`principal-agent-problem.md`** — Misaligned incentives between principal and the agent acting on their behalf.
- **`tragedy-of-the-commons.md`** — Individually rational use of a shared resource produces collective ruin.
- **`free-rider-problem.md`** — Non-excludable benefits incentivize non-contribution.
- **`fgl-fear-greed-laziness.md`** — Motivational scan for loss avoidance, gain seeking, and inertia.
- **`incentives.md`** — "Show me the incentive, I'll show you the outcome" (Munger).
- **`commitment-consistency.md`** — Cialdini: people honor public, voluntary, written commitments.
- **`reciprocity.md`** — Cialdini: an unsolicited favor creates obligation to repay.
- **`social-proof.md`** — Cialdini: behavior of others as a default action signal.
- **`scarcity.md`** — Limited availability increases perceived value.
- **`choice-architecture.md`** — Thaler-Sunstein: how options are presented shapes which is chosen.
- **`nudge` (see `choice-architecture.md`)** — Default-setting and presentation design that influences choice without restricting options.
- **`pareto-principle.md`** — ~80% of effects from ~20% of causes; uneven distributions are normal.
- **`supply-demand.md`** — Price equilibrates supply and demand; shortages and surpluses signal misalignment.
- **`winners-curse.md`** — In auctions of uncertain-value items, the winner is likely to have overestimated.
- **`greshams-law.md`** — Bad money drives out good when both circulate at official parity.

## Spatial composition and visual perception

- **`alexander-pattern-language.md`** — Christopher Alexander: design as a vocabulary of recurring spatial patterns.
- **`appleton-prospect-refuge.md`** — Habitat preference: vantage (prospect) + shelter (refuge).
- **`arnheim-compositional-forces.md`** — Arnheim: visual forces (gravity, balance, dynamic tension) as primary perceptual content.
- **`bachelard-topoanalysis.md`** — Bachelard: the felt resonance of intimate spaces (corner, drawer, attic).
- **`bertin-visual-variables.md`** — Bertin's seven retinal variables (position, size, value, texture, color, orientation, shape).
- **`bordwell-poetics-of-cinema.md`** — Film poetics lens for mise-en-scene, shot design, viewer attention, and inference.
- **`bringhurst-typographic-hierarchy.md`** — Bringhurst: typographic structure as the architecture of reading.
- **`cleveland-mcgill-perceptual-tasks.md`** — Ranked accuracy of visual encoding tasks (position > length > angle > area > volume > color).
- **`gestalt-grouping-principles.md`** — Proximity, similarity, closure, continuity, common fate.
- **`japanese-aesthetics-catalog.md`** — Wabi-sabi, ma, yūgen, mono no aware, kanso, fukinsei.
- **`kaplan-attention-restoration.md`** — Kaplan: natural environments restore directed attention.
- **`lynch-image-of-the-city.md`** — Lynch's five elements (paths, edges, districts, nodes, landmarks).
- **`norberg-schulz-genius-loci.md`** — Norberg-Schulz: the spirit of place as design and analysis target.
- **`tufte-data-ink-chartjunk.md`** — Tufte: maximize data-ink ratio; eliminate decorative non-data ink.
- **`tversky-spatial-correspondence-principles.md`** — Spatial-cognition checks for congruence between layout and reasoning task.

## Conceptual / philosophical

- **`cappelen-plunkett-conceptual-engineering.md`** — Conceptual engineering: deliberately revising what concepts mean.
- **`cynefin-framework.md`** — Snowden's Clear / Complicated / Complex / Chaotic / Confused contexts and their respective approaches.
- **`hanlons-razor.md`** — Don't attribute to malice what's adequately explained by stupidity.
- **`hegelian-dialectic-aufheben.md`** — Sublation as cancel / preserve / lift in dialectical analysis.
- **`kuhn-paradigm-incommensurability.md`** — Paradigm conflict, standards, anomaly, and partial translation limits.
- **`lakatos-hard-core-protective-belt.md`** — Research-program hard core, auxiliary belt, and progressive vs. degenerating adjustment.
- **`ordinary-language-philosophy-tradition.md`** — Use-sensitive conceptual clarification through ordinary-language practice, contrasts, and category checks.

## Policy and systemic critique

- **`allisons-three-lenses.md`** — Allison: rational-actor / organizational-process / governmental-politics frames for policy analysis.
- **`arrows-impossibility-theorem.md`** — No ranked-choice voting system satisfies all reasonable criteria simultaneously.
- **`public-choice-theory.md`** — Political and bureaucratic behavior analyzed through incentives, collective action, and rent seeking.
- **`rittel-webber-wicked-characteristics.md`** — Rittel-Webber characteristics for distinguishing wicked problems from merely hard problems.
- **`ulrich-csh-boundary-categories.md`** — Ulrich's twelve boundary questions for Critical Systems Heuristics.

## Coordination and process

- **`de-bono-consequence-and-sequel.md`** — Immediate, short-, medium-, and long-term consequence tracing.
- **`debono-ago.md`** — de Bono Aims / Goals / Objectives clarification before choosing actions or outputs.
- **`debono-pmi.md`** — Plus / Minus / Interesting scan for balanced critique and benefit analysis.
- **`ooda-loop.md`** — Boyd: Observe / Orient / Decide / Act as the contest cycle.
- **`differential-diagnosis-schema.md`** — Medical schema for differential diagnosis applicable to non-medical reasoning.
- **`klein-pre-mortem.md`** — Klein's pre-mortem method (lens shared by `pre-mortem-action.md` and `pre-mortem-fragility.md`).
- **`mcdm-methods.md`** — Multi-Criteria Decision Methods (AHP, TOPSIS, weighted-sum, etc.).
- **`novak-concept-map-tradition.md`** — Concept maps as focus-question-driven, proposition-labeled, hierarchical knowledge maps.
- **`opv-other-points-of-view.md`** — de Bono perspective-taking scan for other actors' knowledge, incentives, and constraints.
- **`structural-relationship-taxonomy.md`** — Typed-edge taxonomy for causal, temporal, hierarchical, dependency, evidential, and analogical relations.
- **`shell-scenario-method.md`** — Shell-style scenario planning through focal question, driving forces, uncertainties, scenarios, and signposts.
- **`stakeholder-analysis-frameworks.md`** — Standard stakeholder-mapping approaches (power-interest grid, salience model).
- **`sensemaking.md`** — Weick: retrospective construction of meaning from streams of events.

## Group dynamics

- **`groupthink.md`** — Janis: cohesive groups suppressing dissent in pursuit of consensus.
- **`psychological-safety.md`** — Edmondson: shared belief that the team is safe for interpersonal risk.
- **`seeing-the-front.md`** — Direct observation at the operational edge vs. command-post abstraction.

## Information and inference

- **`cia-tradecraft-red-team.md`** — Heuer / CIA tradecraft for adversarial structured analysis.
- **`cross-domain-analogical-mapping.md`** — Structure-mapping discipline for analogies between distant domains.
- **`heuer-ach-diagnosticity.md`** — ACH diagnosticity check for evidence that separates hypotheses.
- **`heuer-ach-methodology.md`** — Analysis of Competing Hypotheses protocol for matrix-based hypothesis comparison.
- **`precommitment.md`** — Strategic commitment that constrains future self to maintain credibility.
- **`red-queen-effect.md`** — "Run as fast as you can to stay in place" — coevolutionary arms race.

## Optional drift-repair lenses

- **`adornian-negative-dialectics.md`** - Preserves contradiction and non-identity when synthesis would falsely reconcile what remains damaged or irreducible.
- **`albers-interaction-of-color.md`** - Analyzes color as relational and context-dependent rather than as isolated hue value.
- **`alexander-isolated-demands-for-rigor.md`** - Flags asymmetric demands for unusually high proof applied to one claim but not comparable alternatives.
- **`alexander-nature-of-order.md`** - Analyzes wholeness, centers, structure-preserving transformations, and living structure in built form.
- **`axelrod-evolution-of-cooperation.md`** - Analyzes repeated games where reciprocity, shadow of the future, and strategy ecology allow cooperation to emerge.
- **`benford-snow-collective-action-frames.md`** - Examines movement frames through diagnostic, prognostic, motivational, resonance, and mobilization functions.
- **`bernays-engineering-of-consent.md`** - Analyzes public-relations artifacts as deliberate construction of consent through symbols, authority, and staged social proof.
- **`bloom-taxonomy.md`** - Classifies learning aims by cognitive level so domain induction can scaffold from recall through creation.
- **`cage-silence-and-framing-of-attention.md`** - Treats silence, duration, and environmental sound as active framing of attention rather than absence.
- **`chong-druckman-emphasis-equivalence.md`** - Distinguishes emphasis framing from equivalence framing and checks frame strength, competition, and exposure.
- **`copi-informal-fallacy-taxonomy.md`** - Maps artifacts to canonical informal fallacy families while preserving the evidence standard for each label.
- **`counter-deception-frameworks.md`** - Checks whether evidence, signals, and apparent inconsistencies could be planted, manufactured, or adversarially shaped.
- **`cross-domain-cascade-patterns.md`** - Tracks cascades that move across domains such as technical, social, economic, legal, and cultural systems.
- **`dagitty-causal-dag-formalism.md`** - Uses DAG adjustment logic to reason about causal paths, confounding, colliders, and sufficient adjustment sets.
- **`debono-concept-fan.md`** - Climbs from a specific idea to broader concepts, then fans back down into alternative routes.
- **`debono-fip.md`** - Identifies First Important Priorities before execution or project structuring begins.
- **`debono-random-entry.md`** - Uses an unrelated stimulus to break habitual search paths and generate lateral associations.
- **`dekker-just-culture.md`** - Reframes human error through accountability, learning, system conditions, and just-culture distinctions.
- **`dennett-charitable-interpretation.md`** - Reconstructs an opponent's position so clearly and fairly that critique addresses its strongest recognizable form.
- **`domain-specific-frameworks-per-deliverable-type.md`** - Selects the relevant domain framework based on the actual deliverable rather than applying a generic project frame.
- **`ellul-integration-vs-agitation.md`** - Distinguishes propaganda that integrates people into an existing order from propaganda that mobilizes agitation.
- **`engineering-and-technical-analysis-module.md`** - Adds technical-domain checks for mechanisms, constraints, interfaces, tolerances, and feasibility when clarification concerns engineered systems.
- **`few-information-dashboard-design.md`** - Evaluates dashboards by information density, comparative visibility, signal priority, and cognitive load.
- **`format-template-library.md`** - Selects output structure by document type, audience, use case, and completion criteria.
- **`foucault-discursive-formation.md`** - Maps rules that make certain statements, objects, subjects, and authorities sayable within a discourse.
- **`gallie-essentially-contested-concepts.md`** - Identifies concepts whose proper use is persistently contestable because they are appraisive, complex, and internally open-ended.
- **`habermas-discourse-ethics.md`** - Tests legitimacy through inclusion, reason-giving, absence of coercion, and whether affected parties could accept the norm in practical discourse.
- **`hambidge-dynamic-symmetry.md`** - Uses dynamic symmetry as a proportional vocabulary while treating it as heuristic rather than proof.
- **`hamblin-fallacies-standard-treatment-critique.md`** - Uses Hamblin's critique of textbook fallacy treatment to avoid unsupported fallacy labeling.
- **`haslanger-ameliorative-analysis.md`** - Asks what a concept should mean to serve legitimate critical, explanatory, or emancipatory purposes.
- **`herman-chomsky-five-filter-propaganda-model.md`** - Situates media output through ownership, advertising, sourcing, flak, and ideological filters.
- **`hermeneutic-circle.md`** - Clarifies interpretation through movement between part and whole, pre-understanding and revised understanding.
- **`itten-seven-contrasts.md`** - Uses Itten's seven color-contrast categories to analyze visual tension, hierarchy, and compositional force.
- **`kahneman-planning-fallacy.md`** - Checks whether plans underestimate time, cost, and obstacles by using inside-view optimism instead of outside-view base rates.
- **`kellert-biophilic-design.md`** - Assesses sustained-occupancy design through direct nature, indirect nature, and place-based human-nature patterns.
- **`kosslyn-graph-design.md`** - Assesses graphs through cognitive communication principles: discriminability, organization, compatibility, and message fit.
- **`kriesberg-constructive-conflicts.md`** - Analyzes conflict trajectory, escalation, de-escalation, constructive outcomes, and historical depth.
- **`lakoff-strict-father-nurturant-parent.md`** - Maps political moral language to Lakoff's strict-father and nurturant-parent family models.
- **`larkin-simon-diagram-literacy.md`** - Explains why diagrams can outperform sentential representations by grouping information and supporting perceptual inference.
- **`leading-indicators-methodology.md`** - Finds near-term proxy signals that can warn of distant or delayed effects before lagging outcomes arrive.
- **`lederach-conflict-transformation.md`** - Reads conflict through relationships, social patterns, constructive change, and long-horizon transformation.
- **`lupton-thinking-with-type.md`** - Uses typographic form, hierarchy, grid, spacing, and readability as analytical variables.
- **`macintyre-traditions-of-inquiry.md`** - Maps rationality as tradition-embedded inquiry with internal standards, virtues, and unresolved epistemic crises.
- **`marxist-historical-materialism.md`** - Reads ideas, institutions, and conflict through material conditions, production relations, class power, and historical development.
- **`mechanism-design-foundations.md`** - Flips game analysis from predicting play to designing rules so self-interested behavior produces desired outcomes.
- **`midgley-systemic-intervention.md`** - Frames intervention as boundary critique plus methodological pluralism, asking whose purposes and methods are included or excluded.
- **`minimax-regret-and-robust-decision-making.md`** - Compares choices by regret under adverse states and by robustness across deep uncertainty.
- **`munzner-visualization-analysis-and-design.md`** - Checks visualization choices against the task-data-encoding design triangle.
- **`novice-expert-cognition.md`** - Distinguishes novice surface-feature reasoning from expert chunking, pattern recognition, and deep-structure organization.
- **`pragma-dialectics-rules-for-critical-discussion.md`** - Evaluates argumentation as a rule-governed critical discussion aimed at resolving a difference of opinion.
- **`raiffa-art-and-science-of-negotiation.md`** - Adds reservation price, ZOPA, efficient frontier, and analytic bargaining structure to negotiation analysis.
- **`real-options-methodology.md`** - Values staged commitments, deferral, expansion, abandonment, and option-preserving moves under uncertainty.
- **`reinforcing-counteracting-distinction.md`** - Separates consequences that amplify an initial effect from consequences that offset, dampen, or reverse it.
- **`relph-place-and-placelessness.md`** - Evaluates authenticity, identity, insideness, outsideness, and placelessness in environments.
- **`rorty-final-vocabulary.md`** - Identifies the words a worldview uses as ultimate justification and cannot justify without circularity.
- **`schon-rein-frame-reflection.md`** - Surfaces policy frames, naming/framing moves, and frame conflicts that block agreement.
- **`schrader-transcendental-style.md`** - Reads slow-cinema restraint, delay, stasis, and decisive action through Schrader's transcendental-style frame.
- **`schwartz-art-of-the-long-view.md`** - Uses scenario stories to stretch strategic imagination and test decisions against multiple plausible futures.
- **`second-order-effects-catalog.md`** - Catalogs downstream effects such as precedent, signaling, path dependence, adaptation, and incentive shifts.
- **`snow-benford-frame-alignment.md`** - Analyzes diagnostic, prognostic, and motivational framing plus alignment processes in movement or campaign communication.
- **`stakeholder-incidence-analysis.md`** - Maps who receives benefits, who bears costs, and how those effects distribute across stakeholder classes.
- **`steep-framework.md`** - Scans social, technological, economic, environmental, and political drivers for scenario planning.
- **`strategic-2x2-matrix-tradition.md`** - Uses two-axis strategic matrices to expose option territories, constraint tradeoffs, and missing quadrants.
- **`structural-isomorphism-detection.md`** - Tests whether two domains share the same relational structure despite different surface content.
- **`structural-pattern-libraries.md`** - Provides reusable spatial structures such as hub-and-spoke, chain, cycle, star, cluster bridge, and orphan.
- **`taleb-extremistan-mediocristan.md`** - Distinguishes thin-tailed Mediocristan domains from fat-tailed Extremistan domains where extremes dominate outcomes.
- **`tanizaki-in-praise-of-shadows.md`** - Analyzes shadow, patina, dimness, depth, and indirect illumination as positive aesthetic material.
- **`taxonomic-frameworks-for-the-target-domain.md`** - Uses existing domain taxonomies to orient terrain maps without inventing categories prematurely.
- **`thompson-mind-and-heart-of-the-negotiator.md`** - Adds psychological, emotional, cultural, and relational dynamics to negotiation analysis.
- **`tuan-space-and-place.md`** - Distinguishes abstract space from lived place through experience, attachment, movement, and meaning.
- **`wilkinson-grammar-of-graphics.md`** - Decomposes charts into data, transformations, scales, coordinates, guides, and geometric marks.

## Adjacencies and uncategorized

- **`differential-diagnosis-schema.md`** — *(also listed under Coordination)*
- **`inertia.md`** — Tendency of established systems and behaviors to persist absent applied force.
- **`trade-offs.md`** — Acknowledgment that improvement on one dimension typically costs on another.

---

## Conventions

- **Filenames:** lowercase-hyphenated (kebab-case). Names are concept-name-first when distinctive (`prospect-theory.md`); author-name-first when the author is the load-bearing reference (`pearl-causal-graphs.md`, `klein-pre-mortem.md`).
- **YAML on both sides:** vault and ora copies both carry frontmatter.
- **Pairing:** `vault/Lenses/<lens>.md` ↔ `~/ora/knowledge/mental-models/<lens>.md`. One-to-one filename match. See `Framework — System File Drift Correction.md`.

## See also

- `Reference — Lens Library Specification.md` — authoritative spec for lens-spec template, slot conventions, sharing rules, maintenance protocol.
- `Registry — Mode Registry.md` — each mode entry lists its lens dependencies.
- `Modes/INDEX.md` — mode files that reference these lenses.
- `Reference — Edward de Bono's Complete Thinking Systems.md` — extended treatment of de Bono's overlapping toolkit (Six Hats, Lateral Thinking, CoRT) which informs many lenses here.

---

*Note on completeness: this index covers the 240 lens files present after the 2026-06-17 drift-repair additions. Categorization is informal — a few lenses (e.g., `klein-pre-mortem.md`, `differential-diagnosis-schema.md`) appear under more than one category since they belong analytically to multiple. New lenses should be added in alphabetical order within the most appropriate category.*
