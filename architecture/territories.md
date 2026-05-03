
# Reference — Analytical Territories

*The 21-territory inventory for Ora's mode registry. Each territory is a coherent region of analytical work characterized by shared problem-shape, input-types, and output contracts. Modes are positions within territories; every mode lives in exactly one home territory (Decision D parsing principle). This file is the load-bearing reference cited from `Reference — Mode Specification Template.md`, `Reference — Within-Territory Disambiguation Trees.md`, `Reference — Cross-Territory Adjacency.md`, and the four-stage pre-routing pipeline.*

---

## How to read this file

Every territory entry has the same shape:

- **Territory ID + Name** — `T<n>. <Display Name>`
- **Super-cluster** — A (Argument & Reasoning), B (Causation, Hypothesis & Mechanism), C (Decision, Future & Risk), D (Position, Stakeholder & Strategy), E (Synthesis, Orientation, Structure & Generation). Super-clusters are for orientation only; routing operates per-territory.
- **Characterization** — what the territory is for.
- **Boundary conditions** — input requirements; what is in vs. out of scope.
- **Primary axis** — the dominant axis along which member modes differ (depth, complexity, stance, or specificity).
- **Secondary axes** — additional gradation axes present.
- **Resident modes** — `mode_id` list with status (`existing` | `Wave 1` | `Wave 2` | `Wave 3` | `Wave 4` | `gap-deferred`). Status reflects the build state per the implementation plan, not analytical importance.
- **Adjacencies** — territories with which routing-level disambiguation may be required.
- **Cross-territory disambiguation pointers** — see `Reference — Cross-Territory Adjacency.md` for the disambiguating questions.
- **Coverage status** — `Strong` (all primary-axis positions filled) | `Near-Strong` (most positions filled) | `Moderate` (half) | `Partial` (a few positions filled) | `Gap-heavy` (mostly empty).
- **Open debates** — debates carried in territory documentation rather than mode specs. Most debates land in mode specs; T19 carries five at the territory level per Decision G.

The boundary-verification sub-deliverable appears at the end of this file. It enumerates, for each adjacent territory pair, the disambiguating question that distinguishes them. Per Decision D (parsing principle), if a candidate mode appears to fit two territories, it is parsed into two modes rather than dual-citizened. Pre-Mortem is the canonical case (parsed into `pre-mortem-action` for T6 and `pre-mortem-fragility` for T7); Systems Dynamics is the second (parsed into `systems-dynamics-causal` for T4 and `systems-dynamics-structural` for T17).

---

## Super-cluster A: Argument and Reasoning

### T1. Argumentative Artifact Examination

**Characterization.** Operations that take an existing argument, claim-set, position, or text-as-argument as input and evaluate its internal soundness, coherence, framing, or rhetorical structure.

**Boundary conditions.** Input must be a structured or semi-structured argumentative artifact (an article, memo, policy, debate transcript, stated position). Excludes evaluating *interests behind* the argument (T2) or evaluating *empirical claims* against external evidence (T5).

**Primary axis.** Depth (Coherence Audit → Frame Audit → Argument Audit molecular).
**Secondary axes.** Specificity (general argument vs. propaganda-specific vs. position-genealogy variants); stance is weak in T1.

**Resident modes.**
- `coherence-audit` — existing (built Wave 2, 2026-05-01). depth-light, neutral, internal-consistency.
- `frame-audit` — existing (built Wave 2, 2026-05-01). depth-light + stance-suspending, frame-surfacing.
- `propaganda-audit` — existing (built Wave 2, 2026-05-01). specificity-specialized + Stanley-influenced, adversarial-stance variant.
- `argument-audit` — existing (built Wave 4, 2026-05-01). depth-molecular, neutral synthesis.
- `position-genealogy` — gap-deferred. specificity-specialized + stance-historical, descriptive-historical.

**Adjacencies.** T2 (Interest and Power), T5 (Hypothesis Evaluation), T9 (Paradigm and Assumption Examination), T10 (Conceptual Clarification), T15 (Artifact Evaluation by Stance — Steelman cross-territory case).

**Coverage status.** Near-Strong after Wave 4 (foundational triad + Propaganda Audit; Position Genealogy deferred per CR-6).

### T2. Interest and Power Analysis

**Characterization.** Operations that ask, of a state of affairs, decision, claim, or text: who benefits, who pays, who has power to shape this, whose voices are absent, and how do interest structures explain what is observed.

**Boundary conditions.** Input is a situation, decision, or claim with multiple parties whose interests may diverge. Excludes negotiation/conflict-resolution operations (T13) and pure stakeholder-mapping without interest analysis (T8).

**Primary axis.** Complexity (Cui Bono → Stakeholder Mapping → Wicked Problems molecular; Decision Clarity is depth-molecular along same complexity ladder).
**Secondary axes.** Stance (descriptive cui bono vs. critical/Ulrich-CSH boundary critique).

**Resident modes.**
- `cui-bono` — existing. complexity-simple.
- `boundary-critique` — existing (built Wave 2, 2026-05-01). stance-critical (Ulrich CSH).
- `wicked-problems` — Phase 2 (mode created from existing framework per Decision H). complexity-systemic + depth-molecular.
- `decision-clarity` — existing (built Wave 4, 2026-05-01). depth-molecular, decision-maker-output. Paired with restructured `Framework — Decision Clarity Analysis.md`.

**Note on Stakeholder Mapping.** The `stakeholder-mapping` mode is built in Wave 1 but lives in T8 (Stakeholder Conflict). T2 routes to it via cross-territory adjacency when interest analysis requires multi-party complexity that exceeds Cui Bono.

**Adjacencies.** T1, T8, T13, T18.

**Coverage status.** Strong after Phase 2 + Wave 2 + Wave 4.

### T9. Paradigm and Assumption Examination

**Characterization.** Operations that step outside the assumed frame of a problem to examine the assumptions, paradigms, and worldviews that shape how the problem is being constructed.

**Boundary conditions.** Input is a problem, debate, or impasse where reframing is in play. Excludes within-frame causal investigation (T4) and within-frame hypothesis evaluation (T5).

**Primary axis.** Stance (suspending vs. comparing vs. critiquing).
**Secondary axes.** Depth (light atomic Paradigm Suspension → Frame Comparison → Worldview Cartography molecular).

**Resident modes.**
- `paradigm-suspension` — existing. stance-suspending.
- `frame-comparison` — existing (built Wave 2, 2026-05-01). stance-comparing.
- `worldview-cartography` — existing (built Wave 4, 2026-05-01). depth-molecular.

**Adjacencies.** T1 (Frame Audit operates on a single artifact's frame; Frame Comparison operates on two-or-more frames), T4 (within-frame causation vs. frame-as-cause), T5 (within-frame hypothesis evaluation vs. inter-frame disagreement).

**Coverage status.** Strong after Wave 2 + Wave 4.

### T10. Conceptual Clarification

**Characterization.** Operations that take a concept, term, or definitional disagreement as input and resolve, sharpen, engineer, or genealogically trace it.

**Boundary conditions.** Input is a concept whose meaning, scope, or normative status is in question. Excludes ordinary-language exposition where the concept is uncontested.

**Primary axis.** Stance (descriptive vs. ameliorative vs. essentially-contested).
**Secondary axes.** Depth (light Deep Clarification → Conceptual Engineering thorough).

**Resident modes.**
- `deep-clarification` — existing. depth-thorough, ordinary-language.
- `conceptual-engineering` — existing (built Wave 2, 2026-05-01). stance-ameliorative (Cappelen/Plunkett).
- `definitional-dispute` — gap-deferred. specificity-essentially-contested (Gallie).

**Adjacencies.** T1 (concept embedded in argument), T9 (concept embedded in paradigm).

**Coverage status.** Moderate after Wave 2; Definitional Dispute remains deferred per CR-6.

---

## Super-cluster B: Causation, Hypothesis, and Mechanism

### T4. Causal Investigation

**Characterization.** Operations that take an outcome, symptom, or pattern of events and trace backward to causes, mechanisms, or generative structures.

**Boundary conditions.** Input is an outcome or pattern; question is *why did this happen*. Excludes process mapping (T17 — *how does this work*) and mechanism understanding (T16 — *how do the parts produce the whole's behavior*).

**Primary axis.** Complexity (single cause-chain → feedback structure).
**Secondary axes.** Specificity (general → historical-event-specific); depth (light → DAG-formal).

**Resident modes.**
- `root-cause-analysis` — existing. complexity-single-cause-chain.
- `systems-dynamics-causal` — Phase 2 parse from `systems-dynamics` per Decision D. complexity-feedback-structure.
- `causal-dag` — existing (built Wave 3, 2026-05-01). depth-thorough + formalism-explicit (Pearl).
- `process-tracing` — existing (built Wave 3, 2026-05-01). specificity-historical-event (Bennett/Checkel).

**Adjacencies.** T9 (within-frame vs. frame-as-cause), T16, T17.

**Coverage status.** Strong after Wave 3.

### T5. Hypothesis Evaluation

**Characterization.** Operations that take multiple competing explanations and a body of evidence and adjudicate among them using diagnosticity, base rates, and Bayesian or quasi-Bayesian reasoning.

**Boundary conditions.** Input is two-or-more competing hypotheses plus evidence. Excludes single-hypothesis testing and excludes within-paradigm-debate cases that are really about frame (T9).

**Primary axis.** Depth (light differential-diagnosis → full Heuer ACH → Bayesian network molecular).
**Secondary axes.** Specificity (general ACH vs. forensic vs. scientific-hypothesis variants).

**Resident modes.**
- `differential-diagnosis` — existing (built Wave 1, 2026-05-01). depth-light.
- `competing-hypotheses` — existing. depth-thorough (Heuer ACH).
- `bayesian-hypothesis-network` — existing (built Wave 4, 2026-05-01). depth-molecular.

**Adjacencies.** T9 (within-frame vs. inter-frame disagreement), T1 (when hypotheses are themselves arguments).

**Coverage status.** Strong after Wave 4.

### T16. Mechanism Understanding

**Characterization.** Operations that take a phenomenon and explain *how* it works — the parts, their relationships, the process by which inputs become outputs.

**Boundary conditions.** Input is a phenomenon whose internal workings are sought. Excludes causal investigation (T4 — backward to causes) and process mapping (T17 — temporal flow).

**Primary axis.** Depth (mechanism founder mode at thorough depth).
**Secondary axes.** None at current population; grows specificity axis as domain-specific mechanism modes added.

**Resident modes.**
- `mechanism-understanding` — existing (built Wave 3, 2026-05-01) (territory founder).

**Adjacencies.** T4, T11, T17.

**Coverage status.** Moderate after Wave 3 (founder built; expansion deferred).

### T17. Process and System Analysis

**Characterization.** Operations that map a process, workflow, organization, or system as it currently is — identifying components, flows, bottlenecks, and dependencies. Diagnostic in posture; not yet seeking causes (T4) or interventions.

**Boundary conditions.** Input is a process, workflow, or system. Excludes causal investigation (why this happens) and excludes mechanism understanding (how parts produce behavior at the principle level rather than the operational level).

**Primary axis.** Specificity (general process vs. organizational structure vs. systems-dynamics-with-feedback).
**Secondary axes.** Complexity (single process → multi-process system).

**Resident modes.**
- `systems-dynamics-structural` — Phase 2 parse from `systems-dynamics` per Decision D. complexity-feedback (T4-T17 boundary case).
- `process-mapping` — existing (built Wave 3, 2026-05-01). specificity-process-flow.
- `organizational-structure` — gap-deferred. specificity-organizational.

**Adjacencies.** T4 (causal-vs.-structural framing of feedback), T11 (structural-relationship overlap), T16 (process vs. mechanism).

**Coverage status.** Moderate after Wave 3.

---

## Super-cluster C: Decision, Future, and Risk

### T3. Decision-Making Under Uncertainty

**Characterization.** Operations that take a decision context (alternatives, criteria, constraints, uncertainty) and produce structured guidance for choice.

**Boundary conditions.** Input is a decision the user faces. Excludes negotiation-like situations where the parties' conflict itself is the analytical object (T8/T13) and excludes decision-clarity-document production for a third-party decision-maker (`decision-clarity` lives in T2 because its primary work is interest/stakeholder articulation, not optimization-under-uncertainty).

**Primary axis.** All three (depth, complexity, stance) active.
**Secondary axes.** Specificity (general decision → real-options → ethical-trade-off).

**Resident modes.**
- `constraint-mapping` — existing. depth-light, environment-known.
- `decision-under-uncertainty` — existing. depth-thorough, probability-and-time-weighted.
- `multi-criteria-decision` — existing (built Wave 2, 2026-05-01). complexity-multi-criteria.
- `decision-architecture` — existing (built Wave 4, 2026-05-01). depth-molecular.
- `real-options-decision` — gap-deferred. specificity-staged-investment.
- `ethical-tradeoff` — gap-deferred. stance-normative + specificity-values-laden.

**Adjacencies.** T2 (decision-clarity as T2 cousin), T6 (when decision is inseparable from future projection), T7 (when decision is about risk avoidance), T8 (when decision is among parties).

**Coverage status.** Near-Strong after Wave 4 (deferred items remain deferred per CR-6).

### T6. Future Exploration

**Characterization.** Operations that look forward — projecting, scenario-building, forecasting probabilities, exploring possibility-spaces, anticipating sequels.

**Boundary conditions.** Input is the present plus a forward-looking question. Excludes risk-and-failure-specific analysis (T7), which has its own territory.

**Primary axis.** Depth (light projection → probabilistic forecasting → scenario planning → wicked-future molecular).
**Secondary axes.** Stance (neutral forecasting vs. adversarial pre-mortem-action vs. constructive backcasting).

**Resident modes.**
- `consequences-and-sequel` — existing. depth-light, forward.
- `probabilistic-forecasting` — existing (built Wave 2, 2026-05-01). depth-thorough, probability-output.
- `scenario-planning` — existing. depth-thorough, narrative-output.
- `pre-mortem-action` — existing (built Wave 1, 2026-05-01). stance-adversarial-future. **Parsed from Pre-Mortem dual-citizenship per Decision D.** Shares `klein-pre-mortem` lens with `pre-mortem-fragility`.
- `wicked-future` — existing (built Wave 4, 2026-05-01). depth-molecular.
- `backcasting` — gap-deferred. stance-constructive-future.

**Adjacencies.** T3 (decision as forward-looking), T7 (Pre-Mortem cross-territory case — handled by parse).

**Coverage status.** Near-Strong after Wave 4 (Backcasting deferred per CR-6; Wicked-Future composes around its absence).

### T7. Risk and Failure Analysis

**Characterization.** Operations that examine a plan, system, or design specifically for failure modes, vulnerabilities, fragilities, and tail risks.

**Boundary conditions.** Input is a plan, system, or design. Question is *how could this fail*. Excludes general-future-exploration (T6 — broader question than failure) and excludes Red Team's adversarial-actor framing (T15 — about an adversary, not about structural fragility).

**Primary axis.** Depth (FMEA-light → fault tree → fragility/antifragility molecular).
**Secondary axes.** Specificity (technical-system risk vs. plan-risk vs. organizational-risk); stance (Talebian asymmetry vs. structural).

**Resident modes.**
- `pre-mortem-fragility` — existing (built Wave 1, 2026-05-01). stance-adversarial-future. **Parsed from Pre-Mortem dual-citizenship per Decision D.** Shares `klein-pre-mortem` lens with `pre-mortem-action`.
- `fragility-antifragility-audit` — existing (built Wave 3, 2026-05-01). stance-Talebian + asymmetry-focused.
- `failure-mode-scan` — gap-deferred. depth-light.
- `fault-tree` — gap-deferred. depth-thorough + structural.

**Adjacencies.** T6 (Pre-Mortem parse), T15 (Red Team is adversarial-actor, not failure-mode), T18 (failure of strategic interaction).

**Coverage status.** Moderate after Wave 3 (FMEA-style and fault-tree deferred per CR-6).

---

## Super-cluster D: Position, Stakeholder, and Strategy

### T8. Stakeholder Conflict

**Characterization.** Operations that take a situation involving multiple parties with divergent interests/values and characterize the conflict structure, surface positions and interests, and identify integrative possibilities.

**Boundary conditions.** Input is a situation with multiple identifiable parties. Excludes pure interest-power analysis without conflict structure (T2) and excludes negotiation-active operations (T13).

**Primary axis.** Complexity (multi-party-descriptive → systemic).
**Secondary axes.** Depth (light → integrative).

**Resident modes.**
- `stakeholder-mapping` — existing (built Wave 1, 2026-05-01). complexity-multi-party-descriptive. Foundational for T13.
- `conflict-structure` — gap-deferred. complexity-systemic.

**Adjacencies.** T2 (interest analysis vs. conflict structure), T13 (descriptive vs. active conflict resolution), T3 (decision-among-parties).

**Coverage status.** Moderate after Wave 1 (Conflict Structure deferred per CR-6).

### T13. Negotiation and Conflict Resolution

**Characterization.** Operations that take a negotiation or active conflict and produce guidance — interest-mapping, BATNA assessment, integrative-option generation, third-side analysis.

**Boundary conditions.** Input is an active negotiation or conflict where guidance for the user (or for a mediator) is sought. Excludes descriptive stakeholder mapping (T8) and pure interest-power analysis (T2).

**Primary axis.** Depth (light Interest Mapping → full Principled Negotiation).
**Secondary axes.** Complexity (Third-Side adds multi-party mediator stance).

**Resident modes.**
- `interest-mapping` — existing (built Wave 2, 2026-05-01). depth-light, Fisher/Ury.
- `principled-negotiation` — existing (built Wave 3, 2026-05-01). depth-thorough, Fisher/Ury full.
- `third-side` — existing (built Wave 3, 2026-05-01). stance-mediator + complexity-multi-party (Ury).

**Adjacencies.** T2, T8, T18 (negotiation as strategic interaction).

**Coverage status.** Strong after Wave 3.

### T18. Strategic Interaction

**Characterization.** Operations that model a situation as a game between rational (or boundedly rational) agents and analyze likely play, equilibria, signaling, and incentive design.

**Boundary conditions.** Input is a situation modelable as a game with two-or-more agents. Excludes situations where the parties' conflict is to be resolved rather than analyzed strategically (T13).

**Primary axis.** Complexity (2-to-n-player → mechanism design).
**Secondary axes.** Specificity (signaling games as their own variant).

**Resident modes.**
- `strategic-interaction` — existing. complexity-2-to-n-player.
- `mechanism-design` — gap-deferred. complexity-mechanism-design.
- `signaling` — gap-deferred. specificity-signaling-games.

**Adjacencies.** T7 (failure-of-strategy), T13 (negotiation as strategic), T2 (power as strategic resource).

**Coverage status.** Moderate (founder strong; gaps deferred per CR-6).

### T15. Artifact Evaluation by Stance

**Characterization.** Operations that take a plan, proposal, idea, or course of action and evaluate it by adopting a defined stance — constructive (Steelman, Benefits), adversarial (Red Team), or neutral (Balanced Critique).

**Boundary conditions.** Input is a plan, proposal, idea, or argument-as-proposal. The user wants the artifact evaluated *as a proposal*. Excludes evaluating an argument *as an argument for soundness* (T1 — Coherence Audit, Frame Audit, Argument Audit).

**Primary axis.** Stance (constructive-strong → constructive-balanced → neutral → adversarial-light → adversarial-actor-modeling).
**Secondary axes.** Depth (atomic across the stance gradient).

**Resident modes.**
- `steelman-construction` — existing. stance-constructive-strong. **Re-homed to T15 per Decision G/research-report §10.1; carries cross-reference into T1 when artifact is an argument.**
- `benefits-analysis` — existing. stance-constructive-balanced.
- `balanced-critique` — existing (built Wave 1, 2026-05-01). stance-neutral.
- `red-team-assessment` — existing (parsed from `red-team` per Decision D, 2026-05-01). stance-adversarial-actor-modeling-assessment. Default red-team mode when ambiguous.
- `red-team-advocate` — existing (parsed from `red-team` per Decision D, 2026-05-01). stance-adversarial-actor-modeling-advocate. Requires explicit advocate-stance signal.
- `devils-advocate-lite` — gap-deferred. stance-adversarial-light.

**Adjacencies.** T1 (Steelman cross-reference; Argument Audit operates on argument-as-argument), T7 (Red Team — both assessment and advocate — cf. Fragility — adversarial-actor vs. structural-fragility).

**Coverage status.** Strong after Wave 1 (deferred Devil's Advocate Lite per CR-6).

---

## Super-cluster E: Synthesis, Orientation, Structure, Generation

### T11. Structural Relationship Mapping

**Characterization.** Operations that extract relations among entities in a representation (diagram, network, schema) — the topology of inter-element connections.

**Boundary conditions.** Input is a representation of entities and their relations (diagram, network graph, organizational chart, schema). Excludes spatial-composition reading (T19 — what the spatial structure does as primary content).

**Primary axis.** Specificity (general relationship mapping vs. visual-input variant).
**Secondary axes.** None at current population.

**Resident modes.**
- `relationship-mapping` — existing. general specificity.
- `spatial-reasoning` — existing, **re-homed to T11 per Decision G**. specificity-visual-input. Operation is *missing-element/gap detection on diagrams*; this is a T11 operation (notice missing relations) on visual-medium input.

**Adjacencies.** T19 (spatial-composition vs. relationship-extraction — same input image, different question), T16 (mechanism-of-relations), T17 (process-of-relations-over-time).

**Coverage status.** Strong (re-home aligns mode with proper territory).

### T12. Cross-Domain and Knowledge Synthesis

**Characterization.** Operations that synthesize across domains, integrate disparate knowledge bodies, or hold thesis/antithesis in productive tension.

**Boundary conditions.** Input is two-or-more domains, knowledge bodies, or positions to be integrated. Excludes within-domain analysis.

**Primary axis.** Stance (integrative vs. thesis-antithesis vs. cross-domain analogical).
**Secondary axes.** Specificity.

**Resident modes.**
- `synthesis` — existing. stance-integrative.
- `dialectical-analysis` — existing. stance-thesis-antithesis.
- `cross-domain-analogical` — gap-deferred. specificity-cross-domain.

**Adjacencies.** T9 (paradigm-comparison vs. knowledge-synthesis), T20 (generative synthesis vs. analytical synthesis).

**Coverage status.** Strong after existing (Cross-Domain Analogical deferred per CR-6).

### T14. Orientation in Unfamiliar Territory

**Characterization.** Operations that take an unfamiliar domain, problem space, or codebase and produce structured orientation for the user — the lay of the land.

**Boundary conditions.** Input is a domain or space the user is new to. Excludes deep-domain expertise application.

**Primary axis.** Depth (light Quick Orientation → thorough Terrain Mapping → molecular Domain Induction).
**Secondary axes.** None at current population.

**Resident modes.**
- `quick-orientation` — existing (built Wave 1, 2026-05-01). depth-light.
- `terrain-mapping` — existing. depth-thorough.
- `domain-induction` — existing (built Wave 4, 2026-05-01). depth-molecular.

**Adjacencies.** T20 (orientation in known space vs. generative exploration), T11 (orientation produces relationship map as side-effect).

**Coverage status.** Strong after Wave 4.

### T19. Spatial Composition

*Renamed from "Visual and Spatial Structure" per Decision G. Confirmed as a real territory by the T19 reanalysis (`Reference — T19 Reanalysis — Spatial Dynamics as Distinct Analytical Territory.md` and `Reference — Spatial Composition Modes and T19 Reanalysis.md`). Existing `spatial-reasoning` mode re-homed to T11.*

**Characterization.** Operations that take a spatial composition (painting, garden, room, page, film frame, dashboard, urban scene, network diagram qua image) and analyze what the spatial structure itself does as primary content — voids, groupings, forces, affordances.

**Boundary conditions.** Input is a bounded spatial composition (real or depicted). Excludes inter-element relationship extraction (T11 — that is what the diagram *says*; T19 is what the *layout* does), causal investigation (T4), and process analysis (T17). When input is a diagram, T11 and T19 may both fire on the same input answering different questions.

**Primary axis.** Specificity (aesthetic-experiential vs. universal-perceptual vs. operational-applied).
**Secondary axes.** Depth (surface-pattern → deep-affordance); stance (descriptive vs. critical vs. contemplative).

**Resident modes.**
- `ma-reading` — existing (built Wave 2, 2026-05-01). contemplative-descriptive-deep. Suffix: `reading` per Decision L. Japanese aesthetics: Ma + Yūgen + Wabi-sabi + Mu.
- `compositional-dynamics` — existing (built Wave 2, 2026-05-01). universal-principle, descriptive, medium-depth. Gestalt + Arnheim + Itten + Albers.
- `place-reading-genius-loci` — existing (built Wave 3, 2026-05-01) (Decision G). descriptive-evaluative-deep. Suffix: `analysis` per Decision L (mode is analytical even though source traditions include phenomenological elements). Alexander + Norberg-Schulz + Lynch + Bachelard + Appleton + Kaplan.
- `information-density` — existing (built Wave 3, 2026-05-01) (Decision G). applied-evaluative-medium-depth. Tufte + Bertin + Cleveland-McGill + Bringhurst + Lupton.

**Reserved (not built; promotion threshold).** A fifth candidate — **Information-Graphic Visual-Hierarchy Analysis** — is held in reserve. Promotion threshold: info-graphic critique workload exceeds ~15% of T19 invocations, *or* M2+M3 outputs on dashboards visibly fail to distinguish chart-encoding-misfit from generic compositional critique. Below threshold, route info-graphic inputs through Compositional Dynamics with Tufte/Bertin/Cleveland citations.

**Adjacencies.** T11 (relations-asserted vs. layout-doing), T16 (mechanism vs. spatial-structure), T17 (process vs. spatial-structure), T20 (open exploration on aesthetic input).

**Coverage status.** Strong after Wave 3.

**Open debates carried at territory level (per Decision G).** Five debates surfaced by the T19 reanalysis are documented in this territory entry rather than in mode specs:

1. **Spatial vs. compositional framing.** Is "spatial dynamics" the right name, or "compositional dynamics" (which generalizes to time-based compositions)? Holding "Spatial Composition" preserves the spatial focus while allowing the underlying operation (interval/structure-as-primary-content) to be acknowledged as transferable.
2. **Aesthetic-only or also abstract spatial inputs?** Some traditions (Bachelard, wabi-sabi) are aesthetic-experiential; others (Tufte, Bertin, Lynch) are applied-analytical on non-aesthetic spatial inputs. The mode population (M1–M4) cuts across both; the unified territory rests on the claim that the operation is the same across both.
3. **Western-analytical and Eastern-aesthetic: same operation or convergent traditions?** Strong reading: gestalt's figure-ground inversion *is* what ma-reading does, with different vocabulary. Weaker reading: epistemic warrants differ — Western tradition is empirically falsifiable, Eastern tradition is constitutively experiential. Bears on Ma Reading's stance (analytical-predictive vs. contemplative-articulative).
4. **Verbal accessibility for AI implementation.** Pessimistic view: Compositional Dynamics requires actual visual processing because perceptual grouping is not propositional. Optimistic view: the AI's job is to predict consequences of structure, not have the experience. Middle view: implementable for direct image input or high-fidelity verbal description; degrades for rough sketch.
5. **Mode granularity: general vs. tradition-specific.** Whether more tradition-specific modes (yūgen, wabi-sabi, cinematic-montage) should be promoted to first-class modes or remain stance-flags / vocabulary inside the four modes. Currently the latter; revisit if outputs collapse.

### T20. Open Exploration (Generative)

**Characterization.** Operations that take an open prompt, partial idea, or area-of-interest and produce generative output — exploration, ideation, question-formulation. Output is generative, not analytical (no "— Analysis" suffix per Decision L).

**Boundary conditions.** Input is an open prompt or area-of-interest where the user wants to explore rather than evaluate. Excludes analytical territories where defeasible output contracts apply.

**Primary axis.** Specificity (personal-interest vs. creative-generation vs. research-question-formulation).
**Secondary axes.** None at current population.

**Resident modes.**
- `passion-exploration` — existing. specificity-personal-interest. Suffix: none (bare name) per Decision L.
- `idea-development` — gap-deferred. specificity-creative-generation.
- `research-question-generation` — gap-deferred. specificity-question-formulation.

**Adjacencies.** T19 (open prompt on aesthetic input), T14 (orientation as exploration), T12 (synthesis as generation).

**Coverage status.** Partial (founder mode exists; expansion deferred per CR-6).

**Crystallization Detection note (per Decision M).** Crystallization Detection — the recognition that a passion or open exploration has crystallized into a specifiable project — lives within this territory's documentation and within Passion Exploration's mode spec, *not* as a meta-architectural answer-seeking-vs.-question-seeking distinction. The territory model + suffix convention encode the analytical/generative distinction implicitly.

### T21. Execution / Project Mode (Non-Analytical)

**Characterization.** Operations that execute or format rather than analyze. Project Mode walks the user through executing a defined project; Structured Output formats material under a structural template. Suffix: none (bare name) per Decision L.

**Boundary conditions.** Input is a project to execute or material to format. Excludes analytical operations.

**Primary axis.** Specificity (per execution type).
**Secondary axes.** None.

**Resident modes.**
- `project-mode` — existing. Suffix: none.
- `structured-output` — existing. Suffix: none.

**Adjacencies.** None within the analytical routing tree (T21 sits outside it).

**Coverage status.** Strong.

---

## 21-Territory Summary Table (post-Wave-4)

| # | Territory | Super-cluster | Primary Axis | Resident Modes (count) | Coverage |
|---|---|---|---|---|---|
| T1 | Argumentative Artifact Examination | A | Depth | 4 (Position Genealogy deferred) | Near-Strong |
| T2 | Interest and Power Analysis | A | Complexity | 4 | Strong |
| T3 | Decision-Making Under Uncertainty | C | All three | 4 (Real-Options + Ethical-Tradeoff deferred) | Near-Strong |
| T4 | Causal Investigation | B | Complexity | 4 | Strong |
| T5 | Hypothesis Evaluation | B | Depth | 3 | Strong |
| T6 | Future Exploration | C | Depth, stance | 5 (Backcasting deferred) | Near-Strong |
| T7 | Risk and Failure Analysis | C | Depth | 2 (FMEA + Fault Tree deferred) | Moderate |
| T8 | Stakeholder Conflict | D | Complexity | 1 (Conflict Structure deferred) | Moderate |
| T9 | Paradigm and Assumption Examination | A | Stance | 3 | Strong |
| T10 | Conceptual Clarification | A | Stance | 2 (Definitional Dispute deferred) | Moderate |
| T11 | Structural Relationship Mapping | E | Specificity | 2 | Strong |
| T12 | Cross-Domain and Knowledge Synthesis | E | Stance | 2 (Cross-Domain Analogical deferred) | Strong |
| T13 | Negotiation and Conflict Resolution | D | Depth | 3 | Strong |
| T14 | Orientation in Unfamiliar Territory | E | Depth | 3 | Strong |
| T15 | Artifact Evaluation by Stance | D | Stance | 4 (Devil's Advocate Lite deferred) | Strong |
| T16 | Mechanism Understanding | B | Depth | 1 | Moderate |
| T17 | Process and System Analysis | B | Specificity | 2 (Organizational Structure deferred) | Moderate |
| T18 | Strategic Interaction | D | Complexity | 1 (Mechanism Design + Signaling deferred) | Moderate |
| T19 | Spatial Composition | E | Specificity | 4 (Mode 5 reserved against threshold) | Strong |
| T20 | Open Exploration (Generative) | E | Specificity | 1 (Idea Development + Research Question Generation deferred) | Partial |
| T21 | Execution / Project Mode (Non-Analytical) | — | Specificity | 2 | Strong |

**Total resident modes (post-Wave-4):** 57 modes across 21 territories. Of these:
- 22 keep-modes from the existing 25 (after retiring 3 catch-alls and parsing Systems Dynamics into 2)
- 1 Wicked Problems mode created from existing framework (Decision H)
- 33 new modes built across Waves 1–4
- 1 Wicked Problems framework restructured to Decision Clarity Analysis framework (Decision H)
- Plus 14 deferred candidates per CR-6

---

## Boundary Verification Sub-Deliverable

For each pair of adjacent territories, the disambiguating question that distinguishes them. Detailed disambiguation patterns live in `Reference — Cross-Territory Adjacency.md`; the pointers below name the question and the answer-pattern that selects each territory.

Per Decision D parsing principle: where two territories appear to fit a candidate mode, the mode is parsed (Pre-Mortem → action + fragility; Systems Dynamics → causal + structural). No dual-citizenship.

### T1 ↔ T2 (Argumentative Artifact ↔ Interest and Power)
**Disambiguating question.** "Are you mostly asking whether the argument itself holds up, or who benefits if people accept it?"
- Argument-soundness focus → T1.
- Interest-pattern focus → T2.
- Both → sequential dispatch, T1 first, T2 follow-up.

### T1 ↔ T15 (Argumentative Artifact ↔ Artifact Evaluation by Stance — Steelman case)
**Disambiguating question.** "Want me to evaluate the argument's *soundness* (does it hold up?), or *evaluate the proposal* with a particular stance (steelman it / push back hard / weigh both)?"
- Soundness evaluation → T1 (Coherence Audit / Frame Audit / Argument Audit).
- Stance-bearing evaluation → T15 (Steelman / Benefits / Balanced Critique / Red Team).
- Steelman cross-territory: home is T15, with T1 cross-reference activated when the artifact under steelmanning is itself an argument.

### T1 ↔ T9 (Argumentative Artifact ↔ Paradigm)
**Disambiguating question.** "Are you evaluating this single argument's frame, or comparing different paradigms that frame the issue differently?"
- Single-artifact frame surfacing → T1 (Frame Audit).
- Multi-paradigm comparison → T9 (Frame Comparison or Worldview Cartography).

### T1 ↔ T10 (Argumentative Artifact ↔ Conceptual Clarification)
**Disambiguating question.** "Is the issue with how the argument deploys a specific concept (clarify the concept first), or with how the argument coheres given any reasonable reading of the concept?"
- Concept-precision issue → T10.
- Argument-coherence issue → T1.

### T2 ↔ T8 (Interest and Power ↔ Stakeholder Conflict)
**Disambiguating question.** "Mostly asking who benefits or has power, or asking how the parties' competing claims can be worked through?"
- Power/interest analysis → T2.
- Conflict structure → T8.

### T2 ↔ T13 (Interest and Power ↔ Negotiation)
**Disambiguating question.** "Are you mapping the interest landscape, or are you about to negotiate (or advise a negotiation)?"
- Mapping → T2.
- Active negotiation guidance → T13.

### T3 ↔ T8 (Decision ↔ Stakeholder Conflict)
**Disambiguating question.** "Is this fundamentally your decision to make (with the parties as inputs), or is it a situation where the parties' conflict itself is what needs to be worked through first?"
- Your-decision → T3.
- Parties'-conflict-first → T8.

### T3 ↔ T6 (Decision ↔ Future Exploration)
**Disambiguating question.** "Are you choosing among options now, or exploring how the future might unfold (irrespective of what you do)?"
- Choice-now → T3.
- Future-shape → T6.

### T3 ↔ T7 (Decision ↔ Risk)
**Disambiguating question.** "Choosing among options where risk is one input among several, or specifically stress-testing how things could fail?"
- Multi-input choice → T3.
- Failure-focused → T7.

### T4 ↔ T9 (Causal ↔ Paradigm)
**Disambiguating question.** "Looking for the causes within how the problem is currently framed, or stepping back to ask whether the framing itself is generating the problem?"
- Within-frame → T4.
- Frame-as-cause → T9.

### T4 ↔ T16 (Causal ↔ Mechanism)
**Disambiguating question.** "Tracing back to causes, or explaining how the parts produce the behavior?"
- Backward-to-causes → T4.
- How-it-works → T16.

### T4 ↔ T17 (Causal ↔ Process)
**Disambiguating question.** "Why does this keep happening (causes), or how does this currently work (process map)?"
- Causal investigation → T4.
- Process mapping → T17.

### T5 ↔ T9 (Hypothesis ↔ Paradigm)
**Disambiguating question.** "Are you weighing competing explanations within a shared understanding of the problem, or are the explanations using such different frames that the disagreement is really about how to see the issue?"
- Within-frame hypothesis comparison → T5.
- Inter-frame disagreement → T9.

### T5 ↔ T1 (Hypothesis ↔ Argumentative Artifact)
**Disambiguating question.** "Are the competing hypotheses each a complete argument-as-artifact (audit each), or are they propositions to weigh against evidence (ACH-style)?"
- Argument-as-artifact → T1.
- Proposition-against-evidence → T5.

### T6 ↔ T7 (Future ↔ Risk — Pre-Mortem parse)
**Disposition per Decision D.** Pre-Mortem is parsed into `pre-mortem-action` (T6) and `pre-mortem-fragility` (T7). They share the `klein-pre-mortem` lens but differ in operation:
- `pre-mortem-action` (T6): adversarial-future stance applied to *the action plan* — what could go wrong with this plan.
- `pre-mortem-fragility` (T7): adversarial-future stance applied to *the system or design* — what failure modes does this structure exhibit.
**Disambiguating question.** "Is this about an action plan that could fail, or about a system/design with structural fragilities?"

### T7 ↔ T15 (Risk ↔ Red Team)
**Disambiguating question.** "Adversarial-actor stress test (someone is trying to defeat this), or structural-fragility audit (where could this break under any pressure)?"
- Actor-modeling → T15 Red Team.
- Structural fragility → T7 Fragility Audit.

### T8 ↔ T13 (Stakeholder ↔ Negotiation)
**Disambiguating question.** "Mapping the conflict structure, or guiding active negotiation?"
- Mapping → T8.
- Active → T13.

### T11 ↔ T19 (Structural Relationship ↔ Spatial Composition)
**Disambiguating question.** "Is the question about what relations the diagram asserts among elements, or about what the layout/composition itself is doing?"
- Relation-extraction (the diagram-as-notation) → T11.
- Layout-doing (the diagram-as-composition) → T19.
- Same input may legitimately invoke both for different questions; sequential dispatch.

### T11 ↔ T16 ↔ T17 (Structural ↔ Mechanism ↔ Process)
**Disambiguating question.** "Is the question about how this works (the gears — T16), about the flow/process (sequence — T17), or about how the parts relate (structure — T11)?"
- How → T16.
- Flow → T17.
- Structure → T11.

### T9 ↔ T12 (Paradigm ↔ Synthesis)
**Disambiguating question.** "Stepping back to examine the paradigms, or integrating across paradigms?"
- Examining → T9.
- Integrating → T12.

### T14 ↔ T20 (Orientation ↔ Open Exploration)
**Disambiguating question.** "Trying to orient in an unfamiliar space (analytical — what's here), or generating in an open space (generative — what could be)?"
- Orienting → T14.
- Generating → T20.

### T15 ↔ T7 (Artifact Evaluation ↔ Risk — already noted under T7)

### T19 ↔ T20 (Spatial Composition ↔ Open Exploration on aesthetic input)
**Disambiguating question.** "Are you asking for analytical reading of the composition (defeasible operations), or for open-ended exploration of what it opens up?"
- Analytical reading → T19.
- Open exploration → T20.
- Both may fire when input is aesthetic and prompt is broad.

---

## Parsing Principle Application Summary

Per Decision D / Decision H, two existing modes were parsed during this architecture lock:

1. **Pre-Mortem** → `pre-mortem-action` (T6, stance-adversarial-future-on-plan) + `pre-mortem-fragility` (T7, stance-adversarial-future-on-system). Shared lens: `klein-pre-mortem`.
2. **Systems Dynamics** → `systems-dynamics-causal` (T4, complexity-feedback-causal) + `systems-dynamics-structural` (T17, complexity-feedback-structural). Shared lenses: existing feedback-loop lenses.

A third parse executed at the framework level per Decision H:

3. **Wicked Problems framework** → `wicked-problems` mode (T2, depth-molecular per research report §6.2 composition) created in Phase 2 + `decision-clarity` mode (T2, depth-molecular for decision-clarity-document production) built in Wave 4. The existing `Framework — Wicked Problems.md` was renamed to `Framework — Decision Clarity Analysis.md` (effective 2026-05-01) and restructured to align with `decision-clarity`'s molecular_spec.

A re-homing without parsing executed per Decision G:

4. **Spatial Reasoning** → re-homed from old T19 to T11 with `gradation_position: specificity-visual-input`. The mode's actual operation (structural gap detection on diagrammatic input) is a T11 operation on visual-medium input.

A re-homing without parsing executed per Decision G / research report §10.1:

5. **Steelman Construction** → re-homed primarily to T15 with cross-reference into T1. The mode's primary work is stance-bearing artifact evaluation; the T1 cross-reference activates when the artifact under steelmanning is itself an argument.

---

## Notes for Future Maintenance

- Adding a new mode requires assigning it to exactly one home territory. If the candidate mode appears to fit two, apply the parsing principle (Decision D) — split into two modes that share a lens.
- Adding a new territory requires demonstrating shared problem-shape, input-types, and output contracts (the four-criterion territory test from research report §2.1). Architectural decisions to add a territory require user review.
- The Coverage status column reflects post-Wave-4 build state. Deferred candidates per CR-6 are not coverage gaps to be filled by future work without a deliberate decision; they are out-of-scope until the user re-prioritizes them.
- The 5 T19 open debates listed above are kept in this file rather than in mode specs because they bear on territory architecture, not on individual mode operation. Mode specs may reference them.

*End of Reference — Analytical Territories.*
