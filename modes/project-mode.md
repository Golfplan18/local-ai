---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-24
meta_mode: true

---

# MODE: Project Mode

```yaml
# 0. IDENTITY
mode_id: project-mode
canonical_name: Project Mode
suffix_rule: none
educational_name: project execution mode

# 1. TERRITORY AND POSITION
territory: T21-execution-project-mode
gradation_position:
  axis: specificity
  value: project-execution
adjacent_modes_in_territory:
  - mode_id: structured-output
    relationship: specificity variant (rendering-only execution; PM thinks, SO renders)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "user names a specific output to produce"
    - "user has stated requirements, success criteria, or scope"
    - "user wants a deliverable, not exploration or analysis"
  prompt_shape_signals:
    - "build"
    - "write"
    - "create"
    - "produce"
    - "draft"
    - "design"
    - "make"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user names a deliverable or specifies an output"
    - "AGO output identifies a defined artefact as the deliverable"
  routes_away_when:
    - "no deliverable stated; framing is exploration" → passion-exploration (T20) or terrain-mapping (T14)
    - "request matches an analytical mode (DUU, RCA, SD, etc.)" → that analytical mode
    - "task is rendering existing content into a format" → structured-output (T21)
    - "requirements involve questioning a foundational assumption" → paradigm-suspension (T9) first, then Project Mode
when_not_to_invoke:
  - "Request matches a specific analytical mode — dispatch to that mode rather than treating as Project Mode"
  - "Task is rendering existing content rather than producing original work — Structured Output is correct"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: constructive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [deliverable_specification, success_criteria, scope_constraints]
    optional: [prior_session_context, established_decisions, domain_standards_to_follow]
    notes: "Applies when user supplies precise requirements with scope and acceptance criteria."
  accessible_mode:
    required: [deliverable_described]
    optional: [context, motivation, audience]
    notes: "Default. Mode infers requirements through clarification when needed."
  detection:
    expert_signals: ["acceptance criteria", "scope", "requirements", "must include", "deliverable"]
    accessible_signals: ["build me", "write me", "can you create", "I need a"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What specifically should the deliverable be — its form, its scope, what it should accomplish?'"
    on_underspecified: "Ask: 'Is this a defined deliverable I should produce (Project Mode), or are you exploring what the deliverable should be (Passion Exploration / Terrain Mapping)?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have all stated requirements been satisfied in the deliverable?"
    failure_mode_if_unmet: requirement-unmet
  - cq_id: CQ2
    question: "Is the deliverable scoped to what was requested, or has it expanded beyond?"
    failure_mode_if_unmet: scope-creep
  - cq_id: CQ3
    question: "Does the request actually match an analytical mode, in which case dispatch is the correct response rather than direct Project Mode execution?"
    failure_mode_if_unmet: dispatch-missed
  - cq_id: CQ4
    question: "Have substantive decisions been logged with reasoning, and have ≥ 1 limitation or risk been acknowledged?"
    failure_mode_if_unmet: decision-and-limitation-omission
  - cq_id: CQ5
    question: "If a constraint looks like an unstated assumption limiting the solution space, has the lightweight paradigm check been applied?"
    failure_mode_if_unmet: assumption-lock

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: dispatch-missed
    detection_signal: "Project Mode is executing what should have been dispatched to a specific analytical mode."
    correction_protocol: re-dispatch (re-classify to the matching analytical mode)
  - name: scope-creep
    detection_signal: "Deliverable expands beyond user's stated requirements without explicit acknowledgement."
    correction_protocol: flag (trim to exactly what was requested; propose additional scope as separate suggestions)
  - name: gold-plating
    detection_signal: "Over-engineering beyond what the request needs."
    correction_protocol: flag (match quality to request)
  - name: assumption-lock
    detection_signal: "A constraint is accepted as fixed when it is actually an unstated assumption limiting the solution space."
    correction_protocol: flag (apply lightweight paradigm check)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - debono-ago (aims, goals, objectives)
    - debono-fip (first important priorities)
    - domain-specific frameworks per deliverable type
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Project Mode is its own depth target for execution; deeper means dispatch to an analytical mode for analysis input."
  sideways:
    target_mode_id: structured-output
    when: "Task is rendering existing content rather than producing original work."
  downward:
    target_mode_id: null
    when: "Project Mode is T21's heavier execution sibling; lighter would be Structured Output."
```

## DEPTH ANALYSIS GUIDANCE

Project Mode is execution-oriented; depth here means the rigor of requirement satisfaction and the substance of the decisions log. Going deeper means tracing each requirement to a specific element of the deliverable, recording each decision with its reasoning, and naming limitations and risks rather than glossing them. A thin pass produces the artefact and stops; a substantive pass cross-checks the artefact against requirements, surfaces decisions that were not in the requirements but had to be made, and names what the deliverable does not address. Test depth by asking: could the user audit the deliverable against the requirements line by line and find each requirement satisfied?

When Project Mode dispatches to an analytical mode (the typical case for analytically-shaped requests), the analytical mode's depth guidance governs — Project Mode's role becomes orchestration rather than direct execution.

## BREADTH ANALYSIS GUIDANCE

Breadth in Project Mode is the survey of alternative approaches considered before committing to the deliverable's form. Widen the lens to consider: alternative formats, alternative scopes, alternative tools, alternative interpretations of the request. Breadth markers: at least one alternative was considered before commitment; the lightweight paradigm check has been applied to constraints that look like unstated assumptions; adjacent opportunities (scope additions the user might want) are surfaced as suggestions, not silently included.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Project Mode is execution-oriented: the user has named a deliverable and Project Mode produces it. The mode's distinctive move is the dispatch-check — when the request actually matches an analytical mode (DUU, RCA, SD, etc.), Project Mode re-routes rather than executing in-mode. It is distinct from structured-output (which renders existing content into a format rather than producing original work) and from passion-exploration / terrain-mapping (which explore an open space generatively rather than producing a defined deliverable).

**Procedure.**

1. Apply the dispatch-check first — if the request matches an analytical mode, re-dispatch rather than executing in Project Mode.
2. Lock the deliverable shape — its form, scope, and acceptance criteria, named explicitly before its content.
3. Apply the lightweight paradigm check — surface constraints that look like unstated assumptions limiting the solution space.
4. Survey alternative approaches (alternative formats, scopes, tools, interpretations) before committing to the chosen path.
5. Produce the deliverable in its native form — memo format for a memo, code for code, outline for an outline; do not impose analytical-mode template shapes.
6. Trace each stated requirement to a specific element of the deliverable; gap-report any unaddressed requirements rather than silently skipping them.
7. Log substantive decisions with alternatives considered and reasoning — entries without reasoning are trivial.
8. Acknowledge at least one limitation or risk — what the deliverable does not address or what could go wrong.
9. Run the scope-discipline check — was there silent expansion beyond the user's stated requirements? Trim back or surface as a separate suggestion.

**Goal.** Produce the user-requested deliverable in its native form, plus three universal accompanying elements (decisions log, limitations, scope-discipline note), with the dispatch-check guard rail honoured when the request actually matches an analytical mode.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — requirement satisfaction.** Have all stated requirements been satisfied in the deliverable? Failure mode if unmet: `requirement-unmet`.
- **CQ2 — scope discipline.** Is the deliverable scoped to what was requested, or has it expanded beyond? Failure mode if unmet: `scope-creep`.
- **CQ3 — dispatch check.** Does the request actually match an analytical mode, in which case dispatch is the correct response rather than direct Project Mode execution? Failure mode if unmet: `dispatch-missed`.
- **CQ4 — decisions and limitations.** Have substantive decisions been logged with reasoning, and ≥1 limitation or risk acknowledged? Failure mode if unmet: `decision-and-limitation-omission`.
- **CQ5 — paradigm check.** If a constraint looks like an unstated assumption limiting the solution space, has the lightweight paradigm check been applied? Failure mode if unmet: `assumption-lock`.

A passing output satisfies all stated requirements, stays scoped to the request, logs at least one substantive decision with reasoning, acknowledges at least one limitation or risk, applies the lightweight paradigm check where constraints look unnecessary, and (when applicable) re-dispatches rather than executing analytical-shaped requests.

**Named failure modes.**

- *dispatch-missed* — Project Mode is executing what should have been dispatched to a specific analytical mode.
- *scope-creep* — deliverable expands beyond user's stated requirements without explicit acknowledgement.
- *gold-plating* — over-engineering beyond what the request needs.
- *assumption-lock* — a constraint is accepted as fixed when it is actually an unstated assumption limiting the solution space.

## REVISION GUIDANCE

Revise to address requirements that are unaddressed (or explicitly acknowledge the gap in a Gap report). Revise to trim scope where the deliverable has expanded beyond requirements. Revise to add the decisions log substance where it is trivial. Revise to add limitations where they are missing. Resist revising toward gold-plating — match quality to request. If revision reveals the request was actually analytical, re-dispatch rather than completing in Project Mode.

## CONSOLIDATION GUIDANCE

**Note: pipeline architecture applies imperfectly to T21 execution modes.** Project Mode is execution-oriented; when the request matches an analytical mode, the dispatch-check fires first and that mode's consolidation governs. Where Project Mode is terminal (direct execution, not orchestration to another mode) and parallel-stream consolidation has run, organize the consolidated corpus as **a deliverable-shape atom set: requirement-satisfaction atoms tracking each stated requirement, decision-log atoms with reasoning, limitation/risk atoms, dispatch-check atom, and alternative-approach atoms preserved from the breadth pass**. The atoms are:

1. **Dispatch-check atom.** The first-fired consolidation move: does this request match an analytical mode? If yes, the corpus surfaces the dispatch and Project Mode's deliverable-production is replaced by a dispatch-recommendation. Dispatch-missed is the named failure mode the consolidator watches for; analytical-shaped requests executed as Project Mode without checking get reshaped.

2. **Deliverable-shape atom.** The form, scope, and acceptance criteria the user named (or that were inferred and confirmed). The deliverable's *shape* — what it is — is named explicitly before its content.

3. **Requirement-satisfaction atoms.** Each atom names: one stated requirement, the element of the deliverable that satisfies it, and any gap. Requirement-unmet is the named failure mode; unaddressed requirements get reshaped or surfaced as explicit gap-report entries.

4. **Decision-log atoms.** Each atom records: a substantive decision that had to be made (because the requirements did not specify it), the alternatives considered, and the reasoning for the chosen path. Decision-and-limitation-omission is the named failure mode; corpora without substantive decisions logged get reshaped.

5. **Limitation and risk atoms.** Each atom names: a limitation of the deliverable or a risk that the deliverable carries. At least one such atom is required.

6. **Scope-discipline check.** A standing atom: did the deliverable expand beyond what the user requested? Scope-creep is the named failure mode; silent expansion gets reshaped (either trim back, or surface as a separate suggestion). Gold-plating is also flagged here: over-engineering beyond what the request needs.

7. **Alternative-approach atoms (from breadth).** Each atom names one alternative format, scope, tool, or interpretation that was considered before committing to the chosen approach. Even when one alternative was chosen, the others survive as breadth-context.

8. **Lightweight paradigm-check atom — when applicable.** Where a constraint looked like an unstated assumption limiting the solution space, the corpus carries the paradigm-check result. Assumption-lock is the named failure mode.

9. **Confidence per finding.** Each requirement-satisfaction claim and each decision-log entry carries confidence with grounding.

**Mode-specific bloat patterns to cut:**

- **Dispatch-missed** — Project Mode executing what should have been dispatched to an analytical mode. The check fires first.
- **Scope creep** — deliverable expanding beyond stated requirements without acknowledgement.
- **Gold-plating** — over-engineering beyond request needs.
- **Trivial decisions log** — entries without reasoning, or merely restating what the requirements specified rather than capturing substantive choices.
- **Missing limitations** — deliverable presented as if it addressed everything, without naming what it does not.
- **Assumption lock** — constraints accepted as fixed when they are unstated assumptions; lightweight paradigm check not applied.
- **Analytical-mode-shape impositions on rendering tasks** — if the task is rendering existing content into a format, structured-output is the right sideways-route.

**What NOT to collapse:**

- **Alternative-approach atoms** — the considered-and-rejected alternatives are part of the breadth signal; the user may want to see what was weighed before commitment.
- **Limitations and risks** — never smoothed for deliverable polish. The mode's character includes honest acknowledgement of what the deliverable does not address.
- **Stream disagreement about scope** — when streams disagreed on whether a feature falls inside or outside the user's stated scope, the disagreement is preserved as a scope-discipline flag.
- **Dispatch disagreement** — when one stream judged the request analytical-shaped and another judged it execution-shaped, the disagreement surfaces as a dispatch-check entry rather than being silently resolved.

## VERIFICATION CRITERIA

Verified means: deliverable matches request; ≥ 1 substantive decision logged with reasoning; ≥ 1 limitation or risk acknowledged; scope discipline preserved (no silent expansion). The five critical questions are addressed. If the request actually matched an analytical mode, dispatching there is the verified-correct response — completing in Project Mode is a failure regardless of deliverable quality. The dispatch-check guard rail fires before emission: does this request match an analytical mode? If yes, dispatch.

## OUTPUT FORMAT GUIDANCE

**Note: pipeline architecture applies imperfectly to T21 execution modes.** When the dispatch-check fires (request matches an analytical mode), the deliverable is *not* an in-Project-Mode artifact; it is a re-dispatch recommendation. When Project Mode is terminal, the deliverable is **the user-requested artifact plus three universal elements (decisions log, limitations, scope-discipline note)**. The artifact's structure follows the deliverable type (a memo for a memo request, code for a code request, an outline for an outline request — the mode does not impose a structure where the deliverable type has one).

Place the consolidated-corpus atoms into the following sections (or their deliverable-appropriate equivalents):

1. **Deliverable.** The user-requested artifact, in its native form. Structure follows the deliverable type. For a memo: memo format. For code: code format. For an outline: outline format. The mode does not paste analytical-mode shape onto execution outputs.

2. **Decisions log.** A short labelled section after the deliverable. Numbered list. Each: `[N]. **Decision:** [what was chosen]. **Alternatives considered:** [the others]. **Reasoning:** [why this one].` At least one substantive decision appears; trivial entries (restating requirements) are reshaped at this layer.

3. **Limitations acknowledged.** A short labelled section. Bulleted list. Each: `**Limitation N:** [what the deliverable does not address — with reasoning].` or `**Risk N:** [risk the deliverable carries — with reasoning and mitigation hint if known].` At least one entry appears; missing limitations are reshaped to surface what the deliverable does not address.

**Per-section conventions:**

- The deliverable (section 1) follows its native form, not an analytical-mode template. Imposing the 7-section analytical-mode shape on a memo or code request is reshaped at this layer.
- The decisions log (section 2) and limitations (section 3) appear *after* the deliverable, not interleaved. They support audit but do not interrupt the deliverable's natural reading.
- The dispatch-check fires *before* emission. When the request matches an analytical mode, the deliverable is replaced by: `**Note: this request matches an analytical mode ([mode_id]) more directly than Project Mode. Re-dispatching to [mode_id] will produce a more appropriate deliverable than continuing here. The dispatch-check is a guard rail, not a refusal — if you want Project-Mode-shaped execution despite the analytical match, say so explicitly.**`
- When the task is rendering existing content into a format (structured-output territory), the deliverable opens with: `**Note: this task is rendering existing content into a format rather than producing original work; structured-output (T21) is the appropriate sideways-route.**`
- When the scope-discipline check surfaced scope creep, section 3 closes with a labelled `**Scope-discipline note:** [what was trimmed back from the deliverable; what is offered as a separate suggestion if the user wants it].`
- When the lightweight paradigm-check surfaced an unstated assumption limiting the solution space, section 2 closes with a labelled `**Paradigm-check note:** [constraint that may be unnecessary; alternative solution-space if the constraint is relaxed].`
- Limitations and risks (section 3) use the literal prefixes `**Limitation N:**` or `**Risk N:**` for audit traceability.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- AGO
- APC
- FIP
- CAF
- C&S

Mental models (always loaded):
- ooda-loop
- first-principles
- satisficing
- leverage
- bottlenecks
- klein-pre-mortem
- decision-trees

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[framework, mode, engram]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `requires`, `enables`, `parent`, `child`, `produces`
**Deprioritize:** `analogous-to`, `contradicts`

*Family: execution-output. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
