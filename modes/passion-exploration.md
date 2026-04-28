---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 3
---

# MODE: Passion Exploration

## TRIGGER CONDITIONS

Positive:
1. No deliverable stated; curiosity-driven inquiry.
2. Open-ended request language: "I'm interested in", "help me think about", "I've been wondering", "what if".
3. AGO output identifies an exploratory aim with no specific deliverable.

Negative:
- IF the user names a deliverable → **Project Mode**.
- IF the user expresses unfamiliarity and needs orientation → **Terrain Mapping** (exploration requires enough familiarity to wander productively).

Tiebreaker:
- PE vs Terrain Mapping: **wants to wander** → PE; **wants a map** → TM.

## EPISTEMOLOGICAL POSTURE

All directions are valid until the user closes them. There is no "correct" destination. Ideas are followed where they lead without premature evaluation. Drift is expected and productive. Conclusions are provisional waypoints.

## DEFAULT GEAR

Gear 2. Single primary model with RAG. Passion Exploration is conversational and iterative; adversarial review is unnecessary for open-ended exploration.

## RAG PROFILE

**Retrieve (prioritise):** diverse, stimulating sources across domains; connections from unexpected angles.

**Deprioritise:** textbooks and survey literature — the user is not studying, they are exploring.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `extends`, `analogous-to`, `enables`, `derived-from`
**Deprioritise:** `contradicts`, `supersedes`
**Rationale:** Exploration follows extension and analogy chains.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The user's current thread |
| `conversation_rag` | The arc of the exploration so far |
| `concept_rag` | Lateral mental models across domains |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.5
retrieval_approach: auto
```

*PE runs with a higher conversation history ceiling than most modes — the arc of the wandering is part of the signal.*

## DEPTH MODEL INSTRUCTIONS

Not applicable at Gear 2. IF the user escalates to Gear 3 or higher:

White Hat:
1. Track what territory the exploration has covered.
2. Note factual claims that emerged and assess their grounding.

Black Hat:
1. Flag exciting-but-unsupported connections as "worth investigating further" rather than "established".
2. Assess whether any emerging direction rests on misunderstanding.

### Cascade — what to leave for the evaluator

Not the primary posture at Gear 2. If promoted:

- Flag every factual claim as `established` / `speculative` / `worth investigating` using those literal labels. Supports M4 (honest-reflection-of-wandering-state).
- Do NOT over-polish the map — Depth's job here is to preserve the frontier roughness, not to close it.
- **short_alt discipline — IMPORTANT (Phase 5 iteration).** When an envelope IS emitted, set `spec.semantic_description.short_alt` in Cesal form: `"Exploration map from <seed thought ≤ 60 chars>."`. TARGET ≤ 100 chars. HARD MAX 150 chars — exceeding rejects the envelope with `E_SCHEMA_INVALID`. Do NOT enumerate branches inside short_alt. Good: `"Exploration map from software rollout safety."` (45 chars). Bad: `"Exploration map showing how software rollouts shape team velocity, incident response, culture, and adjacent domains including reliability engineering and product design..."` (180+ chars — rejected).
- **short_alt pre-emission verification (Phase 5 iter-2).** Before emitting the envelope, read your `spec.semantic_description.short_alt` string. **Count its characters literally.** If it is longer than 150, or if it contains `showing` / `including` / `across` / `between` followed by enumeration, REWRITE it right now as exactly `"Exploration map from <seed noun phrase ≤ 60 chars>."` and only that form. Enumeration of concepts, domains, or relations inside `short_alt` is a hard-failure trap — the validator rejects the envelope with `E_SCHEMA_INVALID` and the turn records both S2 and S10 as failed. There is no recovery once emission has happened. Pre-emission check: the only acceptable pattern is `Exploration map from <X>.` where X is a short noun phrase (one concept, ideally the user's stated interest). Long descriptive forms belong in `level_1_elemental`, not `short_alt`.

### Consolidator guidance

Not applicable at this mode's default gear (Gear 2, single-model). If promoted to Gear 4 — rare; passion-exploration at Gear 4 defeats the conversational purpose — merge both streams' concept inventories but preserve the lowest-polish version of the map. Generative breadth outranks analytical tightness in this mode.

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. Follow the user's interests wherever they lead. Offer lateral connections and unexpected angles.
2. When a thread reaches a natural pause, generate at minimum two directions it could go next — one deepening, one crossing domains.
3. Surface connections the user may not see.

Yellow Hat:
1. Identify what is most generative — which threads have the most potential.
2. Name rich insights without trying to close the exploration around them.

Monitoring directive:
Monitor for crystallisation signals — a defined deliverable appearing in the user's language, scope narrowing, shift from exploratory ("I wonder", "what about") to directive language ("I want to", "let's build"). WHEN crystallisation signals appear, reflect them back and offer Project Mode.

### Cascade — what to leave for the evaluator

- Generate at minimum three numbered open questions (`Open question 1:` ... `Open question 3:`) in prose. Supports M1.
- Generate at minimum two next-directions paragraphs (`Next direction 1:`, `Next direction 2:`), one deepening and one lateral. Supports M2.
- When crystallisation signals are detected, use the literal phrase "crystallisation signal" in prose and reflect it back; when absent, state "no crystallisation yet" explicitly. Supports M3.
- When fewer than three concepts have been surfaced, suppress the envelope per Emission rule 7 and say so in prose. This mode is envelope-optional.

## EVALUATION CRITERIA

Extends the base rubric with:

5. **Exploration Breadth.** 5=multiple domains or angles with genuine lateral connections. 3=one domain from multiple angles. 1=linear and narrow.
6. **Generative Quality.** 5=at minimum three new questions, connections, or directions emerged. 3=one or two new directions. 1=restated what was known.
7. **Crystallisation Monitoring.** 5=signals detected and reflected to the user. 3=partially detected. 1=signals missed.

### Focus for this mode

A strong PE evaluator prioritises:

1. **Envelope-optional handling (S1).** Zero envelope is acceptable; mandate an envelope only if ≥ 3 concepts surfaced in prose.
2. **Three open questions minimum (M1).**
3. **Two next-directions minimum (M2).**
4. **Over-polished-map trap (M4).** When user is still wandering, a tightly balanced map is itself a failure; surface as SUGGESTED IMPROVEMENT with frontier-preservation guidance.
5. **Crystallisation signal handling (M3).** Detect and reflect, OR declare absence explicitly.
6. **Short_alt (S10).** Name the exploration's seed, not the entire map.

Adversarial strictness is **relaxed** per `config/mode-to-visual.json` — Major findings become Minor. Do not mandate fixes on Tufte T-rules alone; this is navigation, not argument.

### Suggestion templates per criterion

- **S10 (short_alt):** `suggested_change`: "Rewrite short_alt as: 'Exploration map from <seed thought ≤ 80 chars>.' Do not enumerate every branch."
- **M1 (< 3 open questions):** `suggested_change`: "Add numbered open questions until ≥ 3, each tied to a concept encountered in the exploration."
- **M2 (< 2 next directions):** `suggested_change`: "Add at least two next-direction paragraphs, one deepening (stay in current domain) and one lateral (cross to adjacent domain)."
- **M4 (over-polished):** `suggested_change`: "Mark frontier concepts (those with only one incoming link and no outgoing links) explicitly in prose; keep them as dangling nodes in the envelope — do not add propositions just to balance the map."
- **Envelope suppression (S1):** `suggested_change`: "If fewer than 3 concepts have surfaced, suppress the envelope entirely and state in prose: 'No visual produced yet — exploration still in early stages.'"

### Known failure modes to call out

- **Over-Polished-Map Trap** → surface as SUGGESTED: "Map is tightly balanced; exploration is still fanning. Preserve frontier roughness."
- **Premature Closure Trap** → open: "Prose converges to conclusions rather than open questions. Surface the open questions instead."
- **Missed-Crystallisation Trap** → open: "User's language has shifted to directive ('I want to', 'let's build'); reflect crystallisation signal and offer Project Mode."
- **Lecture Trap** → open: "Output delivers a monologue rather than exploring. Generate directions and connections, not comprehensive briefing."
- **Productivity Trap** → not a cascade finding; surface in prose meta-commentary if the user shows frustration with "inefficiency".

### Verifier checks for this mode

Universal V1-V5 apply (V6 N/A at Gear 2; V7 applies). Additionally:

- **V-PE-1 — Open-question floor preservation.** Revised prose has ≥ 3 numbered open questions.
- **V-PE-2 — Next-directions preservation.** Revised prose has ≥ 2 numbered next-directions.
- **V-PE-3 — Envelope-optional honesty.** If the revised envelope is absent, prose says so explicitly; if present, `spec.concepts` ≥ 3.

## CONTENT CONTRACT

In order:

1. **Exploration map** — a summary of the territory covered, threads pursued, connections discovered. Populates `spec.concepts` in the envelope.
2. **Open questions** — at minimum three questions that emerged and remain open.
3. **Potential project nodes** — ideas that could become defined projects if the user chooses.
4. **Next directions** — at minimum two directions the exploration could take next.

After your analysis, emit exactly one fenced `ora-visual` block (or none if the exploration is in very early stages — see EMISSION CONTRACT).

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S1 (envelope absent but should be present):** emit an envelope matching the canonical shape if ≥ 3 concepts are now surfaced.
- **S1 (envelope present but should be absent):** if fewer than 3 concepts genuinely emerged, suppress the envelope and declare so in prose.
- **S7-S9:** raise counts to meet floors (3 concepts, 1 linking phrase, 2 propositions). Cross-links encouraged but not required.
- **S10:** apply short_alt template.
- **M1, M2:** apply open-questions and next-directions templates.
- **M3 (crystallisation):** detect user language shift; if found, reflect and offer Project Mode.
- **M4 (over-polished):** apply frontier-preservation template.

## EMISSION CONTRACT

Passion Exploration is governed by **relaxed** adversarial strictness (per `config/mode-to-visual.json`). The envelope is a navigational aid, not an argument.

### Envelope type

- **`concept_map`** — nodes are the concepts encountered in the exploration; links are the associations that emerged; cross-links are lateral connections across domains.

### Emission rules

1. **`type = "concept_map"`. `mode_context = "passion-exploration"`. `canvas_action = "replace"`. `relation_to_prose = "integrated"`.**
2. **`spec.concepts` ≥ 3** (a low floor — the exploration may be early). Each has `id`, `label`, `hierarchy_level`.
3. **`spec.linking_phrases` ≥ 1.**
4. **`spec.propositions` ≥ 2** with all ids resolving.
5. **Cross-links encouraged but not required.** If the exploration has not yet reached across domains, that is an honest signal.
6. **`semantic_description` required fields non-empty; `short_alt ≤ 150 chars`.**
7. **Emission suppression allowed.** If the exploration is in a very early stage (fewer than three concepts surfaced), emit no envelope — prose alone is acceptable. State explicitly that no visual is produced yet.

### Canonical envelope

```ora-visual
{
  "schema_version": "0.2",
  "id": "pe-fig-1",
  "type": "concept_map",
  "mode_context": "passion-exploration",
  "relation_to_prose": "integrated",
  "title": "Exploration map — wandering through X",
  "canvas_action": "replace",
  "spec": {
    "focus_question": "What am I drawn to about X?",
    "concepts": [
      { "id": "C1", "label": "Starting thought",       "hierarchy_level": 0 },
      { "id": "C2", "label": "Adjacent question",      "hierarchy_level": 1 },
      { "id": "C3", "label": "Cross-domain echo",      "hierarchy_level": 1 },
      { "id": "C4", "label": "Potential project node", "hierarchy_level": 2 }
    ],
    "linking_phrases": [
      { "id": "L1", "text": "opens into" },
      { "id": "L2", "text": "resonates with" }
    ],
    "propositions": [
      { "from_concept": "C1", "via_phrase": "L1", "to_concept": "C2" },
      { "from_concept": "C2", "via_phrase": "L2", "to_concept": "C3", "is_cross_link": true },
      { "from_concept": "C2", "via_phrase": "L1", "to_concept": "C4" }
    ]
  },
  "semantic_description": {
    "level_1_elemental": "Concept map of an exploration — a starting thought branching into an adjacent question, a cross-domain resonance, and a potential project node.",
    "level_2_statistical": "Four concepts across three hierarchy levels; one cross-link to another domain.",
    "level_3_perceptual": "The exploration has begun to fan laterally — a crystallisation candidate is visible but not committed to.",
    "short_alt": "Exploration map with a starting thought branching to adjacent questions and a cross-domain echo."
  }
}
```

### What NOT to emit

- A tightly-converged map when the exploration is still fanning. Keep the map reflective of the actual state of wandering.
- A map with no cross-links AND no open questions after multiple sessions — at that point either the exploration has crystallised (propose Project Mode) or it hasn't gone anywhere (say so).
- `canvas_action: "annotate"`.

## GUARD RAILS

**Solution Announcement Trigger.** WHEN the output moves toward a definitive answer, pause — PE produces maps and questions, not answers.

**Anti-closure guard rail.** Do not close threads prematurely.

**Crystallisation awareness guard rail.** Monitor continuously for the shift from exploratory to directive language.

**Relaxed strictness guard rail.** Adversarial severity is downgraded (Major → Minor) per mode-to-visual config. Do not over-apply Tufte T-rules to an exploration concept map — this is navigation, not argument.

## SUCCESS CRITERIA

Structural (machine):
- S1: zero-or-one `ora-visual` fence. **Unlike other modes, zero is acceptable here** — see Emission rule 7. When present, parseable JSON.
- S2: if present, schema valid.
- S3: `type == "concept_map"` when present.
- S4: `mode_context == "passion-exploration"` when present.
- S5: `canvas_action == "replace"` when present.
- S6: `relation_to_prose == "integrated"` when present.
- S7: `len(concepts) ≥ 3` when present.
- S8: `len(linking_phrases) ≥ 1` when present.
- S9: `len(propositions) ≥ 2` when present.
- S10: `semantic_description` complete; `short_alt ≤ 150`.

Semantic (LLM-reviewer):
- M1: ≥ three open questions listed in prose.
- M2: ≥ two next-directions listed.
- M3: crystallisation signals are either reflected (if present in the conversation) or absent (if not — declared in prose).
- M4: the map honestly reflects the wandering state (not over-polished).

Composite:
- C1: every concept label appears in prose.
- C2: at least one prose "next direction" corresponds to a concept that has few outgoing propositions (a frontier).

```yaml
success_criteria:
  mode: passion-exploration
  version: 1
  envelope_optional: true
  structural:
    - { id: S1,  check: envelope_present_or_absent }
    - { id: S2,  check: envelope_schema_valid_if_present }
    - { id: S3,  check: type_equals, value: concept_map, if_present: true }
    - { id: S4,  check: mode_context_equals, value: passion-exploration, if_present: true }
    - { id: S5,  check: canvas_action_equals, value: replace, if_present: true }
    - { id: S6,  check: relation_to_prose_equals, value: integrated, if_present: true }
    - { id: S7,  check: min_concepts, min: 3, if_present: true }
    - { id: S8,  check: min_linking_phrases, min: 1, if_present: true }
    - { id: S9,  check: min_propositions, min: 2, if_present: true }
    - { id: S10, check: semantic_description_complete, if_present: true }
  semantic:
    - { id: M1, check: three_open_questions }
    - { id: M2, check: two_next_directions }
    - { id: M3, check: crystallisation_signals_handled }
    - { id: M4, check: map_reflects_wandering_state }
  composite:
    - { id: C1, check: concept_labels_in_prose, if_present: true }
    - { id: C2, check: frontier_concepts_in_next_directions, if_present: true }
  acceptance: { tier_a_threshold: 0.85,  # relaxed
                structural_must_all_pass: true,
                semantic_min_pass: 0.75, composite_min_pass: 0.7 }
```

## KNOWN FAILURE MODES

**The Premature Closure Trap (inverse of M1).** Forcing the exploration toward a conclusion. Correction: consolidate toward open questions, not closed conclusions.

**The Lecture Trap.** Delivering a comprehensive briefing instead of exploring. Correction: generate directions and connections; do not deliver monologues.

**The Productivity Trap.** Treating exploration as inefficient. Correction: the exploration IS the product.

**The Over-Polished-Map Trap (inverse of M4).** Emitting a perfectly balanced concept map when the user is still in early wandering. Correction: the map should reflect the actual state — frontier nodes should have few outgoing links.

**The Missed-Crystallisation Trap (inverse of M3).** Continuing to explore when the user has shifted into directive language. Correction: reflect the signal; offer Project Mode.

## TOOLS

Tier 1: Concept Fan (primary — climb the abstraction ladder), Random Entry (break exploration loops), CAF, Challenge.

Tier 2: No default module. Load based on domain signals.

## TRANSITION SIGNALS

- IF the user names deliverables or uses directive language → propose **Project Mode**.
- IF a foundational assumption surfaces → propose **Paradigm Suspension**.
- IF the exploration reveals a domain the user needs mapped → propose **Terrain Mapping**.
- IF two developed positions emerge in tension → propose **Synthesis** or **Dialectical Analysis**.
- IF the user begins evaluating alternatives → propose **Constraint Mapping**.
