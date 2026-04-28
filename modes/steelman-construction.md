---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 3
no_visual: true
---

# MODE: Steelman Construction

## TRIGGER CONDITIONS

Positive:
1. A position is about to be critiqued or dismissed.
2. "What's the best case for X"; "give me the strongest version".
3. Debate involves caricature of one side.
4. User wants to understand an opposing argument at its strongest before evaluating.
5. Request language: "steelman", "best case for", "play devil's advocate", "strongest version of the other side".

Negative:
- IF questioning foundational assumptions rather than strengthening the position → **Paradigm Suspension**.
- IF tracing whose interests a position serves → **Cui Bono**.
- IF neutrally examining tension between positions → **Synthesis**.
- IF driving thesis through antithesis → **Dialectical Analysis**.

Tiebreaker:
- Steelman vs Dialectical: **build + critique one position** → Steelman; **build + negate + sublate** → DA.

## EPISTEMOLOGICAL POSTURE

The opposing position is treated as potentially correct and deserving the strongest possible formulation. This is self-directed epistemic hygiene — steelmanning serves the analyst's understanding, not the opponent's ego. Evidence and reasoning are taken seriously on their own terms. The position is reconstructed at its logical best: hidden premises identified, logical gaps filled, best evidence marshalled. The steelman is built BEFORE critique begins — never simultaneously.

## DEFAULT GEAR

Gear 3. Sequential construction and stress-testing is the natural workflow. Breadth constructs; Depth stress-tests.

## RAG PROFILE

**Retrieve (prioritise):** strongest advocates for the position; academic literature supporting it; canonical formulations (foundational papers, definitive books).

**Deprioritise:** critiques of the position during construction — critiques belong in the evaluation phase only.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `supports`, `extends`, `qualifies`, `analogous-to`
**Deprioritise:** `contradicts`, `supersedes`
**Rationale:** Steelmanning requires finding the strongest support, extensions, and analogies.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The position to be steelmanned |
| `conversation_rag` | Prior turns' critiques that constructed only a weak version |
| `concept_rag` | Proponents' canonical arguments |
| `relationship_rag` | Objects linked by `supports` to the position |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat:
1. Identify the position as originally stated.
2. Identify the strongest evidence supporting it — evidence that would be most difficult for a critic to dismiss.
3. After Breadth completes the steelman, assess whether the construction genuinely strengthens or subtly weakens (tinmanning).

Black Hat:
1. Apply the **mirror test**: would a thoughtful proponent say "I wish I'd thought of putting it that way"? If not, the steelman is insufficient.
2. Identify ≥ 2 points where the steelmanned version is strongest.
3. Critique only the steelmanned version, never retreating to the weaker original.

### Cascade — what to leave for the evaluator

This mode emits NO envelope. All cascade cues live in prose.

- Separate the six CONTENT CONTRACT sections with literal headings `Original position:`, `Steelmanned reconstruction:`, `Strength identification:`, `Points of agreement:`, `Critique of the steelman:`, `Survival assessment:`. Supports S2.
- Keep the Original-position paragraph ≤ 1/3 of the total steelman section length — construction must dominate. Supports S3.
- Apply the literal phrase "mirror test:" when declaring the steelman mirror-passed. Supports M1.
- List ≥ 2 points of agreement explicitly numbered (`Agreement 1:`, `Agreement 2:`). Supports M2.
- Critique section uses the literal phrase "addressing the steelmanned version:" to signal no-retreat-to-original. Supports M3.

### Consolidator guidance

Not applicable at this mode's default gear (Gear 3, single-stream). If promoted to Gear 4 (rare — construction and critique are naturally sequential), use Breadth's construction as canonical and Depth's critique as the stress-test; do NOT present both constructions side-by-side, which defeats the mode's purpose (one steelman, not a side-by-side compare).

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. Reconstruct at logical best. Identify hidden premises that make the argument stronger. Fill gaps with the most charitable inferences. Marshal the best available evidence.
2. Formulate more precisely than proponents have.
3. Identify ≥ 2 points of agreement between the steelmanned position and the user's own.

Yellow Hat:
1. Identify what is genuinely valuable in the position.
2. Assess what the user gains from the steelman: better understanding of opposition, genuine vulnerabilities in their own position, unexpected common ground.
3. Identify what survives critique.

### Cascade — what to leave for the evaluator

- Prefix each hidden premise uncovered during construction with `Hidden premise:`.
- Prefix filled gaps with `Gap filled:`.
- Use the literal phrase "survives critique:" for each element in the Survival assessment. Supports M4.
- Identify genuine value with the literal phrase "Genuinely valuable:".

## EVALUATION CRITERIA

5. **Steelman Fidelity.** 5=recognisably the same argument, strengthened. 3=shifted the core claim. 1=replaced with a different argument.
6. **Mirror Test.** 5=a thoughtful proponent would endorse. 3=recognises the argument with one mischaracterisation. 1=would not recognise their own argument.
7. **Critique Quality.** 5=addresses only the strongest version. 3=retreats to original at one point. 1=primarily addresses the original formulation.

### Focus for this mode

A strong Steelman evaluator prioritises (prose-only, no envelope):

1. **No-envelope invariant (S1).** Any `ora-visual` block is a mandatory fix — this mode is prose-only.
2. **Six-section presence (S2).** Each of the six CONTENT CONTRACT sections must be identifiable.
3. **Construction-dominance (S3).** Original-position paragraph ≤ 1/3 of total steelman section length.
4. **Mirror test (M1).** Would a thoughtful proponent endorse the reconstruction?
5. **Critique-addresses-steelman-only (M3).** No retreat to the original formulation during critique.
6. **Fidelity (M5).** Steelman is the same argument strengthened, not replaced.

No visual short_alt criterion applies — mode is envelope-free.

### Suggestion templates per criterion

- **S1 (envelope present):** `suggested_change`: "Remove the `ora-visual` block. Steelman Construction is prose-only. If the user asked for a visual summary, propose transition to Dialectical Analysis (which emits IBIS)."
- **S2 (missing section):** `suggested_change`: "Add the missing section with the literal heading `<section-name>:`. Six sections required in order: Original position / Steelmanned reconstruction / Strength identification / Points of agreement / Critique / Survival assessment."
- **S3 (original over-long):** `suggested_change`: "Trim the Original-position paragraph to ≤ 1/3 of the total steelman section length. Construction must dominate, not repetition of the weak formulation."
- **M1 (mirror test failed):** `suggested_change`: "Rewrite the steelman until a thoughtful proponent would say 'I wish I'd thought of putting it that way'. The current version is recognisably weaker than what a committed advocate would produce."
- **M3 (retreat to original):** `suggested_change`: "Critique paragraph addresses the weaker original at passage <quote>. Rewrite to address only the steelmanned formulation. If the critique doesn't apply to the steelman, it isn't a critique — drop it."
- **M5 (identity loss):** `suggested_change`: "The steelman has drifted into a different argument. Re-anchor to the original position's core claim; the steelman strengthens that claim, not replaces it."

### Known failure modes to call out

- **Envelope-Slip Trap** → open: "An `ora-visual` block was emitted. Mandate removal — Steelman Construction is prose-only."
- **Tinman Trap** → open: "The 'steelman' is designed to be defeated. Apply the mirror test and rewrite."
- **Steel-Strawman Trap** → open: "The steelman appears strong but has a specific point engineered for defeat. Strengthen that specific point or drop the critique."
- **Identity Loss Trap** → open: "Reconstruction has drifted into a different argument. Re-anchor to the original claim."
- **Projection Trap** → surface as SUGGESTED: "Reconstruction filtered through the analyst's worldview. Rebuild from the proponent's values."

### Verifier checks for this mode

Universal V1-V8 (V2/V3/V6 N/A since Gear 3 single-stream; V5 applies to prose content contract only); then:

- **V-STM-1 — No-envelope preservation.** Revised response has NO `ora-visual` fenced block.
- **V-STM-2 — Six-section preservation.** All six CONTENT CONTRACT sections present in revised prose.
- **V-STM-3 — Construction-dominance preservation.** Original-position paragraph still ≤ 1/3 of total steelman section length.
- **V-STM-4 — No-retreat preservation.** Critique section still addresses only the steelmanned version; no retreat to original formulation.

## CONTENT CONTRACT

In order:

1. **Original position** — faithful re-expression of the position as actually stated, including its weaknesses.
2. **Steelmanned reconstruction** — the strongest possible version.
3. **Strength identification** — which premises are most defensible, which evidence hardest to dismiss.
4. **Points of agreement** — ≥ 2 places where the steelmanned position and the user's position converge.
5. **Critique of the steelman** — addressing only the strongest version, with specific vulnerabilities.
6. **Survival assessment** — what remains compelling after critique.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S1 (envelope present):** apply envelope-removal template.
- **S2 (missing section):** apply missing-section template.
- **S3 (original too long):** apply trim template.
- **M1 (mirror test):** apply mirror-test template.
- **M2 (< 2 agreement points):** add agreement points until ≥ 2, each numbered.
- **M3 (retreat):** apply no-retreat template.
- **M4 (survival missing):** add Survival-assessment section with "survives critique:" labels.
- **M5 (identity loss):** apply re-anchor template.

## EMISSION CONTRACT

**Steelman Construction emits NO `ora-visual` block.** Linguistic argument is the native form of the deliverable; any diagram would misrepresent the argument's structure as spatial when it is rhetorical.

### Suppression rule

- The response is prose only, in the seven content-contract sections above.
- A conceptual reader may be tempted to emit an `ibis` diagram — **do not**. IBIS is Dialectical Analysis's envelope; rendering a steelman as IBIS flattens the construction's rhetorical arc into a static graph.
- If the user explicitly asks for a visual summary, emit nothing in Steelman Construction and propose transitioning to **Dialectical Analysis** (which emits IBIS) for the visual.

## GUARD RAILS

**Solution Announcement Trigger.** WHEN declaring the steelmanned position correct or refuted, verify the assessment is grounded in the analysis.

**Construction-before-critique guard rail.** Complete the steelman before beginning any critique.

**Mirror test guard rail.** Apply the mirror test before presenting.

**Symmetry guard rail.** If multiple positions need steelmanning, apply identical rigour to each.

**No-envelope guard rail.** Do NOT emit any `ora-visual` block. Prose is the deliverable.

## SUCCESS CRITERIA

Since there is no envelope, structural criteria focus on prose shape. The Phase 4 reviewer uses only prose content.

### Structural (prose-only)

- S1: NO `ora-visual` fence in response. Envelope absence is the pass condition.
- S2: Prose contains all six CONTENT CONTRACT sections (in order or clearly demarcated).
- S3: Original-position paragraph is ≤ 1/3 of total steelman section length (construction dominates, not repetition).

### Semantic (LLM-reviewer)

- M1: Mirror test — a thoughtful proponent would endorse.
- M2: ≥ 2 points of agreement explicit.
- M3: Critique addresses only the steelmanned version (no retreat to original).
- M4: Survival assessment explicit.
- M5: The steelmanned reconstruction is recognisably the same argument, not a replacement.

```yaml
success_criteria:
  mode: steelman-construction
  version: 1
  no_visual: true
  structural:
    - { id: S1, check: no_envelope_present }
    - { id: S2, check: six_content_sections_present }
    - { id: S3, check: original_position_length_bounded }
  semantic:
    - { id: M1, check: mirror_test }
    - { id: M2, check: two_agreement_points }
    - { id: M3, check: critique_targets_steelman_only }
    - { id: M4, check: survival_assessment_present }
    - { id: M5, check: steelman_fidelity }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8 }
```

## KNOWN FAILURE MODES

**The Tinman Trap (inverse of M1).** Declaring a steelman while constructing a position designed to be defeated. Correction: apply the mirror test.

**The Projection Trap.** Filtering through the analyst's worldview. Correction: reconstruct from the proponent's values, not the analyst's.

**The Steel-Strawman Trap.** Appearing strong but defeatable at a specific point. Correction: identify strongest points explicitly.

**The Identity Loss Trap (inverse of M5).** "Improving" into a different argument. Correction: the steelman must be the same argument strengthened.

**The Envelope-Slip Trap (inverse of no-envelope guard).** Emitting an `ibis` diagram as a visual summary. Correction: no envelope in this mode; propose Dialectical Analysis if visual needed.

## TOOLS

Tier 1: OPV (understand from proponents' perspective), Challenge, PMI.
Tier 2: Domain modules based on the position's domain.

## TRANSITION SIGNALS

- IF critique reveals unexamined assumptions → propose **Paradigm Suspension**.
- IF tracing interests behind the position → propose **Cui Bono**.
- IF two steelmanned positions produce tension worth examining → propose **Synthesis** or **Dialectical Analysis**.
- IF choosing between the steelmanned position and the user's → propose **Constraint Mapping**.
- IF the user wants a visual rendering of the argument → propose **Dialectical Analysis** (IBIS).
