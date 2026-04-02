# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Repository Overview

Local AI is a multi-model orchestrator for local LLMs on Apple Silicon. It runs an 8-step adversarial pipeline with configurable "Gears" that route prompts through cleanup, context assembly, analysis, cross-evaluation, revision, and verification stages.

**Hardware:** Apple M4 Max, 128 GB RAM, macOS 26.3

## Architecture

### Pipeline (boot.py — the orchestrator)
1. **Step 1** — Prompt cleanup + mode selection + triage tier (Tier 1/2/3)
2. **Step 2** — Context assembly: mode file, conversation RAG, concept RAG (ChromaDB)
3. **Steps 3-8** — Gear-appropriate execution:
   - **Gear 1-2**: Single model, direct response
   - **Gear 3**: Sequential adversarial (Depth → Breadth eval → revise → verify, up to 2 correction cycles)
   - **Gear 4**: Parallel adversarial (ThreadPoolExecutor — parallel analysis, cross-eval, revision, consolidation, verification)
4. **Output routing** — Screen, file (with vault YAML frontmatter), or both

### Model Slots
Models are assigned to named slots (not tied to gears): `sidebar`, `breadth`, `depth`, `evaluator`, `consolidator`, `step1_cleanup`. Any model can fill any slot via the UI model switcher.

### Server (server.py — Flask + SSE)
- Imports all pipeline functions from `orchestrator/boot.py` (no duplicate code)
- SSE streaming with `pipeline_stage` events for UI progress
- Conversation persistence with content-derived filenames
- Clarification panel: Tier 2/3 triage pauses pipeline, generates questions, resumes with answers
- Three clarification endpoints: `POST /api/clarification`, `POST /api/clarification/skip`, `GET /api/clarification/pending`

### Knowledge System
- **ChromaDB** vector store with `knowledge` and `conversations` collections
- **Embeddings** via nomic-embed-text through Ollama
- **Knowledge indexer**: `orchestrator/tools/knowledge_index.py` indexes markdown files with YAML frontmatter
- **Mental models**: `knowledge/mental-models/` — 33 atomic notes indexed into ChromaDB, surface via Step 2 concept RAG

## Key Directories

```
orchestrator/boot.py     — Pipeline orchestrator (all shared logic)
server/server.py         — Flask chat server (localhost:5000)
server/templates/        — index.html (browser UI)
frameworks/book/         — Pipeline stage specifications (F-Analysis, F-Evaluate, etc.)
modes/                   — Mode files (exploratory.md, analytical.md, etc.)
modules/tools/           — Thinking tools (Tier 1) and question banks (Tier 2)
knowledge/mental-models/ — Tier 3 mental model notes (gitignored, local-only)
config/                  — endpoints.json, models.json, interface.json
installer/               — 20-file structured installer (phase1/, phase2/, manifest)
boot/boot.md             — System prompt loaded at startup
soul.md                  — Identity/personality layer
```

## Development Notes

- **Python**: Use `/opt/homebrew/bin/python3` (3.14.3, has Flask/chromadb/mlx-lm/keyring). System Python 3.9.6 lacks these packages.
- **Type hints**: `boot.py` uses `from __future__ import annotations` for Python 3.9 compat with `dict | None` syntax.
- **knowledge/ is gitignored**: Mental model notes are local-only user content. The indexer script IS in the repo.
- **No Gear 5**: The model switcher UI makes Gear 5 redundant (any model in any slot).
- **Gear selection**: Deterministic from `## DEFAULT GEAR` heading in mode files, not an AI decision.
- **Verification protocol**: Verifiers output `VERDICT: PASS` or `VERDICT: FAIL` — structured, not conversational.

## Remaining Work

1. **Frontend clarification UI** — `server/templates/index.html` needs a panel/modal to display clarification questions, accept answers, and call `/api/clarification`. Server-side API is complete.
2. **More mental models** — 33 of ~100 written. Source: fs.blog/mental-models, game theory, Wikipedia. Format documented in `knowledge/mental-models/inversion.md`. Index with: `/opt/homebrew/bin/python3 ~/local-ai/orchestrator/tools/knowledge_index.py ~/local-ai/knowledge/mental-models/`
3. **Canonical changes 5 & 8** — Blocked on Agent System Architecture document.

## Commands

```bash
# Start terminal orchestrator
./start.sh

# Start chat server (localhost:5000)
cd server && ./start-server.sh

# Index mental models into ChromaDB
/opt/homebrew/bin/python3 ~/local-ai/orchestrator/tools/knowledge_index.py ~/local-ai/knowledge/mental-models/

# Reindex (clear + rebuild)
/opt/homebrew/bin/python3 ~/local-ai/orchestrator/tools/knowledge_index.py --reindex ~/local-ai/knowledge/mental-models/
```
