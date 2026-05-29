# Local AI First Boot — Installer Manifest

*Orchestrated installer. Each layer is a separate file loaded and executed sequentially by the coding agent. Layers must execute in order within each phase. Phase 2 is conditional on the Hardware Evaluation Gate.*

*Canonical source: ~/Documents/vault/Installer — Local AI First Boot.md*

## How to Use

Load this manifest into the coding agent. The agent reads each layer file in sequence, executes its instructions, verifies its output, and proceeds to the next layer only after verification passes. If a layer fails, the agent reports the failure and stops — it does not proceed to the next layer.

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

**After Phase 1:** Reader has a working browser-based AI at localhost:5000 with tool execution. Cloud-API access (OpenRouter required; Anthropic / OpenAI / Google direct optional) is set up via API keys when the reader runs the API Key Setup Framework.

**Deployment profiles (install Chunk 7):** the install script (`scripts/install.py`) prompts for a deployment profile at Step 2. **Solo** is the desktop single-user profile and is the only profile enabled today; **Hybrid** (MLX worker + small API worker pool) and **Organization** (pure API, scales to 20+ concurrent processes) are scaffolded but gated on the concurrency-architecture work landing. Server installs use a dedicated `scripts/install-server.sh` (API-only, single-process) as an interim path until the Organization profile lands.

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
| 10 | `phase2/layer10-interface-customization.md` | Interface Customization | Multi-panel UI, mode selector, display settings |
| 11 | `phase2/layer11-app-bundle.md` | App Bundle + Icon | macOS .app bundle with custom icon |
| 12 | `phase2/layer12-conversation-autosave.md` | Conversation Auto-Save | Session logging and ChromaDB indexing |

## Appendix

| File | Contents |
|------|----------|
| `appendix.md` | File access architecture, practical implications, tier capability summary |

## Evaluation Criteria

The complete installation is evaluated against 7 criteria (rated 1-5): Hardware Evaluation Accuracy, Model Selection Appropriateness, Model Integrity, Installation Completeness, Error Recovery, Documentation Completeness, Infrastructure Completeness. Full rubrics are in the canonical source document.
