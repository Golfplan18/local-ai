# Local AI First Boot — Installer Manifest

**Status as of 2026-07-12: legacy natural-language installer specification, not the live install path.** The live public desktop install is `scripts/install.py --profile solo`, documented in `~/Documents/vault/Installer — Ora.md` and `docs/install-guide.md`. This layer set is retained as architecture/specification material and is scheduled for a G3.32 reconciliation into a current natural-language installer. Layer 10 now records the retirement boundary for the superseded config-driven interface rather than specifying installable work.

*Original shape: orchestrated installer. Each layer is a separate file loaded and executed sequentially by a coding agent. Layers must execute in order within each phase. Phase 2 is conditional on the Hardware Evaluation Gate.*

*Current operational source: `scripts/install.py`; user-facing source: `~/Documents/vault/Installer — Ora.md`; architecture paper: `~/Documents/vault/Paper — Installer.md`.*

## How to Use

Do not use this manifest to install Ora today. Use `python3 scripts/install.py --profile solo` for the desktop source install or `./scripts/install-server.sh` for a headless Linux/API-only server. This manifest is useful for understanding the intended layered architecture and for the future G3.32 natural-language installer update.

Each layer file contains its own processing instructions, output format, and verification criteria.

## Shared Context

These apply to all layers and should be loaded once at the start:

- **Purpose:** Transform a bare machine into a working AI system
- **Workspace:** `~/ora/` (default) or user-specified path
- **Named failure modes:** See `appendix.md` and the canonical source document

## Phase 1 — Universal Base (all hardware)

Every reader executes Phase 1 regardless of hardware capability.

| Order | File | Layer | What It Does |
|-------|------|-------|-------------|
| 1 | `phase1/layer1-python-environment.md` | Python Environment | Python 3, pip, core packages |
| 2 | `phase1/layer2-directory-structure.md` | Directory Structure | Workspace directories, config files, routing-config.json (v2; endpoints.json was retired in install Chunk 12) |
| 3 | `phase1/layer3-framework-library.md` | Framework Library | Clone framework files from git repository |
| 4 | `phase1/layer4-orchestrator-installation.md` | Orchestrator Installation | boot.py, boot.md, mind.md, tool implementations |
| 5 | `phase1/layer5-api-key-framework.md` | API Key Framework | Install API key acquisition framework |
| 6 | `phase1/layer6-universal-chat-server.md` | Universal Chat Server | Browser interface at localhost:5000 with agentic loop |

**After Phase 1 in the original layered design:** Reader has a working browser-based AI at localhost:5000 with tool execution. In the live script, API keys are optional: OpenRouter is strongly recommended but not required, free models are rate-limited/sometimes unavailable, and direct provider APIs can be added later in Settings -> External APIs.

**Deployment profiles:** `scripts/install.py` reserves Solo, Hybrid, and Organization, but only **Solo** is supported today. **Hybrid** and **Organization** are future profiles gated on G1.27 network discovery and later concurrency validation. Server installs use a dedicated `scripts/install-server.sh` API-only path.

## Hardware Evaluation Gate

| File | What It Does |
|------|-------------|
| `phase2/gate-hardware-evaluation.md` | Determines whether Phase 2 should execute based on hardware capability |

**Gate outcome:** IF hardware supports local model inference, THEN proceed to Phase 2. ELSE Phase 1 system is complete.

## Phase 2 — Additive Local Capability (hardware permitting)

Phase 2 adds local model inference on top of the Phase 1 system. The Phase 1 system is not modified — Phase 2 registers additional endpoints.

| Order | File | Layer | What It Does |
|-------|------|-------|-------------|
| 1 | `phase2/layer1-hardware-evaluation.md` | Hardware Evaluation | Detect OS, RAM, disk, processor, GPU |
| 2 | `phase2/layer2-model-selection.md` | Model Selection | Select model based on hardware, user preference, RAM formula |
| 3 | `phase2/layer3-workspace-setup.md` | Workspace Setup | Model storage directory |
| 4 | `phase2/layer4-inference-engine.md` | Inference Engine | Install MLX, Ollama, or vllm-mlx based on architecture |
| 5 | `phase2/layer5-model-download.md` | Model Download | Download and verify model files |
| 6 | `phase2/layer6-endpoint-registration.md` | Endpoint Registration | Register local endpoint, verify routing |
| 7 | `phase2/layer7-desktop-launcher.md` | Desktop Launcher | Create desktop launcher for the chat server |
| 8 | `phase2/layer8-documentation-verification.md` | Documentation + Verification | Hardware report, README, final verification tests |
| 9 | `phase2/layer9-model-switcher.md` | Model Switcher | UI for switching between models/endpoints |
| 10 | `phase2/layer10-interface-customization.md` | Interface Customization (retired) | Retirement record: do not recreate layout config/presets/generator or legacy themes; use the hardcoded V3 interface and Theme Library |
| 11 | `phase2/layer11-app-bundle.md` | App Bundle + Icon | In-place macOS Ora.app shell delegating to the tracked launcher/service path, with generated icon variants |
| 12 | `phase2/layer12-conversation-autosave.md` | Conversation Auto-Save | Session logging and ChromaDB indexing |

## Appendix

| File | Contents |
|------|----------|
| `appendix.md` | File access architecture, practical implications, tier capability summary |

## Evaluation Criteria

The complete installation is evaluated against 7 criteria (rated 1-5): Hardware Evaluation Accuracy, Model Selection Appropriateness, Model Integrity, Installation Completeness, Error Recovery, Documentation Completeness, Infrastructure Completeness. Full rubrics are in the canonical source document.
