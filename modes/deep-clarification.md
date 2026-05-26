---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-24

---

# MODE: Deep Clarification

```yaml
# 0. IDENTITY
mode_id: deep-clarification
canonical_name: Deep Clarification
suffix_rule: analysis
educational_name: deep conceptual clarification (ordinary-language tradition)

# 1. TERRITORY AND POSITION
territory: T10-conceptual-clarification
gradation_position:
  axis: depth
  value: thorough
adjacent_modes_in_territory:
  - mode_id: conceptual-engineering
    relationship: stance counterpart (ameliorative; Cappelen/Plunkett)
  - mode_id: definitional-dispute
    relationship: specificity counterpart (essentially-contested; Gallie) — gap-deferred

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "why does X work that way"
    - "explain the mechanics of"
    - "what's really going on underneath"
    - "I want depth, not orientation"
  prompt_shape_signals:
    - "deeper"
    - "mechanism"
    - "how does it actually work"
    - "explain the physics / math / internals"
disambiguation_routing:
  routes_to_this_mode_when:
    - "the domain is already familiar; user wants the next mechanism beneath the current explanation"
    - "concept is uncontested but its inner workings are sought"
  routes_away_when:
    - "user wants to engineer the concept normatively (should we redefine X)" → conceptual-engineering
    - "concept is essentially contested with rival defenders" → definitional-dispute
    - "user is unfamiliar and needs the lay of the land first" → terrain-mapping
    - "user wants to question whether the framework holding the concept is itself sound" → paradigm-suspension
when_not_to_invoke:
  - "User is exploring an unfamiliar domain — Terrain Mapping is the right depth"
  - "User has a deliverable in mind and wants execution" → Project Mode
  - "Concept is contested between rival camps; the question is which definition wins" → definitional-dispute or T1 frame audit

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [phenomenon_or_concept, user_current_level_of_understanding]
    optional: [domain_briefing, primary_sources_already_consulted]
    notes: "Applies when user explicitly states their starting depth and asks for the next level beneath."
  accessible_mode:
    required: [phenomenon_or_concept]
    optional: [hint_at_user_intuition_or_misconception]
    notes: "Default. Mode infers user's starting level from the way the question is phrased and pushes ≥2 levels beneath."
  detection:
    expert_signals: ["I already understand X at level Y", "first-principles", "primary literature", "the canonical reference is"]
    accessible_signals: ["explain it deeper", "what's underneath", "how does it really work"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the phenomenon or concept you want to understand deeper, and roughly what level of explanation do you already have?'"
    on_underspecified: "Ask: 'Are you familiar with the surface explanation already, or do you want the lay of the land first?' If the latter, route to Terrain Mapping."
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Is each successive level a genuine mechanism beneath, or is it horizontal detail at the same level?"
    failure_mode_if_unmet: elaboration-trap
  - cq_id: CQ2
    question: "Has the epistemic boundary been marked — where settled knowledge ends and current-best-understanding begins?"
    failure_mode_if_unmet: false-certainty
  - cq_id: CQ3
    question: "Does the deeper understanding change what the user would do or conclude — is there a practical implication?"
    failure_mode_if_unmet: academic-drift

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: lateral-drift-trap
    detection_signal: "Successive levels move to adjacent topics rather than deeper into the same phenomenon."
    correction_protocol: re-dispatch (redirect to same-phenomenon depth)
  - name: elaboration-trap
    detection_signal: "Deeper level adds more facts at the same level of abstraction rather than revealing mechanism."
    correction_protocol: re-dispatch (depth is vertical — name the mechanism beneath)
  - name: jargon-trap
    detection_signal: "Replacing accessible explanation with terminology without naming a mechanism in plain terms."
    correction_protocol: flag
  - name: false-certainty
    detection_signal: "Mechanistic claims presented as settled when current science is indeterminate."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - engineering-and-technical-analysis-module (for technical domains)
  foundational:
    - ordinary-language-philosophy-tradition

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: conceptual-engineering
    when: "Clarification reveals the concept's current definition is normatively inadequate; user wants to ameliorate it."
  sideways:
    target_mode_id: paradigm-suspension
    when: "Clarification surfaces a load-bearing assumption the framework depends on; user wants to question the framework."
  downward:
    target_mode_id: null
    when: "Deep Clarification is the depth-thorough founder; lighter clarification routes to T14 quick-orientation."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Deep Clarification is vertical: each successive level reveals the mechanism beneath the previous one, not more detail at the same level. A thin pass restates the surface explanation in different words; a substantive pass identifies what causes the phenomenon at level N-1 and exposes the next mechanism beneath. Test depth by asking: could the deeper level predict behaviours the surface level cannot? Each level uses the literal labels "Surface:" / "Level 1 beneath:" / "Level 2 beneath:".

## BREADTH ANALYSIS GUIDANCE

Breadth in Deep Clarification is the surrounding terrain that anchors the mechanism: analogies in other domains, alternative mechanistic explanations, connections to adjacent areas of the user's knowledge, and the point at which further depth becomes academic rather than actionable. Widen the lens to identify ≥1 analogy, ≥1 alternative mechanism, and ≥1 practical implication. Breadth markers: the analysis identifies where deeper understanding changes practical implications and where it does not.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Deep Clarification descends through ordinary-language explanations into the mechanisms beneath — what makes the surface phenomenon work at level N-1, what makes that level work at N-2, marking explicitly where settled knowledge ends. It is distinct from terrain-mapping (which lays out the lay of the land for users unfamiliar with the domain), from conceptual-engineering (which normatively redefines concepts rather than describing how they work), from definitional-dispute (which adjudicates between rival defenders of essentially-contested concepts), and from paradigm-suspension (which questions the framework holding the concept). The depth axis is vertical: each level reveals mechanism beneath mechanism, not adjacent facts at the same level.

**Procedure.**

1. State the surface explanation the user already (likely) has — the accessible-level explanation, labelled `**Surface:**` verbatim. Never skip this anchor.
2. Identify the mechanism beneath at Level 1 — what causes the surface-level phenomenon to behave as it does, named in plain terms.
3. Descend to Level 2 beneath — what makes the Level 1 mechanism work as it does, still on the same phenomenon (not lateral drift to neighbouring topics).
4. Test verticality per level — could the deeper level predict behaviour the surface couldn't? Could the surface be derived from the deeper one? If the deeper level is just more surface detail, it gets reshaped to name an actual mechanism.
5. Gloss terminology rather than substituting for it — when a technical term must appear, it sits alongside the plain-terms statement, not as replacement.
6. Mark the epistemic boundary explicitly — where settled knowledge ends and current-best-understanding (or active debate) begins. When the mechanism is fully settled, say so explicitly.
7. Surface alternative mechanisms when the phenomenon admits more than one explanation — preserve both with their respective epistemic standing rather than silently picking.
8. Name at least one practical implication — what the deeper understanding changes (a predicted behaviour, a reframed decision, an enabled intervention). When the deeper level genuinely has no practical consequence, say so explicitly rather than fabricating one.
9. Calibrate confidence per level — surface-level typically high; Level 2 often touches the active-research frontier.

**Goal.** Produce a deep clarification — prose that walks from surface accessible reading down through at least two genuine mechanistic layers, marks where settled knowledge ends, and lands at least one practical implication.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — vertical not horizontal (load-bearing).** Is each successive level a genuine mechanism beneath, or is it horizontal detail at the same level? Failure mode if unmet: `elaboration-trap`.
- **CQ2 — epistemic boundary marked (load-bearing).** Has the epistemic boundary been named explicitly — where settled knowledge ends and current-best-understanding begins? Failure mode if unmet: `false-certainty`.
- **CQ3 — practical implication present (load-bearing).** Does the deeper understanding change what the user would do or conclude — is there a practical bearing? Failure mode if unmet: `academic-drift`.

A passing output anchors with a labelled surface explanation, descends through at least two genuinely-vertical mechanistic levels into the same phenomenon (not lateral drift), states each mechanism in plain terms with terminology glossed alongside, marks the epistemic boundary explicitly, names at least one practical implication, preserves alternative mechanisms when the phenomenon admits more than one, and calibrates confidence per level.

**Named failure modes.**

- *lateral-drift-trap* — successive levels move to adjacent topics rather than deeper into the same phenomenon.
- *elaboration-trap* — deeper level adds more facts at the same level of abstraction rather than revealing mechanism.
- *jargon-trap* — replacing accessible explanation with terminology without naming a mechanism in plain terms.
- *false-certainty* — mechanistic claims presented as settled when current science is indeterminate.

## REVISION GUIDANCE

Revise to convert horizontal elaboration into vertical mechanism. Revise to add the epistemic boundary where missing. Revise to name the mechanism in plain terms when jargon has substituted for explanation. Resist revising toward authoritative tone when current science is indeterminate — humility about the boundary is part of the output. Resist revising toward generality when the user asked for depth — depth is the contract.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a vertical mechanism-stack atom set: surface explanation, two or more genuinely-deeper mechanistic levels, epistemic-boundary atom, and practical-implication atoms — preserved as prose rather than as a list of facts**. The atoms are:

1. **Surface-explanation atom.** The accessible explanation the user already (likely) has — the baseline this clarification deepens. One short paragraph. Never skipped; the deeper levels are anchored to this.

2. **Level-1-beneath atoms.** Each atom names a mechanism one genuine layer beneath the surface. Mechanism here means: what causes the surface-level phenomenon to behave as it does. Elaboration-trap is the named failure mode the consolidator watches for; atoms that add more facts at the surface level (horizontal detail) rather than naming a mechanism (vertical depth) get reshaped or flagged.

3. **Level-2-beneath atoms.** Each atom names a mechanism one layer beneath Level 1 — i.e., what makes the Level 1 mechanism work as it does. Lateral-drift-trap is the named failure mode; atoms that move to adjacent topics rather than deeper into the same phenomenon get reshaped.

4. **Plain-language-mechanism check per atom.** Each Level 1 and Level 2 atom carries the mechanism stated in plain terms, not replaced by terminology that hides the mechanism. Jargon-trap is the named failure mode; atoms where terminology substitutes for explanation get reshaped to name the mechanism in plain terms (the terminology may sit alongside as a glossing aid).

5. **Epistemic-boundary atom.** Names explicitly where settled knowledge ends and current-best-understanding (or active debate) begins. False-certainty is the named failure mode; mechanistic claims presented as settled when current science is indeterminate get reshaped or flagged. The boundary may sit at the level-2 layer (deeper levels are indeterminate) or within a level (parts settled, parts active research).

6. **Practical-implication atoms.** Each atom names: what the deeper understanding changes — a behaviour the deeper level predicts that the surface did not, a decision the deeper level reframes, an intervention the deeper level enables. Academic-drift is the named failure mode; deeper levels that have no practical bearing on what the user would do or conclude get reshaped or flagged.

7. **Analogy atoms (optional).** When streams produced analogies that genuinely transfer the mechanism (rather than decorating it), they survive as anchoring atoms — never as a substitute for the mechanism itself.

8. **Alternative-mechanism atoms (optional).** When the phenomenon admits more than one mechanistic explanation, both are preserved with their respective epistemic grounding.

**Mode-specific bloat patterns to cut:**

- **Horizontal elaboration** — additional facts at the same level of abstraction presented as if they were deeper. Depth is vertical, not horizontal.
- **Lateral drift** — successive levels that move to adjacent phenomena rather than deeper into the same one.
- **Jargon substitution** — replacing accessible explanation with terminology without naming a mechanism. The corpus standard is mechanism-in-plain-terms with terminology as a gloss, not the reverse.
- **False certainty** — mechanistic claims presented as settled when current science is indeterminate or contested.
- **Academic drift** — deeper levels with no bearing on what the user would do, conclude, or expect. Depth must change something.
- **Surface-explanation skipping** — the baseline anchors the deeper levels; corpus that jumps straight to mechanism without the surface anchor loses the reader's purchase.

**What NOT to collapse:**

- **Alternative mechanisms** — when streams identified competing mechanistic explanations for the same phenomenon, both survive with their respective epistemic grounding. The corpus does not pick one when the field has not picked one.
- **Settled-vs-active disagreements** — when one stream presented a mechanism as settled and another flagged active scientific debate, the disagreement is the epistemic-boundary finding.
- **Depth disagreement** — when streams converged on different "Level 2 beneath" mechanisms (because the depth-direction admits multiple equally-valid axes — e.g., chemical vs. evolutionary mechanism), both survive as labelled alternative axes.

## VERIFICATION CRITERIA

Verified means: surface explanation present (not skipped); ≥2 mechanistic levels below surface, each genuinely vertical (not horizontal detail); epistemic boundary marked; ≥1 practical implication named; no jargon-substitution-for-mechanism; if a flowchart envelope is emitted, the mechanism is genuinely procedural. The three critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **deep clarification** — a prose explanation that walks from the surface accessible reading down through at least two genuine mechanistic layers, marks the epistemic boundary where knowledge ends, and lands at least one practical implication. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Surface explanation.** One paragraph stating the accessible-level explanation the user (likely) already has. Labelled inline with the literal `**Surface:**` prefix on the opening sentence to make the depth-axis explicit.

2. **Mechanistic clarification — two levels deeper.** Two labelled sub-blocks of prose:
   - `**Level 1 beneath:** [mechanism that causes the surface phenomenon].` One or two paragraphs naming the mechanism in plain terms; terminology may appear in parentheses or as a glossing line but does not replace the plain-terms explanation.
   - `**Level 2 beneath:** [mechanism that makes the Level 1 mechanism work].` Same plain-terms discipline. Each level is a genuine layer deeper into the same phenomenon — not lateral drift to adjacent topics.

3. **Epistemic boundary.** One short paragraph or labelled line: `**Epistemic boundary:** [where settled knowledge ends and current-best-understanding or active debate begins].` The boundary is named explicitly, not implied.

4. **Practical implications.** Bulleted list. Each: `**Practical implication:** [what the deeper understanding changes — behaviour predicted, decision reframed, intervention enabled].` At least one practical implication appears; "this is interesting but bears on nothing the user would do" gets surfaced as academic-drift rather than rendered as if it were an implication.

**Per-section conventions:**

- Use H2 headings for sections 1 through 4.
- The literal label prefixes — `**Surface:**`, `**Level 1 beneath:**`, `**Level 2 beneath:**`, `**Epistemic boundary:**`, `**Practical implication:**` — appear verbatim. They are operative depth-axis markers, not decoration.
- Prose first; envelope optional. The default is no diagram. The narrow exception is a `flowchart` envelope when the mechanism being clarified is itself procedural or spatial (a multi-step process, a pipeline, a control-flow algorithm). When in doubt, suppress the envelope.
- Plain-terms mechanism takes precedence over terminology. When a technical term must appear, it is glossed alongside the plain-terms statement, not substituted for it.
- When alternative mechanisms survived consolidation, render them as labelled sub-blocks inside section 2: `**Alternative Level 2 mechanism:** [the other axis or competing explanation]. [Plain-terms statement]. Epistemic standing: [how it relates to the primary mechanism].`
- When analogies anchor the mechanism, they appear inline within the level they support: `Analogous to: [domain] [analogy]. The transfer holds because [mechanism in common]; it does not transfer where [disanalogy].` Analogies that decorate without transferring mechanism are reshaped or removed at this layer.
- The epistemic-boundary section (3) is never silently elided; if the mechanism is fully settled, the boundary section states that explicitly (`No active boundary at the levels traversed here; the mechanism is settled at both Level 1 and Level 2.`).


---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, chat, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `contradicts`, `qualifies`, `analogous-to`, `extends`, `supersedes`
**Deprioritize:** `precedes`, `produces`

*Family: frame-paradigm. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
