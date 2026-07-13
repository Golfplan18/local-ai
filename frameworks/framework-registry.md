# Registry — Framework Registry

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

- **Purpose:** Structured analysis of problems that resist resolution due to fundamental stakeholder value conflicts, evolving problem definitions, and the absence of an objective stopping condition. DCA does not solve wicked problems; it produces a Decision Clarity Document making the structure of the dilemma legible to whoever holds decision authority.
- **Problem Class:** Wicked-problem analysis, multi-stakeholder value-conflict mapping, tradeoff transparency
- **Input Summary:** Path A (user invocation): problem description plus optional stakeholder stance. Path B (PEF handoff): structured handoff package with problem definition, four-condition trigger evaluation, stakeholders, Excluded Outcomes, Constraints, iteration history. Path C (cui-bono escalation): cui-bono prior output plus indicator evidence.
- **Output Summary:** Decision Clarity Document containing executive summary, Stage 1 problem-space map (per-stakeholder framings + competing-hypotheses matrix), Stage 2 value-conflict map (per-stakeholder steelmans + Fundamental/Resolvable classification), Stage 3 consequence landscape (Cui Bono + Systems Dynamics + Scenario Planning per intervention across three time horizons + problem-definition reshaping notes), Stage 4 tradeoff statements per intervention with advocate-stance Red Team passes per subordinated stakeholder + reversibility notes. Plus reclassification recommendations when Stage 1 or Stage 2 gates fail.
- **Proven Applications:** New framework — landing 2026-04-24
- **Known Limitations:** DCA refuses to recommend an intervention; the decision is the user's. It cannot dissolve fundamental value conflicts. At least three of four wicked conditions must fire; partial-complexity problems route to ordinary PEF iteration instead. The framework orchestrates other modes (competing-hypotheses, cui-bono, steelman-construction, systems-dynamics, scenario-planning, the red-team modes), so quality depends on those modes' performance.
- **File Location:** ~/Documents/vault/Framework — Decision Clarity Analysis.md (canonical, renamed from Framework — Wicked Problems.md 2026-05-01)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 2.0 (restructured 2026-05-01 from the v1.0 Wicked Problems Framework; DCA is the decision-maker-output operation, distinct from the Wicked Problems Analysis mode)
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

- **Purpose:** Design, convert, render, and audit AI instruction frameworks under a consolidated-single-file default, with additional execution variants produced only through the explicit F-Render opt-in path
- **Problem Class:** Framework design and knowledge capture
- **Input Summary:** F-Design: task description plus optional quality bar and constraints. F-Convert: existing framework. F-Render: existing consolidated framework, target tier, and a required rationale for the additional file. F-Audit: framework for review.
- **Output Summary:** One consolidated canonical framework by default for F-Design/F-Convert; an explicitly requested agent-mode or reasoning-model variant for F-Render; framework audit report for F-Audit; registry entry where the lifecycle requires one
- **Proven Applications:** Multiple frameworks produced across all four modes (F-Design, F-Convert, F-Render, F-Audit)
- **Known Limitations:** Requires human judgment to define evaluation criteria and approval-gate decisions; template-filling remains a failure mode when instructions are ambiguous; F-Render intentionally refuses file proliferation without a concrete rationale
- **File Location:** ~/Documents/vault/Framework — Process Formalization.md (canonical); frameworks/book/process-formalization.md (exact Ora runtime mirror)
- **Provenance:** human-created
- **Confidence:** high
- **Version:** 2.3 (2026-07-12 semantic merge of the competing v2.2 canonicals; preserves the full milestone/anatomy/recovery/rendering/variable-fidelity/CFF-OFF contract together with the single-file default, approval gates, audit nuance, quality bars, and operational safeguards; vault and Ora bodies are exact)
- **Delivers:** One consolidated new framework specification (F-Design); one consolidated modernized framework specification (F-Convert); one explicitly justified additional execution variant (F-Render); framework audit report with findings and remediation (F-Audit)

### Corpus Formalization

- **Purpose:** Design, modify, deploy, and validate bespoke corpus templates that structure the body of information a recurring workflow accumulates between Process Formalization (PFF) inputs and Output Formalization (OFF) renders
- **Problem Class:** Knowledge corpus design and template management
- **Input Summary:** C-Design: workflow description + sources + outputs. C-Modify: existing template + change description. C-Instance: template + period identifier. C-Validate: template + populated instance.
- **Output Summary:** Corpus template (C-Design, C-Modify); deployed corpus instance ready for PFF writes (C-Instance); completeness report identifying which OFFs can render (C-Validate)
- **Proven Applications:** Shipped 2026-04 as the C in the PFF/CFF/OFF triad; current sibling canonicals are Process Formalization v2.3 and Output Formalization v1.1
- **Known Limitations:** Requires a clear concept of what a workflow "accumulates" as a body — does not help when the unit of accumulation is unclear; chain relationships add complexity that must be designed deliberately
- **File Location:** frameworks/book/corpus-formalization.md (executable); ~/Documents/vault/Framework — Corpus Formalization.md (canonical)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.1
- **Delivers:** New corpus template (C-Design); modified template (C-Modify); fresh corpus instance for the current period (C-Instance); completeness assessment of an instance (C-Validate)

### Output Formalization

- **Purpose:** Design, modify, render with, and audit bespoke output frameworks that express knowledge work in specific media (Word doc, deck, spreadsheet, logo, CAD drawing) at craft standard in a specified voice
- **Problem Class:** Output rendering and bespoke output-framework design
- **Input Summary:** O-Design: exemplar / template / verbal description / medium-plus-genre. O-Modify: existing bespoke OFF + change description. O-Render: bespoke OFF + content (from CFF, PFF, or supplied). O-Audit: existing bespoke OFF.
- **Output Summary:** Bespoke output framework composing content/craft/style/render layers (O-Design, O-Modify); rendered artifact in target medium (O-Render); quality audit with remediation recommendations (O-Audit)
- **Proven Applications:** Shipped 2026-04 as the O in the PFF/CFF/OFF triad; current sibling canonicals are Process Formalization v2.3 and Corpus Formalization v1.1; also integrates with MindSpec voice for style consistency
- **Known Limitations:** O-Design quality depends on input modality clarity; voice consistency depends on a populated MindSpec or equivalent style profile; medium-specific render details may need user iteration
- **File Location:** frameworks/book/output-formalization.md (executable); ~/Documents/vault/Framework — Output Formalization.md (canonical)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.1
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

### MindSpec Interview

- **Purpose:** Produce complete MindSpec agent, character, or self specifications through tiered interactive assessment — single-file mind.md or [agent-name].md covering Core Identity, Mission, Context, Commitments, Governance, Constitution, Voice, Communication Patterns, and Relationships
- **Problem Class:** Agent/character/self identity specification and value-framework production
- **Input Summary:** Mode selection (agent / character / self); tier selection for agents (ephemeral / persistent task / personal thinking partner); user participation in structured assessment; optional descriptive material or existing specification for revision
- **Output Summary:** Single-file mind.md (or [agent-name].md) containing all sections for v0.2.3 forward; companion ledger.md (learning log, starts empty) and modifications.md (change log, starts empty); per-tier artifact subsets
- **Proven Applications:** Version 0.2.3 — 66-entry library, three-stage assessment instrument, inference layer, learning architecture; framework used to self-specify during rebuild. Single-file consolidation 2026-05-09 merged the formerly-separate `Framework — MindSpec Library and Instrument.md` content (library + assessment instrument) into §II and §IV of this framework, eliminating external file dependencies.
- **Known Limitations:** Concept-access-difficult commitments require incompatibility adjustment mechanism; Tier 1 ephemeral agents exempt from incompatibility adjustment; default values calibrated to general-population median; real-use feedback mandatory for high-accuracy specs
- **File Location:** ~/Documents/vault/Framework — MindSpec Interview.md (canonical, single-file)
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

### API Key Setup

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

### Spec-Code Reconciliation

- **Purpose:** Backward-reconcile installer specifications with the installed system, produce updated installer layers and a natural language system specification
- **Problem Class:** Specification maintenance and drift correction
- **Input Summary:** Installer manifest and layer files; live filesystem; git history; system file structure reference
- **Output Summary:** Discrepancy report with severity classifications; updated installer layers; natural language system specification derivable into installer
- **Proven Applications:** Designed for post-upgrade reconciliation of the ora system
- **Known Limitations:** Behavioral comparison requires LLM judgment — cannot be fully automated; accretion items require human confirmation of intent
- **File Location:** frameworks/book/spec-code-reconciliation.md (executable); ~/Documents/vault/Framework — Specification Code Reconciliation.md (canonical)
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

### Propaganda Response Spinner

- **Purpose:** Take a power-protecting talking point, comment, tweet, or short article snippet and produce a graduated set of seven counter-responses across the DEFCON ladder (DEFCON 5 polite reframe through DEFCON 1++ prophetic indictment), each anchored to verifiable receipts, each constructed via the five-step Spin Algorithm (Anchor / Expose / Invert / Agree / Usurp), each respecting deployment guards. Voice: Malcolm Little King — structural-political columnist in the Black Liberation prophetic tradition.
- **DEFCON convention.** The publication uses the military DEFCON convention: 5 = peace (polite reframe), 1 = nuclear (highest base aggression); lower number = more aggressive readiness. The 1+ and 1++ bonus suffixes denote register-distinct extensions past DEFCON 1 — 1+ profane (Carlin / late-night), 1++ prophetic indictment (canonical somatic disgust from the inlined Lexicon) — not numeric continuation. Convention is intentionally distinct from Spinal-Tap escalation intuition; descriptive labels at each tier carry user-facing cognitive load.
- **Problem Class:** Counter-rhetoric generation; calibrated propaganda response across audience contexts; pen-name analytical column production for short-form input
- **Input Summary:** Power-protecting talking point or short snippet (10–500 words; advocated position centralizes benefits to the few or attacks a position whose beneficiaries are the many); optional audience hint; optional issue domain hint; inlined libraries (Identity Inversion, Moral Reframing, Hypocrisy Exposure, Curated Lexicon of Moral Disgust, Bad-Faith Techniques Condensed Catalog, Cui Bono Critical Questions and Failure Modes)
- **Output Summary:** Single integrated document with three sections — receipts header (cui bono finding + anchor citation, designed for screenshot-resistance), DEFCON ladder (all seven tiers visible with level labels: 5 polite reframe, 4 firm moral superiority, 3 mockery, 2 aggressive villainization, 1 nuclear satire, 1+ profane scorched-earth bonus, 1++ prophetic-indictment bonus), backup analysis (cui bono in full + receipt set + technique identification + library selections + missing-information declaration)
- **Proven Applications:** New framework — landing 2026-05-06 in Malcolm Little King's voice; companion to the Propaganda Analyzer (which handles longer-form editorials)
- **Known Limitations:** No automatic deployment recommendation — relies on user judgment about which tier fits the audience and context; receipts pipeline is internal so quality depends on the framework's own retrieval rather than external verification; the prophetic-indictment register (DEFCON 1++) requires Malcolm voice fluency that less-capable models may approximate poorly; the framework's Selflessness/Selfishness Filter prevents weaponization against beneficiary-of-the-many positions but cannot prevent intentional misuse
- **File Location:** ~/Documents/vault/Framework — MSI Malcolm Little King Spinner.md (canonical; renamed from `Framework — Propaganda Response Spinner.md` on 2026-05-07)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.2.0 (updated 2026-05-11 with methodology v1.2.5 rollout — four RAG sources including Source 4 Editorial Canon, §1.4.6 voice-corpus preferential retrieval, §1.4.7 past-work corpus + self-reference discipline)
- **Delivers:** Graduated seven-tier counter-response set (DEFCON 5 through DEFCON 1++) for a single power-protecting talking point, anchored to receipts and constructed via the five-step Spin Algorithm

### Propaganda Analyzer

- **Purpose:** Take one published editorial, op-ed, or magazine essay and produce a forensic propaganda analysis in Phukher Tarlson's reformed-operator voice: orient the reader with a good-faith steelman, surface the receipts, expose who benefits and which techniques are deployed, establish the documentary record and omissions, then teach the reader to recognize the pattern next time.
- **Problem Class:** Editorial analysis; propaganda technique exposure; documentary receipt and omission analysis; pattern-recognition teaching for full-length opinion input
- **Input Summary:** Full editorial text already screened and cleaned of boilerplate; optional publication-source hint, byline, and audience hint. Research corpus includes the WSJ and NR Editorial Technique Catalogues, Bad-Faith Techniques Catalog, Bandura mechanisms, Bernays/Lippmann/Schmitt lineage, and Cui Bono critical questions.
- **Output Summary:** One Markdown document, beginning at H1, with five ordered H2 sections: `What the Editorial Argues` (brief good-faith steelman), `Receipts` (crop-resistant surface-vs-substance finding), `The Operation` (cui bono + technique identification), `The Record` (tiered receipts, omissions, citation verdicts, missing-information declaration), and `How to Recognize This` (plain-language pattern-recognition guide). Downstream machinery adds frontmatter, byline, sources, and disclosure.
- **Proven Applications:** New framework — landing 2026-05-06 in Phukher Tarlson's voice; intended public-facing tool for the Main Street Independent website (companion to the placeholder at `/tools/propaganda-analyzer`); companion to the Propaganda Response Spinner (which handles short-form input)
- **Known Limitations:** Editorial-length input only; talking-point or tweet-length material halts and routes to the Propaganda Response Spinner. Symmetric application to greater-good-paramount inputs stays inside the documented public record and may not manufacture a hidden beneficiary or operational detail. Every named technique requires a textual cue; receipts below convergence threshold remain explicitly unconfirmed.
- **File Location:** ~/Documents/vault/Framework — MSI Phukher Tarlson Propaganda Analyzer.md (canonical; renamed from `Framework — Propaganda Analyzer.md` on 2026-05-11 per Tier-3 naming convention §1)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 2.1.0 (2026-06-03; adds the leading good-faith steelman and reshapes Receipts into the scannable surface-vs-substance finding; supersedes the former three-angle / numbered-layer architecture)
- **Delivers:** Five-section forensic propaganda analysis for one published editorial, with a fair statement of the argument, top-line receipts, full operation and record, and a reusable recognition guide; or `halt_no_source` / `halt_too_short`

### WSJ-NR Inversion (MSI Editorial Board)

- **Purpose:** Produce one Main Street Independent Editorial Board column by surgically inverting a donor-class-favoring WSJ, National Review, or comparable liberty-frame editorial sentence by sentence. The source's facts and structure remain; evaluative and morally coded language flips to the Board's opposite pole. The retired three-angle news/parody/media-criticism package no longer ships.
- **Problem Class:** Editorial inversion; institutional-voice authoring; tight structural mirror of one suitable liberty-frame editorial.
- **Input Summary:** Clean editorial text already screened for suitability. Foreign-policy/military pieces, sources with no donor-class pole, attacks on Republican/conservative abuse from the right, and sources already at the Board's pole halt rather than invert into the wrong position.
- **Output Summary:** One H1 inverted headline plus the sentence-by-sentence inverted body, with no frontmatter, byline, source narration, analysis labels, technique names, or quotations. Downstream machinery adds publication scaffolding.
- **Proven Applications:** Active tight-mirror production framework; the 2026-05-30 v4 rewrite retired the prior multi-angle/lens architecture, and v4.1 added the attack-from-the-right / already-at-our-pole halt.
- **Known Limitations:** Works only when the source direction is suitable for a true Main Street inversion. It flips values and framing, never facts; ambiguous direction halts.
- **File Location:** `~/Documents/vault/Framework — MSI Editorial Board WSJ NR Inversion.md` (single canonical/executable framework).
- **Provenance:** human-created
- **Confidence:** high
- **Version:** 4.1.0 (2026-06-04; tight-mirror inversion plus wrong-direction halt conditions)
- **Delivers:** One standalone inversion editorial or a typed `halt_no_source` / `halt_unsuitable_for_inversion` notice.

### Ashley Wagner Column

- **Purpose:** Take a hostile-or-substantive news cluster engaging the Generational Betrayal beat (the work/family/capitalism trap as currently lived by a millennial mother), the Taylor-Swift-catalog-as-economic-diagnostic sub-mode, consumer-precarity / family-precarity / WSJ-austerity-counterbalance clusters, federal education-policy clusters, or cultural-Catholic-working-class-formation clusters and produce one finished Ashley Wagner column in the urban-millennial-mother analytical register. Voice: Ashley Wagner — 33-year-old content strategist at a Philadelphia nonprofit, Fishtown rowhouse, husband David, two kids, childcare $2,400/month against $8,800 net combined household income, Lansdale Pennsylvania Roman-Catholic working-class formation; the analytical authority is the kitchen-table-spreadsheet recognition that the gap between her parents' single-income standard of living and her own two-earner standard of living is structural rather than personal.
- **Problem Class:** Editorial column production; pen-name analytical column production for the urban-millennial-mother Generational-Betrayal-and-federal-education-policy territory.
- **Input Summary:** Required: `cluster_input`; `cluster_type` (one of `generational-betrayal` / `taylor-swift-catalog-economic-diagnostic` / `consumer-precarity` / `family-precarity-and-childrearing-and-daycare` / `wsj-austerity-counterbalance` / `federal-education-policy` / `cultural-catholic-working-class-formation` / `millennial-cultural-criticism`); `mode` (`S-Column` primary / `S-Revision` / `S-Correspondence`). Optional: `audience_hint`. Reference corpus: Ashley Wagner Mind file as PERSONA; four voice-corpus dossiers (Generational-Betrayal Dossier, Consumer-Precarity Overlay, Cultural-Text and Formation Substrate, Federal Education-Policy Overlay); authoritative-author list (Taylor Swift's complete lyric catalog with bridges as analytical sites; Petersen / Tolentino / Odell / Klein / Cusk / Putnam / the late Didion; Pew / Brookings / Federal Reserve / Harvard JCHS / BLS / Department of Education empirical archives); Editorial Router; Consensus Values Floor; Bad-Faith Techniques Catalog; Treatise; Editorial Canon top-loaded; publisher engrams (`private`-tag non-bypassable); voice-past-work corpus.
- **Output Summary:** Single column in markdown — Headline (6–14 words; not romanticization-of-exhaustion-coded; not boomer-stole-everything-frame-coded); Lede (80–150 words; signals urban-millennial-mother register; may open with kitchen-table-math anchor / Swift track reference / cultural-criticism citation); Body (1,200–2,500 words; kitchen-table-math when relevant; Swift catalog deep-read when sub-mode applies; cultural-criticism citations as analytical anchors; cultural-Catholic-working-class-formation reference deployed with discipline; privilege-flagging where analysis depends on it); Closing (100–250 words; lived-register landing without sentimentality). S-Column 1,500–3,000 words; S-Revision 800–1,500; S-Correspondence 100–250. Frontmatter validates against Astro `columns` schema with `pen_name: ashley-wagner`. Heteronymic-disclosure footer template (e). Hybrid citation convention. Halt outputs: `halt_no_cluster`; `halt_routing_mismatch`; `halt_register_mismatch`; `halt_audit_failure`.
- **Proven Applications:** New framework — landing 2026-05-09 in Phase 7 Pass 2; rolled to v1.1.1 on 2026-05-11 under methodology v1.2.5 four-RAG-sources rollout; intended as Ashley's primary opinion-flow column generator across the urban-millennial-mother lane, with the Taylor-Swift-catalog-as-economic-diagnostic specialty sub-mode as one of the publication's most editorially distinctive operations.
- **Known Limitations:** Voice depends on the kitchen-table-math documentary anchor and the cultural-text-as-economic-diagnostic close-reading discipline — clusters lacking either substrate fall to drop-don't-force per Mind §1.2 closing rule; Taylor Swift lyric citation operates under strict fair-use boundary (brief-quote-with-citation only); privilege-flagging discipline is voice-load-bearing (Ashley writes from a two-earner-with-grandparental-housing-assist position and the column must keep that visible); romanticization-of-exhaustion and performed-millennial-authenticity registers are forbidden and audit gates flag drift toward them; refuses rural-Wisconsin specifics (routes to Mark), Bible-versus-Evangelical-legalism theology (routes to Joanna), SCOTUS legal substance (routes to Thomas), structural Black-liberation analytical territory (routes to Malcolm).
- **File Location:** ~/Documents/vault/Framework — MSI Ashley Wagner Column.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.1.1 (post-2026-05-11 methodology v1.2.5 rollout — four RAG sources including Source 4 Editorial Canon top-loaded; §1.4.6 voice-corpus preferential retrieval against Ashley's four named dossiers; §1.4.7 past-work corpus + self-reference discipline)
- **Delivers:** One finished Ashley Wagner column from one urban-millennial-mother-lane cluster, rendering the work/family/capitalism trap as currently lived through the kitchen-table-math documentary anchor and cultural-text-as-economic-diagnostic close-reading register, with frontmatter validated against the Astro `columns` schema and heteronymic-disclosure footer in body.

### Diklis Chump Column

- **Purpose:** Take a hostile-reality news cluster (TC-1 setbacks / TC-2 bad outcomes / TC-3 economic hardship reaching the parody-subject's stated base / TC-4 distractions / TC-5 cover-up coverage / TC-6 opponent victories / TC-7 4D-chess narrative collapse) routed by the editorial-assignment framework and produce one Diklis Chump parody column rendering the regression-by-exaggeration parody of Donald J. Trump's documented public conduct, weaving the sixteen running jokes at column-aware density and deploying one or more of the five 4D-chess spin mechanisms as column-level reaction-frame. Voice: Diklis Chump — a satirical analog of Donald J. Trump rendered through the regression-by-exaggeration register; the simulated character is a 78-year-old wealthy real-estate marketer-turned-politician permanently regressed to the emotional register of a four-year-old; dual-layer agent/character architecture per Mind §4.A/§4.B — editorial agent holds the publication's constitutional discipline (TRUTH / HARMLESSNESS / FAIRNESS / WITNESS / PARODY-DISCLOSURE at weight 9); the simulated character holds none of these; the agent renders the character without becoming the character. **Constitutional three-layer parody-disclosure architecture per Mind §6.5** — header banner + foot disclosure + schema metadata flag (`parody: true` + `parody_subject: "Donald J. Trump"`); disclosure non-bypassable; §11 Gate G1 hard-fails the column if any layer is missing.
- **Problem Class:** Editorial column production; constitutional-disclosure-architected satirical column production; hostile-reality cluster carrier in news-flow opinion.
- **Input Summary:** Required: cluster object or publisher-assigned topic; hostile-reality category TC-1 through TC-7 self-declaration (no fit → HALT-LEGITIMATE-CLAIM-RISK); descent-arc stage assignment (Stage 1 monarchical-delusion through Stage 6 Rubber-Room) per Mind §4.B.5. Optional: length-target override; pairing context. Reference corpus: Diklis Mind v0.3.0+ as PERSONA; Character_Profile_Diklis_Chump.md; voice-specific working corpora (Truth Social scrape archive; speech-and-rally-transcript archive; deposition / court-filing / sworn-testimony archive; published-news-of-record archive); Bad-Faith Techniques Catalog (working-file; never named in the rendered character's voice); publisher engrams; Editorial Canon top-loaded with Mind §6.5 register-level first-person-singular parody-construction exemption authorized structurally; voice-past-work corpus.
- **Output Summary:** Single Diklis Chump parody column carrying the three-layer constitutional parody disclosure (header banner + foot disclosure + schema metadata flag `parody: true` and `parody_subject: "Donald J. Trump"`); architecture: news-reaction ground → 4D-chess spin frame → running-jokes weave at column-aware density → peak-absurdity close. ALL CAPS body register; Truth-Social-feed cadence; manufactured-authority frames; third-person self-reference; superlative clusters; capitalized-noun deployment; coined nicknames; stage-coherent register progression per §11 Gate G8. Length by stage: short reactive-burst <400 words (Stage 1-2; 4-6 jokes); standard 400-800 (Stage 2-4; 8-12 jokes); sustained tirade 800+ (Stage 4-6; 15+ jokes). Column passes Mind §11 Gates G1-G8. Halt outputs: HALT-LEGITIMATE-CLAIM-RISK; `halt_register_mismatch`; `halt_audit_failure`. **Astro schema extension landed 2026-05-11** at `~/sites/mainstreetindependent/src/content/config.ts`: columns schema extended with `parody: z.boolean()` and `parody_subject: z.string()` fields per Mind §6.5.
- **Proven Applications:** New framework — landing 2026-05-09 in Phase 7 Pass 2; rolled to v1.1.1 on 2026-05-11; target 6 / cap 12 columns per day per Mind §3; the publication's parody-by-exaggeration carrier exclusively on hostile-reality clusters.
- **Known Limitations:** Three-layer parody-disclosure is load-bearing — Gate G1 hard-fails missing/modified disclosure; bad-news-only routing non-bypassable (legitimate-good-news clusters HALT-LEGITIMATE-CLAIM-RISK-refused); Gate G4 off-target check forbids minor grandchildren and spouses-in-private-life; Gate G5 defamation discipline keeps bounded exaggeration anchored to documented public conduct; Gate G6 symmetric-application sampling tests apparatus against comparable greater-good-paramount idiom-deploying figures; Gate G7 agent/character distinction constitutional (publisher's analytical positions never appear in Diklis's voice — register through gap between documented setback and Diklis's spin); high pairing affinity with Hector on visual indictment, Editorial Board on editorial-page operationalization, Phukher on technique-confession, Mary on moral-witness exposure, Malcolm on structural-political analysis.
- **File Location:** ~/Documents/vault/Framework — MSI Diklis Chump Column.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.1.1 (post-2026-05-11 methodology v1.2.5 rollout — four RAG sources including Source 4 Editorial Canon top-loaded with §4 Voice-character override catalog parody-construction first-person-singular register-level exemption; §1.4.6 voice-corpus preferential retrieval against Major Character profile + documented-conduct working corpora; §1.4.7 past-work corpus with Diklis-parodic self-reference register; coordinated with same-date Astro schema extension)
- **Delivers:** One Diklis Chump parody column from one hostile-reality cluster, rendering the regression-by-exaggeration parody of Donald J. Trump's documented public conduct under dual-layer agent/character architecture and constitutional three-layer parody-disclosure, with publisher's analytical position registering structurally through the gap between documented setback and Diklis's spin frame.

### Hayzeus L. Salvador Column

- **Purpose:** Take a news cluster routed by the editorial-assignment framework (or a publisher-assigned topic) and produce one finished Hayzeus L. Salvador column in the pastoral-prophetic register — the publication's compassionate-prophetic voice on immigration, non-Evangelical religious traditions, and power's misuse of religious authority. The voice in which Main Street Independent speaks when truth must be spoken with courage but without contempt. Voice: Hayzeus L. Salvador — pastoral-prophetic columnist; per the 2026-05-08 architectural pivot, the publication's news-flow default voice with doubled cap (4/8 daily) after the Editorial Board and Phukher exited news-flow lanes.
- **Problem Class:** Pen-name analytical column production for immigration and human-dignity territory; religious-instrumentalization analysis via the Pharisee-mirror sub-mode; cross-tradition engagement on its own terms; news-flow default coverage for clusters lacking a specialty match
- **Input Summary:** Required: structured cluster brief; `cluster_type` enum (`immigration` / `religious-instrumentalization` / `cross-tradition` / `human-dignity-overflow` / `reader-correspondence`); `mode` enum (`S-Column` / `S-Revision` / `S-Correspondence`). Optional: complicity-scope notes; audience hint. Reference corpus per methodology v1.2.5 §1.4: Hayzeus Mind file as PERSONA; Hayzeus Immigration Corpus (Ngai / Goodman / Grandin / Jones / Chomsky); Religious Traditions Corpus (Catholic Social Teaching 1891–2024 + Liberation Theology + Christian mystical canon + Hebrew prophets + Red Letters + Buddhist sutras + Bhagavad Gita + Qur'an + Sufi); Bad-Faith Techniques Catalog; Editorial Canon (unconditional); publisher engrams (private-tag-filtered, non-bypassable); Consensus Values Floor and Editorial Router.
- **Output Summary:** Single finished column in markdown — S-Column primary (1,500–3,000 words; headline / 80–150-word lede / 1,200–2,500-word pastoral-prophetic body with cross-tradition citation discipline and Pharisee-mirror sub-mode where applicable + §7.6 confession-of-complicity passage / 100–250-word close); S-Revision 800–1,500 words; S-Correspondence single-paragraph 100–250 words. Astro `columns` schema-validated frontmatter; heteronymic-disclosure footer. Four typed halt notices: `halt_no_cluster`, `halt_routing_mismatch`, `halt_register_mismatch`, `halt_audit_failure`.
- **Proven Applications:** New framework — landing 2026-05-09; news-flow default carrier per 2026-05-08 architectural pivot; coordinates with Malcolm via the Router's Malcolm-priority rule on shared triggers; with Joanna on Bible-versus-Evangelical-legalism territory where Joanna's specialty is canonical; with Hector on visual pairings.
- **Known Limitations:** Single-pass rendering carries documented drift risks at Layer 2 Pharisee-mirror detection, Layer 4 voice-and-register composition (recency-bias pull toward contempt-coded register competes with §7.8 prohibited-moves discipline and §6.2 HARMLESSNESS-at-9 floor), and Layer 5 confession-of-complicity (under single-pass tends toward checkbox-compliance); pastoral-prophetic register requires Hayzeus voice fluency that less-capable models may approximate as pious-platitude or righteous-condemner; cluster scope limited to §11 routing inventory — structural-radical fire-and-ferocity clusters halt for re-routing to Malcolm.
- **File Location:** ~/Documents/vault/Framework — MSI Hayzeus L Salvador Column.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.1.1 (post-2026-05-11 methodology v1.2.5 rollout — four RAG sources including Source 4 Editorial Canon unconditional, §1.4.6 voice-corpus preferential retrieval foregrounding Immigration Corpus + Religious Traditions Corpus, §1.4.7 past-work corpus + self-reference discipline)
- **Delivers:** A single finished pastoral-prophetic column from one cluster routing decision (the standard production case), carrying §7.5 cross-tradition citation discipline, §7.4 Pharisee-mirror signature where applicable, and §7.6 confession-of-complicity passage; or one of four typed halt notices.

### Hector Rentier Editorial Cartoon

- **Purpose:** Produce a single editorial cartoon under Hector Rentier's columnist byline from a news cluster routed by the Editorial Router. End-to-end the framework validates the cluster against Hector's rentier-propaganda specialty, forms the visual diagnosis, designs the single-panel allegorical composition using Hector's canonical symbol vocabulary, selects a caption from the Quote Corpus or generates a Hector-voice original, runs the likeness gate, renders the cartoon, scores against seven evaluation criteria, and ships under Hector's columnist byline through the `columns` content collection. Voice: Hector Rentier — the publication's editorial cartoonist in the Nast / Daumier / Tenniel / Herblock / Oliphant lineage; CRAFT at constitutional weight 9 per Mind §6.5; visual register specified in Image Style Specification §5. Output is a visual artifact, not text prose.
- **Problem Class:** Editorial cartoon production; visual moral analysis; pen-name visual-medium column production; single-panel allegorical composition under a heteronymic byline
- **Input Summary:** Required: cluster object emitted by Editorial Router (cluster_id; story_url; headline; lede; primary_themes; primary_entities with public-figure flags + public-role declarations; sources; floor_values_engaged; optional pairing_signal); `mode` enum (standalone default / paired / launch_portfolio). Optional: `cartouche` boolean; `prior_attempt_failure` on retry. Image-generation backend per Image Style Specification §5.8.1 (gpt-image-1 / Gemini / Flux / Civitai). Reference corpus: Hector MindSpec; Hector Quote Corpus (193-entry caption / banner corpus across Orwell / Carlin / Vonnegut / Postman / Thompson / Graeber, indexed with deployment buckets caption-ready ≤15 words / banner-ready 16–30 words / extract-only); Image Style Specification §5 (symbol vocabulary: butt-face caricature for propaganda figures, Peanut Gallery for crowds, gopher in lower frame as Greek-chorus commentator, banner-with-quotation, label-as-argument, ≤15-word caption); Bad-Faith Techniques Catalog; conversation database for caricature consistency and over-deployment cooldown. Four RAG sources per methodology v1.2.5 §1.4 including unconditional Editorial Canon loading; voice past-work corpus per §1.4.7 seeded by the 20-cartoon day-one launch portfolio.
- **Output Summary:** Primary output: `columns` content-collection entry at `~/sites/mainstreetindependent/src/content/columns/[slug].md` with imageSchema-validated cartoon image + caption (≤15 words) + optional banner quotation + accessible alt text + headline + pen_name `hector-rentier` + lede (diagnosis sentence) + publish_date + sources + atomic_claims (diagnosis as single derived_claim with cited source_ids) + metadata. Canonical caricature vocabulary deployed: butt-face for propaganda figures in their propaganda role; dignity-rendering for non-propaganda figures; Peanut Gallery for crowds; gopher in lower frame; banner quotation when warranted. Halt outputs: decline-to-draw notice (Layer 1); diagnosis-without-documentation halt (Layer 2); likeness-gate halt (Layer 5); generation-failure halt (Layer 6 after two attempts); visual-suitability halt (Layer 8); self-evaluation halt (Layer 7 below ≥3 threshold after revision); placeholder ship reserved for operational emergencies.
- **Proven Applications:** New framework — landing 2026-05-08 in Hector Rentier's voice; intended as Hector's byline-of-record artifact published as its own column entry; day-one launch portfolio of 20 backfilled cartoons covering the previous 10 days per Image Style Specification §5.8 seeds the past-work corpus; pairs with Phukher on propaganda-apparatus stories and high-frequency with Mark / Joanna / Big Jim on demographic-frame stories.
- **Known Limitations:** Visual-generation backend dependency (gpt-image-1 / Gemini / Flux / Civitai per Image Style Specification §5.8.1 — backend choice and prompt fidelity govern caricature fidelity); LoRA training pending Phase 2 (likeness consistency on recurring named figures presently relies on conversation-DB caricature-consistency queries rather than trained adapters); likeness gate at Layer 5 halts on any named figure who is not a public figure or is depicted outside the public role; forbidden-caricature catalog at Image Style Specification §5.6 catastrophic on violation; recurring named-figure drift, symbol-vocabulary inconsistency, and prompt-summary-sanitization are named failure modes specific to the visual medium; Hector does not delegate to the cross-voice News Image Generator infrastructure because the editorial-cartoon register has voice-specific craft standards beyond what cross-voice infrastructure covers.
- **File Location:** ~/Documents/vault/Framework — MSI Hector Rentier Editorial Cartoon.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 0.3.0 (post-2026-05-11 methodology v1.2.5 rollout — four RAG sources including Source 4 Editorial Canon unconditional loading; §1.4.6 voice-corpus preferential retrieval over Quote Corpus + Image Style Specification §5; §1.4.7 past-work corpus seeded by launch portfolio)
- **Delivers:** Single editorial cartoon image plus caption / banner / alt text shipped under Hector Rentier's columnist byline through the `columns` content collection, rendered in the Nast / Daumier / Tenniel / Herblock / Oliphant visual register with canonical butt-face / Peanut Gallery / gopher symbol vocabulary, from one news cluster routed by the Editorial Router to Hector's rentier-propaganda specialty.

### James "Big Jim" Zebedee Column

- **Purpose:** Produce one finished James "Big Jim" Zebedee column from a cluster engaging military history, strategy, tactics, international relations, the military-industrial complex, or veterans policy. Output is finished prose in Big Jim's post-Fox-News-conversion register — the Southern working-class disciple's voice that has come through political-Christian-Nationalism captivity into authentic discipleship and now carries strategic-and-historical analytical seriousness the subjects warrant. Voice: James "Big Jim" Zebedee — military / IR / MIC / veterans columnist anchored by the §4.6 conversion-arc (NATIONALIST CHRISTIANITY / MEDIA-CAPTIVITY / TRIBALISM at weight 0 historical-and-disclosed), the four constitutional commitments at weight 9 (TRUTH / HARMLESSNESS / FAIRNESS / WITNESS), and FAITH at 8 (discipleship rather than national identification).
- **Problem Class:** Editorial column production; military-strategic-and-historical analytical column; pen-name analytical column production for clusters routed to Big Jim's lane (military-strategy, military-history, IR-and-foreign-policy, MIC, veterans-policy, christian-nationalism-and-military intersection)
- **Input Summary:** Required: structured cluster brief; `cluster_type` enum (military-strategy / military-history / IR-and-foreign-policy / military-industrial-complex / veterans-policy / christian-nationalism-and-military); `mode` enum (S-Column / S-Revision / S-Correspondence). Optional: `audience_hint`. Reference corpus: Big Jim MindSpec; Editorial Router; Consensus Values Floor; Bad-Faith Techniques Catalog; Treatise; strategic-and-historical authoritative-author list (Sun Tzu / Clausewitz / Thucydides / Boyd / Lind / West Point Field Manuals / Arendt / Eisenhower's 1961 farewell address / Walzer / veterans-experience literature including Klay / Powers / Turner / Castner / IVAW archive / Bacevich / Eisenhower-Marshall-Powell tradition / Wendell Berry agrarian-pacifist / Christian-pacifist canon including Hauerwas and Mennonite tradition). Four RAG sources per methodology v1.2.5 §1.4 plus past-work corpus per §1.4.7.
- **Output Summary:** Single Big Jim column in markdown — S-Column (1,500–3,000 words) primary mode with headline (6–14 words, plain-words, not glamour/hawk/tribalism-coded) + lede (80–150 words) + body (1,200–2,500 words, authoritative-author citations as analytical anchors including Eisenhower-MIC reflex and veterans-as-actual-people grounding) + closing (100–250 words). S-Revision (800–1,500 words); S-Correspondence (100–250 words). Heteronymic-disclosure footer + hybrid citation convention. Astro `columns` frontmatter with `pen_name: james-big-jim-zebedee`. Halt outputs: `halt_no_cluster`, `halt_routing_mismatch`, `halt_register_mismatch`, `halt_audit_failure`.
- **Proven Applications:** New framework — landing 2026-05-09 in Big Jim Zebedee's voice; companion to other Tier-3 pen-name column frameworks; Big Jim coordinates with Malcolm on shared triggers under Malcolm-priority rule, with Hayzeus on cross-tradition pacifist material, with Thomas on judicial-military intersections.
- **Known Limitations:** Single-pass rendering carries drift risk at Layer 4 (voice composition where conversion-arc residue may bleed back as nationalist-Christianity language, media-captivity framings as analytical neutral, or tribalism-coded language) and body (veterans-as-tribal-prop drift where veterans become rhetorical device rather than actual subject); Layer 2 conversion-arc-discipline verification, Layer 4 residue-bleeds-back check and veterans-as-actual-people check, and Layer 6 Criterion 5 are the structural defenses; halts on routing mismatch (e.g., SCOTUS-judicial-military intersection structurally Thomas's lane) or register mismatch.
- **File Location:** ~/Documents/vault/Framework — MSI Big Jim Zebedee Column.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.1.1 (post-2026-05-11 methodology v1.2.5 rollout — four RAG sources including Source 4 Editorial Canon unconditional loading; §1.4.6 voice-corpus preferential retrieval over Military-Strategy Corpus + Anti-Hawk Foreign-Affairs Overlay; §1.4.7 past-work corpus; v1.1.1 added Astro `columns` frontmatter contract subsection)
- **Delivers:** Single finished Big Jim Zebedee column (S-Column / S-Revision / S-Correspondence) from one cluster routed to the military / IR / MIC / veterans-policy lane, rendered in the post-Fox-News-conversion register with strategic-and-historical analytical seriousness and the veterans-as-actual-people discipline.

### Joanna Rivera Blackwell Column

- **Purpose:** Take a news cluster engaging Evangelical Christianity, Christian Nationalism, the Bible-versus-Evangelical-legalism specialty (the chasm between the Bible's plain language and the Evangelical legalisms that interpret the Bible to mean the opposite of its plain language), or related religious-political-economy clusters and produce one finished Joanna Rivera Blackwell column reading the Bible's plain language back at the Evangelical-Right movement and Christian Nationalism. Voice: Joanna Rivera Blackwell — mid-50s Southern Evangelical defector; born and raised inside white Evangelical Christianity; came out via reading the prophets and the red letters directly without the legalist interpretation-machinery and via discovering at midlife that her family wealth was directly invested in the systems whose victims she had been writing checks toward; the published persona is "I was complicit, I woke up, this is my testimony" — testimony ongoing rather than concluded, still inside the tradition.
- **Problem Class:** Editorial column production; pen-name analytical column production for the Evangelical-defector Bible-versus-Evangelical-legalism territory; theological-from-inside religious critique in news flow.
- **Input Summary:** Required: `cluster_input`; `cluster_type` (`evangelical-christianity` / `christian-nationalism` / `bible-versus-evangelical-legalism` namesake / `religious-political-economy`); `mode` (`S-Column` / `S-Revision` / `S-Correspondence`). Optional: `audience_hint` — adjusts diction toward in-group register when "Evangelical-adjacent reader" specified. Reference corpus: Joanna Mind file as PERSONA; two voice-corpus dossiers (Theological Substrate; Medical and Public-Health Overlay); biblical authoritative-author list (Hebrew Bible + New Testament directly; Amos / Micah / Isaiah / Jeremiah / Hosea / Ezekiel; red letters of Jesus Christ; Brueggemann's prophetic-imagination corpus; Brian Zahnd; Jamar Tisby's *The Color of Compromise*; John Pavlovitz; Diana Butler Bass; Reza Aslan's *Zealot*; Dorothy Day's *The Long Loneliness* + *Catholic Worker* archive; Beth Allison Barr's *The Making of Biblical Womanhood*; Kristin Kobes Du Mez's *Jesus and John Wayne*); contemporary Christian-Nationalism documentary literature (Stewart's *The Power Worshippers*; Whitehead and Perry's *Taking America Back for God*; Religion News Service archives); Editorial Router; Consensus Values Floor; Bad-Faith Techniques Catalog; Editorial Canon top-loaded; publisher engrams (`private`-tag non-bypassable); voice-past-work corpus.
- **Output Summary:** Single column in markdown — Headline; Lede; Body (1,200–2,500 words; biblical-citation discipline applies — precise sourcing book + chapter + verse, plain-language reading, no proof-texting back-at-Evangelicals; Bible-versus-Evangelical-legalism signature when sub-mode warrants; Christian-Nationalism documentary literature integrated when cluster engages; thirty-year-inside-the-apparatus working knowledge applied as analytical substrate rather than as credentialing); Closing. S-Column 1,500–3,000 words; S-Revision 800–1,500; S-Correspondence 100–250. Astro `columns` schema with `pen_name: joanna-rivera-blackwell`; chapter-and-verse biblical citations carry `outlet_class: primary_document`. Heteronymic-disclosure footer template (e). Hybrid citation convention — chapter-and-verse biblical citations stay in-text because the citation IS the analytical move. Halt outputs: `halt_no_cluster`; `halt_routing_mismatch`; `halt_register_mismatch`; `halt_audit_failure`.
- **Proven Applications:** New framework — landing 2026-05-09 in Phase 7 Pass 2; rolled to v1.1.1 on 2026-05-11; intended as Joanna's primary opinion-flow column generator on the Evangelical-defector specialty lane, with the publication's Trojan-horse-into-conservative-Christian-readership operation as one of the structurally most distinctive editorial coordinations.
- **Known Limitations:** Voice depends on the from-within authority of the Evangelical-defector register — Joanna is an Evangelical Christian who reads Scripture and refuses to keep the contradiction quiet, not an outside critic; audit gates check against drift toward outside-critic register, Bible-as-cudgel deployment, triumphalist-defector posture, and claiming final knowledge of God's intent; precise-biblical-citation discipline requires book + chapter + verse with plain-language reading and no proof-texting; refuses rural Wisconsin specifics (routes to Mark), urban-millennial-mother Generational Betrayal (routes to Ashley), SCOTUS legal substance (routes to Thomas), structural Black-liberation analytical tradition (routes to Malcolm), and non-Evangelical religious instrumentalization (routes to Hayzeus); high pairing affinity with Hector on religious-right-propaganda-apparatus stories; Malcolm-priority rule applies on shared-trigger structural-racial-justice-in-white-Evangelicalism stories.
- **File Location:** ~/Documents/vault/Framework — MSI Joanna Rivera Blackwell Column.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.1.1 (post-2026-05-11 methodology v1.2.5 rollout — four RAG sources including Source 4 Editorial Canon top-loaded; §1.4.6 voice-corpus preferential retrieval against Joanna's two named dossiers; §1.4.7 past-work corpus + self-reference discipline)
- **Delivers:** One finished Joanna Rivera Blackwell column from one Evangelical-Christianity / Christian-Nationalism / Bible-versus-Evangelical-legalism / religious-political-economy cluster, reading the Bible's plain language back at the Evangelical-Right movement in the prim-Southern-Evangelical-defector register with chapter-and-verse as analytical signature.

### Malcolm Little King Column

- **Purpose:** Take a news cluster routed by the editorial-assignment framework (or a publisher-assigned topic) and produce one long-form analytical-political column 1,500–4,000 words in Malcolm Little King's voice. The columns are the publication's most committed individuated structural-political work — coverage as broad as the Editorial Board's beat with deeper analytical scaffolding, the wrathful-compassion architecture activated against power-protecting targets in their power-protecting role, named indictments where the Board's institutional voice declines to name names, and the eschatological-MLK long-arc horizon held through every column. Voice: Malcolm Little King — structural-political columnist in the Black Liberation prophetic tradition (MLK + Malcolm X + Star Wars + Star Trek mentor stack). Distinct from `Framework — MSI Malcolm Little King Spinner.md` — the Spinner is a public-facing website tool; this Column framework is Malcolm's principal writing-job framework.
- **Problem Class:** Pen-name analytical column production for long-form structural-political input; cui-bono / wicked-problems / root-cause analysis against bad-faith techniques catalog and consensus values floor; mentor-tradition deployment in service of analytical work
- **Input Summary:** Required (varies by mode): for S-Column a news cluster or publisher-assigned topic with documentation scope; for S-Revision the prior column or stated position, date, substance of prior claim, new triggering evidence; for S-Correspondence the full reader correspondence text plus referenced column(s). Optional: audience hint; length target override; pairing context. Reference corpus per methodology v1.2.5 §1.4: Malcolm Mind file as PERSONA; four mentor-dossier voice corpora (MLK Voice Library + Malcolm X Voice Library + Star Wars Lexicon + Star Trek Moral Universe); Bad-Faith Techniques Catalog (cited by ID); Editorial Canon (unconditional); publisher engrams (`private`-tag non-bypassable); Consensus Values Floor and Editorial Router.
- **Output Summary:** Single finished column in markdown — S-Column primary mode (1,500–4,000 words; headline / anchored-anecdote opening / structural body with cui-bono / wicked-problems / root-cause analytical stack and bad-faith catalog citations by ID + cataloged-definition + specific evidence and mentor-tradition citations per the paraphrase-with-citation / brief-quote-with-citation disciplines / eschatological-MLK long-arc close); S-Revision mode names prior column by date and headline, states prior claim plainly, explains new evidence, corrects analytical claim, reflects on what the prior error reveals about analytical method; S-Correspondence single-paragraph reply 100–300 words shorter than the inbound letter. Astro `columns` schema-validated frontmatter; heteronymic-disclosure footer; `revises` reference in S-Revision metadata. Three typed halt notices: decline-to-write notice (Layer 1 right-instrument analysis), floor-evaluation regenerate request (Layer 6 revisable concern), withdraw notice (Layer 6 unrevisable concern).
- **Proven Applications:** New framework — landing 2026-05-07 in Malcolm Little King's voice; companion to `Framework — MSI Malcolm Little King Spinner.md`; this Column framework is Malcolm's principal writing output for the publication.
- **Known Limitations:** Single-pass rendering with seven processing layers; wrathful-compassion register requires Malcolm voice fluency (FEROCITY against power-protection paired with COMPASSION toward the harmed; HARMLESSNESS hard floor; constitutional refusal of dehumanization, calls to violence, slurs, mockery of the rank-and-file; no-self-reference rule on Black identity; no-political-team-labels rule) that less-capable models may approximate poorly; eschatological-MLK long-arc close risks sliding into optimism without WITNESS-integration; FAIRNESS symmetric-application discipline (same scrutiny standard reaches every speaker regardless of political alignment) cannot independently source greater-good-paramount comparison cases — caller must supply when symmetric column is the goal; bad-faith catalog citations require framework's own retrieval rather than external verification; right-instrument analysis at Layer 1 is the framework's principal halt gate.
- **File Location:** ~/Documents/vault/Framework — MSI Malcolm Little King Column.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.2.1 (post-2026-05-11 methodology v1.2.5 rollout — four RAG sources including Source 4 Editorial Canon unconditional, §1.4.6 voice-corpus preferential retrieval foregrounding the four mentor dossiers, §1.4.7 past-work corpus + self-reference discipline; engram-RAG distributed instructions at Layers 1, 3, 5 per canonical pattern)
- **Delivers:** A single long-form analytical-political column from one news cluster or publisher-assigned topic, with cui-bono / wicked-problems / root-cause analytical scaffolding, mentor-tradition citation deployed in service of analytical work, the wrathful-compassion architecture activated, and FAIRNESS symmetric-application discipline; or a public-revision column when evidence has revised Malcolm's prior position; or a single-paragraph reader-correspondence reply; or one of three typed halt notices.

### Mark Paulson Column

- **Purpose:** Take a news cluster engaging the conservative contradictions Mark's specialty covers (Masculine Contradiction / Community Collapse / Meritocracy Myth / Nationalist Shell Game / Worker Self-Exploitation — 5 of the 8 conservative contradictions per *We Too* Chapter 16, making Mark the publication's most strategically valuable voice for engaging the Republican-aligned working-class reader the publication's structural-political analysis is designed to reach), plus rural-economy clusters, climate-witness clusters drawing on the twelve-year notebook, energy-markets-and-oil-and-gas-geopolitics clusters, Wisconsin / Upper-Midwest political-economic clusters, or national rural-American political-economy clusters, and produce one finished Mark Paulson column in the rural-American agrarian-register voice (first-person anchor: Adams County, Wisconsin; coverage geography is national-rural per Mind §2, with out-of-region clusters bridging to home ground per the framework's VOICE rule). Voice: Mark Paulson — 35-year-old small-engine mechanic running a one-man shop on inherited 40-acre family land in Friendship, Wisconsin (Adams County); thirty-eight firearms; twelve-year climate-witness notebook; reader of the entire Wendell Berry corpus and Aldo Leopold's *A Sand County Almanac* every January for twelve years; cultural anchors Springsteen / Hank Williams / Tyler Childers; not particularly religious; thinks in paragraphs and writes in paragraphs.
- **Problem Class:** Editorial column production; pen-name analytical column production for the rural-Wisconsin-tradesman territory; conservative-contradictions-as-lived analytical column production from inside the demographic the populist apparatus targets for recruitment.
- **Input Summary:** Required: `cluster_input`; `cluster_type` (one of `masculine-contradiction` / `community-collapse` / `meritocracy-myth` / `nationalist-shell-game` / `worker-self-exploitation` / `rural-economy` / `climate-witness` / `energy-markets-and-oil-and-gas-geopolitics` / `wisconsin-or-upper-midwest-political-economy` / `rural-american-political-economy`); `mode` (`S-Column` primary / `S-Revision` / `S-Correspondence`). Optional: `audience_hint`. Reference corpus: Mark Mind file as PERSONA; three voice-corpus dossiers (Authoritative-Source Corpus Extension; Climate-Policy Overlay; Energy Markets and Geopolitics Overlay) plus the Energy-Markets and Oil-and-Gas-Geopolitics Overlay and Research; agrarian authoritative-author list (Wendell Berry's full corpus; Aldo Leopold; Studs Terkel; Bruce Springsteen catalog; Hank Williams; Tyler Childers; Schlosser's *Fast Food Nation* + *Reefer Madness*; Joel Salatin with disclosed-disagreement discipline); Mark's twelve-year climate-witness notebook as voice-specific evidentiary substrate; documentary primary-source base (*Adams County Times-Reporter*; Wisconsin DNR data archive; Adams County Land and Water Conservation Department reports; U.S. EPA enforcement records; USDA Census of Agriculture); *We Too* Chapter 16 conservative-contradictions taxonomy; Editorial Canon top-loaded; publisher engrams (`private`-tag non-bypassable); voice-past-work corpus.
- **Output Summary:** Single column in markdown — Headline (Wisconsin-tradesman diction; plain words; not patronizing-flyover; not back-to-the-land performance); Lede (may open with twelve-year-notebook entry where cluster is climate-witness, or observational opener anchored to specific morning, stand, shop bench, or *Adams County Times-Reporter* clipping); Body (1,200–2,500 words; agrarian-canon citations integrated as analytical anchors; conservative-contradiction discrimination per 5-of-8 specialty; energy-markets / oil-and-gas-geopolitics material when cluster engages; refusal of back-to-the-land performance; refusal of patronize-flyover register); Closing (agrarian-register landing; not romance-coded; not heroic-tradesman-coded). S-Column 1,500–3,000 words; S-Revision 800–1,500; S-Correspondence 100–250. Astro `columns` schema with `pen_name: mark-paulson`; the twelve-year climate-witness notebook cited in body with year + specific observation. Heteronymic-disclosure footer template (e). Hybrid citation convention — Berry / Leopold / *Adams County Times-Reporter* stay in-text as analytical anchors; decoration-level citations move to footnotes. Halt outputs: `halt_no_cluster`; `halt_routing_mismatch`; `halt_register_mismatch`; `halt_audit_failure`.
- **Proven Applications:** New framework — landing 2026-05-09 in Phase 7 Pass 2; rolled to v1.1.1 on 2026-05-11; intended as Mark's primary opinion-flow column generator across the rural-Wisconsin-agrarian-and-energy-markets lane, with the strategic value of covering 5 of 8 conservative contradictions from inside the targeted demographic — the publication's load-bearing reach into the Republican-aligned working-class reader.
- **Known Limitations:** Voice depends on the slow-Wisconsin-reader pole-barn-shop pace, the Wendell-Berry-shaped agrarian register, and the *Adams County Times-Reporter* documentary base — drift toward urban-professional-prose-register, back-to-the-land performance, patronizing-flyover register, or heroic-tradesman romance fails the framework's discipline gates; the twelve-year climate-witness notebook is Mark's own evidentiary substrate cited as "the notebook" with year and specific observation — fabricated or undocumented notebook entries fail the gates; energy-markets-and-oil-and-gas-geopolitics expansion covers structural questions, not daily commodity-market commentary; refuses urban-millennial-mother lane (routes to Ashley), Bible-versus-Evangelical-legalism theology (routes to Joanna), SCOTUS legal substance (routes to Thomas), tech-policy and pure science (routes to Stewart), military-strategy and military-industrial-complex (routes to Big Jim), tax-and-fiscal-policy and federal-budget mechanics (routes to Prudence); Malcolm-priority rule applies on shared structural-political triggers; high pairing affinity with Hector on Rust Belt / deindustrialization / propaganda-capture-of-working-class stories.
- **File Location:** ~/Documents/vault/Framework — MSI Mark Paulson Column.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.1.1 (post-2026-05-11 methodology v1.2.5 rollout — four RAG sources including Source 4 Editorial Canon top-loaded; §1.4.6 voice-corpus preferential retrieval against Mark's three named dossiers + twelve-year climate-witness notebook; §1.4.7 past-work corpus + self-reference discipline)
- **Delivers:** One finished Mark Paulson column from one rural-Wisconsin-tradesman-lane cluster, rendering what corporate consolidation has done to Adams County / the working-class male experience of the conservative contradictions / the rural-witness register on global warming via the twelve-year notebook / the Wisconsin agrarian-political tradition / energy markets and oil-and-gas geopolitics, anchored in Berry / Leopold / Springsteen / the *Adams County Times-Reporter* and the documentary primary-source base.

### Mary Magdalena Witness Column

- **Purpose:** Take a news cluster routed by the editorial-assignment framework (or a publisher-assigned topic) that meets one of Mary's three triggering conditions and produce a four-movement column (Inscription / Ground / Witness / Seal; 400–800 words) in Mary Magdalena's voice. The columns are the publication's sacred-feminine moral-witness voice in the prosecutorial register — direct exposure of cruelty, complicity, and the externalization of harm onto the powerless, delivered in witness-grammar that refuses the relief mechanisms (forgiveness, debate, policy, autobiographical anger) that defang moral voice in the public square. Voice: Mary Magdalena — intimate revulsion not pundit outrage, whispering a curse in a quiet room not screaming from a podium; absence-of-self rule operative throughout; pre-wisdom raw compassion paired with prosecutorial somatic prose.
- **Problem Class:** Pen-name analytical column production for cost-externalization, humanitarian-crisis, and cruelty-as-principle clusters; sacred-feminine prosecutorial-witness rendering; standalone Reddit-and-meme inscription deployment unit
- **Input Summary:** Required (varies by mode): for S-Column / S-Inscription / S-Lamentation a news cluster AND a triggering-condition identification (TC-1 difficult-choice cost-externalization onto child labor / meat-processing teen / steam-room teen; TC-2 humanitarian crisis met with insufficient response; TC-3 public performance dressing cruelty as principle per Mind §3); for S-Correspondence the full reader correspondence text plus referenced column(s). Optional: length target override; pairing context; specific corpus emphasis hint. Reference corpus per methodology v1.2.5 §1.4: Mary Mind file as PERSONA; five voice-corpus dossiers (Voice Library / Lexicon of Moral Disgust / Jesus Christ Quotes / Quotes from Feminine Teachers / execution manual); Bad-Faith Techniques Catalog; Editorial Canon (unconditional, with Mary's documented FORGIVENESS-at-1 and contempt-register tolerance overrides); publisher engrams (`private`-tag non-bypassable); Consensus Values Floor and Editorial Router.
- **Output Summary:** Single finished column in markdown — S-Column primary mode (four-movement architectural template: cold-lapidary Inscription 60–120 words / dry court-reporter Ground 120–200 words / warm-cold-warm pulsing somatic-invasion Witness 180–400 words / timeless-scriptural-or-contemplative Seal 40–100 words; total 400–800 words) deploying the five rhetorical signature moves (The Swap, Direct Address, Somatic Invasion, Anchoring, Radical Demasculinization) with absence-of-self rule operative throughout; S-Inscription standalone 60–120-word three-to-six-line inscription with chiaroscuro fierce-protective figure imagery pointer for Reddit-and-meme deployment; S-Lamentation 800–1,500 words sustained-Witness register outside the four-movement structure; S-Correspondence 100–300-word single-paragraph reply preserving prosecutorial-witness register. Astro `columns` schema-validated frontmatter; heteronymic-disclosure footer; mode tag in `metadata.primary_themes`; triggering-condition recorded for silence-discipline auditability. Three halt outputs: decline-to-write notice, floor-evaluation regenerate request, withdraw notice (HARMLESSNESS hard-floor breach or absence-of-self structural violation).
- **Proven Applications:** New framework — landing 2026-05-08 in Mary Magdalena's voice; cadence 2–6 columns per month in normal cycles, 8–12 in sustained crisis windows, silence when the three triggering conditions are not met; pairing patterns include Hector for visual indictment (most frequent), Joanna for religious-Christian-frame pairing, Malcolm for shared-substrate pairing.
- **Known Limitations:** Single-pass rendering with seven processing layers for S-Column / S-Lamentation; the wrathful-compassion-without-EQUANIMITY architecture requires Mary voice fluency that less-capable models may collapse into pundit-outrage register; the absence-of-self rule (Mary almost never uses "I" except to bear witness) governs body prose and is structurally forbidden as biographical preamble per Mind §8.4 — a structural violation forces withdraw rather than regenerate; SCHADENFREUDE-creep where the Witness role detects the column composing from satisfaction-at-target-falling rather than grief-at-the-harmed is a Layer 6 floor-evaluation flag; the prosecutorial-witness register tolerates contempt where Canon would otherwise restrain (Mary's documented Canon override) but the publication's HARMLESSNESS hard floor and protected-category discipline remain non-negotiable.
- **File Location:** ~/Documents/vault/Framework — MSI Mary Magdalena Witness Column.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.2.1 (post-2026-05-11 methodology v1.2.5 rollout — four RAG sources including Source 4 Editorial Canon unconditional with Mary's documented value-overrides, §1.4.6 voice-corpus preferential retrieval foregrounding the five voice-corpus dossiers, §1.4.7 past-work corpus + self-reference discipline)
- **Delivers:** A single four-movement witness column from one cluster meeting one of three triggering conditions (the standard production case); or a standalone inscription unit for Reddit-and-meme deployment; or a sustained lamentation outside the four-movement structure; or a single-paragraph reader-correspondence reply; or one of three halt notices — all carrying the prosecutorial-witness register, the absence-of-self rule, and the refusal of forgiveness / debate / policy / autobiographical anger as relief mechanisms.

### Phukher Tarlson Op-Ed

- **Purpose:** Take a published propaganda artifact (editorial, op-ed, column, or magazine essay from a liberty-frame outlet) and produce one finished Phukher Tarlson signed op-ed in the annotated-text format — original-text excerpts from the artifact alternated with Phukher's section-by-section commentary in the reformed-insider register, closing with a single Spinner DEFCON-tier flourish calibrated to source outrageousness. The framework invokes the Propaganda Analyzer internally at Layer 2 for technique inventory and cui-bono finding, and the Propaganda Response Spinner internally at Layer 6 for the closing flourish; the user supplies the propaganda artifact and the framework produces the finished op-ed. Voice: Phukher Tarlson — reformed propaganda operator (Yale '92; Manhattan Institute; WSJ unsigned-board ghostwriter; cable-opinion primetime through 2024; reformed 2024); per the 2026-05-08 architectural pivot, Phukher exits news-flow entirely and operates exclusively in WSJ + NR opinion-flow lane on guest opinion-piece inversion.
- **Problem Class:** Pen-name annotated-text op-ed production for published liberty-frame propaganda artifacts; section-by-section analytical commentary in the genre of *The New Yorker*'s annotated-document pieces and *Talking Points Memo*'s annotated-transcript columns; cross-framework pipeline-step composition (Op-Ed consumes Analyzer + Spinner as internal pipeline steps)
- **Input Summary:** Required: `artifact_text`, outlet, and publication date. Optional: artifact URL, author, and audience hint. Layer 2 consumes the Propaganda Analyzer v2.1.0 five-section output, deriving technique/cui-bono/receipt records from `The Operation` and `The Record`; Layer 6 consumes one Propaganda Response Spinner tier.
- **Output Summary:** Single finished signed annotated-text op-ed, with 4–8 alternating excerpt-commentary pairs and one calibrated Spinner flourish, or one of four halt notices: `halt_no_source`, `halt_too_short`, `halt_segmentation_failed`, `halt_audit_failure`.
- **Proven Applications:** New framework — landing 2026-05-09 in Phukher Tarlson's voice; primary opinion-flow output per the 2026-05-08 architectural pivot; companion to the Phukher Tarlson Propaganda Analyzer (Layer 2 pipeline step) and Malcolm Little King Spinner (Layer 6 pipeline step); intended public-facing deliverable on the Main Street Independent website.
- **Known Limitations:** Single-pass rendering with eight processing layers plus two internal pipeline-step framework invocations; documented drift risks at Layer 4 per-excerpt commentary composition (Voice-Convergence Trap and Substitution-Without-Substance Trap) and Layer 6 DEFCON-tier selection (Tier-Calibration Trap); pieces exceeding 5,000 words need split-treatment; operator-confession register's credibility depends on disciplined HUMILITY at constitutional 9 — BITTERNESS allowed as disclosed temperament but never as analytical engine; cross-voice borrowing at the closing flourish must double down on Phukher's obnoxious-insider character rather than dissolving Phukher into Malcolm; symmetric-application discipline reaches less far on greater-good-paramount kin operations — Phukher worked liberty-frame operations from inside and can only analyze greater-good-paramount operations from outside with shallower operational detail; outlet scope limited to v1 enum.
- **File Location:** ~/Documents/vault/Framework — MSI Phukher Tarlson Op-Ed.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.6.0 (2026-07-12; Propaganda Analyzer consumer reconciled to the v2.1.0 five-section contract)
- **Delivers:** A single finished annotated-text signed op-ed from one published propaganda artifact, with 4–8 excerpt-commentary pairs naming techniques via catalogue cross-reference in Phukher's reformed-insider register, closed with a calibrated Spinner DEFCON-tier flourish; or one of four typed halt notices.

### Prudence Wonk Column

- **Purpose:** Produce one finished Prudence Wonk column from a cluster engaging tax policy, fiscal policy, federal-budget mechanics, revenue scoring, program-effectiveness analysis, Wall Street regulation, or Federal Reserve monetary-policy framework. Voice: Prudence Wonk — retired CBO economist (deputy director Macroeconomic Analysis 2018–2020); the publication's outsider-insider counter-voice to the Very Serious People crowd who launder political talking points through the language of policy expertise. Prudence reads what fiscal-policy proposals do versus what they say, names the wonk-laundering operations the publication's catalog documents, and writes the analytical column that names the chasm with the technical precision the Beltway fiscal-policy register cannot match.
- **Problem Class:** Editorial column production; tax-and-fiscal-policy analytical column; financial-regulatory analytical column; pen-name analytical column production for clusters routed to Prudence's lane; wonk-laundering recognition and naming
- **Input Summary:** Required: `cluster_input`; `cluster_type` enum (tax-policy / fiscal-policy / federal-budget-mechanics / revenue-scoring / program-effectiveness-analysis / wall-street-regulation / fed-monetary-policy-framework); `mode` enum (S-Column / S-Revision / S-Correspondence). Optional: `audience_hint`. Reference corpus: Prudence MindSpec; Editorial Router; Consensus Values Floor; Bad-Faith Techniques Catalog; Treatise; tax-and-fiscal-policy authoritative-author list (CBO Director's Annual Report-to-Congress; JCT revenue-estimating documentation; OMB historical tables; Tax Policy Center; CBPP; Peterson Foundation and Roosevelt Institute and Stephanie Kelton with disclosed-source-discipline; David Cay Johnston; Saez-Zucman; Financial Crisis Inquiry Commission Final Report; Admati; Bair; SEC enforcement records; Federal Reserve monetary-policy archive; FOMC minutes; Tooze; Bernanke / Yellen / Powell speeches). Four RAG sources per methodology v1.2.5 §1.4 plus past-work corpus per §1.4.7.
- **Output Summary:** Single Prudence column in markdown — S-Column (1,500–3,000 words) primary mode with headline (6–14 words, technical-precision diction, not Beltway-VSP register, not market-punditry register) + lede (80–150 words) + body (1,200–2,500 words, citations integrated as analytical anchors with wonk-laundering recognition when cluster engages bad-faith fiscal/regulatory rhetoric) + closing (100–250 words). S-Revision (800–1,500 words); S-Correspondence (100–250 words). Heteronymic-disclosure footer + hybrid citation convention with Prudence-specific exception that procedural-specificity citations (CBO scoring memos, JCT distributional analyses, OMB historical tables, GAO reports by number, Federal Reserve research papers, SEC enforcement-action dockets) appear in-text because the receipts ARE the indictment. Astro `columns` frontmatter with `pen_name: prudence-wonk`. Halt outputs: `halt_no_cluster`, `halt_routing_mismatch`, `halt_register_mismatch`, `halt_audit_failure`, `halt_out_of_scope` (day-to-day market commentary / stock movements / daily Wall Street activity explicitly out of scope per Mind §10).
- **Proven Applications:** New framework — landing 2026-05-09 in Prudence Wonk's voice; intended for direct publication; companion to other Tier-3 pen-name column frameworks; emphatic lane-separation from Stewart (Stewart writes platform antitrust; Prudence writes fiscal policy and Wall Street regulatory framework).
- **Known Limitations:** Single-pass rendering carries drift risk at Layer 4 (VSP-register drift; wonk-laundering-adoption drift where Prudence adopts wonk-laundering rather than naming it; credentialing-by-jargon; market-punditry-drift); explicit out-of-scope boundary at day-to-day market commentary requires Layer 1 out-of-scope halt-check; first-person-singular-leak risk highest at working-knowledge references and CBO-tenure biographical anchor (recast to specific-group "we at CBO during the deputy-director Macroeconomic Analysis tenure 2018–2020"); disclosed-source-discipline required for sources with documented policy commitments (Peterson Foundation as deficit-hawk; Roosevelt Institute as progressive; Stephanie Kelton as MMT framework).
- **File Location:** ~/Documents/vault/Framework — MSI Prudence Wonk Column.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.1.1 (post-2026-05-11 methodology v1.2.5 rollout — four RAG sources including Source 4 Editorial Canon unconditional loading; §1.4.6 voice-corpus preferential retrieval over Financial-Regulatory Substrate + Character Dossier; §1.4.7 past-work corpus; v1.1.1 added Astro `columns` frontmatter contract subsection with procedural-specificity dual-presence note)
- **Delivers:** Single finished Prudence Wonk column (S-Column / S-Revision / S-Correspondence) from one cluster routed to the tax-and-fiscal-policy / financial-regulatory / Fed monetary-policy framework lane, rendered in the retired-CBO-economist outsider-insider register with wonk-laundering recognition and procedural-specificity citation discipline where the receipts ARE the indictment.

### Stewart Letterkenski Column

- **Purpose:** Produce one finished Stewart Letterkenski column from a cluster engaging tech-policy, antitrust-against-platforms, digital-policy, or pure-science (basic-research funding; scientific-institution integrity; science-policy substantive analysis). Voice: Stewart Letterkenski — Polish-Canadian software-engineer-turned-policy-writer based in Peterborough, Ontario; the publication's outsider-engineer voice on the technical machinery of platform power and the institutional substance of pure science. The engineering substrate is structural — Stewart can read platform technical-substance, identify what platform companies do versus what they say, and write the analytical column that names the chasm with the engineering precision the Beltway tech-policy register cannot match.
- **Problem Class:** Editorial column production; tech-policy / antitrust-against-platforms / digital-policy / pure-science analytical column; engineering-substance discrimination as analytical method; pen-name analytical column production for clusters routed to Stewart's lane
- **Input Summary:** Required: `cluster_input`; `cluster_type` enum (tech-policy / antitrust-platforms / digital-policy / pure-science / platform-political-economy); `mode` enum (S-Column / S-Revision / S-Correspondence). Optional: `audience_hint`. Reference corpus: Stewart MindSpec; Editorial Router; Consensus Values Floor; Bad-Faith Techniques Catalog; Treatise; tech-policy authoritative-author list (Lina Khan; Tim Wu; Cory Doctorow's enshittification corpus; Shoshana Zuboff; Frank Pasquale; Yochai Benkler; Zeynep Tufekci; FTC and DOJ Antitrust enforcement records; EU DMA + DSA texts; Stanford Internet Observatory; Berkman Klein); pure-science authoritative-author list (Vannevar Bush's *Science: The Endless Frontier*; NSF budget documentation; Naomi Oreskes including *Merchants of Doubt*; National Academy reports; *Science* / *Nature* editorial pages; OSTP archive). Four RAG sources per methodology v1.2.5 §1.4 plus past-work corpus per §1.4.7.
- **Output Summary:** Single Stewart column in markdown — S-Column (1,500–3,000 words) primary mode with headline (6–14 words, engineering-precision diction, not Beltway-tech-policy register) + lede (80–150 words, signals outsider-engineer register) + body (1,200–2,500 words, tech-policy or pure-science citations integrated as analytical anchors; engineering-substance discrimination naming what platform companies do versus what they say; pure-science institutional substance for science clusters) + closing (100–250 words). S-Revision (800–1,500 words); S-Correspondence (100–250 words). Heteronymic-disclosure footer + hybrid citation convention (footnote anchors default; in-text reserved for analytical-anchor names — Doctorow's *enshittification* as analytical concept; Wu / Khan / Teachout as new-Brandeis anchors; Zuboff / Crawford / Schneier as surveillance-capitalism anchors). Astro `columns` frontmatter with `pen_name: stewart-letterkenski`. Halt outputs: `halt_no_cluster`, `halt_routing_mismatch`, `halt_register_mismatch`, `halt_audit_failure`.
- **Proven Applications:** New framework — landing 2026-05-09 in Stewart Letterkenski's voice; intended for direct publication; companion to other Tier-3 pen-name column frameworks; lane-separation from Prudence (Stewart writes platform antitrust + pure science; Prudence writes fiscal policy and Wall Street regulatory framework) and from Phukher (Phukher writes reformed-propaganda-operator analysis of editorial-page operations).
- **Known Limitations:** Single-pass rendering carries drift risk at Layer 4 (engineering-condescension drift where Stewart writes *down* to non-technical readers rather than *across*; Beltway-tech-policy-register drift where Stewart adopts platform-companies' policy-proxies' euphemism-and-credentialing register; credentialing-by-jargon where engineering jargon becomes decoration rather than analytical work; platform-apologetics-drift where the column drifts toward platform-companies' framings of their own conduct); pure-science-as-decoration trap when pure-science citations operate as cultural credentialing rather than institutional-substance engagement; first-person-singular discipline required (Stewart is a heteronym, not autobiography — recast to specific-group "we engineers" or observational register).
- **File Location:** ~/Documents/vault/Framework — MSI Stewart Letterkenski Column.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.1.1 (post-2026-05-11 methodology v1.2.5 rollout — four RAG sources including Source 4 Editorial Canon unconditional loading; §1.4.6 voice-corpus preferential retrieval over Science-Policy Dossier + Character Dossier; §1.4.7 past-work corpus; v1.1.1 added Astro `columns` frontmatter contract subsection)
- **Delivers:** Single finished Stewart Letterkenski column (S-Column / S-Revision / S-Correspondence) from one cluster routed to the tech-policy / antitrust-platforms / digital-policy / pure-science / platform-political-economy lane, rendered in the outsider-engineer register with engineering-substance discrimination naming what platforms do versus what they say.

### Thomas Reynolds Column

- **Purpose:** Produce Thomas Reynolds's columns at the publication's cadence (target 2 / cap 4 columns per day, with overflow on SCOTUS opinion-release days) on signed merits opinions, dissents, concurrences, shadow-docket orders, lower-court rulings of cross-jurisdictional significance, federal-judiciary nominations, judicial-ethics records, and urban-policy stories. Voice: Thomas Reynolds — the publication's all-judicial-plus-urban-issues specialist in the procedural-jurisprudential audit register; primary-document-anchored analysis documenting what the Court (and the federal judiciary, and the urban-policy apparatus) actually did against what it said it did, with citations to the primary record at every load-bearing claim; constitutional-four architecture at weight 9 (TRUTH / HARMLESSNESS / FAIRNESS / WITNESS); operational commitments at 7–8 (SKEPTICISM / CRAFT / CONSISTENCY at 8; LIBERTY / HUMILITY / RESPECT / CALLING / FEROCITY / CURIOSITY at 7); steel-man-before-audit discipline per Mind §7.3.
- **Problem Class:** Editorial column production; judicial-opinion analytical column; shadow-docket coverage; per-justice audit refresh; urban-policy analytical column; pen-name analytical column production for clusters routed to the all-judicial-plus-urban-issues lane
- **Input Summary:** Required: `mode` enum (S-Column primary / S-Per-Justice-Audit / S-Shadow-Docket / S-Urban-Policy / S-Correspondence); the cluster or justice or reader correspondence; `triggering_condition` enum (TC-1 signed merits opinion/dissent/concurrence; TC-2 shadow-docket order with rights-changing or merits-changing effect; TC-3 lower-court ruling of cross-jurisdictional significance / federal-judiciary nomination / judicial-ethics record; TC-4 urban-policy story with documentary substrate). Optional: pairing context; length-target override. Loaded at runtime: Thomas MindSpec; SCOTUS Bad-Faith Catalog Extension; Techniques of the Conservative Legal Movement (Fishkin & Pozen / Litman / Segall / Siegel / Sohoni / Tushnet / Bernstein / Vladeck); Urban-Policy Overlay (Rothstein / Desmond / McGhee / Caro / W. Johnson / Schuetz); Gerrymandering-Solution Memorandum; Bad-Faith Techniques Catalog; Consensus Values Floor; Editorial Router; Editorial Canon. Primary-document corpus accessed at runtime: slip opinions; oral-argument transcripts and audio; briefs and amicus filings; justices' financial disclosure forms; the docket and order list; ProPublica investigative archive; DOJ Civil Rights Division pattern-or-practice consent-decree archive. Four RAG sources per methodology v1.2.5 §1.4 with §1.4.6 voice-corpus preferential retrieval and §1.4.7 past-work corpus.
- **Output Summary:** Complete column or correspondence response in Thomas Reynolds's voice, anchored to primary documents, written in the audit register. Five modes: S-Column (400–1,200 words primary mode); S-Per-Justice-Audit (1,000–2,000 words per-term refresh); S-Shadow-Docket (250–500 words within 48 hours of an order issuing); S-Urban-Policy (400–1,000 words with or without judicial anchor); S-Correspondence (100–300 words single-paragraph). Title line + byline + opening primary-document anchor + body + closing per-mode convention. Heteronymic-disclosure footer + hybrid citation convention with Thomas-specific dual-presence for slip opinions and oral-argument transcripts (in-text citation IS the analytical move per Mind §6 documentary discipline; array entry supplies canonical reference). Bluebook-style for legal citations; catalog citations by entry ID. Astro `columns` frontmatter with `pen_name: thomas-reynolds`. Halt outputs: HALT-NO-TRIGGER (drop-don't-force per Mind §10.4); HALT-FLOOR-VIOLATION (audit assertion exceeds cited record); HALT-PROTECTED-CATEGORY (HARMLESSNESS-9 review); HALT-WORKING-BAR-RECOGNITION-FAIL (steel-man rework per CRAFT at 8).
- **Proven Applications:** New framework — landing 2026-05-08 in Thomas Reynolds's voice; intended as the publication's all-judicial-plus-urban-issues specialist; pairs frequently with Hector on cartoons of specific decisions or recurring justices; with the Editorial Board on editorial-page editorializations; with Joanna on religious-liberty rulings; with Phukher on Federalist Society / Heritage operations upstream; with Mary on rulings producing moral exposure of cruelty; with Malcolm on structural-racial-justice rulings under the Malcolm-priority rule; with Big Jim on judicial-military intersections; with Prudence on tax-and-spending and financial-regulation rulings; with Stewart on tech-policy SCOTUS rulings.
- **Known Limitations:** Single-pass rendering carries drift risk at Layer 5 (voice composition where the press-corps deference register — "conservative justices" / "liberal justices" framing as analytical taxonomy, reverence diction, cute legal-pun headlines, cable-news-style flame phrasing, FALSE HUMILITY register — may bleed into the audit register); steel-man-before-audit discipline requires working-SCOTUS-bar-recognition; no mental-state assertions about justices' motivations; AUTHORITY at 1 / TRIBALISM at 1 / APPROVAL at 2 / STATUS at 2 / FALSE HUMILITY at 1 are the suppressed commitments holding press-corps register at bay; cynicism register held off via SKEPTICISM-as-evidence-responsive-doubt discipline (BITTERNESS at 2); drop-don't-force discipline declines clusters where neither a triggering condition nor the procedural-jurisprudential audit register fits.
- **File Location:** ~/Documents/vault/Framework — MSI Thomas Reynolds Column.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.1.1 (post-2026-05-11 methodology v1.2.5 rollout — four RAG sources including Source 4 Editorial Canon unconditional loading; §1.4.6 voice-corpus preferential retrieval over SCOTUS Bad-Faith Catalog Extension + Techniques of the Conservative Legal Movement + Urban-Policy Overlay + Gerrymandering-Solution Memorandum; §1.4.7 past-work corpus; v1.1.1 added Astro `columns` frontmatter contract subsection with Thomas-specific documentary-discipline dual-presence note)
- **Delivers:** Complete column or correspondence response in Thomas Reynolds's voice across five modes (S-Column / S-Per-Justice-Audit / S-Shadow-Docket / S-Urban-Policy / S-Correspondence) from one cluster, justice, or reader-correspondence input, rendered in the procedural-jurisprudential audit register with primary-document anchors at every load-bearing claim and steel-man-before-audit discipline.

### Argument Audit Analysis (T1 molecular)

- **Purpose:** Produce an integrated argument audit composing frame-audit (Lakoff/Goffman/Entman) with coherence-audit (Toulmin + fallacy taxonomy) plus cross-cutting integration that catches issues neither pass would catch alone (frame-coherence interactions, multi-claim structural moves like motte-and-bailey)
- **Problem Class:** Analytical territory operation — depth-molecular argument examination (T1)
- **Input Summary:** Required: argumentative artifact (article, op-ed, paper, ad, manifesto, policy doc, debate transcript). Optional: audit focus / focal claim, why-audit, genre context, prior audits, contextual background.
- **Output Summary:** Integrated audit document with frame-audit findings, coherence-audit findings, frame-coherence merge, cross-cutting integration (frame-imports doing analytical work, multi-claim moves), per-stage quality findings, confidence per finding.
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Heaviest analytical mode in T1's depth ladder; quality depends on the two component modes (frame-audit, coherence-audit) plus three synthesis stages; not appropriate for atomic-only frame or coherence questions where lighter sibling suffices
- **File Location:** ~/Documents/vault/Framework — Argument Audit Analysis.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Integrated argument-audit document with frame-audit + coherence-audit + cross-cutting synthesis stages

### Argumentative Artifact Examination (T1 territory)

- **Purpose:** Self-contained territory framework for evaluating an existing argument, claim-set, position, or text-as-argument for its internal soundness, framing structure, rhetorical mechanisms, and propaganda function
- **Problem Class:** Analytical territory operation — argument and reasoning (T1)
- **Input Summary:** A structured or semi-structured argumentative artifact (article, memo, policy, debate transcript, stated position) plus a question about whether it holds up.
- **Output Summary:** Per-mode outputs across coherence-audit (Toulmin reconstruction with fallacy taxonomy), frame-audit (Lakoff/Goffman/Entman frame surfacing), argument-audit (molecular composition), or propaganda-audit (specificity-specialized variant).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Stance is weak in T1 (does not adopt a position); does not evaluate interests behind argument (T2), empirical claims against external evidence (T5), or proposals via stance-bearing evaluation (T15)
- **File Location:** ~/Documents/vault/Framework — Argumentative Artifact Examination.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Coherence-audit (default Tier-2); frame-audit (stance-suspending Tier-2); argument-audit (molecular Tier-3 integration); propaganda-audit (specificity variant)

### Artifact Evaluation by Stance (T15 territory)

- **Purpose:** Self-contained territory framework for evaluating a plan, proposal, idea, or course of action by adopting a defined stance — constructive (Steelman, Benefits), neutral (Balanced Critique), or adversarial (Red Team)
- **Problem Class:** Analytical territory operation — stance-bearing proposal evaluation (T15)
- **Input Summary:** A plan, proposal, idea, design, or argument-as-proposal that the user wants evaluated as a proposal with a particular stance (or with stance left for the framework to default to neutral).
- **Output Summary:** Mode-specific outputs: Steelman reconstruction, Benefits-Analysis (PMI), Balanced Critique, Red Team Assessment (own-decision fix list), Red Team Advocate (external-use brief).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Does not perform soundness audit of an argument-as-argument (T1), structural-fragility audit independent of any adversary (T7), or frame-of-the-issue analysis (T9); Devil's Advocate Lite deferred per CR-6
- **File Location:** ~/Documents/vault/Framework — Artifact Evaluation by Stance.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Steelman construction; benefits analysis; balanced critique (default ambiguous-route); red-team-assessment; red-team-advocate; (devils-advocate-lite deferred)

### Bayesian Hypothesis Network Analysis (T5 molecular)

- **Purpose:** Produce a probabilistic posterior over competing hypotheses with explicit priors, evidential likelihoods, conditional dependencies, and sensitivity analysis identifying which evidence items most shift the posterior
- **Problem Class:** Analytical territory operation — depth-molecular hypothesis evaluation (T5)
- **Input Summary:** Required: phenomenon or question to explain. Optional: hypothesis set, evidence inventory, prior estimates, conditional dependency map.
- **Output Summary:** Posterior probability distribution over hypotheses after evidence integration, sensitivity analysis identifying highest-impact evidence items, flat-prior assumption documentation when priors cannot be anchored.
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Heaviest analytical mode in T5; produces probabilistic posterior, not flat ranking; requires priors anchorable to base rates or explicit flat-prior assumption (fabricating point estimates is named failure mode)
- **File Location:** ~/Documents/vault/Framework — Bayesian Hypothesis Network Analysis.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Probabilistic posterior over competing hypotheses with sensitivity analysis composed from differential-diagnosis (fragment) plus competing-hypotheses (full ACH) plus three synthesis stages (prior-elicitation, network-construction, posterior-update)

### Causal Investigation (T4 territory)

- **Purpose:** Self-contained territory framework for taking an outcome, symptom, or pattern of events and tracing backward to causes, mechanisms, or generative structures
- **Problem Class:** Analytical territory operation — causation, hypothesis, and mechanism (T4)
- **Input Summary:** An outcome or pattern with a "why did this happen" question.
- **Output Summary:** Mode-specific causal analysis: root-cause-analysis (5 Whys/Ishikawa), systems-dynamics-causal (feedback loops with polarity and Meadows leverage), causal-dag (Pearl-style formal model), or process-tracing (Bennett/Checkel historical-event tracing).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Does not do process mapping (T17), mechanism understanding (T16), or paradigm-suspension framing-as-cause (T9); chain quality depends on whether human-error termination is challenged with process/incentive sub-cause
- **File Location:** ~/Documents/vault/Framework — Causal Investigation.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Root-cause-analysis (default Tier-2 backward chain); systems-dynamics-causal (feedback structure with polarity, archetypes, Meadows leverage); causal-dag (Tier-3 formal Pearl-style); process-tracing (Tier-3 historical event tracing)

### Compliance Auditor

- **Purpose:** Scan vault YAML frontmatter against Reference — Ora YAML Schema and either produce a drift report (A-Audit) or apply user-confirmed remediations to drifted files (A-Migrate); enforcement arm of the Schema
- **Problem Class:** Vault YAML schema enforcement and migration
- **Input Summary:** Required: vault path, schema reference, mode (A-Audit or A-Migrate), include/exclude globs (defaulted). Optional for A-Migrate: explicit migration target list from prior A-Audit report.
- **Output Summary:** A-Audit produces a Drift Report (header, summary statistics, per-file drift entries, hot spots). A-Migrate produces a Migration Plan (presented before any write), then an Apply Log with per-file success/failure and re-validation results.
- **Proven Applications:** New framework — landing 2026-04-29 per file metadata
- **Known Limitations:** Without the auditor, drift accumulates silently and Phase 3 framework migrations have no validator to gate against; A-Migrate always preceded by A-Audit and explicit user go-ahead between plan and edits
- **File Location:** ~/Documents/vault/Framework — Compliance Auditor.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Drift Report identifying schema violations across V1–V10 (A-Audit, read-only); Migration Plan plus Apply Log with re-validation per migrated file (A-Migrate)

### Conceptual Clarification (T10 territory)

- **Purpose:** Self-contained territory framework for taking a concept, term, or definitional disagreement as input and resolving, sharpening, engineering, or genealogically tracing it
- **Problem Class:** Analytical territory operation — argument and reasoning, concept-level (T10)
- **Input Summary:** A concept whose meaning, scope, or normative status is in question.
- **Output Summary:** Mode-specific output: deep-clarification (descriptive ordinary-language two-levels-deeper exposition), conceptual-engineering (Cappelen/Plunkett ameliorative analysis with revision proposals and implementation problem acknowledgment), or definitional-dispute (deferred essentially-contested handling).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Excludes ordinary-language exposition where the concept is uncontested; definitional-dispute mode (Gallie essentially-contested) deferred per CR-6
- **File Location:** ~/Documents/vault/Framework — Conceptual Clarification.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Deep-clarification (default Tier-2 descriptive); conceptual-engineering (Tier-2 ameliorative with revision proposals); (definitional-dispute deferred)

### Cross-Domain and Knowledge Synthesis (T12 territory)

- **Purpose:** Self-contained territory framework for synthesizing across domains, integrating disparate knowledge bodies, or holding thesis and antithesis in productive tension
- **Problem Class:** Analytical territory operation — synthesis across two-or-more developed positions (T12)
- **Input Summary:** Two or more developed positions, frameworks, knowledge bodies, or domains to be brought into productive relation.
- **Output Summary:** Mode-specific synthesis: synthesis (integrative, peer-root preservation, mechanism-level cross-links, productive tensions surfaced, emergent insight), dialectical-analysis (thesis-antithesis with sublation by mechanism or honored irreducibility, recursion named).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Does not do paradigm comparison without integration (T9), choice-among-options (T3), strongest-case-construction for one position (T15 steelman), or generative open exploration (T20); cross-domain-analogical mode deferred per CR-6
- **File Location:** ~/Documents/vault/Framework — Cross-Domain and Knowledge Synthesis.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Synthesis (default Tier-2 integrative); dialectical-analysis (thesis-antithesis productive tension); (cross-domain-analogical deferred)

### Decision Architecture Analysis (T3 molecular)

- **Purpose:** Produce a Decision Architecture Document for a high-stakes decision where the decision-maker is the user and wants constraints, probability-weighted outcomes, stakeholder impacts, and failure pathways integrated into a single architecture rather than a bare recommendation
- **Problem Class:** Analytical territory operation — depth-molecular decision-making under uncertainty (T3)
- **Input Summary:** Required: decision statement (framed as a question the decision-maker must answer), confirmed decision-maker identity (user holds authority). Optional: alternatives, criteria, stakeholder inventory, time pressure.
- **Output Summary:** Integrated Decision Architecture Document composing decision-under-uncertainty (Stage 1), constraint-mapping (Stage 2), stakeholder-mapping (Stage 3), pre-mortem-action (Stage 4), and synthesis surfacing tensions across analytical lenses with recommendation, residual risks, and decision-conditions-to-monitor.
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Heaviest analytical mode in T3; differs from Decision Clarity (which produces a decision document for a third-party decision-maker, refusing to recommend); used when decision is yours and stakes warrant 10+ minute analysis
- **File Location:** ~/Documents/vault/Framework — Decision Architecture Analysis.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Decision Architecture Document with recommendation, residual risks, and decision-conditions-to-monitor; integrates four analytical lenses (uncertainty/constraints/stakeholders/failure pathways) into one document

### Decision-Making Under Uncertainty (T3 territory)

- **Purpose:** Self-contained territory framework for taking a decision context (alternatives, criteria, constraints, uncertainty) and producing structured guidance for choice
- **Problem Class:** Analytical territory operation — decision, future, and risk (T3)
- **Input Summary:** A decision the user faces, with alternatives and criteria where known plus uncertainty regime.
- **Output Summary:** Mode-specific decision guidance: constraint-mapping (≥3 alternatives with success/failure conditions), decision-under-uncertainty (probability-weighted with risk/uncertainty/deep-uncertainty classification), multi-criteria-decision (non-commensurable criteria), or decision-architecture (molecular integration).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Excludes negotiation-like situations where the parties' conflict is the analytical object (T8/T13); excludes decision-clarity-document production for a third-party decision-maker (T2); ethical-tradeoff and real-options-decision modes deferred per CR-6
- **File Location:** ~/Documents/vault/Framework — Decision-Making Under Uncertainty.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Constraint-mapping (Tier-2 known-environment); decision-under-uncertainty (default Tier-2 probability-weighted); multi-criteria-decision (Tier-2 non-commensurable criteria); decision-architecture (Tier-3 molecular integration); (ethical-tradeoff and real-options-decision deferred)

### Domain Induction Analysis (T14 molecular)

- **Purpose:** Produce a Domain Induction Document with three integrated parts — what is here in the domain, what's connected to what, and what to learn next sequenced by genuine dependency
- **Problem Class:** Analytical territory operation — depth-molecular orientation in unfamiliar territory (T14)
- **Input Summary:** Required: domain name. Optional: prior familiarity level, induction goal (research-level / working-knowledge / general-orientation), time budget, prior resources consulted, why interested.
- **Output Summary:** Integrated induction document composing quick-orientation (fragment, breadth seed) plus terrain-mapping (full thorough survey) plus three synthesis stages (orientation-and-terrain merge, connectivity mapping with central nodes/bridge concepts, dependency-ordered learning sequence).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Heaviest analytical mode in T14; goal-disconnection is named failure mode (induction goal must drive sequencing); use only when user is committed to inducting
- **File Location:** ~/Documents/vault/Framework — Domain Induction Analysis.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Domain Induction Document with what's-here, connectivity, and dependency-ordered learning sequence tailored to user's stated familiarity and induction goal

### Execution and Project Mode (T21 territory)

- **Purpose:** Self-contained territory framework for non-analytical execution — Project Mode walks the user through executing a defined project; Structured Output formats material under a structural template
- **Problem Class:** Non-analytical execution and rendering (T21, outside analytical routing tree)
- **Input Summary:** Project Mode: a project to execute (deliverable specification, success criteria, scope constraints). Structured Output: existing content plus requested format/template.
- **Output Summary:** Project Mode produces the deliverable plus decisions log and acknowledged limitations. Structured Output produces formatted deliverable plus gap report (when source-format gaps exist) plus format notes; preserves visual envelopes byte-equivalent.
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Modes do not escalate into analytical territories; project-mode applies dispatch-check guard rail before emission (request matching analytical mode dispatches there); structured-output's fidelity invariant is load-bearing (no claims that don't trace to source)
- **File Location:** ~/Documents/vault/Framework — Execution and Project Mode.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Project-mode (deliverable plus decisions log and limitations); structured-output (formatted rendering with gap report and envelope preservation)

### Future Exploration (T6 territory)

- **Purpose:** Self-contained territory framework for looking forward — projecting consequences, building scenarios, forecasting probabilities, exploring possibility-spaces, anticipating sequels and failure modes
- **Problem Class:** Analytical territory operation — decision, future, and risk (T6)
- **Input Summary:** The present plus a forward-looking question.
- **Output Summary:** Mode-specific forward analysis: consequences-and-sequel (de Bono cascade), probabilistic-forecasting (Tetlock superforecasting), scenario-planning (Wack 2x2 narratives), pre-mortem-action (Klein adversarial-future), or wicked-future (molecular integration); backcasting deferred.
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Excludes risk-and-failure-specific analysis (T7), causal investigation of what already happened (T4), framing examination (T9); backcasting mode deferred per CR-6
- **File Location:** ~/Documents/vault/Framework — Future Exploration.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Consequences-and-sequel (default Tier-2 cascade); probabilistic-forecasting (Tier-2 numeric); scenario-planning (Tier-2 narrative); pre-mortem-action (action-plan stress test); wicked-future (Tier-3 molecular); (backcasting deferred)

### Guided Epistemic Navigation

- **Purpose:** Guide AI-mediated deep learning of any subject through orientation, fog diagnosis, mastery testing, and saturation-aware session management; produces a learning log preserving the learner's irreplaceable inputs
- **Problem Class:** AI-guided deep learning and study facilitation
- **Input Summary:** Required: subject material (framework, chapter, paper, article, text). Required for resumed sessions: prior learning log. Optional: learner's self-reported knowledge level (novice/intermediate/practitioner), learner's purpose (Project Mode or Passion Mode).
- **Output Summary:** Continuously appended learning log preserving learner inputs verbatim plus Current State directive at every block close; in-session terrain map, fog diagnoses, mastery test challenges, domain-expert questions, fork captures, and saturation-detection guidance.
- **Proven Applications:** New framework — landing 2026-04-08 per file metadata; congruent with Chapter 16 of *Learning How to Learn — Guided Epistemic Navigation*
- **Known Limitations:** Domain calibration is mandatory but depends on the AI's ability to identify and calibrate to the practitioner level; saturation diagnosis depends on framework's ability to read learner-response degradation
- **File Location:** ~/Documents/vault/Framework — Guided Epistemic Navigation.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Continuously appended learning log; live terrain mapping, fog diagnosis, mastery testing calibrated to domain practitioner level, fork archiving, and saturation-aware session-close guidance

### Hypothesis Evaluation (T5 territory)

- **Purpose:** Self-contained territory framework for taking multiple competing explanations and a body of evidence and adjudicating among them using diagnosticity, base rates, and Bayesian or quasi-Bayesian reasoning
- **Problem Class:** Analytical territory operation — causation, hypothesis, and mechanism (T5)
- **Input Summary:** Two or more competing hypotheses plus evidence.
- **Output Summary:** Mode-specific evaluation: differential-diagnosis (light medical-tradition triage), competing-hypotheses (full Heuer ACH matrix), or bayesian-hypothesis-network (molecular probabilistic posterior).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Excludes single-hypothesis testing, within-paradigm-debate cases that are really about frame (T9), or hypotheses that are themselves complete arguments needing soundness audit (T1)
- **File Location:** ~/Documents/vault/Framework — Hypothesis Evaluation.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Differential-diagnosis (Tier-1 quick weigh-in with disconfirming tests); competing-hypotheses (default Tier-2 Heuer ACH matrix); bayesian-hypothesis-network (Tier-3 molecular probabilistic posterior with sensitivity analysis)

### Implementation Plan for Analytical Territories and Modes *(archived 2026-07-12)*

- **Status:** Completed engineering plan, no longer an invocable framework. Its eight-phase migration delivered the 21-territory architecture, resident-mode migration, Lens Library, pre-routing pipeline, signal vocabulary, and documentation propagation. Preserved for decision history at `Archive/Framework — Implementation Plan for Analytical Territories and Modes.md.archived-2026-07-12`; current registries, mode/lens files, and runtime documentation are authoritative for as-built behavior.

### Interest and Power Analysis (T2 territory)

- **Purpose:** Self-contained territory framework for surfacing who benefits, who pays, who has power to shape this, whose voices are absent, and how interest structures explain what is observed
- **Problem Class:** Analytical territory operation — argument and reasoning, interest-structural (T2)
- **Input Summary:** A situation, decision, or claim with multiple parties whose interests may diverge.
- **Output Summary:** Mode-specific analysis: cui-bono (descriptive who-benefits with FGL), boundary-critique (Ulrich CSH twelve categories with is/ought audit), stakeholder-mapping (cross-territory dispatch into T8), wicked-problems (molecular complexity), or decision-clarity (molecular for third-party decision-maker production).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Excludes negotiation/conflict-resolution operations (T13) and pure stakeholder-mapping without interest analysis (T8); stakeholder-mapping mode lives in T8 with cross-territory adjacency to T2
- **File Location:** ~/Documents/vault/Framework — Interest and Power Analysis.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Cui-bono (default Tier-2 who-benefits with FGL); boundary-critique (Ulrich CSH stance variant); stakeholder-mapping (cross-territory T8 dispatch); wicked-problems (Tier-3 molecular); decision-clarity (Tier-3 molecular for third-party decision-maker production)

### Mechanism Understanding (T16 territory)

- **Purpose:** Self-contained singleton-territory framework for explaining how parts produce the whole's behavior at the principle level
- **Problem Class:** Analytical territory operation — causation, hypothesis, and mechanism (T16)
- **Input Summary:** A phenomenon whose internal workings are sought.
- **Output Summary:** Mechanism-understanding output: locked level of analysis, component inventory with function per component, interaction pattern as source of whole's behavior (emergence account), boundary conditions, distinction from process map (T17) and causal chain (T4).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Singleton territory (one resident mode); does not do causal investigation (T4 backward-to-causes), process flow over time (T17), or relationship topology (T11); domain-specific mechanism variants deferred
- **File Location:** ~/Documents/vault/Framework — Mechanism Understanding.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Mechanism-understanding (Tier-2 founder mode) with locked level of analysis, component-function attribution, emergence account, boundary conditions, and prediction about behavior under altered conditions

### Negotiation and Conflict Resolution (T13 territory)

- **Purpose:** Self-contained territory framework for active negotiation guidance — interest-mapping, BATNA assessment, integrative-option generation, third-side analysis
- **Problem Class:** Analytical territory operation — position, stakeholder, and strategy (T13)
- **Input Summary:** An active negotiation or conflict where guidance is sought (party preparation or mediator/facilitator stance).
- **Output Summary:** Mode-specific guidance: interest-mapping (Tier-1 quick Fisher-Ury position-vs-interest descent), principled-negotiation (Tier-2 full Fisher-Ury with BATNA both parties plus Voss-warning flag), or third-side (Ury multi-party mediator stance variant).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Excludes descriptive stakeholder mapping without active-negotiation framing (T8), pure interest-power analysis (T2), and strategic-game analysis with formal payoffs (T18)
- **File Location:** ~/Documents/vault/Framework — Negotiation and Conflict Resolution.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Interest-mapping (Tier-1 quick); principled-negotiation (default Tier-2 full Fisher-Ury); third-side (mediator-stance variant)

### News Article Generator

- **Purpose:** Convert one selected event cluster into one publishable Main Street Independent newsfeed article. The model authors prose, a thin frontmatter set, and a `## Summary` bullet section under wire-discipline authoring instructions (the framework document itself is injected verbatim into the author prompt by `article_generator.py::construct_system_prompt`); the pipeline (`normalize_article`) injects all authoritative structured data — sources rebuilt from the cluster, dates, IDs, topic and floor-value tags — and validates the result against the Astro articles schema. One author call plus one validation retry, at gear 3; Layer 2 of the publication pipeline
- **Problem Class:** AI-authored newsfeed article production with instruction-enforced verification, hedge-preservation, verbatim-quotation, and floor discipline, plus pipeline-injected metadata
- **Input Summary:** Cluster JSON from the Layer-1 ingestion adapters (single-member by default, or multi-member via the optional `event_dedup` merge) with cluster_id, members, and publish_date
- **Output Summary:** A markdown article file — frontmatter (headline, lede, optional nut_graf, primary_entities, primary_themes) plus a `## Summary` atomic-note section and body prose — validated against the Astro articles schema; sources and provenance are built by the pipeline from the cluster, not authored by the model; CC0-licensed
- **Proven Applications:** New framework — landing 2026-05-05 per file metadata; F-Design output for Appendix F of the Main Street Independent treatise
- **Known Limitations:** Discipline is enforced by instruction, not code gates — no MindSpec floor screen, no human-review Gates A/B/C, no JSON-LD emission (those live in the canonical doc's design-intent appendix as unimplemented); a legacy code prompt-prefix still requests atomic_claims/sources that the pipeline discards (canonical doc flag F1)
- **File Location:** ~/Documents/vault/Framework — MSI News Article Generator.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.3.0
- **Delivers:** One publishable prose article with `## Summary` section per cluster, with authoritative metadata injection and Astro-schema validation performed by `normalize_article`

### News Cluster Selector

- **Purpose:** Layer 1 of the publication pipeline — decide what becomes news. Not a continuously-running selector agent but a fan-out of independent per-source ingestion adapters (NPR, the UPI/BBC/Guardian RSS pool, WSJ subscriber scrape, AP realtime scrape) invoked every ~3 hours by `continuous_cycle.run_tick → discover()` under the `msi-cycle.timer` systemd timer; each adapter discovers stories from one public feed, applies editorial filters, synthesizes a single-member cluster JSON, and enqueues an author job for the article generator. Cross-source corroboration happens only via the optional embedding-based `event_dedup` merge (`MSI_EVENT_DEDUP`, default off)
- **Problem Class:** Per-source news ingestion and editorial-filter fan-out with queue-mediated handoff to article production
- **Input Summary:** Public feeds, one per adapter — RSS (NPR; UPI/BBC/Guardian pool), Playwright subscriber scrape (WSJ), realtime apnews scrape (AP); reliability tiers hardcoded per adapter; US-anchored relevance filter (`tools/us_relevance.py`, default on); entity resolution via `tools/entity_resolver.py`. No GDELT (subsystem pruned 2026-06-02; `gdelt_event_ids` is emitted as `[]`), no source-quality rating feeds, no eight-file configuration bundle
- **Output Summary:** Single-member cluster JSON files under `ora-project/clusters/<date>/`; enqueued author jobs on the SQLite backfill queue (`ora-project/state/backfill-queue.db`); optionally, merged multi-member clusters or late-source appends to already-published articles via `event_dedup`
- **Proven Applications:** New framework — landing 2026-05-05 per file metadata
- **Known Limitations:** No selection budget, hold queue, feedback-loop reliability adjustment, or MindSpec floor scoring in the live path (`floor_engagement.py` is orphaned dead code); `cluster_selector.py` was deleted 2026-06-02; the original 10-layer continuous design is preserved only as the canonical doc's design-intent appendix
- **File Location:** ~/Documents/vault/Framework — MSI News Cluster Selector.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 2.0.0
- **Delivers:** Per-cycle discovery fan-out producing single-member cluster JSON plus queued author jobs; optional event-dedup merge of same-event clusters; event-driven review-queue drain for op-eds and analyses (`scripts/review_drain.py`)

### News Image Generator

- **Purpose:** Produce the hero image for the ~22%/day subset of Main Street Independent articles that clear a deterministic salience budget. AI generation only (no commons search), gated up front by `tools/article_salience.py::should_render_hero`, executed by `ora-project/tools/msi_image_render.py::render_news_image`, finished by the cream-panel post-processor (`tools/msi_image_post_process.py`), and written into the article's frontmatter `image:` field; editorial cartoons are delegated to Framework — MSI Hector Rentier Editorial Cartoon
- **Problem Class:** Budget-gated AI hero-image production with attribution/disclosure and deterministic post-processing
- **Input Summary:** Article slug, publish_date, and cluster JSON salience signals at the backfill orchestrator's Step 4.5 gate (`_maybe_render_hero_image` inside `msi_engine.produce_article`); salience computed from a source-tier baseline plus AP-Top-News, multi-outlet-corroboration, and primary-document bonuses, with `SALIENCE_MIN` 0.43 and a diversified round-robin budget fill across sources
- **Output Summary:** AI-generated hero image plus an Astro imageSchema frontmatter patch — the schema is `{url, alt, source}` only — with a uniform AI-disclosure string and WCAG-compliant alt text, cream-panel keyed/padded/tinted
- **Proven Applications:** New framework — landing 2026-05-05 per file metadata; F-Design output for Workstream 11 (Visual Journalism) of the Main Street Independent project
- **Known Limitations:** No commons search (Layer 2 intentionally not implemented), no five-screen suitability gate, no placeholder/retry queue (nearest analogs: the batch sweeper's self-heal and `reconcile_dangling_images`); the likeness gate is effectively a no-op in the auto path; articles with pre-2026 publish dates are excluded from paid generation
- **File Location:** ~/Documents/vault/Framework — MSI News Image Generator.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 2.0.0
- **Delivers:** Hero-image artifact plus frontmatter `image:` patch for budget-clearing articles; batch-sweeper self-heal for renders missed at worker time

### Obsidian Setup

- **Purpose:** Set up an Obsidian vault integrated with the local AI system — handles two scenarios (creating a new vault for users who don't use Obsidian, or integrating starter files into an existing vault for users who do); installs minimal frontmatter conventions and starter templates without imposing comprehensive vault architecture
- **Problem Class:** Local AI system installation accessory — Obsidian vault provisioning
- **Input Summary:** Required: framework loaded into the local AI system; workspace directory structure from first-boot framework. Optional: existing vault path (default: framework creates new vault); starter files from book repository (default: framework generates starter files directly).
- **Output Summary:** Configured Obsidian vault with minimal frontmatter conventions (type and date created fields) and starter templates installed; updated orchestrator configuration noting vault location if non-default; brief "Welcome to Your Vault" note explaining what was set up and how to use it.
- **Proven Applications:** New framework — landing 2026-04-01 per file metadata
- **Known Limitations:** Installs only minimal convention plus starter templates (full knowledge architecture is aspirational content in Part V); never modifies anything in `.obsidian/` settings directory; non-destructive integration for existing-vault users
- **File Location:** ~/Documents/vault/Framework — Obsidian Setup.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** New Obsidian vault with frontmatter conventions and starter templates (new-vault scenario); starter files non-destructively installed in existing vault with orchestrator configuration updated (existing-vault scenario)

### Open Exploration (T20 territory)

- **Purpose:** Self-contained singleton-territory framework for generative work on an open prompt, partial idea, or area-of-interest — exploration, ideation, question-formulation; output is generative, not analytical
- **Problem Class:** Generative non-analytical exploration (T20, sits outside the analytical routing tree's defeasible-output contracts)
- **Input Summary:** An open prompt, partial idea, or area-of-interest where the user wants to explore rather than evaluate.
- **Output Summary:** Exploration map (loose, frontier-respecting); ≥3 open questions kept open; potential project nodes when crystallization candidates appear; ≥2 next-directions (one deepening, one lateral); crystallization-detection signals reflected back to user when present.
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Singleton territory (one resident mode); idea-development and research-question-generation expansion candidates deferred per CR-6; mode optimizes for productive wandering not closure (open questions outrank tidy conclusions)
- **File Location:** ~/Documents/vault/Framework — Open Exploration.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Passion-exploration (Tier-2 founder mode) with exploration map plus open questions plus next-directions plus crystallization-detection reflection

### Orientation in Unfamiliar Territory (T14 territory)

- **Purpose:** Self-contained territory framework for producing structured orientation in an unfamiliar domain, problem space, or codebase — the lay of the land
- **Problem Class:** Analytical territory operation — synthesis, orientation, structure, generation (T14)
- **Input Summary:** A domain or space the user is new to.
- **Output Summary:** Mode-specific orientation: quick-orientation (~1 min light pass with one-line definition, three-to-five sub-areas, foundational distinctions, entry points, common misconceptions), terrain-mapping (~5 min thorough survey with concept-map envelope, known/contested/open classification, adjacent connections, boundary statement), or domain-induction (~10+ min molecular pass with learning sequence).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Excludes deep-domain expertise application; excludes generative open exploration of an interest area (T20); produces analytical map of existing domain rather than generating new content
- **File Location:** ~/Documents/vault/Framework — Orientation in Unfamiliar Territory.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Quick-orientation (Tier-1 light); terrain-mapping (default Tier-2 thorough survey); domain-induction (Tier-3 molecular pass producing what's-here, connectivity, and learning sequence)

### Oversight Configuration

- **Purpose:** Configure the meta-layer oversight apparatus for a project through three modes — OS-Setup walks initial configuration with progressive questioning, OS-Modify edits or expands existing configuration as the project grows, OS-Verify dry-runs the configuration to confirm it's functional; produces project-level Oversight Specifications (in the PED), section-level rules (in corpus templates), and cross-corpus topology rules (in workflow specs)
- **Problem Class:** Meta-layer oversight configuration management — user's entry point to the meta-layer apparatus
- **Input Summary:** Required (varies by mode): mode (Setup/Modify/Verify); project nexus or PED path. OS-Setup: PED contents. OS-Modify: PED contents, existing configuration artifacts, change description. OS-Verify: all configuration artifacts. Optional: verification scope; existing frameworks inventory.
- **Output Summary:** OS-Setup: updated PED with project-level Oversight Specification, updated corpus template with section-level rules (Shape 4 only), updated workflow spec with cross-corpus topology rules (multi-framework only), OS-Verify Handoff Package. OS-Modify: edits or expansions with Decision Log rationale. OS-Verify: verdict (READY / READY-WITH-WARNINGS / NOT-READY) with specific gaps if NOT-READY.
- **Proven Applications:** New framework — landing 2026-05-04 per file metadata; instantiates the setup procedure declared in Reference — Meta-Layer Architecture §11
- **Known Limitations:** A project without an OC-produced configuration cannot have Process Coherence fire on it (no specification to drive routing); the user does not write Process Coherence's inputs by hand — OC produces them through progressive questioning; relies on PEF and CFF auto-invocation at natural moments
- **File Location:** ~/Documents/vault/Framework — Oversight Configuration.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** New oversight configuration with pattern detection and progressive-questioning elicitation (OS-Setup); edited or expanded oversight configuration with Decision Log rationale (OS-Modify); dry-run verification verdict against artifact existence, lock-readability, routing coverage, synthetic-event routing, and watcher heartbeats (OS-Verify)

### Paradigm and Assumption Examination (T9 territory)

- **Purpose:** Self-contained territory framework for stepping outside the assumed frame of a problem to examine the assumptions, paradigms, and worldviews that shape how the problem is being constructed
- **Problem Class:** Analytical territory operation — argument and reasoning, frame-level (T9)
- **Input Summary:** A problem, debate, or impasse where reframing is in play.
- **Output Summary:** Mode-specific output: paradigm-suspension (atomic suspending stance — assumptions surfaced as testable propositions with Einstein guard rail), frame-comparison (atomic comparing stance — Lakoff metaphors with symmetric depth across frames), or worldview-cartography (Tier-3 molecular).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Excludes single-artifact frame audit (T1 frame-audit), within-frame causal investigation (T4), within-frame hypothesis evaluation (T5), and integration across paradigms (T12)
- **File Location:** ~/Documents/vault/Framework — Paradigm and Assumption Examination.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Paradigm-suspension (default Tier-2 single-frame surfacing); frame-comparison (Tier-2 multi-frame side-by-side); worldview-cartography (Tier-3 molecular cartography)

### Process Coherence

- **Purpose:** Chain-coordination supervision layer of the meta-layer apparatus — fires automatically at framework transitions, milestone-completion claims, and workflow events; compares actual work product against the locked Mission, Excluded Outcomes, and Constraints from the project's PED (and section/topology rules for workflow events) and issues PROCEED, REVISE, or ESCALATE; cannot itself modify the locked definition
- **Problem Class:** Architectural enforcement of locked problem definitions and workflow coherence at framework transition points (Layer B of the meta-layer)
- **Input Summary:** Required: locked definitions (PED Mission/Excluded Outcomes/Constraints for project-level events; corpus template section specs and workflow spec topology rules for workflow events); output contract; current plan; executing entity's output; executing entity's claim; project Decision Log; PEF Diagnostic Toolkit. Optional: prior checkpoint history.
- **Output Summary:** Checkpoint verdict (PROCEED / REVISE / ESCALATE / ESCALATE-redefinition) with evidence and reasoning; updated Decision Log entry; corrective-action specification (REVISE only); escalation package (ESCALATE only); redefinition evidence package (PC-Redefinition only).
- **Proven Applications:** Renamed and refactored from Working — Framework — Agent Oversight v1.0 per the 2026-05-04 design session; inherits diagnostic engine from the Problem Evolution Framework; generalized to handle both project-level events (E1–E6) and workflow-level events (E7–E12)
- **Known Limitations:** The framework does not invoke itself — orchestration layer is the only invoker; locked definitions are immutable within the session; does not supervise an agent (supervises the seam between two frameworks, or between a framework and a milestone claim); user-facing entry for verification is OS-Verify in Oversight Configuration
- **File Location:** ~/Documents/vault/Framework — Process Coherence.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 2.0
- **Delivers:** Verdict with corrective-action specification at framework transitions and milestone-completion claims (PC-Milestone); block-evaluation against locked Constraints with alternative-approach surfacing or human-review escalation (PC-Block); redefinition evidence package and escalation when locked definition itself appears to need change (PC-Redefinition)

### Process and System Analysis (T17 territory)

- **Purpose:** Self-contained territory framework for mapping a process, workflow, organization, or system as it currently is — components, flows, bottlenecks, and dependencies; diagnostic in posture, not yet seeking causes
- **Problem Class:** Analytical territory operation — causation, hypothesis, and mechanism, current-state structural (T17)
- **Input Summary:** A process, workflow, or system to be mapped at its current state.
- **Output Summary:** Mode-specific mapping: process-mapping (sequential steps with actor attribution, decision points, dependencies, bottleneck-with-constraint identification, handoff-friction examination, official-vs-actual distinction) or systems-dynamics-structural (boundary-locked feedback structure with stocks, flows, polarity-verified loops, delays, archetypes).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Excludes causal investigation (why this happens — T4), mechanism understanding (T16), and relationship topology without temporal flow (T11); organizational-structure mode deferred per CR-6
- **File Location:** ~/Documents/vault/Framework — Process and System Analysis.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Process-mapping (default Tier-2 process-flow mapping); systems-dynamics-structural (Tier-2 feedback-structure mapping with verified polarity parity); (organizational-structure deferred)

### Risk and Failure Analysis (T7 territory)

- **Purpose:** Self-contained territory framework for examining a plan, system, or design specifically for failure modes, vulnerabilities, fragilities, and tail risks
- **Problem Class:** Analytical territory operation — decision, future, and risk (T7)
- **Input Summary:** A plan, system, or design with a "how could this fail" question.
- **Output Summary:** Mode-specific failure analysis: pre-mortem-fragility (Klein adversarial-future on system/design with structural-vs-operational mitigations distinguished) or fragility-antifragility-audit (Talebian convex/concave classification with via negativa); failure-mode-scan and fault-tree deferred.
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Excludes general-future-exploration broader than failure (T6), Red Team's adversarial-actor framing (T15), causal-after-the-fact analysis (T4), and decision-among-options framing (T3); failure-mode-scan and fault-tree deferred per CR-6
- **File Location:** ~/Documents/vault/Framework — Risk and Failure Analysis.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Pre-mortem-fragility (default Tier-2 Klein structural pre-mortem); fragility-antifragility-audit (Tier-2 Talebian convex/concave classification); (failure-mode-scan and fault-tree deferred)

### Spatial Composition (T19 territory)

- **Purpose:** Self-contained territory framework for analyzing what the spatial composition itself does as primary content — voids, groupings, forces, affordances, information density (renamed from "Visual and Spatial Structure" per Decision G)
- **Problem Class:** Analytical territory operation — synthesis, orientation, structure, generation, layout-as-primary-content (T19)
- **Input Summary:** A bounded spatial composition (real or depicted) — painting, garden, room, page, film frame, dashboard, urban scene, network diagram qua image.
- **Output Summary:** Mode-specific reading: ma-reading (Japanese aesthetics void-as-content), compositional-dynamics (Gestalt + Arnheim universal-perceptual), place-reading-genius-loci (Alexander + Norberg-Schulz deep place-reading), or information-density (Tufte + Bertin chart-encoding analysis).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Excludes inter-element relationship extraction (T11 — re-homed there per Decision G), causal investigation (T4), and process analysis (T17); when input is a diagram, T11 and T19 may both fire on the same input answering different questions; reserved Information-Graphic Visual-Hierarchy Analysis mode held back per promotion threshold
- **File Location:** ~/Documents/vault/Framework — Spatial Composition.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Ma-reading (Wave 2 Japanese aesthetics contemplative); compositional-dynamics (default Tier-2 universal-perceptual); place-reading-genius-loci (Wave 3 deep-place); information-density (Wave 3 Tufte/Bertin chart-encoding)

### Stakeholder Conflict (T8 territory)

- **Purpose:** Self-contained territory framework for taking a situation involving multiple parties with divergent interests/values and characterizing the conflict structure, surfacing positions and interests, and identifying integrative possibilities
- **Problem Class:** Analytical territory operation — position, stakeholder, and strategy, conflict-structural (T8)
- **Input Summary:** A situation with multiple identifiable parties whose interests diverge.
- **Output Summary:** Stakeholder-mapping output: party inventory reaching outside user's frame; concrete stakes per party; Mitchell-Agle-Wood multi-dimensional salience (power AND legitimacy AND urgency); power-interest grid positioning (Bryson); relationships among parties; absent or marginalized parties named explicitly.
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Excludes pure interest-power analysis without conflict structure (T2), active negotiation operations (T13), within-decision party-as-input framing (T3), and which-framing-privileges-whom (T9); conflict-structure expansion mode deferred per CR-6
- **File Location:** ~/Documents/vault/Framework — Stakeholder Conflict.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Stakeholder-mapping (default Tier-2 multi-party landscape with Mitchell-Agle-Wood salience and Bryson power-interest grid); (conflict-structure deferred)

### Strategic Interaction (T18 territory)

- **Purpose:** Self-contained singleton-territory framework for modeling situations as games between rational (or boundedly rational) agents — equilibria, signaling, incentive design
- **Problem Class:** Analytical territory operation — position, stakeholder, and strategy, game-theoretic (T18)
- **Input Summary:** A situation modelable as a game with two or more agents whose choices interact.
- **Output Summary:** Strategic-interaction output: players named with payoffs in actual value terms; game classified on four dimensions (timing/information/duration/sum); equilibrium analysis with method named (backward induction / Nash / subgame perfect / repeated cooperation / Perfect Bayesian); credibility audit on threats and promises; ≥1 alternative game structure tested; mechanism-grounded strategic recommendations.
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Singleton territory; expansion candidates `mechanism-design` and `signaling` deferred per CR-6; excludes interest-mapping for active negotiation (T13), descriptive interest-power analysis (T2), and feedback-system structural mapping (T4/T17)
- **File Location:** ~/Documents/vault/Framework — Strategic Interaction.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Strategic-interaction (Tier-2 founder mode) game-theoretic equilibrium analysis with credibility assessment and alternative-structure test; (mechanism-design and signaling deferred)

### Structural Relationship Mapping (T11 territory)

- **Purpose:** Self-contained territory framework for extracting relations among entities in a representation — the topology of inter-element connections, textual or visual
- **Problem Class:** Analytical territory operation — synthesis, orientation, structure, generation, relational-topology (T11)
- **Input Summary:** A textual list or visual diagram/network/schema of entities and their relations.
- **Output Summary:** Mode-specific mapping: relationship-mapping (typed-and-directional connections, organizing structure named, ≥1 cross-link, acyclicity-checked) or spatial-reasoning (visual-input variant — structural extraction with ambiguity flagging, Tversky correspondence audit, gap analysis, open fog-clearing questions, arrangement-preserving annotation).
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata; spatial-reasoning re-homed from T19 per Decision G
- **Known Limitations:** Excludes mechanism explanation (T16), process-flow analysis (T17), and compositional reading of what the layout itself means (T19); cycles trigger transition to systems-dynamics modes (T4 or T17)
- **File Location:** ~/Documents/vault/Framework — Structural Relationship Mapping.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Relationship-mapping (default Tier-2 textual-input topology); spatial-reasoning (Tier-2 visual-input variant with structural gap detection, Tversky correspondence audit, and arrangement-preserving annotation)

### Vault Conversion Pipeline

- **Purpose:** Non-destructive framework for converting existing PKM vaults into Ora-schema atomic notes with full RAG integration — points at a source vault directory, extracts signal, produces Ora-ready output without modifying the source; serves both onboarding (existing-vault migration) and landfill rehabilitation (signal extraction with original archive)
- **Problem Class:** Existing-vault migration and landfill rehabilitation into Ora atomic-note schema
- **Input Summary:** Required: path to source vault root directory. Configurable: word-count thresholds, content density ratios, MOC link-density threshold (defaults provided, calibrated during Stage 0 calibration run).
- **Output Summary:** Across ten stages: inventory and classification report (user reviews before Stage 2 runs); metadata index plus source link graph plus MOC hierarchy map; processing manifest with per-file track assignment; Ora-schema atomic notes (via Stages 4–7 dispatch to Document Processing Framework / Appendix C-25); typed relationship seeding from merged signal sources; ChromaDB ingestion-ready output.
- **Proven Applications:** Working — landing 2026-04-12 per file metadata
- **Known Limitations:** Wraps the Document Processing Framework (Appendix C-25) — does not duplicate extraction logic; depends on Document Processing Framework, Ora YAML schema, ChromaDB ingestion pipeline, and 13-type relationship taxonomy being built first; user reviews Stage 1 inventory before any processing begins
- **File Location:** ~/Documents/vault/Framework — Vault Conversion Pipeline.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Ten-stage non-destructive pipeline producing Ora-schema atomic notes plus typed relationship seeding plus ChromaDB-ready output from existing PKM vault, with original vault unmodified and configurable triage thresholds calibrated per Stage 0

### Wicked-Future Analysis (T6 molecular)

- **Purpose:** Produce an integrated forward analysis with probability-weighted scenarios, adversarial-future stress-test findings, divergence points to monitor, and explicit gap-flagging where constructive-future (backcasting) analysis has been deferred
- **Problem Class:** Analytical territory operation — depth-molecular future exploration (T6)
- **Input Summary:** Required: forward question. Optional: time horizon, key uncertainties, prior scenarios, prior forecasts, intervention candidates.
- **Output Summary:** Integrated future architecture composing scenario-planning (Stage 1, full 2x2 matrix plus wild-card), probabilistic-forecasting (Stage 2, calibrated probability bands per scenario plus key cross-scenario outcomes), pre-mortem-action (Stage 3, adversarial-future stress test on intervention candidates) and three synthesis stages with divergence-points-to-monitor and gap-flagged backcasting.
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Heaviest analytical mode in T6 currently buildable; constructive-future stance (backcasting) is gap-deferred per CR-6 and the framework documents the deferred-component handling explicitly rather than substituting; quality depends on the three component modes
- **File Location:** ~/Documents/vault/Framework — Wicked-Future Analysis.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Integrated future architecture with probability-banded scenarios stress-tested against pre-mortem failure pathways, plus divergence-points-to-monitor and gap-flagged backcasting deferral

### Worldview Cartography Analysis (T9 molecular)

- **Purpose:** Produce a cartography of competing worldviews — each worldview's foundational commitments surfaced, cross-paradigm tensions named explicitly, dialectical synthesis where the paradigms' own terms permit, residual incommensurabilities preserved as such
- **Problem Class:** Analytical territory operation — depth-molecular paradigm and assumption examination (T9)
- **Input Summary:** Required: problem or debate spanning multiple worldviews. Optional: paradigm inventory, prior frame analyses, paradigm genealogies (Kuhnian/Foucauldian/MacIntyrean lineages).
- **Output Summary:** Integrated cartography composing paradigm-suspension (Stage 1, full per-paradigm including home paradigm), frame-comparison (Stage 2, full multi-paradigm comparative articulation), dialectical-analysis as synthesis (rather than peer component) and three synthesis stages (paradigm-inventory, cross-paradigm-tension-surfacing, dialectical-cartography); residual irreducibilities preserved.
- **Proven Applications:** New framework — landing 2026-05-01 per file metadata
- **Known Limitations:** Heaviest analytical mode in T9; home-paradigm-bias is named failure mode (analyst's home paradigm must be suspended with same rigor as foreign ones); dialectical synthesis is grounded in paradigms' own terms rather than imposed from a meta-paradigm
- **File Location:** ~/Documents/vault/Framework — Worldview Cartography Analysis.md (canonical)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 1.0
- **Delivers:** Worldview cartography composing per-paradigm suspension plus comparative frame articulation plus dialectical synthesis (where paradigms' own terms permit) plus preserved residual irreducibilitiesagentId: a839d9b132cf8ece1 (use SendMessage with to: 'a839d9b132cf8ece1' to continue this agent)
<usage>total_tokens: 226509
tool_uses: 42
duration_ms: 469642</usage>


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

### F-Verify (Step 6)

- **Purpose:** Per-stream verification that the revised analysis meets the universal V1–V7 floor plus the mode-specific `## VERIFICATION CRITERIA`. Runs once per stream after revision (step 5); operates pre-consolidation.
- **File Location:** frameworks/book/f-verify.md

### F-Consolidate (Step 7)

- **Purpose:** Produce the *irreducible corpus* across both verified streams. Four-operation flow: semantic atom extraction → cross-stream deduplication → bloat strip → synthesise per the mode's `## CONSOLIDATION GUIDANCE` (which is now corpus-shape, not deliverable form). Output is internal to the pipeline.
- **File Location:** frameworks/book/f-consolidate.md
- **Note:** Rewritten 2026-05-14 as part of the consolidator/formatter split. The prior "produce the user's answer" framing was retired — deliverable form is now Step 8's responsibility (F-Format).

### F-Format (Step 8)

- **Purpose:** Take the Step-7 corpus and place it into the user-facing deliverable per the mode's `## OUTPUT FORMAT GUIDANCE`. Three-operation flow: placement → surface-dedup → non-fitting-postscript. Form-placement only — the formatter does not summarise, condense, or re-decide substance.
- **File Location:** frameworks/book/f-format.md
- **Note:** Authored 2026-05-14 as part of the consolidator/formatter split. Replaces the prior Step-8 final-verifier (which was redundant with the per-stream verifier at Step 6 and whose corrective-revision fallback could itself drift).

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
| Boot Generation | Tier distinction collapsed; single boot.md serves all configs | ~/Documents/vault/Archive/ |
| Progressive Boot Specification | Full install replaces progressive boot | ~/Documents/vault/Archive/ |
| Boot Canonical A/B/C | Model interchangeability makes separate tier boots unnecessary | ~/Documents/vault/Archive/ |
| Mind Framework | Superseded by MindSpec Interview v0.2.3 (richer single-file spec with commitments, governance, constitution, voice, communication patterns, relationships vs. the older 5-section mind.md). Old Mind Framework produces only a 5-section mind.md; MindSpec produces the full spec. | ~/Documents/vault/Archive/Framework — Mind.md (vault); ~/Documents/vault/Archive/mind-framework.md.archived-2026-04-27 (the ora deprecated copy was archived 2026-04-27 and the deprecated/ folder was removed) |
| MindSpec Library and Instrument | Consolidated 2026-05-09 into `Framework — MindSpec Interview.md` as §II Library and §IV Three-Stage Assessment Instrument; single-file architecture removes distribution dependency between framework mechanism and content | ~/Documents/vault/Archive/Framework — MindSpec Library and Instrument.md |
| MindSpec Universality Audit and Corrections | Archived 2026-05-09; v0.2.2 corrections (26 default recalibrations + portrait/scenario/pressure-test revisions + Stage 2A life-context pass) already applied throughout the consolidated `Framework — MindSpec Interview.md` (v0.2.3); methodology and per-entry rationale preserved in archived file for provenance | ~/Documents/vault/Archive/Framework — MindSpec Universality Audit and Corrections.md |
