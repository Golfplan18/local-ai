
# Reference — Pre-Routing Pipeline Architecture

*The four-stage routing pipeline that replaces the intent-classification flow of the retired Mode Classification Directory. This file specifies the architecture; companion files specify the supporting registries: `Reference — Signal Vocabulary Registry.md` (Stage 2 lookup), `Reference — Within-Territory Disambiguation Trees.md` (Stage 2 within-territory disambiguation), `Reference — Cross-Territory Adjacency.md` (Stage 1 cross-territory disambiguation), `Reference — Disambiguation Style Guide.md` (Stage 2 and Stage 3 question phrasing). The orchestrator implementation (Phase 9) reads from `~/ora/architecture/pre-routing-pipeline.md` (this file's ora-runtime pair) and the supporting registries.*

---

## Architectural Principle: Deep-Mode Default With Friction Reducers

Per Decision 1, the pipeline defaults to **disambiguation by default** — every analytical prompt is offered the disambiguation flow that selects an appropriate mode and depth. **Friction reducers** skip questions the prompt has already answered. The result: routine prompts dispatch with zero clarifying questions because the prompt itself supplied the answers; ambiguous prompts get the disambiguation they need.

This replaces the retired Mode Classification Directory's intent-classification flow, which routed by inferring user intent from a flat 25-mode list. The new flow operates on territories and gradation positions, with disambiguation as a first-class operation rather than a fallback.

The pipeline has four sequential stages. Each stage has a clear input, processing logic, and output. Stage transitions are deterministic (no stage advances on a partial decision; each stage's output is complete before the next stage begins).

---

## Stage 1 — Pre-Analysis Filter

**Purpose.** Distinguish prompts that should enter the analytical pipeline from prompts that bypass it (chitchat, simple lookups, conversation continuations, system commands).

**Input.** Raw user prompt plus minimal context (current conversation thread, attached documents if any).

**Processing logic.**

1. **Analytical-artifact signal detection.** Substring match against a curated signal vocabulary list of analytical-artifact triggers (≥40 phrases). Examples: "analyze," "make the case for," "what could go wrong," "who benefits," "compare these," "is this argument sound," "what are the tradeoffs," "stress-test," "what's missing," "frame this." Match is case-insensitive. Negation is detected (e.g., "don't analyze" bypasses).
2. **Bypass detection.** Substring match against bypass triggers: greetings, simple factual questions, system commands, prior-answer references ("what did you say earlier"). Matches → direct response (no analytical pipeline).
3. **Ambiguity handling.** When neither analytical signal nor bypass signal matches, default to **permissive** (let the prompt enter the pipeline). The downstream stages will catch genuinely non-analytical prompts and route to direct response.

**Output.**
- `bypass_to_direct_response: true | false`
- If `false`: forwarded prompt + initial signal-vocabulary matches as input to Stage 2.
- If `true`: bypass with rationale.

**Detection logic notes.**
- Substring match (not regex) for performance and predictability.
- Case-insensitive.
- Negation handling: a window of ±3 tokens around the trigger is checked for negation markers ("not," "don't," "no," "without").
- Multiple matches accumulate (signal-vocabulary registry consulted in Stage 2).
- Empty signal-vocabulary match + no bypass match → default permissive (forward to Stage 2).

**Performance characteristic.** Stage 1 runs in O(n × m) where n = prompt length and m = signal-vocabulary size. With m ≈ 100 phrases and n ≈ 500 tokens, this is sub-millisecond on the orchestrator's hot path.

---

## Stage 2 — Prompt Sufficiency Analyzer

**Purpose.** Determine whether the prompt contains enough signal to dispatch to a specific mode without disambiguation, or whether disambiguation questions are needed (and which).

**Input.** Forwarded prompt + Stage 1's signal-vocabulary matches.

**Processing logic.**

### 2.1 Signal-strength classification

Each signal in the prompt is classified as **strong** or **weak** per the signal vocabulary registry's `confidence_weight` field:

**Strong signals.**
- Explicit method-name reference (e.g., "steelman this," "do an ACH on these hypotheses," "wicked problem analysis").
- Named artifact-type reference (e.g., "evaluate this op-ed," "analyze this decision," "audit this argument").
- Unambiguous depth/stance/complexity vocabulary (e.g., "quick read," "deep dive," "make the strongest case for," "stress-test").
- Multiple corroborating signals from the same territory.

**Weak signals.**
- Tonal cues (e.g., "I'm worried about this," "what should I think about this").
- Contextual implication (e.g., paste of a document without an explicit question; the document type implies but does not specify the analytical operation).
- Single-territory vocabulary that could match multiple modes within the territory.

### 2.2 Multiple-signal composition

Signals AND together. A complete combination dispatches directly. A partial combination leaves residual disambiguation questions.

**Complete combination examples.**
- "Make the strongest case for this housing policy" → T15 + stance-constructive-strong + artifact-type=proposal → `steelman-construction` directly. No questions asked.
- "Quick read on what could go wrong with this rollout plan" → T6 + stance-adversarial-future + depth-light + artifact-type=action-plan → `pre-mortem-action` (light variant). No questions asked.

**Partial combination examples.**
- "Look at this op-ed" → T1 candidate (artifact-type=argument) + no depth signal + no stance signal → ask depth + stance disambiguation.
- "Help me think about this decision" → T3 candidate (decision-shape) + no complexity signal + no specificity signal → ask complexity disambiguation.

### 2.3 Conflict detection

Contradictory signals trigger surfacing. Examples:
- "Quick deep-dive" → contradictory depth signals → ask user to clarify (Tier-1 vs. Tier-3).
- "Steelman the red-team perspective" → contradictory stance signals → ask user whether to (a) steelman the adversarial argument or (b) red-team a steelman.

When conflict is detected, Stage 2 surfaces a single targeted question via the Disambiguation Style Guide patterns.

### 2.4 Cross-territory adjacency check

Before within-territory disambiguation, Stage 2 consults `Reference — Cross-Territory Adjacency.md`. If signals straddle two territories, the cross-territory disambiguation question fires first. Example: prompt mentions both "argument soundness" (T1) and "who benefits" (T2) → ask the T1↔T2 disambiguating question first; the user's answer narrows to one territory; within-territory disambiguation then proceeds (or skips, if the answer also disambiguates the mode).

### 2.5 Within-territory disambiguation

When the territory is identified but the mode is ambiguous, Stage 2 consults `Reference — Within-Territory Disambiguation Trees.md` and asks the relevant tree's question(s) using Disambiguation Style Guide phrasing.

### 2.6 Default-on-ambiguity

When the user's response to a disambiguation question is ambiguous or absent:
- **Tier-2 thorough atomic** by default (per Style Guide §5.6).
- **Neutral stance** when the territory has a stance axis and the user has not signaled.
- **General specificity** when the territory has a specificity axis.

### 2.7 Friction-reducer behavior

When the prompt has supplied an answer to a disambiguation question (via signal vocabulary match), that question is **skipped** automatically. The user does not have to repeat themselves. Example: prompt is "Steelman this op-ed quickly" → both stance ("steelman") and depth ("quickly") supplied → no disambiguation questions; direct dispatch to `steelman-construction` at Tier-1.

**Output.**
- `dispatched_mode_id: <mode_id>` (after disambiguation completes)
- `disambiguation_questions_asked: [<questions>]`
- `disambiguation_answers_received: [<answers>]`
- `confidence: high | medium | low`
- Forwarded to Stage 3 with mode_id and the validated routing context.

---

## Stage 3 — Input Completeness Check

**Purpose.** Verify that the dispatched mode's required inputs are present (per its dual `input_contract`). Surface missing or underspecified inputs and either elicit them or offer graceful-degradation to a sibling mode.

**Input.** Dispatched mode_id + forwarded prompt + any prior-conversation context, attached documents, URLs, prior-answer references, in-prompt examples.

**Processing logic.**

### 3.1 Contract version selection

Stage 3 selects between the mode's `expert_mode` and `accessible_mode` input contracts using the mode spec's `input_contract.detection` rules:

- **Expert signals present** → `expert_mode` contract applies.
- **Accessible signals present** → `accessible_mode` contract applies (default per Decision 3).
- **Neither** → `accessible_mode` (default).

### 3.2 Presence detection

For each `required` field in the selected contract, Stage 3 checks for presence across all input sources:
- Pasted text in the current prompt.
- Attached documents (PDF, image, etc.).
- URLs (if URL fetch is available).
- Prior-conversation references ("the document I shared earlier").
- In-prompt examples ("here's an example: ...").

Presence is a binary check per field. Field-specific detection logic lives in `Reference — Mode Specification Template.md`'s `input_contract.detection` block per mode.

### 3.3 Underspecification detection

A field may be present but underspecified. Example: a mode requires `decision_context` and the prompt mentions "I have a decision" without specifying the decision. Underspecification is detected per-field by mode-spec rules.

### 3.4 Graceful-degradation rules

When a required field is missing or underspecified, Stage 3 consults the mode spec's `input_contract.graceful_degradation` block:

- `on_missing_required` — typically a follow-up question template, possibly suggesting a lighter sibling mode that needs less.
- `on_underspecified` — follow-up question template.

Example: User asks "do a wicked problems analysis" without supplying a problem statement. Stage 3 detects missing `problem_description` and surfaces:
> "I can run a Wicked Problems analysis (*integrated multi-perspective analysis of tangled problems*) — this takes about 10 minutes. Could you describe the problem and any history of attempts to address it? If you'd prefer a quicker read, I can run a lighter Cui Bono (*who-benefits analysis*) on the situation as you describe it."

The graceful-degradation offer pairs the heavier mode (with its time-cost) against a lighter sibling. The user picks one or supplies the missing input.

### 3.5 Accept-and-resume path

When the user supplies the missing input, Stage 3 re-runs the completeness check. When it passes, Stage 3 forwards to Stage 4. When the user opts for the lighter sibling, Stage 3 re-dispatches (returning to Stage 2's mode selection with the new mode_id) and re-runs Stage 3 against the new mode's contract.

**Output.**
- `inputs_complete: true | false`
- `validated_inputs: { <field>: <source-and-value> }`
- If `inputs_complete: false`: dialog turn to user with completeness-check question (per Style Guide §5.8).
- If `inputs_complete: true`: forwarded to Stage 4.

---

## Stage 4 — Mode Execution

**Purpose.** Dispatch to the selected mode against the validated inputs.

**Input.** Validated `dispatched_mode_id` + `validated_inputs` from Stage 3 + the orchestrator's routing context (user, conversation, RAG profile, etc.).

**Processing logic.**

1. **Load mode spec** from `~/ora/modes/<mode_id>.md` (ora-runtime path).
2. **Load runtime config entry** from `~/ora/architecture/runtime-configuration.md` keyed by `mode_id`. If the entry is missing, error and surface to user (per Decision C: default-on-missing-config errors safely; no silent fallback).
3. **Compose dispatch announcement** with educational parenthetical per Decision E:
   > "Plain-language description *(named technique)*"
   The plain-language description is composed dynamically by the orchestrator from the mode's `educational_name` and the user's prompt; the named technique is the `educational_name` field verbatim.
4. **Execute the universal pipeline stages** (F-Analysis-Depth → F-Analysis-Breadth → F-Evaluate → F-Revise → F-Consolidate → F-Verify). Each stage extracts the relevant `## DEPTH ANALYSIS GUIDANCE` (etc.) subsection from the mode spec.
5. **Apply runtime config** for instruction design per pipeline stage (`runtime_config.instructions.depth_pass`, etc.), gear (default 4 universally per Decision C), type_filter, context_budget.
6. **Output the mode's artifact** per `output_contract`.

**Output.**
- The mode's analytical artifact per its `output_contract`.
- Output format per Decision I/J: territory + mode + residual disambiguation questions if any + completeness gaps if any (richer than current 7-field output).

---

## End-to-End Worked Example

**Prompt.** "give me a quick steelman of this op-ed on housing policy"

**Stage 1 — Pre-Analysis Filter.**
- Signal vocabulary matches: `steelman` (strong, T15), `quick` (depth-Tier-1), `op-ed` (artifact-type=argument).
- No bypass triggers.
- `bypass_to_direct_response: false`.
- Forward to Stage 2 with matches.

**Stage 2 — Prompt Sufficiency Analyzer.**
- `steelman` → T15 + `steelman-construction` mode (strong signal).
- `quick` → Tier-1 depth (strong signal).
- `op-ed` → artifact-type=argument → activates T1 cross-reference for `steelman-construction` (per Decision G re-home).
- Multiple corroborating signals from T15 → complete combination → no disambiguation questions.
- Cross-territory check: T15 home with T1 cross-reference is the configured pattern; not a conflict.
- `dispatched_mode_id: steelman-construction`
- `confidence: high`
- Forward to Stage 3.

**Stage 3 — Input Completeness Check.**
- Mode: `steelman-construction`.
- Contract version: `accessible_mode` (no expert signals).
- Required field: `argument_or_artifact_to_steelman` → present (the op-ed text is in the prompt or attached).
- Underspecification check: passes (op-ed text is concrete content).
- `inputs_complete: true`.
- Forward to Stage 4.

**Stage 4 — Mode Execution.**
- Load `~/ora/modes/steelman-construction.md`.
- Load runtime config for `steelman-construction`.
- Compose dispatch announcement: "I'll make the strongest case for this op-ed *(steelman construction)*."
- Execute pipeline stages at Tier-1 (light depth, single pass).
- Output the steelman artifact per `output_contract`.

**Friction-reducer success.** The prompt contained complete signal (mode-name + depth + artifact-type), so no disambiguation questions fired. The pipeline dispatched in one orchestrator turn.

---

## Pipeline Failure Modes and Handling

The pipeline exhibits known failure modes; each has a documented response.

### Failure 1 — Stage 1 false-bypass

**Symptom.** An analytical prompt is mistakenly classified as bypass and routed to direct response.
**Detection.** User repeats the prompt or asks for analysis explicitly.
**Response.** Re-run Stage 1 in permissive mode (skip bypass detection); forward to Stage 2.

### Failure 2 — Stage 2 disambiguation loop

**Symptom.** User's answer to a disambiguation question is itself ambiguous; Stage 2 asks another question; user's answer is again ambiguous; loop.
**Detection.** Same disambiguation context elicits ≥3 ambiguous answers.
**Response.** Apply default-on-ambiguity rules (Tier-2, neutral stance, general specificity). Dispatch to default mode and surface that the default was chosen.

### Failure 3 — Stage 3 missing-input loop

**Symptom.** User does not supply requested missing input (declines, doesn't have it, or doesn't understand the request).
**Detection.** ≥2 missing-input requests for the same field unresolved.
**Response.** Offer graceful-degradation to lightest sibling (which has the smallest required-input contract). If even the lightest sibling cannot run, exit pipeline with explanation.

### Failure 4 — Stage 4 missing runtime config

**Symptom.** Dispatched mode_id has no entry in runtime configuration.
**Detection.** Stage 4 attempts to load runtime config and fails.
**Response.** Per Decision C, error and surface to user. Do not silently fall back to default gear or default instructions. The fix is to add the runtime config entry; surfacing alerts maintainers.

### Failure 5 — Mode execution exception

**Symptom.** Mode pipeline stage (e.g., F-Evaluate) raises an exception or produces no output.
**Detection.** Pipeline-stage output is empty or error-typed.
**Response.** Re-run failed stage once with a fresh context. If it fails again, exit with the partial output produced and an explanation.

---

## Architectural Invariants

These invariants hold across all pipeline behavior. They are the bedrock for orchestrator implementation (Phase 9) and for any future revision of the pipeline.

1. **Plain-language disambiguation only.** Every Stage 2 and Stage 3 question uses the Disambiguation Style Guide vocabulary. No mode names, territory labels, methodology jargon, or "atomic vs. molecular" distinctions in the question itself.
2. **Educational parenthetical convention.** Every dispatch announcement uses `"plain language *(named technique)*"`. No bare mode names or bare technique names. Acronyms expanded per Decision E.
3. **Default-on-ambiguity is Tier-2 + neutral + general.** Never Tier-1 by default; never Tier-3 by default; never adversarial by default.
4. **Friction reducer skips answered questions.** A signal already supplied by the prompt does not trigger a disambiguation question on the same content.
5. **Default-on-missing-config errors.** Stage 4 does not silently substitute defaults for runtime config.
6. **Cross-territory disambiguation precedes within-territory.** When signals straddle two territories, the cross-territory question fires first.
7. **Graceful degradation pairs heavy mode with light sibling.** When required input is missing, Stage 3 offers a lighter sibling explicitly so the user has a real choice.
8. **Vault canonical and ora runtime stay synchronized.** Phase 9 reads exclusively from `~/ora/architecture/`; any change to `Reference — Pre-Routing Pipeline Architecture.md` (this file) requires drift sync.

---

## Cross-Reference Map

This file is **read by** the orchestrator implementation (Phase 9 reads its ora-runtime pair `~/ora/architecture/pre-routing-pipeline.md`).

This file **references**:
- `Reference — Signal Vocabulary Registry.md` (Stage 1 + Stage 2)
- `Reference — Within-Territory Disambiguation Trees.md` (Stage 2)
- `Reference — Cross-Territory Adjacency.md` (Stage 1 + Stage 2)
- `Reference — Disambiguation Style Guide.md` (Stage 2 + Stage 3 question phrasing)
- `Reference — Mode Specification Template.md` (Stage 3 contract version selection)
- `Reference — Mode Runtime Configuration.md` (Stage 4 runtime config)
- `Reference — Analytical Territories.md` (territory inventory; consulted across stages)

This file **is referenced from**:
- `Reference — Mode Registry.md` (Phase 7 rewrite — opens with pipeline overview)
- `Reference — Ora Overview and Document Registry.md` (Phase 7 update)
- `~/ora/CLAUDE.md` (Phase 7 update — pairing rules + orchestrator architecture pointer)
- `Framework — System File Drift Correction.md` (Phase 1 update — drift correction registry)

*End of Reference — Pre-Routing Pipeline Architecture.*
