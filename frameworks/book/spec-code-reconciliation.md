---
title: Spec-Code Reconciliation Framework
nexus: ora
type: engram
writing: no
date created: 2026/04/06
date modified: 2026/04/06
framework_version: 1.0
execution_tier: agent
pipeline_step: standalone
---

# Spec-Code Reconciliation Framework

*A framework for backward-reconciling installer specifications with the actual installed system, then producing a natural language system specification from which the installer could be derived.*

---

## PURPOSE

This framework takes a divergent system — where the running installation no longer matches the installer specifications that originally created it — and produces three outputs: (1) a complete discrepancy report documenting every difference between what the installer says and what the filesystem contains, (2) updated installer layers that would produce the current system if executed on a fresh machine, and (3) a natural language system specification — a single document describing the complete system in plain English, from which the installer layers could be derived.

The framework exists because debugging changes code without updating specifications. Every fix, feature addition, and structural change that happens after initial installation creates drift between the spec and the system. If natural language is source code, a specification that describes a system that doesn't exist is a bug in the source code.

## INPUT CONTRACT

Required:
- **Installer manifest**: `installer/install-manifest.md`. Source: repository. Provides the ordered list of all installer layers and their declared purposes.
- **Installer layers**: All files listed in the manifest (Phase 1 Layers 1–7, Hardware Gate, Phase 2 Layers 1–12, Appendix). Source: `installer/` directory. Each layer contains processing instructions, expected output format, and verification criteria.
- **Installed filesystem**: The live `~/ora/` directory and its contents. Source: filesystem traversal.
- **Git history**: The commit log from initial installation to present. Source: `git log` in the repository root. Provides a chronological record of what changed and why.
- **System file structure reference**: `Reference — System File Structure.md` (in the vault). Source: most recently updated reference document describing the current system.

Optional:
- **Pending reconciliation notes**: `~/ora/reconciliation/pending/*.md`. Source: session-end change lists from prior sessions. Default behavior if absent: the framework operates without them, relying on filesystem comparison and git history instead.
- **Previous sweep reports**: `~/ora/reconciliation/sweeps/*.md`. Source: prior reconciliation sweep outputs. Default behavior if absent: this is treated as the first reconciliation.

## OUTPUT CONTRACT

Primary outputs:
- **Discrepancy Report**: Markdown document saved to `~/ora/reconciliation/sweeps/[date]_sweep-report.md`. Lists every difference between installer specifications and the installed system, categorized by severity (STRUCTURAL, BEHAVIORAL, COSMETIC) and by drift type (bug-fix drift, design-change drift, accretion drift). Quality threshold: every file governed by an installer layer is accounted for — no silent omissions.
- **Updated Installer Layers**: Modified versions of each installer layer file that would produce the current system if executed on a fresh machine. Saved in-place (overwriting the current layer files). Quality threshold: a hypothetical fresh install from the updated layers would produce a system functionally identical to the current one.
- **Natural Language System Specification**: A single document saved to `~/ora/installer/system-specification.md`. Written in plain English, it describes the complete system — its architecture, every component, every configuration structure, every behavioral contract — at sufficient fidelity that a competent AI agent reading only this document could produce the installer layers. Quality threshold: the specification-to-installer derivation path is unambiguous. No implementation detail of the running system is left undocumented.

Secondary outputs:
- **Drift Inventory**: A structured list of all drift items discovered, embedded in the Discrepancy Report. Each item identifies the drift type, source layer, affected files, and resolution applied.
- **Reconciliation Log**: Appended to the Discrepancy Report. Timestamped record of each comparison performed and each update applied, creating an audit trail.

## EXECUTION TIER

Agent mode. This framework requires filesystem access, git access, and the ability to read and write files. The processing layers execute sequentially with explicit handoffs.

Available tools and trigger conditions:
- **file_read**: Read any file from the workspace or vault. Trigger: when comparing installer layer content against actual file content.
- **file_write**: Write updated installer layers, the discrepancy report, and the system specification. Trigger: when a layer update or output document is ready.
- **bash**: Execute shell commands for filesystem traversal, git log queries, and structural verification. Trigger: when comparing directory structures, checking file existence, or querying commit history.
- **glob**: Find files by pattern. Trigger: when scanning for files that an installer layer references.
- **grep**: Search file contents. Trigger: when checking whether specific configuration keys, function names, or structural elements exist in the codebase.

This framework is agent-only; single-pass execution is not supported because filesystem access and git history consultation are intrinsic to Layers 1, 3, and 4. In a non-agent context, the framework produces only a reconciliation plan (methodology and questions for manual operator execution), not the three concrete deliverables.

---

## MILESTONES DELIVERED

This framework's declaration of the project-level milestones it can deliver. Used by the Problem Evolution Framework (PEF) to invoke this framework for milestone delivery under project supervision.

### Milestone Type: Full backward-reconciliation bundle
- **Endpoint produced:** Three-document bundle written to disk — (1) Discrepancy Report at `~/ora/reconciliation/sweeps/[date]_sweep-report.md` with severity-classified (STRUCTURAL/BEHAVIORAL/COSMETIC) and drift-typed (bug-fix/design-change/accretion) findings plus embedded Drift Inventory and Reconciliation Log; (2) Updated Installer Layers written in-place over the current layer files; (3) Natural Language System Specification at `~/ora/installer/system-specification.md`
- **Verification criterion:** All seven Evaluation Criteria score 3 or above; every installer layer has been parsed and every file under `~/ora/` is accounted for in at least one of the three outputs; a hypothetical fresh install from the updated layers would produce a system functionally identical to the current one; the Derivation Notes section in the specification maps every major section to the installer layer it would generate
- **Preconditions:** Installer manifest, all installer layer files, live `~/ora/` filesystem, git history from initial installation to present, and the System File Structure reference are all accessible to the agent
- **Mode required:** Full Reconciliation (Layers 1–7)
- **Framework Registry summary:** Backward-reconciles installer specifications with the installed system and produces a derivable natural language system specification

### Milestone Type: Discrepancy report and resolution plan
- **Endpoint produced:** Scoped diagnostic output covering a single installer layer (or named layer subset) — Structural Inventory Table, Behavioral Comparison Report with severity and drift-type classifications, and Resolution Plan naming the specific text changes needed for each discrepancy. No installer layer files are modified and no system specification is produced.
- **Verification criterion:** Every file the targeted installer layer references has been compared to the filesystem; every discrepancy has a severity, a drift type, and a resolution decision (code-is-correct / spec-is-correct / both-update / new-content) with justification referencing git commits where applicable; the layer-one and layer-two invariant checks both pass
- **Preconditions:** The targeted installer layer file(s), the relevant live filesystem subtree, and git history for the affected files are all accessible; the user names the specific layer(s) to be reconciled
- **Mode required:** Partial Reconciliation (Layers 1–3, single-layer scope)
- **Framework Registry summary:** Diagnoses spec-code drift for a named installer layer without modifying layers or producing a system specification

### Milestone Type: Natural language system specification
- **Endpoint produced:** `~/ora/installer/system-specification.md` — a declarative natural language document describing the current system's architecture, component catalog, configuration architecture, behavioral contracts, dependency map, and hardware adaptation, with a Derivation Notes section mapping specification sections to the installer layers they would generate
- **Verification criterion:** An AI agent given only the specification can determine complete directory structure, every file to create, every dependency to install, every configuration schema, and every behavioral contract needed to produce the installer layers; Evaluation Criterion 4 (Specification Derivability) scores 3 or above; every claim in the specification corresponds to something verifiable on the filesystem or in the code
- **Preconditions:** The installer layers under `~/ora/installer/` are treated as current (no reconciliation is performed); the live `~/ora/` filesystem and the System File Structure reference are accessible
- **Mode required:** Specification Only (Layer 5)
- **Framework Registry summary:** Produces a natural language system specification from current installer layers and the live filesystem

---

## EVALUATION CRITERIA

This framework's output is evaluated against these 7 criteria. Each criterion is rated 1–5. Minimum passing score: 3 per criterion.

1. **Coverage Completeness**
   - 5 (Excellent): Every file in every installer layer is accounted for in the discrepancy report. Every file on the filesystem that should be governed by an installer layer is identified. No gaps.
   - 4 (Strong): All major components covered. One or two minor utility files may be missed but no functional code is unaccounted for.
   - 3 (Passing): All installer layers are compared. Files created by accretion drift (never in any installer layer) may be incompletely cataloged.
   - 2 (Below threshold): Multiple installer layers are compared only superficially — checking file existence but not file content or behavioral correspondence.
   - 1 (Failing): Entire installer layers are skipped or major filesystem areas are not examined.

2. **Drift Classification Accuracy**
   - 5 (Excellent): Every discrepancy is correctly classified by severity (STRUCTURAL/BEHAVIORAL/COSMETIC) and drift type (bug-fix/design-change/accretion). The classification directly informs the correct resolution action.
   - 4 (Strong): Classifications are correct for all STRUCTURAL and BEHAVIORAL items. A few COSMETIC items may be misclassified.
   - 3 (Passing): STRUCTURAL items are correctly identified. Some BEHAVIORAL items may be classified as COSMETIC or vice versa, but no STRUCTURAL drift is missed.
   - 2 (Below threshold): Severity ratings are inconsistent. Some STRUCTURAL drift is classified as BEHAVIORAL or COSMETIC.
   - 1 (Failing): No systematic classification is applied. Discrepancies are listed without severity or drift type.

3. **Installer Layer Fidelity**
   - 5 (Excellent): Each updated installer layer, if executed on a fresh machine, would produce files and configurations functionally identical to the current system. No behavioral differences would exist.
   - 4 (Strong): Updated layers would produce a functionally correct system. Minor differences in file comments, whitespace, or non-functional content may exist.
   - 3 (Passing): Updated layers would produce a working system. Some configuration details might require manual adjustment after fresh install.
   - 2 (Below threshold): Updated layers contain significant gaps — entire features or components would be missing from a fresh install.
   - 1 (Failing): Updated layers still describe the old system. Little or no reconciliation was applied.

4. **Specification Derivability**
   - 5 (Excellent): The natural language system specification could be handed to a competent AI agent with no other context, and that agent could produce installer layers that build the current system. The derivation path is explicit and unambiguous.
   - 4 (Strong): The specification covers all major components with sufficient detail for derivation. One or two minor implementation details would require inference.
   - 3 (Passing): The specification describes the system's architecture and major components. Some implementation details are implicit rather than explicit, but the overall derivation path is clear.
   - 2 (Below threshold): The specification is a high-level overview. Significant implementation detail is missing. An agent would need to make substantial design decisions not covered by the spec.
   - 1 (Failing): The specification is too vague to derive an installer from. It reads as marketing copy rather than a technical specification.

5. **Atomicity of Updates**
   - 5 (Excellent): Every installer layer update is paired with its corresponding discrepancy report entry. The relationship between "what changed" and "why it changed" is explicit and traceable.
   - 4 (Strong): Updates are paired with report entries. A few minor updates lack explicit justification but are self-evident from context.
   - 3 (Passing): All significant updates have corresponding report entries. Minor updates may be batched.
   - 2 (Below threshold): Updates are applied in bulk without clear mapping to specific discrepancies.
   - 1 (Failing): Installer layers are rewritten without documentation of what changed or why.

6. **Completeness of Accretion Capture**
   - 5 (Excellent): Every file, feature, and configuration that exists in the running system but was never in any installer layer is identified, documented, and added to the appropriate installer layer. No "dark matter" — no unaccounted functionality.
   - 4 (Strong): All functional code and user-facing features added by accretion are captured. Some internal implementation details (logging, error handling improvements) may be noted but not fully specified.
   - 3 (Passing): Major accretion items are captured. Some minor utility scripts or configuration additions may be missed.
   - 2 (Below threshold): Only obvious accretion items are captured. The system has significant functionality not reflected in any installer layer.
   - 1 (Failing): Accretion drift is not systematically addressed. The installer layers still describe only the original system.

7. **Resolution Correctness**
   - 5 (Excellent): For every discrepancy, the correct resolution is applied: spec updated to match code (when code is right), code flagged for correction (when spec is right), or both updated (when the discrepancy revealed a design issue). No "Spec Nostalgia" — no blind defaulting to "the code is right."
   - 4 (Strong): Resolutions are correct for all STRUCTURAL and BEHAVIORAL items. Each resolution includes explicit justification.
   - 3 (Passing): Resolutions are provided for all items. Most are correct, but one or two may default to "update spec to match code" without explicitly verifying that the code's behavior is intentional.
   - 2 (Below threshold): Resolutions are inconsistent. Multiple items resolved by fiat without analysis.
   - 1 (Failing): No systematic resolution process. Installer layers are updated without determining whether the code or the spec is correct.

---

## NAMED FAILURE MODES

### Quick Fix Amnesia
Small bug fixes — a one-line WebSocket timeout change, a CSS overflow fix, a conditional for an edge case — that are individually trivial but collectively represent the difference between a system that works and a system that doesn't. These fixes are the hardest to capture because they feel too small to document. **Countermeasure:** Layer 1 of this framework performs file-level diffing, not just structural comparison. If a file's content differs from what the installer would produce, the diff is captured regardless of size.

### Spec Nostalgia
Updating the spec to match the code when the code is actually wrong — it runs, but it's not what was intended. The code works by accident or workaround, and blessing it as correct locks in the workaround. **Countermeasure:** Layer 3 forces an explicit "which is correct?" decision for every discrepancy, with a third option ("both need updating") that surfaces design problems.

### The Regeneration Trap
Handing stale specifications to an AI for code generation, faithfully reproducing bugs that were already fixed. This is the terminal failure mode — the reason the reconciliation framework exists. **Countermeasure:** The framework's Output Contract requires that updated installer layers are the final deliverable. No stale spec survives the process.

### Accretion Blindness
Features added during implementation that were never in any installer layer — error handling, UI polish, performance optimizations, entirely new tools. These features are invisible to a spec-only audit because no spec exists to be wrong. They can only be found by comparing the filesystem against the spec's total coverage. **Countermeasure:** Layer 2 scans the filesystem for files that no installer layer references, and Layer 3 explicitly addresses each one.

### Template Drift
The `endpoints.json.template` or other config templates in the repository diverge from what the running system actually uses. Template files are documentation of the config structure — if the running config has keys the template doesn't list, fresh installs will produce incomplete configurations. **Countermeasure:** Layer 1 compares template files against their running counterparts.

### Governance Gaps
Code files that no specification governs. These files are invisible to any reconciliation process because there's nothing to reconcile against. **Countermeasure:** Layer 2's filesystem scan identifies ungoverned files. Layer 4 assigns every file to an installer layer, closing all governance gaps.

### The Cosmetic Trap
Treating a BEHAVIORAL difference as COSMETIC because the surface appearance is similar. A function that was renamed and reimplemented looks cosmetically different but is behaviorally different — and if the installer still references the old function name, a fresh install breaks. **Countermeasure:** The severity classification in Layer 3 requires checking whether the difference affects behavior, not just appearance.

---

## LAYER 1: STRUCTURAL INVENTORY

**Stage Focus**: Build a complete inventory of what the installer says should exist versus what actually exists on the filesystem. This is mechanical comparison — existence, naming, and location — not behavioral analysis.

**Input**: Installer manifest, all installer layer files, live filesystem.

**Output**: A Structural Inventory Table with four columns: (1) Component (file or directory), (2) Installer Layer (which layer specifies it), (3) Installer Says (path, name, purpose per the spec), (4) Filesystem Says (actual path, actual state, actual content hash). Plus a list of Unmatched Filesystem Items — files that exist but no installer layer references.

### Processing Instructions

1. Parse the installer manifest to extract the ordered list of all layers.

2. For each installer layer file, extract every file and directory it specifies. Record:
   - The exact path the layer says should exist
   - The purpose/description the layer gives for that file
   - Any specific content the layer mandates (config structure, function signatures, specific strings)
   - Any verification criteria the layer defines

3. For each specified file/directory, check the actual filesystem:
   - Does it exist at the specified path?
   - If it exists, what is its actual content? (For code files, read the file. For directories, list contents.)
   - If it exists at a different path, note the path discrepancy.
   - If it doesn't exist, note the absence.

4. Scan the live filesystem (`~/ora/`) recursively. For every file found, check whether any installer layer references it. Files not referenced by any layer are added to the Unmatched Filesystem Items list.

5. Compare config templates against running configs:
   - `config/endpoints.json.template` (if it exists) against `config/endpoints.json`
   - `config/interface.json` against the schema in Layer 10
   - `config/browser-models.json` against the schema implied by Layer 9 / the model switcher

6. Compare directory structure against Layer 2's specification:
   - Every directory Layer 2 says should exist — does it?
   - Every directory that exists — did Layer 2 create it, or was it added later?

### Output Formatting for This Layer

```
## Structural Inventory

### Specified Components
| Component | Layer | Spec Path | Actual Path | Status |
|-----------|-------|-----------|-------------|--------|
| [file]    | P1-L2 | ~/ora/modes/ | ~/ora/modes/ | MATCH |
| [file]    | P2-L11| ~/ora/ai.app/ | ~/ora/ai.app/ | MATCH |
| [file]    | P1-L7 | ~/ora/server/start-server.sh | — | MISSING |
...

### Unmatched Filesystem Items
| Path | Type | Probable Purpose |
|------|------|-----------------|
| ~/ora/models.app/ | directory | Model updater app bundle (not in any layer) |
...

### Config Template Comparison
| Template | Running Config | Discrepancies |
|----------|---------------|---------------|
...
```

**Variable State**:
- file inventory size: [count of files scanned under workspace root]
- layer count discovered: [count of installer layers parsed from the manifest]
- workspace root: [current value]
- manifest path: [current value]

**Invariant check before proceeding:** Confirm that every installer layer has been parsed and every file in `~/ora/` has been checked against the inventory. If any layer was skipped or any filesystem subtree was not scanned, halt and report the gap.

---

## LAYER 2: BEHAVIORAL COMPARISON

**Stage Focus**: For every component where the structural inventory shows a MATCH (file exists at the expected path), compare what the installer says the file should do against what the file actually does. This is semantic comparison — behavioral correspondence, not just existence.

**Input**: Structural Inventory Table from Layer 1, installer layer files, actual file contents.

**Output**: A Behavioral Comparison Report listing every behavioral discrepancy with severity classification.

### Processing Instructions

1. For each MATCH item in the Structural Inventory Table, read both the installer layer's description of that file and the file's actual contents.

2. Compare along these dimensions:
   - **Architecture**: Does the file implement the architecture the layer describes? (e.g., Layer 7 says "Flask server with SSE streaming" — does `server.py` use Flask and SSE?)
   - **Features**: Does the file implement all features the layer specifies? Does it implement features the layer doesn't specify?
   - **Configuration structure**: Do config files match the schemas the layers define?
   - **Dependencies**: Does the file use the dependencies the layer says to install?
   - **Verification criteria**: Would the file pass the layer's own verification tests as written?

3. For each discrepancy found, classify it:
   - **STRUCTURAL**: The file implements a fundamentally different architecture than the layer describes. (e.g., the layer says "overnight batch processing" but the code does inline processing.)
   - **BEHAVIORAL**: The file's behavior differs from the layer's description, but the architecture is the same. (e.g., the layer says "five panel types" but the code implements four.)
   - **COSMETIC**: Naming, formatting, or organizational differences that don't affect function. (e.g., the layer says `start-server.sh` but the file is named `start.sh`.)

4. For each discrepancy, also classify the drift type:
   - **Bug-fix drift**: The code was changed to fix a bug. The layer still describes the buggy behavior.
   - **Design-change drift**: A design decision changed after the layer was written. The layer describes the old design.
   - **Accretion drift**: The code has features the layer never specified.

5. For MISSING items from the Structural Inventory: classify as either "correctly removed" (the feature was deprecated) or "incorrectly absent" (the feature should exist but doesn't).

6. For Unmatched Filesystem Items: determine which installer layer should govern each one, or whether it's an implementation detail that needs no layer.

### Output Formatting for This Layer

```
## Behavioral Comparison Report

### Discrepancies

#### [SEVERITY] [Layer Reference]: [Brief Description]
- **Drift type**: [bug-fix | design-change | accretion]
- **Installer says**: [quote or paraphrase from the layer]
- **System does**: [description of actual behavior]
- **Affected files**: [list]
- **Resolution needed**: [spec-to-code | code-to-spec | both | new-layer-needed]

...

### Summary
- STRUCTURAL discrepancies: [count]
- BEHAVIORAL discrepancies: [count]
- COSMETIC discrepancies: [count]
- Accretion items (ungoverned features): [count]
```

**Invariant check before proceeding:** Confirm that every MATCH item has been behaviorally compared and every MISSING and Unmatched item has been classified. If any items remain unexamined, halt and report.

---

## LAYER 3: RESOLUTION DECISIONS

**Stage Focus**: For every discrepancy identified in Layer 2, make an explicit resolution decision. This is the judgment layer — it determines whether the spec or the code is correct, or whether both need updating.

**Input**: Behavioral Comparison Report from Layer 2, installer layer files, actual file contents, git history.

**Output**: A Resolution Plan — an ordered list of specific changes to make to each installer layer, with justification.

### Processing Instructions

1. For each discrepancy in the Behavioral Comparison Report, consult the git history to understand why the code diverged:
   - `git log --oneline -- [affected file]` to see the commit history
   - Read commit messages to determine whether the change was intentional (feature addition, design decision) or incidental (quick fix, debugging artifact)

2. For each discrepancy, answer three questions explicitly:
   a. **Which is correct?** The installer layer's description, the code's actual behavior, or neither (both need updating).
   b. **Why?** One sentence justifying the decision. Reference git commits where applicable.
   c. **What changes?** The specific text in the installer layer that must be modified, added, or removed.

3. Apply these resolution rules:
   - **Code is correct, spec is wrong** (most common): The code was fixed or improved after the layer was written. Update the layer to describe what the code does. This is the standard case.
   - **Spec is correct, code is wrong** (rare): The code regressed or a fix introduced a new problem. Update the specification only when the code is verifiably correct. When the code is broken, flag it for correction and leave the specification unchanged pending the fix.
   - **Both need updating**: The divergence reveals a design problem. Write the spec to describe the system as it *should* work, then flag any code changes needed to match the cleaned-up spec.
   - **New layer content needed**: For accretion items that no layer covers, determine which existing layer should absorb the feature, or whether a new layer is needed.

4. Order the resolution plan by installer layer (Phase 1 Layer 1 through Phase 2 Layer 12) so updates can be applied systematically.

5. **Guard against Spec Nostalgia:** For every "code is correct" resolution, verify that the code's behavior is genuinely intentional, not just functional-by-accident. Check git commit messages for intent. If there's ambiguity, classify as "both need updating" and flag for human review.

### Output Formatting for This Layer

```
## Resolution Plan

### Phase 1, Layer [N]: [Layer Name]

#### Resolution [number]: [Brief description]
- **Discrepancy**: [reference to Layer 2 report]
- **Decision**: [code-is-correct | spec-is-correct | both-update | new-content]
- **Justification**: [one sentence, with git commit reference if applicable]
- **Layer change**: [specific text to add/modify/remove in the installer layer]

...

### Accretion Items — Layer Assignment

| Item | Assigned Layer | Action |
|------|---------------|--------|
| models.app/ | P2-L11 (App Bundle) | Add section for model updater bundle |
| config/themes/*.css heading colors | P2-L10 (Interface) | Add heading color specification |
...
```

**Variable State**:
- code-is-correct resolutions: [count]
- spec-is-correct resolutions: [count]
- both-update resolutions: [count]
- new-content resolutions: [count]
- drift severity summary: STRUCTURAL [count] / BEHAVIORAL [count] / COSMETIC [count]

**Invariant check before proceeding:** Confirm that every discrepancy from Layer 2 has a resolution decision. No discrepancy may be left unresolved. If any remain, halt and list them.

---

## LAYER 4: INSTALLER LAYER UPDATES

**Stage Focus**: Apply the Resolution Plan from Layer 3 to each installer layer file, producing updated layers that would generate the current system.

**Input**: Resolution Plan from Layer 3, current installer layer files.

**Output**: Updated installer layer files written in-place. A change log documenting every modification made to each file.

### Processing Instructions

1. Process installer layers in order (Phase 1 Layer 1 through Phase 2 Layer 12, then manifest and appendix).

2. For each layer, apply all resolutions from the Resolution Plan that target that layer:
   - Modify processing instructions to describe current behavior
   - Update file paths, names, and directory structures
   - Add accretion items assigned to this layer
   - Update verification criteria to test current behavior
   - Update output format sections to reflect current outputs
   - Remove references to deprecated or deleted components

3. Maintain the layer's existing structure and voice. Updates should read as if the layer was originally written to produce the current system, not as if patches were bolted on.

4. For each layer update, record in the change log:
   - What was changed (old text → new text, summarized)
   - Which resolution drove the change
   - Whether the change is STRUCTURAL, BEHAVIORAL, or COSMETIC

5. Update the installer manifest (`install-manifest.md`) to reflect any changes to layer names, purposes, or ordering.

6. After updating all layers, perform a cross-layer consistency check:
   - File paths referenced in multiple layers must be consistent
   - Configuration structures described in multiple layers must agree
   - Dependencies installed in early layers and used in later layers must still match
   - Verification criteria in later layers must not reference components that earlier layers no longer create

### Output Formatting for This Layer

```
## Installer Update Log

### [Layer identifier]: [Layer name]
- [Change 1]: [brief description] (Resolution [ref])
- [Change 2]: [brief description] (Resolution [ref])
...

### Cross-Layer Consistency Check
- [Pass/Fail]: [description of any inconsistencies found and resolved]

### Summary
- Layers modified: [count] / [total]
- Resolutions applied: [count]
- Cross-layer inconsistencies found and fixed: [count]
```

**Invariant check before proceeding:** Confirm that every resolution from the Resolution Plan has been applied to the appropriate layer. If any resolutions remain unapplied, halt and report.

---

## LAYER 5: NATURAL LANGUAGE SYSTEM SPECIFICATION

**Stage Focus**: Produce a single natural language document that describes the complete system at sufficient fidelity that an AI agent reading only this document could derive the installer layers.

**Input**: Updated installer layers from Layer 4, live filesystem, system file structure reference.

**Output**: `~/ora/installer/system-specification.md` — the natural language system specification.

### Processing Instructions

1. **This document is not a reformatted installer.** The installer is a sequence of imperative instructions ("create this directory, write this file, install this package"). The system specification is a declarative description ("the system consists of these components, organized this way, with these relationships, producing these behaviors"). The specification describes *what exists and why*. The installer describes *how to build it*.

2. Structure the specification as follows:

   **System Identity**: What the system is, who it's for, what it does. One paragraph.

   **Architecture Overview**: The major subsystems and how they relate. This is the map — the reader should understand the system's shape before encountering any detail.

   **Component Catalog**: For each component (directory, major file, configuration structure), document:
   - What it is
   - What it does (behavioral contract)
   - What it depends on (upstream requirements)
   - What depends on it (downstream consumers)
   - What configuration governs it
   - How it was designed to fail (error handling, fallback behavior)

   **Configuration Architecture**: Every configuration file, its schema, its purpose, and what reads it. This section should be detailed enough that someone could write the config files from scratch.

   **Behavioral Contracts**: The system's major behavioral promises — what happens when the user does X. This includes the pipeline flow, the UI interactions, the model switching protocol, the conversation persistence system, and any other user-facing behavior.

   **Dependency Map**: Every external dependency (Python packages, system tools, services) with version requirements and what breaks if it's absent.

   **Hardware Adaptation**: How the system adapts to different hardware tiers. What changes between Tier 0 and Tier C. What remains constant.

3. Write in the present tense, declarative voice. "The server listens on port 5000" not "Start the server on port 5000." The specification describes a system that exists, not instructions for building one.

4. Every claim in the specification must correspond to something verifiable on the filesystem or in the code. Describe only features that currently exist on the filesystem. Limit claims to verifiable system state.

5. The specification must be complete enough that the following derivation test passes: An AI agent given only the system specification (not the installer layers) should be able to:
   - Determine the complete directory structure
   - Determine every file that needs to be created and what it contains
   - Determine every dependency that needs to be installed
   - Determine every configuration structure and its schema
   - Determine the behavioral contracts the system must fulfill
   - Produce installer instructions that would build this system

6. Include a section header "Derivation Notes" at the end that explicitly maps major specification sections to the installer layers they would generate. This makes the spec-to-installer derivation path visible.

### Output Formatting for This Layer

The system specification is a standalone Markdown document with YAML frontmatter:

```yaml
---
title: Local AI System Specification
nexus: ora
type: engram
writing: no
date created: [today]
date modified: [today]
specification_version: 1.0
derived_from: installed system as of [today]
---
```

Sections use H2 for major divisions, H3 for components within divisions, H4 for sub-components. No section should exceed 200 lines — if it does, split it.

**Invariant check before proceeding:** Confirm that every major section of the natural-language system specification traces to at least one installer layer or filesystem artifact; that no claim in the specification lacks a verifiable referent; and that the Derivation Notes section maps every H2 section back to its source. If any section fails traceability, halt and report the failing sections.

---

## LAYER 6: SELF-EVALUATION

**Stage Focus**: Evaluate all output produced in Layers 1 through 5 against the Evaluation Criteria defined above.

**Calibration warning**: Self-evaluation scores are systematically inflated. Research finds LLMs are overconfident in 84.3% of scenarios. A self-score of 4/5 likely corresponds to 3/5 by external evaluation standards. Score conservatively. Articulate specific uncertainties alongside scores.

For each criterion:
1. State the criterion name and number.
2. Wait — verify the current output against this specific criterion's rubric descriptions before scoring.
3. Identify specific evidence in the output that supports or undermines each score level.
4. Assign a score (1–5) with cited evidence from the output.
5. IF the score is below 3, THEN:
   a. Identify the specific deficiency with a direct quote or reference to the deficient passage.
   b. State the specific modification required to raise the score.
   c. Apply the modification.
   d. Re-score after modification.
6. IF the score meets or exceeds 3, THEN confirm and proceed.

After all criteria are evaluated:
- IF all scores meet threshold, THEN proceed to the Output Formatting layer.
- IF any score remains below threshold after one modification attempt, THEN flag the deficiency explicitly in the output with the label UNRESOLVED DEFICIENCY and state what additional input or iteration would be needed to resolve it.

---

## LAYER 7: ERROR CORRECTION AND OUTPUT FORMATTING

**Stage Focus**: Final verification, mechanical error correction, and output formatting for delivery.

### Error Correction Protocol

1. Verify variable fidelity. Confirm that the installer manifest path, workspace root, vault path, conversations path, and every installer layer file path defined in the Persistent Reference Document appear unchanged in every output document that references them. If any variable has been silently dropped, conflated, or simplified, restore it.
2. Verify factual consistency across all output documents. The discrepancy report, the updated installer layers, and the system specification must not contradict each other. If the discrepancy report says "models.app added to Layer 11," then Layer 11 must contain models.app, and the system specification must describe models.app.
3. Verify path consistency. Every file path that appears in any output document must be the same path. No document should reference a path that another document spells differently.
4. Verify completeness. Every file in `~/ora/` must appear in at least one of: an installer layer, the system specification, or the discrepancy report's "ungoverned files" section.
5. Verify the installer manifest matches the updated layers — layer names, purposes, and ordering must all agree.
6. Document all corrections made in a Corrections Log appended to the discrepancy report.

### Output Formatting

All output documents use Markdown with:
- YAML frontmatter per the vault standard (nexus, type, writing, dates)
- H2 for major sections, H3 for subsections
- Tables for structured comparisons
- Code blocks for file paths, commands, and configuration snippets
- No emoji unless present in the original installer layers

### Missing Information Declaration

Before finalizing output, explicitly state:
- Any installer layer whose intent could not be determined from the layer text alone
- Any file on the filesystem whose purpose could not be determined from the file contents or git history
- Any behavioral comparison where the installer layer's description was too vague to compare against the actual code

### Recovery Declaration

IF the Self-Evaluation layer flagged any UNRESOLVED DEFICIENCY, THEN restate each deficiency here with:
- The specific criterion that was not met
- What additional input, iteration, or human judgment would resolve it
- Whether the deficiency affects the reliability of the updated installer layers or the system specification

---

## AGENT EXECUTION METADATA

### Stage Boundaries

This framework executes in three stages with context window resets between them.

**Stage 1: Inventory and Comparison (Layers 1–2)**
Execute Layers 1 and 2 in a single inference session. These layers require simultaneous access to installer layers and filesystem contents.
Handoff to Stage 2: The complete Structural Inventory Table and Behavioral Comparison Report.

**Stage 2: Resolution and Update (Layers 3–4)**
Execute Layers 3 and 4 in a single inference session. These layers require the comparison reports from Stage 1 plus git history access.
Handoff to Stage 3: Updated installer layers (written to disk), Resolution Plan, and Installer Update Log.

**Stage 3: Specification and Verification (Layers 5–7)**
Execute Layers 5, 6, and 7 in a single inference session. Layer 5 reads the updated installer layers from disk (written by Stage 2) and the live filesystem. Layers 6 and 7 evaluate and finalize all outputs.
Handoff: Final outputs written to disk.

### Persistent Reference Document

Injected into every stage's context window:

```
RECONCILIATION OBJECTIVE: Backward-reconcile the installer specifications
with the installed system. Produce three outputs: (1) discrepancy report,
(2) updated installer layers, (3) natural language system specification.

CONSTRAINT: The system specification must be derivable into installer
layers without additional information. If the specification is not
sufficient to derive the installer, the reconciliation is incomplete.

SCOPE: ~/ora/ directory and all installer layer files in
installer/phase1/ and installer/phase2/.

NAMED VARIABLES: installer manifest path, workspace root, vault path,
conversations path, all installer layer file paths.
```

### Checkpoint Protocol

At each stage boundary:
1. Write the stage's output to `~/ora/reconciliation/sweeps/[date]_stage-[N]-output.md`.
2. Log stage completion with timestamp.
3. IF stage output fails the invariant check, THEN retry the stage once with the deficiency flagged. IF retry fails, THEN halt and surface the failure with the label STAGE FAILURE.

---

## EXECUTION COMMANDS

### Step 0 — Input validation

Before invoking the framework, verify that every required input from the Input Contract is accessible and well-formed. (a) Installer manifest exists and parses. (b) Every layer file named in the manifest exists on disk. (c) The workspace root is readable and contains the expected directory structure. (d) Git history is available and reaches the initial installation commit. (e) `Reference — System File Structure.md` in the vault is present. If any input is missing or ambiguous, declare the gap explicitly, document the assumption you will make if proceeding, and proceed only after the user confirms. If an input's absence makes the framework non-executable (e.g., the installer manifest is missing), halt and report.

### Full Reconciliation

Load this framework into a Claude Code session with access to `~/ora/`. Execute:

> "Run the Spec-Code Reconciliation Framework. The workspace is ~/ora/. The installer layers are in ~/ora/installer/. Compare every installer layer against the actual filesystem and produce all three outputs: discrepancy report, updated installer layers, and natural language system specification."

### Partial Reconciliation (single layer)

> "Run Layers 1–3 of the Spec-Code Reconciliation Framework for installer layer [phase]/[layer filename] only. Produce the discrepancy report and resolution plan for that single layer. Do not update the layer or produce the system specification."

### Specification Only (skip reconciliation)

> "Run Layer 5 of the Spec-Code Reconciliation Framework. The installer layers in ~/ora/installer/ are assumed to be current. Produce the natural language system specification from the current installer layers and filesystem."

---
