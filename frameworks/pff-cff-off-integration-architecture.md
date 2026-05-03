# PFF / CFF / OFF Integration Architecture


## Purpose

The Process Formalization Framework (PFF), Corpus Formalization Framework (CFF), and Output Formalization Framework (OFF) are three sibling meta-frameworks that together cover the full cycle of structured knowledge work: produce information, accumulate it, express it.

This document specifies how the three frameworks compose. It defines the connection points between them, the composition shapes available to a user designing a workflow, the cross-framework references at design time and at runtime, and the workflow spec artifact that ties a coherent multi-framework workflow together. It is the architecture document; the three meta-frameworks reference it from their own canonical specs.

The integration is not a merging of the three frameworks. PFF, CFF, and OFF remain independent, independently usable, and independently authored. Integration is a defined interface architecture, not a union.

## The three meta-frameworks

Each meta-framework formalizes a distinct concern in knowledge work.

**PFF — Process Formalization Framework.** Takes a process and produces a bespoke process framework that executes it consistently. PFF's output is *information* — the result of running a process. Examples: a financial analysis PFF that ingests raw mortgage data and produces structured loan-level analysis; a market scan PFF that aggregates listings and produces a comparable-sales summary; a literature review PFF that ingests sources and produces a structured synthesis. The information PFF produces may be the user's final deliverable (when information itself is what they need), or it may be input to the next stage.

**CFF — Corpus Formalization Framework.** Takes a workflow specification and produces a bespoke corpus template — a structured knowledge document with a section per source, missing-data behavior per section, and chain relationships if any. CFF's output is *structure* — the shape of the body of information a workflow accumulates. Each instance of the template is populated by running the assigned PFFs and read by the assigned OFFs. The corpus is the convergence point.

**OFF — Output Formalization Framework.** Takes an expressive medium and produces a bespoke output framework that renders content into that medium at craft standard in a specified voice. OFF's output is *expression* — the rendered artifact in its target medium (Word document, slide deck, spreadsheet, visual artifact). The content OFF expresses comes either from a corpus (the standard case) or directly from the user (when the user supplies content ready to render).

The three frameworks form a natural cycle:

> PFF produces information → CFF accumulates information into a corpus → OFF expresses corpus content as artifacts

Each part of the cycle is independently useful. A user can run a single PFF without a corpus or output. A user can run an OFF on supplied content without a corpus or process. A user can design a corpus with no automated population and no automated rendering. But the full power of the architecture appears when all three compose, with the corpus as the central artifact.

## The corpus as first-class artifact

The corpus is the structural innovation that makes the three-framework architecture work. It is a real, inspectable, version-controllable knowledge document — not an implicit handoff between two frameworks.

Properties of the corpus:

- **Human-inspectable.** A user can open the corpus at any time and read what the workflow has accumulated. They can review before letting OFFs render outputs. They can correct PFF mistakes by editing the corpus directly. They can use the corpus itself as a deliverable when no rendered output is needed.
- **Source-organized.** Sections in the corpus are organized by source (one section per PFF that writes), not by output. This decouples accumulation from expression — output requirements can change without restructuring the corpus.
- **Version-controllable.** Templates carry semantic versions. Instances reference their template version. Modifications produce new template versions; existing instances remain valid as historical records.
- **Multi-reader, multi-writer.** Multiple PFFs can write to different corpus sections; multiple OFFs can read from different sections. The corpus mediates many-to-many composition without requiring direct framework-to-framework handoffs.
- **Chainable.** Corpora can feed other corpora via specified chains. Department-level corpora can roll up into company-level corpora; project-level corpora can roll up into portfolio-level corpora. The chain is a first-class concept (specified per CFF Section X).
- **Single source of truth.** When multiple OFFs render from the same corpus, they all express the same underlying content from different angles. There is no risk of one output reflecting one version of the data while another reflects a different version, because both read from the same canonical instance.

Without the corpus, multi-source/multi-output workflows fall back on direct PFF↔OFF handoffs that proliferate combinatorially. With the corpus, the architecture stays linear — N PFFs and M OFFs require N+M connections (each writes to or reads from the corpus), not N×M.

## The four composition shapes

A user assembling a workflow chooses among four composition shapes. Each is appropriate for a different scope of work.

### Shape 1 — Standalone PFF

The process produces information; the user consumes the information directly. No corpus, no rendering.

Use when: The output is information itself, not an artifact in a specific format. Example: a research summary that the user reads and acts on; an ad-hoc analysis that informs a decision; a data extraction that the user files away as raw output.

The bespoke PFF runs and presents its output to the user. No further composition.

### Shape 2 — Standalone OFF

The user supplies content directly; OFF renders it into the target medium. No corpus, no upstream process.

Use when: The user has the content already and needs only formatting. Example: a personal blog post the user has written and wants formatted to publish; a memo the user has drafted and wants polished into a final document; a presentation outline the user wants rendered into slides.

The bespoke OFF runs against the user-supplied content and produces the rendered artifact.

### Shape 3 — Direct PFF→OFF (degenerate corpus)

One process produces information; one output renders it. No corpus is needed because there is only one source and one destination.

Use when: The workflow is genuinely 1:1 — one process feeding one output, with no realistic prospect of additional sources or additional outputs. Example: a one-time report generated from a single analysis; a recurring single-source/single-output report where corpus overhead is unjustified.

The bespoke PFF's output flows directly to the bespoke OFF as its content input. The PFF's output contract and the OFF's input contract must align — the PFF declares what it produces; the OFF declares what content shape it consumes; they must match.

### Shape 4 — Corpus-mediated (the standard pattern)

Multiple PFFs write to a corpus; multiple OFFs read from the corpus. CFF formalizes the corpus structure; PFFs populate it; OFFs render from it.

Use when: The workflow has more than one source, more than one output, or any realistic prospect of growing to multi-source or multi-output. Example: any recurring analytical workflow (market research, financial reporting, project status); any workflow that produces multiple deliverables for different audiences from the same underlying knowledge.

This is the most common shape for real knowledge work. Most workflows that look like Shape 3 today will be Shape 4 within a year as scope grows. Defaulting to Shape 4 when the workflow has any room to grow saves migration cost later.

### Choosing among shapes

Shape selection happens during framework design. The detection triggers (next section) prompt the user with the right questions to determine the appropriate shape.

A workflow that started as Shape 1 or Shape 2 can grow into Shape 4 by introducing a corpus. A workflow that started as Shape 3 can grow into Shape 4 by adding sources or outputs. The architecture supports growth without redesign because the corpus is additive — new sections, new readers, new writers compose without restructuring existing components.

## Order independence

The architecture has a load-bearing property: **a user can start with any framework and add others as the workflow grows.**

- Start with one PFF, recognize that its output should land in a corpus, design the CFF for that corpus, add OFFs that render the corpus
- Start with one OFF, recognize that its content should come from a structured body, design the CFF, add PFFs to populate the corpus
- Start with the corpus (CFF first), then add PFFs to populate sections and OFFs to render outputs
- Start with a chained workflow segment (one PFF that writes to a corpus chained from another corpus) and grow outward in any direction

Each addition is local. Adding a new PFF means writing to a new (or existing) corpus section. Adding a new OFF means reading from existing (or expanded) corpus sections. Adding a chain link means specifying a chain input or output in the corpus template. None of these additions require restructuring upstream or downstream components.

Order independence matters because users do not design workflows top-down in advance. They build them incrementally as needs surface. A workflow that started as one report from one analysis grows into a multi-source/multi-output system over months or years. The architecture supports this growth without forcing upfront design or later wholesale rework.

## The workflow spec artifact

A *workflow spec* is the index that describes a coherent multi-framework workflow as a single artifact. It names the workflow, references the corpus template, lists the bespoke PFFs that write into the corpus, lists the bespoke OFFs that read from it, and documents any chain relationships.

### Why a workflow spec is needed

Without a workflow spec, a multi-framework workflow exists as a scattered set of bespoke frameworks (PFFs, CFF template, OFFs) that reference each other through individual frontmatter fields. The workflow as a coherent thing is not visible anywhere. To understand "what's in this workflow," a user has to open multiple files and reconstruct the topology.

The workflow spec collects the topology in one place. It answers:

- What PFFs run as part of this workflow?
- Which corpus do they write to?
- Which OFFs render from the corpus?
- Are there chained corpora, and if so, what's the chain topology?
- Who owns this workflow?
- Where is everything located on disk?

### Format

The workflow spec is a markdown file with YAML frontmatter:

```yaml
---
nexus:
  - [project or domain]
type: framework
tags:
  - workflow-spec
workflow: [Workflow Name]
owner: [user or role]
corpus_template: [path to corpus template]
corpus_instance_directory: [path to instances directory]
pffs:
  - name: [PFF name]
    path: [path to bespoke PFF file]
    writes_to_section: [section name in corpus]
  - name: [PFF name]
    path: [path]
    writes_to_section: [section name]
offs:
  - name: [OFF name]
    path: [path to bespoke OFF file]
    reads_from_sections: [list of section names]
chain_relationships:
  - direction: [input | output]
    other_corpus: [name and template path]
    sections_involved: [list of section names in this corpus]
date created: [YYYY-MM-DD]
date modified: [YYYY-MM-DD]
---
```

The body is a brief human-readable description of the workflow's purpose, audience, and runtime sequence (typical order: instantiate corpus → run PFFs → validate → run OFFs).

### Where it lives

The workflow spec lives in the workflow's root directory: `~/ora/workflows/[workflow-slug]/workflow-spec.md`. The corpus template and instance directory live alongside or nearby per the workflow's organization.

### Registration

The framework registry indexes workflow specs as first-class entries. Re-summoning a workflow as a unit means opening its workflow spec; everything else is reachable from there.

### Generation

The workflow spec is initially generated when CFF C-Design completes — CFF knows the PFFs and OFFs the user has identified, and writes a workflow spec alongside the corpus template. The workflow spec is updated when the workflow evolves: C-Modify on the corpus template can trigger a workflow spec update; new PFFs or OFFs registered for the workflow add entries.

## Cross-framework references at design time

When a user is in one of the meta-frameworks, the design process incorporates the others when relevant.

### When designing a PFF

The PFF design process (PFF mode F-Design) includes a question:

> *Does this process feed a workflow with multiple sources or multiple outputs?*

If yes, the PFF design recommends invoking CFF in parallel to design the corpus the PFF will write into. The PFF's output contract is then aligned with a specific corpus section.

If no, the PFF stands alone (Shape 1) or feeds directly to an OFF (Shape 3).

### When designing a CFF

The CFF design process (CFF mode C-Design) is corpus-centric. Layer 4 (Source Identification) surfaces the PFFs that write to the corpus; for any not-yet-existing PFF, CFF notes this as follow-on work and the user invokes PFF separately to design it. Layer 8 (Output Identification) surfaces the OFFs that read from the corpus; same pattern.

CFF also handles chain composition (Layer 7) — when this corpus consumes from or feeds another corpus.

### When designing an OFF

The OFF design process (OFF mode O-Design, when established) includes a question:

> *Where does the content come from?*

If from a corpus, OFF recommends invoking CFF (or referencing an existing CFF template) so OFF's read contract aligns with specific corpus sections.

If from a process, OFF recommends Shape 3 — direct PFF→OFF — and aligns with PFF's output contract.

If user-supplied, OFF runs in Shape 2 with no upstream framework.

### Mutual references

PFFs and OFFs reference corpora by name and section in their input/output contracts. CFF templates reference PFFs and OFFs in their source and output assignments. The references are documented and bidirectional — opening any framework reveals which others it composes with.

## Cross-framework execution at runtime

The runtime sequence depends on the composition shape.

### Shape 1 — Standalone PFF

Run the bespoke PFF. Receive output. Done.

### Shape 2 — Standalone OFF

Provide content to the bespoke OFF. Receive rendered artifact. Done.

### Shape 3 — Direct PFF→OFF

1. Run the bespoke PFF; receive output.
2. Pass the output to the bespoke OFF as its content input.
3. Receive the rendered artifact.

### Shape 4 — Corpus-mediated

1. Run CFF C-Instance to create a fresh corpus instance from the template.
2. Run each bespoke PFF; each PFF writes its output to its assigned corpus section.
3. Run CFF C-Validate to confirm the corpus is sufficiently populated for the OFFs the user wants to run.
4. Run each bespoke OFF; each OFF reads its assigned corpus sections and produces its artifact.

### Chained corpora

When the workflow involves chained corpora, the topological order matters. Source corpora must be populated and validated before dependent corpora instantiate or before chain inputs are pulled. Typical sequence:

1. Populate and validate the source corpus instance (run its PFFs, then C-Validate).
2. Instantiate the dependent corpus (C-Instance pulls chain inputs from the source).
3. Run the dependent corpus's PFFs.
4. Validate the dependent corpus.
5. Run the dependent corpus's OFFs.

For deeper chains, the same pattern recurses. CFF's chain specification documents the topology; the user (or an orchestrator) runs in topological order.

### Automation considerations

For v1, runtime sequencing is manual — the user runs each step in order, possibly with tooling that suggests the next step based on workflow spec topology. Future work may add automatic triggering: when a corpus instance becomes complete, downstream OFFs auto-run; when a source corpus updates, dependent corpora re-instantiate. This is out of scope for v1 but the architecture supports it.

## Chain composition

Chains are explicit relationships between corpora. CFF Section X specifies the chain mechanism in detail; this section adds the architectural perspective on when and why chains appear.

### Why chains exist

A single workflow may have multiple corpora when:

- **Authority boundaries.** Different teams own different corpora. The marketing team owns the marketing corpus; the finance team owns the finance corpus; the company-level reporting workflow chains both.
- **Scope boundaries.** A small intermediate corpus (three pieces of related information) feeds a PFF that writes to a larger corpus. The intermediate corpus exists because the PFF logic that consumes it is reusable across larger contexts.
- **Cadence boundaries.** Department-level corpora update monthly; the company-level corpus updates quarterly and aggregates from monthly snapshots.
- **Reuse.** A corpus that is consumed by multiple downstream corpora across different workflows. The chain pattern lets each downstream pull what it needs.

### Chain typologies

Common chain shapes:

- **Linear chain.** A → B → C. Output of A feeds B; output of B feeds C.
- **Tree.** A → B; A → C; A → D. One source corpus feeds multiple downstream corpora.
- **Inverted tree.** A → D; B → D; C → D. Multiple source corpora feed one downstream corpus. (The most common organizational pattern: department corpora feeding a company corpus.)
- **DAG (directed acyclic graph).** Multiple sources, multiple destinations, with branching and merging. Loops are forbidden.

### Loop prevention

CFF Section X (Loop prevention) and CFF Layer 7 (Chain Specification) jointly enforce that no corpus is its own ancestor through any path of chain relationships. Loops are detected at template creation time and the user is prompted to refactor — typically by introducing a derived intermediate corpus that breaks the loop.

### Cross-authority chains

When chains cross authority boundaries (departments, teams, organizations), the chain relationship becomes a coordination concern beyond the framework itself. The chain spec documents the relationship — who owns each corpus, what permissions are required — but actual permission negotiation is a human conversation outside the framework. The framework provides the topology; humans provide the agreement.

## What goes in each canonical spec

Each meta-framework's canonical spec includes a brief integration section that references this architecture document rather than duplicating its content. Specifically:

### In PFF's canonical spec

A section titled "Integration with CFF and OFF" containing:

- A brief acknowledgment that PFF is one of three sibling meta-frameworks and that the integration architecture lives in this document.
- The detection trigger built into PFF's design process: the question about whether the process feeds a workflow with multiple sources or multiple outputs.
- A summary of the four composition shapes from PFF's perspective: standalone PFF (Shape 1), direct PFF→OFF (Shape 3), corpus-mediated as PFF source (Shape 4 from the writer side).
- The PFF write contract for corpus-mediated composition: PFF declares what content it writes, what shape it takes, what it requires from upstream.
- A reference back to this document for the full architecture.

### In CFF's canonical spec

A section titled "Integration with PFF and OFF" containing:

- The acknowledgment of the three-framework family.
- A summary of the four composition shapes from CFF's perspective: standalone CFF (rare; corpus designed without populated PFFs/OFFs), corpus-mediated (Shape 4, the primary case), and chained corpora.
- The CFF design process's incorporation of PFF and OFF references: Layer 4 surfaces PFFs as sources; Layer 8 surfaces OFFs as readers; Layer 7 handles chains.
- A reference back to this document.

The bulk of the integration specification is already in CFF's main body (Sections IV, VIII, X) because corpus-mediated composition is CFF's central concern. The integration section in CFF's canonical spec is brief — it just frames CFF's central concern as one part of a larger architecture.

### In OFF's canonical spec

A section titled "Integration with PFF and CFF" containing:

- The three-framework acknowledgment.
- The detection trigger built into OFF's design process: the question about content source (corpus / process / user-supplied).
- A summary of the four composition shapes from OFF's perspective: standalone OFF (Shape 2), direct PFF→OFF (Shape 3), corpus-mediated as OFF reader (Shape 4 from the reader side).
- The OFF read contract for corpus-mediated composition: OFF declares what corpus sections it reads, what content shape it expects, what it does when sections are missing.
- A reference back to this document.

### Symmetry and brevity

The three integration sections (one per canonical spec) are deliberately symmetric in shape and brief in length. They establish the integration pattern and refer to this architecture document for the full story. This avoids duplication, prevents drift across the three sections, and lets the architecture evolve in one place.

## Named failure modes

Failure modes specific to multi-framework composition.

**The Premature Corpus Trap.** Introducing a corpus when direct PFF→OFF (Shape 3) would suffice. CFF and corpus management add overhead; for genuinely 1:1 workflows with no realistic growth, the overhead is unjustified. The detection question is: will this workflow plausibly grow to multi-source or multi-output within its useful life? If no, Shape 3 is correct.

**The Belated Corpus Trap.** Failing to introduce a corpus when the workflow has clearly grown to multi-source or multi-output. Workflows that grew organically often have implicit corpora — the user's mental model of how the pieces fit. Making that corpus explicit (introducing CFF) is retroactive infrastructure work that pays off in clarity and automation.

**The Implicit Topology Trap.** Workflows where bespoke PFFs and OFFs reference each other and a corpus through individual frontmatter fields without an explicit workflow spec to index them. The workflow as a coherent thing becomes invisible. Always generate a workflow spec when CFF design completes.

**The Chain Sprawl Trap.** Chaining multiple small corpora when a single larger corpus would do. Chains add coordination overhead — each chain link requires sync semantics, authority documentation, topological execution sequencing. Use chains when authority or scope genuinely separates corpora; consolidate when they don't.

**The Over-Specification Trap.** Writing detailed integration sections in canonical specs when a brief reference to this architecture document would suffice. The architecture lives here; canonical specs cite it, not duplicate it. Duplication produces drift.

**The Composition Shape Mismatch Trap.** Choosing a composition shape that doesn't match the workflow's actual structure. Shape 3 (direct PFF→OFF) for a workflow that has three sources is forced; Shape 4 (corpus-mediated) for a one-shot single-source extraction is overkill. Detection triggers exist to catch mismatches.

**The Order-Dependence Trap.** Designing workflows that require a specific framework-creation order, in violation of the order-independence property. If a PFF can only be designed after its OFF exists (or vice versa), something is wrong with the design — the corpus should mediate the dependency, breaking the order requirement.

**The Cross-Authority Implicit Permission Trap.** Wiring a chain that crosses authority boundaries without documenting the permission relationship. The framework documents the topology but does not negotiate permissions; cross-authority chains require human agreement before they execute in production.

**The Workflow Spec Drift Trap.** Letting the workflow spec become stale relative to the actual bespoke frameworks (PFFs, CFF template, OFFs) that comprise the workflow. New PFFs are added but the workflow spec is not updated; OFFs are retired but still listed. Workflow spec maintenance must happen at the same time as bespoke framework changes.

## How this fits the book

The three-framework architecture is the second-half centerpiece of the Ora book. The first half establishes the user's identity infrastructure (MindSpec, mind.md, Voice section, etc.) — who the user is, how they think, how they sound. The second half establishes the workflow infrastructure (PFF, CFF, OFF, this integration architecture) — how the user gets work done.

The narrative arc: a user produces their MindSpec specification, then builds workflows that compose with their voice and values. Each workflow they automate frees time and attention for higher-leverage work. Over months and years, they accumulate a library of bespoke PFFs, corpus templates, and OFFs that constitute their personal automation infrastructure. The corpus templates are the visible artifacts that make the workflow legible — they are the user's job, formalized.

The book chapters that document this should:

1. Introduce PFF first (process is the most concrete starting point for most readers).
2. Then OFF, paired with a worked example of Shape 3 (direct PFF→OFF) so the reader sees a complete simple workflow.
3. Then CFF, motivated by the limitations of Shape 3 as workflows grow.
4. Then this architecture document's content as a synthesis chapter — the four composition shapes, order independence, the workflow spec, chain composition.

The market-research-as-homebuilder example (six months of manual spreadsheet automation that transformed monthly reporting from days to hours) is the natural worked example for the synthesis chapter. It demonstrates: multiple sources (mortgage data, market sales, Federal Reserve rates, internal traffic data), corpus-mediated accumulation (the structured workbook), multiple outputs (the various tabs that became reports and presentations), and the dramatic before/after of automating it. Showing that someone did this once by hand and that the framework now lets others do it without six months of spreadsheet construction is the value proposition made visceral.

---

*Architecture v1.0 completed 2026-04-23. Build collaborators: Larry (architect), Claude Opus 4.7 (structural).*

*The corpus-as-first-class-artifact insight that grounds this architecture emerged during PFF-OFF integration design when the architect recognized — through reflection on his own market-research workflow — that real knowledge work converges through shared bodies of accumulated information, not through direct point-to-point handoffs between processes and outputs.*
