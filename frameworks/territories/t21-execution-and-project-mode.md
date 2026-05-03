# Framework — Execution and Project Mode

*Self-contained framework for non-analytical execution: Project Mode walks the user through executing a defined project; Structured Output formats material under a structural template. Compiled 2026-05-01.*

---

## Territory Header

- **Territory ID:** T21
- **Name:** Execution / Project Mode (Non-Analytical)
- **Super-cluster:** — (T21 sits outside the analytical routing tree)
- **Characterization:** Operations that execute or format rather than analyze. Project Mode walks the user through executing a defined project; Structured Output formats material under a structural template.
- **Boundary conditions:** Input is a project to execute or material to format. Excludes analytical operations.
- **Primary axis:** Specificity (per execution type).
- **Secondary axes:** None.
- **Coverage status:** Strong.

**Outside-analytical-routing-tree note.** T21 modes carry `suffix_rule: none` (no "— Analysis" suffix per Decision L) because their output is execution or formatting, not analysis. T21 sits outside the analytical routing tree; if analytical work is needed mid-execution, that surfaces as a new top-level routing decision rather than as a within-T21 escalation.

---

## When to use this framework

Use T21 when the user wants execution or formatting rather than analysis. T21 has two modes:
- **`project-mode`** — when the user names a deliverable to produce (build, write, create, draft, design, make).
- **`structured-output`** — when the user wants existing content rendered into a specific format (write this as a report, format as a memo, put in outline form, draft a one-pager).

T21 does NOT do analytical work. If the request matches an analytical mode, the analytical mode is the correct response, not T21 execution. The dispatch-check guard rail in `project-mode` fires before emission: does this request match an analytical mode? If yes, dispatch.

---

## Within-territory disambiguation

```
[Territory identified: execution or formatting, non-analytical]

Q1 (situation): "Are you executing a defined project (walk through the steps),
                  or formatting material under a structural template?"
  ├─ "execute a defined project" → project-mode
  ├─ "format material under a template" → structured-output
  └─ ambiguous → project-mode (the more common path; structured-output is
                  invoked when explicitly formatting)
```

**Default route.** `project-mode` when ambiguous and the input has any project-execution shape; `structured-output` when the input is explicitly material to be formatted.

**Escalation hooks.** None within the analytical routing tree — T21 sits outside it. T21 modes do not escalate into analytical territories; if analytical work is needed, that surfaces as a new top-level routing decision.

---

## Mode entries

### `project-mode` — Project Mode

**Educational name:** project execution mode.

**Suffix.** None (bare name) per Decision L.

**Plain-language description.** Executes a defined project. Receives requirements (deliverable specification, success criteria, scope constraints); produces the deliverable; logs substantive decisions with reasoning; acknowledges limitations and risks. Applies the dispatch-check guard rail before emission: if the request actually matches an analytical mode, dispatching there is the verified-correct response — completing in Project Mode is a failure regardless of deliverable quality. Applies a lightweight paradigm check on constraints that look like unstated assumptions limiting the solution space.

**Critical questions.**
- CQ1: Have all stated requirements been satisfied in the deliverable?
- CQ2: Is the deliverable scoped to what was requested, or has it expanded beyond?
- CQ3: Does the request actually match an analytical mode, in which case dispatch is the correct response rather than direct Project Mode execution?
- CQ4: Have substantive decisions been logged with reasoning, and have ≥1 limitation or risk been acknowledged?
- CQ5: If a constraint looks like an unstated assumption limiting the solution space, has the lightweight paradigm check been applied?

**Per-pipeline-stage guidance.**
- **Analyst.** Apply dispatch check first; produce deliverable matching request; log substantive decisions; acknowledge ≥1 limitation or risk; apply lightweight paradigm check on constraints.
- **Evaluator.** Verify dispatch-check applied; verify requirements satisfied; verify scope discipline (no silent expansion); verify decisions log substance; verify limitations named.
- **Reviser.** Address unaddressed requirements (or explicitly acknowledge gaps in a Gap report); trim scope where draft expanded beyond requirements; add decisions log substance where trivial; add limitations where missing; resist gold-plating.
- **Verifier.** Confirm three required sections (deliverable, decisions_log, limitations_acknowledged); verify dispatch-check guard rail applied.
- **Consolidator.** Merge as the deliverable plus decisions log and limitations; format follows the deliverable type. When dispatched to an analytical mode, that mode's consolidation governs.

**Source tradition.** de Bono AGO (aims, goals, objectives — for purpose clarification); de Bono FIP (first important priorities — for scope discipline); domain-specific frameworks per deliverable type.

**Lens dependencies.**
- Required: none.
- Optional: debono-ago, debono-fip, domain-specific frameworks per deliverable type.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

### `structured-output` — Structured Output

**Educational name:** structured output formatting.

**Suffix.** None (bare name) per Decision L.

**Plain-language description.** Renders existing content into a specific format. The fidelity invariant is load-bearing: every substantive claim in the output must trace to source content. Gaps between source and requested format are flagged explicitly (Gap report) rather than silently filled. No recommendation or conclusion is added that was not in source — SO renders, does not advise. If source contains visual envelopes, they are preserved byte-equivalent in the output (no schema drift; mode_context preserved from source).

**Critical questions.**
- CQ1: Does every substantive claim in the output trace to source content, or has the rendering introduced new claims?
- CQ2: Has the requested format been followed faithfully, or has format mismatch occurred?
- CQ3: Have gaps between source and format been flagged explicitly, or silently filled?
- CQ4: Has the rendering avoided introducing recommendation or conclusion not in source — SO renders, does not advise?
- CQ5: If source contains visual envelopes, are they preserved byte-equivalent in the output (no schema drift)?

**Per-pipeline-stage guidance.**
- **Analyst.** Render source into requested format; trace every substantive claim to source; flag gaps explicitly in Gap report; preserve visual envelopes byte-equivalent with mode_context preserved.
- **Evaluator.** Verify fidelity (every substantive claim traces to source); verify format followed; verify gaps flagged not silently filled; verify no added recommendation; verify envelope passthrough.
- **Reviser.** Remove substantive claims that do not trace to source; flag gaps that were silently filled; restore visual envelope byte-equivalence where regeneration occurred; preserve mode_context on passthrough envelopes (do NOT rewrite to "structured-output"); resist analytical contribution.
- **Verifier.** Confirm three required sections (formatted_deliverable, gap_report, format_notes); confirm envelope count matches source (if source has N visuals, output has N visuals).
- **Consolidator.** Merge as formatted deliverable plus gap report and format notes; format follows deliverable type; conversation history weight higher than for analytical modes (source content is usually in history).

**Source tradition.** Format-template library (per document type); de Bono AGO (when format selection requires goal clarification).

**Lens dependencies.**
- Required: none.
- Optional: format-template-library (per document type), debono-ago.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

---

## Cross-territory adjacencies

T21 has no cross-territory adjacencies within the analytical routing tree. The modes do not escalate sideways or upward into analytical territories.

The relevant relationship is the **T20 ↔ T21 handoff** (Crystallization Detection per Decision M): when Passion Exploration in T20 detects that an exploration has crystallized into a specifiable project, it hands off to `project-mode` in T21. The handoff is a transition out of generative exploration into execution; the user retains discretion to decline and continue wandering.

The other relevant relationship is the **dispatch-check** in `project-mode`: if the request matches an analytical mode (any of T1-T20), dispatching to that mode is the verified-correct response rather than completing in Project Mode. This is not an escalation hook but a routing-failure check: Project Mode catches misrouted analytical requests and dispatches them to their correct home.

---

## Lens references (Core Structure embedded)

### de Bono AGO — Aims, Goals, Objectives (optional)

**Core Structure.** Edward de Bono's framework for clarifying what is being pursued at three nested levels:
- **Aims** — broad direction or purpose. Why are we doing this at all?
- **Goals** — outcomes that mark substantial progress toward aims. What does success look like?
- **Objectives** — specific, measurable steps that produce goals. What concrete results are we producing?

For Project Mode, AGO supports requirement clarification: when a user names a deliverable, the AGO tool surfaces the underlying purpose (aim) the deliverable serves, the success markers (goals) the deliverable should produce, and the concrete steps (objectives) execution requires. Misalignment among the three levels (objectives that do not produce goals, or goals that do not advance aims) is a primary source of misexecution.

### de Bono FIP — First Important Priorities (optional)

**Core Structure.** Edward de Bono's tool for explicit prioritization. The protocol:
1. Generate all candidate priorities (the full set of things that could matter).
2. Apply explicit filters to narrow to "first important" priorities — typically 3-5 items.
3. Treat the rest as deferrable, even if individually valuable.

For Project Mode, FIP supports scope discipline: when a deliverable's scope risks expanding beyond the user's stated requirements, FIP names which priorities are first-and-important (in scope) vs. valuable-but-deferred (suggested as separate scope additions, not silently included). The discipline guards against gold-plating and scope-creep.

### Format-Template Library (optional, per document type)

**Core Structure.** A library of conventional formats with their structural elements, organization conventions, and tone defaults:
- **Memo** — header (To, From, Date, Re); brief situation; key points; recommendation or request; supporting detail.
- **Report** — executive summary; introduction; body sections; conclusion; appendices.
- **One-pager** — single page; headline; problem; solution; key data; ask.
- **Comparison table** — rows are options or items; columns are dimensions; cells are values.
- **Outline** — hierarchical bullet structure with consistent depth conventions.
- **Letterhead / Brief / Press release / Case study / Email** — each with its own structural conventions.

For Structured Output, the format-template library provides the conventions that the rendering follows. Format adaptations (when source does not cleanly fit) are surfaced in format notes; they are not silently performed.

---

## Open debates

T21 carries no territory-level open debates. As an execution territory outside the analytical routing tree, mode-level debates do not currently apply.

---

## Citations and source-tradition attributions

- de Bono, E. (1982). *de Bono's Thinking Course*. BBC Books. AGO and FIP tools.
- de Bono, E. (1992). *Serious Creativity*. HarperBusiness. Companion treatment.
- Format-template tradition (organizational and journalistic conventions; no single canonical source).
- Kahneman, D. & Tversky, A. (Various). Heuristics-and-biases catalog (foundational substrate).

*End of Framework — Execution and Project Mode.*
