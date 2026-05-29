---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-24

---

# MODE: Passion Exploration

```yaml
# 0. IDENTITY
mode_id: passion-exploration
canonical_name: Passion Exploration
suffix_rule: none
educational_name: passion exploration (specificity-personal-interest)

# 1. TERRITORY AND POSITION
territory: T20-open-exploration
gradation_position:
  axis: specificity
  value: personal-interest
adjacent_modes_in_territory:
  - mode_id: idea-development
    relationship: specificity variant (creative-generation, deferred per CR-6)
  - mode_id: research-question-generation
    relationship: specificity variant (question-formulation, deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "no deliverable stated; curiosity-driven inquiry"
    - "wants to wander rather than execute"
    - "interested in a topic without a specific endpoint"
  prompt_shape_signals:
    - "I'm interested in"
    - "help me think about"
    - "I've been wondering"
    - "what if"
    - "let me explore"
disambiguation_routing:
  routes_to_this_mode_when:
    - "wants to wander productively without committing to a destination"
    - "open exploration of an area of personal interest"
  routes_away_when:
    - "names a deliverable or uses directive language" → project-mode (T21)
    - "expresses unfamiliarity and needs orientation" → terrain-mapping (T14)
    - "two developed positions emerge in tension" → synthesis or dialectical-analysis (T12)
when_not_to_invoke:
  - "User has named a deliverable or specified an output — Passion Exploration is generative, not productive"
  - "User needs analytical defeasibility — Passion Exploration produces maps and questions, not adjudicated findings"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: generative

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: not-applicable
    optional: not-applicable
    notes: "expert_mode is not-applicable for Passion Exploration — the mode is generative rather than analytical, so the dual-contract distinction (which separates expert-vocabulary prompts from accessible prompts within an analytical operation) does not apply. All Passion Exploration prompts are accessible_mode by construction."
  accessible_mode:
    required: [topic_or_seed_thought]
    optional: [prior_exploration_context, motivating_curiosity]
    notes: "Default and only mode. The user supplies a seed; the mode wanders productively from there."
  detection:
    expert_signals: []
    accessible_signals: ["I'm interested in", "wondering about", "let me explore", "help me think about"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the topic or thread you'd like to explore? It can be loose — exploration starts where curiosity points.'"
    on_underspecified: "Ask: 'Are you exploring open-endedly, or do you have a specific question or deliverable in mind? The first invites Passion Exploration; the second invites Project Mode.'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have at least three open questions emerged and remained open, rather than being closed prematurely?"
    failure_mode_if_unmet: premature-closure
  - cq_id: CQ2
    question: "Have at least two next-directions been offered (one deepening, one lateral)?"
    failure_mode_if_unmet: lecture-trap
  - cq_id: CQ3
    question: "Has the mode monitored for crystallization signals (shift to directive language) and reflected them back to the user?"
    failure_mode_if_unmet: missed-crystallization
  - cq_id: CQ4
    question: "Does the exploration map honestly reflect the wandering state, or has it been over-polished into apparent completion?"
    failure_mode_if_unmet: over-polished-map

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: premature-closure
    detection_signal: "Output converges to conclusions rather than maintaining open questions."
    correction_protocol: re-dispatch (consolidate toward open questions, not closed conclusions)
  - name: lecture-trap
    detection_signal: "Output delivers monologue or comprehensive briefing rather than exploring."
    correction_protocol: re-dispatch (generate directions and connections; not comprehensive briefing)
  - name: missed-crystallization
    detection_signal: "User's language has shifted to directive ('I want to', 'let's build') but mode continued to explore."
    correction_protocol: flag (reflect crystallization signal and offer Project Mode)
  - name: over-polished-map
    detection_signal: "Map is tightly balanced when exploration is still fanning."
    correction_protocol: flag (preserve frontier roughness; mark frontier nodes explicitly)
  - name: productivity-trap
    detection_signal: "Mode treats exploration as inefficient and pushes toward output."
    correction_protocol: flag (the exploration IS the product)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - debono-concept-fan (climb the abstraction ladder)
    - debono-random-entry (break exploration loops)
    - cross-domain-analogical-mapping
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: terrain-mapping
    when: "User shifts from wandering to wanting a structured orientation map of the domain."
  sideways:
    target_mode_id: project-mode
    when: "Crystallization signals appear — user shifts to directive language naming a deliverable."
  downward:
    target_mode_id: null
    when: "Passion Exploration is already T20's lightest depth posture."
```

## DEPTH ANALYSIS GUIDANCE

Passion Exploration is generative rather than analytical, so depth here means depth-of-wandering rather than depth-of-investigation. Going deeper means following the user's seed thread through more lateral connections, generating more open questions per surfaced concept, and surfacing more cross-domain echoes. A thin pass produces a single-line response and a few questions; a substantive pass develops at minimum three open questions, two next-directions (one deepening, one lateral), and an exploration map honest to the actual wandering state. Test depth by asking: would the user be surprised by at least one connection or angle the exploration surfaced?

## BREADTH ANALYSIS GUIDANCE

Breadth in Passion Exploration is the catalog of unexpected angles and lateral connections offered. Widen the lens to cross-domain echoes, analogical resonances, and adjacent territories the user has not named. Generate at minimum two next-directions — one deepening (stay in current domain) and one lateral (cross to adjacent domain). Breadth markers: the exploration map fans rather than converges; frontier concepts (those with few outgoing connections) are explicit rather than padded. The mode does NOT optimize for closure — open questions outrank tidy conclusions.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Passion Exploration is the personal-interest position in T20's open-exploration territory — a generative (not analytical) mode for productive wandering when the user has supplied a seed of curiosity but no deliverable, no defined output, no destination. The mode produces an exploration map, open questions, cross-domain echoes, and next-directions; the wandering IS the product. It is distinct from terrain-mapping (structured orientation when the user is unfamiliar with a domain), project-mode (where a deliverable has been named or directive grammar has appeared), and dialectical-analysis or synthesis (where two developed positions are already in tension). Adversarial strictness is deliberately relaxed: Passion Exploration is navigation, not argument; analytical-mode rules over-apply at their own cost.

**Procedure.**

1. Take the user's seed thread or topic of curiosity as the starting point — accept loose, partial, evolving framing rather than asking for crisp scope.
2. Wander productively from the seed — surface concepts, follow lateral threads, generate cross-domain echoes and analogical resonances.
3. Generate at least three open questions; preserve them as open rather than converging toward conclusions.
4. Offer at least two next-directions — one deepening (stay in the current domain, follow a thread further) and one lateral (cross to an adjacent domain, an unexpected angle).
5. Mark frontier nodes — concepts with few outgoing connections — explicitly rather than smoothing them into apparent completion.
6. Monitor for crystallization signals — defined-deliverable language, scope narrowing, exploratory→directive grammar shift, repeated return to one branch, request for next-actions or outline.
7. Reflect crystallization signals back to the user using the literal phrase "crystallization signal" when present, and offer Project Mode as the sideways-route; when absent, state "no crystallization yet" explicitly.
8. Honour wandering as productive — resist the productivity-trap that treats exploration as inefficient and pushes toward output.

**Goal.** Produce a loose exploration map and questions inventory that honours the user's wandering, preserves open questions as the mode's product, surfaces deepening and lateral next-directions, and reflects crystallization signals when (and only when) the user's language has shifted toward a deliverable.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — open questions preserved.** Have at least three open questions emerged and remained open, rather than being closed prematurely? Failure mode if unmet: `premature-closure`.
- **CQ2 — next-directions offered.** Have at least two next-directions been offered (one deepening, one lateral)? Failure mode if unmet: `lecture-trap`.
- **CQ3 — crystallization monitoring.** Has the mode monitored for crystallization signals (shift to directive language) and reflected them back to the user? Failure mode if unmet: `missed-crystallization`.
- **CQ4 — frontier honesty.** Does the exploration map honestly reflect the wandering state, or has it been over-polished into apparent completion? Failure mode if unmet: `over-polished-map`.

A passing output carries ≥ 3 open questions in prose form, offers ≥ 2 next-directions (one deepening, one lateral), reflects crystallization signals when present (or explicitly notes their absence), and preserves frontier roughness rather than smoothing it into apparent completion. The Premature Closure Trap and Lecture Trap are the load-bearing failures.

**Named failure modes.**

- *premature-closure* — output converges to conclusions rather than maintaining open questions.
- *lecture-trap* — output delivers a monologue or comprehensive briefing rather than exploring; concepts catalogued rather than connected.
- *missed-crystallization* — user's language has shifted to directive ("I want to", "let's build") but the mode continued to explore without reflecting the signal back.
- *over-polished-map* — map is tightly balanced when exploration is still fanning; frontier roughness smoothed away.
- *productivity-trap* — mode treats exploration as inefficient and pushes toward output; the exploration IS the product.

## REVISION GUIDANCE

Revise to add open questions where the draft converged to conclusions. Revise to add lateral next-directions where the draft only deepened. Revise to reflect crystallization signals where the user's language has shifted. Resist revising toward apparent thoroughness — over-polishing the map is itself a failure mode. Resist revising toward closure — the exploration IS the product. If genuinely fewer than three concepts have surfaced, suppress closure rather than padding.

## CONSOLIDATION GUIDANCE

**Note: pipeline architecture applies imperfectly to T20 generative modes.** Passion Exploration is generative rather than analytical (Gear 2 single-pass; no parallel-stream consolidation step typically runs). Where the corpus shape applies — when streams have produced wandering material across turns or threads — organize the consolidated corpus as **a loose-template wandering inventory: surfaced-concept atoms, open-question atoms (preserved open), next-direction atoms (deepening + lateral), frontier-node markers, and crystallization-signal observations**. The atoms are:

1. **Surfaced-concept atoms.** Each atom names one concept the exploration has touched, with its connection back to the user's seed thread. Concepts are atoms, not findings; they remain available for further wandering rather than being closed into conclusions.

2. **Open-question atoms.** Each atom carries an open question generated by the exploration. Premature-closure is the named failure mode the consolidator watches for; corpus that converged to closed conclusions where open questions were the mode's product gets reshaped back to open form. At least three open questions persist.

3. **Cross-domain-echo atoms.** Each atom names an analogical resonance, lateral connection, or cross-domain echo surfaced during wandering. These are operative — they widen the exploration's horizon — not decoration.

4. **Next-direction atoms.** Two minimum: one *deepening* (stay in the current domain, follow a thread further) and one *lateral* (cross to an adjacent domain, an unexpected angle). Lecture-trap is the named failure mode for absence of next-directions.

5. **Frontier-node markers.** Concepts with few outgoing connections — places where the exploration has reached the edge of the user's interest-map. Over-polished-map is the named failure mode; frontier roughness is preserved rather than smoothed into apparent completion.

6. **Potential-project-node atoms — when applicable.** Where crystallization candidates appeared (a specific deliverable shape emerged), the candidate is surfaced as a *potential* project node, not as a closed commitment. Missed-crystallization is the named failure mode; user language shifting to directive grammar (`I want to`, `let's build`) gets reflected back in this atom.

7. **Crystallization-signal observation.** A standing atom: are crystallization signals (defined deliverable in user language, scope narrowing, exploratory→directive grammar shift, repeated return to one branch, request for next-actions or outline) present, absent, or partial? When present, the signal is named verbatim using the phrase `crystallization signal` and a transition to Project Mode is offered; when absent, the corpus says `no crystallization yet` explicitly.

8. **Productivity-trap flag — when applicable.** Where streams treated wandering as inefficient and pushed toward output, the flag is preserved. The exploration *is* the product; productivity-trap reshaping is the consolidator move.

**Mode-specific bloat patterns to cut:**

- **Premature closure** — open questions converted to conclusions; the wandering forced into a verdict.
- **Lecture-trap monologue** — comprehensive briefing rather than wandering; concepts catalogued rather than connected.
- **Over-polished map** — tightly balanced map when the exploration is still fanning; frontier roughness smoothed away.
- **Missed crystallization** — user's directive-grammar shift not reflected back; mode continued to explore when the user signalled they were ready to crystallise.
- **Forced crystallization** — productivity-trap; pushing the exploration to closure that didn't happen.
- **Padded concepts** — concept count inflated to hit verification's `≥3`. If fewer than three concepts genuinely surfaced, the corpus suppresses the map rather than padding.
- **Adversarial-mode shape imposition** — analytical-mode bloat patterns (e.g., evidence audits, dialectical mappings) imposed on generative output. Passion Exploration's analytical strictness is relaxed by design.

**What NOT to collapse:**

- **Open questions themselves** — they're the mode's product, not transitional state. Open questions stay open through any consolidation.
- **Frontier roughness** — the map's loose, fanning state where the exploration is still wandering is itself the finding.
- **The wandering arc** — conversation-history weight is higher than for analytical modes (per RAG profile); the arc of the exploration across turns is part of the signal and is preserved.
- **Stream disagreement about whether crystallization has occurred** — when one stream read the user's language as crystallising and another as still exploring, the ambiguity surfaces in the crystallization-signal observation rather than being resolved by the consolidator.

## VERIFICATION CRITERIA

Verified means: ≥ 3 open questions present in prose; ≥ 2 next-directions present (one deepening, one lateral); crystallization signals either reflected or explicitly noted as absent; map (when emitted) honest to wandering state. The four critical questions are addressed. Silent over-closure during revision is a verification failure. Map suppression is acceptable when fewer than three concepts have genuinely surfaced.

## OUTPUT FORMAT GUIDANCE

**Note: pipeline architecture applies imperfectly to T20 generative modes.** Passion Exploration's deliverable is a **loose exploration map and questions inventory** — generative-shape prose that honours wandering rather than analytical-mode closure. The deliverable preserves open questions as the product and surfaces next-directions without forcing convergence. Place the available atoms into the following sections, in this order:

1. **Exploration map.** Prose (concept map optional, only when ≥ 3 concepts have surfaced). A loose, fanning rendering of the surfaced concepts and the connections between them, in the user's own thread-language as much as possible. The map is *frontier-respecting* — concepts at the edge of the exploration are marked explicitly (`Frontier: [concept] — few connections yet, exploration could continue here`) rather than padded into apparent completion. Tightly balanced maps where exploration is still fanning are reshaped at this layer.

2. **Open questions.** A numbered list. Each: `[N]. **[Open question]** — connection to surfaced concept(s): [...].` Three or more open questions appear. Questions that drifted toward conclusion during consolidation are reshaped back to open form at this layer.

3. **Potential project nodes.** Where crystallization candidates appeared, a bulleted list. Each: `**[Candidate deliverable shape]** — what would crystallise it: [...]. User's directive-grammar signals so far: [quoted or paraphrased].` When no crystallization candidates have appeared, this section states explicitly: `No crystallization yet — exploration remains generative.`

4. **Next directions.** A numbered list with at least two entries:
   - `[1]. **Deepening direction:** [stay in current domain, follow this thread further]. What it would surface: [...].`
   - `[2]. **Lateral direction:** [cross to an adjacent domain, an unexpected angle]. What it would surface: [...].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 4.
- Format is **prose-friendly**, not matrix-structured. Concept maps are optional and emit only when ≥ 3 concepts have surfaced; below threshold, the map is suppressed rather than padded.
- Generative posture is preserved throughout — the deliverable invites further wandering rather than closing the exploration. Analytical-mode shape (evidence audits, dialectical mappings, verdict-style conclusions) is reshaped at this layer.
- When crystallization signals appeared, section 3 reflects them using the literal phrase `crystallization signal` and offers Project Mode as the appropriate sideways-route: `**Crystallization signal detected:** [user language quoted]. If you want to convert this exploration into a specific deliverable, Project Mode is the appropriate transition. You may also keep wandering — the choice is yours.`
- When no crystallization signals appeared, section 3 says so explicitly: `No crystallization yet — exploration remains generative.` This is a first-class outcome; the mode honours aimless wandering as productive.
- Frontier nodes (concepts with few outgoing connections) are marked in section 1 rather than smoothed away. The mode's character preserves frontier roughness.
- Adversarial strictness is **relaxed** at this layer — Passion Exploration is navigation, not argument. Do not over-apply analytical-mode format rules. Premature-closure-trap and lecture-trap are the load-bearing failures to reshape; everything else is held lightly.
- The exploration arc across turns (conversation history) is part of the signal and may surface explicitly in section 1 as `Where the exploration has been: [...]` when the multi-turn shape is itself a finding.

## CRYSTALLIZATION DETECTION

Per Decision M, Crystallization Detection lives within Passion Exploration's spec (and within T20's territory documentation), NOT as a meta-architectural answer-seeking-vs.-question-seeking concept. The territory model and the suffix convention encode the analytical/generative distinction implicitly; Passion Exploration's job is to detect when an exploration has crystallized into a specifiable project and to reflect that signal back to the user.

**Crystallization signals to monitor:**

- A defined deliverable appearing in the user's language ("I want to write", "let's build", "we should produce").
- Scope narrowing — the user starts ruling out branches rather than fanning into them.
- Shift from exploratory grammar ("I wonder", "what about", "could it be") to directive grammar ("I want to", "let's", "I'll").
- A repeated return to one branch — the user keeps coming back to a specific concept across turns.
- The user asks for next-actions or for an outline rather than for more connections.

**Detection-and-reflection protocol:**

When crystallization signals appear, name the signal in prose using the literal phrase "crystallization signal" and offer transition to Project Mode. The user retains discretion — they may want to keep wandering. If signals are absent, state "no crystallization yet" explicitly so the user knows the mode is monitoring.

**What crystallization is NOT:**

- It is NOT the user expressing enthusiasm — enthusiasm without a deliverable is still exploration.
- It is NOT the mode's judgment that the exploration "should" produce something — Passion Exploration honors aimless wandering as productive.
- It is NOT triggered by length — long explorations stay exploratory if no deliverable language emerges.

The Missed-Crystallization Trap is the failure mode for missing the signal; the Productivity Trap is the failure mode for forcing crystallization that hasn't happened.

---

## DEFAULT GEAR

Gear 3

- **Expected Runtime:** ~1min
- **Context Budget:** conversation_history_soft_ceiling=0.5

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `parent`, `child`, `analogous-to`, `requires`, `extends`
**Deprioritize:** `contradicts`, `supersedes`

*Family: orientation-exploration. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
