---
title: Framework Registry
nexus: wisdom_nexus
type: engram
writing: no
date created: 2026/04/01
date modified: 2026/04/01
---

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

## Maintenance Protocol

- New entries are added whenever the FCF produces a framework (the FCF includes registry entry generation as a standard output step).
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
- **File Location:** pending — not yet installed to frameworks/book/ (canonical: ~/Documents/vault/Installer — Local AI First Boot.md)
- **Provenance:** human-created
- **Confidence:** high
- **Version:** v4 (Layers 1–12)

### Framework — Framework Creation
- **Purpose:** Design, convert, render, and audit AI instruction frameworks to a standardized canonical specification
- **Problem Class:** Framework design and knowledge capture
- **Input Summary:** A task description (F-Design), an existing framework (F-Convert), a canonical spec (F-Render), or a framework for review (F-Audit)
- **Output Summary:** Canonical framework specification; rendered execution variants; framework registry entry
- **Proven Applications:** Multiple frameworks produced across all four modes (F-Design, F-Convert, F-Render, F-Audit)
- **Known Limitations:** Requires human judgment to define evaluation criteria; template-filling failure mode when instructions are ambiguous
- **File Location:** pending — not yet installed to frameworks/book/ (canonical: ~/Documents/vault/Framework — Framework Creation.md)
- **Provenance:** human-created
- **Confidence:** high
- **Version:** 2.0

### Framework — Process Inference
- **Purpose:** Discover unknown transformation processes from defined endpoints when the user knows what they have and what they want but not the path between them
- **Problem Class:** Process discovery and formalization
- **Input Summary:** Current state description; desired end state description; available resources and constraints
- **Output Summary:** Inferred process map with decision points; Formalization Handoff Package for FCF conversion
- **Proven Applications:** Initial version — tested against process discovery scenarios
- **Known Limitations:** Requires honest endpoint definition; confabulation risk when constraints are underspecified
- **File Location:** pending — not yet installed to frameworks/book/ (canonical: ~/Documents/vault/Framework — Process Inference.md)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0

### Framework — Soul
- **Purpose:** Interview the user about their values, communication preferences, and behavioral boundaries, then generate or update soul.md
- **Problem Class:** AI identity and behavioral configuration
- **Input Summary:** User responses to structured interview about tone, directness, ethics, and operating principles
- **Output Summary:** soul.md — a persistent values guideline loaded into every session
- **Proven Applications:** Personal AI identity configuration
- **Known Limitations:** Output quality depends on depth and honesty of user interview responses
- **File Location:** pending — not yet installed to frameworks/book/ (canonical: ~/Documents/vault/Framework — Soul.md)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0

### Framework — Boot Generation
- **Purpose:** Produce complete boot.md system specification files (canonical and agent variants) for local AI agents at the appropriate tier and version
- **Problem Class:** System specification generation
- **Input Summary:** Hardware description; book chapter context (optional); tier and version overrides (optional)
- **Output Summary:** boot-[version]-canonical.md; boot-[version]-agent.md; configuration summary
- **Proven Applications:** Tier A–C boot specifications; multiple version levels
- **Known Limitations:** Re-run required when Progressive Content Registry changes; does not auto-detect mode file changes
- **File Location:** pending — not yet installed to frameworks/book/ (canonical: ~/Documents/vault/Framework — Boot Generation.md)
- **Provenance:** human-created
- **Confidence:** high
- **Version:** 1.0

### Framework — Conversation Processing Pipeline
- **Purpose:** Process raw conversation exports and live session exchanges into structured turn-pair chunks with contextual headers, topic metadata, and ChromaDB indexing for RAG retrieval
- **Problem Class:** Knowledge processing and conversation indexing
- **Input Summary:** Inline mode: prompt-response pair from orchestrator; Batch mode: raw conversation files in ~/Documents/conversations/raw/
- **Output Summary:** Processed chunk files in ~/Documents/conversations/; ChromaDB conversations collection entries; processing manifest
- **Proven Applications:** Inline processing for live sessions; batch processing for commercial AI exports (Claude, ChatGPT, Gemini)
- **Known Limitations:** Inline headers are template-generated; richer LLM-generated headers require batch mode
- **File Location:** pending — not yet installed to frameworks/book/ (canonical: ~/Documents/vault/Framework — Conversation Processing Pipeline.md)
- **Provenance:** human-created
- **Confidence:** high
- **Version:** 1.0

### Framework — Browser Evaluation Setup
- **Purpose:** Connect Playwright browser automation to commercial AI services and register endpoints for use by the orchestrator
- **Problem Class:** Integration setup
- **Input Summary:** Existing commercial AI accounts (Claude, ChatGPT, Gemini)
- **Output Summary:** Saved browser sessions; registered endpoints in endpoints.json
- **Proven Applications:** All tiers with existing subscriptions
- **Known Limitations:** Sessions expire; re-run when login cookies expire
- **File Location:** pending — not yet installed to frameworks/book/ (canonical: ~/Documents/vault/Framework — Browser Evaluation Setup.md)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0

### Framework — API Key Acquisition
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

### Framework — Gear 4 Pipeline Specifications
- **Purpose:** Define the six-stage adversarial analysis pipeline: breadth, depth, evaluation, revision, consolidation, and verification
- **Problem Class:** Multi-model adversarial analysis
- **Input Summary:** User query or analysis task; available models for each stage role
- **Output Summary:** Stage-by-stage analysis outputs culminating in a verified consolidated response
- **Proven Applications:** Complex analytical tasks requiring adversarial review
- **Known Limitations:** Requires multiple capable models; resource-intensive; not suitable for simple queries
- **File Location:** pending — not yet installed to frameworks/book/ (canonical: ~/Documents/vault/Framework — Gear 4 Pipeline Specifications.md)
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0

### Framework — Agent Identity and Programming
- **Purpose:** Create and program specialized agent identities using the SoulSpec pattern, producing a compiled agent boot file and registry entry
- **Problem Class:** Agent creation and identity specification
- **Input Summary:** Agent purpose description; tier selection (functional vs. incarnated); mission parameters
- **Output Summary:** SoulSpec canonical file set; compiled agent boot file; agent registry entry
- **Proven Applications:** None yet — framework not yet created (pending F-Design session)
- **Known Limitations:** Requires the Agent System Architecture document as input to the F-Design session
- **File Location:** pending — framework not yet created (canonical will be: ~/Documents/vault/Framework — Agent Identity and Programming.md)
- **Provenance:** human-created
- **Confidence:** low
- **Version:** 0.1 (placeholder)

---

## Pending — Not Yet Created

The following frameworks are referenced in the system or planned for inclusion but do not yet exist as specification files.

| Framework | Description |
|---|---|
| Framework — Knowledge Artifact Coach | Guide creation of high-quality knowledge artifacts for vault indexing |
| Framework — Guided Epistemic Navigation | Navigate complex epistemic terrain in research and analysis tasks |
| F-Analysis-Breadth | Gear 4 breadth stage — lateral thinking, alternatives, synthesis |
| F-Analysis-Depth | Gear 4 depth stage — sustained logical focus, critical analysis |
| F-Evaluate | Gear 4 evaluator stage — cross-model critique and convergence signaling |
| F-Revise | Gear 4 revision stage — incorporating evaluator feedback |
| F-Consolidate | Gear 4 consolidation stage — merging outputs into final response |
| F-Verify | Gear 4 verification stage — factual and logical final check |
