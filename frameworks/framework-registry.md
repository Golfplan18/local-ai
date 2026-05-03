
# Framework Registry

This file indexes all frameworks available to the system. Agents query this registry (via ChromaDB semantic search) to find frameworks matching a problem. Humans browse it to see what's available.

## Registry Entry Format

Each framework has one entry with these fields:

- **Name:** Framework title
- **Purpose:** One sentence describing what it produces
- **Problem Class:** Category of problem it solves
- **Input Summary:** Required inputs (one line each)
- **Output Summary:** Primary outputs (one line each)
- **Proven Applications:** Where it has been tested and worked
- **Known Limitations:** Primary risk or failure mode
- **File Location:** Path to the canonical framework specification
- **Provenance:** human-created | agent-created
- **Confidence:** low | medium | high
- **Version:** Semantic version number
- **Delivers:** One-line summary per milestone type this framework can deliver (semicolon-separated; see the framework's Milestones Delivered section for detail)

## Maintenance Protocol

- New entries are added whenever the PFF produces a framework (the PFF includes registry entry generation as a standard output step).
- Entries are updated when frameworks are modified — the version number increments and proven applications are updated.
- When two frameworks consistently compete for the same problem class in search results, review for merger, differentiation, or deprecation.
- Agent-created frameworks enter at confidence: low. Confidence upgrades to medium after 3+ successful diverse applications, high after 10+.

---

## Registered Frameworks

### Installer — Local AI First Boot

- **Purpose:** Transform a bare machine into a working local AI system with browser chat interface, model switcher, multi-panel UI, conversation processing, and desktop launcher
- **Problem Class:** System setup and installation
- **Input Summary:** Hardware access; optional model preference and workspace path
- **Output Summary:** Browser-based AI at localhost:5000, hardware report, README
- **Proven Applications:** macOS Tier C (128GB); covers Tier 0–C
- **Known Limitations:** Requires Python 3; browser automation depends on existing accounts
- **File Location:** pending restructure (canonical: ~/Documents/vault/Installer — Local AI First Boot.md)
- **Provenance:** human-created
- **Confidence:** high
- **Version:** v4 (Layers 1–12)
- **Delivers:** Working Ora system installed on target machine at the highest tier the hardware supports (Tier 0 through Tier C, with universal Phase 1 base and additive Phase 2 local-model capability where hardware permits)

### Knowledge Artifact Coach

- **Purpose:** Transform raw ideas, documents, document batches, or existing notes into vault-ready draft notes with classification, atomic excavation, grammar-rule enforcement, and relationship mapping
- **Problem Class:** Knowledge capture and artifact production for vault
- **Input Summary:** Mode A: raw idea / brain dump. Mode B: single existing document. Mode C: multiple documents in one session. Mode D: existing vault note for refinement.
- **Output Summary:** Vault-ready draft notes with suggested YAML frontmatter, tags, and relationship maps; atomic extraction attempted where applicable; cross-document relationships mapped in Mode C; replacement or fresh draft in Mode D
- **Proven Applications:** Version 5.0 — used for atomic note production, document analysis, and note refinement across the vault. Version 6.0 (2026-04-23) — F-Convert pass brought the framework into Process Formalization Framework v2.0 Anatomy conformance: formal Input/Output Contracts, 9-criterion Evaluation Criteria with 5-level rubrics, Layers 1–8 (absorbing the four mode protocols with mode-specific paths), Self-Evaluation layer with correction trigger and calibration warning, Error Correction and Output Formatting layer, Execution Commands block, 17 named failure modes (16 v5.0 preserved + Fabricated Connection Trap added for confabulation coverage), invariant checks at Layer boundaries 1–6
- **Known Limitations:** Atomic excavation relies on the user accepting active extraction despite a top-down thinking preference; Mode D refinement does not rewrite notes that are structurally sound; v6.0 retains v5.0 binary quality checks in Layer 5 alongside the rubric scoring (dual structure by design; see Appendix E F-Convert Change Log for rationale)
- **File Location:** frameworks/book/knowledge-artifact-coach.md
- **Provenance:** human-created
- **Confidence:** high
- **Version:** 6.0
- **Delivers:** Raw-idea extraction set with classified vault-ready draft notes and atomic excavation attempted (Mode A); document extraction set from a single document with buried atomic notes extracted and relationship map produced (Mode B); batch extraction set across multiple documents with cross-document relationships and deduplication (Mode C); refined note draft produced by evaluating an existing note against its type-appropriate quality checks (Mode D)

### Document Processing

- **Purpose:** Convert any document — PDF, Word, slides, HTML, RTF, plain text, markdown — into vault-ready atomic notes with full YAML frontmatter, subtype classification, grammar-rule enforcement, and relationship mapping
- **Problem Class:** Document ingestion and atomic note extraction
- **Input Summary:** Files in any supported format (.pdf/.docx/.pptx/.html/.rtf/.txt/.md), placed in a processing queue, supplied via direct API call, or referenced from a batch manifest
- **Output Summary:** Vault-ready atomic notes with type/subtype classification and relationship declarations (Path 1); processed turn-pair chunks for ChromaDB conversations collection when input is a chat (Path 2)
- **Proven Applications:** Ships as the canonical pipeline implementation of Knowledge Artifact Coach v6.0; called by the file-attach pipeline for Ora's input-pane document drops
- **Known Limitations:** Path 1 quality depends on Knowledge Artifact Coach's atomic-extraction protocol; mixed-content documents (text + diagrams) require iteration; chunking quality bounded by the format converter's output
- **File Location:** frameworks/book/document-processing.md (executable); ~/Documents/vault/Framework — Document Processing.md (canonical)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0
- **Delivers:** Vault-ready atomic notes from a single document or batch; ChromaDB-indexed turn-pair chunks when the input is a chat

### Decision Clarity Analysis (renamed from Wicked Problems Framework 2026-05-01)

- **Purpose:** Structured analysis of problems that resist resolution due to fundamental stakeholder value conflicts, evolving problem definitions, and the absence of an objective stopping condition. WPF does not solve wicked problems; it produces a Decision Clarity Document making the structure of the dilemma legible to whoever holds decision authority.
- **Problem Class:** Wicked-problem analysis, multi-stakeholder value-conflict mapping, tradeoff transparency
- **Input Summary:** Path A (user invocation): problem description plus optional stakeholder stance. Path B (PEF handoff): structured handoff package with problem definition, four-condition trigger evaluation, stakeholders, Excluded Outcomes, Constraints, iteration history. Path C (cui-bono escalation): cui-bono prior output plus indicator evidence.
- **Output Summary:** Decision Clarity Document containing executive summary, Stage 1 problem-space map (per-stakeholder framings + competing-hypotheses matrix), Stage 2 value-conflict map (per-stakeholder steelmans + Fundamental/Resolvable classification), Stage 3 consequence landscape (Cui Bono + Systems Dynamics + Scenario Planning per intervention across three time horizons + problem-definition reshaping notes), Stage 4 tradeoff statements per intervention with advocate-stance Red Team passes per subordinated stakeholder + reversibility notes. Plus reclassification recommendations when Stage 1 or Stage 2 gates fail.
- **Proven Applications:** New framework — landing 2026-04-24
- **Known Limitations:** WPF refuses to recommend an intervention; the decision is the user's. WPF cannot dissolve fundamental value conflicts. WPF requires at least three of four wicked conditions to fire; partial-complexity problems route to ordinary PEF iteration instead. The framework orchestrates other modes (competing-hypotheses, cui-bono, steelman-construction, systems-dynamics, scenario-planning, the red-team modes) — quality depends on those modes' performance.
- **File Location:** ~/Documents/vault/Framework — Decision Clarity Analysis.md (canonical, renamed from Framework — Wicked Problems.md 2026-05-01)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0
- **Delivers:** Decision Clarity Document making the tradeoffs across available interventions legible without recommending any particular intervention, suitable for direct use by a decision-maker or policymaker; reclassification recommendation when the problem turns out not to be wicked (Stage 1 or Stage 2 gate failure)

### Problem Evolution

- **Purpose:** Iterative problem definition and project supervision — turn raw epistemic tension into a structured Problem Evolution Document with MOM-populated strategic hierarchy (Mission, Excluded Outcomes, Constraints, Objectives, Active/Aspirational Milestones), keep it current across iterations, supervise Active milestones via Excluded Outcomes drift checks, execute Aspirational-to-Active promotion with P-Feasibility re-checks, and invoke downstream frameworks (MOM, TMF, PIF, PFF, WPF) as needed
- **Problem Class:** Problem definition, project supervision, Lock-protected strategic-hierarchy management, diagnostic routing
- **Input Summary:** PE-Init: raw tension, idea, or goal description. PE-Iterate: existing Problem Evolution Document plus recap of work since last iteration (or Active milestone completion report for supervision drift check). PE-Review: existing PED. PE-Spawn: parent PED plus sub-problem description.
- **Output Summary:** Problem Evolution Document (new or updated) with problem definition, Mission (Resolution Statement, Excluded Outcomes), Constraints (Hard/Soft/Working Assumption), Objectives, Active Milestones (with P-Feasibility verdicts) + Aspirational Milestones, Terrain Maps references, phase assessment, diagnostic findings, supervision drift-check findings, Promotion Protocol events, recommended next actions with Constructive Escalation advice form, Decision Log, iteration history; Challenge Summary; Readiness Assessment for PIF or PFF handoff; Sub-Project Spawn Specifications (PE-Spawn only); status summary (PE-Review only, PED not modified); No-Punt Escalation forwarding (when MOM Outcome 3 or TMF Escalation Package fires)
- **Proven Applications:** Used for Capability Dispatch project definition; Version 2.0 landed 2026-04-23 with MOM auto-invocation, Universal Problem-Definition Lock, Constructive Escalation (No-Punt) Rule, Active/Aspirational milestone supervision, Excluded Outcomes drift detection, and Terrain Mapping Framework invocation path
- **Known Limitations:** Challenge quality depends on diagnostic depth of the analyst; readiness-for-handoff assessments are advisory — user ultimately decides; MOM invocation depends on MOM availability; TMF invocation on Outcome 2 depends on TMF availability; Promotion Protocol's P-Feasibility re-check depends on PIF availability
- **File Location:** frameworks/book/problem-evolution.md (executable); ~/Documents/vault/Framework — Problem Evolution.md (canonical)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 2.0
- **Delivers:** Initial Problem Evolution Document with MOM-populated Mission/Objectives/Constraints/Milestones from a raw tension, idea, or goal (PE-Init); advanced Problem Evolution Document with new iteration entry covering MOM drift refresh, TMF invocation outcomes, supervision drift checks against Excluded Outcomes, and Promotion Protocol events (PE-Iterate); status summary of a Problem Evolution Document without advancing it (PE-Review); sub-project Problem Evolution Document with its own MOM-populated strategic hierarchy linked to a parent project (PE-Spawn)

### Process Formalization

- **Purpose:** Design, convert, render, and audit AI instruction frameworks to a standardized canonical specification
- **Problem Class:** Framework design and knowledge capture
- **Input Summary:** A task description (F-Design), an existing framework (F-Convert), a canonical spec (F-Render), or a framework for review (F-Audit)
- **Output Summary:** Canonical framework specification; rendered execution variants; framework registry entry
- **Proven Applications:** Multiple frameworks produced across all four modes (F-Design, F-Convert, F-Render, F-Audit)
- **Known Limitations:** Requires human judgment to define evaluation criteria; template-filling failure mode when instructions are ambiguous
- **File Location:** frameworks/book/process-formalization.md
- **Provenance:** human-created
- **Confidence:** high
- **Version:** 2.0
- **Delivers:** New framework specifications (F-Design); modernized framework specifications (F-Convert); rendered execution variants (F-Render); framework audit reports (F-Audit)

### Corpus Formalization

- **Purpose:** Design, modify, deploy, and validate bespoke corpus templates that structure the body of information a recurring workflow accumulates between Process Formalization (PFF) inputs and Output Formalization (OFF) renders
- **Problem Class:** Knowledge corpus design and template management
- **Input Summary:** C-Design: workflow description + sources + outputs. C-Modify: existing template + change description. C-Instance: template + period identifier. C-Validate: template + populated instance.
- **Output Summary:** Corpus template (C-Design, C-Modify); deployed corpus instance ready for PFF writes (C-Instance); completeness report identifying which OFFs can render (C-Validate)
- **Proven Applications:** Shipped 2026-04 as the C in the PFF/CFF/OFF triad (sibling to Process Formalization v2.0 and Output Formalization v1.0)
- **Known Limitations:** Requires a clear concept of what a workflow "accumulates" as a body — does not help when the unit of accumulation is unclear; chain relationships add complexity that must be designed deliberately
- **File Location:** frameworks/book/corpus-formalization.md (executable); ~/Documents/vault/Framework — Corpus Formalization.md (canonical)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0
- **Delivers:** New corpus template (C-Design); modified template (C-Modify); fresh corpus instance for the current period (C-Instance); completeness assessment of an instance (C-Validate)

### Output Formalization

- **Purpose:** Design, modify, render with, and audit bespoke output frameworks that express knowledge work in specific media (Word doc, deck, spreadsheet, logo, CAD drawing) at craft standard in a specified voice
- **Problem Class:** Output rendering and bespoke output-framework design
- **Input Summary:** O-Design: exemplar / template / verbal description / medium-plus-genre. O-Modify: existing bespoke OFF + change description. O-Render: bespoke OFF + content (from CFF, PFF, or supplied). O-Audit: existing bespoke OFF.
- **Output Summary:** Bespoke output framework composing content/craft/style/render layers (O-Design, O-Modify); rendered artifact in target medium (O-Render); quality audit with remediation recommendations (O-Audit)
- **Proven Applications:** Shipped 2026-04 as the O in the PFF/CFF/OFF triad (sibling to Process Formalization v2.0 and Corpus Formalization v1.0); also integrates with MindSpec voice for style consistency
- **Known Limitations:** O-Design quality depends on input modality clarity; voice consistency depends on a populated MindSpec or equivalent style profile; medium-specific render details may need user iteration
- **File Location:** frameworks/book/output-formalization.md (executable); ~/Documents/vault/Framework — Output Formalization.md (canonical)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0
- **Delivers:** New bespoke output framework for a specific medium/genre (O-Design); modified output framework (O-Modify); rendered artifact (O-Render); quality audit with remediation (O-Audit)

### Process Inference

- **Purpose:** Discover unknown transformation processes from defined endpoints when the user knows what they have and what they want but not the path between them
- **Problem Class:** Process discovery and formalization
- **Input Summary:** Current state description; desired end state description; available resources and constraints
- **Output Summary:** Inferred process map with decision points; Formalization Handoff Package for PFF conversion
- **Proven Applications:** Initial version — tested against process discovery scenarios
- **Known Limitations:** Requires honest endpoint definition; confabulation risk when constraints are underspecified
- **File Location:** frameworks/book/process-inference.md
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0
- **Delivers:** Discovered transformation paths (P-Infer); failure diagnoses (P-Debug); decomposed subproblem sets (P-Decompose); formalization handoff packages (P-Formalize); feasibility verdicts (P-Feasibility)

### Mission, Objectives, and Milestones Clarification

- **Purpose:** Convert a raw idea, tension, or goal into a structured hierarchy of Mission, Objectives, Constraints, and Milestones — either standalone (Project / Passion / Incubator) or under PEF supervision (Project-only with Active/Aspirational split and P-Feasibility-verified Active milestones)
- **Problem Class:** Project definition and strategic hierarchy formulation
- **Input Summary:** M-Standalone: raw idea description. M-Supervised: current problem definition from PED, current state description, optional Resolution Statement candidate and user-stated constraints
- **Output Summary:** Populated Mission, Objectives, Constraints, and Milestones in Matrix Master format (M-Standalone) or PED-insertion format (M-Supervised); Resolution Statement Objectivity Report; Excluded Outcomes field; classified Constraints; P-Feasibility verdicts for Active milestones (M-Supervised); No-Punt Escalation Report when Project Test fails under M-Supervised
- **Proven Applications:** Original standalone form used for project matrix authoring in the vault since 2025-09; v2.0 canonical with PEF supervision and Resolution Statement Objectivity Protocol landed 2026-04-23
- **Known Limitations:** M-Supervised Outcome 2 (terrain-mapping case) depends on the Terrain Mapping Framework as delivery vehicle; P-Feasibility invocation for Active milestones depends on PIF being available
- **File Location:** frameworks/book/mission-objectives-milestones.md
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 2.0
- **Delivers:** Standalone strategic hierarchy (M-Standalone); PEF-supervised strategic hierarchy with Active/Aspirational milestone split and P-Feasibility verdicts (M-Supervised)

### Terrain Mapping

- **Purpose:** Close knowledge gaps in an ill-mapped problem space through bounded research loops and produce a navigable Terrain Map Artifact sufficient for the calling framework (PEF or MOM) to formulate the next concrete milestone
- **Problem Class:** Problem-space mapping, knowledge gap closure, pre-PIF terrain preparation
- **Input Summary:** Current Problem Space (from PEF/MOM); Known Knowledge Gaps; Closure Criteria per Gap; optional project constraints, prior Excluded Outcomes, prior Terrain Map Artifact (TM-Continue), loop counter
- **Output Summary:** Terrain Map Artifact (separate vault document, minimal YAML `nexus:` and `type: terrain_map` only); calling-PED artifact reference; Return Package to PEF/MOM with gap-closure status and next-action recommendation; Escalation Package on three-loop non-convergence (no artifact written)
- **Proven Applications:** Initial version — designed to be invoked from PEF when PED reveals knowledge gaps that block the next milestone
- **Known Limitations:** Depends on the Deep Research Protocol (under development as of 2026-04-23; imminent DRP canonicalization will replace the temporary direct Ora research-capability scaffolding in Layer 3); three-loop threshold is bounded by design and shifts unresolvable problems back to the calling framework rather than producing a forced map
- **File Location:** frameworks/book/terrain-mapping.md
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0
- **Delivers:** Terrain map sufficient to formulate next concrete milestone (TM-Initiate / TM-Continue); problem redefinition escalation (TM-Escalate-Redefine, internally triggered)

### MindSpec Interview Framework

- **Purpose:** Produce complete MindSpec agent, character, or self specifications through tiered interactive assessment — single-file mind.md or [agent-name].md covering Core Identity, Mission, Context, Commitments, Governance, Constitution, Voice, Communication Patterns, and Relationships
- **Problem Class:** Agent/character/self identity specification and value-framework production
- **Input Summary:** Mode selection (agent / character / self); tier selection for agents (ephemeral / persistent task / personal thinking partner); user participation in structured assessment; optional descriptive material or existing specification for revision
- **Output Summary:** Single-file mind.md (or [agent-name].md) containing all sections for v0.2.3 forward; companion ledger.md (learning log, starts empty) and modifications.md (change log, starts empty); per-tier artifact subsets
- **Proven Applications:** Version 0.2.3 — 66-entry library, three-stage assessment instrument, inference layer, learning architecture; framework used to self-specify during rebuild
- **Known Limitations:** Concept-access-difficult commitments require incompatibility adjustment mechanism; Tier 1 ephemeral agents exempt from incompatibility adjustment; default values calibrated to general-population median; real-use feedback mandatory for high-accuracy specs
- **File Location:** frameworks/book/mindspec-interview.md
- **Provenance:** human-created
- **Confidence:** high
- **Version:** 0.2.3
- **Delivers:** Complete MindSpec agent specification (ephemeral, persistent task, or personal thinking partner tier) with tier-dependent assessment depth, incompatibility adjustment where applicable, and governance configuration (Agent); MindSpec fiction-character specification with pathology signatures produced through direct-authoring flow with coherence check (Character); MindSpec self-specification produced through full three-stage assessment with incompatibility adjustment and constitutional identification (Self)

### Conversation Processing Pipeline

- **Purpose:** Process raw conversation exports and live session exchanges into structured turn-pair chunks with contextual headers, topic metadata, and ChromaDB indexing for RAG retrieval
- **Problem Class:** Knowledge processing and conversation indexing
- **Input Summary:** Inline mode: prompt-response pair from orchestrator; Batch mode: raw conversation files in ~/Documents/conversations/raw/
- **Output Summary:** Processed chunk files in ~/Documents/conversations/; ChromaDB conversations collection entries; processing manifest
- **Proven Applications:** Inline processing for live sessions; batch processing for commercial AI exports (Claude, ChatGPT, Gemini)
- **Known Limitations:** Inline headers are template-generated; richer LLM-generated headers require batch mode
- **File Location:** frameworks/book/conversation-processing.md
- **Provenance:** human-created
- **Confidence:** high
- **Version:** 1.0
- **Delivers:** Processed conversation chunks with ChromaDB indexing (batch mode). Inline mode is pipeline-stage-exempt — invoked automatically by the orchestrator on every session turn, not PEF-selectable.

### Browser Evaluation Setup

- **Purpose:** Connect Playwright browser automation to commercial AI services and register endpoints for use by the orchestrator
- **Problem Class:** Integration setup
- **Input Summary:** Existing commercial AI accounts (Claude, ChatGPT, Gemini)
- **Output Summary:** Saved browser sessions; registered endpoints in endpoints.json
- **Proven Applications:** All tiers with existing subscriptions
- **Known Limitations:** Sessions expire; re-run when login cookies expire
- **File Location:** frameworks/book/browser-evaluation-setup.md
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0
- **Delivers:** Authenticated Playwright browser session registered for a commercial AI service (Claude, ChatGPT, Gemini, or custom URL) as an active endpoint in endpoints.json

### API Key Acquisition

- **Purpose:** Acquire and securely store API keys for commercial AI services, then register endpoints in endpoints.json
- **Problem Class:** Credential management
- **Input Summary:** User-selected AI providers
- **Output Summary:** API keys stored in system keyring; endpoints registered in endpoints.json
- **Proven Applications:** Anthropic, OpenAI, Google AI
- **Known Limitations:** Requires paid account for some providers
- **File Location:** frameworks/book/api-key-setup.md
- **Provenance:** human-created
- **Confidence:** high
- **Version:** 1.0
- **Delivers:** Configured API provider access — keys stored in credential store, endpoints registered in endpoints.json, fallback chain documented in api-providers.md

### Agent Identity and Programming

- **Purpose:** Create and program specialized agent identities using the MindSpec pattern, producing a compiled agent boot file and registry entry
- **Problem Class:** Agent creation and identity specification
- **Input Summary:** Agent purpose description; tier selection (functional vs. incarnated); mission parameters
- **Output Summary:** MindSpec canonical file set; compiled agent boot file; agent registry entry
- **Proven Applications:** Framework produced via F-Design from PFF v2.0
- **Known Limitations:** Incarnated agent voice calibration requires user-provided reference materials for best results
- **File Location:** frameworks/book/agent-identity.md
- **Provenance:** human-created
- **Confidence:** high
- **Version:** 1.0
- **Delivers:** New persistent AI agent identity as MindSpec canonical files plus compiled boot file plus registry entry (I-Create); modified agent's MindSpec files and recompiled boot file (I-Modify); full mission brief programming an existing agent to prosecute a mission autonomously (M-Program); compressed task specification assigning bounded work to an existing agent (M-Task)

### Spec-Code Reconciliation

- **Purpose:** Backward-reconcile installer specifications with the installed system, produce updated installer layers and a natural language system specification
- **Problem Class:** Specification maintenance and drift correction
- **Input Summary:** Installer manifest and layer files; live filesystem; git history; system file structure reference
- **Output Summary:** Discrepancy report with severity classifications; updated installer layers; natural language system specification derivable into installer
- **Proven Applications:** Designed for post-upgrade reconciliation of the ora system
- **Known Limitations:** Behavioral comparison requires LLM judgment — cannot be fully automated; accretion items require human confirmation of intent
- **File Location:** frameworks/book/spec-code-reconciliation.md
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0
- **Delivers:** Full backward-reconciliation bundle (discrepancy report, updated installer layers, natural language system specification) in Full Reconciliation mode; discrepancy report and resolution plan in Partial Reconciliation mode; natural language system specification alone in Specification Only mode

### Phase A — Prompt Cleanup

- **Purpose:** Mechanical preprocessing of raw user input: transcription correction, syntax normalization, reference resolution, semantic extraction, ambiguity resolution, and conversion to Operational Notation
- **Problem Class:** Pipeline Step 1 — prompt preprocessing
- **Input Summary:** Raw user prompt; recent conversation history; AMBIGUITY_MODE setting
- **Output Summary:** Cleaned prompt in natural language and Operational Notation; CORRECTIONS_LOG; INFERRED_ITEMS
- **Proven Applications:** New — designed from System Overview and research references
- **Known Limitations:** Quality of reference resolution depends on conversation history availability
- **File Location:** frameworks/book/phase-a-prompt-cleanup.md
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0
- **Delivers:** *Pipeline-stage exempt per PFF Section II subsection 2.3 — invoked by the orchestrator as Step 1 of every pipeline run, not PEF-selectable.*

### Deep Research Protocol

- **Purpose:** Produce structured, cited research reports addressing open-ended knowledge gaps via orchestrated multi-step search — vault-first, then parallel Level 1 subagent fan-out to web, browser AI, and API AI sources — with confidence-triggered iteration
- **Problem Class:** Open-ended research and knowledge gap resolution
- **Input Summary:** A research query (from TMF, user, or project agent); caller context; optional nexus, source filter, depth cap, subagent cap, persist flag
- **Output Summary:** Structured markdown research report with executive summary, per-sub-query sections, cross-query synthesis, named caveats, bibliography; saved to vault root with inherited nexus if specified
- **Proven Applications:** None yet — initial version
- **Known Limitations:** Token cost scales 4-15× a single-shot query (per Anthropic's published figures); vault-first retrieval quality depends on vault content; confabulation risk present where external sources are sparse
- **File Location:** frameworks/book/deep-research-protocol.md (executable); ~/Documents/vault/Framework — Deep Research Protocol.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Cited research reports addressing specified knowledge gaps via vault-first retrieval and parallel external fan-out

---

## Pipeline Stage Frameworks (Gear 4)

These six frameworks are loaded into model context windows at specific pipeline stages. They were extracted from the Gear 4 Pipeline Specifications container document.

*These six frameworks are pipeline-stage-exempt per PFF Section II subsection 2.3 — they are invoked by the orchestrator at specific pipeline stages and are not PEF-selectable. They do not declare Milestones Delivered or Delivers fields.*

### F-Analysis-Breadth (Step 3)

- **Purpose:** Green/Yellow hat analysis — map alternatives, surface opportunities, identify benefits
- **File Location:** frameworks/book/f-analysis-breadth.md

### F-Analysis-Depth (Step 3)

- **Purpose:** Black/White hat analysis — commit to best-supported answer, map risks and failure modes
- **File Location:** frameworks/book/f-analysis-depth.md

### F-Evaluate (Step 4)

- **Purpose:** Cross-adversarial evaluation — quality audit within mode + cross-modal perspective
- **File Location:** frameworks/book/f-evaluate.md

### F-Revise (Step 5)

- **Purpose:** Revision incorporating cross-evaluation feedback while retaining independent judgment
- **File Location:** frameworks/book/f-revise.md

### F-Consolidate (Step 7)

- **Purpose:** Synthesize both analyses into coherent output preserving convergent and divergent findings
- **File Location:** frameworks/book/f-consolidate.md

### F-Verify (Step 8)

- **Purpose:** Final verification — 7-check validation that consolidated output accurately represents both analyses
- **File Location:** frameworks/book/f-verify.md

### System File Drift Correction

- **Purpose:** Detect and reconcile drift between content files in the canonical vault and the `~/ora/` deployment surface, under explicit user-controlled direction with `.bak` backups for every overwrite
- **Problem Class:** System maintenance — vault/deployment dual-copy reconciliation
- **Input Summary:** Operation mode (D-Detect | D-Sync | D-Accept-Ora | D-Bootstrap); vault root path; ora root path; optional pair filter; explicit pair list (D-Accept-Ora only)
- **Output Summary:** D-Detect → drift report classifying every registered pair (`identical | yaml-only-diff | vault-newer | ora-newer | body-different | vault-only | ora-only | excluded`); D-Sync → vault→ora sync log with `.bak` paths; D-Accept-Ora → reverse sync log with `.bak` paths; D-Bootstrap → creation log for new vault copies derived from ora-only files matching registered patterns
- **Proven Applications:** New framework — landing 2026-04-28 alongside the vault canonicalization migration that produced the initial paired state
- **Known Limitations:** Refuses to silently resolve `ora-newer` pairs or pairing ambiguities — surfaces them as conflicts requiring explicit user decision. Pairing rules are category-keyed; new content categories require an updated Pairing Rules table in the framework spec.
- **File Location:** frameworks/book/system-file-drift-correction.md (canonical: ~/Documents/vault/Framework — System File Drift Correction.md)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0
- **Delivers:** Drift detection report classifying every registered file pair; drift correction (vault → ora) with `.bak` backups for every overwrite; reverse sync (ora → vault, opt-in) for explicitly-approved pairs; bootstrap creation of vault copies for ora-only files matching registered patterns

---

### Periodic Maintenance

- **Purpose:** Four scheduled vault-maintenance tasks for work that genuinely requires full-vault scans or has no runtime trigger; per the Runtime Principle, scheduled execution is reserved for tasks where runtime execution is impossible
- **Problem Class:** Vault maintenance, scheduled tasks
- **Input Summary:** Vault read access; for each scheduled task: the entire current vault state at the time the task runs
- **Output Summary:** Updated relationship graph (Task 1, weekly); vault health report with action items (Task 2, monthly); provenance audit fold-in (within Task 2); plus two additional scheduled tasks defined in the framework
- **Proven Applications:** Currently four named scheduled tasks ship with Ora; runtime-eligible work explicitly excluded per the Runtime Principle gate
- **Known Limitations:** Schedule cadences are fixed in the framework; tasks that become runtime-eligible should be migrated to the runtime pipeline rather than left here; fragility to bulk vault reorganization (which can flood Task 1's orphan threshold)
- **File Location:** frameworks/book/periodic-maintenance.md (executable); ~/Documents/vault/Framework — Periodic Maintenance.md (canonical)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0
- **Delivers:** Weekly orphan relationship cleanup; monthly vault health audit including provenance audit; additional scheduled vault hygiene tasks per the framework spec

---

### Video Editing Suggestions

- **Purpose:** Read a clip's whisper transcript and propose specific edits — cuts (filler, silence, false starts), chapter markers, title cards, transitions — as structured JSON the UI renders with one-click Apply buttons
- **Problem Class:** Audio/video editing assistance, transcript-driven suggestion generation
- **Input Summary:** Required: media-library entry id and normalized whisper transcript (`{language, duration_ms, segments: [{start_ms, end_ms, text}, ...]}`). Optional: free-text goals; current timeline state for the entry.
- **Output Summary:** JSON validated against `~/ora/config/framework-schemas/video-editing-suggestions.schema.json`; `entry_id`, `summary`, and ordered `suggestions[]` of four types (cut / chapter / title_card / transition), each with reason and source-time offsets.
- **Proven Applications:** New framework — landing 2026-05-01 with the heuristic generator (deterministic Python pass over the transcript). LLM path wired but gated until the user enables live model dispatch.
- **Known Limitations:** Heuristic generator covers filler, silence, false starts, and discourse-marker chapter cues — does not yet detect nuanced topic shifts, redundant content, or pacing issues. Auto-apply currently implemented for `cut` only; chapter / title_card / transition show a "coming soon" message on Apply. Cuts that span multiple timeline clips return `ok:false` and require manual resolution.
- **File Location:** frameworks/book/video-editing-suggestions.md (executable); ~/Documents/vault/Framework — Video Editing Suggestions.md (canonical); JSON Schema at config/framework-schemas/video-editing-suggestions.schema.json
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Schema-validated suggestions JSON for a transcribed clip; one-click cut application that splits the affected timeline clip, removes the cut span, and ripple-shifts later clips on the same track

---

## Deprecated / Archived

| Framework | Reason | Location |
|---|---|---|
| Boot Generation | Tier distinction collapsed; single boot.md serves all configs | ~/Documents/vault/Old AI Working Files/ |
| Progressive Boot Specification | Full install replaces progressive boot | ~/Documents/vault/Old AI Working Files/ |
| Boot Canonical A/B/C | Model interchangeability makes separate tier boots unnecessary | ~/Documents/vault/Old AI Working Files/ |
| Mind Framework | Superseded by MindSpec Interview Framework v0.2.3 (richer single-file spec with commitments, governance, constitution, voice, communication patterns, relationships vs. the older 5-section mind.md). Old Mind Framework produces only a 5-section mind.md; MindSpec produces the full spec. | ~/Documents/vault/Old AI Working Files/Framework — Mind.md (vault); ~/Documents/vault/Old AI Working Files/mind-framework.md.archived-2026-04-27 (the ora deprecated copy was archived 2026-04-27 and the deprecated/ folder was removed) |
