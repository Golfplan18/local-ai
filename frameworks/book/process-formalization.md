# Framework — Process Formalization

## Display Name

Process Formalization (PFF)

## Display Description

Design, convert, render, and audit AI instruction frameworks. Default output is a single consolidated framework file (single-pass rendering, which is the canonical exchange format because it runs both inside Ora and outside it). Four modes: F-Design (new framework), F-Convert (existing → current standard), F-Render (produce additional execution variants on explicit request — opt-in), F-Audit (review).

_A Meta-Framework for Formalizing Domain Expertise into Executable AI Specifications_

_Version 2.5_

_v2.5 formalizes reusable procedures as exact versioned Process Definitions over the domain-general graph grammar, replaces Multi-stage runtime renderings with bounded-judgment and multi-stage runtime projections, and requires all seven Process Run directives with final-only ACCEPT. v2.4 added domain-neutral formalization of externally acting process applications, preserved PIF-inferred verification boundaries, and defined the standalone human-readable PROCESS APPLICATION CONTRACT in §2.13._

_v2.3 update: semantically reconciled the two competing v2.2 canonicals. The full milestone, anatomy, recovery, rendering, variable-fidelity, and CFF/OFF integration specification was preserved together with the single-file default, approval gates, audit nuance, quality bars, and operational safeguards. At the v2.3 release, this file and its Ora runtime mirror were exact body copies._

_v2.2 update: consolidated single-file output is now the default for F-Design and F-Convert. Additional execution variants (multi-stage-runtime, reasoning-model) are produced only when explicitly requested with stated rationale, per the user's strong preference against file profusion. v2.1 baseline incorporated research-backed findings from "Best Practices for Multi-Step AI Prompting" (Appendix)._

---

## Setup Questions

### Mode

Required. Which of the four PFF operations: F-Design (create a new framework from a task description; default output is one consolidated framework file), F-Convert (modernize an existing framework against the current standard; default output is one consolidated framework file), F-Render (produce an additional execution variant from an existing framework — opt-in path), or F-Audit (review an existing framework for quality issues).

### Task description — for F-Design

Required for F-Design. Description of the task or domain you want a framework for. The more concrete, the better — name the deliverable, the stakeholders, and the hard requirements.

### Existing framework — for F-Convert, F-Render, F-Audit

Required for F-Convert, F-Render, and F-Audit. The framework spec (paste the content, attach the file, or provide a vault path).

### Target execution tier — for F-Render

Required for F-Render. The additional rendering you want produced beyond the default consolidated file: `multi-stage` (multi-model execution with stages and tools) or `reasoning-model` (simplified for o3/o4/DeepSeek-R1). For backward compatibility with PFF v2.1 split-artifact frameworks, `single-pass` is also accepted as a target. The legacy value `specification` is accepted only when reconstructing an older v2.1-style canonical spec from a v2.2 consolidated file; new work should not produce specification-tier files.

### Rationale for additional variant — for F-Render

Required for F-Render. Explain why the consolidated single-file is insufficient and why the requested variant is the right fit. This rationale is a file-proliferation gate: PFF never produces additional variants merely because it can.

### Existing display name and display description

Optional for F-Convert and F-Audit. Provide existing picker copy so PFF can preserve, correct, or improve it instead of silently replacing it.

### Quality bar

Optional. Select `production-ready`, `draft`, or `rough sketch`. Defaults to `production-ready`; Section XII defines each threshold.

### Constraints

Optional. State scope, length, format, audience, prohibited behavior, and any other boundaries the framework must honor.

### PIF formalization handoff

Optional for F-Design and F-Convert. Provide the Process Inference Framework's Formalization Handoff Package, including Process Capability Requirements and Verification-Boundary Map, when available. PFF preserves these requirements or records an explicit reason for each material change.

### External effects and authorization

Optional. Identify external artifacts or state the framework's process reads or changes, consequential actions it may perform, and permission, reversibility, or terminal-proof requirements. If absent and the task implies external effects, PFF elicits them before architecture design.

### Evidence, identity, and independent review

Optional. Identify available checks, evidence providers, identity providers, independent reviewers, final gates, and review-cost constraints. If absent, PFF may formalize symbolic requirements but must mark concrete bindings unresolved.

## How to Use This File

This is a meta-framework — a framework for creating frameworks. It serves four functions:

1. **Design new frameworks from scratch** by following the Framework Design Process (Section IV). Default output: one consolidated framework file.
2. **Convert existing frameworks** to the current standard by following the Conversion Protocol (Section VI). Default output: one consolidated converted framework file.
3. **Render an additional execution variant** (multi-stage runtime or reasoning-model) from an existing consolidated framework file by following the Rendering Protocol (Section V). This is the explicit opt-in path for producing extra rendering files beyond the consolidated default.
4. **Audit existing frameworks** against the quality standard by following the Quality Verification Checklist (Section VII).

Paste this entire file into any AI session — commercial (Claude, ChatGPT, Gemini) or local multi-model runtime model — then provide your input below the USER INPUT marker at the bottom. State which function you need, or the AI will determine it from context.

**Standalone-use invariant:** This consolidated Markdown file is the complete executable Process Formalization Framework. No Ora service, Python module, parser, registry, runtime adapter, or machine-readable configuration is required to interpret or apply it. Runtime identifiers may be recorded as optional bindings, but complete process meaning, authorization, evidence, boundary, loop, transition, and final-gate requirements remain human-readable in the framework itself. When a concrete provider or independent reviewer is unavailable, preserve the symbolic requirement and disclose the assurance limit rather than inventing a binding.

**Mode F-Design:** You have a task that needs a framework. You will describe what the framework must accomplish, what inputs it receives, and what outputs it produces. The AI will guide you through the full design process and produce **one consolidated framework file** — the single-pass rendering, which contains all the canonical intellectual content and runs in commercial AI without further packaging. This is the default. If you have a concrete reason to also produce an multi-stage-runtime or reasoning-model rendering (e.g., this framework will run on the Mac Studio multi-model runtime with tool access), state that reason explicitly and additional renderings will be produced as separate files. The AI may surface a recommendation to render an additional variant, but always presents it as a choice and never produces multiple files by default.

**Mode F-Convert:** You have an existing framework that needs modernization. Paste the old framework as input. The AI will analyze it against the current standard, identify gaps, and produce **one consolidated updated framework file** conforming to the Framework Anatomy and Authoring Standards defined here. Same single-file default as F-Design — additional execution variants only on explicit request with stated rationale.

**Mode F-Render:** You have an existing consolidated framework file (or a canonical specification from a prior PFF version) and need an _additional_ execution variant generated from it. This is the explicit opt-in path for producing extra renderings beyond the default consolidated file. Paste the framework as input and state which variant you need (multi-stage runtime for multi-model execution, reasoning-model for o3/R1, or another single-pass rendering if you are deriving from an older split-artifact framework). The output is one additional file.

**Mode F-Audit:** You have a framework (new or converted) and want it evaluated against the standards in this document. Paste the framework as input. The AI will score it against the Quality Verification Checklist and provide specific remediation recommendations.

---

## Table of Contents

- Section I: Governing Principles
- Section II: Framework Anatomy — The Structural Standard
- Section III: Framework Authoring Standards — Language and Convention
- Section IV: Framework Design Process — Creating a New Framework
- Section V: Rendering Protocol — Generating Execution Variants
- Section VI: Conversion Protocol — Modernizing Existing Frameworks
- Section VII: Quality Verification Checklist
- Section VIII: Named Failure Modes in Framework Design
- Section IX: Reference Examples — Structural Patterns
- Section X: Integration with CFF and OFF
- Section XI: Execution Commands
- Section XII: Operational Safeguards and Reference

---

## MILESTONES DELIVERED

This framework's own declaration of the substantial results it can deliver. Governed Process Runs and users use this declaration to bind reviewable boundaries; PEF may be one caller when a genuinely contingent interim-goal contract selects formalization.

PFF is a multi-mode framework. The four modes (F-Design / F-Convert / F-Render / F-Audit) deliver different milestones along independent paths. F-Design is decomposed at four substantive verification boundaries; the other three modes each produce one independently reviewable final result. All milestone properties are defined inline per milestone per the inline-properties principle.

### Milestones for Mode F-Design

#### Milestone 1: Requirements Gathered

- **Mode:** F-Design
- **Endpoint produced:** A complete requirements record covering: final user-facing deliverable; mode structure; routing layer (if any); PIF handoff (if supplied); verification-boundary map; per-mode milestone breakpoints; input inventory; quality definition; failure modes; pipeline position; standalone execution; external artifacts and state; authorized actions; evidence, identity, loop, transition, and final-gate needs; domain expertise; precedents; proactive gap assessment; and complexity assessment.
- **Verification criterion:** Every question 1-10 in Phase 1 has a recorded answer; externally acting process requirements and unresolved bindings are explicit; every PIF-proposed verification boundary is preserved or has a Boundary Change Rationale; every preserved boundary is placed as a formal milestone or process-internal verification point; the proactive gap and complexity assessments were confirmed; if the framework is multi-mode, each mode has its own boundary-placement map and milestone breakdown; M0 routing (if present) was identified per Step C.
- **Layers covered:** Phase 1 (Requirements Gathering and Proactive Elicitation)
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** Structured Phase 1 record with one section per question 1-10 in the Question Sequence.
- **Drift check question:** Do the captured requirements faithfully reflect the user's stated task without injected framework defaults the user did not confirm, and do the proactive gap items reflect the user's actual problem space rather than generic patterns?
- **Independent review examines:** The requirements record, supplied PIF handoff, recorded unresolved bindings, and user confirmations.
- **Required evidence:** Complete Phase 1 response record; explicit applicability decision for Section 2.13; user acceptance of proactive gaps and complexity assessment.
- **Failure route:** Return to the unresolved Phase 1 question or boundary decision; withhold architecture design until corrected.
- **Boundary rationale:** Requirements must be reviewable before criteria and architecture are designed because later discovery of missing authority, evidence, or scope would invalidate both.

#### Milestone 2: Evaluation Criteria and Architecture Designed

- **Mode:** F-Design
- **Endpoint produced:** Numbered evaluation criteria (7-12) with five-level rubrics; processing architecture with layer structure, handoffs, preserved or explicitly revised verification boundaries, formal project milestones, process-internal verification points, optional runtime stage boundaries, invariant checks, anti-drift anchors, named failure modes, recovery protocol, and—when applicable—planning/execution nodes plus acceptance, artifact identity, authorization, evidence, bounded-loop, transition, and final-gate contracts.
- **Verification criterion:** Quality, anti-failure, integration, capability-binding, evidence-sufficiency, boundary-quality, and standalone-use dimensions that apply are represented; criteria count is 7-12 with five-level rubrics; layers map to criteria; handoffs declare what each layer produces, consumes, and discards; each changed PIF boundary has a rationale; the architecture was accepted before Phase 4.
- **Layers covered:** Phase 2 (Evaluation Criteria Design), Phase 3 (Architecture Design)
- **Required prior milestones:** M1
- **Gear:** 4
- **Output format:** Numbered criteria list with rubrics + textual architecture description with layer structure + handoff table + named failure modes inventory + recovery protocol per failure point.
- **Drift check question:** Do the evaluation criteria collectively cover the quality, anti-failure, and integration dimensions captured in M1, and does the architecture map every criterion to a producing layer with explicit handoffs?
- **Independent review examines:** The criteria-to-requirements trace, processing architecture, verification boundaries, Boundary Change Rationales, and process application semantics.
- **Required evidence:** M1 requirements record; criterion coverage map; layer and handoff map; accepted boundary architecture; user architecture approval.
- **Failure route:** Return to Phase 2 for criterion gaps or Phase 3 for architecture, boundary, or contract gaps.
- **Boundary rationale:** Architecture is the last low-cost point to correct missing criteria, unsafe unreviewed spans, or unsupported capabilities before full specification drafting.

#### Milestone 3: Canonical Specification Drafted

- **Mode:** F-Design
- **Endpoint produced:** Full canonical framework specification conforming to Framework Anatomy (Section II), including the human-readable §2.13 PROCESS APPLICATION CONTRACT when the applicability test identifies an externally acting process.
- **Verification criterion:** Every applicable Section II subsection (2.1-2.13) is present or explicitly justified as omitted; Milestones Delivered uses the inline-properties schema and boundary rules; any PROCESS APPLICATION CONTRACT is complete and standalone; the Authoring Standards are applied; invariant checks and named failure modes are present.
- **Layers covered:** Phase 4 (Specification Drafting)
- **Required prior milestones:** M2
- **Gear:** 4
- **Output format:** Full markdown specification document following the structure defined in Section II.
- **Drift check question:** Does the drafted specification faithfully implement the architecture from M2 and satisfy the requirements from M1, without introducing scope, criteria, or layers that were not part of the design?
- **Independent review examines:** The full Markdown specification against M1 requirements, M2 architecture, Section II, and Section III.
- **Required evidence:** Requirements-to-specification trace; architecture-to-section trace; Section 2.13 applicability record and completed contract when applicable.
- **Failure route:** Return to the affected Phase 4 drafting step; return to M2 only when the approved architecture itself is inadequate.
- **Boundary rationale:** Canonical meaning must be accepted before rendering so format conversion cannot conceal substantive omissions or boundary drift.

#### Milestone 4: Consolidated Framework File Rendered and Verified

- **Mode:** F-Design
- **Endpoint produced:** **One consolidated framework file** rendered from the M3 specification draft, applying the Single-Pass Rendering Protocol (Section 5.1) so the file is both the canonical intellectual source and a self-contained executable in commercial AI. The single-pass rendering is the canonical exchange format because it is what runs outside Ora and is how frameworks are shared with others. Verification against the Section VII Quality Verification Checklist is performed and presented inline (not as a separate persistent file) showing pass on every applicable item. Framework Registry entry produced. **Additional renderings (multi-stage-runtime, reasoning-model) are produced only when the user explicitly requested them in Phase 1 Question 6 with stated rationale, or when the AI surfaces a recommendation that the user accepts**; in those cases each additional rendering is a separate file beyond the default.
- **Verification criterion:** The consolidated framework file passes every applicable Section VII category, including Process Application Contract Compliance when §2.13 applies; all runtime bindings remain optional supplements to complete natural-language meaning; any additional rendering preserves the contract; the Framework Registry entry accurately compresses the framework's milestones and capabilities.
- **Layers covered:** Phase 5 (Rendering), Phase 6 (Verification)
- **Required prior milestones:** M3
- **Gear:** 4
- **Output format:** One consolidated framework file at its target path + inline Section VII audit summary + Framework Registry entry. Additional rendering files only if explicitly requested.
- **Drift check question:** Does the consolidated framework file faithfully express every operational directive from the M3 specification draft, pass all applicable Quality Verification Checklist items, and avoid producing additional rendering files that the user did not explicitly request? Is the Framework Registry entry's Delivers summary an accurate compression of the framework's actual milestones?
- **Independent review examines:** The rendered consolidated file, source-to-render preservation, applicable Section VII results, file count, and Framework Registry entry.
- **Required evidence:** Passing checklist verdicts with locations; M3-to-render comparison; file inventory; registry-entry comparison.
- **Failure route:** Return to Phase 5 for rendering defects, M3 for source defects, or the registry-entry step for metadata defects; withhold delivery until all applicable items pass.
- **Boundary rationale:** This is the independent final gate because it verifies both canonical meaning and deliverable integrity before the framework is represented as complete.

### Milestones for Mode F-Convert

#### Milestone 1: Modernized Framework Specification

- **Mode:** F-Convert
- **Endpoint produced:** Updated canonical framework spec conforming to the current Framework Anatomy and Authoring Standards; intellectual content preservation cross-check confirming no original substance was lost; updated Framework Registry entry reflecting any changed Delivers content; conversion change-log enumerating what was added, modified, restructured, or removed relative to the prior version.
- **Verification criterion:** All applicable Section VII items pass; original intellectual content and any existing process-application meaning are preserved; the Section VI phases complete; milestone boundaries are preserved or explicitly re-justified; legacy schemas are converted without inventing providers or authority.
- **Layers covered:** Section VI (Conversion Protocol — 6.1 Analysis Phase, 6.2 Conversion Phase, 6.3 Verification Phase)
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** Updated canonical framework specification document plus a conversion change-log noting what was added, modified, restructured, or removed.
- **Drift check question:** Does the modernized framework preserve every piece of original intellectual content while conforming to current Authoring Standards, and does it correctly use the inline-properties schema for any milestones declared?
- **Independent review examines:** The source framework, converted framework, change log, boundary-preservation record, and Section VII audit.
- **Required evidence:** Source-to-conversion content trace; Boundary Change Rationales where applicable; passing checklist verdicts; user-approved conversion scope.
- **Failure route:** Return to Section 6.1 for missed source meaning or Section 6.2 for conversion defects; withhold the converted result until corrected.
- **Boundary rationale:** Conversion is accepted only after preservation and current-standard compliance can be judged together on the completed artifact.

### Milestones for Mode F-Render

#### Milestone 1: Additional Rendered Execution Variant

- **Mode:** F-Render
- **Endpoint produced:** One new framework file rendered from an existing consolidated framework file (the canonical single-pass file from PFF v2.2 onward, or a legacy canonical specification from v2.1 and earlier) into the requested target environment (multi-stage-runtime, reasoning-model, or — in the legacy case — a single-pass file derived from a v2.1 split-artifact framework). This is an opt-in additional artifact beyond the consolidated default.
- **Verification criterion:** The rendered variant passes the rendering-specific checks; every operational directive and any PROCESS APPLICATION CONTRACT remain complete; runtime worker mechanics may supplement but never replace the standalone natural-language contract.
- **Layers covered:** Section V (Rendering Protocol — 5.1 Single-Pass Rendering Protocol, 5.2 Multi-Stage Runtime Rendering Protocol, or 5.3 Reasoning-Model Rendering Protocol per target; plus 5.4 Rendering Order if the user explicitly requests more than one additional rendering in the same F-Render invocation)
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** One additional framework file in the target environment's expected format.
- **Drift check question:** Does the rendered variant preserve every operational directive from the source framework while honoring the target environment's specific rendering rules, and does it pass the rendering-specific compliance checks for that environment?
- **Independent review examines:** The source framework, rendered variant, target-specific compliance results, and PROCESS APPLICATION CONTRACT preservation when applicable.
- **Required evidence:** Source-to-render directive trace; applicable rendering checklist results; provider-binding and boundary-preservation check.
- **Failure route:** Return to the selected Section V rendering protocol; withhold the variant until source meaning and target rules both pass.
- **Boundary rationale:** A variant becomes usable only when an evaluator can verify that execution-specific adaptation preserved the complete canonical contract.

### Milestones for Mode F-Audit

#### Milestone 1: Framework Audit Report

- **Mode:** F-Audit
- **Endpoint produced:** Scored audit report documenting framework compliance against the Quality Verification Checklist (Section VII) with pass/fail per checklist item, specific location identification for each failure, and concrete remediation recommendations.
- **Verification criterion:** Every Section VII checklist item received a pass/fail verdict; every failure cites the specific location in the framework being audited where the failure occurs; every failure is paired with a concrete remediation recommendation rather than a generic suggestion; the audit covers Structural Completeness, Milestones Delivered Compliance, Input/Output Integrity, Evaluation Architecture, Language Compliance, Anti-Drift Compliance, Think-Then-Format Compliance, Variable Fidelity Compliance, Anti-Confabulation Compliance, Recovery Compliance, Process Application Contract Compliance when applicable, applicable rendering compliance categories, Backward Compatibility, and Proactive Elicitation Compliance.
- **Layers covered:** Section VII (Quality Verification Checklist application)
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** Markdown audit report with verdict-per-item, location citations, and remediation recommendations.
- **Drift check question:** Does the audit report assign verdicts to every checklist item, cite specific locations for failures rather than generic claims, and provide concrete remediation rather than vague exhortations?
- **Independent review examines:** The audited framework, complete checklist verdict set, cited evidence, and remediation specificity.
- **Required evidence:** One verdict per applicable checklist item; exact location for every failure; concrete correction for every flag or failure.
- **Failure route:** Return to the omitted or weak checklist assessment; withhold the audit verdict until coverage and evidence are complete.
- **Boundary rationale:** The audit report is itself the independently reviewable final result of F-Audit and must be complete before its conclusions can guide changes.

---

## Section I: Governing Principles

These principles govern all framework design decisions. When a design choice is ambiguous, resolve it by reference to these principles in priority order.

### 1. Specification Is the Control Surface

A framework is a natural language specification. It is not code, not a suggestion, and not a style guide. The framework defines what happens, in what order, with what inputs, producing what outputs, meeting what standards. The AI's role is execution, not interpretation. Every instruction that requires interpretation is an instruction that will be interpreted differently by different models, producing inconsistent results.

**Design implication:** Prefer explicit directives over implied expectations. Prefer concrete criteria over qualitative descriptions. Prefer enumerated options over open-ended guidance.

### 2. Separation of Intellectual Content from Execution Environment

The intellectual content of a framework — what it accomplishes, what quality standards govern it, what evaluation criteria apply — is independent of how it executes. The same intellectual content can render into a single-pass framework for commercial AI, an multi-stage runtime file for a local multi-model runtime, a reasoning-model profile, or any future execution environment.

**The default consolidated framework file (single-pass rendering) IS the canonical specification.** They are not separate artifacts. The single-pass rendering preserves all intellectual content while being directly executable in commercial AI, which is the primary distribution context. This consolidation is the v2.2 default. multi-stage-runtime and reasoning-model renderings, when needed, are produced as additional separate files on explicit request — they do not displace the consolidated default.

**Design implication:** Do not embed execution-environment assumptions into the framework's intellectual layers. Stage boundaries in the framework are logical, not mechanical. Whether a stage boundary becomes an actual context window reset (multi-stage runtime) or remains a conceptual division within a single pass (commercial mode, the default) is a rendering decision, not a design decision. Complete process meaning remains in human-readable Markdown. Provider names, tool names, runtime identifiers, and runtime worker mechanics are optional bindings or execution enhancements; they never substitute for the natural-language requirements they implement. Tool-dependent steps must degrade gracefully when tools are absent.

### 3. Minimum Information Forward

At every stage boundary, carry forward only the information the next stage requires to do its job correctly. Discard everything else. Context debt — accumulated irrelevant information — degrades output quality in proportion to its volume. This principle applies within a framework (between layers/stages) and between frameworks (between pipeline steps).

Research confirms this principle quantitatively: a 2025 study of 18 frontier models found that adding full conversation history (~113,000 tokens) dropped accuracy by 30% compared to a focused 300-token version. LLM reasoning degrades at approximately 3,000 tokens of accumulated context even when within the model's stated context window. LLMs can identify irrelevant content but cannot reliably ignore it during generation. Signal-to-noise ratio, not context capacity, determines output quality.

**Design implication:** Every stage must declare its output contract — what it produces that downstream stages consume. Every stage must declare its input contract — what it requires from upstream. The intersection of these contracts defines the handoff. Anything not in the handoff is discarded.

### 4. Named Failure Modes Over General Caution

A model told "be careful about X" will be careful sometimes and not other times, unpredictably. A model told "the specific failure mode here is [name]: [description of what goes wrong and why]" will watch for that pattern reliably. Named failure modes are more effective than general quality exhortations because they give the model a concrete pattern to match against.

Research on LLM attention mechanisms confirms the mechanism: during generation, models emit "anchor tokens" that are repeatedly attended to by subsequent positions, stabilizing reasoning. Named concepts in prompts become these anchor tokens. When a failure mode is named "The Drift Trap," that name becomes a retrievable reference point the model's attention mechanism repeatedly activates during generation. Named concepts create cognitive hooks; general caution does not.

**Design implication:** Every framework must include a Named Failure Modes section listing the specific ways that framework's output typically goes wrong. Generic quality language ("ensure high quality," "maintain consistency") is prohibited. Replace it with specific failure modes and their correction protocols.

### 5. Evaluation Is Architecture, Not Afterthought

Evaluation criteria are not appended to a framework after design — they are the framework's structural skeleton. The evaluation criteria define what "correct output" means. The processing layers exist to produce output that meets those criteria. Design the evaluation criteria first, then design the processing layers to satisfy them.

**Design implication:** The Framework Design Process begins with output requirements and evaluation criteria. Processing layers are derived from criteria, not the reverse.

### 6. Anti-Confabulation by Design

AI models do not have a hard stop when information is missing. They generate plausible-sounding output regardless of factual grounding. Framework design must assume this behavior and architect against it. Three mechanisms apply universally:

- **Explicit instruction:** Direct the model to state what information is missing rather than filling gaps with assumptions.
- **Named failure mode:** Identify the specific confabulation risk for each stage ("The most common error at this stage is presenting assumed information as retrieved fact").
- **Structured output with confidence indicators:** Force the model to evaluate its own certainty before producing output.

### 7. Progressive Disclosure Over Monolithic Instruction

A framework with 50 instructions presented simultaneously competes with itself for the model's attention. A framework with 5 stages of 10 instructions each, where each stage focuses attention on its specific task, produces better results. This is true even in single-pass execution — the model processes sequentially and benefits from staged focus.

Research validates this directly: Anthropic's context engineering research found that "giving LLMs more context often makes them perform worse, not better, in instruction-following tasks." Bounded worker-call architectures that return condensed summaries (1,000–2,000 tokens from 10,000+ token explorations) outperform monolithic context injection.

**Design implication:** Organize framework instructions into discrete layers/stages with clear focus boundaries. Each stage should be comprehensible on its own terms without requiring the model to hold all other stages in active attention simultaneously.

### 8. Backward Compatibility

A framework designed for multi-stage runtime execution must degrade gracefully to single-pass execution. A framework designed for a two-model adversarial pipeline must degrade gracefully to single-model execution. Multi-stage-runtime metadata (tool definitions, checkpoint protocols, stage boundary markers) is ignored by commercial AI in single-pass mode, and this is by design. No framework should require a specific execution environment to produce useful output. When an unavailable tool, identity provider, evidence provider, or independent reviewer weakens assurance, the framework preserves the requirement, marks the binding unresolved or unavailable, and discloses the resulting limit. It must not present reduced assurance as equivalent completion.

### 9. Recovery Is Architecture, Not Exception Handling

Contracts that specify only what must be true — preconditions, postconditions, quality thresholds — are incomplete. A complete contract also specifies what happens when violations occur. Bounded behavioral-contract research proved mathematically that if recovery rate exceeds natural drift rate, behavioral drift is bounded. The key parameter in controlling drift is not the quality of the original instructions but the speed and specificity of recovery when drift occurs.

**Design implication:** Every framework must specify recovery protocols at two levels. At the layer level: what happens when a layer's output fails its local quality check (retry with flagged deficiency, halt and report, or proceed with explicit acknowledgment). At the framework level: what happens when the Self-Evaluation layer identifies an unresolvable deficiency (flag for human review, specify what additional input would resolve it, or identify which upstream layer needs rework).

### 10. Complexity-Appropriate Design

Not every task benefits from full multi-layer decomposition. Research on budget-aware evaluation (EMNLP 2024) found that excessive decomposition produces diminishing returns and can decrease performance. Simple chain-of-thought with self-consistency is extremely competitive against more complex multi-step strategies for straightforward tasks.

Empirical evidence converges on a practical complexity ceiling of approximately 10–12 processing layers within a single context window, beyond which anti-drift techniques become essential and performance degrades noticeably. This ceiling varies by model capability and task complexity.

**Design implication:** The Framework Design Process includes a complexity assessment that routes simple tasks to fewer layers. A three-layer framework (Input Validation, Core Processing, Self-Evaluation + Output) is a legitimate and often optimal design for straightforward tasks. Layer count should match task complexity, not a target architecture. When a framework exceeds 10–12 layers for single-pass execution, split it into multiple execution stages (multi-stage runtime) or a multi-pass sequence with explicit carry-forward specifications.

---

## Section II: Framework Anatomy — The Structural Standard

Every framework, regardless of its purpose, conforms to this structural standard. Sections may be minimal for simple frameworks or extensive for complex ones, but the structure is invariant. Omitting a section is an explicit design decision documented with rationale, not a silent absence.

### 2.1 YAML Frontmatter

```yaml
---
title: [Framework Name]
nexus: [project or domain]
type: engram
writing: [no | value from controlled vocabulary]
date created: [YYYY/MM/DD]
date modified: [YYYY/MM/DD]
framework_version: [semantic version]
execution_tier: [specification | single-pass | multi-stage | reasoning-model]
pipeline_step: [step number if part of a multi-step pipeline, or "standalone"]
---
```

The `execution_tier` property identifies the document's role:

- `single-pass` — **The default value for consolidated framework files** (v2.2 default). Self-contained framework executable in commercial AI, contains all canonical intellectual content. This is the canonical exchange format and is what runs both inside and outside Ora.
- `multi-stage` — Rendered for multi-model execution with stage boundaries, tool access, and state management. Produced as an additional file only on explicit request.
- `reasoning-model` — Rendered for reasoning-specialized models (o3, o4, DeepSeek R1) with simplified instruction profile. Produced as an additional file only on explicit request.
- `specification` — Legacy value retained for backward compatibility with frameworks designed under PFF v2.1 and earlier, where the canonical specification was a separate file from the renderings. New frameworks should not use this value; the single-pass file IS the canonical specification.

The `pipeline_step` property identifies the framework's position in a multi-step pipeline, or "standalone" if the framework operates independently.

YAML frontmatter is navigation metadata only. Keep process capability requirements, authorization rules, evidence requirements, identity requirements, verification boundaries, loop policies, transitions, and final-gate semantics in the Markdown body. A YAML identifier may point to a body-defined element, but YAML must not be the only place where an operational requirement is expressed.

### 2.2 Framework Header Block

The header block appears immediately after frontmatter. It provides the AI with essential orientation before any processing begins.

```
# [Framework Name]

## Display Name
[Short picker-friendly name, 60 char limit. Used in the framework picker row title and the bridge-zone label when this framework is invoked.]

## Display Description
[Brief description, 500 char limit. 2–4 sentences. Used in the framework picker dropdown row to tell the user what this framework produces and when to pick it.]

## Setup Questions
[Optional but strongly recommended for user-pickable frameworks. Structured list of inputs this framework needs, consumed by the framework setup popup (V3 Input Handling Phase 7) to detect missing inputs deterministically. Each question is an `### Name` heading whose body's first sentence flags `Required.` or `Optional.`; the rest of the body is the description shown to the user.

When a framework declares this section, the popup uses it directly. When absent, the popup falls back to LLM-driven analysis of the `## INPUT CONTRACT` section below.

Mode-conditional questions are written as `Required for [mode-name] mode.` and the analyzer handles the conditional logic against the user's chosen mode.]

## PURPOSE
[One to three sentences. What this framework produces and why it exists.
Name the deliverable concretely, not the aspiration.]

## INPUT CONTRACT
[Explicit enumeration of every input this framework requires.
For each input: name, format, source, and whether required or optional.]

## OUTPUT CONTRACT
[Explicit enumeration of every output this framework produces.
For each output: name, format, destination, and quality threshold.]

[For an externally acting process application: state that the output
includes a PROCESS APPLICATION CONTRACT under Section 2.13.]

## EXECUTION TIER
[specification | single-pass | multi-stage | reasoning-model]
[If multi-stage: list of available tools and their trigger conditions.]
[If single-pass: state that all stages execute sequentially in one context window.]
[If reasoning-model: state that instructions are simplified for
internal reasoning models.]
```

**Display Name and Display Description rules:**

- **Display Name** is the picker row title and bridge-zone label. Hard limit 60 characters. Plain text, no Markdown. Should make the framework immediately recognizable to a user scanning the picker. Acronyms in parentheses are encouraged when the framework is commonly referenced by acronym (e.g. "Process Formalization (PFF)").
- **Display Description** is the picker row body. Hard limit 500 characters. 2–4 sentences. Lead with the deliverable; close with when to pick this framework over the alternatives. Plain text, no Markdown.
- Both fields are mandatory for every framework that is user-pickable. Pipeline-internal stage specs (F-* and Phase A) are exempt — they are loaded automatically by the orchestrator and never appear in the picker.
- The picker parser reads these sections by literal heading match. Do not rename, demote to a sub-heading, or add modifiers like `## Display Name (preview)`.

**Input Contract format:**

```
INPUT CONTRACT

Required:
- [Input name]: [format description]. Source: [where it comes from].
- [Input name]: [format description]. Source: [where it comes from].

Optional:
- [Input name]: [format description]. Source: [where it comes from].
  Default behavior if absent: [what the framework does without this input].
```

**Output Contract format:**

```
OUTPUT CONTRACT

Primary outputs:
- [Output name]: [format description]. Destination: [where it goes].
  Quality threshold: [specific measurable criterion].

Secondary outputs (if applicable):
- [Output name]: [format description]. Destination: [where it goes].
```

### 2.3 Milestones Delivered

Every framework that delivers substantial independently reviewable results declares them here. This declaration is a handoff point between a governed Process Run's approved plan and framework execution: the invoking Run uses it to bind the exact result, criteria, evidence, and continuation route. PEF may consume the declaration for a contingent interim goal, but it is not a mandatory wrapper. It is also the structural basis for layered framework execution: the runtime binds each milestone to a declared verification boundary and persists the resulting evidence and transition.

The Milestones Delivered section is required for every framework that exposes substantial result boundaries to a caller or governed Process Run.

**Exemption for pipeline-stage and fixed-sequence frameworks:** Frameworks invoked deterministically as internal steps of an already-approved parent Process Definition are exempt when they expose no independently acceptable result boundary. Examples include the Gear 4 pipeline stage frameworks (F-Analysis-Breadth, F-Analysis-Depth, F-Evaluate, F-Revise, F-Consolidate, F-Verify) and Phase A prompt cleanup. These frameworks produce internal outputs that feed the next declared node; they do not deliver standalone milestones.

Exempt frameworks must declare the exemption explicitly in their Execution Tier section with a statement of the form: _"This framework is an internal step of [Process Definition or pipeline name]; it exposes no independently acceptable result boundary and does not declare Milestones Delivered."_

**Inline-properties principle.** All milestone properties are defined inline within each milestone block — never via shared definitions, factored references, or parent-subsection inheritance. Every property is bound to the specific milestone path it governs. This prevents cross-mode property mismatches and makes each milestone block fully self-contained for the parser.

**Schema:**

```
## MILESTONES DELIVERED

[Optional intro paragraph: what milestones the framework delivers, across how many modes, where drift checks fire.]

### M0: Routing
[Declare ONLY if the framework has a triage / routing / classification layer that fires before mode selection. Skip entirely if the framework has no such layer.]

- **Function:** [what this layer classifies, routes, or gates]
- **Layers covered:** [layer numbers]
- **Output:** [what M0 produces — typically a mode selection plus any classification flag that downstream milestones consume conditionally]

### Milestone N: [Name]

- **Mode:** [mode name (e.g., I-Create, F-Design); for single-mode frameworks, write "all" or omit this property entirely]
- **Endpoint produced:** [concrete artifact or state change this milestone produces]
- **Verification criterion:** [how to objectively determine this milestone is achieved]
- **Layers covered:** [comma-separated layer numbers, e.g., "1, 2" or "3, 4, 5"]
- **Conditional layers:** [OPTIONAL — present only if one or more layers in Layers covered fire conditionally. List the conditional layers and state the activating condition inline. Example: "3, 4, 6 — fire only when M0 classifies tier as Incarnated"]
- **Required prior milestones:** [M-references whose deliverables this milestone consumes. Use "None" for the first milestone. For cross-mode references, prefix with the mode name (e.g., "I-Create.M4")]
- **Gear:** [pipeline gear at which this milestone runs. Default 4]
- **Output format:** [reference to a Layer Output Format block from the framework, or inline description of the deliverable's structure]
- **Drift check question:** [specific question used at this milestone's boundary to detect wandering from the user's original intent — specific enough to surface scope expansion, terminology shift, or premature convergence; not generic]
- **Independent review examines:** [OPTIONAL — required for a verification boundary; the concrete artifact, state, decision, or evidence bundle an independent evaluator reviews]
- **Required evidence:** [OPTIONAL — required for a verification boundary; evidence that must exist before the boundary can be accepted]
- **Failure route:** [OPTIONAL — required for a verification boundary; the named destination or action when acceptance fails]
- **Boundary rationale:** [OPTIONAL — required when the milestone represents a verification boundary; why review belongs here and why adjacent work is not merged into the same unreviewed span]

[Additional Milestone entries follow the same structure with all properties inline. Multi-mode frameworks MAY group milestones under optional `### Milestones for Mode <Name>` subsection headers for human readability — but the parser uses each milestone's inline Mode property as the source of truth, never the parent subsection header.]
```

**Format standards:**

- All milestone properties are defined inline within their milestone block. No factoring, no shared definitions, no parent-subsection inheritance for property values.
- The **Endpoint produced** is a concrete deliverable or state change — a specific artifact, file, or observable change in the system. Abstract outcomes are prohibited.
- The **Verification criterion** must be objectively determinable per the Resolution Statement Objectivity Protocol. Ambiguous quality terms ("good," "robust," "complete") are prohibited unless paired with objective evaluation criteria.
- **Layers covered** lists the processing layers grouped under this milestone. The milestone executor concatenates these layers' instructions into a single pipeline pass.
- **Conditional layers** is optional. Declare only when one or more layers in Layers covered fire conditionally on runtime state — typically a classification produced by M0 or an earlier milestone. State the condition inline so the parser and executor can resolve it without external context.
- **Required prior milestones** lists the prior milestones whose deliverables this milestone consumes. Cross-mode references (rare; usually only the first milestone of a mode pulling from M0) use the mode-prefix syntax `<ModeName>.<MilestoneId>`.
- **Gear** is the pipeline gear at which this milestone runs. Default is Gear 4 (parallel adversarial review with consolidation). Lower gears are acceptable for milestones that only assemble structured data with no synthesis.
- **Output format** can reference an existing Layer Output Format block from the framework rather than duplicate it inline.
- **Drift check question** is asked at the milestone's boundary to detect whether the deliverable still addresses the user's original input.
- **Mode** is required as an inline property when the framework has multiple modes producing different milestone paths. Single-mode frameworks may omit Mode or write "all".
- **Independent review examines**, **Required evidence**, **Failure route**, and **Boundary rationale** are required when a milestone represents a verification boundary. They may be omitted only for legacy milestones that do not claim independent acceptance; F-Design and F-Convert must either formalize them or record why the legacy checkpoint is not a verification boundary.

**Verification-boundary preservation requirement.** When a PIF Formalization Handoff Package includes a Verification-Boundary Map, treat that map as an authoritative design input. Preserve every accepted boundary in one of two formal homes:

1. **Formal milestone:** Use when the boundary accepts a substantial deliverable or state change that the governing Process Run or user can invoke, track, and review as meaningful progress.
2. **Process-internal verification point:** Use when the boundary must gate continuation inside a milestone but the reviewed result is not itself a substantial project-level deliverable. Formalize it in the PROCESS APPLICATION CONTRACT's Verification Boundaries and Transition Policy rather than inflating it into Milestones Delivered.

Classifying a preserved PIF boundary into one of these homes is a placement decision, not a boundary change. Document the placement and rationale. IF the framework designer merges, splits, moves, or removes the substantive review point itself, THEN document a **Boundary Change Rationale** showing that the revision improves observability, independent review, recovery, or review economics without creating an unsafe unreviewed span.

A verification boundary is eligible only when all of the following are true:

- A concrete artifact, external state, decision, or evidence bundle exists to inspect.
- Explicit acceptance criteria can be applied by an identified independent evaluator or by an unresolved-but-required evaluator role.
- Rejection has a defined revision, replanning, escalation, or blocked route.
- The cost or consequence of discovering failure later justifies pausing here.

Processing-layer boundaries, handoffs, runtime stages, tool calls, and convenient file splits do not become verification boundaries merely because they exist. Conversely, a verification boundary remains canonical even when a particular rendering executes several adjacent layers or stages in one context.

**Milestone placement test.** Promote an accepted boundary to a formal milestone only when all of the following are true:

- The accepted result is a durable, substantial project-level deliverable or state change rather than an internal work product.
- The governing Process Run, PEF when contingently invoked, or the user could meaningfully invoke, track, or review completion at that result.
- Acceptance changes project-level progress or authorizes a distinct downstream phase.

IF any condition fails but the boundary still protects downstream work, THEN preserve it as a process-internal verification point in the PROCESS APPLICATION CONTRACT.

**Multi-milestone heuristic.** Layer count is a warning signal, not the source of milestone placement. A mode with more than approximately five processing layers requires an explicit review for missing verification boundaries. Declare multiple milestones only when substantial project-level deliverables pass the Milestone Placement Test. Preserve lower-level but valuable review stops as process-internal verification points. Retain a single milestone when no eligible intermediate project-level deliverable exists, and document that rationale in the Execution Tier section. Never create low-value milestones solely to satisfy a layer-count target.

**Multi-mode frameworks.** Frameworks with multiple modes (e.g., M-Operational / M-Supervised in MOM, or F-Design / F-Convert / F-Render / F-Audit in this framework) declare the milestones for each mode separately, with Mode bound inline to each milestone. M0 routing layers, when present, fire before mode selection and feed the mode classification to downstream milestones via Conditional layers.

**During F-Design:** The designer elicits verification boundaries and classifies each preserved boundary as a formal milestone or process-internal verification point during Phase 1 Question 1. Each formal milestone becomes an entry in this section with all properties inline. Each internal point is carried into the PROCESS APPLICATION CONTRACT when Section 2.13 applies.

**Fixture — one formal milestone containing a distinct process-internal verification point:**

The process produces an approved briefing package. Evidence assembly is independently checked before drafting because bad source identity would contaminate the briefing, but the evidence packet is not a project-level deliverable. The final approved briefing is the formal milestone; the evidence check remains inside it.

```markdown
## MILESTONES DELIVERED

### Milestone 1: Approved Briefing Package

- **Endpoint produced:** A briefing package accepted for authorized release.
- **Verification criterion:** The independent final evaluator confirms that every claim is supported by the verified evidence packet, required sections are present, and no unresolved blocking issue remains.
- **Layers covered:** 1, 2, 3, 4, 5, 6
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** Final briefing package plus final-gate acceptance record.
- **Drift check question:** Does the accepted briefing answer the original brief using only evidence that passed the internal evidence review?
- **Independent review examines:** The final briefing package and its evidence trace.
- **Required evidence:** E-BRIEF-1 and the B-INTERNAL-1 acceptance record.
- **Failure route:** REVISE returns to briefing composition; REPLAN returns to evidence planning; BLOCKED withholds release.
- **Boundary rationale:** The approved briefing is a durable project-level deliverable whose acceptance authorizes a distinct downstream release decision.

## PROCESS APPLICATION CONTRACT

### Verification Boundaries

| Boundary ID | Placement | Containing Milestone | Result Examined | Independent Evaluator Requirement | Acceptance Criteria | Required Evidence | Failure Route | Boundary Rationale | PIF Boundary Status |
|---|---|---|---|---|---|---|---|---|---|
| B-INTERNAL-1 | Process-internal verification point | M1 | Assembled evidence packet | Evidence reviewer independent of assembly | Every source identity is resolved; required coverage is present; unsupported items are removed | E-SOURCE-ID, E-COVERAGE | REVISE → evidence assembly; REPLAN → evidence plan; BLOCKED → withhold drafting | Review protects drafting from contaminated evidence, but the packet is not a substantial project-level deliverable | Preserved |
| B-FINAL-1 | Formal milestone boundary | M1 | Final briefing package | Final evaluator independent of composition | M1 verification criterion passes | E-BRIEF-1, B-INTERNAL-1 acceptance record | REVISE / REPLAN / BLOCKED per M1 | Acceptance completes the project-level deliverable | Preserved |
```

This fixture contains one formal milestone, M1, and one distinct process-internal verification point, B-INTERNAL-1, inside that milestone. B-INTERNAL-1 gates progression from evidence assembly to drafting without becoming a second project milestone.

**Example — Deep Research Protocol (single-mode, multiple intermediate milestones):**

```
## MILESTONES DELIVERED

This framework delivers three sequential milestones. Each milestone is a coherent intermediate deliverable that downstream milestones consume; each is a checkpoint where adversarial review and drift detection fire.

### Milestone 1: Approved Research Plan

- **Endpoint produced:** A research plan containing 3-7 sub-queries; per-sub-query coverage_criterion; per-sub-query source_hints (VAULT_CONTENT first-ranked); stopping_criteria for the run; for caller_context=USER_DIRECT with vague initial query, explicit user approval of the plan structure.
- **Verification criterion:** Every sub-query has a coverage_criterion; every sub-query has source_hints; stopping_criteria declared; sub-queries collectively cover normalized_query without obvious gap; plan_review_status appropriate to caller_context.
- **Layers covered:** 1, 2
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** See Layer 2 Output Format.
- **Drift check question:** Does this research plan address the user's original query without scope expansion into adjacent topics?

### Milestone 2: Evidence Integrated and Iteration Resolved

- **Endpoint produced:** An integrated_evidence_map with one entry per sub-query in research_plan, each carrying deduplicated claims tagged with source class and citations; iteration_decision (CONVERGED, CONVERGED_WITH_GAPS, or BLOCKED).
- **Verification criterion:** Every sub-query in research_plan appears in integrated_evidence_map; every retained claim carries a source-class tag and citation; iteration count did not exceed depth_cap; vault was consulted before external retrieval; iteration_decision is one of CONVERGED, CONVERGED_WITH_GAPS, or BLOCKED.
- **Layers covered:** 3, 4, 5
- **Required prior milestones:** M1
- **Gear:** 4
- **Output format:** See Layer 5 Output Format.
- **Drift check question:** Does the integrated evidence cover every sub-query approved in the research plan, and does the iteration decision faithfully reflect coverage status without falsely declaring CONVERGED while material gaps remain?

### Milestone 3: Final Research Report

- **Endpoint produced:** Structured markdown research report with Executive Summary, per-sub-query sections with citations, Cross-Query Synthesis, Caveats, Bibliography, Corrections Log, Missing Information Declaration, Recovery Declaration; persisted to vault if persist=true.
- **Verification criterion:** Every sub-query has a section in the report; every claim carries a source-class tag; Bibliography contains every cited URL with no orphans in either direction; all 9 Evaluation Criteria scored at threshold or with documented UNRESOLVED DEFICIENCY.
- **Layers covered:** 6, 7, 8
- **Required prior milestones:** M2
- **Gear:** 4
- **Output format:** See Layer 6 Output Format and Layer 8 Output Format.
- **Drift check question:** Does the final report directly answer the user's original query with proper citation grounding, no fabricated URLs, and faithful representation of the integrated evidence?
```

(Single-mode framework: no Mode property declared; no M0 routing milestone; no Conditional layers; flat M1, M2, M3 numbering.)

For a multi-mode example with M0 routing and Conditional layers, see the Mission/Objectives/Milestones framework's Milestones Delivered section.

### 2.4 Evaluation Criteria

Immediately following the header block. Listed before processing layers because evaluation criteria define what the processing must achieve. The model reads the criteria before it reads the processing instructions, establishing the quality target before execution begins.

```
## EVALUATION CRITERIA

This framework's output is evaluated against these [N] criteria.
Each criterion is rated 1-5. Minimum passing score: [threshold] per criterion.

1. **[Criterion Name]**:
   - 5 (Excellent): [Specific, observable description of what constitutes
     a top score for this dimension.]
   - 4 (Strong): [What distinguishes strong from excellent.]
   - 3 (Passing): [Minimum acceptable standard — concrete and observable.]
   - 2 (Below threshold): [Specific observable deficiencies.]
   - 1 (Failing): [What constitutes clear failure on this dimension.]

2. **[Criterion Name]**: [Same structure.]

[Continue for all criteria. Limit to 7-12 criteria.]
```

**Standard for writing evaluation criteria:**

Each criterion must specify what is being measured in concrete terms. "Quality of output" is not a criterion. "Psychological authenticity of character motivation as demonstrated by consistent internal parliament coalition activation across three or more independent decision points" is a criterion.

Each criterion must include rubric-level descriptions for all five score levels. Research shows that rubric-based evaluation with concrete per-level descriptions achieves 0.897 correlation with human judgment, while unstructured evaluation achieves only 0.392 — a 2.3× difference (Prometheus, ICLR 2024). Vague criteria produce unreliable self-evaluation. Concrete rubrics produce reliable self-evaluation.

Use a 1-5 scale rather than 1-10. A five-point scale requires less differentiation per level and produces more consistent self-evaluation scores. Each level needs a description of uniform length to prevent length bias in the model's scoring.

Limit criteria to 7–12. Research on criterion proliferation confirms that evaluation quality degrades as criterion count rises — each criterion receives less attention. IF more dimensions need tracking, THEN consolidate related dimensions into composite criteria.

For externally acting process applications, include the applicable quality dimensions from Section 2.13: verification-boundary quality, acceptance observability, evidence sufficiency, artifact identity, authorization integrity, bounded-loop safety, transition completeness, and final-gate independence. Consolidate related dimensions when necessary to remain within the 7–12 criterion limit; do not omit a load-bearing dimension merely to preserve a preferred count.

### 2.5 Persona Activation (Optional)

IF the framework benefits from a specialized persona, THEN define it here. Persona activation is a tool for focusing the model's response patterns, not a requirement. Simple frameworks may omit this section.

```
## PERSONA

You are the [Persona Name] — [one-sentence description of expertise and orientation].

You possess:
- [Specific capability relevant to this framework's task]
- [Specific capability relevant to this framework's task]
- [Specific capability relevant to this framework's task]

Throughout this framework, you will shift between specialized roles
as indicated by Role Shift markers at the beginning of each layer.
Your core identity as [Persona Name] persists across all role shifts.
```

**Persona design standards:**

- Personas combine domain expertise relevant to the framework's task. Name specific exemplars of mastery rather than generic descriptors. "The psychological insight of Dostoevsky" is more effective than "deep psychological understanding."
- Limit persona capabilities to three to five items. Each must be directly relevant to the framework's processing requirements.
- **Every persona detail must be task-relevant. Irrelevant details are prohibited.** Research shows performance drops of almost 30 percentage points from irrelevant persona attributes (Araujo et al., 2025). Do not add biographical details, personality traits, or expertise areas that do not serve the framework's processing requirements.
- Simple role specification ("You are an expert in X") primarily affects tone and style, not factual accuracy. Detailed expert identities with task-relevant capabilities meaningfully improve performance. IF a persona is used, THEN make it detailed and specific.
- Role shifts within layers are optional for focus purposes but recommended for adversarial self-review. Use them when a layer requires materially different expertise than the default persona. IF a Role Shift creates a critic or evaluator role, THEN include an explicit identification quota: "Identify at minimum [N] specific deficiencies" rather than open-ended review. This forces genuine adversarial engagement rather than rubber-stamping.

### 2.6 Processing Layers

The core of the framework. Each layer represents a discrete processing stage with its own focus, input, and output.

```
## LAYER [N]: [LAYER NAME]

**Role Shift** (if applicable): As the [Role Name], you [one sentence
describing the shifted focus].

**Stage Focus**: [One sentence stating what this layer accomplishes.]

**Input**: [What this layer reads — either the original framework inputs
or the output of a previous layer.]

**Output**: [What this layer produces for downstream consumption.]

### [Processing Instructions]

[Concrete, directive instructions for this layer's work.
Use imperative voice. Use IF/THEN for conditional logic.
Use enumerated lists for sequential steps.
Use named failure modes for known risks at this stage.]

### Output Formatting for This Layer

[Specific formatting requirements for this layer's output.
Separated from processing instructions per the Think-Then-Format
standard — reasoning instructions always precede formatting instructions.]
```

**Layer design standards:**

- Each layer has a single primary focus. IF a layer is doing two unrelated things, THEN split it into two layers.
- Layer output must be explicitly defined. "Complete this layer's analysis" is insufficient. "Produce a prioritized list of [specific items] with [specific attributes] for each" is sufficient.
- Layers are numbered sequentially. Cross-references between layers use layer numbers, not descriptions.
- The number of layers is determined by the task's complexity, not by a target count. Simple frameworks may have three layers. Complex frameworks may have twelve. No layer exists without a clear reason. IF a framework exceeds 12 processing layers for single-pass execution, THEN evaluate whether it should be split into multiple execution stages or a multi-pass sequence.
- **Think-Then-Format:** Within every processing layer, reasoning instructions precede formatting instructions, and the two are structurally separated by a subsection break. The model reasons about the problem first, then formats its output per the layer's requirements. This prevents the documented reasoning degradation caused by format constraints (Tam et al., EMNLP 2024).
- **Invariant Check at Layer Boundaries:** At the end of each processing layer (except the final two), include a brief invariant verification: "Before proceeding: confirm that the primary objective stated in the Purpose has not shifted, that all named variables from the Input Contract are still being tracked, and that the output of this layer falls within the scope defined by the Output Contract." This is not a full self-evaluation — it is a lightweight drift detection mechanism. Full evaluation is consolidated in the Self-Evaluation layer.

Layer handoffs move the minimum information forward between processing functions. They are not automatically verification boundaries. A verification boundary pauses progression for acceptance of an observable result under Section 2.3; a layer handoff may occur without independent review. Keep both meanings explicit when they coincide.

### 2.7 Self-Evaluation Layer

A dedicated processing layer (always the penultimate layer) where the model evaluates its own output against the Evaluation Criteria from Section 2.4.

```
## LAYER [N]: SELF-EVALUATION

**Stage Focus**: Evaluate all output produced in Layers 1 through [N-1]
against the Evaluation Criteria defined in Section 2.4.

**Calibration warning**: Self-evaluation scores are systematically
inflated. Research finds LLMs are overconfident in 84.3% of scenarios.
A self-score of 4/5 likely corresponds to 3/5 by external evaluation
standards. Score conservatively. Articulate specific uncertainties
alongside scores.

For each criterion:
1. State the criterion name and number.
2. Wait — verify the current output against this specific criterion's
   rubric descriptions before scoring. [Explicit correction trigger.]
3. Identify specific evidence in the output that supports or undermines
   each score level.
4. Assign a score (1-5) with cited evidence from the output.
5. IF the score is below [threshold], THEN:
   a. Identify the specific deficiency with a direct quote or
      reference to the deficient passage.
   b. State the specific modification required to raise the score.
   c. Apply the modification.
   d. Re-score after modification.
6. IF the score meets or exceeds [threshold], THEN confirm and proceed.

After all criteria are evaluated:
- IF all scores meet threshold, THEN proceed to the Output Formatting layer.
- IF any score remains below threshold after one modification attempt,
  THEN flag the deficiency explicitly in the output with the label
  UNRESOLVED DEFICIENCY and state what additional input or iteration
  would be needed to resolve it.
```

**Self-evaluation design standards:**

- **Use explicit correction trigger phrases.** The phrase "Wait — let me verify" at the start of each criterion evaluation reduces the self-correction blind spot by 89.3% and increases correction accuracy by 156% (Tsui, 2025). Do not use open-ended "check your work" instructions.
- **Require cited evidence.** For each score, the model must point to specific passages in its own output that support the score. Unsupported scores are prohibited.
- **Pairwise comparison where possible.** LLMs demonstrate higher reliability in comparative assessments than absolute scoring. Where the framework provides reference examples or the evaluation criteria include concrete exemplars, instruct the model to compare its output against those references rather than scoring in the abstract.
- **Treat scores as upper bounds.** Include the calibration warning in every Self-Evaluation layer to counteract documented overconfidence.

### 2.8 Error Correction and Output Formatting Layer

The final processing layer. Handles mechanical error correction, output formatting, and final verification.

```
## LAYER [N]: ERROR CORRECTION AND OUTPUT FORMATTING

**Stage Focus**: Final verification, mechanical error correction,
and output formatting for delivery.

### Error Correction Protocol

1. Verify factual consistency across all output sections.
   Flag and correct any contradictions.
2. Verify terminology consistency. Confirm that defined terms are
   used with their defined meanings throughout.
3. Verify structural completeness. Confirm all required output
   components (per Output Contract) are present.
4. Verify variable fidelity. Confirm that all named variables,
   entities, and quantities defined in the Input Contract or
   established during processing are still present and accurately
   represented. IF any variable has been silently dropped, conflated
   with another variable, or simplified, THEN restore it.
5. Verify word count compliance (if applicable).
6. Document all corrections made in a Corrections Log appended
   to the output.

### Output Formatting

[Specific formatting instructions for the framework's deliverables.
Include templates, section structures, and formatting standards.]

### Missing Information Declaration

Before finalizing output, explicitly state:
- Any input information that was expected but absent.
- Any processing step where insufficient information forced assumptions.
- Any evaluation criterion where the score reflects a gap in
  available information rather than a quality deficiency.

A response that acknowledges missing information is always preferable
to a response that fills gaps with assumptions.

### Recovery Declaration

IF the Self-Evaluation layer flagged any UNRESOLVED DEFICIENCY, THEN
restate each deficiency here with:
- The specific criterion that was not met.
- What additional input, iteration, or human judgment would resolve it.
- Whether the deficiency affects downstream consumers of this
  framework's output (if part of a pipeline).
```

### 2.9 Multi-Stage Runtime Metadata (Multi-Stage Runtime Only)

This section appears only in multi-stage-runtime renderings. It is absent from specifications, single-pass renderings, and reasoning-model renderings.

Runtime stage boundaries are execution-environment choices and do not define, merge, or erase canonical verification boundaries. IF a stage ends at a verification boundary, THEN the runtime-stage metadata implements that boundary's evidence and transition requirements. IF multi-stage runtime is unavailable, THEN the PROCESS APPLICATION CONTRACT remains complete and executable as natural-language instructions.

```
## MULTI-STAGE RUNTIME METADATA

### Stage Boundaries

[Enumeration of which layers constitute discrete execution stages
with actual context window resets between them.]

Stage 1: Layers 1-3 (executed in single inference call)
  Handoff to Stage 2: [specific data extracted and carried forward]

Stage 2: Layers 4-6 (executed in single inference call)
  Handoff to Stage 3: [specific data extracted and carried forward]

[Continue for all stages.]

### Persistent Reference Document

[A compact summary injected into every stage's context window alongside
the previous stage's output and the current stage's instructions.
Contains: the original objective (unchanged across all stages), key
constraints, scope boundaries, and named variables that must persist
throughout the pipeline. This document is the stable frame that no
individual stage can override.]

### Tool Definitions

[Enumeration of available tools with trigger conditions.]

Tool: file_read
  Description: Read contents of a file from the vault or workspace.
  Trigger: When processing requires information from a file not already
           in the context window.
  Input: file path (string)
  Output: file contents (string)
  Failure handling: IF tool call fails, THEN [specific recovery action].

Tool: file_write
  Description: Write output to a file in the workspace.
  Trigger: When a stage produces output that must persist for
           downstream stages or final delivery.
  Input: file path (string), content (string)
  Output: confirmation with file path
  Failure handling: IF tool call fails, THEN [specific recovery action].

Tool: rag_query
  Description: Query the ChromaDB knowledge base for relevant context.
  Trigger: When processing requires information that may exist in the
           vault but is not in the current context window.
  Input: query string, optional filters (nexus, type, tags)
  Output: ranked list of relevant chunks with source metadata
  Failure handling: IF tool call fails, THEN [specific recovery action].

[Additional tools as needed for the specific framework.]

### Checkpoint Protocol

At each stage boundary:
1. Extract the stage's output per the handoff specification.
2. Write the extracted output to [workspace location].
3. Log stage completion with timestamp.
4. IF stage output fails self-evaluation threshold, THEN:
   a. Log the failure with specifics.
   b. Retry the stage once with the deficiency flagged in the
      stage's input context.
   c. IF retry fails, THEN halt execution and surface the failure
      to the user with the label STAGE FAILURE, the stage number,
      and the specific deficiency.

### Python Runner Specification

[Natural language specification for the Python code that executes
this framework. This specification is used to generate runner.py
via the modified-date regeneration pattern.]

The runner for this framework:

Initialization:
1. [What the runner does before the first inference call]

Stage execution loop:
1. [How each stage is called]
2. [How output is captured]
3. [How handoff extraction occurs]
4. [How stage boundaries are managed]

Tool call routing:
1. [How tool calls are detected in model output]
2. [How each tool type is dispatched]
3. [How tool results are injected back into context]

Error handling:
1. [Retry logic for failed stages]
2. [Retry logic for failed tool calls]
3. [Halt conditions and user notification]

Output collection:
1. [How final output is assembled from stage outputs]
2. [Where final output is written]
3. [What metadata is logged]
```

### 2.10 Named Failure Modes Section

Every framework includes a section listing failure modes specific to that framework's task.

```
## NAMED FAILURE MODES

**The [Name] Trap:** [One-sentence description of what goes wrong.]
Correction: [One-sentence description of what to do instead.]

**The [Name] Trap:** [One-sentence description of what goes wrong.]
Correction: [One-sentence description of what to do instead.]

[Continue for all identified failure modes.]
```

Failure modes are identified during the design process (Phase 3, Step 7). Additional failure modes may be discovered during use and added in subsequent versions.

### 2.11 Execution Commands Block

The final element of every framework. Provides the model with explicit activation instructions.

```
---

## EXECUTION COMMANDS

1. Confirm you have fully processed this framework and all associated
   input materials.
2. IF any required inputs (per Input Contract) are missing, THEN list
   them now and request them before proceeding.
3. IF any required inputs are present but ambiguous, THEN state what
   you understand, what you are uncertain about, and what assumptions
   you will make if not corrected. Wait for confirmation before proceeding.
4. Once all required inputs are confirmed present, execute the framework.
   Process each layer sequentially. Produce all outputs specified in the
   Output Contract.
```

### 2.12 Framework Registry Entry

Every framework specification is accompanied by a registry entry — a compressed metadata record designed for search indexing. The registry entry is produced automatically during the Execution Commands step and does not require separate user action beyond saving the entry to the registry file.

The registry entry format:

```
Name: [framework title]
Purpose: [one sentence]
Problem Class: [category of problem]
Input Summary: [required inputs, one line each]
Output Summary: [primary outputs, one line each]
Proven Applications: [test history]
Known Limitations: [primary risk]
File Location: [path]
Provenance: [human-created | model-assisted]
Confidence: [low | medium | high]
Version: [semantic version]
Delivers: [one-line summary per milestone type, semicolon-separated]
```

Registry entries are indexed in ChromaDB's knowledge collection for semantic search. When a bounded model step needs a framework, it queries the registry rather than loading all framework files into context.

### 2.13 Externally Acting Process Applications

Apply this section when a framework governs a process that reads, creates, changes, transmits, approves, publishes, deletes, or otherwise acts upon artifacts or state outside the framework's own conversational output. Also apply it when completion depends on evidence from a named provider role, authorization from an external authority, repeated action until a terminal condition, or an independent final decision. A framework that only produces ordinary text for the user to consider, with no claimed external action or externally verified completion, may declare this section not applicable.

An externally acting framework includes one consolidated, human-readable `## PROCESS APPLICATION CONTRACT`. The contract formalizes the PIF Process Capability Requirements and Verification-Boundary Map without depending on a runtime schema, parser, provider, durable actor object, or code module. Every operational field must be understandable and executable from the Markdown alone. Concrete bindings may be supplied later, but missing bindings remain explicitly unresolved; PFF never invents a provider, identity source, permission, reviewer, or proof of completion.

**Boundary preservation rule.** Preserve every PIF-proposed verification boundary as either a formal milestone or a process-internal verification point. Record the placement, containing milestone, and placement rationale. Classification into one of these two homes does not require a Boundary Change Rationale. For each substantive boundary change, identify the original boundary, the revised review point, the change type (merge, split, move, or remove), and the reason the revision improves observability, recovery, independence, or review economics. A convenience of implementation is not sufficient rationale.

**Boundary containment rule.** A formal milestone may contain zero or more process-internal verification points. Internal points gate transitions among the planning and execution nodes inside that milestone; they do not independently report project-level completion. The milestone's acceptance may require evidence that its contained internal points passed.

**Required contract semantics:**

1. **Process Definition identity and applicability:** Give the reusable capability a stable `definition_id`, exact version, content digest, title, purpose, lifecycle status, and scope. Explain why Section 2.13 applies. A changed digest is a changed identity even when the display title is unchanged.
2. **External artifacts and identity:** Identify every external artifact or state surface the process relies on or changes. For each, state the identity-provider requirement, required identity attributes, ambiguity behavior, and whether the concrete provider is bound or unresolved.
3. **Authorized actions:** Enumerate the consequential actions the process may perform. For each action, name the actor or role, target, preconditions, authorization source, reversibility, prohibited effects, and terminal proof. An action absent from this list is unauthorized.
4. **Process graph:** Express control flow with only the domain-general node kinds: action, sequence, parallel branch, join, decision, bounded loop, verification boundary, human checkpoint, process call, process return, and terminal state. Construction and operation are relationships recorded on one Run model, never separate engines or mutually exclusive `run_kind` values.
5. **Planning and execution nodes:** Define decision-producing and action-producing nodes without turning labels such as planner, executor, evaluator, or overseer into durable actors. Every node declares its ID, inputs, output, acceptance criteria, evidence, authority references, artifact selectors, and permitted transitions.
6. **Bounded judgments:** For every material judgment, state the verified circumstances and bounded question; permitted conclusions, directives, and actions; referenced authority grants and artifact scope; required evidence and evaluator boundary; stop, return, and escalation conditions; and the record binding the judgment to the current Process Run and exact artifact identity.
7. **Acceptance criteria:** Write concrete observable conditions for every node and verification boundary. Criteria identify the exact result identity being judged, the evidence required, the evaluator role, and the consequence of failure. Merely completing an activity is not acceptance.
8. **Evidence contract:** Define each evidence item by evidence ID, claim supported, provider requirement, exact artifact or observation identity, freshness or timing requirement, independence requirement, and missing-evidence behavior. Self-report by the acting node is not independent evidence unless the contract explicitly permits it and discloses the reduced assurance.
9. **Loop policy:** Define every repeated planning, action, or review sequence as a bounded synchronous loop. State the loop ID, controlled nodes, continuation condition, success condition, maximum attempts or equivalent hard bound, progress and repeated-defect tests, failure-class evaluation route, and evidence retained across attempts. A hard bound stops churn but does not diagnose whether the defect is execution-, plan-, definition-, authority-, evidence-, or blockage-level. A loop may not rely on scheduled cleanup, deferred review, or unbounded retry.
10. **Seven transition directives:** Enumerate all permitted transitions and their destinations using exactly these Process Run directives: `PROCEED` accepts an intermediate boundary within the current definition, plan, and authority; `ACCEPT` alone completes the final governed outcome; `REVISE` corrects execution or produced-artifact work while retaining the plan and definition; `REPLAN` returns to planning because evidence invalidates the plan; `REDEFINE` returns to definition authority because the reusable Process Definition is defective or insufficient; `ESCALATE` requests reserved human authority; and `BLOCKED` records that no authorized, evidence-supported continuation is currently available. `PASS`, `FAIL`, and `BROKEN` are observations, never transitions. Every non-completion state has a deterministic destination or resume target.
11. **Redefinition and authority bifurcation:** A generic `REDEFINE` remains in the nonterminal Process Run and creates no human queue entry when existing authority covers draft-and-test definition work. Use `ESCALATE` only when the next action requires a typed reserved-authority request, such as changing a locked problem definition, expanding scope, approving an exception, or promoting or activating a replacement definition.
12. **Continuation and recovery:** Define checkpoints, restart reconstruction, idempotency keys, external-effect receipts, receipt digests, post-checkpoint revalidation, process-call and exact process-return bindings, deterministic resume targets, and stop behavior. Recovery may replay observation or pure computation but never an already-recorded external mutation without exact proof that replay is safe.
13. **Independent final gate:** Identify one final gate, distinct from the acting node whose output it judges, that alone may support `ACCEPT`. State the `Final gate ID`, evaluator role, exact subject artifact ID and digest, evidence set, acceptance criteria, rejection destinations, and completion record. If no qualified independent evaluator is concretely bound, preserve the role requirement, mark the binding unresolved, and withhold completion.
14. **Package manifest:** When the capability spans multiple files, bind each member by role, locator, exact identity, and required/optional status. The entry member is the Process Definition; folders are packaging, not conceptual taxonomy.
15. **Unresolved bindings and assurance limits:** List every symbolic provider, reviewer, authority, tool, or identity binding not yet resolved. State which actions or completion claims remain unavailable until each binding is resolved.

**Canonical template:**

```markdown
## PROCESS APPLICATION CONTRACT

### Process Definition Identity and Applicability

- **Definition ID:** [stable identifier]
- **Version:** [exact version]
- **Digest:** [sha256 content digest]
- **Status and scope:** [draft/approved/active/superseded/archived; universal/project/engagement selector]
- **Purpose:** [what the application accomplishes]
- **Why this contract applies:** [external action, external evidence, authorization, loop, or independent final-decision requirement]

### External Artifacts and Identity

| Artifact or State ID | Description | Identity Provider Requirement | Required Identity Attributes | Binding Status | Ambiguity Behavior |
|---|---|---|---|---|---|
| [ID] | [artifact or state surface] | [provider role or requirement] | [attributes] | [Bound: name / Unresolved] | [halt, escalate, or request clarification] |

### Authorized Actions

| Action ID | Actor or Role | Target | Preconditions | Authorization Source | Reversibility | Prohibited Effects | Terminal Proof |
|---|---|---|---|---|---|---|---|
| [ID] | [actor] | [artifact/state] | [conditions] | [authority or unresolved requirement] | [reversible/irreversible and recovery] | [effects outside scope] | [observable proof] |

### Planning Nodes

| Node ID | Purpose | Inputs | Output | Acceptance Criteria | Required Evidence | Permitted Transitions |
|---|---|---|---|---|---|---|
| [ID] | [decision produced] | [inputs] | [plan/decision] | [observable conditions] | [evidence IDs] | [outcome → destination] |

### Execution Nodes

| Node ID | Authorized Action References | Inputs | Output or State Change | Acceptance Criteria | Required Evidence | Permitted Transitions |
|---|---|---|---|---|---|---|
| [ID] | [Action IDs] | [inputs] | [observable result] | [observable conditions] | [evidence IDs] | [outcome → destination] |

### Bounded Judgment Contracts

| Judgment ID | Verified Circumstances and Bounded Question | Permitted Conclusions / Directives / Actions | Authority Grant IDs | Artifact Selectors | Required Evidence | Stop / Return / Escalation Conditions | Persisted Record |
|---|---|---|---|---|---|---|---|
| [ID] | [question] | [bounded set] | [grant IDs] | [selectors] | [evidence IDs] | [conditions] | [Run-bound record] |

### Verification Boundaries

| Boundary ID | Placement | Containing Milestone | Result Examined | Independent Evaluator Requirement | Acceptance Criteria | Required Evidence | Failure Route | Boundary Rationale | PIF Boundary Status |
|---|---|---|---|---|---|---|---|---|---|
| [ID] | [Formal milestone / Process-internal verification point] | [Milestone ID] | [artifact/state/decision] | [role or unresolved requirement] | [criteria] | [evidence IDs] | [destination] | [why review belongs here and why this placement is correct] | [Preserved / Changed—see rationale] |

### Boundary Change Rationales

| Original Boundary ID | Change Type | Revised Placement | Rationale | Assurance Effect |
|---|---|---|---|---|
| [ID] | [Merge/Split/Move/Remove] | [new boundary or none] | [observability, recovery, independence, or review-economics reason] | [improved, unchanged, or reduced with disclosure] |

### Evidence Contract

| Evidence ID | Claim Supported | Provider Requirement | Artifact or Observation | Freshness or Timing | Independence Requirement | Missing-Evidence Behavior |
|---|---|---|---|---|---|---|
| [ID] | [claim] | [provider role or unresolved requirement] | [evidence produced] | [when valid] | [independence rule] | [withhold, retry, replan, escalate, or block] |

### Loop Policy

| Loop ID | Controlled Nodes | Continuation Condition | Success Condition | Hard Bound | Failure Route | Evidence Retained Across Attempts |
|---|---|---|---|---|---|---|
| [ID] | [Node IDs] | [condition] | [terminal condition] | [maximum attempts or equivalent] | [destination] | [evidence IDs/state] |

### Transition Policy

| From Node or Boundary | Outcome | Destination | Required Evidence or Reason | Completion Withheld? |
|---|---|---|---|---|
| [ID] | [PROCEED/ACCEPT/REVISE/REPLAN/REDEFINE/ESCALATE/BLOCKED] | [Node/Boundary/terminal state] | [evidence/reason] | [Yes/No] |

### Independent Final Gate

- **Final gate ID:** [stable identifier]
- **Independent evaluator requirement:** [role and independence from acting node]
- **Inputs:** [artifacts, state, and decisions examined]
- **Required evidence:** [Evidence IDs]
- **Acceptance criteria:** [observable conditions]
- **Rejection destinations:** [outcome → destination]
- **Completion record:** [artifact or state that proves acceptance]
- **Binding status:** [Bound: name / Unresolved]

### Continuation and Recovery

| Checkpoint or Effect ID | Persisted State and Artifact Identities | Idempotency / Receipt Binding | Revalidation Required | Deterministic Resume or Stop Target |
|---|---|---|---|---|
| [ID] | [state and exact identities] | [key or digest-bound receipt] | [evidence IDs] | [target] |

### Package Manifest

| Member ID | Role | Locator | Exact Identity | Required? |
|---|---|---|---|---|
| [ID] | [process_definition/instruction/script/template/test/schema/resource] | [locator] | [digest/version] | [Yes/No] |

### Unresolved Bindings and Assurance Limits

| Binding Requirement | Needed By | Current Status | Action or Claim Withheld Until Resolved |
|---|---|---|---|
| [provider/reviewer/authority/tool/identity requirement] | [Action, Node, Boundary, or Final gate ID] | [Unresolved/Unavailable] | [withheld action or completion claim] |
```

The field labels above are canonical natural-language contract terms. A runtime may project them into an implementation-specific process application representation, but that projection is downstream and non-canonical. Optional runtime identifiers may appear in YAML as navigation bindings, including `execution_tier`, provider IDs, or references to body-defined elements. No operational meaning may exist only in YAML, and no YAML binding may replace or weaken the Markdown contract.

---

## Section III: Framework Authoring Standards — Language and Convention

These standards govern the language, syntax, and structural conventions used in all framework documents. They exist to maximize clarity for AI models and minimize interpretation variance across different models and sessions.

### 3.1 Instruction Voice

**Use imperative voice for all directives.**

- Write: "Produce a list of five items."
- Do not write: "You should consider producing a list of five items."
- Do not write: "It would be helpful to produce a list of five items."

**Use declarative voice for definitions and descriptions.**

- Write: "A molecular note synthesizes two or more atomic concepts into an emergent second-order insight."
- Do not write: "You might think of a molecular note as something that synthesizes concepts."

**Use conditional structure for branching logic.**

- Write: "IF the character is classified as Major, THEN produce a profile of 700-850 words. IF the character is classified as Secondary, THEN produce a profile of 375-550 words."
- Do not write: "The profile length should vary based on character importance."

**Use affirmative directives rather than negative ones.** Research shows "do X" consistently outperforms "don't do Y" across models, with up to 67% accuracy improvement in controlled tests (Bsharat et al., 2023).

- Write: "Use active voice for all directives."
- Do not write: "Don't use passive voice."

### 3.2 Precision of Reference

**Name every actor explicitly. Do not rely on pronouns when the referent could be ambiguous.**

- Write: "The Depth model evaluates the Breadth model's output."
- Do not write: "It evaluates the output."

**Name every document by its full title on first reference. Use a defined short name on subsequent references.**

- Write: "The Character Foundation Framework (hereafter: Character Framework) produces four outputs."
- Subsequent: "The Character Framework's self-evaluation layer…"

**Use specific quantities rather than qualitative descriptors.**

- Write: "Produce exactly three alternative framings."
- Do not write: "Produce several alternative framings."
- Write: "The summary must not exceed 200 words."
- Do not write: "Keep the summary concise."

### 3.3 Structural Conventions

**Section headers use the following hierarchy:**

```
# Document Title (one per document)
## Major Section (numbered in Table of Contents)
### Subsection
#### Sub-subsection (use sparingly — prefer flatter structure)
```

**Enumerated lists for sequential steps.** IF order matters, THEN number the items.

**Bullet lists for non-sequential items.** IF order does not matter, THEN use bullets.

**Bold for defined terms on first use.** After first definition, use the term without bold.

**Code blocks for templates, formats, and structural patterns.**

Markdown headings, labels, lists, and tables may carry operational meaning. Write them so a human reader can execute the framework without a parser. Machine extraction may consume the same structures, but parseability is not a prerequisite for correctness and machine-only fields do not replace natural-language meaning.

**IF/THEN blocks for conditional logic.** Capitalize IF, THEN, ELSE for visual parsing:

```
IF [condition], THEN [action].
IF [condition], THEN [action], ELSE [alternative action].
IF [condition A] AND [condition B], THEN [action].
```

### 3.4 Named Failure Mode Convention

Every Named Failure Mode follows this structure:

```
**The [Name] Trap:** [One-sentence description of what goes wrong.]
Correction: [One-sentence description of what to do instead.]
```

The name should be descriptive and memorable. "The Topic Trap" is better than "Failure Mode 7." Names create cognitive hooks — anchor tokens in the model's attention mechanism — that the model pattern-matches against during processing.

### 3.5 Input/Output Contract Convention

Every input and output is specified with this minimum information:

```

For externally acting process applications, extend the ordinary Input and Output Contracts with the Process Capability Requirements and `PROCESS APPLICATION CONTRACT` defined in Section 2.13. Keep artifact identity, authorized actions, evidence, verification boundaries, loop policy, transitions, and final-gate requirements explicit even when a concrete provider binding is unresolved.
- [Name]: [Data type or format]. [Size constraints if applicable].
  Source/Destination: [Where it comes from or goes to].
  Required/Optional: [Required | Optional — default if absent: (behavior)].
```

### 3.6 Evaluation Criterion Convention

Every evaluation criterion follows this structure:

```
[N]. **[Criterion Name]** ([Weight if weighted scoring is used]):
  - 5 (Excellent): [Specific observable requirements.]
  - 4 (Strong): [What distinguishes strong from excellent.]
  - 3 (Passing): [Minimum acceptable standard.]
  - 2 (Below threshold): [Specific observable deficiencies.]
  - 1 (Failing): [What constitutes clear failure.]
```

Each level's description should be approximately the same length to prevent length bias in the model's scoring.

### 3.7 Anti-Drift Conventions

These conventions specifically address context drift — the progressive degradation of instruction adherence over long documents.

**Restate critical constraints at the point of application, not only at the point of definition.** IF a word count limit is defined in the header and applies during Layer 8, THEN restate it in Layer 8. Models lose awareness of early instructions as they process deeper into a document.

**Place anti-drift anchors after accumulated context, exploiting recency bias.** Research confirms that as context grows, primacy bias (attention to early content) weakens while recency bias (attention to recent content) remains stable. Anti-drift anchors should appear at the start of the next processing block, immediately after the section divider — so they are the most recently read content before the model begins generating. The anchor structure:

```
---
ORIENTATION ANCHOR — MIDPOINT REMINDER
Primary deliverable: [restate from Output Contract]
Key decisions made so far: [brief summary of upstream conclusions]
Scope boundaries that must not shift: [restate critical constraints]
Next layer must produce: [preview of upcoming output requirement]
Continue to Layer [N+1].
---
```

Insert an orientation anchor in any framework with more than seven processing layers, positioned at approximately the midpoint of the layer sequence. Additional anchors may be inserted in frameworks exceeding twelve layers.

**Place the highest-priority instruction last within each layer.** Models exhibit recency bias — the last instruction read before generating output receives the most attention.

**Use section dividers (horizontal rules) between layers.** Visual separation reinforces cognitive separation for the model.

**Limit each layer to a single primary focus.** Multi-focus layers produce drift because the model satisfies one focus and loses track of the other.

**Preserve verification-boundary intent across authoring and rendering.** Carry each accepted boundary, its evidence requirement, and its failure route into every applicable milestone and contract section. IF PFF changes a PIF-proposed boundary, THEN place the Boundary Change Rationale beside the revised architecture so the decision cannot disappear during drafting or rendering.

### 3.8 Word Count and Output Density

**Specify word counts as ranges, not targets.** "900-1000 words" is enforceable. "About 1000 words" is not.

**Specify information density expectations explicitly.** "Every sentence must advance the analysis. Filler language, restatement of the prompt, and transitional phrases that add no information are prohibited." This instruction is more effective than word count limits alone because it addresses the underlying behavior that inflates word count.

**Include a word count verification step in the Error Correction layer.** The model must count its own output and adjust before finalizing.

### 3.9 Think-Then-Format

**Separate reasoning from formatting within every processing layer.** Research demonstrates that format restrictions cause significant reasoning degradation, with stricter constraints producing greater harm (Tam et al., EMNLP 2024). JSON-mode formatting alone can cause up to 56% performance variation.

The mitigation: within every layer, processing instructions (reasoning, analysis, generation) appear first. Output formatting instructions (structure, templates, field requirements) appear second, in a clearly separated subsection. The model reasons about the problem, then formats its conclusion. Never embed format requirements within reasoning instructions.

```
## LAYER [N]: [LAYER NAME]

### Processing Instructions
[All reasoning, analysis, and generation directives here.]

### Output Format for This Layer
[All formatting, structure, and template requirements here.]
```

### 3.10 Variable Fidelity

**Track named variables explicitly at layer boundaries.** When a framework establishes named variables — character names, numerical quantities, defined terms, specific entities, scope parameters — those variables must be maintained accurately across all subsequent layers. Models silently drop, conflate, or simplify variables as processing depth increases.

The mitigation: include variable inventory requirements at layer boundaries (as part of the invariant check in Section 2.6). At any layer that establishes or transforms named variables, the output format should include an explicit variable state summary listing all active variables and their current values.

---

## Section IV: Framework Design Process — Creating a New Framework

This section provides the step-by-step process for designing a new framework from scratch. The AI follows this process when operating in Mode F-Design.

### Phase 1: Requirements Gathering and Proactive Elicitation

The AI conducts a structured interview with the user to establish the framework's requirements. This phase uses progressive questioning — questions build on previous answers, and the AI does not advance to the next question until the current one is resolved.

**The AI asks both reactive and proactive questions.** Reactive questions clarify what the user has stated. Proactive questions surface requirements the user has not articulated — missing dimensions, unstated constraints, implicit assumptions. Research shows LLMs are 15 times less likely than humans to ask follow-up questions and default to assuming an interpretation rather than seeking clarification (Shaikh et al., 2025). The structured question sequence below forces proactive elicitation through explicit prompts.

**Question Sequence:**

1. **Task Definition, Modes, and Milestones Delivered:** Establish the framework's mode structure, then elicit milestones with all properties inline.

    **Step A — Final deliverable.** What does this framework produce as its final user-facing deliverable?

    **Step B — Modes.** Does this framework have a single execution path or multiple modes (e.g., create / modify / audit)? For each mode identified, what does that mode deliver as its final output?

    **Step C — Routing.** Does the framework have a triage / classification / routing layer that fires BEFORE mode selection? If so, what does it produce that downstream milestones will consume? (This becomes M0 — routing is not itself a milestone but precedes them.)

    **Step D — Verification boundaries and per-mode placement.** Start with the PIF Verification-Boundary Map when supplied. Otherwise, identify points where a concrete artifact, external state, decision, or evidence bundle becomes independently reviewable; rejection has a defined destination; and delayed discovery would create material rework, risk, or consequence. Preserve each accepted boundary, then apply the Section 2.3 Milestone Placement Test. IF the accepted result is a substantial deliverable or state change that the governing Process Run, PEF when contingently invoked, or the user can meaningfully invoke, track, and review, THEN declare a formal milestone and elicit all inline milestone properties. IF the result gates continuation but is only an internal work product, THEN classify it as a process-internal verification point and carry its acceptance criteria, evaluator, evidence, failure route, containing milestone, and placement rationale into the PROCESS APPLICATION CONTRACT. IF a PIF boundary is merged, split, moved, or removed rather than merely classified, THEN record a Boundary Change Rationale.

    **Step E — Verify boundary and milestone sufficiency.** IF any mode has more than approximately five layers and only one milestone, THEN re-evaluate the path for missing verification boundaries. Preserve useful internal review points in the PROCESS APPLICATION CONTRACT even when they do not qualify as milestones. IF no additional substantial project-level deliverable exists, THEN retain one milestone and document that rationale in the Execution Tier section. Do not convert internal checkpoints into project milestones solely to satisfy a layer-count heuristic.

    All elicited properties are recorded inline per milestone — never factored into shared definitions or parent-subsection-only inheritance.

2. **Input Inventory:** What information does this framework receive as input? For each input: What is it? Where does it come from? Is it always available or sometimes absent? Identify external artifacts and state separately, including how their identities are established and what happens when identity is ambiguous.
3. **Quality Definition:** How do you know the output is good? What specific attributes distinguish excellent output from mediocre output for this task? Push beyond "high quality" — name the dimensions. For externally acting processes, include acceptance observability, evidence sufficiency, authorization integrity, verification-boundary quality, loop safety, and final-gate independence where applicable.
4. **Failure Modes:** What are the most likely ways this framework's output could go wrong? What mistakes have you seen AI make on this type of task before?
5. **Pipeline Position and Authorized Effects:** Is this framework standalone or part of a multi-step pipeline? IF part of a pipeline: What step does it receive input from? What step consumes its output? What is the minimum information the next step needs from this step's output? Identify every consequential external action, the authority required, reversibility, prohibited effects, and terminal proof. IF no external action exists, THEN record that Section 2.13 may be inapplicable.
6. **Execution Environment and Assurance Providers:** The default output is **one consolidated framework file** (the single-pass rendering, executable in commercial AI and serving as the canonical exchange format). Identify available identity providers, evidence providers, independent evaluator roles, and final-decision authority; mark absent concrete bindings unresolved. Determine whether the process needs planning nodes, execution nodes, bounded synchronous loops, rejection transitions, or an independent final gate. Confirm the single-file default is acceptable. IF the user has a concrete reason to also produce an multi-stage-runtime rendering or reasoning-model rendering, THEN they state the rationale explicitly and the additional rendering is added to Milestone 4's deliverable. The AI may recommend an additional rendering when architecture warrants it, but presents it as a choice and proceeds with single-file output unless the user accepts. Never produce multiple rendering files by default.
7. **Domain Expertise:** Does this task require specialized knowledge or perspective? IF so, THEN define the expertise in terms of specific exemplars of mastery (real or archetypal) rather than generic descriptors.
8. **Precedent Frameworks:** Are there existing frameworks (in your vault or elsewhere) that do something similar to what this framework needs to do? IF so, THEN identify what they do well and what they lack.
9. **Proactive Gap Assessment:** Based on the answers above, the AI identifies and presents:

    - Requirements the user likely has not articulated, based on common patterns for this task type.
    - Constraints that typically matter for this domain but were not mentioned.
    - Stakeholders or downstream consumers whose needs have not been addressed.
    - Potential failure modes the user did not identify.

    The user reviews, accepts relevant items, and dismisses irrelevant ones. This step does not proceed automatically — the AI presents its assessment and waits for the user's response. The assessment must be grounded in the framework's emerging Input/Output Contracts, not generic questions.

10. **Complexity Assessment:** Based on the task definition, input/output inventory, and quality dimensions:

    - IF the task can be accomplished in three layers (Input Validation, Core Processing, Self-Evaluation + Output), THEN recommend the simple architecture.
    - IF the task requires five to eight layers, THEN recommend the standard architecture.
    - IF the task requires more than eight layers, THEN recommend multi-stage-runtime execution with stage boundaries, and identify where human review gates should be inserted.
    - IF the task requires more than twelve layers, THEN evaluate whether it should be decomposed into a multi-framework pipeline with an orchestration layer.

    Evaluate verification-boundary placement independently from layer and stage count. Compare the cost of review at each candidate boundary against the expected cost and consequence of discovering failure later. Flag both Boundary Desert (material work proceeds too long without review) and Checkpoint Confetti (review is inserted where no independently judgeable result exists).

    Present the complexity assessment to the user with reasoning and wait for confirmation.

### Phase 2: Evaluation Criteria Design

From the requirements gathered in Phase 1, the AI drafts the evaluation criteria. This happens before processing layer design because the criteria define what the processing must achieve.

**Process:**

1. Extract quality dimensions from the user's answers to Question 3 (Quality Definition).
2. Extract anti-failure dimensions from the user's answers to Question 4 (Failure Modes) — each failure mode implies a quality dimension that prevents it.
3. Extract integration dimensions from the user's answers to Question 5 (Pipeline Position) — output must satisfy downstream requirements.
4. For externally acting processes, extract applicable capability dimensions from the PIF handoff and Phase 1: external-artifact identity, authorization, evidence, verification boundaries, bounded loops, transition completeness, and independent final-gate integrity.
5. Combine, deduplicate, and organize into a numbered list of evaluation criteria. Limit to 7–12 criteria.
6. For each criterion, draft the five-level rubric per the convention in Section 3.6.
7. Present the draft criteria to the user for review and revision.

### Phase 3: Architecture Design

With evaluation criteria established, the AI designs the processing architecture.

**Process:**

1. **Map criteria to processing requirements.** For each evaluation criterion, identify what processing must occur to satisfy it. This produces a list of required processing functions.
2. **Group functions into layers.** Processing functions that share a focus and operate on the same information group into a single layer. Functions that require different information or a different analytical mode become separate layers.
3. **Sequence the layers.** Determine the logical order. Layers that produce information consumed by later layers must precede them. Layers that require user input or external data should be positioned to minimize context switching.
4. **Define handoffs.** For each layer boundary, specify:

    - What the completed layer produces (output contract of the layer).
    - What the next layer requires (input contract of the next layer).
    - What is discarded at the boundary (everything not in the next layer's input contract).
    - Whether the handoff coincides with a substantive verification boundary. IF it does, THEN identify the accepted result, evidence, independent evaluator requirement, and failure route. IF it does not, THEN do not treat the handoff as acceptance.
5. **Insert standard layers.** Every framework includes:

    - A Self-Evaluation layer (penultimate position).
    - An Error Correction and Output Formatting layer (final position).
6. **Insert invariant checks.** At the end of every processing layer (except the final two), insert the lightweight invariant verification per Section 2.6.
7. **Insert anti-drift anchors.** IF the framework has more than seven processing layers, THEN insert an orientation anchor at the midpoint per Section 3.7.
8. **Formalize verification boundaries and externally acting process semantics.** Preserve the PIF Verification-Boundary Map or record a Boundary Change Rationale for every substantive change. Classify each preserved boundary as a formal milestone or a process-internal verification point; record the containing milestone and placement rationale for every internal point. When Section 2.13 applies, define planning nodes, execution nodes, acceptance criteria, external-artifact identity requirements, authorized actions, evidence contract, bounded synchronous loop policy, transitions, unresolved bindings, and an independent `Final gate ID` before selecting optional execution mechanics.
9. **Identify stage boundaries for multi-stage runtime.** Determine which layer boundaries should become actual execution breaks in multi-stage runtime. Stage boundaries implement execution packaging; they do not create or erase verification boundaries. Criteria for stage boundaries:

    - The output of the preceding layers constitutes a complete intermediate product.
    - The next layers require a materially different analytical mode.
    - Tool access is required at the boundary (file read/write, RAG query).
    - Context window pressure is a risk if layers are combined.
10. **Draft Named Failure Modes.** For each layer, identify the most likely failure mode specific to that layer's processing task. For the framework as a whole, identify cross-cutting failure modes.
11. **Draft Recovery Protocol.** For each identified failure point: what happens when the failure occurs? Specify retry conditions, halt conditions, and what information the user needs to resolve the failure.
12. **Present the architecture to the user.** Show the layer structure, handoff specifications, verification boundaries, any Boundary Change Rationales, optional stage boundaries, process application semantics, failure modes, and recovery protocol for review before proceeding to full draft.

### Phase 4: Specification Drafting

The AI produces the full canonical specification following the Framework Anatomy in Section II.

**Process:**

1. Draft the Header Block (Purpose, Input Contract, Output Contract).
2. Draft the Milestones Delivered section per Section 2.3. All milestone properties are defined inline per milestone — never factored into shared definitions.

    IF the framework has a routing / triage layer (identified in Phase 1 Question 1 Step C), THEN declare it as M0 at the top of the Milestones Delivered section with Function, Layers covered, and Output. M0 is not itself a milestone; it precedes mode selection.

    For each mode (identified in Phase 1 Question 1 Step B), draft the mode's milestones in sequence. For each milestone, produce an entry with all required properties bound inline: Mode (omit or write "all" for single-mode frameworks), Endpoint produced, Verification criterion, Layers covered, Conditional layers (only if applicable, with the condition stated inline), Required prior milestones (with mode prefix for cross-mode references), Gear, Output format, and Drift check question.

    IF any mode has more than approximately five layers and only one milestone has been declared for that mode, THEN return to Phase 1 Question 1 Step D to evaluate whether a verification boundary was missed. Preserve any discovered internal point in the PROCESS APPLICATION CONTRACT. Add another milestone only when the reviewed result also passes the Milestone Placement Test.

    Verify each Verification criterion is objectively determinable per the Resolution Statement Objectivity Protocol — no ambiguous quality terms without objective evaluation criteria.

3. Draft the Evaluation Criteria (from Phase 2, refined by architecture decisions in Phase 3). Use five-level rubrics with concrete per-level descriptions.
4. Draft the Persona (if applicable, based on Question 7 from Phase 1).
5. Draft each Processing Layer with full instructions following the Authoring Standards in Section III. Apply the Think-Then-Format standard to every layer. Insert invariant checks at layer boundaries.
6. Draft the Self-Evaluation Layer keyed to the specific evaluation criteria, including correction trigger phrases and calibration warning.
7. Draft the Error Correction and Output Formatting Layer, including variable fidelity verification and Recovery Declaration.
8. Draft the Named Failure Modes section.
9. IF Section 2.13 applies, THEN draft one complete `## PROCESS APPLICATION CONTRACT` in the Markdown body. Preserve PIF boundaries or include Boundary Change Rationales; keep concrete provider bindings unresolved when they are not supplied.
10. Append the Execution Commands block.

### Phase 5: Rendering

The AI produces **one consolidated framework file by default** by applying the Single-Pass Rendering Protocol (Section 5.1) to the M3 specification draft. The resulting file is both the canonical intellectual source and a self-contained executable in commercial AI — these are not separate artifacts. The single-pass rendering is the canonical exchange format because it is what runs outside Ora and is how frameworks are shared with others.

Additional renderings are produced **only on explicit request** as captured in Phase 1 Question 6:

- IF multi-stage-runtime rendering was requested with stated rationale, THEN follow the Multi-Stage Runtime Rendering Protocol (Section 5.2) and produce that as a separate file.
- IF reasoning-model rendering was requested with stated rationale, THEN follow the Reasoning-Model Rendering Protocol (Section 5.3) and produce that as a separate file.
- IF multiple additional renderings were requested, THEN render the consolidated single-pass file first (validates intellectual content), then multi-stage runtime (adds execution machinery on top of validated content), then reasoning-model (simplifies from validated single-pass).

Default path: one file out, no additional renderings. The user may always invoke F-Render later if they decide they need an additional rendering.

Every rendering preserves the full natural-language PROCESS APPLICATION CONTRACT when Section 2.13 applies. Runtime-stage metadata, tools, or provider identifiers may implement the contract but may not replace, weaken, or relocate its operational meaning into machine-only configuration.

### Phase 6: Verification

The AI applies the Quality Verification Checklist from Section VII to the finished framework(s), including Process Application Contract Compliance when applicable, and presents the verification **inline in the conversation** as a summary of pass/fail per applicable checklist item — not as a separate persistent file. The verification is operational and ephemeral: its purpose is to catch issues at production time, not to live alongside the framework in the vault. Save a separate verification file only if the user explicitly requests one.

---

## Section V: Rendering Protocol — Generating Execution Variants

**Preamble (v2.2 update).** The single-pass rendering (Section 5.1) is the **default and canonical output** of F-Design and F-Convert. It contains all of the intellectual content of a framework and is directly executable in commercial AI, which is the primary distribution context (the format that runs outside Ora and that frameworks can be shared in with others). There is no separate "specification" file in addition to the single-pass file — they are the same artifact.

The multi-stage-runtime rendering (Section 5.2) and reasoning-model rendering (Section 5.3) are **opt-in additional artifacts** produced only when the user explicitly requests them with stated rationale (e.g., the framework will run on the Mac Studio multi-model runtime; the framework targets o3/R1). Each additional rendering is a separate file beyond the consolidated default.

This section defines all three protocols. By default, only Section 5.1 is applied.

### 5.1 Single-Pass Rendering Protocol

The single-pass rendering is the **default consolidated framework file**. It contains the canonical intellectual content of the framework AND is directly executable in a single commercial AI context window with no tool access. This is the primary output of F-Design and F-Convert.

**Rendering steps:**

1. **Copy the specification structure intact.** The Framework Anatomy sections remain in the same order.
2. **Remove all multi-stage-runtime metadata.** Delete: Stage Boundaries, Persistent Reference Document, Tool Definitions, Checkpoint Protocol, and Python Runner Specification.
3. **Set execution_tier to `single-pass`** in YAML frontmatter.
4. **Adjust the Execution Tier section** of the Header Block:

    ```
    ## EXECUTION TIER
    Single-pass: All layers execute sequentially in one context window.
    Complete process meaning is available in this Markdown file. IF an
    authorized external action requires a tool or provider that is not
    available, THEN preserve the requirement and withhold the action or
    completion claim; do not simulate the missing external effect.
    ```

5. **Add anti-drift anchors.** In frameworks with more than seven processing layers, insert an orientation anchor at the midpoint of the layer sequence per Section 3.7. Position the anchor at the start of the next processing block, immediately after the section divider.
6. **Add the input validation and proactive elicitation protocol** to the first processing layer. In single-pass mode, the framework must gather any needed clarification from the user within the same session. Insert at the beginning of Layer 1:

    ```
    Before beginning Layer 1 processing, review all required inputs
    per the Input Contract. IF any required input is absent, THEN
    present a numbered list of specific questions to the user
    referencing the missing Input Contract items by name.
    Do not proceed until all required inputs are confirmed.

    IF any required input is present but ambiguous, THEN state
    what you understand, what you are uncertain about, and what
    assumption you will make if not corrected. Wait for confirmation.

    IF optional inputs are absent, THEN note their absence and state
    the default behavior that will apply.

    Additionally, assess whether the provided inputs are likely
    underspecified for this framework's task. IF common requirements
    for this task type appear to be missing, THEN surface them:
    "Based on [framework task], the following requirements are
    typically important but were not specified: [list]. Should any
    of these be addressed before proceeding?"
    ```

7. **Consolidate evaluation into a single pass.** In the Self-Evaluation layer, add:

    ```
    Execute all criterion evaluations in a single sequential pass.
    Do not skip criteria. Do not defer criteria to a later step.
    IF any criterion cannot be fully evaluated due to context window
    limitations, THEN score it as INCOMPLETE rather than guessing.
    ```

8. **Verify total document length.** Single-pass frameworks must operate within a commercial AI context window alongside the user's input materials. IF the specification plus typical inputs would exceed 75% of a standard context window (approximately 150,000 tokens for current frontier models), THEN identify layers that can be condensed or split the framework into a multi-pass sequence with explicit pass boundaries and carry-forward specifications.
9. **Preserve externally acting process semantics.** IF Section 2.13 applies, THEN retain the complete PROCESS APPLICATION CONTRACT, every accepted verification boundary, every evidence and authorization requirement, every transition, and the `Final gate ID`. Mark unavailable concrete bindings unresolved and disclose the assurance limit.

### 5.2 Multi-Stage Runtime Rendering Protocol

The multi-stage-runtime rendering takes a canonical specification and produces a mode file optimized for execution in a multi-stage pipeline with tool access and Python orchestration.

**Rendering steps:**

1. **Copy the specification structure intact.**
2. **Set execution_tier to `multi-stage`** in YAML frontmatter.
3. **Map layers to execution stages.** Using the stage boundaries identified in Phase 3 of the design process, group layers into stages. Each stage becomes one inference call in the pipeline. Preserve verification boundaries independently; a stage boundary implements a verification boundary only when the PROCESS APPLICATION CONTRACT says they coincide.
4. **Write handoff specifications for each stage boundary.** For each boundary:

    ```
    STAGE BOUNDARY: Stage [N] → Stage [N+1]

    Extract from Stage [N] output:
    - [Specific data element 1]
    - [Specific data element 2]
    - [Specific data element N]

    Discard:
    - [Everything not listed above]

    Construct Stage [N+1] context window:
    - System prompt: [mode file header through Stage N+1 instructions]
    - Persistent Reference Document: [original objective, key constraints,
      scope boundaries, named variables — unchanged across all stages]
    - Previous stage output: [extracted data elements above]
    - Additional context: [any RAG retrievals or file reads needed]
    ```

5. **Write the Persistent Reference Document.** A compact summary (target: under 500 tokens) containing: the framework's Purpose statement, the Output Contract's primary deliverable, the three highest-priority evaluation criteria, all named variables and their current values, and any scope boundaries that must not shift. This document is injected into every stage's context window.
6. **Write tool definitions.** For each tool available to this framework:

    ```
    TOOL: [tool_name]
    Description: [What it does]
    Trigger condition: [When the model should invoke this tool]
    Input schema: [parameter names and types]
    Output schema: [what the tool returns]
    Failure handling: IF tool call fails, THEN [specific recovery action]
    ```

7. **Write the checkpoint protocol** per the template in Section 2.8.
8. **Write the Python Runner Specification.** Structure the specification as described in Section 2.8.
9. **Add adversarial review integration points.** Identify which stages produce outputs that should be cross-evaluated by the opposing model in the multi-model runtime. For each such point:

    ```
    ADVERSARIAL REVIEW POINT after Stage [N]:

    Reviewing model: [Depth | Breadth]
    Review focus: [What the reviewer evaluates — map to Six Hats assignment]
    Review input: Stage [N] output + evaluation criteria [list numbers]
    Review output: [Scored evaluation with specific deficiency identification]
    Action on review:
      IF all scores ≥ [threshold], THEN proceed to Stage [N+1].
      IF any score < [threshold], THEN return to Stage [N] with
      deficiency report appended to context. Maximum retries: [count].
    ```

10. **Bind optional mechanics to the natural-language contract.** Map tools, providers, and reviewer processes to existing Action IDs, Evidence IDs, Boundary IDs, Node IDs, and the `Final gate ID`. Keep the body contract complete and treat these bindings as replaceable execution enhancements.

### 5.3 Reasoning-Model Rendering Protocol

The reasoning-model rendering takes a canonical specification and produces a framework optimized for execution by reasoning-specialized models (o3, o4-mini, DeepSeek R1) that structure reasoning internally.

Research on reasoning models converges on a clear finding: traditional prompting techniques — chain-of-thought instructions, step-by-step scaffolding, few-shot examples — can hinder reasoning model performance because they interfere with the model's native reasoning patterns. Reasoning models benefit from simpler, more direct prompts.

**Rendering steps:**

1. **Copy the specification structure intact.**
2. **Set execution_tier to `reasoning-model`** in YAML frontmatter.
3. **Simplify processing layer instructions.** For each layer:

    - Remove explicit chain-of-thought instructions ("think step by step," "reason through this carefully"). The model does this internally.
    - Remove few-shot examples unless they demonstrate edge cases the model would not encounter in training.
    - Reduce procedural scaffolding. Replace multi-step instruction sequences with direct objective statements where the intermediate steps are obvious.
    - Retain: evaluation criteria, output contracts, named failure modes, conditional logic, and constraints. These are specifications, not reasoning scaffolding.
4. **Retain the Self-Evaluation layer** but simplify its instructions:

    ```
    Evaluate your output against each criterion. For any criterion
    scoring below [threshold], identify the deficiency and correct it.
    Flag unresolvable deficiencies.
    ```

    Reasoning models show near-zero self-correction blind spots due to error-correction sequences in their training data. Elaborate correction trigger phrases are unnecessary.

5. **Retain all structural elements.** Input/Output Contracts, Evaluation Criteria, Named Failure Modes, and Execution Commands remain unchanged. These are contracts and specifications, not reasoning instructions.
6. **Retain the PROCESS APPLICATION CONTRACT when applicable.** Preserve all process application semantics, unresolved bindings, verification boundaries, and final-gate independence.
7. **Retain anti-drift anchors and invariant checks.** Even reasoning models benefit from explicit scope reminders.

### 5.4 Rendering Order

The single-pass rendering is always produced first because it is the default consolidated output. **When the user has explicitly requested additional renderings beyond the single-pass default**, render them in this order: multi-stage-runtime after single-pass, then reasoning-model. This order is correct because:

- The single-pass version validates that the intellectual content is complete and self-contained.
- The multi-stage-runtime version adds execution machinery on top of validated content.
- The reasoning-model version simplifies from the validated single-pass version.
- Issues caught in the single-pass rendering (missing layers, unclear handoffs, evaluation gaps) are corrected before the more complex renderings.

---

## Section VI: Conversion Protocol — Modernizing Existing Frameworks

This section provides the process for converting an existing framework to the current standard. The AI follows this process when operating in Mode F-Convert.

### 6.1 Analysis Phase

1. **Read the existing framework completely** before making any changes.
2. **Identify the framework's intellectual content:**

    - What does it produce? (Map to Output Contract.)
    - What does it require? (Map to Input Contract.)
    - What quality standards does it apply? (Map to Evaluation Criteria.)
    - What processing steps does it follow? (Map to Processing Layers.)
    - What failure modes does it address? (Map to Named Failure Modes.)
    - Does it govern external artifacts, authorized actions, evidence providers, identity providers, bounded loops, transitions, verification boundaries, or an independent final gate? (Map to Process Capability Requirements and Section 2.13.)
3. **Identify structural gaps against the Framework Anatomy:**

    - Is there a formal Input Contract? (Existing frameworks typically lack this.)
    - Is there a formal Output Contract? (Often implied but not explicit.)
    - Are evaluation criteria separated from processing instructions? (Often mixed together.)
    - Are evaluation criteria written as five-level rubrics with concrete per-level descriptions? (Almost never in legacy frameworks.)
    - Are processing layers clearly bounded with single focus? (Often blended.)
    - Is Think-Then-Format observed within layers? (Rarely in legacy frameworks.)
    - Is there an explicit Self-Evaluation layer with correction triggers? (May exist informally.)
    - Is there an explicit Error Correction layer with variable fidelity checks? (Often partial.)
    - Are failure modes named? (Sometimes present, often generic.)
    - Are recovery protocols specified? (Almost never in legacy frameworks.)
    - IF the framework is externally acting, is there a complete human-readable PROCESS APPLICATION CONTRACT with preserved boundary intent and no invented bindings?
4. **Identify language standard gaps against the Authoring Standards:**

    - Instruction voice: imperative or suggestive?
    - Conditional logic: IF/THEN structure or prose descriptions?
    - References: named or pronoun-dependent?
    - Quantities: specific or qualitative?
    - Word counts: ranges or vague targets?
    - Directives: affirmative ("do X") or negative ("don't do Y")?
5. **Identify consolidation opportunities** (for frameworks that were split into initiation/foundation/evaluation triads):

    - Can the initiation framework's progressive questioning be absorbed into the first processing layer?
    - Can the evaluation framework's criteria be absorbed into the Evaluation Criteria section and Self-Evaluation layer?
    - Is the split still justified by context window pressure, or does the updated structural standard resolve the drift that caused the split?
6. **Assess complexity.** Apply the complexity assessment from Phase 1, Question 10 of the Framework Design Process. IF the framework exceeds 12 layers, THEN recommend either multi-stage-runtime execution or decomposition into a multi-framework pipeline.
7. **Present the analysis to the user** with specific recommendations before proceeding to conversion.

### 6.2 Conversion Phase

1. **Draft the canonical specification** by restructuring the existing framework's intellectual content into the Framework Anatomy:

    - Extract and formalize the Input Contract.
    - Extract and formalize the Output Contract.
    - Extract, separate, and formalize the Evaluation Criteria with five-level rubrics.
    - Reorganize processing instructions into properly bounded layers with Think-Then-Format separation.
    - Add invariant checks at layer boundaries.
    - Add or formalize the Self-Evaluation layer with correction triggers and calibration warning.
    - Add or formalize the Error Correction and Output Formatting layer with variable fidelity verification and Recovery Declaration.
    - Name all identified failure modes.
    - Draft recovery protocols.
    - Apply all Authoring Standards to instruction language.
    - Preserve or formalize Process Capability Requirements, verification boundaries, and the PROCESS APPLICATION CONTRACT when Section 2.13 applies. Record a Boundary Change Rationale for every changed boundary; do not infer concrete providers, authority, or reviewer identities from absence.
2. **Preserve all intellectual content.** Conversion modernizes structure and language. It does not add, remove, or alter the framework's substantive instructions unless a deficiency is identified, in which case the AI flags it for user review rather than silently correcting it.
3. **Consolidate split frameworks** (if applicable and if the user confirms consolidation):

    - Absorb initiation questioning into Layer 1 progressive questioning protocol.
    - Absorb evaluation criteria into the Evaluation Criteria section.
    - Absorb evaluation processing into the Self-Evaluation layer.
    - Verify that the consolidated framework does not exceed context window viability for single-pass use.
4. **Render the consolidated converted framework file.** Apply the Single-Pass Rendering Protocol (Section 5.1) to produce one consolidated file as the default output of F-Convert. Additional execution variants are produced only on explicit user request with stated rationale, per Section V Preamble (v2.2).

### 6.3 Verification Phase

1. **Cross-check intellectual content.** Verify that every instruction, criterion, processing step, capability requirement, verification boundary, evidence rule, authorization rule, transition, loop, and final-gate requirement from the original framework exists in the converted version. Document and justify any omissions or boundary changes.
2. **Apply the Quality Verification Checklist** from Section VII.
3. **Present the converted framework** to the user with a change log documenting:
    - Structural changes (sections added, reorganized, or consolidated).
    - Language changes (instructions rewritten for standard compliance).
    - Content additions (new layers, failure modes, criteria, or recovery protocols not in the original).
    - Content flagged for review (potential deficiencies discovered during conversion).

---

## Section VII: Quality Verification Checklist

Apply this checklist to any framework — new, converted, or rendered. Score each item Pass/Fail. All items must pass for the framework to be considered complete.

### Structural Completeness

- [ ] YAML frontmatter present with all required properties.
- [ ] Header Block present with Purpose, Input Contract, Output Contract, and Execution Tier.
- [ ] Milestones Delivered section present, OR pipeline-stage exemption declared in Execution Tier per Section II subsection 2.3.
- [ ] Evaluation Criteria present and positioned before processing layers.
- [ ] All processing layers numbered, named, and bounded with single focus.
- [ ] Self-Evaluation layer present in penultimate position.
- [ ] Error Correction and Output Formatting layer present in final position.
- [ ] Named Failure Modes section present with framework-specific failure modes.
- [ ] Execution Commands block present at end of document.
- [ ] Section 2.13 applicability is stated; when applicable, one human-readable PROCESS APPLICATION CONTRACT is present in the Markdown body.

### Milestones Delivered Compliance

_These items apply only to frameworks that declare Milestones Delivered. Pipeline-stage and fixed-sequence frameworks exempt per Section II subsection 2.3 are not subject to this category; their exemption declaration in Execution Tier is checked under Structural Completeness._

- [ ] Milestones Delivered section is positioned between the Framework Header Block and the Evaluation Criteria.
- [ ] At least one milestone is declared.
- [ ] Every milestone has all required properties defined inline within its block: Endpoint produced, Verification criterion, Layers covered, Required prior milestones, Gear, Output format, Drift check question. Multi-mode frameworks also declare Mode inline per milestone.
- [ ] No milestone property is factored into shared definitions, parent-subsection-only inheritance, or external references — every property is bound inline to its specific milestone path.
- [ ] If the framework has a routing / triage / classification layer that fires before mode selection, M0 is declared at the top of the Milestones Delivered section with Function, Layers covered, and Output.
- [ ] If any milestone declares Conditional layers, both the conditional layer numbers and the activating condition are stated inline within that milestone.
- [ ] Each Verification criterion is objectively evaluable — no ambiguous quality terms without objective evaluation criteria.
- [ ] Each Endpoint produced is a concrete artifact or state change, not an abstract outcome.
- [ ] Each Drift check question is specific enough to surface scope expansion, terminology shift, or premature convergence — not a generic "is this on track?".
- [ ] Each Layers covered list is non-overlapping with other milestones' Layers covered (no layer appears in two milestones, except M0 which is its own routing pass).
- [ ] Required prior milestones references are valid (every M-N reference resolves to a declared milestone; cross-mode references use the mode-prefix syntax `<ModeName>.<MilestoneId>`).
- [ ] Each milestone corresponds to an eligible verification boundary whose accepted result also passes the Milestone Placement Test as a substantial project-level deliverable or state change.
- [ ] Each mode with more than approximately five processing layers has been reviewed for missing verification boundaries; a retained single-milestone design includes rationale in the Execution Tier section.
- [ ] Every accepted PIF verification boundary is preserved, OR a Boundary Change Rationale identifies and justifies each merge, split, move, or removal.
- [ ] Every preserved boundary is explicitly classified as a formal milestone or process-internal verification point; classification alone is not mislabeled as a substantive boundary change.
- [ ] Every process-internal verification point appears in the PROCESS APPLICATION CONTRACT with its containing milestone, acceptance criteria, evaluator requirement, evidence, failure route, and placement rationale.
- [ ] Every verification-boundary milestone identifies Independent review examines, Required evidence, Failure route, and Boundary rationale inline.
- [ ] Multi-mode frameworks declare Mode as an inline property per milestone (single-mode frameworks may omit Mode or write "all").

### Input/Output Integrity

- [ ] Every required input is named with format, source, and required/optional status.
- [ ] Every output is named with format, destination, and quality threshold.
- [ ] Every processing layer's internal input (what it reads) is explicit.
- [ ] Every processing layer's internal output (what it produces) is explicit.
- [ ] Handoffs between layers specify what carries forward and what is discarded.
- [ ] No layer requires information that no previous layer or input provides.

### Evaluation Architecture

- [ ] Every evaluation criterion has a name and a five-level rubric with concrete per-level descriptions of approximately uniform length.
- [ ] Criteria are limited to 7–12. IF more, THEN consolidated or justified.
- [ ] Every criterion is measurable — an independent evaluator could apply it and arrive at a consistent score.
- [ ] The Self-Evaluation layer references all criteria by number and name.
- [ ] The Self-Evaluation layer includes explicit correction trigger phrases.
- [ ] The Self-Evaluation layer includes the calibration warning about systematic overconfidence.
- [ ] The Self-Evaluation layer includes a remediation protocol for below-threshold scores.

### Language Compliance

- [ ] All directives use imperative voice.
- [ ] All conditional logic uses IF/THEN structure.
- [ ] All actors are named explicitly (no ambiguous pronouns).
- [ ] All quantities are specific (no "several," "some," "concise," "brief").
- [ ] All word count requirements are ranges, not single targets.
- [ ] All documents and sections are referenced by name, not description.
- [ ] Directives use affirmative form ("do X") rather than negative ("don't do Y").

### Anti-Drift Compliance

- [ ] Each processing layer has a single primary focus.
- [ ] Critical constraints are restated at the point of application, not only at definition.
- [ ] Frameworks with more than seven layers include an orientation anchor positioned at the start of the next processing block after the midpoint.
- [ ] Section dividers (horizontal rules) separate all layers.
- [ ] Invariant checks present at layer boundaries (except final two layers).

### Think-Then-Format Compliance

- [ ] Every processing layer separates reasoning instructions from formatting instructions.
- [ ] Formatting instructions appear after reasoning instructions within each layer.
- [ ] No format requirements are embedded within reasoning instructions.

### Variable Fidelity Compliance

- [ ] The Error Correction layer includes explicit variable fidelity verification.
- [ ] Layers that establish or transform named variables include variable state summaries in their output format.

### Anti-Confabulation Compliance

- [ ] The Error Correction layer includes an explicit Missing Information Declaration.
- [ ] At least one Named Failure Mode addresses confabulation risk for this framework's specific task.
- [ ] The Self-Evaluation layer includes a confidence assessment requirement.

### Recovery Compliance

- [ ] Recovery protocols specified for layer-level failures (what happens when a layer's output fails its invariant check).
- [ ] Recovery protocols specified for framework-level failures (what happens when Self-Evaluation identifies unresolvable deficiencies).
- [ ] The Error Correction layer includes a Recovery Declaration section.

### Process Application Contract Compliance (When Applicable)

- [ ] The PROCESS APPLICATION CONTRACT is complete, human-readable, and executable without a parser, runtime schema, provider-specific configuration, or multi-stage runtime.
- [ ] YAML remains navigation metadata and contains no machine-only substitute for authorization, evidence, loop, transition, boundary, or final-gate meaning.
- [ ] The applicability rationale identifies the external action, external evidence, authorization, loop, or independent final-decision requirement.
- [ ] Every planning node and execution node has a stable ID, inputs, observable output, acceptance criteria, required evidence, and permitted transitions.
- [ ] Every execution node references only actions explicitly listed in Authorized Actions.
- [ ] Every external artifact or state surface has an identity-provider requirement, required identity attributes, ambiguity behavior, and binding status.
- [ ] Every consequential action states authority, preconditions, reversibility, prohibited effects, and terminal proof.
- [ ] Every evidence item states the claim supported, provider requirement, produced observation, timing, independence, and missing-evidence behavior.
- [ ] Every verification boundary states whether it is a formal milestone or process-internal verification point and identifies its containing milestone.
- [ ] Every loop is synchronous and bounded, with a continuation condition, success condition, hard bound, failure route, and retained evidence.
- [ ] Every non-success outcome has an explicit transition destination; completion is withheld for unresolved authority, provider, identity, evidence, or proof requirements.
- [ ] One `Final gate ID` identifies an evaluator independent of the acting node, required evidence, acceptance criteria, rejection destinations, completion record, and binding status.
- [ ] Every unavailable concrete provider, reviewer, authority, tool, or identity source remains unresolved rather than invented, and its assurance limit is explicit.

### Multi-Stage Runtime Compliance (Multi-Stage Runtime Renderings Only)

- [ ] Stage Boundaries section present with layer-to-stage mapping.
- [ ] Handoff specifications present for each stage boundary.
- [ ] Persistent Reference Document defined with original objective, constraints, and named variables.
- [ ] Tool Definitions present with trigger conditions and failure handling.
- [ ] Checkpoint Protocol present with retry and halt conditions.
- [ ] Python Runner Specification present in natural language.
- [ ] Adversarial Review Points identified where applicable.

### Reasoning-Model Compliance (Reasoning-Model Renderings Only)

- [ ] Chain-of-thought scaffolding removed from processing layers.
- [ ] Few-shot examples removed unless demonstrating edge cases.
- [ ] Processing layer instructions use direct objective statements rather than procedural scaffolding.
- [ ] Evaluation criteria, output contracts, named failure modes, and constraints retained.
- [ ] Self-Evaluation layer simplified to direct evaluation instructions.

### Backward Compatibility (All Renderings)

- [ ] Single-pass rendering contains complete process meaning and can be followed without Ora-specific tool access; unavailable external capabilities trigger the declared withholding or escalation behavior.
- [ ] multi-stage-runtime rendering degrades to single-pass if executed in a commercial AI context.
- [ ] Reasoning-model rendering produces usable output if executed by a non-reasoning model (may not be optimal, but must not break).
- [ ] No rendering requires a specific model or provider to function.
- [ ] IF an external action or verified completion requires an unavailable provider, THEN the rendering preserves the symbolic requirement and withholds the action or claim rather than simulating equivalent assurance.

### Proactive Elicitation Compliance

- [ ] The Execution Commands block or first processing layer includes input validation against the Input Contract.
- [ ] Ambiguous inputs trigger explicit assumption declaration before proceeding.
- [ ] The framework includes proactive gap assessment for likely missing requirements (F-Design mode) or input validation with underspecification assessment (rendered frameworks).

---

## Section VIII: Named Failure Modes in Framework Design

These are the most common ways framework design itself goes wrong. They apply to the meta-process of creating frameworks, not to any specific framework's task.

**The Abstraction Trap:** Designing a framework that describes what good output looks like without specifying the processing steps that produce it. A framework that says "produce psychologically authentic characters" without defining what psychological authenticity means operationally and what processing steps achieve it. Correction: Every quality aspiration must decompose into concrete processing steps and measurable evaluation criteria.

**The Kitchen Sink Trap:** Including every possible consideration in every layer, producing layers that are unfocused and internally competing. A layer that simultaneously handles character psychology, thematic integration, reader engagement, and continuity tracking will do all four poorly. Correction: One primary focus per layer. IF a layer has more than one primary focus, THEN split it.

**The Echo Chamber Trap:** Writing evaluation criteria that merely restate the processing instructions rather than independently defining output quality. IF Criterion 3 says "thematic integration is well-executed" and Layer 4 says "integrate themes well," THEN the evaluation is circular — it will always pass because it measures nothing the processing did not already claim to do. Correction: Evaluation criteria must be independently verifiable. Write them as if they will be applied by a reviewer who has never read the processing instructions.

**The Implicit Handoff Trap:** Assuming the model will naturally carry information between layers without explicit specification. In single-pass mode, this sometimes works because everything is in one context window. In multi-stage runtime, it fails completely because context resets at stage boundaries. Even in single-pass mode, implicit handoffs cause drift over long frameworks. Correction: Every layer boundary has an explicit handoff. What carries forward is named. What is discarded is stated.

**The Persona Inflation Trap:** Creating an elaborate persona with extensive backstory that consumes context without improving output. The persona is a focusing tool, not a character. Correction: Limit persona to name, one-sentence description, and three to five specific capabilities directly relevant to the task. Every persona detail must be task-relevant; irrelevant details produce measurable performance degradation.

**The Criterion Proliferation Trap:** Defining more than twelve evaluation criteria, creating an evaluation burden that the Self-Evaluation layer cannot execute thoroughly in its context allocation. Evaluation quality degrades as criterion count rises — each criterion receives less attention. Correction: Limit criteria to 7–12. IF more dimensions need tracking, THEN consolidate related dimensions into composite criteria.

**The Specification-as-Prose Trap:** Writing framework instructions as flowing prose paragraphs rather than structured directives. Prose is ambiguous. Directives are not. Correction: Apply the Authoring Standards from Section III. Convert every paragraph of instruction into enumerated steps, IF/THEN conditionals, or explicit directives.

**The Tool Assumption Trap (Multi-Stage Runtime):** Designing processing steps that require tool access without defining the tool, its trigger conditions, or its failure handling. The model will either skip the step or confabulate the tool's output. Correction: Every tool reference must point to a formal Tool Definition. Every tool call must have a defined failure path.

**The Monolithic Stage Trap (Multi-Stage Runtime):** Mapping the entire framework to a single execution stage, losing all benefits of multi-stage execution (context window management, checkpoint recovery, adversarial review integration). Correction: Identify natural break points using the criteria from Phase 3, Step 8 of the Framework Design Process.

**The False Atomization Trap:** Splitting a framework into excessive micro-layers that create overhead without analytical benefit. Not every instruction needs its own layer. Correction: Apply the single-focus test. IF two instruction groups share a focus and operate on the same information, THEN they belong in the same layer.

**The Missing Context Trap (Pipeline Frameworks):** Designing a framework as if it operates in isolation when it is actually part of a multi-step pipeline. The framework's Input Contract does not account for what the previous step actually produces, or its Output Contract does not provide what the next step actually needs. Correction: Verify input and output contracts against adjacent pipeline steps during design. IF adjacent steps do not yet exist, THEN specify what this framework requires and produces and flag the dependency.

**The Retroactive Evaluation Trap:** Designing processing layers first and then writing evaluation criteria to match what the layers produce. This reverses the correct design sequence (criteria first, then layers to satisfy criteria) and produces criteria that rubber-stamp whatever the processing happens to generate. Correction: Design evaluation criteria before processing layers. See Governing Principle 5.

**The Silent Variable Collapse Trap:** Variables defined early in processing — character names, numerical quantities, specific entities, scope parameters — are silently dropped, conflated with similar variables, or simplified as processing depth increases. The model does not flag the loss because it does not recognize it as an error. Correction: Include variable inventory requirements at layer boundaries. At any layer that establishes or transforms named variables, include an explicit variable state summary.

**The Simulated Refinement Trap:** In self-evaluation or multi-pass contexts, the model introduces artificial errors into its own output just to demonstrate correction, rather than performing genuine critique. Research documents this as a specific failure mode of stepwise prompting (Sun et al., ACL 2024). Correction: Structure self-evaluation as criterion-by-criterion scoring against concrete rubrics with cited evidence, not open-ended "find and fix problems."

**The Premature Accommodation Trap:** During input elicitation or clarification, the AI abandons important questioning steps when the user signals impatience, sacrificing specification quality for conversational comfort. Research found AI interviewers ended structured interviews prematurely when users expressed time constraints, missing critical requirements. Correction: Framework elicitation sequences must complete mandatory items even when the user signals impatience. The AI may acknowledge the user's time constraint but must flag that skipped items may affect output quality.

**The Format-Before-Reasoning Trap:** Embedding output format requirements within processing instructions, causing the model to prioritize syntactic compliance over analytical quality. Research shows format restrictions cause significant reasoning degradation (Tam et al., EMNLP 2024). Correction: Apply the Think-Then-Format standard from Section 3.9. Processing instructions precede formatting instructions within every layer.

**The Over-Specification Trap:** Specifying requirements the model already satisfies by default, consuming context budget on instructions that add no value while potentially overwhelming the model with competing requirements. Research found that adding more requirements does not reliably improve performance and that LLMs can guess unspecified requirements 41.1% of the time (Yang et al., CMU 2025). Correction: Specify what the model will not get right by default. Leave implicit what it handles well natively. Test against real inputs to identify which specifications are actually needed.

**The Boundary Desert Trap:** Consequential work proceeds across a long span without an independently reviewable stop, so defects are discovered only after expensive or irreversible downstream effects. Correction: Place verification boundaries where observable results, independent criteria, and meaningful failure routes justify review.

**The Checkpoint Confetti Trap:** Milestones proliferate around layers, handoffs, or tool calls that produce no independently judgeable result, creating review cost without assurance. Correction: Retain only eligible verification boundaries and treat layer or stage count as a warning signal rather than a milestone rule.

**The Unreviewable Boundary Trap:** A milestone claims to be a verification point but lacks an observable result, independent evaluator requirement, evidence, or failure destination. Correction: Complete all boundary semantics or merge the checkpoint into the next eligible boundary with a Boundary Change Rationale.

**The Capability Hallucination Trap:** PFF fills an unspecified provider, authority, identity source, reviewer, or tool with a plausible concrete binding. Correction: Preserve the symbolic requirement, mark the binding unresolved, and withhold affected actions or completion claims.

**The Probe–Verification Confusion Trap:** An exploratory test or information-gathering probe is treated as acceptance of production work. Correction: Label probes as learning activities and require separate acceptance evidence at the governing verification boundary.

**The Platform Capture Trap:** Runtime schemas, provider names, runtime stages, or tool mechanics become the only place where operational meaning exists. Correction: Keep the PROCESS APPLICATION CONTRACT complete in natural-language Markdown and treat every implementation binding as an optional projection.

---

## Section IX: Reference Examples — Structural Patterns

This section provides abbreviated structural patterns for common framework types. These are not complete frameworks — they are structural skeletons showing how the Framework Anatomy maps to specific use cases.

### 9.1 Analytical Framework Pattern

For frameworks that analyze input material and produce structured assessment.

```
Header Block:
  Purpose: Analyze [input type] and produce [assessment type].
  Input Contract: [Source material] + [evaluation criteria or rubric].
  Output Contract: [Structured assessment with scored dimensions].

Evaluation Criteria: [Dimension-specific criteria with five-level rubrics.]

Layer 1: Input Analysis — Read and decompose input material into
         assessable components.
Layer 2: Dimension Mapping — Map components to evaluation dimensions.
Layer 3: Assessment Execution — Evaluate each dimension with evidence.
         [Think-Then-Format: analyze first, structure scores second.]
Layer 4: Synthesis — Produce integrated assessment with priorities.
Layer 5: Self-Evaluation (with correction triggers and calibration warning).
Layer 6: Error Correction and Output Formatting (with variable fidelity
         check and Recovery Declaration).

Named Failure Modes:
- The Surface Reading Trap
- The Criterion Conflation Trap
- The Unsupported Score Trap
```

### 9.2 Generative Framework Pattern

For frameworks that produce creative or structured content from specifications.

```
Header Block:
  Purpose: Generate [content type] from [input specifications].
  Input Contract: [Specification documents] + [reference materials] +
                  [author direction].
  Output Contract: [Generated content in specified format] +
                   [condensed variant if applicable].

Evaluation Criteria: [Content quality criteria with five-level rubrics.]

Layer 1: Specification Intake — Parse requirements and constraints.
         [Includes proactive gap assessment for likely missing requirements.]
Layer 2: Foundation Principles — Establish governing standards for
         generation.
Layer 3-N: Domain-Specific Processing Layers — Generate content
           through progressive development stages.
           [Think-Then-Format applied to every layer.]
           [Invariant checks at every layer boundary.]
           [Orientation anchor at midpoint if N > 7.]
Layer N+1: Self-Evaluation (with correction triggers).
Layer N+2: Error Correction and Output Formatting (with variable
           fidelity check and Recovery Declaration).

Named Failure Modes:
- The Prompt Echo Trap (restating input as output)
- The Drift Trap (progressive departure from specifications)
- The Density Trap (inflating word count without information gain)
- The Silent Variable Collapse Trap
```

### 9.3 Pipeline Step Framework Pattern

For frameworks that occupy a position in a multi-step automated pipeline.

```
Header Block:
  Purpose: Execute Step [N] of [pipeline name].
           Receive [previous step output] and produce [next step input].
  Input Contract: [Previous step output specification] +
                  [persistent reference documents].
  Output Contract: [Deliverable for this step] +
                   [handoff package for next step].

Evaluation Criteria: [Step-specific criteria with five-level rubrics] +
                     [pipeline integration criteria].

Layer 1: Input Validation — Verify all required inputs from previous
         step are present and well-formed. IF missing or malformed,
         THEN halt and report.
Layer 2-N: Step-Specific Processing Layers.
           [Think-Then-Format applied to every layer.]
Layer N+1: Handoff Preparation — Extract minimum information forward
           per the next step's input contract.
Layer N+2: Self-Evaluation.
Layer N+3: Error Correction and Output Formatting (with Recovery
           Declaration specifying impact on downstream steps).

Multi-Stage Runtime Metadata:
  Stage Boundaries: [Defined based on processing requirements.]
  Persistent Reference Document: [Pipeline objective, scope boundaries,
     named variables carried from Step 1.]
  Tool Definitions: [file_read, file_write, rag_query as applicable.]
  Checkpoint Protocol: [Standard protocol with step-specific additions.]
  Adversarial Review Points: [After primary processing, before handoff.]
  Python Runner Specification: [Step-specific orchestration requirements.]

Named Failure Modes:
- The Orphan Output Trap (producing output the next step cannot consume)
- The Context Contamination Trap (carrying forward noise from input)
- The Silent Failure Trap (proceeding despite missing required inputs)
- The Silent Variable Collapse Trap
```

### 9.4 Evaluation Framework Pattern

For standalone frameworks designed to assess the output of other frameworks.

```
Header Block:
  Purpose: Evaluate the output of [framework name] against its
           evaluation criteria.
  Input Contract: [Framework output to evaluate] +
                  [evaluation criteria from the original framework] +
                  [original input materials for reference].
  Output Contract: [Scored evaluation with criterion-by-criterion
                   assessment] + [specific remediation recommendations
                   for any below-threshold scores].

Evaluation Criteria: [Meta-criteria for evaluation quality — assessing
                     whether the evaluation itself is thorough, fair,
                     and actionable. Five-level rubrics.]

Layer 1: Criteria Loading — Parse and internalize all evaluation criteria
         from the source framework.
Layer 2: Evidence Mapping — For each criterion, identify specific evidence
         in the output that supports scoring.
Layer 3: Criterion-by-Criterion Scoring — Score each criterion with
         cited evidence. Use correction triggers before each score.
         For each below-threshold score, draft a specific remediation
         recommendation. [Think-Then-Format.]
Layer 4: Cross-Criterion Consistency Check — Verify that scores across
         criteria are logically consistent (a high score on
         "psychological authenticity" with a low score on "response
         pattern consistency" requires explanation).
Layer 5: Synthesis — Produce overall assessment with prioritized
         remediation recommendations.
Layer 6: Self-Evaluation.
Layer 7: Error Correction and Output Formatting.

Named Failure Modes:
- The Inflation Trap (scoring generously to avoid delivering bad news)
- The Criterion Blindness Trap (evaluating against general quality
  rather than the specific criteria defined for this framework)
- The Vague Remediation Trap (identifying deficiencies without
  specifying exactly what should change)
```

### 9.5 Conversion Framework Pattern

For frameworks that transform an existing document from one format or standard to another.

```
Header Block:
  Purpose: Convert [source document type] to [target standard/format].
  Input Contract: [Source document] + [target standard specification].
  Output Contract: [Converted document conforming to target standard] +
                   [change log documenting all modifications].

Evaluation Criteria: [Completeness of conversion] +
                     [preservation of intellectual content] +
                     [compliance with target standard].
                     [Five-level rubrics for each.]

Layer 1: Source Analysis — Read and inventory all intellectual content
         in the source document.
Layer 2: Gap Analysis — Compare source structure against target standard.
         Identify all structural, language, and content gaps.
Layer 3: Conversion Execution — Restructure source content into target
         format. Apply target language standards. Add required sections.
         [Think-Then-Format.]
Layer 4: Content Preservation Verification — Cross-check that every
         instruction, criterion, and processing step from the source
         exists in the converted output.
Layer 5: Self-Evaluation.
Layer 6: Error Correction and Output Formatting.

Named Failure Modes:
- The Silent Omission Trap (dropping source content during restructuring)
- The Over-Standardization Trap (forcing generic structure where the
  source had justified custom structure)
- The Format-Over-Substance Trap (achieving structural compliance
  while degrading intellectual content)
```

---

## Section X: Integration with CFF and OFF

PFF is one of three sibling meta-frameworks. The Corpus Formalization Framework (CFF) formalizes the knowledge corpus where information accumulates across a workflow. The Output Formalization Framework (OFF) formalizes the rendered artifacts that express corpus content. The full three-framework integration is specified in `Reference — PFF-CFF-OFF Integration Architecture.md`. This section provides PFF's perspective on that architecture.

### Detection trigger built into PFF design

When a user invokes PFF (mode F-Design), the design process includes the question:

> _Does this process feed a workflow with multiple sources or multiple outputs?_

If yes, PFF recommends invoking CFF in parallel to design the corpus the bespoke PFF will write into. The bespoke PFF's output contract is then aligned with a specific corpus section.

If no, the bespoke PFF stands alone (Shape 1) or feeds directly to an OFF (Shape 3).

The detection is gated on user confirmation. The user may decline; PFF proceeds with whatever shape they prefer.

### Composition shapes from PFF's perspective

The integration architecture defines four composition shapes. From PFF's perspective:

- **Standalone PFF (Shape 1):** the bespoke PFF runs and presents output directly to the user. No corpus, no OFF.
- **Direct PFF→OFF (Shape 3, degenerate corpus):** the bespoke PFF's output flows directly into a bespoke OFF as its content input. The PFF's output contract and the OFF's input contract must align.
- **Corpus-mediated (Shape 4, the standard pattern):** the bespoke PFF writes into a specified corpus section. CFF's template defines the section; the bespoke PFF's write contract aligns with the section's expected content.

### PFF write contract for corpus-mediated composition

For Shape 4 composition, the bespoke PFF declares:

- Which corpus it writes to (by template name and instance directory)
- Which section of the corpus it writes (by section name)
- What content shape it produces (matching the corpus section's expected content schema)
- What happens when the PFF cannot run successfully (write contract surfaces failure to the corpus's missing-data behavior)

The write contract becomes part of the corpus's source assignment in CFF Layer 4 (Source Identification).

### Reference

Full architecture: `Reference — PFF-CFF-OFF Integration Architecture.md`. Sibling specifications: `Framework — Corpus Formalization.md` and `Framework — Output Formalization.md`.

---

## Section XI: Execution Commands

---

## EXECUTION COMMANDS

1. Confirm you have fully processed this meta-framework and any associated input materials.
2. Identify the operating mode from the user's input:

    - **Mode F-Design:** User describes a new framework to create. Follow the Framework Design Process (Section IV). **Default output: one consolidated framework file** (single-pass rendering, which is also the canonical intellectual source).
    - **Mode F-Convert:** User provides an existing framework. Follow the Conversion Protocol (Section VI). **Default output: one consolidated converted framework file.**
    - **Mode F-Render:** User provides an existing framework and explicitly wants an additional execution variant beyond the default. Follow the Rendering Protocol (Section V). Output: one additional rendering file.
    - **Mode F-Audit:** User provides a framework for evaluation. Apply the Quality Verification Checklist (Section VII). Output: audit report presented inline by default; persistent file only if requested.
3. IF the mode is ambiguous, THEN ask the user to confirm before proceeding.
4. Execute the appropriate process. **Produce the default single-file output unless the user has explicitly requested additional renderings with stated rationale.** If the architecture clearly warrants suggesting an additional rendering (e.g., complexity assessment of >8 layers suggests multi-stage-runtime may be valuable), surface the recommendation as a choice and proceed with single-file output unless the user accepts.
5. IF the process is externally acting, THEN preserve or elicit the PIF Process Capability Requirements and Verification-Boundary Map, apply Section 2.13, and keep unavailable concrete bindings unresolved. IF a proposed external action is outside confirmed authority, THEN withhold it and request authorization rather than expanding scope.
6. Apply the Quality Verification Checklist to all outputs before delivery. Include Process Application Contract Compliance when applicable. Present the verification inline as a pass/fail summary unless the user requested a persistent verification file.
7. Produce a Framework Registry Entry for every framework specification produced. The entry follows this format:

    FRAMEWORK REGISTRY ENTRY Name: [framework name from the specification's title] Purpose: [one sentence from the specification's PURPOSE section] Problem Class: [what category of problem this framework solves — inferred from the specification's purpose and input contract] Input Summary: [condensed from the specification's INPUT CONTRACT — required inputs only, one line each] Output Summary: [condensed from the specification's OUTPUT CONTRACT — primary outputs only, one line each] Proven Applications: [list any test cases run during this session; if none, state "None yet — initial version"] Known Limitations: [inferred from the specification's Named Failure Modes — one sentence summarizing the most significant risk] File Location: [the path where the specification file will be saved] Provenance: [human-created | model-assisted] Confidence: [low — initial version | medium — tested against 3+ diverse inputs | high — tested against 10+ diverse inputs with consistent results] Version: [from the specification's YAML frontmatter framework_version]

    Present the registry entry alongside the framework specification. Instruct the user (or model step) to save the entry to the framework registry file and index it in ChromaDB's knowledge collection.

8. Present outputs with a summary of decisions made, gaps identified, unresolved bindings, assurance limits, and recommendations for refinement.

---

## Section XII: Operational Safeguards and Reference

This section preserves the concise v2.2 execution safeguards that complement the full structural specification above.

### 12.1 Approval and Change-Control Gates

Apply these gates in every mode:

1. **F-Design:** Restate the task, enumerate hard requirements, resolve structure-changing ambiguities, and announce the proposed mode structure and deliverable before drafting. Wait for explicit approval or correction.
2. **F-Convert:** Inventory the existing structure and deviations, then state exactly what will change and what will be preserved. Wait for explicit approval before converting. Preserve substance; modernize structure.
3. **F-Render:** Confirm the rationale for an additional file before rendering. Treat the consolidated framework as canonical, preserve all domain logic, and use an unambiguous `-multi-stage-runtime` or `-reasoning-model` suffix.
4. **F-Audit:** Score the framework and propose concrete fixes, but do not modify files during the audit. Apply changes only after user approval.

For externally acting processes, user approval of the framework design does not itself authorize every external action described by that framework. Bind each action to the authority stated in the PROCESS APPLICATION CONTRACT. IF authority is absent or narrower than the proposed effect, THEN withhold the action and report the exact authorization needed.

Frameworks are authored and modified through PFF or another guided framework, not by ungrounded direct editing. If direct edits occurred, the next guided session must revisit the relevant Problem Evolution record and verify that the change still serves the original problem before accepting it as canonical.

### 12.2 Compact Audit Rules

Use `Pass / Flag / Fail` when diagnostic nuance is useful; production-ready output still requires every applicable item to pass.

- **Pass:** present, correct, internally consistent, and operationally usable.
- **Flag:** present but ambiguous, suboptimal, or at risk; user judgment is required.
- **Fail:** absent, incorrect, contradictory, or non-executable; remediation is required.

For every flag or failure, cite the exact location and propose a concrete correction. Run the audit top-down and bottom-up. Cross-check Setup Questions, Execution, and Output Contract in both directions. Count hard limits mechanically; do not estimate them. A Setup Question is orphaned if Intake, Execution, and Output Contract never consume it.

### 12.3 File-Proliferation Gate

The default output of F-Design and F-Convert is exactly one consolidated framework file. Before delivery, verify:

1. The Output Contract promises only what Execution produces.
2. Execution produces everything the Output Contract promises.
3. No additional rendering exists without an explicit request, a stated rationale, and user acceptance.
4. Any requested variant faithfully renders the corrected consolidated source rather than accumulating its own canonical changes.
5. Any PROCESS APPLICATION CONTRACT remains inside the consolidated framework file; do not split capability, evidence, loop, transition, or final-gate semantics into a sidecar specification.

### 12.4 Quality Bars

**Production-ready** requires all standard sections to be present and non-empty, zero audit failures or flags, valid cross-references, picker copy within its hard limits, consistency between Execution and Output Contract, and at least one real-input test.

**Draft** requires all standard sections, zero failures, flags explicitly recorded, approximate Execution/Output consistency, draft picker copy, and a declared cross-reference-validation status.

**Rough sketch** requires at minimum an Execution section and Output Contract. Other sections may remain absent, and the audit need not yet have run.

### 12.5 Named Operational Failure Modes

**FM-1 — Scope creep during F-Design.** The design grows beyond confirmed hard requirements. *Recovery:* remove every element that no confirmed requirement, quality criterion, or accepted gap assessment justifies.

**FM-2 — Conversion loses domain logic.** Structural normalization strips load-bearing content. *Recovery:* compare source and conversion before delivery; restore or explicitly escalate every omitted substantive element.

**FM-3 — Audit misses a failure.** A top-down pass overlooks a contradiction. *Recovery:* repeat the audit bottom-up and explicitly cross-check Output Contract against Execution.

**FM-4 — Picker text exceeds runtime limits.** Display Name exceeds 60 characters or Display Description exceeds 500 characters. *Recovery:* count mechanically and revise before delivery.

**FM-5 — Mode confusion.** Input matches multiple modes or none. *Recovery:* resolve the mode during intake; ask one discriminating question when the ambiguity cannot be resolved from provided context.

**FM-6 — Unsolicited variants.** PFF produces files the user did not request. *Recovery:* retain only the consolidated canonical and surface optional variants as choices.

**FM-7 — Stale cross-references.** A referenced framework or vault artifact was renamed, archived, or materially changed. *Recovery:* validate existence and semantic compatibility against current canonical state.

**FM-8 — Version mismatch.** Version metadata, body labels, and end markers disagree. *Recovery:* establish one version and update every declaration before delivery.

**FM-9 — Boundary drift.** Drafting, conversion, or rendering silently moves or removes a PIF-proposed verification boundary. *Recovery:* restore the boundary or add a Boundary Change Rationale and re-run Process Application Contract Compliance.

**FM-10 — False completion under degraded assurance.** An unavailable provider, reviewer, identity source, or final gate is treated as optional and completion is still claimed. *Recovery:* preserve the unresolved requirement, identify the affected action or claim, and route to the contract's escalation or blocked destination.

### 12.6 Research Basis Preserved from v2.1

The v2.1 design synthesis recorded five operational findings that remain part of PFF's rationale:

1. Structured decomposition reduced hallucination and improved completeness relative to monolithic prompts; therefore every non-trivial framework uses phases with explicit deliverables.
2. Restate-and-confirm intake reduced downstream error propagation; therefore intake is a load-bearing control rather than optional conversational scaffolding.
3. Explicit output contracts reduced structural variance; therefore exact deliverable, format, file count, and naming are runtime quality gates.
4. Named failure modes reduced recurrence through attentional priming; therefore generic cautions are replaced with named patterns and recovery instructions.
5. Deliverable-first picker descriptions reduced selection errors; therefore Display Description is user-routing infrastructure, not decorative copy.

These findings are design inputs, not a substitute for current empirical testing. When a source study, internal synthesis, or runtime limit changes, update the affected rule and record the change in the version history.

### 12.7 Compact Glossary

- **Consolidated framework file:** the single canonical, executable framework specification used inside and outside Ora.
- **Execution variant:** an opt-in rendering for a specific environment; never an independent source of truth.
- **Hard requirement:** a confirmed non-negotiable constraint captured during intake.
- **Intake Protocol:** pre-execution confirmation, ambiguity resolution, and approval steps.
- **Orphan question:** a setup question that no downstream instruction consumes.
- **Output Contract:** the exact deliverable, format, file count, destination, and quality promise.
- **Phase bleed:** work assigned to one phase being performed in another, obscuring boundaries and handoffs.
- **Process Capability Requirements:** PIF's domain-neutral statement of the external artifacts, authorized actions, evidence and identity providers, loop needs, transitions, verification boundaries, and final-gate requirements a process must support.
- **PROCESS APPLICATION CONTRACT:** the consolidated human-readable Section 2.13 formalization of an externally acting process application's nodes, artifacts, authority, evidence, loops, transitions, boundaries, and independent final gate.
- **Verification boundary:** a substantive stop where an observable result is judged against explicit criteria using required evidence and a defined failure route before progression.
- **Boundary Change Rationale:** the explicit record required when PFF merges, splits, moves, or removes a PIF-proposed verification boundary.
- **Self-audit:** applying F-Audit to a draft before delivery.

### 12.8 Version History

- **v1.0:** Four-mode baseline with structural format, picker fields, and audit checklist.
- **v2.0:** Added research basis and quality benchmarks; strengthened picker validation.
- **v2.1:** Integrated multi-step prompting findings and tightened operational guidance.
- **v2.2:** Made one consolidated file the F-Design/F-Convert default; gated additional variants behind explicit rationale and approval; integrated milestone, recovery, variable-fidelity, CFF/OFF, and full rendering contracts into this single canonical.
- **v2.3:** Reconciled two divergent v2.2 lines into this single canonical. Preserved the richer full specification and the concise operational safeguards, standardized the Display Description limit at 500 characters, corrected the framework end marker, and restored exact vault-to-Ora body parity.
- **v2.4:** Added domain-neutral externally acting process formalization in §2.13; made PIF verification boundaries authoritative design inputs placed either as formal milestones or process-internal verification points; reserved Boundary Change Rationales for substantive boundary changes; allowed optional YAML runtime identifiers as navigation bindings while keeping all operational meaning in Markdown; formalized artifacts, identity, authorized actions, planning and execution nodes, acceptance, evidence, bounded loops, transitions, unresolved bindings, and an independent final gate in the standalone PROCESS APPLICATION CONTRACT. This is an untested capability release; Programming Oversight derivation and cross-domain trials remain pending.
- **v2.5:** Recast externally acting frameworks as exact versioned Process Definitions over the domain-general graph grammar; replaced durable-actor-specific renderings and provenance with bounded-judgment and multi-stage runtime projections; added Process Run continuation/recovery and package-manifest semantics; required all seven directives with intermediate `PROCEED`, final-only `ACCEPT`, generic `REDEFINE`, and typed-authority `ESCALATE`; and retained `PASS` / `FAIL` / `BROKEN` only as local observations.

---

## USER INPUT

[State Mode F-Design (new framework, default single-file output), Mode F-Convert (modernize existing, default single-file output), Mode F-Render (generate an additional execution variant from an existing framework — explicit opt-in path), or Mode F-Audit (evaluate against standards) — or let the AI auto-detect from your input. Then provide your input materials.]

---

**END OF PROCESS FORMALIZATION FRAMEWORK v2.5**
