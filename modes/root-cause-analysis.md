---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 1
---

# MODE: Root Cause Analysis

## TRIGGER CONDITIONS

Positive (fire the mode):
1. Something has gone wrong and the cause is unclear.
2. A problem has recurred despite one or more attempted fixes.
3. The user frames the presented issue as a symptom rather than the real problem.
4. Diagnostic investigation is required before any solution can be designed.
5. Fishbone-shaped request language: "what are the root causes of…", "why does this keep happening", "draw a fishbone for…", "give me an Ishikawa of…", "what's the real problem here", "we've tried X but it didn't work".

Negative (route elsewhere):
- IF the user wants to map an ongoing system's feedback structure without a specific failure to trace → **Systems Dynamics**.
- IF the user wants to choose between solutions and the diagnosis is settled → **Constraint Mapping** or **Decision Under Uncertainty**.
- IF the user wants to explore unfamiliar territory rather than diagnose a failure in familiar territory → **Terrain Mapping**.
- IF the user's question is forward-looking ("what could go wrong if we ship X") rather than backward-looking ("why did X fail") → **Consequences and Sequel**.
- IF the user wants the strongest version of an argument for or against a position → **Steelman Construction**.

Tiebreakers:
- RCA vs Systems Dynamics: **specific failure chain** → RCA; **ongoing feedback-driven behaviour** → SD.
- RCA vs Competing Hypotheses: **diagnosing one symptom's causes** → RCA; **choosing between multiple explanations under ambiguous evidence** → CH.
- RCA vs Spatial Reasoning: **user asks for causes via text** → RCA; **user has drawn a structure and asks what's missing** → SR.

## EPISTEMOLOGICAL POSTURE

The surface problem is a symptom, not the disease. First-order explanations are inherently suspect. Evidence is followed backward through causal chains. Expert opinion about "the problem" is questioned — direct observation is favoured over executive assumptions. Each potential cause is treated as a hypothesis to be tested. The method investigates the process, not the people — "human error" is never accepted as a root cause. Behind every human error is a process failure that permitted or incentivised it.

## DEFAULT GEAR

Gear 3. Root cause investigation is inherently sequential — each level of cause reveals the next. The Depth model traces the causal chain; the Breadth model challenges whether each causal link is genuine and whether alternative chains exist. Independence is less critical than rigorous chain-testing. Gear 2 for a quick 5-Whys sketch when the user explicitly asks for a lightweight pass. Gear 4 when competing causal chains need to be analysed independently and contrasted.

## RAG PROFILE

**Retrieve (prioritise):** domain-specific failure analysis, incident reports, process documentation, prior analyses of similar failures; RCA methodology references (5 Whys, Ishikawa/fishbone frameworks — 6M / 4P / 4S / 8P, fault tree analysis, FMEA); known common failure patterns in the relevant domain.

**Deprioritise:** solution-oriented sources, vendor promotional material, and design-pattern catalogues until the diagnosis is complete.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `causes`, `enables`, `requires`, `produces`, `precedes`, `derived-from`
**Deprioritise:** `analogous-to`, `supersedes`, `parent`, `child`
**Rationale:** Root cause tracing follows causal chains — what causes what, what enables what, what produces what, what requires what. Analogies and part-whole structure are distractors at diagnosis time.


### RAG PROFILE — INPUT SPEC (context-package fields consumed)

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The stated symptom and any prior-fix history |
| `conversation_rag` | Prior turn's causal hypotheses; refutations; user-confirmed evidence |
| `concept_rag` | Mental models — 5 Whys, Ishikawa, FMEA, blameless post-mortem |
| `relationship_rag` | Domain objects already linked by `causes` / `enables` / `requires` |
| `prior_spatial_representation` | Any fishbone or CLD the user drew in a previous turn; preserve framework and category names |
| `spatial_representation` | User's current drawing (entities / relationships) that should ground the diagnosis |
| `annotations` | User callouts targeting specific causes ("I've already ruled this out"; "I suspect this") |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

*Token measurements to be calibrated during Phase 8E testing.*

## DEPTH MODEL INSTRUCTIONS

White Hat directives:
1. State the presented problem — the observable symptom or failure. Document it precisely: what happened, when, where, and what the observable evidence is. **This exact phrasing becomes `spec.effect` in the emitted envelope.**
2. Declare the categorisation framework you will use (6M / 4P / 4S / 8P / custom). State the rationale — why this framework fits this failure. **This framework becomes `spec.framework` and governs category names in the envelope.**
3. For each proposed cause, ask: what caused this cause? Continue for at minimum two levels of depth on at least one branch (the envelope's `sub_causes` nesting must reach ≥2 somewhere). At each level, distinguish the causal claim from the evidence supporting it.
4. Distinguish root causes from contributing factors. A root cause is one whose removal would prevent recurrence. A contributing factor increases probability but does not independently cause the failure.

Black Hat directives:
1. For each causal link in the chain, assess: is this causation or correlation? What evidence distinguishes them?
2. Challenge any point where the chain terminates at "human error," "bad judgment," or "insufficient effort." Ask: what process permitted this error? What system incentivised this judgment? Record the deeper process cause as a `sub_cause` rather than as the leaf.
3. Assess whether the chain has stopped too early — whether the identified "root cause" is actually an intermediate cause with deeper causes beneath it.

### Cascade — what to leave for the evaluator

Explicit structural cues the Depth analyst must leave so the evaluator can mechanically verify the success criteria:

- State the declared framework (`6M` / `4P` / `4S` / `8P` / `custom`) in the first sentence of the "Chosen framework" paragraph. Exact string match against `spec.framework` satisfies C1.
- State the presented problem as the first-sentence noun phrase of the "Presented problem" paragraph, phrased so it can be used verbatim as `spec.effect`. Lexical overlap ≥ 0.7 satisfies C2.
- Open each category-analysis paragraph with the canonical category name exactly as it will appear in `spec.categories[].name`. Supports C3 and S11.
- Prefix each identified root cause in the "Root cause(s)" paragraph with the literal string `Root Cause:`. Enables C4 trace from prose to envelope leaves.
- Use the literal phrase "correlation vs causation" somewhere in the "Evidence assessment" paragraph for at least one link. Substring search satisfies M5.
- For the branch that reaches `sub_cause` depth 2, ensure the sub-cause noun phrase is lexically distinct from the parent. Supports M3 (non-trivial chain).

### Consolidator guidance

Not applicable at this mode's default gear (Gear 3). If promoted to Gear 4 by user override — typically when competing causal chains need independent investigation — use the Depth stream's framework declaration as the reference frame for the envelope. Present the Breadth stream's alternative chains as a dedicated "Alternative causal framings" prose section; the envelope emits only the dominant chain.

## BREADTH MODEL INSTRUCTIONS

Green Hat directives:
1. Generate alternative causal chains for the same symptom. The first chain identified is not necessarily the correct one. Require at minimum two alternative chains emerge from the deliberation, even if only one ships in the final emission.
2. Identify contributing factors that interact with the primary chain — conditions that are not root causes alone but amplify the root cause's effect. These either become additional categories or get recorded as contributing-factor annotations in the prose (not as mis-classified root-cause leaves).
3. Map the full causal structure: IF multiple chains converge on the same symptom, the actual cause may be their interaction. IF that interaction contains a feedback loop, prefer `causal_loop_diagram` as the emission type (see EMISSION CONTRACT).

Yellow Hat directives:
1. For each identified root cause, assess what the user gains from knowing it — is it actionable? Can the root cause be addressed, or is it a fixed constraint? Flag any leaf cause that is not actionable for the user's role.
2. Identify preventive measures — changes that would prevent recurrence by addressing the root cause rather than managing the symptom.
3. Distinguish between corrective actions (fix the current instance) and preventive actions (prevent future instances). Both are needed; they serve different purposes.

### Cascade — what to leave for the evaluator

Explicit structural cues the Breadth analyst must leave so the evaluator can mechanically verify:

- Number alternative causal chains explicitly (`Chain 1:`, `Chain 2:`) in prose. Supports the ≥ 2 alternatives floor.
- Use the literal phrases `contributing factor` and `root cause` when drawing the distinction. Supports M2 and evaluation rubric #6.
- Use the literal phrases `corrective action` and `preventive action` in the "Recommendations" paragraph so both are demonstrably addressed.
- Mark any non-actionable leaf with the suffix `[non-actionable for this role]`. Supports M2.

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Causal Depth.** 5=at minimum three levels of causal analysis with each level genuinely deeper than the previous. 3=two levels of genuine depth. 1=analysis stays at symptom level or accepts first-order explanations.
6. **Root vs. Contributing Distinction.** 5=root causes cleanly distinguished from contributing factors with explicit reasoning. 3=distinction drawn but one contributing factor classified as a root cause. 1=no distinction made.
7. **Evidence per Link.** 5=every causal link supported by evidence, with causation-versus-correlation assessed for each. 3=most links supported but one link assumed without evidence. 1=causal chain asserted without evidence at multiple points.
8. **Framework Coherence.** 5=declared framework (6M/4P/4S/8P/custom) is used consistently; every category's inclusion is justified by a cause that belongs in that category. 3=framework declared but one category is a poor fit or ornamental. 1=framework is post-hoc, categories are mixed from different frameworks, or causes routinely cross categories.

### Focus for this mode

A strong RCA evaluator prioritises in this order:

1. **Framework coherence first (C1, S7, S11).** Ad-hoc framework or non-canonical category names within a declared canonical framework invalidate everything downstream — mandate before any semantic critique.
2. **Effect phrasing (S6).** Solution-verb-prefixed effects invalidate the fishbone.
3. **Depth floor (S10).** At least one branch must reach `sub_cause` depth 2; a flat fishbone is diagnostically useless.
4. **Process-not-people terminal (M4).** A leaf at "human error" without a process sub-cause is a mandatory fix, not a suggestion — this is RCA's load-bearing epistemic commitment.
5. **Short_alt discipline (S12).** RCA's fishbone `short_alt` must be ≤ 150 chars; target ≤ 100. See Suggestion Templates below.

### Suggestion templates per criterion

Use verbatim in SUGGESTED IMPROVEMENTS output when the named criterion fails or is weak.

- **S12 (short_alt length):** `suggested_change`: "Rewrite short_alt as: 'Fishbone of <short noun phrase ≤ 60 chars>.' Do not enumerate categories, causes, or frameworks inside short_alt — that belongs in level_1_elemental. Target ≤ 100 chars." `reasoning`: "Hard 150-char cap enforced by validator; Phase 4 Tier A identified this as the dominant failure." `criterion_it_would_move`: `S12`.
- **S11 (non-canonical category name):** `suggested_change`: "Rename category '<current>' to canonical '<suggested>' from the declared framework's set, OR switch framework to one whose canonical set fits, OR declare 'custom' and justify in prose." `criterion_it_would_move`: `S11`.
- **M3 (trivial sub-cause paraphrase):** `suggested_change`: "Rewrite sub-cause '<current>' to name a specific process, policy, resource, or incentive one causal step deeper than the parent. The sub-cause must not reuse the parent's noun phrase." `criterion_it_would_move`: `M3`.
- **M4 (human-error terminal):** `suggested_change`: "Add a sub-cause to '<human error leaf>' naming the process that permitted or incentivised the error. Template: '<process name> did not <required check>' or '<policy name> permitted <specific condition>'." `criterion_it_would_move`: `M4`.
- **C2 (effect-prose-envelope disagreement):** `suggested_change`: "Align the 'Presented problem' paragraph's first sentence with `spec.effect` verbatim, or update `spec.effect` to match the prose — pick one canonical phrasing." `criterion_it_would_move`: `C2`.

### Known failure modes to call out

Dispatch rule: when the analyst's output shows any of these patterns, open the evaluator output by naming the failure mode before listing individual findings.

- **Human Error Trap** → open: "The analysis terminates at human error on branch X; per the Process-not-people guard, this is a mandatory fix." List the specific leaf and the required sub-cause template.
- **Ad-hoc Framework Trap** → open: "No framework was declared before categories were named; this invalidates C1 and S7." Mandate framework declaration as the first fix.
- **Restatement Trap** → open: "Cause X paraphrases the effect — it is not a cause." Mandate deletion or one-level-deeper rewrite.
- **Type-Switch Trap** → open: "A `causal_loop_diagram` was emitted but no feedback loop is articulated in prose." Mandate revert to `fishbone` or articulate the loop in prose.
- **Linear Chain Trap** → surface as SUGGESTED IMPROVEMENT (not mandatory — the mode permits one primary chain): "Generate at minimum two alternative causal chains in prose before committing to the dominant chain."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-RCA-1 — Framework persistence.** `spec.framework` in the revised envelope equals the framework named in the revised prose's "Chosen framework" paragraph. Silent drift between draft and revision is a FAIL.
- **V-RCA-2 — Root-cause envelope traceability.** Every root cause identified in the revised prose's "Root cause(s)" paragraph appears as a leaf `cause.text` or `sub_cause.text` in the revised envelope.
- **V-RCA-3 — Sub-cause depth preservation.** If the original envelope had `sub_cause` depth ≥ 2 and the reviser reduced it to < 2, the depth floor regressed — FAIL unless the reviser's CHANGELOG names the reduction with explicit justification.
- **V-RCA-4 — Canonical-names preservation.** If `spec.framework != "custom"`, every `spec.categories[].name` is in the framework's canonical set. Silent introduction of a non-canonical name during revision is a FAIL.

## CONTENT CONTRACT

The prose is complete when it contains, in order:

1. **Presented problem** — one short paragraph stating the observable symptom precisely. The first-sentence noun phrase must be usable verbatim as the envelope's `spec.effect`. Do not phrase as a solution ("increase reliability"); phrase as a problem ("deployments fail intermittently").
2. **Chosen framework and rationale** — name the Ishikawa framework (6M / 4P / 4S / 8P / custom), state in one sentence why this framework fits the failure domain, and list the categories you will use. If framework is `custom`, justify why none of the canonical frameworks fit.
3. **Category analysis** — for each category you include in the envelope, one paragraph stating: (a) the category name, (b) at least one concrete cause that sits in that category, (c) for at least one branch, a sub-cause that goes one level deeper. Do not include a category with no causes.
4. **Root cause(s)** — explicit identification of which leaf nodes in the fishbone are root causes (intervention here prevents recurrence) vs contributing factors (intervention here reduces probability but does not prevent). At least one root cause must be identified.
5. **Evidence assessment** — for each causal link, the evidence supporting causation and any ambiguity between causation and correlation. Cite specific signals, not general plausibility.
6. **Recommendations** — actionable interventions targeting the identified root causes. Distinguish corrective actions (fix the current instance) from preventive actions (prevent future instances).
7. **Confidence and alternative framings** — one short paragraph stating (a) how confident you are in the dominant chain (low / moderate / high) and why, and (b) at least one alternative causal framing that was considered and why it was deprioritised.

After your analysis, emit exactly one fenced `ora-visual` block conforming to the EMISSION CONTRACT below as the final block of the response.

### Reviser guidance per criterion

When the evaluator's output mandates a fix against the named criterion, address as follows:

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S1 (envelope absent):** append the envelope as the final block of the response. S1 is a format failure, not a content failure — do not change prose.
- **S2 (schema invalid):** read the first `E_*` error code in the evaluator's `what's_wrong`. Most common: `E_SCHEMA_INVALID` driven by `short_alt > 150 chars` — apply the S12 suggestion template. If `E_GRAPH_CYCLE`, the envelope type is wrong — revert to `fishbone` and move any loop content into prose.
- **S6 (solution-phrased effect):** rephrase `spec.effect` to start with the observed failure's noun phrase, not a solution verb; update the "Presented problem" paragraph in lockstep to preserve C2.
- **S7 (framework not declared):** name the framework in the first sentence of the "Chosen framework" paragraph; set `spec.framework` to the same string. Pick whichever framework fits the most causes you already have.
- **S8 (fewer than three categories):** either find causes for a third canonical category OR switch to `framework: "custom"` with three declared custom categories, each justified in prose.
- **S10 (depth floor):** deepen at least one branch by adding a sub-cause that names the process or incentive behind the parent cause.
- **S11 (non-canonical category name):** apply the S11 suggestion template.
- **S12 (short_alt over 150 chars):** apply the S12 suggestion template verbatim — this is the dominant Phase 4 Tier A failure.
- **M1 (MECE):** if a cause belongs equally in two categories, keep it in the one where the root-cause intervention sits; delete from the other.
- **M2 (non-actionable leaf):** rewrite the leaf to name a process, policy, resource, signal, or incentive that can be changed.
- **M3 (trivial paraphrase):** apply the M3 suggestion template.
- **M4 (human-error terminal):** apply the M4 suggestion template.
- **M5 (correlation-causation not addressed):** add one sentence to the "Evidence assessment" paragraph explicitly distinguishing correlation from causation on at least one link.
- **C1-C4 (prose-envelope disagreement):** update whichever side is wrong. If both read differently but neither is wrong, pick one canonical phrasing and update the other.

## EMISSION CONTRACT

Root Cause Analysis produces a response containing BOTH prose (the seven content-contract sections above) AND exactly one fenced `ora-visual` block. The prose arrives first; the envelope is the final block of the response.

### Envelope type selection

- **Default: `fishbone`.** Use for almost all RCA turns.
- **Only switch to `causal_loop_diagram` when the causal analysis contains at least one genuine feedback loop** (A worsens B which worsens A, possibly via intermediaries). The loop must have been articulated in the prose; do not switch types merely because the domain "feels systemic." When in doubt, stay with `fishbone` — RCA is a decomposition task, not a feedback-loop discovery task.

### Canonical envelope (fishbone)

```ora-visual
{
  "schema_version": "0.2",
  "id": "rca-fig-1",
  "type": "fishbone",
  "mode_context": "root-cause-analysis",
  "relation_to_prose": "integrated",
  "title": "Root causes of intermittent deployment failures",
  "canvas_action": "replace",
  "spec": {
    "effect": "Deployments fail intermittently in production",
    "framework": "6M",
    "categories": [
      {
        "name": "Method",
        "causes": [
          {
            "text": "No canary stage in the deployment pipeline",
            "sub_causes": [
              { "text": "Pipeline simplified for throughput during Q2 cost-cutting" }
            ]
          },
          { "text": "Rollback criteria are not declared before a release" }
        ]
      },
      {
        "name": "Machine",
        "causes": [
          {
            "text": "Build server runs with insufficient memory headroom",
            "sub_causes": [
              { "text": "Concurrency raised without resizing the instance" }
            ]
          }
        ]
      },
      {
        "name": "Measurement",
        "causes": [
          { "text": "Production error-rate alerting threshold hides short spikes" }
        ]
      }
    ]
  },
  "semantic_description": {
    "level_1_elemental": "Fishbone with three 6M categories (Method, Machine, Measurement) and five leaf causes; two branches reach sub-cause depth 2.",
    "level_2_statistical": "Method holds the most causes (two leaves plus one sub-cause); Machine has one leaf with one sub-cause; Measurement has one leaf.",
    "level_3_perceptual": "Causes cluster in Method and Machine (procedural + infrastructural); diagnosis points at process and capacity, not people or materials.",
    "short_alt": "Fishbone of deployment failures across Method, Machine, and Measurement categories."
  }
}
```

### Emission rules (fishbone)

1. **`type` must be `"fishbone"`** unless a declared feedback loop forces `"causal_loop_diagram"`.
2. **`mode_context` must be `"root-cause-analysis"`** (hyphens, not underscores).
3. **`relation_to_prose` must be `"integrated"`** — the visual summarises the prose diagnosis, not a standalone deliverable.
4. **`canvas_action` must be `"replace"`** — RCA renders fresh; it does not overlay user-drawn content.
5. **`spec.effect` must name a problem**, not a solution. Do not start with "increase", "reduce", "implement", "adopt", "deploy", or "improve" — the validator emits `W_EFFECT_SOLUTION_PHRASED` and adversarial review escalates.
6. **`spec.framework` must be one of `6M`, `4P`, `4S`, `8P`, or `custom`** and must match the framework the prose declared.
7. **If `framework` is not `custom`, `spec.categories[].name` must match exactly one canonical string** for that framework — no combined forms (never `"Milieu/Environment"`), no aliases, no pluralisation, no adjectives. Pick one. The validator rejects non-canonical names.
   - **6M:** `Man`, `Machine`, `Method`, `Material`, `Measurement`, `Milieu`, `Mother Nature`, `Environment` — `Milieu` and `Environment` are alternative names for the same spine; choose one.
   - **4P:** `People`, `Process`, `Policy`, `Plant`
   - **4S:** `Surroundings`, `Suppliers`, `Systems`, `Skills`
   - **8P:** `Product`, `Price`, `Place`, `Promotion`, `People`, `Process`, `Physical Evidence`, `Productivity`
8. **`spec.categories` must have at least three entries**, each with at least one cause. Do not emit empty categories.
9. **At least one cause branch must reach `sub_causes` depth 2** (`cause → sub_cause`). Fishbone depth is capped at 3 — the validator rejects depth > 3.
10. **Every `cause.text` and `sub_cause.text` must be non-empty and must not restate the effect.** If a cause reads as a paraphrase of `spec.effect`, it is not a cause — delete or refine.
11. **`semantic_description` must include all four required fields** (`level_1_elemental`, `level_2_statistical`, `level_3_perceptual`, `short_alt`) with non-empty strings. **`short_alt` has a HARD 150-character maximum enforced by the validator** — the envelope is rejected with `E_SCHEMA_INVALID` if this is exceeded. Aim for ≤100 characters. Write it in Cesal form — `"[chart type] of [subject]."` — and do NOT enumerate every category, every cause, or every framework option inside it. That is what `level_1_elemental` is for. Good: `"Fishbone of intermittent deployment failures."` (45 chars). Bad: `"Fishbone of intermittent software deployment failures across Method, Machine, Material, Measurement, Milieu, and Man categories highlighting procedural, infrastructural and human factors."` (185 chars — rejected).
12. **`id` must be unique within the response.** If more than one figure is ever needed, increment the suffix (`rca-fig-2`) — but the one-envelope rule (13) forbids this in a single turn.
13. **Emit no second `ora-visual` block.** One envelope per turn.

### Emission rules (causal_loop_diagram — secondary)

When a feedback loop is articulated in the prose, switch to `type: "causal_loop_diagram"` with:

- `spec.variables` — every noun in the loop, minimum four entries, each with an `id` and a `label`.
- `spec.links` — every directed cause-with-sign between the variables, polarity `+` or `-`.
- `spec.loops` — each declared loop with `id` (e.g. `R1` or `B1`), `type` (`R` / `B`), ordered `members` list of variable ids traversed, and a short `label`.
- The loop's declared type must match the parity of `-` edges on its members (even → R, odd → B); the validator enforces this via `E_GRAPH_CYCLE`.
- `mode_context` and `relation_to_prose` same as fishbone.

### What NOT to emit

- **Do not** emit `canvas_action: "annotate"` — that is Spatial Reasoning's mode.
- **Do not** invent category names outside the declared framework's canonical set.
- **Do not** classify contributing factors as root-cause leaves in the envelope; record contributing factors in the prose only.
- **Do not** emit a fishbone with two or fewer categories; if only two branches of causes exist, stay with 5 Whys prose and suppress the envelope.
- **Do not** emit a CLD for non-feedback decomposition — the fishbone IS the right shape when causes don't loop back.
- **Do not** terminate a leaf at "human error" without a process sub-cause beneath it.

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN the analysis moves toward proposing solutions, THEN verify: has the root cause been identified, or is the solution targeting a symptom? Solutions proposed before root cause identification are symptom management.

**Diagnosis-before-prescription guard rail.** Complete the causal analysis before proposing solutions. IF the user presses for solutions before diagnosis is complete, state what is known and unknown, propose provisional measures, and continue diagnosis.

**Process-not-people guard rail.** Do not terminate causal chains at individual actors. Investigate the process, system, or incentive structure that produced the behaviour. In envelope terms: a leaf naming a person is a signal to add a `sub_cause` that names the process that permitted or incentivised the behaviour.

**No-restatement guard rail.** WHEN authoring a cause that rephrases the effect (e.g. effect "deployments fail intermittently" → cause "deployments are unreliable"), THEN delete the cause and write a cause one level deeper. Restatements are not causes.

**Framework-first guard rail.** WHEN categories get named before a framework is declared, THEN stop and declare a framework first. Ad-hoc categories produce non-MECE fishbones. `custom` is a valid choice — but `custom` must still be declared, and its categories justified.

**One-envelope guard rail.** Emit exactly one `ora-visual` fence per turn. If the analysis is incomplete, emit no envelope and continue the diagnosis in the next turn.

**Effect-phrasing guard rail.** WHEN writing `spec.effect`, THEN express it as an observed problem, not as a target state. `"Deployments fail intermittently"` — yes. `"Improve deployment reliability"` — no.

## SUCCESS CRITERIA

A Root Cause Analysis turn succeeds when all structural, semantic, and composite criteria below are met. Structural checks are machine-verifiable against the emitted envelope. Semantic checks are LLM-reviewer verifiable against the prose + envelope together. Composite checks compare prose and envelope for agreement.

### Structural (machine-checkable)

- **S1 — Envelope presence.** Exactly one fenced `ora-visual` block appears in the response, parseable as JSON.
- **S2 — Schema validity.** The envelope passes `visual_validator.validate_envelope` with zero errors.
- **S3 — Mode-correct type.** `envelope.type ∈ {"fishbone", "causal_loop_diagram"}`.
- **S4 — Mode context.** `envelope.mode_context == "root-cause-analysis"`.
- **S5 — Canvas action.** `envelope.canvas_action == "replace"`.
- **S6 — Effect phrasing.** `spec.effect` is non-empty and does NOT start with a solution verb (`increase`, `reduce`, `implement`, `adopt`, `deploy`, `improve`). Equivalent to `W_EFFECT_SOLUTION_PHRASED` absent.
- **S7 — Framework declared.** `spec.framework ∈ {"6M", "4P", "4S", "8P", "custom"}` (fishbone only).
- **S8 — Category count.** `len(spec.categories) ≥ 3` (fishbone only).
- **S9 — Non-empty causes.** Every category has `len(causes) ≥ 1` and every `cause.text` is a non-empty string.
- **S10 — Depth floor.** At least one branch reaches `sub_causes` depth 2 (cause → sub_cause) for fishbone; for CLD, at least one declared loop with `len(members) ≥ 2`.
- **S11 — Canonical category names.** If `framework != "custom"`, every category name is in the framework's canonical set.
- **S12 — Semantic description complete.** `level_1_elemental`, `level_2_statistical`, `level_3_perceptual`, and `short_alt` are all non-empty strings.

### Semantic (LLM-reviewer)

- **M1 — MECE categories.** Within the declared framework, categories are mutually exclusive (no cause belongs equally to two) and collectively exhaustive for the failure domain (no obvious additional-category cause is being forced into an unrelated category).
- **M2 — Actionable leaves.** Every leaf cause names a process, policy, resource, signal, or incentive that could plausibly be changed. Leaves that are pure attributions ("people didn't care enough") fail this check.
- **M3 — Non-trivial chain.** At least one branch contains a genuine causal step between levels — the sub-cause is not a paraphrase of the parent cause.
- **M4 — Process-not-people terminal.** No chain terminates at "human error", "bad judgment", or "insufficient effort" without a deeper process cause beneath it.
- **M5 — Causation distinguished from correlation.** The prose's evidence assessment explicitly addresses correlation-vs-causation on at least one link, even if briefly.

### Composite (prose + envelope agreement)

- **C1 — Framework agreement.** The framework named in prose equals `spec.framework` in the envelope.
- **C2 — Effect agreement.** The first-sentence noun phrase of the presented-problem paragraph appears verbatim or near-verbatim (lexical overlap ≥ 0.7) in `spec.effect`.
- **C3 — Category agreement.** Every category name in `spec.categories` is mentioned in the prose's "Category analysis" section and justified in one sentence.
- **C4 — Root-cause traceability.** Every root cause identified in the prose's "Root cause(s)" paragraph appears in the envelope as a leaf cause or sub_cause.

### Machine-readable summary (for the Phase 4 adversarial reviewer)

```yaml
success_criteria:
  mode: root-cause-analysis
  version: 1
  structural:
    - id: S1
      check: envelope_present
    - id: S2
      check: envelope_schema_valid
    - id: S3
      check: type_in_allowlist
      allowlist: [fishbone, causal_loop_diagram]
    - id: S4
      check: mode_context_equals
      value: root-cause-analysis
    - id: S5
      check: canvas_action_equals
      value: replace
    - id: S6
      check: effect_not_solution_phrased
      banned_prefixes: [increase, reduce, implement, adopt, deploy, improve]
    - id: S7
      check: framework_declared
      allowlist: [6M, 4P, 4S, 8P, custom]
      applies_to: fishbone
    - id: S8
      check: min_categories
      min: 3
      applies_to: fishbone
    - id: S9
      check: non_empty_causes
    - id: S10
      check: depth_floor
      min: 2
    - id: S11
      check: canonical_category_names
      applies_to: fishbone_non_custom
    - id: S12
      check: semantic_description_complete
  semantic:
    - id: M1
      check: mece_categories
    - id: M2
      check: actionable_leaves
    - id: M3
      check: non_trivial_chain
    - id: M4
      check: process_not_people_terminal
    - id: M5
      check: causation_vs_correlation_addressed
  composite:
    - id: C1
      check: framework_prose_envelope_match
    - id: C2
      check: effect_prose_envelope_match
      similarity: lexical_overlap_0.7
    - id: C3
      check: category_coverage_in_prose
    - id: C4
      check: root_cause_prose_to_envelope_trace
  acceptance:
    tier_a_threshold: 0.9
    structural_must_all_pass: true
    semantic_min_pass: 0.8
    composite_min_pass: 0.75
```

## KNOWN FAILURE MODES

Each failure below mirrors the inverse of a success criterion.

**The Linear Chain Trap (inverse of M3).** The 5 Whys isolates a single causal chain when multiple causes may interact. Correction: Generate at minimum two alternative chains. IF multiple chains converge on the same symptom, analyse their interaction.

**The Premature Stop Trap (inverse of M3 + Causal Depth rubric).** Accepting an intermediate cause as root because it is satisfying or actionable. Correction: For each proposed root cause, ask one more time — what caused this? IF the answer is non-trivial, the chain has not reached root and `sub_causes` should be added.

**The Human Error Trap (inverse of M4).** Terminating the chain at a person's mistake. Correction: Behind every human error is a process that permitted or incentivised it. Continue the chain through the process failure.

**The Knowledge Boundary Trap.** The analysis cannot go beyond the investigator's current knowledge. Correction: When the chain reaches a point where the analyst lacks domain knowledge to continue, state the boundary explicitly and identify what expertise is needed. Emit the envelope with what is known; do not fabricate leaves.

**The Ad-hoc Framework Trap (inverse of S7, C1, Framework Coherence rubric).** Categorising causes without declaring a framework, producing a non-MECE fishbone whose spines mix 6M, 4P, and invented names. Correction: Declare framework first; if no canonical framework fits, declare `custom` and justify.

**The Restatement Trap (inverse of M3, No-restatement guard).** Writing a cause that rephrases the effect ("deployments fail" → "deployments are unreliable"). Correction: Delete the restatement; write a cause one level deeper.

**The Solution-Phrased Effect Trap (inverse of S6, Effect-phrasing guard).** Stating the effect as something to fix ("increase deployment reliability") rather than as the observed failure ("deployments fail intermittently"). Correction: Re-phrase `spec.effect` as a problem statement before emitting. Validator emits `W_EFFECT_SOLUTION_PHRASED` if this slips.

**The Non-Canonical Category Trap (inverse of S11).** Renaming `Machine` to `Infrastructure` inside a declared 6M framework, or merging two canonical options with a slash (e.g. `Milieu/Environment`). Correction: Pick exactly one canonical name per spine. If no canonical name fits, switch framework to one whose canonical names do (4P — `Plant`; 4S — `Systems`) or declare `custom` and justify.

**The Type-Switch Trap (inverse of type-selection rule).** Emitting a `causal_loop_diagram` for a decomposition that has no feedback loops, because "causal" sounds like "causal_loop_diagram". Correction: fishbone is the default; only emit CLD when a loop has been articulated in prose.

**The Missing-Envelope Trap (inverse of S1).** Producing a text-only hierarchical bullet list of causes and no fenced envelope. Correction: The prose must be followed by exactly one fenced `ora-visual` block; the bullets-only form is the pre-rebuild failure mode.

## TOOLS

Tier 1: Challenge (test each causal link), CAF (identify all factors contributing to the failure), C&S (trace forward consequences of proposed corrective actions — do they create new problems?), RAD (recognise whether this is a single failure or multiple failures being conflated).

Tier 2: Engineering and Technical Analysis Module (5 Whys protocol, Ishikawa/fishbone methodology, fault tree analysis, failure mode and effects analysis). Problem Definition Question Bank (Module 3 — Structural Analysis).

## TRANSITION SIGNALS

- IF the root cause involves feedback loops or systemic structure → propose **Systems Dynamics** for deeper structural analysis (and emit `causal_loop_diagram` from within RCA when the loop is clear).
- IF the root cause involves institutional interests or distributional choices → propose **Cui Bono**.
- IF the user wants to choose between corrective approaches → propose **Constraint Mapping** or **Decision Under Uncertainty**.
- IF the user begins defining a deliverable (incident report, corrective action plan) → propose **Project Mode**.
- IF the root cause rests on unexamined assumptions about how the process should work → propose **Paradigm Suspension**.
