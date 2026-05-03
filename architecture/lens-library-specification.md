
# Reference — Lens Library Specification

*This file specifies the uniform structure all lens artifacts follow, with type-specific inner content. Lenses are not modes — they don't dispatch; they're invoked from within modes. The lens library is built (Phase 5) per this specification. Comprehensive scope per Decision F: ~120–140 lens artifacts (17 foundational lenses + ~20 mode-specific lenses + ~100 existing prose-style mental-model lenses converted to uniform structure). Locked per the 15 architectural decisions of 2026-05-01.*

---

## 1. Lens-Type Taxonomy

A lens is a named pattern, framework, mental model, or scheme that one or more modes draws on to structure its analysis. Every lens declares one of nine `lens_type` values. The type determines the inner format of `## Core Structure` (Section 3) but does not change the outer structure (Section 2).

| `lens_type` | Inner-content shape | Canonical example |
|---|---|---|
| `argumentation-scheme` | Tabular catalog: scheme-name, premise-pattern, conclusion-pattern, critical-questions | Walton schemes catalog |
| `causal-framework` | Level-based rubric: level, definition, operational test | Pearl ladder of causation; Knightian risk/uncertainty/ambiguity |
| `rubric` | Graded criteria with positive and negative exemplars per level | Tetlock calibration scoring; Brier score bands |
| `catalog` | Enumerated patterns with one-paragraph description per item | Senge system archetypes; Meadows leverage points; Kahneman-Tversky bias catalog |
| `protocol` | Numbered procedural steps with input/output per step | Heuer ACH eight steps; Tetlock ten commandments; Klein pre-mortem method |
| `mental-model` | Prose-with-fields: core insight, mechanism, applicability, common misapplications, related models | Most existing prose lenses (Cynefin, Feedback Loops, Decision Trees, etc.) |
| `strategic-framework` | Kernel-style spec with named components | Rumelt diagnosis-policy-action; Fisher/Ury four principles |
| `aesthetic-tradition` | Tradition-stance template: foundational text(s), operational principle, output contract, contrast cases, evaluative axes | Japanese-aesthetics lens (T19); other tradition-bound aesthetic frameworks |
| `environmental-framework` | Feature-pattern catalog with predicted experiential/functional consequence per pattern | Alexander pattern language; Appleton prospect-refuge theory |

The taxonomy is closed in this version. New lens types require an architectural amendment, not ad-hoc addition.

---

## 2. Uniform Outer Structure

Every lens file in `/Users/oracle/Documents/vault/Lenses/` carries the same YAML frontmatter and the same seven top-level `##` sections, regardless of `lens_type`. Type-specific variation lives only inside `## Core Structure`.

### 2.1 YAML Frontmatter (locked)

```yaml
---
lens_id: <kebab-case>                              # filename without .md extension
name: <Display Name>                               # title-case
lens_type: argumentation-scheme | causal-framework | rubric | catalog | protocol | mental-model | strategic-framework | aesthetic-tradition | environmental-framework
applicability: [<mode_ids that use this lens>]     # by mode_id, matches Lenses-to-Modes index
foundational: true | false                         # foundational lenses are globally available; non-foundational are mode-specific
source: "<canonical source citation, including year>"
date created: <YYYY-MM-DD>
date modified: <YYYY-MM-DD>
nexus:
  - ora
type: resource
tags:
  - lens
  - <type-specific tag, e.g., "argumentation", "decision", "framing", "systems", "mental-model">
---
```

### 2.2 Body Sections (locked, in order)

```markdown
# <Display Name>

## Trigger

[One paragraph: when this lens is invoked from within a mode. Names the
host modes by mode_id and the analytical situation that calls for the
lens. Not a list — a paragraph.]

## Core Structure

[The substantive content. Format adapts to lens_type per Section 3 below.
This is the only section whose internal shape varies by type.]

## Application Steps

[Numbered steps for invoking the lens. Brief — typically 3–7 steps. Each
step names the action and its output, not the rationale. The rationale
lives in Core Structure.]

## Detection Signals

[How the orchestrator or analyst recognizes that this lens is appropriate.
Bullet list. Each signal is concrete and observable in a prompt or in
mid-analysis state.]

## Critical Questions

[Walton-style defeasibility conditions specific to the lens. Bullet list.
Each CQ's negative answer invalidates the lens application or flags it
for reconsideration. Minimum 3 CQs.]

## Common Failure Modes

[Named failure patterns when the lens is misapplied. Bullet list. Each
entry: failure-name — detection signal — correction protocol.]

## Source Citations

[Primary sources with year. Bullet list. Foundational lenses cite the
originating text(s); converted mental-model lenses cite the canonical
source plus any major commentaries.]
```

The outer structure is locked: all seven `##` sections appear in every lens file in this exact order, even when a section is brief. Empty sections are not permitted; if a section has no content the lens is not yet ready for the library.

---

## 3. Inner Format per `lens_type`

This section specifies what `## Core Structure` contains for each of the nine lens types. Each subsection includes a one-paragraph description of the inner format and a 5–10 line schematic example.

### 3.1 `argumentation-scheme`

**Inner format.** Tabular markdown with one row per scheme. Columns: scheme-name, premise-pattern (the abstract argument shape), conclusion-pattern, critical-questions (the defeasibility conditions specific to that scheme). When the lens covers multiple schemes (the Walton catalog covers ~60), the table can be grouped under sub-headings by scheme family (e.g., "Source-based schemes," "Causal schemes," "Practical-reasoning schemes"). Critical-questions per row are listed, not paragraph-form.

**Schematic example (Walton catalog excerpt):**

```markdown
### Source-Based Schemes

| Scheme | Premise pattern | Conclusion pattern | Critical questions |
|---|---|---|---|
| Argument from Expert Opinion | E is an expert in domain D; E asserts that A is true; A is in D | A is plausibly true | (1) Is E a genuine expert in D? (2) Did E actually assert A? (3) Is A within D? (4) Is E reliable? (5) Do other experts agree? (6) Is the assertion based on evidence? |
| Argument from Position to Know | P is in a position to know about A; P asserts A | A is plausibly true | (1) Is P actually in a position to know? (2) Is P an honest source? (3) Did P actually assert A? |
```

### 3.2 `causal-framework`

**Inner format.** A level-based rubric in markdown table form. Columns: level (the named tier), definition (what holds at that level), operational test (how to determine in practice that one is operating at that level vs. an adjacent level). Rows are ordered from least to most demanding. The lens may carry a brief paragraph following the table that names the most common confusion (e.g., conflating association with intervention) and how to detect it.

**Schematic example (Pearl ladder of causation):**

```markdown
| Level | Definition | Operational test |
|---|---|---|
| 1. Association | Statistical dependency between variables; "seeing" | Can the claim be settled by observational data alone? |
| 2. Intervention | Effect of an action; "doing" | Does the claim require predicting the result of changing one variable while holding others fixed? |
| 3. Counterfactual | What would have been; "imagining" | Does the claim require reasoning about a world that did not occur? |

Common confusion: treating Level-1 correlations as Level-2 causal claims is the dominant failure pattern. Detection signal: claim asserts that intervening on X will change Y, but evidence supports only that X and Y co-vary.
```

### 3.3 `rubric`

**Inner format.** Graded criteria in markdown table form. Columns: level (named or numeric), criteria (what qualifies at that level), positive exemplar (a short concrete case that meets the criteria), negative exemplar (a short concrete case that fails). When the rubric is multidimensional (e.g., calibration plus resolution), one table per dimension.

**Schematic example (Tetlock calibration band rubric):**

```markdown
| Calibration band | Criteria | Positive exemplar | Negative exemplar |
|---|---|---|---|
| Excellent (Brier ≤0.15) | Forecasted probabilities track observed frequencies within ±5% across all confidence bins | Superforecaster sample, 2011–2015 IARPA tournament | Pundit predictions on cable TV (Brier ≈ 0.40+) |
| Acceptable (0.15–0.25) | Probabilities track frequencies within ±10% in major bins; minor over- or under-confidence | Domain analyst with structured updating | Forecaster who is right on direction but consistently overconfident |
| Poor (>0.25) | Forecasts cluster at extreme probabilities (0/1) regardless of evidence; or systematic bias | Confirmation-bias-driven analyst | One-sided forecaster ignoring base rates |
```

### 3.4 `catalog`

**Inner format.** Enumerated list of patterns (numbered or bulleted), each with a one-paragraph description giving the pattern's structure, when it manifests, and a brief example. The catalog may be grouped under sub-headings when the patterns fall into natural families (e.g., Meadows leverage points group from "lowest leverage" to "highest leverage"). Each pattern's name is bolded; the description follows.

**Schematic example (Senge system archetypes excerpt):**

```markdown
1. **Limits to Growth.** A reinforcing loop that initially produces growth eventually encounters a balancing loop (a limit) that slows or reverses the growth. Pattern manifests in product adoption, organizational expansion, ecological populations. Example: a startup's user growth driven by word-of-mouth eventually saturates the addressable market; growth flattens because the reinforcing engine has run out of substrate.

2. **Shifting the Burden.** A symptom-suppressing intervention is repeatedly applied while the underlying cause is left unaddressed; over time the underlying cause worsens and capacity to address it atrophies. Manifests in addiction, technical debt, organizational firefighting. Example: a team responds to every incident by patching the immediate failure rather than addressing the architectural fragility, until the system can no longer be patched.

3. **Tragedy of the Commons.** Multiple actors independently pursuing rational self-interest deplete a shared resource that none individually owns. Manifests in fisheries, atmospheric carbon, shared codebases without ownership. Example: every team adds dependencies to a shared library without coordination; the library accumulates conflicting requirements until no team can upgrade safely.
```

### 3.5 `protocol`

**Inner format.** Numbered procedural steps. Each step states: the action, the input the step takes from the prior step (or from the host mode), and the output the step produces for the next step. Steps are written as imperatives ("List...", "Score...", "Eliminate..."). When a step has sub-steps or branching, it carries a brief sub-list. The protocol's overall input and output are stated before step 1.

**Schematic example (Heuer ACH protocol):**

```markdown
**Input:** A set of competing hypotheses about a situation; a body of evidence.
**Output:** A diagnosticity matrix and a ranked-by-disconfirmation hypothesis list.

1. **Identify hypotheses.** List all reasonable hypotheses, including ones initially seen as unlikely. Input: situation description. Output: hypothesis list (typically 4–8).

2. **List evidence and assumptions.** Enumerate all relevant evidence and identify which items are assumptions vs. observations. Input: situation context. Output: evidence list.

3. **Build the matrix.** Construct an N×M matrix (N hypotheses, M evidence items). Input: outputs of steps 1–2. Output: empty matrix.

4. **Score consistency.** For each cell, mark whether the evidence is Consistent, Inconsistent, or Not-Applicable with the hypothesis. Input: matrix. Output: filled matrix.

5. **Refine matrix.** Delete evidence items consistent with all hypotheses (non-diagnostic). Input: filled matrix. Output: diagnosticity matrix.

6. **Draw tentative conclusions.** Rank hypotheses by *number of inconsistent evidence items* (least is most consistent with evidence). Input: diagnosticity matrix. Output: ranked hypothesis list.

7. **Sensitivity analysis.** Identify which evidence items are load-bearing for the ranking; assess the consequences of each being wrong. Input: ranked list and diagnosticity matrix. Output: sensitivity report.

8. **Report conclusions.** Present all hypotheses, the diagnosticity matrix, the ranking, and the sensitivity findings. Input: outputs of steps 6–7. Output: final ACH report.
```

### 3.6 `mental-model`

**Inner format.** Prose-with-fields. The Core Structure carries the following sub-headings in order: **Core Insight** (one paragraph, the central claim of the model), **Mechanism** (one to two paragraphs, the underlying causal or structural reason the model holds), **Applicability Conditions** (bullet list of conditions under which the model is well-fit), **Common Misapplications** (bullet list of patterns where the model is mistakenly invoked or stretched beyond its scope), **Related Models** (bullet list of adjacent or contrasting lenses with one-line relationship notes). This is the dominant format for the ~100 existing prose lenses (Cynefin, Feedback Loops, Decision Trees, etc.) once converted.

**Schematic example (excerpt from a converted mental-model lens):**

```markdown
### Core Insight

A small change in one part of a system can be amplified into a large effect (reinforcing loop) or absorbed without effect (balancing loop). Most non-trivial system behavior is generated by the interaction of these two loop types.

### Mechanism

Output feeds back as input. When the feedback raises the variable that produced it, the loop is reinforcing and trajectories diverge exponentially. When the feedback opposes the variable that produced it, the loop is balancing and trajectories converge to a setpoint.

### Applicability Conditions

- The variable of interest can be observed over time, not just sampled at one point.
- The downstream effects of the variable plausibly loop back to affect the variable itself.
- The time-scale of the loop is within the analysis horizon.

### Common Misapplications

- Treating a sequence of events as a loop when no actual feedback path exists (post-hoc narrative pattern).
- Identifying only one loop when multiple loops compete; the dominant loop changes the picture.

### Related Models

- **System Archetypes** — named patterns of multi-loop interaction.
- **Leverage Points** — where to intervene in a loop structure (Meadows).
```

### 3.7 `strategic-framework`

**Inner format.** Kernel-style spec with explicit named components. Core Structure carries one sub-heading per component, in the order the framework's author specifies. Each component carries: definition (what it is), distinguishing features (what it is not), and a worked-example sketch (3–5 lines showing the component instantiated). Frameworks with three components (Rumelt: diagnosis-policy-action) get three sub-headings; frameworks with four (Fisher/Ury: people-interests-options-criteria) get four.

**Schematic example (Rumelt strategy kernel):**

```markdown
### Component 1 — Diagnosis

**Definition.** A simplified statement of the situation's defining challenge that translates the complexity of the situation into a tractable problem.

**Distinguishing features.** A diagnosis is not a goal, not a vision, and not a list of conditions; it identifies *the* obstacle whose removal unlocks progress.

**Worked-example sketch.** "Our customers are not buying because the product requires three days of training before it produces value, and our buyers don't have three days." (Diagnosis names training-time as the obstacle; rules out price, awareness, distribution as the central challenge.)

### Component 2 — Guiding Policy

**Definition.** An overall approach for dealing with the challenge identified in the diagnosis.

**Distinguishing features.** A guiding policy is directional, not specific; it constrains action without prescribing every move. It is judged by whether it would address the diagnosis if executed.

**Worked-example sketch.** "Eliminate the three-day training requirement by redesigning the product around progressive disclosure and in-product onboarding."

### Component 3 — Coherent Action

**Definition.** Coordinated steps that implement the guiding policy.

**Distinguishing features.** Actions are coherent when each reinforces the others rather than working at cross-purposes; coherence is the distinguishing test.

**Worked-example sketch.** "(1) Replace the training program with an interactive in-product tutorial. (2) Restructure the UI so that core value is reachable in 15 minutes. (3) Retrain the sales team to demonstrate 15-minute value rather than 3-day training. (4) Shift marketing copy from 'enterprise platform' to 'works in fifteen minutes.'"
```

### 3.8 `aesthetic-tradition`

**Inner format.** Tradition-stance template. Core Structure carries the following sub-headings in order: **Foundational Text(s)** (the canonical sources defining the tradition), **Operational Principle** (the central aesthetic commitment expressed as a working rule, not a definition), **Output Contract** (what an analysis or work that genuinely operates in this tradition must contain), **Contrast Cases** (other traditions and how this one differs from each — typically 2–4 contrasts), **Evaluative Axes** (the criteria by which a work is judged within the tradition). Used by T19 modes and other tradition-bound aesthetic frameworks.

**Schematic example (Japanese-aesthetics lens, used by T19):**

```markdown
### Foundational Text(s)

- Sen no Rikyū (16th c.) on tea-ceremony aesthetics.
- Yanagi Sōetsu, *The Unknown Craftsman* (1972).
- Junichiro Tanizaki, *In Praise of Shadows* (1933).

### Operational Principle

Beauty is found in the imperfect, the impermanent, and the incomplete. The work or experience does not strive toward completeness; it accommodates the trace of time, use, and absence.

### Output Contract

An analysis operating in this tradition must (1) name what the work refuses to perfect or complete; (2) identify the specific imperfection or absence the work foregrounds; (3) account for how the imperfection produces, rather than diminishes, the work's quality.

### Contrast Cases

- **Classical Western perfection (Vitruvian).** Beauty is symmetry and completion; the imperfect is to be corrected. Japanese aesthetics treats correction as loss.
- **Romantic sublime.** Beauty is overwhelming presence; Japanese aesthetics is beauty in subtraction.
- **Modernist minimalism.** Reduction is to a designed essential; Japanese aesthetics permits the accidental and the residual.

### Evaluative Axes

- Wabi (rustic simplicity, austere beauty).
- Sabi (the patina of age and use).
- Yūgen (mysterious depth not made fully explicit).
- Ma (the negative space, the pause).
```

### 3.9 `environmental-framework`

**Inner format.** Feature-pattern catalog with one entry per pattern. Each entry carries: pattern name, feature description (the structural or environmental feature being identified), predicted experiential or functional consequence (what occupants or users will tend to feel or do when the pattern is present or absent). Numbered or bulleted; numbered when the patterns are explicitly ordered (e.g., Alexander's pattern numbers), bulleted when they are not.

**Schematic example (Appleton prospect-refuge theory):**

```markdown
- **Prospect.** Open vista or unobstructed view across distance. Predicted consequence: occupants experience legibility and oversight; appropriate for territories where threats are visually detectable. Absence produces a sense of being closed in.

- **Refuge.** Protected location with limited points of approach (alcove, raised bench, bay window). Predicted consequence: occupants experience security and the ability to observe without being observed. Absence in an otherwise-prospect-dominant space produces a sense of exposure.

- **Prospect-and-refuge.** A position offering both — a refuge from which one can see prospect. Predicted consequence: maximum experiential comfort; the most reliable predictor of preferred seating in cafés, lobbies, and parks. Spaces lacking this combination are typically vacated first.

- **Hazard.** Apparent threat (cliff edge, dark passage, visible obstacle) viewable from a position of safety. Predicted consequence: heightened arousal; appropriate in dramatic landscape design (e.g., overlooks, scenic balconies); maladaptive in everyday environments where it produces background anxiety.
```

---

## 4. File Location Convention

All lens files live in `/Users/oracle/Documents/vault/Lenses/`. The filename is `<lens-id>.md`, where `<lens-id>` is the kebab-case identifier declared in the YAML frontmatter and matches the value of `lens_id`. There are no subdirectories — the directory is flat. The flat structure permits simple referencing from mode files (a single relative path) and simple verification (one directory listing covers the entire library).

Existing prose lenses already living in `/Users/oracle/Documents/vault/Lenses/` (100 files as of 2026-05-01) use a legacy frontmatter format (`title`, `nexus: mental-model`, `type: engram`, `domain`, `triggers`) and a four-section body (`## Core Principle`, `## When to Apply`, `## How to Apply`, `## Example`). These migrate to the uniform structure during Phase 5. The migration mapping is straightforward:

- `title` → `name`
- `nexus: mental-model` → `lens_type: mental-model` (most cases) or reclassified per Section 1
- `domain` → reflected in tags
- `triggers` → folded into `## Trigger` and `## Detection Signals` sections
- `## Core Principle` → `## Core Structure` (Mental-Model format)
- `## When to Apply` → `## Trigger` and `## Detection Signals`
- `## How to Apply` → `## Application Steps`
- `## Example` → folded into `## Core Structure` (worked-example sketch)

New lenses (the 17 foundational and ~20 mode-specific not yet in the library) are built directly to the uniform structure during Phase 5.

---

## 5. Mode Reference Mechanism

Modes reference lenses through the `lens_dependencies` block in the mode YAML frontmatter (see `Reference — Mode Specification Template.md` §7). The block has three fields:

- **`required`** — lens_ids that must be available in `/Users/oracle/Documents/vault/Lenses/` for this mode to dispatch. If a required lens is missing, the orchestrator refuses to dispatch the mode and reports the missing dependency. Example: Wicked Problems Analysis requires `rittel-webber-wicked-characteristics`, `meadows-twelve-leverage-points`, `senge-system-archetypes`.

- **`optional`** — lens_ids the mode uses if available but does not require. Optional lenses are typically conditional ("when artifact is a strategy document"); the YAML may include a parenthetical condition next to the lens_id. Example: Cui Bono optionally uses `rumelt-strategy-kernel` when the artifact is a strategy document.

- **`foundational`** — lens_ids of foundational lenses (those with `foundational: true`) that the mode draws on. Foundational lenses are globally available; this list is for transparency, not gating. Every mode that does cross-mode bias-checking lists `kahneman-tversky-bias-catalog` here.

The `lens_id` value matches the filename in `/Users/oracle/Documents/vault/Lenses/` without the `.md` extension. The verification script checks: every `lens_id` referenced in any mode's `lens_dependencies` exists as a file in `Lenses/`; conversely, every lens file in `Lenses/` is referenced by at least one mode's `applicability` field (orphan lenses are flagged).

### Cross-reference: `applicability` (in lens) vs. `lens_dependencies` (in mode)

The reference is bidirectional and must be consistent:

- A lens declares which modes use it: `applicability: [<mode_ids>]` in its YAML.
- A mode declares which lenses it uses: `lens_dependencies.{required, optional, foundational}: [<lens_ids>]` in its YAML.

The verification script enforces: for every `(mode_id, lens_id)` pair, both directions of the reference exist or both are absent. One-sided references are flagged.

---

## 6. "Do Not Build as Mode" Inventory

Per research report §10.1, the following analytical operations are *not* built as modes in the Ora registry. They are analytical primitives whose appropriate home is the lens library; modes that need them invoke them as lens dependencies.

### Verification findings (run 2026-05-01 against `/Users/oracle/Documents/vault/Lenses/`)

A directory listing was performed against `Lenses/` searching for filenames matching `swot`, `porter`, `five.forces`, `pros.cons`, and `brainstorm`. None of these patterns matched. Of the 100 existing lens files, none cover these five primitives.

| Operation | Disposition | Verification | Phase 5 action |
|---|---|---|---|
| **SWOT analysis** | Build as lens (`lens_type: catalog` — four-quadrant pattern) | Absent from `Lenses/` as of 2026-05-01 | Build new in Phase 5. Filename `swot.md`. Cite Humphrey 1960s SRI work; Andrews 1971. |
| **Decision Tree** | Already exists as `decision-trees.md` (legacy `mental-model` format) | Present (legacy format) | Convert to uniform structure in Phase 5 as `lens_type: mental-model` (or reclassify to `protocol` if the decision-procedure framing dominates — flag during conversion). |
| **Pros and Cons** | Do not build. Covered by composition: Benefits + Red Team + Balanced Critique modes produce the same analytical product with stronger structure. | N/A — explicit non-build | Document non-build decision in Phase 5 build plan; no file created. |
| **Brainstorming** | Do not build. Absorbed into T20 specificity variants (Passion Exploration, etc.) which carry the generative-mode posture. | N/A — explicit non-build | Document non-build decision; no file created. |
| **Porter's Five Forces** | Build as lens (`lens_type: strategic-framework` — five named forces as components) | Absent from `Lenses/` as of 2026-05-01 | Build new in Phase 5. Filename `porters-five-forces.md`. Cite Porter 1979/1980. Used by T3 strategy modes and T15 commercial-strategy reads. |

Two new lens files (`swot.md`, `porters-five-forces.md`) are added to the Phase 5 build plan as a result of this verification. One existing lens (`decision-trees.md`) is queued for conversion. The two non-build decisions (Pros and Cons, Brainstorming) are documented but produce no artifact.

### Why these are lenses, not modes

These five operations share three properties that disqualify them as modes: (1) they have no distinctive mode-template fields beyond what their host modes already supply (no distinct critical-question set, no distinct failure-mode catalog tied to the operation itself); (2) they are reused across territories rather than belonging to one home territory (SWOT in T3 and T15; Porter in T3 and T15; Decision Tree in T6 and T7); (3) they have a structured artifact form (matrix, tree, force-diagram) rather than an analytical posture. Lenses are the right home for structured analytical artifacts that multiple modes invoke; modes are the right home for analytical postures with their own critical-question sets.

---

## 7. Phase 5 Build Plan Cross-Reference

Phase 5 (per `Reference — Implementation Plan` Phases 1–7) builds the lens library in this order:

1. **Foundational lenses (17 files).** The lenses in research report §12.1 (Walton schemes, Toulmin model, Pearl ladder, Heuer ACH, Tetlock ten commandments, Meadows leverage points, Senge archetypes, Rittel-Webber wicked characteristics, Ulrich CSH, Lakoff frames, Stanley propaganda, Rumelt kernel, Fisher/Ury principles, Taleb fragility, Kahneman-Tversky bias catalog, Knightian risk/uncertainty/ambiguity, Gallie essentially contested concepts). Each built directly to the uniform structure with its appropriate `lens_type`.

2. **Mode-specific lenses (~20 files).** The lenses in research report §12.2 (Bernays/Ellul/Herman-Chomsky propaganda models, Goffman/Entman framing, Pearl do-calculus, Bennett-Checkel process tracing, fallacy taxonomy, Mill's principle of charity, CIA Tradecraft adversary modeling, Klein pre-mortem, Brier scoring, Wack/Schwartz scenario planning, AHP/SMART/ELECTRE multi-criteria, Dixit-Pindyck real options, Cappelen conceptual engineering, Gallie-extension definitional dispute, Lax-Sebenius integrative-distributive, Schelling strategic interaction, Taleb convex-concave fragility audit, plus T19 aesthetic traditions). Each built to the uniform structure.

3. **New "do not build as mode" lenses (2 files).** `swot.md` and `porters-five-forces.md` from Section 6.

4. **Existing prose-lens conversions (~100 files).** The 100 lenses already in `Lenses/` migrate from legacy mental-model prose format to the uniform structure per the migration mapping in Section 4. Most retain `lens_type: mental-model`; a minority reclassify (e.g., `decision-trees.md` may move to `protocol` if conversion surfaces that the procedural framing dominates).

Total Phase 5 scope: ~120–140 lens artifacts (17 foundational + ~20 mode-specific + 2 new "do not build" + ~100 conversions).

The verification script run at the end of Phase 5 enforces: every lens file conforms to the uniform structure (frontmatter + 7 sections); every `lens_id` referenced by any mode exists; every lens file is referenced by at least one mode's `applicability` field; no `lens_type` value is outside the closed taxonomy in Section 1.

---

*End of Reference — Lens Library Specification.*
