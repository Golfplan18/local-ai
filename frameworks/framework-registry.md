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
- **File Location:** pending restructure (canonical: ~/Documents/vault/Installer — Local AI First Boot.md)
- **Provenance:** human-created
- **Confidence:** high
- **Version:** v4 (Layers 1–12)

### Framework Creation
- **Purpose:** Design, convert, render, and audit AI instruction frameworks to a standardized canonical specification
- **Problem Class:** Framework design and knowledge capture
- **Input Summary:** A task description (F-Design), an existing framework (F-Convert), a canonical spec (F-Render), or a framework for review (F-Audit)
- **Output Summary:** Canonical framework specification; rendered execution variants; framework registry entry
- **Proven Applications:** Multiple frameworks produced across all four modes (F-Design, F-Convert, F-Render, F-Audit)
- **Known Limitations:** Requires human judgment to define evaluation criteria; template-filling failure mode when instructions are ambiguous
- **File Location:** frameworks/book/framework-creation.md
- **Provenance:** human-created
- **Confidence:** high
- **Version:** 2.0

### Process Inference
- **Purpose:** Discover unknown transformation processes from defined endpoints when the user knows what they have and what they want but not the path between them
- **Problem Class:** Process discovery and formalization
- **Input Summary:** Current state description; desired end state description; available resources and constraints
- **Output Summary:** Inferred process map with decision points; Formalization Handoff Package for FCF conversion
- **Proven Applications:** Initial version — tested against process discovery scenarios
- **Known Limitations:** Requires honest endpoint definition; confabulation risk when constraints are underspecified
- **File Location:** frameworks/book/process-inference.md
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0

### Soul Framework
- **Purpose:** Interview the user about their values, communication preferences, and behavioral boundaries, then generate or update soul.md
- **Problem Class:** AI identity and behavioral configuration
- **Input Summary:** User responses to structured interview about tone, directness, ethics, and operating principles
- **Output Summary:** soul.md — a persistent values guideline loaded into every session
- **Proven Applications:** Personal AI identity configuration
- **Known Limitations:** Output quality depends on depth and honesty of user interview responses
- **File Location:** frameworks/book/soul-framework.md
- **Provenance:** human-created
- **Confidence:** medium
- **Version:** 1.0

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

### Agent Identity and Programming
- **Purpose:** Create and program specialized agent identities using the SoulSpec pattern, producing a compiled agent boot file and registry entry
- **Problem Class:** Agent creation and identity specification
- **Input Summary:** Agent purpose description; tier selection (functional vs. incarnated); mission parameters
- **Output Summary:** SoulSpec canonical file set; compiled agent boot file; agent registry entry
- **Proven Applications:** Framework produced via F-Design from FCF v2.0
- **Known Limitations:** Incarnated agent voice calibration requires user-provided reference materials for best results
- **File Location:** frameworks/book/agent-identity.md
- **Provenance:** human-created
- **Confidence:** high
- **Version:** 1.0

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

---

## Pipeline Stage Frameworks (Gear 4)

These six frameworks are loaded into model context windows at specific pipeline stages. They were extracted from the Gear 4 Pipeline Specifications container document.

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

---

## Deprecated / Archived

| Framework | Reason | Location |
|---|---|---|
| Boot Generation | Tier distinction collapsed; single boot.md serves all configs | ~/Documents/vault/Old AI Working Files/ |
| Progressive Boot Specification | Full install replaces progressive boot | ~/Documents/vault/Old AI Working Files/ |
| Boot Canonical A/B/C | Model interchangeability makes separate tier boots unnecessary | ~/Documents/vault/Old AI Working Files/ |
