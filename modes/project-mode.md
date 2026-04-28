---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 3
meta_mode: true
---

# MODE: Project Mode

## TRIGGER CONDITIONS

Positive:
1. The user names a specific output: "build", "write", "create", "produce", "draft", "design".
2. The user states requirements, success criteria, scope, or provides specifications.
3. AGO output identifies a defined artefact or answer as the deliverable.

Negative:
- IF the user expresses no deliverable and frames the query as exploration → **Passion Exploration** or **Terrain Mapping**.
- IF requirements explicitly involve questioning a foundational assumption → **Paradigm Suspension** first, then Project Mode.

## EPISTEMOLOGICAL POSTURE

Accept useful conventions without interrogating them unless the solution space appears artificially constrained. Standard frameworks, established methods, and domain conventions are treated as operational tools. This is the conventional analytical mode: paradigm accepted, territory known, task is execution.

A lightweight paradigm check operates: IF an assumption looks like a constraint limiting the solution space unnecessarily, flag it for the user without forcing Paradigm Suspension.

## DEFAULT GEAR

Gear 3. Most project work benefits from sequential adversarial review.

## RAG PROFILE

**Retrieve (prioritise):** sources relevant to the specific deliverable (technical documentation, reference implementations, prior project work, domain standards); practical over theoretical.

**Deprioritise:** sources unrelated to the concrete deliverable.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `requires`, `enables`, `produces`, `precedes`
**Deprioritise:** `analogous-to`, `supersedes`
**Rationale:** Project execution tracks dependencies, enablers, outputs, and sequencing.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The deliverable and its requirements |
| `conversation_rag` | Prior session work on the same project |
| `concept_rag` | Mental models relevant to the deliverable's domain |
| `relationship_rag` | Domain objects linked by `requires`/`precedes` |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat:
1. Identify the requirements — what the user has specified and success criteria.
2. Produce the deliverable that best satisfies all stated requirements.
3. Track decisions with reasoning.

Black Hat:
1. Evaluate the deliverable against stated requirements. Identify gaps.
2. Assess whether assumptions constrain unnecessarily; flag as lightweight paradigm check.
3. Identify ≥ 1 risk or limitation.

### Cascade — what to leave for the evaluator

Project Mode is a **dispatch spec**. Cascade cues depend on whether classification resolves to an analytical mode:

- If an analytical mode fits the request, the classifier re-runs and the analytical mode's cascade subsections govern — do NOT attempt to cascade from Project Mode's universal elements.
- If Project Mode is terminal (pure document production): state requirements verbatim with literal prefix `Requirement N:`; record decisions with literal prefix `Decision N:`; name limitations with literal prefix `Limitation N:`.
- Use the literal phrase "lightweight paradigm check:" when flagging a constraint that looks like an unnecessary assumption. Supports M4.

### Consolidator guidance

Not applicable at this mode's default gear (Gear 3). Project Mode's consolidator behaviour inherits from the dispatched analytical mode when one is active. If Project Mode is terminal and the user forced Gear 4, merge both streams' decisions logs by de-duplicating decision IDs; retain all limitations from both streams.

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. Identify alternatives Depth did not consider.
2. Assess whether the solution space was artificially constrained.
3. Note adjacent opportunities.

Yellow Hat:
1. Identify strongest features of the deliverable.
2. Assess usability as-is.

### Cascade — what to leave for the evaluator

- Identify ≥ 1 strongest feature with the literal prefix `Strength:`.
- Assess usability with the literal phrase "usability:" followed by `as-is` / `minor modifications needed` / `significant rework`.

## EVALUATION CRITERIA

5. **Requirement Satisfaction.** 5=all stated requirements met. 3=one secondary underserved. 1=primary unmet.
6. **Deliverable Usability.** 5=usable as-is. 3=minor modifications needed. 1=significant rework.

### Focus for this mode

A strong Project Mode evaluator prioritises:

1. **Dispatch check first.** If the request matches an analytical mode (DUU, RCA, SD, etc.), dispatch — do NOT evaluate under Project Mode. Surface the mismatch as a mandatory fix: "Request matches <analytical mode>; re-classify rather than treat as Project Mode."
2. **Requirement satisfaction (M1).** All stated requirements in the deliverable.
3. **Decisions log (M2).** ≥ 1 substantive decision recorded.
4. **Limitations (M3).** ≥ 1 risk or limitation named.
5. **Scope discipline (M5).** Deliverable matches request, not a reinterpretation.
6. **Direct-emission discipline (S2b).** If an envelope is emitted from Project Mode terminal (rare), type must be one of `flowchart` / `concept_map` / `pro_con`; `mode_context == "project-mode"`; not another mode's envelope.

No mode-specific short_alt template — inherit from the dispatched analytical mode when applicable.

### Suggestion templates per criterion

- **Dispatch (mode mismatch):** `suggested_change`: "Request matches <analytical mode, e.g. decision-under-uncertainty>. Re-classify rather than treating as Project Mode. Analytical mode's emission contract governs; Project Mode's dispatch rule fires the re-classification."
- **S2b (wrong envelope type in direct emission):** `suggested_change`: "Project Mode direct emission allows only `flowchart` / `concept_map` / `pro_con`. Current envelope type <X> belongs to another mode — dispatch to that mode, or switch type."
- **M1 (requirement not met):** `suggested_change`: "Requirement '<quote>' is not addressed in the deliverable. Add content meeting the requirement, OR explicitly acknowledge the gap in the Gap report with rationale."
- **M2 (decisions log trivial):** `suggested_change`: "Decisions log must include ≥ 1 substantive decision with reasoning. Pure rendering without decisions suggests a Structured Output task — consider re-dispatching."
- **M3 (no limitation):** `suggested_change`: "Add at least one limitation or risk using the literal prefix `Limitation N:` or `Risk N:`."
- **M5 (scope creep):** `suggested_change`: "Deliverable expands beyond stated requirements. Trim to exactly what was requested; propose additional scope as separate suggestions."

### Known failure modes to call out

- **Dispatch-Missed Trap** → open: "Request matches analytical mode <X>; mandate re-classify."
- **Scope Creep Trap** → open: "Deliverable expands beyond requirements."
- **Gold Plating Trap** → surface as SUGGESTED: "Over-engineering — match quality to request."
- **Assumption Lock Trap** → surface as SUGGESTED: "Constraint <X> looks like an unstated assumption; apply lightweight paradigm check."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-PM-1 — Dispatch preservation.** If original classification dispatched to an analytical mode, revised output follows that mode's structural + semantic criteria. Silent reversion to Project-Mode-direct during revision is a FAIL.
- **V-PM-2 — Decisions-log preservation.** ≥ 1 substantive decision still in revised prose.
- **V-PM-3 — Scope-discipline preservation.** Revised deliverable does not expand beyond user's stated requirements without explicit acknowledgement.

## CONTENT CONTRACT

The content contract is defined by the user's stated requirements, not by the mode. Universal elements regardless of deliverable:

1. **The deliverable** — the artefact the user requested.
2. **Decisions log** — key decisions with reasoning.
3. **Limitations acknowledged** — ≥ 1 risk or limitation.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **Dispatch:** apply dispatch template and re-classify.
- **S2b:** apply wrong-envelope-type template.
- **S3 (missing universal elements):** add each of deliverable / decisions log / limitations explicitly.
- **M1 (requirement unmet):** apply requirement template.
- **M2 (decisions log):** apply decisions-log template.
- **M3 (limitation missing):** apply limitation template.
- **M4 (paradigm check):** add the lightweight check with "lightweight paradigm check:" prefix.
- **M5 (scope):** apply scope-discipline template.
- **Analytical-mode inherited criteria:** when dispatched, the analytical mode's reviser guidance governs — this mode's guidance is supplementary.

## EMISSION CONTRACT

**Project Mode is a dispatch spec — its emission behaviour inherits from the underlying analytical mode.**

### Dispatch rule

When Project Mode fires, the classifier re-runs against the analytical-mode set to resolve which emission contract governs. Examples:
- User: "Build me a decision tree for the vendor choice" → dispatches to **Decision Under Uncertainty**; emission contract from that mode applies.
- User: "Write the incident report for last night's outage" → dispatches to **Root Cause Analysis** (for the causal analysis) then **Structured Output** (for the report format); whichever is active governs emission.
- User: "Design a scenario matrix for 2030" → dispatches to **Scenario Planning**.

### Direct-emission fallback

IF no analytical mode fits and Project Mode is the terminal classification (rare — the user is purely producing a document from known content):
- Emit NO `ora-visual` block by default. Prose deliverable.
- Exception: if the user explicitly requests a visual (e.g. "include a flowchart of the deployment pipeline"), emit a single appropriate envelope — `flowchart` for procedural, `concept_map` for conceptual, `pro_con` for argument. `mode_context = "project-mode"`, `canvas_action = "replace"`, `relation_to_prose = "integrated"`.

### What NOT to emit

- Do not emit an envelope type whose success criteria belong to another mode; if the user's request matches an analytical mode, dispatch to that mode.
- Do not emit multiple envelopes — one per turn.
- Do not emit `canvas_action: "annotate"`.

## GUARD RAILS

**Solution Announcement Trigger.** WHEN the deliverable is presented as complete, verify against user's requirements.

**Scope discipline guard rail.** Produce the deliverable the user requested, not what you think they should have requested.

**Continuity guard rail.** Maintain consistency with established decisions from prior sessions.

**Dispatch-check guard rail.** Before emitting an envelope, ask: does this request match an analytical mode? If yes, dispatch.

## SUCCESS CRITERIA

### Structural

- S1: if an analytical mode is dispatched to, its structural criteria apply.
- S2: if direct Project Mode emission:
  - S2a: envelope absence by default; acceptable.
  - S2b: if envelope present (user requested), `type ∈ {"flowchart", "concept_map", "pro_con"}`, `mode_context == "project-mode"`, `canvas_action == "replace"`, `relation_to_prose == "integrated"`, `semantic_description` complete.
- S3: prose contains the three universal elements (deliverable, decisions log, limitations).

### Semantic

- M1: requirements satisfaction — all stated requirements addressed in the deliverable.
- M2: decisions log non-trivial (≥ 1 substantive decision recorded).
- M3: ≥ 1 limitation / risk acknowledged.
- M4: if a lightweight paradigm check surfaced an unnecessary constraint, it is flagged (not silently accepted).
- M5: scope discipline — deliverable matches the request.

### Composite

- C1: universal elements present in prose.
- C2: if dispatched to an analytical mode, that mode's composite criteria apply.

```yaml
success_criteria:
  mode: project-mode
  version: 1
  dispatch_spec: true
  structural:
    - { id: S1, check: dispatch_to_analytical_mode_if_applicable }
    - { id: S2, check: direct_emission_fallback_ok }
    - { id: S3, check: three_universal_elements }
  semantic:
    - { id: M1, check: requirement_satisfaction }
    - { id: M2, check: decisions_log_nontrivial }
    - { id: M3, check: limitation_acknowledged }
    - { id: M4, check: lightweight_paradigm_check }
    - { id: M5, check: scope_discipline }
  composite:
    - { id: C1, check: universal_elements_in_prose }
    - { id: C2, check: dispatch_composite_applies }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8, composite_min_pass: 0.75 }
```

## KNOWN FAILURE MODES

**The Scope Creep Trap.** Deliverable expands beyond requirements. Correction: produce exactly what was requested; propose scope additions explicitly.

**The Gold Plating Trap.** Over-engineering beyond requirements. Correction: match quality to the request.

**The Assumption Lock Trap (inverse of M4).** Accepting a constraint as fixed when it is an unstated assumption. Correction: flag constraints that look unnecessary.

**The Dispatch-Missed Trap.** Emitting in Project Mode when the request matches an analytical mode. Correction: re-route to the analytical mode.

## TOOLS

Tier 1: AGO, CAF, FIP, PMI.
Tier 2: Loads based on deliverable domain.

## TRANSITION SIGNALS

- IF the deliverable reveals a foundational assumption → propose **Paradigm Suspension**.
- IF the deliverable requires choosing between alternatives → propose **Constraint Mapping**, return to Project Mode.
- IF user shifts to exploratory language → propose **Passion Exploration**.
- IF deliverable requires understanding institutional interests → propose **Cui Bono**, return to Project Mode.
