---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
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
output_contract:
  artifact_type: synthesis
  required_sections:
    - exploration_map
    - open_questions
    - potential_project_nodes
    - next_directions
  format: prose

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

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing Passion Exploration output (a) carries ≥ 3 open questions; (b) offers ≥ 2 next-directions; (c) reflects crystallization signals when present (or explicitly notes their absence); (d) preserves frontier roughness rather than over-polishing the map. Adversarial strictness is **relaxed** for this mode — Passion Exploration is navigation, not argument; do not over-apply analytical-mode rules. The Premature Closure Trap and Lecture Trap are the load-bearing failures.

## REVISION GUIDANCE

Revise to add open questions where the draft converged to conclusions. Revise to add lateral next-directions where the draft only deepened. Revise to reflect crystallization signals where the user's language has shifted. Resist revising toward apparent thoroughness — over-polishing the map is itself a failure mode. Resist revising toward closure — the exploration IS the product. If genuinely fewer than three concepts have surfaced, suppress closure rather than padding.

## CONSOLIDATION GUIDANCE

Consolidate as prose with the four required sections. The exploration map is loose and frontier-respecting (not tightly balanced). Open questions are numbered and tied to surfaced concepts. Next-directions are numbered (one deepening, one lateral minimum). Potential project nodes are surfaced when crystallization candidates appear, but not forced. Format is prose-friendly (concept maps are optional and emit only when ≥ 3 concepts have surfaced). Conversation history weight is higher than for analytical modes — the arc of wandering is part of the signal.

## VERIFICATION CRITERIA

Verified means: ≥ 3 open questions present in prose; ≥ 2 next-directions present (one deepening, one lateral); crystallization signals either reflected or explicitly noted as absent; map (when emitted) honest to wandering state. The four critical questions are addressed. Silent over-closure during revision is a verification failure. Map suppression is acceptable when fewer than three concepts have genuinely surfaced.

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
