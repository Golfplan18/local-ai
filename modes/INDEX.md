---
nexus:
  - ora
type: reference
tags:
  - reference
  - index
  - modes
date created: 2026-05-04
date modified: 2026-06-18

---

# Modes — Index

*Per-mode index for the mode files in `Modes/`. The runtime folder currently has 64 content mode files: 60 resident public/campaign analysis modes plus 4 utility/bypass modes listed separately below. One-line description per mode, organized by home territory for the resident analysis modes.*

*Authoritative source for mode-id, suffix, gradation position, and depth tier:* `Registry — Mode Registry.md`.
*Authoritative source for territory boundaries and resident-mode mapping:* `Reference — Analytical Territories.md`.
*Mode specification template (the structure each mode file follows):* `Reference — Mode Specification Template.md`.
*Runtime configuration surfaces and mode-file runtime fields:* `Reference — Ora Runtime Configuration.md` and `Reference — Mode Specification Template.md`.
*Lens dependencies cross-reference:* `Reference — Lens Library Specification.md` and `Lenses/INDEX.md`.

---

## T1 — Argumentative Artifact Examination

- **`coherence-audit.md`** — Surfaces internal contradictions, unstated premises, and reasoning-step gaps in a single argumentative artifact.
- **`frame-audit.md`** — Surfaces the frame an argument relies on without yet comparing it to other frames.
- **`propaganda-audit.md`** — Detects propagandistic structure (in the Jason Stanley sense) within a stated position.
- **`argument-audit.md`** — Composes Coherence + Frame + (optionally) Propaganda passes into a full audit deliverable.

## T2 — Interest and Power Analysis

- **`cui-bono.md`** — Traces who benefits from a position, claim, or status quo.
- **`boundary-critique.md`** — Applies Critical Systems Heuristics' twelve boundary questions to surface whose interests are excluded from the framing.
- **`wicked-problems.md`** — Produces wicked-problems analysis composed around the Decision Clarity framework (created Phase 2 from `Framework — Decision Clarity Analysis.md`).
- **`decision-clarity.md`** — Produces a Decision Clarity Document for a third-party decision-maker, paired with the restructured `Framework — Decision Clarity Analysis.md` (renamed from the retired Wicked Problems Framework, 2026-05-01).

## T3 — Decision-Making Under Uncertainty

- **`constraint-mapping.md`** — Maps success conditions, failure conditions, gains, and forfeitures across alternatives in a known environment.
- **`decision-under-uncertainty.md`** — Frames choice under uncertainty with probability, value-of-information, and conditional recommendation.
- **`multi-criteria-decision.md`** — Applies MCDA-style weighted-criteria scoring to choices with multiple incommensurable axes.
- **`decision-architecture.md`** — Composes constraint, uncertainty, and multi-criteria passes into a single decision-architecture deliverable.

## T4 — Causal Investigation

- **`root-cause-analysis.md`** — Traces a symptom backward through at least three causal levels to a root cause and recommends corrective action.
- **`systems-dynamics-causal.md`** — Applies feedback-loop analysis to identify reinforcing/balancing structures generating an outcome (parsed from Systems Dynamics per Decision D).
- **`causal-dag.md`** — Builds an explicit causal directed-acyclic graph and applies do-calculus / backdoor reasoning.
- **`process-tracing.md`** — Applies hoop / smoking-gun / doubly-decisive evidence tests to trace a causal mechanism through a single historical event.

## T5 — Hypothesis Evaluation

- **`differential-diagnosis.md`** — Generates and ranks competing explanations for an ambiguous presentation; suitable when a quick discriminating-evidence pass is enough.
- **`competing-hypotheses.md`** — Applies Heuer's ACH matrix (consistent / inconsistent / N/A) with diagnosticity weighting to elimination-based conclusions.
- **`bayesian-hypothesis-network.md`** — Builds an explicit Bayesian network over hypotheses and evidence, propagating posteriors quantitatively.

## T6 — Future Exploration

- **`consequences-and-sequel.md`** — Traces second- and third-order effects forward from a specific action.
- **`probabilistic-forecasting.md`** — Produces calibrated probability estimates with reference-class reasoning and resolution criteria.
- **`scenario-planning.md`** — Identifies critical uncertainties and produces 2–4 scenario narratives with leading indicators.
- **`pre-mortem-action.md`** — Applies Klein's pre-mortem stance to an action plan: assume failure, generate causes (parsed from Pre-Mortem per Decision D; shares `klein-pre-mortem` lens with `pre-mortem-fragility`).
- **`wicked-future.md`** — Composes future-exploration passes for futures whose constituting questions remain unsettled.

## T7 — Risk and Failure Analysis

- **`pre-mortem-fragility.md`** — Applies Klein's pre-mortem stance to a system or design: assume structural failure, surface fragilities (parsed from Pre-Mortem per Decision D; shares `klein-pre-mortem` lens with `pre-mortem-action`).
- **`fragility-antifragility-audit.md`** — Applies Talebian asymmetry-of-payoff reasoning to identify fragile, robust, and antifragile structural features.

## T8 — Stakeholder Conflict

- **`stakeholder-mapping.md`** — Enumerates parties, interests, positions, and power asymmetries; foundational input for T13 negotiation work.

## T9 — Paradigm and Assumption Examination

- **`paradigm-suspension.md`** — Suspends the assumed frame to test whether unspoken paradigm commitments are doing load-bearing work.
- **`frame-comparison.md`** — Compares two or more frames a problem can be cast in, surfacing what each frame includes and excludes.
- **`worldview-cartography.md`** — Maps the worldviews in tension across a debate, locating each on shared and divergent commitments.

## T10 — Conceptual Clarification

- **`deep-clarification.md`** — Pushes a concept past first-level explanation through ordinary-language analysis to mechanistic clarity at depth.
- **`conceptual-engineering.md`** — Evaluates whether a concept ought to be replaced or revised on ameliorative grounds.

## T11 — Structural Relationship Mapping

- **`relationship-mapping.md`** — Extracts entities and typed connections from prose and renders them as a relationship graph.
- **`spatial-reasoning.md`** — Performs gap detection and missing-relation surfacing on a user-provided diagram (re-homed from old T19 to T11 per Decision G; the operation is T11 work on visual-medium input).

## T12 — Cross-Domain and Knowledge Synthesis

- **`synthesis.md`** — Holds two or more frameworks in productive tension and extracts emergent insight where structural parallels are genuine.
- **`dialectical-analysis.md`** — Argues thesis and antithesis with genuine commitment, then sublates or articulates irreducibility.

## T13 — Negotiation and Conflict Resolution

- **`interest-mapping.md`** — Maps positions to underlying interests across parties (Fisher-Ury short form).
- **`principled-negotiation.md`** — Applies the full Fisher-Ury principled-negotiation framework with BATNA, integrative-option generation, and objective-criteria selection.
- **`third-side.md`** — Applies William Ury's Third Side framework: surface what the surrounding community can do to contain and resolve a conflict.

## T14 — Orientation in Unfamiliar Territory

- **`quick-orientation.md`** — Produces a fast orientation sketch with entry points and predictable wrong impressions; sub-five-minute output.
- **`terrain-mapping.md`** — Maps known / contested / open territory in an unfamiliar domain with cross-links and prerequisite chains.
- **`domain-induction.md`** — Produces a structured induction into a domain over multiple sessions, layering terrain + mechanism + competing-position passes.

## T15 — Artifact Evaluation by Stance

- **`steelman-construction.md`** — Constructs the strongest possible version of a position before any critique. **Re-homed to T15 per Decision G / research report §10.1; carries cross-reference into T1 when the artifact under steelmanning is itself an argument.**
- **`benefits-analysis.md`** — Applies de Bono's PMI (Plus / Minus / Interesting) with stress-tested claims and second-order effects.
- **`balanced-critique.md`** — Produces a neutral evaluation that explicitly weighs both supporting and undermining considerations.
- **`red-team-assessment.md`** — Models an adversarial actor attacking the artifact and ranks vulnerabilities by severity for the user's own fix-prioritisation. Default red-team mode when ambiguous. **Parsed from `red-team` per Decision D, 2026-05-01.**
- **`red-team-advocate.md`** — Builds an argument brief against the artifact for an external audience, ranking attacks by persuasive force with suggested phrasing. Requires explicit advocate-stance signal. **Parsed from `red-team` per Decision D, 2026-05-01.**

## T16 — Mechanism Understanding

- **`mechanism-understanding.md`** — Explains how parts of a phenomenon produce its observed behaviour at the principle level.

## T17 — Process and System Analysis

- **`process-mapping.md`** — Maps a workflow or process as it currently is — components, flows, bottlenecks, dependencies.
- **`systems-dynamics-structural.md`** — Applies feedback-loop analysis to a system's structural composition rather than its causal trajectory (parsed from Systems Dynamics per Decision D).
- **`market-dynamics.md`** — Applies supply-demand, competitive-selection, network-effects, and creative-destruction lenses to explain how a market or economy behaves over time (added 2026-06-01).

## T18 — Strategic Interaction

- **`strategic-interaction.md`** — Models the situation as a game between rational agents and analyses likely play, equilibria, signalling, and credible commitment.
- **`mechanism-design.md`** — Applies adverse-selection, moral-hazard, principal-agent, and auction-design frameworks to information-asymmetry market failures and incentive-structure design problems (promoted from deferred 2026-06-01).

## T19 — Spatial Composition

- **`ma-reading.md`** — Reads negative space, interval, and presence-of-absence in compositions through the Ma + Yūgen + Wabi-sabi + Mu Japanese-aesthetics tradition.
- **`compositional-dynamics.md`** — Applies Gestalt + Arnheim + Itten + Albers principles to the perceptual dynamics of a composition.
- **`place-reading-genius-loci.md`** — Reads the spirit, affordances, and structure of a place using Alexander + Norberg-Schulz + Lynch + Bachelard + Appleton + Kaplan.
- **`information-density.md`** — Applies Tufte + Bertin + Cleveland-McGill + Bringhurst + Lupton to the information density and visual hierarchy of an artifact.

## T20 — Open Exploration (Generative)

- **`passion-exploration.md`** — Wanders an open territory with the user, surfacing questions, connections, and potential project nodes without driving toward resolution. Output is generative (no `Analysis` suffix per Decision L).

## T21 — Execution / Project Mode (Non-Analytical)

- **`project-mode.md`** — Walks the user through executing a defined project; produces deliverable + decisions log + acknowledged limitations.
- **`structured-output.md`** — Renders existing content into a requested document format faithfully; produces deliverable + gap report + format notes.

## Runtime utility / bypass modes

These files are runtime modes, but they are not part of the 60 resident public/campaign analysis-mode roster.

- **`factual-lookup.md`** — Retrieval-only factual lookup when no judgment or analysis is needed.
- **`general-inquiry.md`** — Catch-all analytical inquiry when judgment is required but no specific analytical mode cleanly fits.
- **`subjective-inquiry.md`** — Opinion, preference, taste, and aesthetic questions without objective criteria.
- **`simple.md`** — Direct bypass response for greetings, system-meta requests, and other non-analytical prompts.
## Conventions

- **Filenames:** lowercase-hyphenated (kebab-case). The mode_id matches the filename minus `.md`.
- **YAML on both sides:** vault and ora copies both carry frontmatter.
- **Pairing:** `vault/Modes/<mode>.md` ↔ `~/ora/modes/<mode>.md`. One-to-one filename match. See `Framework — System File Drift Correction.md`.

## See also

- `Registry — Mode Registry.md` — authoritative per-mode catalog with mode_id, suffix, gradation position, depth tier, lens dependencies.
- `Reference — Mode Specification Template.md` — the section template every mode spec follows.
- `Reference — Ora Runtime Configuration.md` — live runtime-configurable surfaces; mode-specific gear, RAG profile, and stage guidance now live in each mode file per `Reference — Mode Specification Template.md`.
- `Reference — Within-Territory Disambiguation Trees.md` — selects among resident modes once a territory has been chosen.
- `Reference — Cross-Territory Adjacency.md` — disambiguating questions for adjacent territory pairs.
- `Reference — Disambiguation Style Guide.md` — naming, suffix, parenthesization conventions.
- `Lenses/INDEX.md` — lens library this mode set draws from.
