# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Vault Canonical Rule (READ FIRST)

**The Wisdom Nexus vault at `/Users/oracle/Documents/vault/` is the canonical source of truth for all markdown content in this repository.** Files in `~/ora/` are operational copies the orchestrator loads at runtime; the vault is where edits happen and where the source-of-truth lives.

**When you modify any `.md` file in `~/ora/`, you MUST also update the paired vault file** — otherwise drift accumulates and the next vault → ora sync will silently overwrite your ora-side edits.

The pairing convention:
- `~/ora/frameworks/book/<name>.md` ↔ `/Users/oracle/Documents/vault/Framework — <Title Case Name>.md` (or `Specification — <Title>.md` for the F-stage specs). Vault has YAML, ora does not.
- `~/ora/modes/<name>.md` ↔ `/Users/oracle/Documents/vault/Modes/<name>.md`. Both have YAML; preserve.
- `~/ora/knowledge/mental-models/<name>.md` ↔ `/Users/oracle/Documents/vault/Lenses/<name>.md`. Both have YAML; preserve.
- `~/ora/modules/tools/.../<name>.md` ↔ `/Users/oracle/Documents/vault/Modules/Tools/.../<name>.md`. Neither has YAML.
- A handful of singletons: `~/ora/agents/agent-registry.md` ↔ `Reference — Agent Registry.md`; `~/ora/FORKING.md` ↔ `Reference — Forking Ora.md`; `~/ora/frameworks/mode-classification-directory.md` ↔ `Reference — Mode Classification Directory.md`; `~/ora/frameworks/framework-registry.md` ↔ `Framework — Framework Registry.md`.
- `~/ora/CLAUDE.md` (this file), `~/ora/boot/boot.md`, `~/ora/mind.md`, `~/ora/mindspec/default-mindspec.md` — ora-only, no vault counterpart.

**The recommended workflow when editing ora .md files:**
1. Make your edit to the ora file (fast iteration).
2. Immediately propagate the body change to the paired vault file (preserve vault's YAML; replace the body).
3. OR surface the change so the user can run the System File Drift Correction framework to reconcile.

If you skip step 2 or 3, the user has to remember the divergence — and they will miss it. Don't make them.

The full pairing rules and operational details are in `~/ora/frameworks/book/system-file-drift-correction.md` (canonical: `/Users/oracle/Documents/vault/Framework — System File Drift Correction.md`).

## Repository Overview

Ora is a multi-model orchestrator for local LLMs on Apple Silicon. It runs an 8-step adversarial pipeline with configurable "Gears" that route prompts through cleanup, context assembly, analysis, cross-evaluation, revision, and verification stages.

**Hardware:** Apple M4 Max, 128 GB RAM, macOS 26.3

**Local Models (Config A — "The Surgeon and the Architect"):**
- **Breadth/Consolidator (local-premium):** Hermes-4-70B (Llama 3.1 base, NousResearch) — 40 GB, dense 70B
- **Depth/Evaluator (local-premium):** Kimi-Dev-72B (Qwen 2.5 base, Moonshot AI) — 41 GB, dense 72B
- **Sidebar/Step1/RAG (local-mid):** Qwen3.5-27B-Claude-Opus-Distilled — 14 GB, dense 27B
- **Classification (local-fast):** Qwen3.5-4B-MLX (4-bit) — 3 GB, dense 4B. 100% mode classification accuracy at ~10s.
- **Backup fast (local-fast):** Qwen3.5-9B-OptiQ (4-bit) — 6 GB, dense 9B. 94.4% accuracy at ~34s (before directory fix).
- **Total model RAM:** ~95 GB active with 33 GB headroom. Three model families for adversarial diversity.

## Architecture

### Pipeline (boot.py — the orchestrator)
1. **Step 1** — Two-pass: Phase A (prompt cleanup) → Phase A.5 (mode classification via Mode Classification Directory)
2. **Step 2** — Context assembly: mode file, conversation RAG, concept RAG (ChromaDB)
3. **Steps 3-8** — Gear-appropriate execution:
   - **Gear 1-2**: Single model, direct response
   - **Gear 3**: Sequential adversarial (Depth → Breadth eval → revise → verify, up to 2 correction cycles)
   - **Gear 4**: Parallel adversarial (ThreadPoolExecutor — parallel analysis, cross-eval, revision, consolidation, verification)
4. **Output routing** — Screen, file (with vault YAML frontmatter), or both

### Model Slots
Models are assigned to named slots (not tied to gears): `sidebar`, `breadth`, `depth`, `evaluator`, `consolidator`, `step1_cleanup`, `classification`. Any model can fill any slot via the UI model switcher. The `classification` slot resolves from the `local-fast` bucket, enabling a 4B model to handle Phase A.5 at ~10s per call.

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

### Visual Intelligence Subsystem (2026-04-17)
- **Client compiler** at `server/static/ora-visual-compiler/`: 22 typed renderers covering QUANT (Vega-Lite), PROCESS (Mermaid), CAUSAL (CLD / stock-and-flow / DAGitty / fishbone), DECISION (tree + EV rollback, influence diagram, ACH, 2×2), RISK (bow-tie), ARGUMENT (IBIS, pro-con), RELATIONAL (concept map), SPATIAL (C4). Validates against 23 JSON Schema 2020-12 definitions, dispatches to type-specific renderer, runs accessibility layer (Lundgard-Satyanarayan 4-level descriptions + element-level ARIA + Olli keyboard nav), then artifact-level adversarial review (overlap / text truncation / WCAG 2.1 contrast). Critical findings force fallback to table or prose per Protocol §8.5.
- **Visual panel** at `server/static/visual-panel.js`: Konva 4-layer stage (background / annotation / userInput / selection) with pan, zoom, click-select, keyboard nav, shape-drawing tools (rect / ellipse / diamond / line / arrow / text + undo-redo), annotation-authoring (callout / highlight / strikethrough / sticky / pen), and image-upload backdrop.
- **Input merging**: `/chat/multipart` endpoint accepts text + `spatial_representation` (from `canvas-serializer.js`) + `annotations` (from `annotation-parser.js`) + image binary. `boot.py` serializes structured input into the system prompt for text-only local models; vision-capable models receive the image directly when `vision_capable: true` in `models.json`.
- **Server validation**: `orchestrator/visual_validator.py` (schema + structural invariants) + `orchestrator/visual_adversarial.py` (Tufte T-rules + LLM-prior-inversion checks) hook into `boot.py` at the emission point. Block on Critical, warn on Major.
- **Vault export**: `orchestrator/vault_export.py` writes canonical markdown with `![[fig-N.svg]]` sidecars to `~/Documents/vault/Sessions/`. Node CLI at `ora-visual-compiler/tools/render-envelope.js` does server-side envelope→SVG rendering via jsdom-booted compiler.
- **Spatial continuity**: `orchestrator/conversation_memory.py` persists per-turn `spatial_representation` + `annotations` in conversation.json; prior state injected into next turn's prompt with a layout-preservation instruction.
- **Active layouts**: `solo` (chat 50% + visual 50%) is default; `studio` (chat 40% + visual 40% + sidebar 20% on `local-fast` bucket) when both `local-mid` and `local-premium` have entries. Legacy `simple.json` and `workbench.json` archived under `config/layouts/legacy/`.

## Key Directories

```
orchestrator/boot.py                         — Pipeline orchestrator (all shared logic)
orchestrator/visual_validator.py             — Ora-visual schema + structural invariants
orchestrator/visual_adversarial.py           — Tufte T-rules + LLM-prior-inversion checks
orchestrator/visual_extraction.py            — Vision-model extraction prompt + response parser
orchestrator/vault_export.py                 — Session → canonical markdown + SVG sidecars
orchestrator/conversation_memory.py          — Turn-level spatial/annotation persistence
server/server.py                             — Flask chat server (localhost:5000)
server/templates/                            — index.html (browser UI)
server/static/ora-visual-compiler/           — Client compiler: errors.js, validator.js, dispatcher.js, index.js, renderers/, vendor/ (Vega, Vega-Lite, Mermaid, viz-js, D3, Dagre, Konva, Ajv, structurizr-mini), tests/
server/static/ora-visual-compiler/tools/     — Node CLI render-envelope.js (envelope → SVG)
server/static/visual-panel.js                — Konva dual-pane panel (canvas input + artifact display + annotations)
server/static/canvas-serializer.js           — userInputLayer → spatial_representation JSON
server/static/annotation-parser.js           — annotationLayer (user) → structured instructions
server/static/chat-panel.js                  — Chat panel (extended for ora-visual block extraction + multipart send)
frameworks/book/                             — Pipeline stage specifications (F-Analysis, F-Evaluate, etc.)
frameworks/mode-classification-directory.md  — Phase A.5 classification reference (22 modes, includes SPATIAL intent)
modes/                                       — Mode files (22 modes incl. spatial-reasoning, benefits-analysis, consequences-and-sequel)
modules/tools/                               — Thinking tools (Tier 1) and question banks (Tier 2)
knowledge/mental-models/                     — Tier 3 mental model notes (gitignored, local-only)
config/endpoints.json                        — Model endpoint URLs
config/models.json                           — Model registry with vision_capable flag per model
config/routing-config.json                   — Capability routing + vision_extraction policy
config/interface.json                        — Active layout (default: solo)
config/panel-types.json                      — Panel type registry (chat, vault, pipeline, clarification, visual, switcher)
config/layouts/                              — solo.json, studio.json (active); legacy/ holds retired layouts
config/visual-schemas/                       — 23 JSON Schemas + 44 example envelopes + README
config/mode-to-visual.json                   — Per-mode visual defaults + adversarial strictness
installer/                                   — 20-file structured installer (phase1/, phase2/, manifest)
boot/boot.md                                 — System prompt loaded at startup
mind.md                                      — Identity/personality layer
```

## Development Notes

- **Python**: Use `/opt/homebrew/bin/python3` (3.14.3, has Flask/chromadb/mlx-lm/keyring). System Python 3.9.6 lacks these packages.
- **Type hints**: `boot.py` uses `from __future__ import annotations` for Python 3.9 compat with `dict | None` syntax.
- **knowledge/ is gitignored**: Mental model notes are local-only user content. The indexer script IS in the repo.
- **No Gear 5**: The model switcher UI makes Gear 5 redundant (any model in any slot).
- **Gear selection**: Deterministic from `## DEFAULT GEAR` heading in mode files, not an AI decision.
- **Verification protocol**: Verifiers output `VERDICT: PASS` or `VERDICT: FAIL` — structured, not conversational.

## Remaining Work

1. **More mental models** — 33 of ~100 written. Source: fs.blog/mental-models, game theory, Wikipedia. Format documented in `knowledge/mental-models/inversion.md`. Index with: `/opt/homebrew/bin/python3 ~/ora/orchestrator/tools/knowledge_index.py ~/ora/knowledge/mental-models/`
2. **Tier 2 question bank modules** — 6 markdown files in `modules/tools/tier2/` (domain question banks for the front-end process)

## Completed (recent sessions)

- **Frontend clarification UI** — Popup modal with SSE streaming, submit/skip endpoints, keyboard shortcuts (Escape/Cmd+Enter)
- **Canonical changes 1–9** — All complete. Agent System Architecture document created, Agent Identity framework validated, book outline fully updated.
- **System Overview updated** — Gear 5 removed, model slot system added, agent subsystem section added, chapter numbering corrected, clarification UI documented.
- **Visual Intelligence system (2026-04-17)** — All six phases of the Visual Intelligence plan: 22 typed renderers + client accessibility layer + Python validator + adversarial T-rule review + Konva dual-pane UI + canvas drawing tools + vision-capable routing + user annotation system + spatial continuity across turns + vault markdown export with SVG sidecars. Driving plan: `~/Documents/vault/Working — Framework — Visual Intelligence Implementation Plan.md`. Handoff brief: `~/Documents/vault/Working — Framework — Visual Intelligence Thread Handoff.md`. Live-fire results (2026-04-18): `~/Documents/vault/Working — Framework — Visual Intelligence Live-Fire Results.md`.

- **Mode Specification Rebuild — Phases 1–3 (2026-04-18)** — Rebuilt 20 of 21 mode files in `~/ora/modes/` (all except `spatial-reasoning.md`, which is preserved as the reference) against an 11-section specification structure: Trigger Conditions → Epistemological Posture → Default Gear → RAG Profile (with Input Spec) → Depth/Breadth Model Instructions → Content Contract → Emission Contract → Guard Rails → Success Criteria (structural + semantic + composite + machine-readable YAML) → Known Failure Modes. Added Tier A harness at `orchestrator/tests/test_mode_emission.py` with per-mode structural + composite checkers for 18 modes, plus always-on file-structure tests. Phase 1 (`root-cause-analysis`) live Tier A = 100% on 18 runs against Gemini 2.5 Flash; Phase 2/3 live Tier A deferred to Phase 4. Driving plan: `~/Documents/vault/Working — Framework — Mode Specification Rebuild Plan.md`.

- **Mode Specification Rebuild — Phase 4 (2026-04-18)** — Wired the rebuilt mode files into production. `boot.py::build_system_prompt_for_gear` now extracts `## EMISSION CONTRACT` + `## SUCCESS CRITERIA` and injects them alongside the pre-existing DEPTH/BREADTH/CONTENT CONTRACT/GUARD RAILS blocks. Created `orchestrator/mode_success_criteria.py` — the shared structural-checker module used by both the Tier A harness and `visual_adversarial.review_envelope` (no duplication). `visual_adversarial.review_envelope` now emits per-mode structural findings keyed `mode_success_criterion_<id>` at Major severity alongside the generic Tufte / LLM-prior-inversion pass. Tier A harness gained per-call timeout (default 60s, overridable via `--timeout` or `ORA_TIER_A_TIMEOUT`), prompt-length instrumentation (chars + estimated tokens), and correct handling for envelope-optional modes (`deep-clarification`, `passion-exploration`) + no-visual modes (`steelman-construction`, `paradigm-suspension`). Live Tier A run across all 18 visual-bearing modes. Python tests: 417 (was 396). JS tests: 715 (unchanged). Driving plan: `~/Documents/vault/Working — Framework — Mode Specification Phase 4 Integration Plan.md`.

- **Mode Specification Rebuild — Phase 5 Pipeline Cascade Integration (2026-04-18)** — F-* files made strictly universal: `f-evaluate.md` carries the universal 7-section output contract (VERDICT / CONFIDENCE / MANDATORY FIXES / SUGGESTED IMPROVEMENTS / COVERAGE GAPS / UNCERTAINTIES / CROSS-FINDING CONFLICTS); `f-revise.md` the mirror reviser contract; `f-verify.md` universal V1-V7 floor; `f-consolidate.md` universal synthesis. Every rebuilt mode file (20 of 21; `spatial-reasoning.md` preserved) carries 8 new `###` subsections inside the existing 11 `##` sections: Depth cascade cues, Breadth cascade cues, Consolidator guidance, Focus for this mode, Suggestion templates per criterion, Known failure modes to call out, Verifier checks for this mode, Reviser guidance per criterion. `boot.py::build_system_prompt_for_gear(step=...)` dispatches per pipeline step (analyst / evaluator / reviser / verifier / consolidator) via `_extract_section` + `_extract_subsection` helpers. `mode_success_criteria.check_evaluator_output_shape` validates the universal evaluator contract (E1-E7). Four live cascade structural tests pass on Gemini 2.5 Flash (analyst→evaluator, →reviser, →verifier, and Gear 4 →consolidator). **Tier A analyst-stage live sweep:** 7/18 at 100%, 5 marginal at 88.9% (runs=3 variance), 6 residual below 90% — driven by structural classes (envelope absence, adversarial quality, composite semantic) not cascade-subsection-fixable. Gate relaxed to ≥ 88.9% at runs=3 with documented residuals per Cascade Plan §13. Python tests: 446 (was 417). JS tests: 715 (unchanged). **Next work: Phase 6 — cascade-aware harness + pipeline-function refactor + Tier B/C validation.** Driving plan: `~/Documents/vault/Working — Framework — Pipeline Cascade Integration Plan.md`. Handoff: `~/Documents/vault/Working — Framework — Phase 5 Handoff.md`.

- **Mode Specification Rebuild — Phase 7 Reviser Short_alt Fix + DUU Caption Resolution + Tier B/C Validation (2026-04-18 / 2026-04-19)** — Closed the two residuals Phase 6 surfaced plus the Tier B/C validation originally scoped for the Rebuild Plan. (1) Universal short_alt preservation bullet added to every rebuilt mode's `### Reviser guidance per criterion` subsection — closes the Phase 6 reviser-introduced short_alt overflow regression. Track 1 target mean Δ = +15pp (synthesis 73.3% → 86.7%, CB 66.7% → 80.0%, CS 66.7% → 93.3%, TM 93.3% → 100%). Full 18-mode mean Δ = +3.65pp; ≥ 88.9% clearance 11/18 → 12/18 (CS jumped ✗ → ✓). Two residual failure classes surfaced for Phase 8: reviser meta-commentary S1 (synthesis/CS/DUU/SD) and prose-envelope lockstep (CB C4, SD C3). (2) `orchestrator/visual_adversarial.py::_t7_labelling` + `::_t15_caption_source_n` rewritten with a three-tier fallback (`envelope.caption` string → `spec.caption` dict → flag at `envelope.caption`). Closes the tornado schema-vs-checker mismatch (`specs/tornado.json` forbids `spec.caption`; base envelope schema declares `envelope.caption` as a string) without schema changes. DUU Tier B per-run adversarial rate dropped 60 % (Phase 6 = 1.33/run, Phase 7 = 0.53/run); remainder requires mode-side `envelope.caption` emission guidance (Phase 8 target). (3) New `run_tier_c_pipeline` harness + `--tier-c` CLI flag in `orchestrator/tests/test_mode_emission.py`: chains analyst → evaluator → reviser → verifier (Gear 3) or + consolidator + final-verifier (Gear 4), tracking VERIFIED / VERIFIED WITH CORRECTIONS / VERIFICATION FAILED verdicts per the Phase 5 universal verifier contract. `RunResult` extended with `tier_c_*` fields; `_aggregate` emits `tier_c_verdict_distribution` + `tier_c_verified_rate` when populated (pre-Phase-7 JSON shape preserved). `_classify_verdict` + `_extract_default_gear` helpers with unit test coverage (`TestPhase7TierCHelpers` + `TestPhase7AggregateTierCFields` + `TestPhase7CaptionFallback`). `TestBuildSimulatedSystemPromptEmitLast` substring-anchor fix (Phase 7 reviser bullet mentions `## EMISSION CONTRACT` in prose). Tier C 6-mode sweep: verifier verdict distribution across 54 runs = 45 VERIFIED + 5 VERIFIED_WITH_CORRECTIONS + 1 VERIFICATION_FAILED + 3 UNKNOWN; UNKNOWN is all Gear 4 and surfaces a verifier-contract-drift class for Phase 8. Python tests: 493 (was 479; +14 new). JS tests: 715 (unchanged). **Driving plan:** `~/Documents/vault/Working — Framework — Pipeline Cascade Integration Plan.md` §13. **Handoff:** `~/Documents/vault/Working — Framework — Phase 7 Handoff.md`. **Next work:** Phase 8 — reviser meta-commentary fix + universal prose-envelope lockstep bullet + envelope.caption emission guidance + verifier contract-adherence tightening.

- **Mode Specification Rebuild — Phase 6 Cascade-Aware Validation + Pipeline Refactor (2026-04-18)** — Phase 5's cascade architecture made measurable end-to-end and wired into production. New `run_cascade_tier_a(mode_name, ...)` in `orchestrator/tests/test_mode_emission.py` chains analyst→evaluator→reviser, extracts the reviser's `## REVISED DRAFT`, and runs the same `spec.structural()` + `spec.composite()` checkers the analyst-only harness applies. `RunResult` extended with `cascade_stage` + prior-stage excerpts + `adversarial_block_detail` (full `Finding.as_dict()` records, not just count) + `envelope_retry_used`. `_extract_revised_draft` parses the Phase 5 reviser mirror contract (stops at `## CHANGELOG`, not any `##`, so revised prose can carry its own headings). `--cascade` and `--envelope-retry` CLI flags land the two new execution paths; `ORA_TIER_A_EMIT_LAST` env var enables the prompt-reorder experiment. `run_gear3` / `run_gear4` in `boot.py` refactored to call `build_system_prompt_for_gear(step=...)` via shared `_assemble_step_prompt` / `_rag_tail` / `_verifier_passed` helpers — the cascade now reaches production; Gear 3's Step-6 verifier loads `f-verify.md` for the first time. PE got a new iter-2 pre-emission short_alt verification bullet; the Phase-5 "unparseable envelope" residual turned out to be the short_alt overflow class all along. **Cascade-aware Tier A sweep:** 11/18 modes ≥ 88.9% (vs 8/18 analyst-only at the same threshold) — PE, DC, SP, CM, SI each lifted +4–11pp by the cascade. But synthesis, CB, and CS cascade-regress by −20+pp because the reviser re-emits the envelope with fresh short_alt overflows — a new Phase 7 target. DUU T7/T15 adversarial firings diagnosed as a schema-vs-adversarial mismatch (`specs/tornado.json` disallows `spec.caption` but `_t7_labelling` requires `spec.caption.source/period/n`) — accepted as known residual, to be resolved Phase 7. Emit-last prompt reorder on CS: −6.7pp (hypothesis not supported). Python tests: 479 (was 446; +33 new). JS tests: 715 (unchanged). **Driving plan:** `~/Documents/vault/Working — Framework — Pipeline Cascade Integration Plan.md`. **Handoff:** `~/Documents/vault/Working — Framework — Phase 6 Handoff.md`. **Next work:** Phase 7 — reviser short_alt preservation fix + DUU caption resolution + Tier B/C validation.

## Commands

```bash
# Start terminal orchestrator
./start.sh

# Start chat server (localhost:5000)
./start.sh

# Run visual-compiler JS test harness (jsdom-based)
cd ~/ora/server/static/ora-visual-compiler/tests && node run.js

# Run Python server-side test suite (visual + pipeline)
cd ~/ora && /opt/homebrew/bin/python3 -m unittest discover -s orchestrator/tests

# Render an envelope → SVG from the command line
echo '<envelope-json>' | node ~/ora/server/static/ora-visual-compiler/tools/render-envelope.js > out.svg

# Export a session to vault with SVG sidecars
/opt/homebrew/bin/python3 -c "from orchestrator.vault_export import export_session_to_vault; print(export_session_to_vault('<conversation_id>'))"

# Index mental models into ChromaDB
/opt/homebrew/bin/python3 ~/ora/orchestrator/tools/knowledge_index.py ~/ora/knowledge/mental-models/

# Reindex (clear + rebuild)
/opt/homebrew/bin/python3 ~/ora/orchestrator/tools/knowledge_index.py --reindex ~/ora/knowledge/mental-models/
```
