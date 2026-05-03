# Framework — Open Exploration

*Self-contained framework for generative work on an open prompt, partial idea, or area-of-interest — exploration, ideation, question-formulation. Output is generative, not analytical (no "— Analysis" suffix per Decision L). Compiled 2026-05-01.*

---

## Territory Header

- **Territory ID:** T20
- **Name:** Open Exploration (Generative)
- **Super-cluster:** E (Synthesis, Orientation, Structure, Generation)
- **Characterization:** Operations that take an open prompt, partial idea, or area-of-interest and produce generative output — exploration, ideation, question-formulation. Output is generative, not analytical.
- **Boundary conditions:** Input is an open prompt or area-of-interest where the user wants to explore rather than evaluate. Excludes analytical territories where defeasible output contracts apply.
- **Primary axis:** Specificity (personal-interest vs. creative-generation vs. research-question-formulation).
- **Secondary axes:** None at current population.
- **Coverage status:** Partial (founder mode exists; expansion deferred per CR-6).

---

## When to use this framework

Use T20 when the user wants to wander rather than execute or analyze — open exploration of an area of personal interest, with no deliverable named, no defeasible question to adjudicate, and no analytical output sought. T20 answers prompts like "I'm interested in...", "help me think about...", "I've been wondering...", "what if...", "let me explore...". The mode produces an exploration map (loose, frontier-respecting), open questions, potential project nodes (when crystallization candidates appear), and next-directions (one deepening, one lateral).

T20 does NOT do orientation in unfamiliar territory analytically (that is T14), synthesis across two developed bodies (T12), or execution of a defined deliverable (T21).

---

## Within-territory disambiguation

```
[Territory identified: open exploration, generative work on an open prompt]

Route: passion-exploration (Tier-2, territory founder)
```

**Singleton territory.** T20 currently has one resident mode (`passion-exploration`). Expansion candidates `idea-development` (specificity-creative-generation) and `research-question-generation` (specificity-question-formulation) are deferred per CR-6.

**Default route.** `passion-exploration` at Tier-2.

**Escalation hooks.**
- After `passion-exploration`: if the exploration crystallizes into a creative work the user wants to actually develop, hook upward to `idea-development` (deferred — surface the flag).
- After `passion-exploration`: if the exploration crystallizes into a research question the user wants to pursue, hook upward to `research-question-generation` (deferred — surface the flag).
- After `passion-exploration`: if the exploration crystallizes into a specifiable project (Crystallization Detection per Decision M), hand off to T21 (`project-mode`).
- After `passion-exploration`: if the exploration is really an orientation question in an unfamiliar space, hook sideways to T14 (`quick-orientation` or `terrain-mapping`).
- After `passion-exploration`: if the exploration is really a synthesis-across-domains operation, hook sideways to T12 (`synthesis` or `dialectical-analysis`).

---

## Mode entries

### `passion-exploration` — Passion Exploration

**Educational name:** passion exploration (specificity-personal-interest).

**Suffix.** None (bare name) per Decision L. T20's output is generative; suffix-rule "none" reflects this.

**Plain-language description.** Generative wandering through an area of personal interest. Produces an exploration map (loose, frontier-respecting — not over-polished into apparent completion); open questions (≥3, kept open rather than closed prematurely); potential project nodes (surfaced when crystallization candidates appear, but not forced); next-directions (≥2, with at least one deepening and one lateral). The mode optimizes for productive wandering, not for closure — open questions outrank tidy conclusions.

**Critical questions.**
- CQ1: Have at least three open questions emerged and remained open, rather than being closed prematurely?
- CQ2: Have at least two next-directions been offered (one deepening, one lateral)?
- CQ3: Has the mode monitored for crystallization signals (shift to directive language) and reflected them back to the user?
- CQ4: Does the exploration map honestly reflect the wandering state, or has it been over-polished into apparent completion?

**Per-pipeline-stage guidance.**
- **Analyst.** Wander productively from user's seed; develop ≥3 open questions; offer ≥2 next-directions (one deepening, one lateral); preserve frontier roughness; monitor crystallization signals and reflect back when present.
- **Evaluator.** Apply four critical questions; flag premature-closure, lecture-trap, missed-crystallization, over-polished-map, productivity-trap. Adversarial strictness is **relaxed** for this mode — Passion Exploration is navigation, not argument; do not over-apply analytical-mode rules.
- **Reviser.** Add open questions where draft converged; add lateral next-directions where draft only deepened; reflect crystallization signals where user's language has shifted; resist over-polishing; resist closure pressure.
- **Verifier.** Confirm four required sections (exploration_map, open_questions, potential_project_nodes, next_directions); ≥3 open questions present; ≥2 next-directions (one deepening, one lateral); crystallization signals reflected or explicitly noted as absent.
- **Consolidator.** Merge as prose with the four required sections; exploration map loose and frontier-respecting; concept maps optional and only when ≥3 concepts have surfaced; conversation history weight higher than for analytical modes (the arc of wandering is part of the signal).

**Source tradition.** de Bono concept fan (climb the abstraction ladder); de Bono random entry (break exploration loops); cross-domain analogical mapping.

**Lens dependencies.**
- Required: none.
- Optional: debono-concept-fan, debono-random-entry, cross-domain-analogical-mapping.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

---

## Decision M — Crystallization Detection note

Per Decision M, **Crystallization Detection** lives within Passion Exploration's mode spec (and within this T20 territory documentation), NOT as a meta-architectural answer-seeking-vs.-question-seeking concept. The territory model (T20 generative vs. T14 analytical orientation vs. T21 execution) and the suffix convention (no "— Analysis" suffix for T20 generative output) encode the analytical/generative distinction implicitly; Passion Exploration's job is to detect when an exploration has crystallized into a specifiable project and to reflect that signal back to the user.

**Crystallization signals to monitor.**
- A defined deliverable appearing in the user's language ("I want to write", "let's build", "we should produce").
- Scope narrowing — the user starts ruling out branches rather than fanning into them.
- Shift from exploratory grammar ("I wonder", "what about", "could it be") to directive grammar ("I want to", "let's", "I'll").
- A repeated return to one branch — the user keeps coming back to a specific concept across turns.
- The user asks for next-actions or for an outline rather than for more connections.

**Detection-and-reflection protocol.** When crystallization signals appear, name the signal in prose using the literal phrase "crystallization signal" and offer transition to Project Mode (T21). The user retains discretion — they may want to keep wandering. If signals are absent, state "no crystallization yet" explicitly so the user knows the mode is monitoring.

**What crystallization is NOT.**
- It is NOT the user expressing enthusiasm — enthusiasm without a deliverable is still exploration.
- It is NOT the mode's judgment that the exploration "should" produce something — Passion Exploration honors aimless wandering as productive.
- It is NOT triggered by length — long explorations stay exploratory if no deliverable language emerges.

The Missed-Crystallization Trap is the failure mode for missing the signal; the Productivity Trap is the failure mode for forcing crystallization that hasn't happened.

---

## Cross-territory adjacencies

### T14 ↔ T20 (Orientation in Unfamiliar Territory ↔ Open Exploration)

**Why adjacent.** Both engage with unfamiliar or open spaces. T14 is analytical — what's here, what's the lay of the land. T20 is generative — what could be, what opens up.

**Disambiguating question.** "Trying to orient in an unfamiliar space (what's here), or generating in an open space (what could be)?"

**Routing.** Orienting → T14. Generating → T20.

**Examples.**
- "I'm new to this codebase — give me the lay of the land." → T14.
- "I'm interested in this area — help me explore where it might go." → T20.
- "What are the major positions in this field?" → T14.
- "What questions could I be asking here?" → T20 (Research Question Generation, deferred).

### T19 ↔ T20 (Spatial Composition ↔ Open Exploration on aesthetic input)

**Disambiguating question.** "Are you asking for analytical reading of the composition (defeasible operations), or for open-ended exploration of what it opens up?"

**Routing.** Analytical reading → T19. Open exploration → T20. Both may fire when input is aesthetic and prompt is broad.

**Sequential dispatch.** When both fire on aesthetic input, T19 typically runs first because the analytical reading grounds the open exploration that T20 then carries.

### T12 ↔ T20 (Cross-Domain Synthesis ↔ Open Exploration)

**Disambiguating question.** Integration across two developed bodies (T12), or generative work on an open prompt (T20)?

**Routing.** Two developed positions to integrate → T12. Open prompt to wander → T20.

### T20 ↔ T21 (Open Exploration ↔ Execution / Project Mode)

**Disambiguating question.** Has the exploration crystallized into a specifiable project, or is it still genuinely open?

**Routing.** Crystallized → T21 (project-mode). Still open → T20 (passion-exploration). The Crystallization Detection protocol governs the handoff.

---

## Lens references (Core Structure embedded)

### de Bono Concept Fan (optional)

**Core Structure.** Edward de Bono's concept fan is a deliberate move *upward* in abstraction to find lateral alternatives. The protocol:
1. State the concrete thing the user is trying to achieve (the leaf node).
2. Move up one level: name the broader purpose this serves (the middle node).
3. Move up again: name the broader purpose THAT serves (the trunk).
4. From the trunk, fan downward into multiple branches: alternative middle nodes that serve the trunk; alternative leaf nodes per middle node.

The technique unlocks lateral options that direct enumeration misses because direct enumeration stays at the leaf level. For Passion Exploration, the concept fan supports breadth: when a user keeps returning to one branch, climbing the abstraction ladder reveals alternative branches that serve the same higher purpose.

### de Bono Random Entry (optional)

**Core Structure.** Edward de Bono's technique for breaking exploration loops: introduce a random word, image, or concept unrelated to the topic, then deliberately seek connections between the random entry and the topic. The connections are typically forced and arbitrary, but the forcing produces lateral connections that systematic search misses.

Operational protocol:
1. When stuck (the exploration has stalled in a recurring pattern), introduce a random entry from a list (random word, random image, random concept).
2. Force connections: name three ways the random entry could relate to the topic.
3. Use the resulting connections as new exploration directions.

The technique is deliberate disruption rather than systematic search; its value is in producing combinations the user would not otherwise have considered.

### Cross-Domain Analogical Mapping (optional)

**Core Structure.** Drawn from Gentner's structure-mapping theory: a cross-domain analogy maps higher-order relations from a source domain to a target domain. For Passion Exploration, cross-domain echoes are a primary breadth move: when the user is exploring topic A, what other domains have analogous structure? The analogy is generative when the source domain has developed insights the target domain has not yet considered. The mode scans:
- **Distant domains** for structural parallels (biology and engineering; music and architecture; chess and economics).
- **Nearby domains** for cross-pollination (organizational design and team sports; personal habits and software development).
- **Personal experience** for resonances the user may not have surfaced (professional frame applied to personal interest, or vice versa).

The structural-mapping discipline (mechanism-level correspondence, not surface analogy) applies even in generative mode: hollow analogies that rest on shared vocabulary are noise; structural analogies that rest on shared mechanism are signal.

---

## Open debates

T20 carries no territory-level open debates at present. Mode-level debates do not currently apply. The Crystallization Detection protocol is treated within the mode's spec rather than as a debate (per Decision M).

---

## Citations and source-tradition attributions

- de Bono, E. (1985). *Six Thinking Hats*. Little, Brown. Companion thinking-tools framework.
- de Bono, E. (1992). *Serious Creativity*. HarperBusiness. Concept fan and random entry.
- Gentner, D. (1983). "Structure-Mapping: A Theoretical Framework for Analogy." *Cognitive Science*. Foundational treatment of structural analogy (used optionally in Passion Exploration's cross-domain scanning).
- Hofstadter, D. R. & Sander, E. (2013). *Surfaces and Essences: Analogy as the Fuel and Fire of Thinking*. Basic Books. Fluid-analogy alternative tradition.
- Kahneman, D. & Tversky, A. (Various). Heuristics-and-biases catalog (foundational substrate).

*End of Framework — Open Exploration.*
