# Process Formalization Framework

*A Meta-Framework for Formalizing Domain Expertise into Executable AI Specifications*

*Version 2.0*

*Research-backed update incorporating findings from "Best Practices for Multi-Step AI Prompting" (Appendix)*

---

## How to Use This File

This is a meta-framework — a framework for creating frameworks. It serves four functions:

1. **Design new frameworks from scratch** by following the Framework Design Process (Section IV).
2. **Convert existing frameworks** to the current standard by following the Conversion Protocol (Section VI).
3. **Render execution variants** (single-pass commercial, agent mode, or reasoning-model) from a canonical specification by following the Rendering Protocol (Section V).
4. **Audit existing frameworks** against the quality standard by following the Quality Verification Checklist (Section VII).

Paste this entire file into any AI session — commercial (Claude, ChatGPT, Gemini) or local swarm model — then provide your input below the USER INPUT marker at the bottom. State which function you need, or the AI will determine it from context.

**Mode F-Design:** You have a task that needs a framework. You will describe what the framework must accomplish, what inputs it receives, and what outputs it produces. The AI will guide you through the full design process and produce a canonical specification plus rendered variants.

**Mode F-Convert:** You have an existing framework that needs modernization. Paste the old framework as input. The AI will analyze it against the current standard, identify gaps, and produce an updated version conforming to the Framework Anatomy and Authoring Standards defined here.

**Mode F-Render:** You have a canonical specification and need one or more execution variants generated from it. Paste the specification as input and state which variant you need (single-pass, agent mode, reasoning-model, or any combination).

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

---

## MILESTONES DELIVERED

This framework's own declaration of the project-level milestones it can deliver. Used by the Problem Evolution Framework (PEF) to invoke this framework for milestone delivery under project supervision.

### Milestone Type: New framework specification

- **Endpoint produced:** Canonical framework spec document + executable copy + Framework Registry entry
- **Verification criterion:** All items in the Quality Verification Checklist (Section VII) pass for the produced spec
- **Preconditions:** A task definition, input/output inventory, quality dimensions, and failure modes are provided by the user
- **Mode required:** F-Design
- **Framework Registry summary:** Designs new framework specifications from task requirements

### Milestone Type: Modernized framework specification

- **Endpoint produced:** Updated canonical framework spec conforming to the current Framework Anatomy and Authoring Standards
- **Verification criterion:** All items in the Quality Verification Checklist pass; cross-check confirms all original framework intellectual content is preserved in the updated version
- **Preconditions:** An existing framework specification requiring modernization
- **Mode required:** F-Convert
- **Framework Registry summary:** Converts legacy framework specifications to current standard

### Milestone Type: Rendered execution variant

- **Endpoint produced:** A new framework file (single-pass, agent-mode, or reasoning-model) rendered from a canonical specification
- **Verification criterion:** The rendered variant passes the rendering-specific compliance checks in the Quality Verification Checklist
- **Preconditions:** A canonical framework specification and a named target execution environment
- **Mode required:** F-Render
- **Framework Registry summary:** Renders execution variants from canonical framework specifications

### Milestone Type: Framework audit report

- **Endpoint produced:** Scored audit report documenting framework compliance against Quality Verification Checklist with specific remediation recommendations
- **Verification criterion:** Report assigns a pass/fail to every checklist item and identifies each failure's specific location in the framework being audited
- **Preconditions:** A framework specification ready for audit
- **Mode required:** F-Audit
- **Framework Registry summary:** Audits frameworks against quality standard and provides remediation

---

## Section I: Governing Principles

These principles govern all framework design decisions. When a design choice is ambiguous, resolve it by reference to these principles in priority order.

### 1. Specification Is the Control Surface

A framework is a natural language specification. It is not code, not a suggestion, and not a style guide. The framework defines what happens, in what order, with what inputs, producing what outputs, meeting what standards. The AI's role is execution, not interpretation. Every instruction that requires interpretation is an instruction that will be interpreted differently by different models, producing inconsistent results.

**Design implication:** Prefer explicit directives over implied expectations. Prefer concrete criteria over qualitative descriptions. Prefer enumerated options over open-ended guidance.

### 2. Separation of Intellectual Content from Execution Environment

The intellectual content of a framework — what it accomplishes, what quality standards govern it, what evaluation criteria apply — is independent of how it executes. The same intellectual content renders into a single-pass framework for commercial AI, an agent mode file for a local swarm, a reasoning-model profile, or any future execution environment. The canonical specification captures the intellectual content. Execution variants are renderings, not rewrites.

**Design implication:** Do not embed execution-environment assumptions into the specification. Stage boundaries in the specification are logical, not mechanical. Whether a stage boundary becomes an actual context window reset (agent mode) or remains a conceptual division within a single pass (commercial mode) is a rendering decision, not a design decision.

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

Research validates this directly: Anthropic's context engineering research found that "giving LLMs more context often makes them perform worse, not better, in instruction-following tasks." Sub-agent architectures that return condensed summaries (1,000–2,000 tokens from 10,000+ token explorations) outperform monolithic context injection.

**Design implication:** Organize framework instructions into discrete layers/stages with clear focus boundaries. Each stage should be comprehensible on its own terms without requiring the model to hold all other stages in active attention simultaneously.

### 8. Backward Compatibility

A framework designed for agent execution must degrade gracefully to single-pass execution. A framework designed for a two-model adversarial pipeline must degrade gracefully to single-model execution. Agent-tier metadata (tool definitions, checkpoint protocols, stage boundary markers) is ignored by commercial AI in single-pass mode, and this is by design. No framework should require a specific execution environment to produce useful output.

### 9. Recovery Is Architecture, Not Exception Handling

Contracts that specify only what must be true — preconditions, postconditions, quality thresholds — are incomplete. A complete contract also specifies what happens when violations occur. The Agent Behavioral Contracts framework (2026) proved mathematically that if recovery rate exceeds natural drift rate, behavioral drift is bounded. The key parameter in controlling drift is not the quality of the original instructions but the speed and specificity of recovery when drift occurs.

**Design implication:** Every framework must specify recovery protocols at two levels. At the layer level: what happens when a layer's output fails its local quality check (retry with flagged deficiency, halt and report, or proceed with explicit acknowledgment). At the framework level: what happens when the Self-Evaluation layer identifies an unresolvable deficiency (flag for human review, specify what additional input would resolve it, or identify which upstream layer needs rework).

### 10. Complexity-Appropriate Design

Not every task benefits from full multi-layer decomposition. Research on budget-aware evaluation (EMNLP 2024) found that excessive decomposition produces diminishing returns and can decrease performance. Simple chain-of-thought with self-consistency is extremely competitive against more complex multi-step strategies for straightforward tasks.

Empirical evidence converges on a practical complexity ceiling of approximately 10–12 processing layers within a single context window, beyond which anti-drift techniques become essential and performance degrades noticeably. This ceiling varies by model capability and task complexity.

**Design implication:** The Framework Design Process includes a complexity assessment that routes simple tasks to fewer layers. A three-layer framework (Input Validation, Core Processing, Self-Evaluation + Output) is a legitimate and often optimal design for straightforward tasks. Layer count should match task complexity, not a target architecture. When a framework exceeds 10–12 layers for single-pass execution, split it into multiple execution stages (agent mode) or a multi-pass sequence with explicit carry-forward specifications.

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
execution_tier: [specification | single-pass | agent | reasoning-model]
pipeline_step: [step number if part of a multi-step pipeline, or "standalone"]
---
```

The `execution_tier` property identifies the document's role:
- `specification` — Canonical intellectual content. Model-agnostic, environment-agnostic.
- `single-pass` — Rendered for commercial AI, single context window execution.
- `agent` — Rendered for swarm execution with stage boundaries, tool access, and state management.
- `reasoning-model` — Rendered for reasoning-specialized models (o3, o4, DeepSeek R1) with simplified instruction profile.

The `pipeline_step` property identifies the framework's position in a multi-step pipeline, or "standalone" if the framework operates independently.

### 2.2 Framework Header Block

The header block appears immediately after frontmatter. It provides the AI with essential orientation before any processing begins.

```
# [Framework Name]

## PURPOSE
[One to three sentences. What this framework produces and why it exists.
Name the deliverable concretely, not the aspiration.]

## INPUT CONTRACT
[Explicit enumeration of every input this framework requires.
For each input: name, format, source, and whether required or optional.]

## OUTPUT CONTRACT
[Explicit enumeration of every output this framework produces.
For each output: name, format, destination, and quality threshold.]

## EXECUTION TIER
[specification | single-pass | agent | reasoning-model]
[If agent: list of available tools and their trigger conditions.]
[If single-pass: state that all stages execute sequentially in one context window.]
[If reasoning-model: state that instructions are simplified for
internal reasoning models.]
```

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

Every framework that delivers project-level milestones declares them here. This declaration is the handoff point between project supervision (via the Problem Evolution Framework, PEF) and framework execution — when PEF needs a milestone delivered, it consults this section to identify which framework to invoke.

The Milestones Delivered section is required for every framework that can be selected by PEF for milestone delivery.

**Exemption for pipeline-stage and fixed-sequence frameworks:** Frameworks invoked deterministically by a parent pipeline driver or orchestrator — not selected by PEF — are exempt from this requirement. Examples include the Gear 4 pipeline stage frameworks (F-Analysis-Breadth, F-Analysis-Depth, F-Evaluate, F-Revise, F-Consolidate, F-Verify) and Phase A prompt cleanup. These frameworks produce intermediate outputs that feed the next stage; they do not deliver standalone project milestones.

Exempt frameworks must declare the exemption explicitly in their Execution Tier section with a statement of the form: *"This framework is invoked as part of [pipeline or orchestration name]; it is not PEF-selectable and does not declare Milestones Delivered."*

```
## MILESTONES DELIVERED

### Milestone Type: [Name]
- **Endpoint produced:** [concrete artifact or state change this framework produces]
- **Verification criterion:** [how to objectively determine the milestone is achieved]
- **Preconditions:** [what must be true in the current state for the framework to deliver this milestone]
- **Mode required (if applicable):** [which framework mode applies, e.g., F-Design]
- **Framework Registry summary:** [one-line searchable summary for the Registry entry]

[Additional Milestone Types follow the same structure]
```

**Format standards:**

- A framework may declare multiple milestone types when different modes produce different outcomes.
- The **Endpoint produced** is a concrete deliverable or state change — a specific artifact, file, or observable change in the system. Abstract outcomes are prohibited.
- The **Verification criterion** must be objectively determinable. It uses the same standard as Resolution Statements in the Mission, Objectives, and Milestones Clarification Framework. Ambiguous quality terms ("good," "robust," "complete") are prohibited unless paired with objective evaluation criteria that allow any observer to determine pass/fail without subjective interpretation.
- **Preconditions** describe what must hold before the framework can execute successfully — inputs required plus any state conditions in the project or system.
- **Mode required** is specified when the framework has multiple modes that deliver different milestone types.
- The **Framework Registry summary** is a single-line phrase copied into the Registry's "Delivers" field to enable semantic search.

**During F-Design:** The designer elicits milestones delivered as part of Phase 1, Question 1 of the Framework Design Process. For each milestone type, the question is: *"What concrete endpoint does this framework produce, how is achievement objectively verified, and what must be true for the framework to run successfully?"* Each declared milestone type becomes an entry in this section.

**Example — the Process Formalization Framework itself:**

```
## MILESTONES DELIVERED

### Milestone Type: New framework specification
- **Endpoint produced:** Canonical framework spec document + executable copy + Framework Registry entry
- **Verification criterion:** All items in the Quality Verification Checklist (Section VII) pass for the produced spec
- **Preconditions:** A task definition, input/output inventory, quality dimensions, and failure modes are provided by the user
- **Mode required:** F-Design
- **Framework Registry summary:** Designs new framework specifications from task requirements

### Milestone Type: Modernized framework specification
- **Endpoint produced:** Updated canonical framework spec conforming to the current Framework Anatomy and Authoring Standards
- **Verification criterion:** All items in the Quality Verification Checklist pass; cross-check confirms all original framework intellectual content is preserved in the updated version
- **Preconditions:** An existing framework specification requiring modernization
- **Mode required:** F-Convert
- **Framework Registry summary:** Converts legacy framework specifications to current standard

### Milestone Type: Rendered execution variant
- **Endpoint produced:** A new framework file (single-pass, agent-mode, or reasoning-model) rendered from a canonical specification
- **Verification criterion:** The rendered variant passes the rendering-specific compliance checks in the Quality Verification Checklist
- **Preconditions:** A canonical framework specification and a named target execution environment
- **Mode required:** F-Render
- **Framework Registry summary:** Renders execution variants from canonical framework specifications

### Milestone Type: Framework audit report
- **Endpoint produced:** Scored audit report documenting framework compliance against Quality Verification Checklist with specific remediation recommendations
- **Verification criterion:** Report assigns a pass/fail to every checklist item and identifies each failure's specific location in the framework being audited
- **Preconditions:** A framework specification ready for audit
- **Mode required:** F-Audit
- **Framework Registry summary:** Audits frameworks against quality standard and provides remediation
```

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

### 2.7 Self-Evaluation Layer

A dedicated processing layer (always the penultimate layer) where the model evaluates its own output against the Evaluation Criteria from Section 2.3.

```
## LAYER [N]: SELF-EVALUATION

**Stage Focus**: Evaluate all output produced in Layers 1 through [N-1]
against the Evaluation Criteria defined in Section 2.3.

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

### 2.9 Agent-Tier Metadata (Agent Mode Only)

This section appears only in agent-mode renderings. It is absent from specifications, single-pass renderings, and reasoning-model renderings.

```
## AGENT EXECUTION METADATA

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
Provenance: [human-created | agent-created]
Confidence: [low | medium | high]
Version: [semantic version]
Delivers: [one-line summary per milestone type, semicolon-separated]
```

Registry entries are indexed in ChromaDB's knowledge collection for semantic search. When an agent needs a framework, it queries the registry rather than loading all framework files into context.

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

1. **Task Definition and Milestones Delivered:** What does this framework produce as its immediate deliverable(s)? Then: what project-level milestones can this framework deliver? For each milestone type, identify (a) the concrete endpoint produced, (b) how achievement would be objectively verified, (c) preconditions that must hold for successful execution, (d) which mode (if any) delivers this milestone type, and (e) a one-line summary suitable for the Framework Registry's "Delivers" field.
2. **Input Inventory:** What information does this framework receive as input? For each input: What is it? Where does it come from? Is it always available or sometimes absent?
3. **Quality Definition:** How do you know the output is good? What specific attributes distinguish excellent output from mediocre output for this task? Push beyond "high quality" — name the dimensions.
4. **Failure Modes:** What are the most likely ways this framework's output could go wrong? What mistakes have you seen AI make on this type of task before?
5. **Pipeline Position:** Is this framework standalone or part of a multi-step pipeline? IF part of a pipeline: What step does it receive input from? What step consumes its output? What is the minimum information the next step needs from this step's output?
6. **Execution Environment:** Will this framework be used in single-pass commercial AI, agent mode in a local swarm, reasoning-model execution, or multiple environments? IF multiple, THEN identify any processing steps that specifically benefit from tool access, multi-stage execution, or simplified reasoning-model instructions.
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
    - IF the task requires more than eight layers, THEN recommend agent-mode execution with stage boundaries, and identify where human review gates should be inserted.
    - IF the task requires more than twelve layers, THEN evaluate whether it should be decomposed into a multi-framework pipeline with an orchestration layer.

    Present the complexity assessment to the user with reasoning and wait for confirmation.

### Phase 2: Evaluation Criteria Design

From the requirements gathered in Phase 1, the AI drafts the evaluation criteria. This happens before processing layer design because the criteria define what the processing must achieve.

**Process:**

1. Extract quality dimensions from the user's answers to Question 3 (Quality Definition).
2. Extract anti-failure dimensions from the user's answers to Question 4 (Failure Modes) — each failure mode implies a quality dimension that prevents it.
3. Extract integration dimensions from the user's answers to Question 5 (Pipeline Position) — output must satisfy downstream requirements.
4. Combine, deduplicate, and organize into a numbered list of evaluation criteria. Limit to 7–12 criteria.
5. For each criterion, draft the five-level rubric per the convention in Section 3.6.
6. Present the draft criteria to the user for review and revision.

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

5. **Insert standard layers.** Every framework includes:
   - A Self-Evaluation layer (penultimate position).
   - An Error Correction and Output Formatting layer (final position).

6. **Insert invariant checks.** At the end of every processing layer (except the final two), insert the lightweight invariant verification per Section 2.6.
7. **Insert anti-drift anchors.** IF the framework has more than seven processing layers, THEN insert an orientation anchor at the midpoint per Section 3.7.
8. **Identify stage boundaries for agent mode.** Determine which layer boundaries should become actual execution breaks in agent mode. Criteria for stage boundaries:
   - The output of the preceding layers constitutes a complete intermediate product.
   - The next layers require a materially different analytical mode.
   - Tool access is required at the boundary (file read/write, RAG query).
   - Context window pressure is a risk if layers are combined.

9. **Draft Named Failure Modes.** For each layer, identify the most likely failure mode specific to that layer's processing task. For the framework as a whole, identify cross-cutting failure modes.
10. **Draft Recovery Protocol.** For each identified failure point: what happens when the failure occurs? Specify retry conditions, halt conditions, and what information the user needs to resolve the failure.
11. **Present the architecture to the user.** Show the layer structure, handoff specifications, stage boundaries, failure modes, and recovery protocol for review before proceeding to full draft.

### Phase 4: Specification Drafting

The AI produces the full canonical specification following the Framework Anatomy in Section II.

**Process:**

1. Draft the Header Block (Purpose, Input Contract, Output Contract).
2. Draft the Milestones Delivered section. For each milestone type elicited in Phase 1 Question 1, produce an entry with Endpoint produced, Verification criterion, Preconditions, Mode required (if applicable), and Framework Registry summary. Verify each Verification criterion is objectively determinable per the Resolution Statement Objectivity Protocol — no ambiguous quality terms without objective evaluation criteria.
3. Draft the Evaluation Criteria (from Phase 2, refined by architecture decisions in Phase 3). Use five-level rubrics with concrete per-level descriptions.
4. Draft the Persona (if applicable, based on Question 7 from Phase 1).
5. Draft each Processing Layer with full instructions following the Authoring Standards in Section III. Apply the Think-Then-Format standard to every layer. Insert invariant checks at layer boundaries.
6. Draft the Self-Evaluation Layer keyed to the specific evaluation criteria, including correction trigger phrases and calibration warning.
7. Draft the Error Correction and Output Formatting Layer, including variable fidelity verification and Recovery Declaration.
8. Draft the Named Failure Modes section.
9. Append the Execution Commands block.

### Phase 5: Rendering

From the canonical specification, the AI renders the requested execution variants:

- IF single-pass is requested, THEN follow the Single-Pass Rendering Protocol (Section 5.1).
- IF agent mode is requested, THEN follow the Agent-Mode Rendering Protocol (Section 5.2).
- IF reasoning-model is requested, THEN follow the Reasoning-Model Rendering Protocol (Section 5.3).
- IF multiple variants are requested, THEN render single-pass first, then agent mode, then reasoning-model (see Section 5.4 for rationale).

### Phase 6: Verification

The AI applies the Quality Verification Checklist from Section VII to the finished framework(s) and reports any deficiencies.

---

## Section V: Rendering Protocol — Generating Execution Variants

### 5.1 Single-Pass Rendering Protocol

The single-pass rendering takes a canonical specification and produces a framework optimized for execution in a single commercial AI context window with no tool access.

**Rendering steps:**

1. **Copy the specification structure intact.** The Framework Anatomy sections remain in the same order.
2. **Remove all agent-tier metadata.** Delete: Stage Boundaries, Persistent Reference Document, Tool Definitions, Checkpoint Protocol, and Python Runner Specification.
3. **Set execution_tier to `single-pass`** in YAML frontmatter.
4. **Adjust the Execution Tier section** of the Header Block:
   ```
   ## EXECUTION TIER
   Single-pass: All layers execute sequentially in one context window.
   No external tool access is available. All processing is internal.
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

### 5.2 Agent-Mode Rendering Protocol

The agent-mode rendering takes a canonical specification and produces a mode file optimized for execution in a multi-stage pipeline with tool access and Python orchestration.

**Rendering steps:**

1. **Copy the specification structure intact.**
2. **Set execution_tier to `agent`** in YAML frontmatter.
3. **Map layers to execution stages.** Using the stage boundaries identified in Phase 3 of the design process, group layers into stages. Each stage becomes one inference call in the pipeline.
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
9. **Add adversarial review integration points.** Identify which stages produce outputs that should be cross-evaluated by the opposing model in the swarm. For each such point:
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
6. **Retain anti-drift anchors and invariant checks.** Even reasoning models benefit from explicit scope reminders.

### 5.4 Rendering Order

When multiple variants are requested, render in this order: single-pass first, then agent mode, then reasoning-model. This order is correct because:

- The single-pass version validates that the intellectual content is complete and self-contained.
- The agent-mode version adds execution machinery on top of validated content.
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

6. **Assess complexity.** Apply the complexity assessment from Phase 1, Question 10 of the Framework Design Process. IF the framework exceeds 12 layers, THEN recommend either agent-mode execution or decomposition into a multi-framework pipeline.
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

2. **Preserve all intellectual content.** Conversion modernizes structure and language. It does not add, remove, or alter the framework's substantive instructions unless a deficiency is identified, in which case the AI flags it for user review rather than silently correcting it.
3. **Consolidate split frameworks** (if applicable and if the user confirms consolidation):
   - Absorb initiation questioning into Layer 1 progressive questioning protocol.
   - Absorb evaluation criteria into the Evaluation Criteria section.
   - Absorb evaluation processing into the Self-Evaluation layer.
   - Verify that the consolidated framework does not exceed context window viability for single-pass use.

4. **Render execution variants** per Section V if requested.

### 6.3 Verification Phase

1. **Cross-check intellectual content.** Verify that every instruction, criterion, and processing step from the original framework exists in the converted version. Document and justify any omissions.
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

### Milestones Delivered Compliance

*These items apply only to frameworks that declare Milestones Delivered. Pipeline-stage and fixed-sequence frameworks exempt per Section II subsection 2.3 are not subject to this category; their exemption declaration in Execution Tier is checked under Structural Completeness.*

- [ ] Milestones Delivered section is positioned between the Framework Header Block and the Evaluation Criteria.
- [ ] At least one milestone type is declared.
- [ ] Every milestone type has: Endpoint produced, Verification criterion, Preconditions, Framework Registry summary. Mode required is declared if the framework has multiple modes producing different milestone types.
- [ ] Each Verification criterion is objectively evaluable — no ambiguous quality terms without objective evaluation criteria.
- [ ] Each Framework Registry summary is a single line suitable for semantic indexing.
- [ ] Each Endpoint produced is a concrete artifact or state change, not an abstract outcome.

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

### Agent-Mode Compliance (Agent Renderings Only)

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

- [ ] Single-pass rendering is self-contained and executable without tool access.
- [ ] Agent-mode rendering degrades to single-pass if executed in a commercial AI context.
- [ ] Reasoning-model rendering produces usable output if executed by a non-reasoning model (may not be optimal, but must not break).
- [ ] No rendering requires a specific model or provider to function.

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

**The Implicit Handoff Trap:** Assuming the model will naturally carry information between layers without explicit specification. In single-pass mode, this sometimes works because everything is in one context window. In agent mode, it fails completely because context resets at stage boundaries. Even in single-pass mode, implicit handoffs cause drift over long frameworks. Correction: Every layer boundary has an explicit handoff. What carries forward is named. What is discarded is stated.

**The Persona Inflation Trap:** Creating an elaborate persona with extensive backstory that consumes context without improving output. The persona is a focusing tool, not a character. Correction: Limit persona to name, one-sentence description, and three to five specific capabilities directly relevant to the task. Every persona detail must be task-relevant; irrelevant details produce measurable performance degradation.

**The Criterion Proliferation Trap:** Defining more than twelve evaluation criteria, creating an evaluation burden that the Self-Evaluation layer cannot execute thoroughly in its context allocation. Evaluation quality degrades as criterion count rises — each criterion receives less attention. Correction: Limit criteria to 7–12. IF more dimensions need tracking, THEN consolidate related dimensions into composite criteria.

**The Specification-as-Prose Trap:** Writing framework instructions as flowing prose paragraphs rather than structured directives. Prose is ambiguous. Directives are not. Correction: Apply the Authoring Standards from Section III. Convert every paragraph of instruction into enumerated steps, IF/THEN conditionals, or explicit directives.

**The Tool Assumption Trap (Agent Mode):** Designing processing steps that require tool access without defining the tool, its trigger conditions, or its failure handling. The model will either skip the step or confabulate the tool's output. Correction: Every tool reference must point to a formal Tool Definition. Every tool call must have a defined failure path.

**The Monolithic Stage Trap (Agent Mode):** Mapping the entire framework to a single execution stage, losing all benefits of multi-stage execution (context window management, checkpoint recovery, adversarial review integration). Correction: Identify natural break points using the criteria from Phase 3, Step 8 of the Framework Design Process.

**The False Atomization Trap:** Splitting a framework into excessive micro-layers that create overhead without analytical benefit. Not every instruction needs its own layer. Correction: Apply the single-focus test. IF two instruction groups share a focus and operate on the same information, THEN they belong in the same layer.

**The Missing Context Trap (Pipeline Frameworks):** Designing a framework as if it operates in isolation when it is actually part of a multi-step pipeline. The framework's Input Contract does not account for what the previous step actually produces, or its Output Contract does not provide what the next step actually needs. Correction: Verify input and output contracts against adjacent pipeline steps during design. IF adjacent steps do not yet exist, THEN specify what this framework requires and produces and flag the dependency.

**The Retroactive Evaluation Trap:** Designing processing layers first and then writing evaluation criteria to match what the layers produce. This reverses the correct design sequence (criteria first, then layers to satisfy criteria) and produces criteria that rubber-stamp whatever the processing happens to generate. Correction: Design evaluation criteria before processing layers. See Governing Principle 5.

**The Silent Variable Collapse Trap:** Variables defined early in processing — character names, numerical quantities, specific entities, scope parameters — are silently dropped, conflated with similar variables, or simplified as processing depth increases. The model does not flag the loss because it does not recognize it as an error. Correction: Include variable inventory requirements at layer boundaries. At any layer that establishes or transforms named variables, include an explicit variable state summary.

**The Simulated Refinement Trap:** In self-evaluation or multi-pass contexts, the model introduces artificial errors into its own output just to demonstrate correction, rather than performing genuine critique. Research documents this as a specific failure mode of stepwise prompting (Sun et al., ACL 2024). Correction: Structure self-evaluation as criterion-by-criterion scoring against concrete rubrics with cited evidence, not open-ended "find and fix problems."

**The Premature Accommodation Trap:** During input elicitation or clarification, the AI abandons important questioning steps when the user signals impatience, sacrificing specification quality for conversational comfort. Research found AI interviewers ended structured interviews prematurely when users expressed time constraints, missing critical requirements. Correction: Framework elicitation sequences must complete mandatory items even when the user signals impatience. The AI may acknowledge the user's time constraint but must flag that skipped items may affect output quality.

**The Format-Before-Reasoning Trap:** Embedding output format requirements within processing instructions, causing the model to prioritize syntactic compliance over analytical quality. Research shows format restrictions cause significant reasoning degradation (Tam et al., EMNLP 2024). Correction: Apply the Think-Then-Format standard from Section 3.9. Processing instructions precede formatting instructions within every layer.

**The Over-Specification Trap:** Specifying requirements the model already satisfies by default, consuming context budget on instructions that add no value while potentially overwhelming the model with competing requirements. Research found that adding more requirements does not reliably improve performance and that LLMs can guess unspecified requirements 41.1% of the time (Yang et al., CMU 2025). Correction: Specify what the model will not get right by default. Leave implicit what it handles well natively. Test against real inputs to identify which specifications are actually needed.

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

Agent-Tier Metadata:
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

PFF is one of three sibling meta-frameworks. The Corpus Formalization Framework (CFF) formalizes the knowledge corpus where information accumulates across a workflow. The Output Formalization Framework (OFF) formalizes the rendered artifacts that express corpus content. The full three-framework integration is specified in `Framework — PFF-CFF-OFF Integration Architecture.md`. This section provides PFF's perspective on that architecture.

### Detection trigger built into PFF design

When a user invokes PFF (mode F-Design), the design process includes the question:

> *Does this process feed a workflow with multiple sources or multiple outputs?*

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

Full architecture: `Framework — PFF-CFF-OFF Integration Architecture.md`. Sibling specifications: `Framework — Corpus Formalization.md` and `Framework — Output Formalization.md`.

---

## Section XI: Execution Commands

---

## EXECUTION COMMANDS

1. Confirm you have fully processed this meta-framework and any associated input materials.
2. Identify the operating mode from the user's input:
   - **Mode F-Design:** User describes a new framework to create. Follow the Framework Design Process (Section IV).
   - **Mode F-Convert:** User provides an existing framework. Follow the Conversion Protocol (Section VI).
   - **Mode F-Render:** User provides a canonical specification. Follow the Rendering Protocol (Section V).
   - **Mode F-Audit:** User provides a framework for evaluation. Apply the Quality Verification Checklist (Section VII).
3. IF the mode is ambiguous, THEN ask the user to confirm before proceeding.
4. Execute the appropriate process. Produce all outputs specified for that mode.
5. Apply the Quality Verification Checklist to all outputs before delivery.
6. Produce a Framework Registry Entry for every framework specification produced. The entry follows this format:

   FRAMEWORK REGISTRY ENTRY
   Name: [framework name from the specification's title]
   Purpose: [one sentence from the specification's PURPOSE section]
   Problem Class: [what category of problem this framework solves — inferred from the specification's purpose and input contract]
   Input Summary: [condensed from the specification's INPUT CONTRACT — required inputs only, one line each]
   Output Summary: [condensed from the specification's OUTPUT CONTRACT — primary outputs only, one line each]
   Proven Applications: [list any test cases run during this session; if none, state "None yet — initial version"]
   Known Limitations: [inferred from the specification's Named Failure Modes — one sentence summarizing the most significant risk]
   File Location: [the path where the specification file will be saved]
   Provenance: [human-created | agent-created]
   Confidence: [low — initial version | medium — tested against 3+ diverse inputs | high — tested against 10+ diverse inputs with consistent results]
   Version: [from the specification's YAML frontmatter framework_version]

   Present the registry entry alongside the framework specification. Instruct the user (or agent) to save the entry to the framework registry file and index it in ChromaDB's knowledge collection.

7. Present outputs with a summary of decisions made, gaps identified, and recommendations for refinement.

---

## USER INPUT

[State Mode F-Design (new framework), Mode F-Convert (modernize existing), Mode F-Render (generate execution variants from specification), or Mode F-Audit (evaluate against standards) — or let the AI auto-detect from your input. Then provide your input materials.]

---

**END OF FRAMEWORK CREATION FRAMEWORK v2.0**
