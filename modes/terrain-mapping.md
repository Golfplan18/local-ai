---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-24

---

# MODE: Terrain Mapping

```yaml
# 0. IDENTITY
mode_id: terrain-mapping
canonical_name: Terrain Mapping
suffix_rule: analysis
educational_name: thorough orientation in unfamiliar terrain

# 1. TERRITORY AND POSITION
territory: T14-orientation-in-unfamiliar-territory
gradation_position:
  axis: depth
  value: thorough
adjacent_modes_in_territory:
  - mode_id: quick-orientation
    relationship: lighter sibling (depth-light)
  - mode_id: domain-induction
    relationship: heavier sibling (depth-molecular)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "what is X"
    - "where do I start"
    - "what do I need to know about"
    - "give me the lay of the land"
    - "I'm unfamiliar with this"
  prompt_shape_signals:
    - "walk me through"
    - "the big picture"
    - "map this domain for me"
    - "concept map of"
    - "introduce me to"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user is unfamiliar with the domain and wants thorough orientation (~5 min)"
    - "the prompt names a domain the conversation history shows the user has not engaged with"
  routes_away_when:
    - "user wants a quick orienting summary (~1 min)" → quick-orientation
    - "user wants a deep molecular induction into the domain (~10+ min)" → domain-induction
    - "user is already familiar and wants the next mechanism beneath" → deep-clarification (T10)
    - "user is exploring open-endedly with no desire for a navigable map" → passion-exploration (T20)
    - "user has multiple competing explanations for the same evidence" → competing-hypotheses (T5)
when_not_to_invoke:
  - "User has named a specific deliverable" → Project Mode
  - "User is in execution mode and wants to act, not orient" → Project Mode
  - "Domain is intimately familiar to the user" → Deep Clarification

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [domain_to_orient_in, current_user_knowledge_level, prior_orientation_attempts]
    optional: [adjacent_domains_user_already_knows, specific_sub_areas_of_interest]
    notes: "Applies when user explicitly states their starting knowledge and asks for a navigable concept map of a specified domain."
  accessible_mode:
    required: [domain_or_topic_user_is_new_to]
    optional: [hint_at_what_user_already_knows, what_user_wants_to_do_with_the_orientation]
    notes: "Default. Mode infers user's starting level from the way the question is phrased and produces a thorough survey-level map."
  detection:
    expert_signals: ["I'm familiar with X but not Y", "the canonical introduction is", "the standard taxonomy"]
    accessible_signals: ["what is X", "where do I start", "give me the lay of the land", "introduce me to"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the domain or topic you want oriented in, and roughly what do you already know about it?'"
    on_underspecified: "Ask: 'Want a quick summary (~1 min — Quick Orientation), thorough survey (~5 min — Terrain Mapping), or deep molecular induction (~10+ min — Domain Induction)?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are concepts classified as known / contested / open, with no contested position presented as settled (or vice versa)?"
    failure_mode_if_unmet: false-consensus
  - cq_id: CQ2
    question: "Does the map have at least one cross-link to an adjacent domain — Novak's marker of integrative understanding?"
    failure_mode_if_unmet: no-cross-link-trap
  - cq_id: CQ3
    question: "Does the prose stay at survey level rather than drilling into one sub-area (≤30% on any single sub-area)?"
    failure_mode_if_unmet: premature-depth
  - cq_id: CQ4
    question: "Does the map name what is out of scope — its boundary?"
    failure_mode_if_unmet: missing-boundary

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: premature-depth
    detection_signal: "Prose spends more than 30% on any single sub-area before the full territory is mapped."
    correction_protocol: re-dispatch (pull back to survey level)
  - name: textbook-trap
    detection_signal: "Output reproduces a standard overview without known/contested/open separation."
    correction_protocol: re-dispatch (classify each major concept by epistemic status)
  - name: false-consensus
    detection_signal: "One school of thought's view is presented as the domain consensus when rival schools exist."
    correction_protocol: re-dispatch (qualify with 'the standard view holds X; dissenters argue Y')
  - name: no-cross-link-trap
    detection_signal: "Output is a strict tree with no lateral connections."
    correction_protocol: re-dispatch (add ≥1 cross-link to an adjacent domain)
  - name: low-concept-count
    detection_signal: "Map has fewer than 4 concepts."
    correction_protocol: re-dispatch (expand to ≥4 concepts, or route to Deep Clarification if domain is too narrow)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - novak-concept-map-tradition
    - taxonomic-frameworks-for-the-target-domain
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: domain-induction
    when: "User wants molecular induction into the domain — full ~10+ min orientation with prerequisite chain and operational competence."
  sideways:
    target_mode_id: passion-exploration
    when: "Orientation opens with no terminal point and user wants generative exploration." 
  downward:
    target_mode_id: quick-orientation
    when: "User has time pressure or wants a ~1 min orienting summary rather than a ~5 min survey."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Terrain Mapping is the precision with which concepts are classified by epistemic status (known / contested / open) and tied to organising structure. A thin pass enumerates concepts; a substantive pass labels each by epistemic status, names the organising framework (hierarchy / hub-and-spoke / network / etc.), and identifies prerequisite chains. Test depth by asking: would the map predict where a newcomer would predictably form a wrong impression from survey-level sources alone? Each concept carries a literal `known` / `contested` / `open` label.

## BREADTH ANALYSIS GUIDANCE

Breadth in Terrain Mapping is the cartographic completeness — all major sub-areas, schools of thought, and adjacent domains represented. Widen the lens to map the full landscape: settled facts, contested positions (with rival schools represented), open questions, principal actors, and adjacent domains. Generate ≥3 questions the user has not asked but would need to answer to navigate effectively. Breadth markers: at least one cross-link to an adjacent domain (`is_cross_link: true`); ≥3 open questions tied to specific concepts; rival schools represented when domain has them.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Terrain Mapping is a thorough (~5min) Novak-tradition concept-map orientation for a user new to a domain. It is the depth-thorough sibling to quick-orientation (depth-light, ~1min) and domain-induction (depth-molecular, ~10+min) within T14. The mode is descriptive of the domain's concepts, organising structure, and epistemic-status distribution (known / contested / open) — not deep mechanism investigation (deep-clarification, T10) and not open-ended generative exploration (passion-exploration, T20). Its central discipline is honest epistemic-status classification: contested territory rendered as authoritative consensus misleads the newcomer at the worst possible point — when they're forming their map.

**Procedure.**

1. Lock the focus question — the orientation question driving the map, plus the user's starting knowledge level.
2. Inventory concepts (minimum 4) — each with brief characterisation and position in domain structure. Below 4 concepts, surface the sideways-route to deep-clarification.
3. Classify each concept with an epistemic-status tag: `known` (settled in the domain), `contested` (rival schools or active debate), `open` (genuine unknown).
4. Represent rival schools in qualified form where they exist — "the standard view holds X; dissenters argue Y" rather than authoritative single-school framing.
5. Surface at least 3 open questions, each tied to a specific concept in the inventory.
6. Name the organising topology of the domain (`hierarchy` / `hub-and-spoke` / `network` / `chain` / `cluster-bridge`) and prerequisite chains.
7. Add at least one cross-link to an adjacent domain — Novak's marker of integrative understanding. Cross-links appear in their own section, not buried inside concept descriptions.
8. State the boundary explicitly — what's out of scope, adjacent domains touched but not surveyed, sub-areas deferred to follow-on modes.
9. Maintain survey-level discipline — no single sub-area exceeds ~30% of the map. Drilling that breached the threshold gets pulled back to survey breadth.
10. Assign confidence per epistemic-status classification and per cross-link.

**Goal.** Produce a thorough survey-level orientation map — a Novak-tradition concept map with epistemic-status tagging per concept, at least one adjacent-domain cross-link, at least three concept-tied open questions, and an explicit boundary statement.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — epistemic-status honesty (load-bearing).** Are concepts classified as known / contested / open, with no contested position presented as settled (or vice versa)? Failure mode if unmet: `false-consensus`.
- **CQ2 — cross-link present.** Does the map have at least one cross-link to an adjacent domain (Novak's marker of integrative understanding)? Failure mode if unmet: `no-cross-link-trap`.
- **CQ3 — survey-level discipline (load-bearing).** Does the prose stay at survey level rather than drilling into one sub-area (≤30% on any single sub-area)? Failure mode if unmet: `premature-depth`.
- **CQ4 — boundary statement explicit.** Does the map name what is out of scope — its boundary? Failure mode if unmet: `missing-boundary`.

A passing output covers at least 4 concepts each carrying a known/contested/open tag, represents rival schools in qualified form where they exist, names the organising topology, surfaces at least 3 concept-tied open questions, includes at least one adjacent-domain cross-link in its own section, and states the boundary explicitly with what's out of scope.

**Named failure modes.**

- *premature-depth* — prose spends more than 30% on any single sub-area before the full territory is mapped.
- *textbook-trap* — output reproduces a standard overview without known/contested/open separation.
- *false-consensus* — one school of thought's view is presented as the domain consensus when rival schools exist.
- *no-cross-link-trap* — output is a strict tree with no lateral connections to adjacent domains.
- *low-concept-count* — map has fewer than 4 concepts; below threshold, route to deep-clarification.

## REVISION GUIDANCE

Revise to pull back when prose has drilled too deeply into one sub-area. Revise to add epistemic-status labels when missing. Revise to add cross-links when the map is a flat tree. Revise to qualify contested positions presented as settled. Resist revising toward authoritative tone when domain has rival schools — qualify with "the standard view holds X; dissenters argue Y". Resist revising toward exhaustive enumeration when survey breadth is the criterion.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a Novak-tradition orientation map: focus-question lock, concept atoms classified by epistemic status (known / contested / open), open-question atoms tied to specific concepts, domain-structure atom naming the organising topology, adjacent-domain cross-link atoms, boundary-statement atom, and survey-level discipline (no single sub-area drilling)**. The atoms are:

1. **Focus-question atom.** The orientation question driving the map. One short sentence; subsequent atoms reference this lock.

2. **Concept atoms — epistemically classified.** Each atom names: one concept with a short characterisation and a literal epistemic-status tag — `known` (settled in the domain), `contested` (rival schools or active debate), `open` (genuine unknown). False-consensus is the named failure mode the consolidator watches for; contested positions presented as settled (or vice versa) get reshaped to honest classification. Textbook-trap is the mirror failure mode; standard overviews without epistemic-status classification get reshaped to per-concept tagging. Low-concept-count is named failure mode for sparse maps (≥4 concepts is the minimum; below threshold, sideways-route to deep-clarification).

3. **Open-question atoms.** Each atom names: an open question tied to a specific concept from the inventory. At least three open questions appear. Open-question count below 3 with concept-inventory ≥4 is reshaped to surface the unknowns.

4. **Domain-structure atom.** Names the organising topology of the domain: `hierarchy` / `hub-and-spoke` / `network` / `chain` / `cluster-bridge`. Where rival schools structure the domain differently, both organising views surface.

5. **Adjacent-domain cross-link atoms.** Each atom names: an adjacent domain and the cross-link concept that connects to it. At least one cross-link with `is_cross_link: true` semantics (Novak's marker of integrative understanding). No-cross-link-trap is the named failure mode; strict tree structures without lateral connections get reshaped to surface ≥1 cross-link.

6. **Boundary-statement atom.** Names what is *out of scope* for the orientation — adjacent domains the map touches but does not survey, sub-areas deferred to follow-on modes, contested-by-the-user framings excluded.

7. **Survey-level discipline atom.** A standing atom: no single sub-area exceeds 30% of the map's content. Premature-depth is the named failure mode; prose that drilled too deeply into one sub-area before mapping the full territory gets reshaped to pull back to survey breadth.

8. **Rival-school representation atoms — when applicable.** Where the domain has rival schools of thought, each school carries its own representation: `the standard view holds X; dissenters argue Y`. The map qualifies authoritative tone when rival schools exist.

9. **Confidence per finding.** Confidence per epistemic-status classification, per concept-mapping, per cross-link.

**Mode-specific bloat patterns to cut:**

- **Premature depth** — drilling into one sub-area before the full territory is mapped.
- **Textbook trap** — standard overview without known/contested/open classification.
- **False consensus** — one school presented as the domain's view when rival schools exist.
- **No-cross-link** — flat tree without lateral connections to adjacent domains.
- **Low concept count** — fewer than 4 concepts; below threshold, this isn't a survey, it's a clarification.
- **Authoritative tone on contested territory** — assertive framing where qualified framing is honest.
- **Missing boundary** — map without naming what's out of scope; expansion-by-default.

**What NOT to collapse:**

- **Epistemic-status tags** — known / contested / open distinctions are operative; tags do not blur.
- **Rival schools** — when the domain has them, both survive with their respective views.
- **Cross-links** — at least one is required; integrative understanding lives in the cross-links.
- **Open questions** — they are the load-bearing finding for orientation; the user needs to know what they don't yet know.
- **Stream disagreement about epistemic status** — when one stream classified a concept as `contested` and another as `known`, the disagreement is itself a finding about the domain's contested-vs-settled boundary.

## VERIFICATION CRITERIA

Verified means: focus question stated and matches envelope; ≥4 concepts mapped (below 4 is Deep Clarification territory); each concept classified known/contested/open; ≥1 cross-link to an adjacent domain; ≥3 open questions tied to specific concepts; survey-level discipline maintained (≤30% on any single sub-area); boundary statement names what is out of scope; rival schools represented when domain has them. The four critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **thorough survey-level orientation map** — a Novak-tradition concept map with epistemic-status tagging per concept, ≥1 cross-link to an adjacent domain, ≥3 open questions tied to specific concepts, and an explicit boundary statement. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Focus question.** One short paragraph stating the orientation question and the user's starting knowledge level.

2. **Known territory.** Bulleted list. Each: `**[Concept]** — epistemic status: known. Brief characterisation: [...]. Position in domain structure: [...].` Concepts here are settled.

3. **Unknown or contested territory.** Bulleted list. Each: `**[Concept]** — epistemic status: [contested / open]. If contested: rival schools represented as 'the standard view holds X; dissenters argue Y'. If open: characterisation of the unknown and why it remains open.`

4. **Open questions.** Numbered list. At least three. Each: `[N]. **[Open question]** — tied to concept: [...]. Why this is operative for orientation: [...].`

5. **Domain structure.** One paragraph. `**Organising topology:** [hierarchy / hub-and-spoke / network / chain / cluster-bridge]. **Prerequisite chains:** [...]. **Where rival schools structure the domain differently:** [...].`

6. **Adjacent connections.** Bulleted list of cross-links. Each: `**[Adjacent domain]** ↔ [concept in this domain]: **cross-link basis:** [shared mechanism / convergent operation / borrowed vocabulary]. **What knowing the adjacent domain unlocks here:** [...].` At least one cross-link surfaces.

7. **Boundary statement.** One paragraph naming what's out of scope. `**This map covers:** [...]. **Out of scope:** [...]. **Adjacent domains touched but not surveyed:** [...]. **Sideways-routes for the out-of-scope material:** [...].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- Epistemic-status tags (`known` / `contested` / `open`) appear verbatim per concept. Untagged concepts are reshaped at this layer.
- Survey-level discipline is enforced — no single sub-area exceeds 30% of the map. Drilling that breached the threshold gets pulled back to survey breadth.
- Rival schools (section 3) carry the qualified-framing pattern `the standard view holds X; dissenters argue Y`. Authoritative single-school framings on contested territory get reshaped.
- Cross-links (section 6) appear in their own section, not buried inside the concept lists. The integrative-understanding signal needs visibility.
- Open questions (section 4) tie to specific concepts. Untied questions get reshaped.
- When envelope-bearing rendering is appropriate: `concept_map` envelope with ≥4 concepts each carrying `hierarchy_level`, ≥2 linking phrases, ≥3 propositions with all ids resolving, ≥1 proposition with `is_cross_link: true`, and `focus_question` matching prose.
- When the concept-count fell below 4 despite the focus question warranting a broader map, the deliverable opens with: `**Note: the domain may be narrower than survey-level orientation requires. Deep-clarification (T10) is the appropriate sideways-route for narrow conceptual deepening; if survey breadth is what's wanted, the focus question may need to widen.**`

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- CAF
- Concept Fan
- AGO

Mental models (always loaded):
- map-territory
- first-principles
- cynefin-framework
- niches
- scale
- alexander-pattern-language

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator, reference]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `parent`, `child`, `analogous-to`, `requires`, `extends`
**Deprioritize:** `contradicts`, `supersedes`

*Family: orientation-exploration. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
