# Conversation Processing Pipeline

## Display Name

Conversation Processing (CPP)

## Display Description

Processes raw conversation exports (Claude, ChatGPT, Gemini) and live Ora exchanges into structured turn-pair chunks indexed in ChromaDB. Batch mode also produces a persistent cleaned-pair archive at ~/Documents/Commercial AI archives/ with per-pair semantic cleanup, pasted-segment classification, and engagement-wrapper stripping. Use for fresh chats from phone, web, or any commercial AI service.

_v2.1 update (2026-07-10): Model-agnostic execution + cleanup hardening. All model references removed from this framework — cleanup calls route by size to a "light" or "heavy" tier, and a pluggable backend (selected at invocation: `api`, `claude-cli`, or `ora-slots`) resolves tiers to whatever the routing configuration serves; this framework never names models. Cleanup prompts v2: a never-refuse rule (any input the model is unsure about is returned verbatim), dictation word-lock correction (similar-sounding wrong words fixed from context), and explicit pronoun-referent resolution. New deterministic Refusal Guard after every cleanup call: output that reads as model commentary about the input (rather than the cleaned input itself) is discarded, the original text is preserved, and the event is logged to `~/ora/data/cleanup-guard.log`. Closes the Refusal Leak failure mode discovered 2026-07-10 (~700 archive pairs corrupted by persisted refusals during the historical run). Historical raw exports now live at `~/Documents/Raw Chat Archive/raw/` (relocated after the one-time run); `~/Documents/conversations/raw/` remains the live input directory for new imports._

_v2.0 update (2026-05-17): Batch mode overhauled to match the historical-reprocessing architectural pivot of 2026-04-30. Cleaned-pair layer is now the primary batch deliverable; chunk extraction is a downstream consumer. Adds per-pair semantic cleanup with model routing, pasted-segment 4-bucket classification with vault-index lookup, and the strict engagement-wrapper strip rule. New Layer 2.5 inserted between format normalization and chunking. Inline mode unchanged. Runnable implementation already exists in `~/ora/orchestrator/historical/` and was used for the one-time historical archive run (39,081 pairs, $510 cost, 99.9% success)._

_v1.1 (2026-03-31): dual-mode architecture — inline processing for ongoing conversations (primary), batch processing for imports only. Inline processing executes as part of the output delivery step, eliminating overnight batch dependency for ongoing work._

---

## Setup Questions

### Mode

Required for picker invocation. Which path the framework runs: `inline` (automatic — invoked by the orchestrator on every Ora session turn) or `batch` (manual — process commercial AI exports). The framework picker normally invokes batch; inline runs without picker involvement as part of the orchestrator's output delivery step.

### Input source — for batch mode

Required for batch mode. Either the default directory (`~/Documents/conversations/raw/`) or an explicit path containing exported chat files. Multiple files supported. The implementation auto-detects format (Claude Web Clipper, ChatGPT export, Gemini export, local-Ora session log).

### Date filter — for batch mode

Optional. `--from-date YYYY-MM-DD` and/or `--to-date YYYY-MM-DD` to scope processing to a date range based on parsed chat metadata. Defaults to all unprocessed files in the input directory.

### Cleanup tier — for batch mode

Optional. `full` (default — runs the full apparatus: pasted-segment classification + per-pair semantic cleanup + engagement strip + cleaned-pair archive write) or `light` (engagement strip only; no cleanup pass; legacy CPP v1.x behavior). Defaults to `full`.

### Backend — for batch mode

Optional. Which model-call path serves the cleanup tiers: `api` (metered API access via stored key — default), `claude-cli` (billed to the operator's chat subscription via the local CLI), or `ora-slots` (Ora's own slot routing; the routing configuration decides what serves each tier). This framework is backend-agnostic and never names models — tier-to-model resolution belongs entirely to the selected backend.

### Concurrency — for batch mode

Optional. `--max-workers` (per-file parallelism) and `--file-workers` (cross-file parallelism). Default values are the ones locked during the historical run: `--max-workers 8 --file-workers 12`. Override only if rate-limit telemetry indicates different capacity. The `claude-cli` backend caps per-file workers at 3 automatically — higher parallelism only thrashes subscription rate windows.

---

## Intake Protocol

### For inline mode

Inline mode runs without intake — the orchestrator invokes it as part of the output delivery step after every model response. No user-facing intake step.

### For batch mode

Before processing:

1. **Restate the scope.** Confirm the input directory and date range. State the expected file count and pair count estimate.

2. **Confirm cleanup tier and backend.** State whether full apparatus or light mode will run, which backend serves the model calls, and the cost model (per-token for `api` — ~$0.013 per pair at the historical run's rates; subscription-billed for `claude-cli`; the slot endpoint's own accounting for `ora-slots`; near-zero at light tier on any backend).

3. **Confirm concurrency.** State the worker counts. Flag if rate-limit capacity has changed since the last run.

4. **Verify environment.** Confirm `~/Documents/Commercial AI archives/` exists, the manifest at `~/ora/data/cleanup-manifest.json` is loadable, the vault index at `~/ora/data/vault-index.json` is fresh (rebuild if vault content has changed since last index build), and the selected backend's access resolves (stored key for `api`; logged-in CLI for `claude-cli`; configured slots for `ora-slots`).

5. **Announce the plan.** Get explicit user approval before launching, especially for runs >100 files or >$5 estimated cost.

---

## PURPOSE

This framework processes conversations into structured turn-pair chunks ready for RAG retrieval. **Batch mode** (commercial AI imports) additionally produces a persistent, semantically-preserved cleaned-pair archive at `~/Documents/Commercial AI archives/`, which serves as the primary deliverable for imports — downstream extractions (chunks, news outlines, resource notes, atomic notes) consume the cleaned layer rather than the raw exports. **Inline mode** processes live Ora exchanges immediately as part of the output delivery step.

The cleaned-pair layer exists for two reasons: (1) cleanup is expensive; downstream extractions should iterate cheaply on cleaned material rather than re-cleaning; (2) the cleaned archive is the user's permanent record of intellectual history, with raw exports kept for re-mining but no longer the active surface.

This pipeline is distinct from the Data Formulation Pipeline / Document Processing framework, which processes documents and research for the vault.

**This pipeline operates in two modes:**

- **Inline mode (primary, automatic):** Processes each prompt-response pair immediately after the model delivers its response, as part of the output delivery step. The exchange is appended to the session's raw log, written as a processed chunk file, and indexed into ChromaDB before the system accepts the next user input. This means conversation RAG has access to every exchange in the current session — including the one that just completed. Inline mode does not run the cleanup apparatus — live exchanges are already structured and well-formed.

- **Batch mode (imports, on demand):** Processes files dropped into `~/Documents/conversations/raw/` — commercial AI exports (Claude, ChatGPT, Gemini) and any other captured chats from phone, web, or external sessions. Batch mode runs the full cleanup apparatus by default, producing cleaned-pair files in `~/Documents/Commercial AI archives/` and then chunk files in `~/Documents/conversations/`. The runnable implementation is `python3 -m orchestrator.historical.cli` (see `~/ora/orchestrator/historical/` subpackage). Batch invocation is always manual; there is no automatic overnight batch.

## INPUT CONTRACT

**Inline mode inputs:**
- The prompt-response pair that just completed: user prompt (full text), assistant response (full text), timestamp (current), model identifier, session ID, turn index within the current session.
- The current session's raw log file path (for appending).
- Source: provided by the orchestrator (boot.py) as part of the output delivery step.

**Batch mode inputs:**
- Unprocessed conversation files in `~/Documents/conversations/raw/` (or explicit input path). Source: user export from commercial AI services (Claude.ai JSON or Web Clipper markdown, ChatGPT export, Gemini export), or local-Ora session logs.
- Processing manifest: `~/ora/data/cleanup-manifest.json` (created and maintained by this pipeline). Resumable — files marked complete in the manifest are skipped on re-runs.
- Vault index: `~/ora/data/vault-index.json` (built by `orchestrator.tools.vault_indexer`). Used during Layer 2.5 pasted-segment classification to detect earlier-draft material.
- Model access for the cleanup pass at `full` tier — one of, per the selected backend: a stored API key (macOS keyring `ora` / `anthropic-api-key`) for `api`; a logged-in local CLI for `claude-cli`; configured Ora slots for `ora-slots`.

Optional (both modes):
- Existing ChromaDB conversations collection. Source: `~/ora/chromadb/`. Default behavior if absent: pipeline creates the collection and indexes all processed chunks.

## OUTPUT CONTRACT

Primary outputs:

- **(Batch mode, full tier)** Cleaned-pair markdown files written to `~/Documents/Commercial AI archives/`. One file per turn pair, flat directory, filename convention `YYYY-MM-DD_HH-MM_keyword-keyword-keyword.md`. Each file carries `type: cleaned-pair` YAML frontmatter with source provenance (source_chat, source_pair_num, source_platform, source_timestamp, thread_id, prior_pair, next_pair, processing_model, processed_at). Body contains multi-level context header (session + pair), cleaned user input with pasted-segment classification annotations, cleaned assistant response with engagement-strip log. **This is the primary batch-mode deliverable** — raw exports can eventually be deleted once the cleaned archive is validated.

- **(Both modes)** Processed turn-pair chunk files written to `~/Documents/conversations/`. Each file contains one prompt-response pair with contextual header, topic metadata, timestamps, and provenance tag. Format: Markdown with YAML frontmatter. Quality threshold: every chunk is self-contained — a reader or retrieval system encountering the chunk in isolation can understand the exchange without needing the full conversation.

Secondary outputs (both modes):
- Updated ChromaDB conversations collection with embeddings for all new chunks. Each entry carries timestamp metadata for recency queries and semantic content for similarity queries.

Additional outputs (inline mode):
- Updated session raw log at `~/Documents/conversations/raw/[session-id].md` with the new exchange appended.

Additional outputs (batch mode):
- Updated cleanup manifest at `~/ora/data/cleanup-manifest.json` recording every file processed, pair-level success/failure counts, model used per pair, and cumulative cost in USD.
- Engagement-strip audit log appended at `~/ora/data/engagement-strips.log` (JSONL — one record per stripped paragraph with source_path, pair_num, paragraph text, length, sanitized prefix).
- Processing summary: count of files processed, pairs succeeded / errored, total cost.

**Not produced by default:**
- News outlines, resource notes, or atomic notes. These are downstream consumers of the cleaned-pair layer, owned by their own frameworks or pipelines (see Downstream Consumers below).

## EXECUTION TIER

**Inline mode:** Orchestrator. This pipeline executes as part of the orchestrator's output delivery step — after the model produces a response and before the system accepts the next user input. Processing a single exchange inline must complete in under two seconds to avoid perceptible delay. The inline path runs Layers 3 and 4 only (semantic chunking, header generation, write, and indexing) because the prompt-response pair is already normalized — it comes directly from the orchestrator, not from a file that needs format detection and parsing, and not from a commercial export that needs cleanup.

**Batch mode:** Agent. This pipeline runs on demand for processing imported conversation files. The runnable implementation lives in `~/ora/orchestrator/historical/`, invoked via `python3 -m orchestrator.historical.cli`. Stage boundaries represent actual context window resets to prevent context debt accumulation across many files. Batch mode runs Layers 1 through 6 including the inserted Layer 2.5.

Available tools (batch mode):
- file_read: Read raw conversation files, cleaned-pair files, and existing chunk files.
- file_write: Write cleaned-pair files, chunk files, and manifest updates.
- file_list: Enumerate files in input and output directories.
- chromadb_index: Add entries to the conversations collection.
- model_client: Per-segment cleanup calls through the selected backend — light tier for ≤30K-token segments, heavy tier for >30K. Tier-to-model resolution belongs to the backend and routing configuration, never to this framework.
- local_endpoint_dispatch: Optional fallback to local slot endpoints via `orchestrator.boot.call_local_endpoint`.

The single batch-mode milestone covers Layers 1–6 (now seven processing layers counting 2.5). Per the Process Formalization Framework Section II §2.3, this single-milestone-for->5-layer-modes design is justified by the integration of the chunk pipeline: cleanup, segment classification, format detection, semantic chunking, header generation, write, and indexing must all complete before the chunk-set is queryable, and intermediate states would represent un-indexed, un-cleaned, or un-headered chunks unsafe to commit to ChromaDB.

---

## MILESTONES DELIVERED

This framework's declaration of the project-level milestones it can deliver. Used by the Problem Evolution Framework (PEF) to invoke this framework for milestone delivery under project supervision. Inline mode is invoked automatically by the orchestrator on every session turn and is not PEF-selectable; it behaves as a pipeline stage per the exemption in PFF Section II subsection 2.3. Only batch mode produces a project-level milestone and is declared below.

### Milestone 1: Cleaned-Pair Archive with Chunk Extraction and ChromaDB Indexing

- **Mode:** batch
- **Endpoint produced:**
  (a) A set of cleaned-pair markdown files in `~/Documents/Commercial AI archives/`, one per turn pair, with `type: cleaned-pair` frontmatter, multi-level context header, semantically-preserved cleaned user input (pasted segments classified into 4 buckets and annotated), and cleaned assistant response (engagement wrapper stripped per the strict 5-step rule).
  (b) A set of processed turn-pair chunk files in `~/Documents/conversations/` derived from the cleaned-pair files (or directly from normalized turn pairs at `light` tier), each with YAML frontmatter (source_file, source_platform, model_used, timestamp, conversation_title, turn_range, topics, chunk_id, agent_id), a 2–4 sentence contextual header, and the full user/assistant exchange.
  (c) Corresponding entries in the ChromaDB conversations collection (document content, metadata, embedding derived from contextual header + user prompt).
  (d) Updated cleanup manifest at `~/ora/data/cleanup-manifest.json` recording every file processed in the run.
  (e) Appended engagement-strip audit log at `~/ora/data/engagement-strips.log`.

- **Verification criterion:**
  (a) every raw file in the batch's input set is either represented in the updated manifest as completed (with cleaned-pair file count and chunk count), or listed as errored with a reason (unrecognized format, parser failure, or API exhaustion);
  (b) every cleaned-pair file has a unique `(source_chat, source_pair_num)` combination and valid YAML frontmatter that parses programmatically;
  (c) every chunk file has a unique chunk_id with no collisions;
  (d) ChromaDB conversations collection entry count increases by exactly the number of new (non-duplicate) chunks written, with embeddings generated from contextual header + user prompt per the Embedding Dilution failure mode;
  (e) cleaned-pair files belonging to the same source file form a coherent thread (prior_pair / next_pair links are consistent and form a chain without orphans or cycles);
  (f) all ten Evaluation Criteria score 3 or above against the produced cleaned-pair files (criteria 8–10) and chunks (criteria 1–7).

- **Layers covered:** 1, 2, 2.5, 3, 4, 5, 6
- **Required prior milestones:** Vault index built (`orchestrator.tools.vault_indexer` has produced a current `vault-index.json`).
- **Gear:** 4
- **Output format:** Set of cleaned-pair markdown files + set of chunk markdown files with structured YAML frontmatter + ChromaDB collection updates + manifest JSON + appended audit log.
- **Drift check question:** Does every input file in the batch produce either a cleaned-pair set or a documented skip reason; do the cleaned-pair files faithfully preserve the thought content of the originals without lossy summarization; and do the chunks reflect the cleaned layer accurately?

---

## EVALUATION CRITERIA

This framework's output is evaluated against these 10 criteria. Each criterion is rated 1-5. Minimum passing score: 3 per criterion. Criteria 1–7 apply to all chunks (both modes). Criteria 8–10 apply only to batch-mode cleaned-pair files at `full` tier.

1. **Chunk Self-Containment**
   - 5: Every chunk is fully comprehensible in isolation. The contextual header provides sufficient background that neither the preceding nor following conversation is needed to understand the exchange.
   - 4: Chunks are comprehensible in isolation. Rare references to prior context exist but do not impair understanding.
   - 3: Chunks are generally self-contained. Occasional references to "as discussed above" or similar without sufficient context, but the core exchange is clear.
   - 2: Multiple chunks depend on conversation context not included in the chunk.
   - 1: Chunks are excerpts, not self-contained units. Most require the full conversation to interpret.

2. **Semantic Boundary Accuracy**
   - 5: Every chunk boundary falls at a natural topic transition. No chunk spans two unrelated topics. No topic is split across chunks in a way that loses coherence.
   - 4: Chunk boundaries are semantically clean. One or two boundaries fall at suboptimal points but content is not lost.
   - 3: Most boundaries are reasonable. Some chunks contain minor topic bleed from adjacent exchanges.
   - 2: Multiple chunks have boundaries that split a coherent exchange or merge unrelated exchanges.
   - 1: Chunking appears mechanical (fixed-length or fixed-count) rather than semantic.

3. **Metadata Accuracy**
   - 5: Every timestamp is correct and in ISO 8601 format. Every topic tag accurately reflects the chunk's content. Provenance source is correctly identified.
   - 4: Metadata is accurate throughout with minor formatting inconsistencies.
   - 3: Metadata is functional. Timestamps are present and correct. Topic tags are reasonable approximations.
   - 2: One or more metadata fields contain errors that would affect retrieval accuracy.
   - 1: Metadata is missing or systematically incorrect.

4. **Contextual Header Quality**
   - 5: The contextual header establishes the conversation's topic, the user's intent, and any relevant prior context in two to four sentences. Reading the header alone tells you what this exchange is about.
   - 4: Header establishes topic and intent. Slightly more or less context than ideal.
   - 3: Header identifies the topic. Intent or prior context could be clearer.
   - 2: Header is generic or formulaic — does not meaningfully orient the reader.
   - 1: Header is absent or a simple filename echo.

5. **Deduplication**
   - 5: No chunk duplicates content already in `~/Documents/conversations/` from a prior processing run. The manifest is checked before processing and updated after.
   - 4: No duplicates. Manifest is maintained correctly.
   - 3: No duplicates detected. Manifest is present but incomplete.
   - 2: One or more duplicate chunks produced due to manifest gap.
   - 1: Systematic duplication — files are reprocessed without manifest checking.

6. **Format Consistency**
   - 5: Every chunk file follows identical YAML frontmatter structure, identical header format, identical body format. A script could parse them programmatically without exception handling.
   - 4: Format is consistent. One or two files have minor deviations that do not affect parsing.
   - 3: Format is generally consistent. Occasional deviations require minor tolerance in parsing.
   - 2: Multiple format inconsistencies that would require exception handling.
   - 1: No consistent format across chunk files.

7. **Information Preservation**
   - 5: Every substantive exchange in the raw file is represented in the output chunks. No information is lost. Mechanical exchanges (greetings, acknowledgments with no content) are appropriately excluded.
   - 4: All substantive exchanges preserved. One or two borderline exchanges excluded that arguably had content value.
   - 3: Most substantive exchanges preserved. A few were lost at chunk boundaries or during filtering.
   - 2: Noticeable information loss — substantive exchanges are missing from the output.
   - 1: Significant portions of the conversation are not represented in any output chunk.

8. **Cleanup Fidelity (batch mode, full tier)**
   - 5: Cleaned user input preserves 100% of thought content from the original. Words, phrases, and grammar are freely changed; implied items made explicit; filler, transcription errors, and rambling stream-of-consciousness tightened. No semantic loss; the cleaned input may bear no surface resemblance to the original wording — only the thought survives.
   - 4: Faithful preservation. Rare cases where a nuance is reduced.
   - 3: Generally faithful. Occasional minor compression of a tangent.
   - 2: Multiple cases of semantic loss — thoughts dropped or distorted.
   - 1: Cleanup is summarization, not preservation.

9. **Pasted-Segment Classification (batch mode, full tier)**
   - 5: Every pasted segment correctly classified into one of the four buckets (news-article / opinion-piece / resource / earlier-draft). Vault-index lookup correctly catches earlier-draft material. Vault override correctly reclassifies misflagged personal segments.
   - 4: Classification accurate with rare misclassifications that don't affect downstream routing.
   - 3: Most segments correctly classified. Occasional borderline calls on the news-vs-opinion or resource-vs-other boundaries.
   - 2: Multiple misclassifications that affect downstream extraction routing.
   - 1: Classification is random or systematically wrong.

10. **Engagement-Strip Precision (batch mode, full tier)**
    - 5: All trailing engagement wrappers stripped per the strict 5-step rule; URL/code pre-stripping prevents false positives from query-string or code `?` characters; every removal logged to the audit JSONL.
    - 4: Aggressive stripping per the locked rule; rare false positives accepted per user policy.
    - 3: Engagement strip applied per rule. Some borderline strips on responses ending with rhetorical questions.
    - 2: Multiple false positives strip substantive content with embedded questions.
    - 1: Engagement strip not applied or systematically wrong.

---

## INLINE MODE PROCESSING

This section describes the processing path for ongoing conversations — every exchange processed immediately as part of the output delivery step. This is the primary operating mode. Batch mode (Layers 1–6 below) is used only for imports.

### Inline Processing Sequence

After the model delivers its response, the orchestrator executes these three steps before accepting the next user input:

**Step 1 — Append to Session Raw Log**

Append the prompt-response pair to the current session's raw log file at `~/Documents/conversations/raw/[session-id].md`. The raw log is one file per session, appended throughout. It is the audit trail and the source for reprocessing if the extraction algorithm improves.

Format for each appended entry:
```markdown
---

**Timestamp:** [ISO 8601]
**Model:** [model identifier]
**Turn:** [turn index within session]

**User:**

[User's prompt, full text]

**Assistant:**

[Assistant's response, full text]
```

The session ID is generated at session start (e.g., `2026-03-31_session-a7f3`). The raw log filename matches the session ID.

**Step 2 — Generate Processed Chunk File**

Generate the contextual header and topic tags for this exchange, then write the processed chunk file to `~/Documents/conversations/`. This step applies the same chunking and header logic as Layer 3 (Semantic Chunking and Contextual Header Generation) below, but operates on a single exchange rather than a full conversation file.

For inline processing, the contextual header is generated by the model that just produced the response — it adds minimal latency because the model already has full conversational context. The orchestrator appends a post-response instruction: "Generate a 2–4 sentence contextual header summarizing what this exchange is about, what the user was trying to accomplish, and any relevant prior context. Also provide 1–3 topic tags as short descriptive phrases." The model returns the header and tags, which the orchestrator uses to assemble the chunk file.

Chunk filename format:
```
YYYY-MM-DD_HH-MM_session-[short-id]_pair-[NNN]_[topic-slug].md
```

Example: `2026-03-31_14-23_session-a7f3_pair-004_model-switching.md`

Chunk file format: identical to the format specified in Layer 3 below, including YAML frontmatter with all metadata fields.

For inline mode, the `source_platform` is always `local` and the `source_file` references the session raw log.

**Step 3 — Index into ChromaDB**

Add the chunk to the ChromaDB conversations collection with:
- Document content: the full chunk text (header + exchange)
- Metadata: all YAML frontmatter fields, especially timestamp (for recency queries) and topics (for semantic queries)
- Embedding: generated from the contextual header + user prompt only (not the full assistant response — see Named Failure Mode: The Embedding Dilution)

After Step 3 completes, the exchange is fully processed. The next query in the same session can retrieve it via conversation RAG.

### Inline Mode Performance Constraint

The three-step inline sequence must complete in under two seconds total. The bottleneck is Step 2 (header generation), which requires a model call. Strategies to meet this constraint:

- Use the sidebar model (smallest, fastest) for header generation rather than the model that produced the response.
- If header generation exceeds the time budget, write the chunk file with a placeholder header and queue the header for asynchronous generation. The chunk is still indexed immediately with the user prompt as the embedding source (which is the primary embedding content regardless). The header is backfilled when the model completes.
- Step 1 (file append) and Step 3 (ChromaDB indexing) are I/O operations that complete in milliseconds.

---

## BATCH MODE PROCESSING

The following layers (1 through 6, including the inserted Layer 2.5) describe the batch processing path for imported conversation files — commercial AI exports and any captured chats from phone, web, or external sessions. Batch mode is triggered manually when the user drops files into `~/Documents/conversations/raw/` (or a specified input directory) and runs `python3 -m orchestrator.historical.cli`. It is not an automatic overnight process.

---

## LAYER 1: INVENTORY AND MANIFEST CHECK

**Stage Focus**: Identify which raw files need processing by comparing the input directory against the cleanup manifest. This layer runs in batch mode only — inline mode skips directly to chunk generation.

### Processing Instructions

1. Read the cleanup manifest from `~/ora/data/cleanup-manifest.json`. IF the manifest does not exist, THEN create an empty manifest and treat all input files as unprocessed.
2. List all files in the input directory (default `~/Documents/conversations/raw/`, or path from `--input` flag).
3. Compare the file list against the manifest. A file needs processing IF:
   - It does not appear in the manifest's `completed_files`, OR
   - It is in `errored_files` and the user has explicitly requested retry, OR
   - Its modification date is newer than the manifest's recorded processing date for that file.
4. For each file needing processing, identify the source format via the parser's auto-detection:
   - Claude Web Clipper markdown (most common; ~96% of historical archive)
   - Claude.ai JSON export
   - ChatGPT export (conversations.json with ChatGPT schema)
   - Gemini export (uses `<details>/<summary>` HTML wrappers and frequently omits `👉` role separators — handled by the parser)
   - Local-Ora session log (Markdown with timestamp headers)
   - Unknown format — flag for manual review, do not attempt processing.
5. Apply date filter (`--from-date` / `--to-date`) if specified, using the chat's parsed `created_at` metadata rather than the file's filesystem date.
6. Sort unprocessed files chronologically (newest first by default; matches the historical-reprocessing order locked 2026-04-30).

### Output Formatting for This Layer

Processing queue: ordered list of files with source format identified and byte size noted. Summary count: N files to process, N already processed, N unrecognized.

Before proceeding: confirm that the primary objective (processing raw conversations into the cleaned-pair archive and chunks) has not shifted and that the manifest has been correctly loaded or created.

---

## LAYER 2: FORMAT NORMALIZATION

**Stage Focus**: Convert each source format into a common intermediate representation — a sequence of timestamped turn pairs (user prompt, AI response) with source metadata. Implementation: `~/ora/orchestrator/historical/parser.py`.

**This layer executes once per file in the processing queue. Context window resets between files to prevent cross-file contamination.**

### Processing Instructions

For each file in the processing queue:

1. Read the file via file_read.
2. Parse according to identified source format:

**Claude Web Clipper markdown:**
- Strip the wrapper preamble and Title field (note: the parser uses `[ \t]*` rather than `\s*` for inner whitespace to avoid the empty-Title-field title pollution bug surfaced 2026-05-01).
- Walk turn boundaries; each user message + subsequent assistant message = one turn pair.

**Claude.ai JSON export:**
- Extract each conversation as a sequence of human/assistant message pairs.
- Preserve conversation-level metadata: title (if present), creation timestamp, model used.
- IF multiple assistant responses exist for one human message (regenerations), THEN use the final response only.

**ChatGPT export:**
- Extract conversations from the messages array.
- Each user/assistant pair = one turn pair.
- When ChatGPT emits search → tool_call → final_answer, merge the three assistant turns into one `assistant_content` separated by `\n\n`. Cleanup phase prunes the search-call noise.
- Preserve conversation title, creation time, model.

**Gemini export:**
- Strip `<details>/<summary>` HTML wrapper blocks pre-parse.
- The `👉` role separator is often omitted — the turn regex treats it as optional.
- Preserve title, creation time, model.

**Local-Ora session log (Markdown):**
- Parse timestamp headers and user/assistant blocks.
- Each timestamped exchange = one turn pair.
- Preserve session start time and model endpoint used.

3. Output: sequence of normalized turn pairs (`RawPair` objects per the parser's data model), each carrying:
   - user_message: the user's prompt (full text)
   - assistant_message: the AI's response (full text)
   - timestamp: ISO 8601 (from source metadata; if unavailable, use file creation date)
   - source_file: filename in raw/
   - source_platform: claude | chatgpt | gemini | local-ora | other
   - model_used: model identifier if available, "unknown" if not
   - conversation_title: if available from source metadata
   - turn_index: position within the original conversation (1-indexed)
   - total_turns: total number of turns in the original conversation

**Named failure mode — The Encoding Trap:** Raw exports from different platforms use different Unicode encodings, line ending conventions, and JSON escaping schemes. Normalize all text to UTF-8 with Unix line endings during this layer. Smart quotes, em dashes, and non-ASCII punctuation are preserved in content but must be valid UTF-8.

### Output Formatting for This Layer

Normalized turn-pair sequence as a structured list. Each entry contains all fields enumerated above. This intermediate representation is consumed by Layer 2.5 (full tier) or directly by Layer 3 (light tier), and discarded after processing completes.

Before proceeding: confirm that the number of extracted turn pairs is plausible given the source file size. IF zero turns were extracted from a non-empty file, THEN the parser failed — flag the file and skip to the next file in the queue.

---

## LAYER 2.5: PER-PAIR CLEANUP AND CLASSIFICATION

**Stage Focus**: Per-pair semantic cleanup, pasted-segment 4-bucket classification with vault-index lookup, engagement-wrapper strip, and cleaned-pair file write. This layer is the architectural heart of the batch pipeline at `full` tier — it produces the persistent cleaned-pair archive that downstream layers and downstream frameworks consume.

**This layer executes once per turn pair (not per file). Pair-level parallelism via `--max-workers`; file-level parallelism via `--file-workers`. Context resets between turn pairs.**

**Skip condition:** At `light` tier, Layer 2.5 reduces to Step 5 (engagement strip) only; Steps 1–4 and 6–8 are bypassed, normalized turn pairs flow directly to Layer 3.

### Processing Instructions

For each normalized turn pair from Layer 2:

**Step 1 — Segment user input into personal text and pasted blocks.**

Implementation: `~/ora/orchestrator/historical/paste_detection.py`.

1. Split `user_message` on blank lines into blocks.
2. Per-block, detect paste signals: markdown headings, code fences, blockquotes, citation patterns (`(Smith 2024)`, `[1]`, `doi:`), byline / dateline, structured lists, length combined with low first-person-pronoun density.
3. Strong signals → pasted. ≥2 weak signals → pasted. Otherwise personal.
4. **Smoothing pass:** continuation paragraphs (no personal voice + sandwiched between paste blocks or trailing one) reclassify as paste continuation.
5. Merge adjacent same-kind blocks into Segments.

**Step 2 — Classify pasted segments into four buckets.**

For each pasted segment:

- **Vault-index lookup first.** Hash the segment's paragraphs and check overlap against `~/ora/data/vault-index.json` (built by `orchestrator.tools.vault_indexer`). If overlap above threshold (default 50%), classify as `earlier-draft` with vault metadata (matched vault_id, vault_path, overlap percentage).
- **Otherwise apply heuristic scoring:**
  - **news-article** — bylined + dateline + third-person reportage + headline structure. Routes to news extraction (downstream) with fact-filtering.
  - **opinion-piece** — signed personal voice + first-person opinion frame ("I think...", "the case for X...", "why X is wrong"). Routes to news extraction without fact filter; user comments preserved as context for downstream reaction extraction.
  - **resource** — structured H1/H2 headings + citation patterns + length >1,000 words. Routes to resource extraction via Document Processing framework HCP.
  - **earlier-draft** (caught above by vault lookup) — mention-only, not extracted.
  - **other** — pasted but doesn't match the above; preserved verbatim with no downstream routing.

**Vault override on personal segments:** a segment classified as `personal` by Step 1 that nonetheless matches vault content (e.g., fiction with first-person dialogue that fooled the personal-voice heuristic) reclassifies to `pasted/earlier-draft`.

**Final merge pass:** adjacent same-classification + same-vault-id segments merge.

**Step 3 — Route personal segments to the cleanup tier.**

Implementation: `~/ora/orchestrator/historical/pair_cleanup.py` + `model_router.py` + `cleanup_backends.py` (+ `api_client.py` for the `api` backend).

For each personal segment, route by input token count:
- **≤30K tokens → light cleanup tier.** Fast, parallelizable; handles typical pairs.
- **>30K tokens → heavy cleanup tier.** Required for stream-of-consciousness pairs that exceed the light tier's effective handling; user-locked policy: "capacity matters more than cost."
- Which model serves each tier is decided by the selected backend (`api`, `claude-cli`, or `ora-slots`) and the routing configuration — never by this framework. Long pasted-block-laden pairs may dispatch to local slot endpoints via `call_local_endpoint` if the user has configured local fallback.

Cleanup prompt (templates in `~/ora/orchestrator/historical/prompts.py`, v2 as of 2026-07-10) instructs the model to:
- Preserve 100% of thought content
- NEVER refuse and NEVER comment on the text — if unsure, return the input verbatim; commands, templates, fragments, and lone questions are content, not requests
- Freely change words, phrases, and grammar
- Fix dictation word-locks: similar-sounding wrong words corrected from context (canonical examples: "providence" → "provenance", "residence" → "resonance")
- Resolve unclear pronouns to their explicit referents — a reader seeing only this message should never have to guess what "it" points to
- Make implied items explicit
- Remove filler, transcription errors, rambling stream-of-consciousness
- Tighten where possible

**Refusal Guard (deterministic, after every cleanup call).** The cleaned output is checked against a signature list of role-commentary phrases ("text-cleanup tool", "I cannot process this input", ...). A signature trips only when it appears in the output but NOT in the input — so conversations that legitimately discuss this pipeline never false-positive. On a trip, the original text is preserved unchanged, the pair proceeds normally, and a JSONL record is appended to `~/ora/data/cleanup-guard.log` (env override `ORA_CLEANUP_GUARD_LOG`). A leading "Here is the cleaned text:" framing line is stripped before the check. Worst case under the guard is uncleaned-but-intact text — never the model's commentary.

Pasted segments are never sent to the model — they are preserved verbatim with classification annotations in the cleaned-pair output. This is a load-bearing architectural decision: sending huge pasted segments to the model exhausts output-token budget and stalls. The segment-based architecture eliminated the 30-minute heavy-tier stalls observed during pilot.

**Step 4 — Clean assistant response.**

Format pass + light junk pruning, followed by the same Refusal Guard as Step 3 (a guarded AI-side output falls back to the raw response). Then apply the engagement-wrapper strip (Step 5).

**Step 5 — Engagement-wrapper strip (strict, final).**

Implementation: `~/ora/orchestrator/historical/engagement.py`.

For the cleaned assistant response:

1. Pre-strip URLs (`https?://\S+`), code fences (` ``` ... ``` `), and inline code (`` `...` ``) for the purposes of question detection only — these may contain `?` that are not engagement questions.
2. Identify the **last paragraph**.
3. If it contains any `?` character → delete the entire last paragraph.
4. Repeat from step 2 against the new last paragraph until the new last paragraph contains no `?`.
5. The cleaned response ends at the last question-free paragraph.

Bias intentionally aggressive. User explicitly accepts false-positive losses on the ~1.7% of pairs that lose >50% content. The "reaction in next message" exception described in earlier framework drafts is **not implemented** — wrappers are removed even when answered in subsequent pairs, because they are context not content.

Every stripped paragraph appends to `~/ora/data/engagement-strips.log` (JSONL — source_path, pair_num, paragraph text, length, sanitized prefix).

**Step 6 — Determine thread continuity.**

Implementation: `~/ora/orchestrator/historical/context_header.py`.

Detect topic shift relative to the immediately prior pair in the same source file. Set `prior_pair` and `next_pair` filename links. Topic-continuous pairs form a thread (shared `thread_id` = `thread_<conversation_hash>_<n>`).

**Step 7 — Generate multi-level context header.**

Two paragraphs:
- **Session context** — one paragraph: what the whole conversation was about.
- **Pair context** — one paragraph: what came before, what's at stake at this specific pair.

**Step 8 — Write cleaned-pair file.**

Implementation: `~/ora/orchestrator/historical/writer.py`.

Write to `~/Documents/Commercial AI archives/[filename].md` with the following format:

```yaml
---
nexus:
type: cleaned-pair
date created: <YYYY-MM-DD>           # source date
date modified: <YYYY-MM-DD>          # cleanup date
source_chat: <relative path under conversations/raw/>
source_pair_num: <int>
source_platform: claude | chatgpt | gemini | local-ora | other
source_timestamp: <ISO-8601>
thread_id: thread_<conversation_hash>_<n>
prior_pair: <filename or null>
next_pair: <filename or null>
processing_model: <backend-reported model or slot label>
processed_at: <ISO-8601>
tags: []
---

## Context

### Session context

<one paragraph>

### Pair context

<one paragraph>

## Exchange

### User input

<cleaned user input — semantic preservation, words/phrases freely changed>

#### Pasted segments

- **Segment 1** — type=`opinion-piece`, status=`extract-with-context`
  - Source marker: `### Article: <title or first 60 chars>`
  - Vault index match: none
  - Heuristic flags: bylined, opinion-frame, ~800 words

(Section omitted if no pasted segments.)

### Assistant response

<cleaned assistant response, engagement wrapper(s) stripped>

#### Engagement strip log

- Stripped 1 trailing paragraph: started with "Would you like me to...". Original ending: `<first 80 chars>`

(Section omitted if nothing was stripped.)
```

Filename convention: `YYYY-MM-DD_HH-MM_keyword-keyword-keyword.md` (matches live-conversation chunk filenames). Collision resolved by appending `_2`, `_3`, etc.

**Named failure mode — The Stream-of-Consciousness Stall (batch mode):** Sending a 100K+-word personal segment to a single model call exhausts output-token budget and produces a 30-minute stall (observed during pilot 2026-05-01). *Recovery:* the per-segment chunker added 2026-05-01 splits any personal segment exceeding ~30K tokens (~120K chars) on paragraph boundaries into ~10K-token chunks, cleans each independently with full preservation prompt, concatenates the results.

**Named failure mode — The Refusal Leak (batch mode, full tier):** The cleanup model, handed input that looks like a template, an instruction, or a short command ("Describe this image."), refuses to clean and emits commentary about its role instead — and that commentary gets persisted as the cleaned content, destroying the original text. Discovered 2026-07-10: ~700 pairs from the historical run carried persisted refusals, which propagated into chunks, ChromaDB embeddings, and a couple dozen engrams. *Recovery:* (a) prompt v2's never-refuse rule with verbatim fallback; (b) the deterministic Refusal Guard — signature-matched output falls back to the original text and logs to `~/ora/data/cleanup-guard.log`. The guard makes this failure structurally impossible: worst case is uncleaned-but-intact text.

**Named failure mode — The Rate-Limit Cascade (batch mode, `api` backend):** Metered-API 429 responses include a `retry-after` header. Exponential backoff alone (1.5^attempt) fires retries before the rate-limit window refills, causing 429 cascades. *Recovery:* parse `retry-after` from the exception's response headers, sleep that exact duration before retry. Falls back to exponential backoff if header absent. Fix landed in `api_client.py::call` per the Full Archive Handoff Step 1a. (The `claude-cli` backend instead backs off ~60s on rate-window pushback; the batch manifest's resume logic makes any interruption safe.)

**Named failure mode — The Cleanup Summarization Drift (batch mode):** The cleanup model summarizes instead of cleaning — drops thoughts that look tangential or repetitive. *Recovery:* the cleanup prompt explicitly instructs preservation of 100% of thought content. Verify on spot-checks (50 random cleaned-pair files vs raw sources); if drift observed, tighten the prompt's preservation language.

**Named failure mode — The Misclassified Paste (batch mode):** A pasted segment is classified into the wrong bucket (e.g., opinion as news, earlier-draft as resource). *Recovery:* the vault-index lookup pass catches earlier-drafts deterministically. For the remaining buckets, the user can run the LLM reclassifier (`orchestrator.historical.llm_reclassify`) to override heuristic classifications on cleaned-pair files post-hoc without re-running the cleanup pass.

### Output Formatting for This Layer

One cleaned-pair markdown file per turn pair, written to `~/Documents/Commercial AI archives/`. Manifest updated after each file's pairs complete. Engagement-strip audit log appended for each stripped paragraph.

Before proceeding to Layer 3: confirm the cleaned-pair file count for this source file matches the turn-pair count from Layer 2 (modulo documented per-pair errors recorded in the manifest's `pairs_with_errors` field).

---

## LAYER 3: SEMANTIC CHUNKING AND CONTEXTUAL HEADER GENERATION

**Stage Focus**: Group consecutive turn pairs into semantically coherent chunks and generate a contextual header for each chunk. **In batch mode at `full` tier, Layer 3 consumes cleaned-pair files from Layer 2.5 (via `orchestrator.historical.cleaned_pair_reader`) rather than raw turn pairs from Layer 2.** The cleaned-pair files already carry multi-level context headers; Layer 3 produces the chunk file specifically formatted for RAG retrieval, which is a different output with different metadata.

**This layer executes once per file's cleaned-pair set (full tier) or normalized output (light tier). Context window resets between files.**

### Processing Instructions

**Chunking strategy:**

1. Process the cleaned-pair set (or normalized turn-pair sequence at light tier) in order.
2. The default unit is one turn pair = one chunk. This is the correct granularity for most exchanges.
3. MERGE consecutive turn pairs into a single chunk IF:
   - The subsequent turn pair is a direct continuation of the same topic with no shift in subject or intent (e.g., a follow-up question that refines the previous exchange).
   - The subsequent turn pair is a brief clarification or correction that is meaningless without the preceding exchange.
   - The combined chunk remains under 2,000 words. IF merging would exceed 2,000 words, THEN keep as separate chunks even if topically continuous.
4. SPLIT a single turn pair into multiple chunks only IF:
   - The assistant's response covers multiple distinct topics that would serve different retrieval needs.
   - Each resulting chunk would be self-contained and useful in isolation.
   - This is rare — prefer keeping turn pairs intact.
5. For each chunk, assign topic tags: one to three short descriptive phrases identifying the subject matter. These become metadata for both the YAML frontmatter and the ChromaDB index. Topic tags should be specific enough to differentiate this chunk from unrelated conversations but general enough to match semantic queries on the same subject.

**Contextual header generation:**

For each chunk, generate a contextual header of two to four sentences that establishes:
- What the conversation is about (topic)
- What the user was trying to accomplish (intent)
- Any relevant prior context needed to understand the exchange (if the chunk is from the middle of a longer conversation)
- The platform and approximate date

The header serves a specific architectural purpose: when this chunk is retrieved by RAG and injected into a future context window, the header is what orients the model to the chunk's relevance. Write the header for that retrieval moment, not for a human reader.

**Named failure mode — The Granularity Trap:** The most common error is over-merging — combining too many turn pairs into a single chunk because they are "part of the same conversation." Long chunks dilute retrieval precision. When a query matches one part of a long chunk, the entire chunk enters the context window, consuming budget with irrelevant content. Err toward smaller chunks. A chunk that is too small is a minor retrieval redundancy. A chunk that is too large is a context window pollutant.

**Named failure mode — The Generic Header:** Headers like "A conversation about AI" or "The user asked about programming" are functionally useless for retrieval orientation. The header must be specific enough that a model reading it can immediately assess whether this chunk is relevant to the current query.

### Output Formatting for This Layer

For each chunk, produce the complete output file content in this format:

```yaml
---
source_file: [filename from raw/]
source_platform: [claude | chatgpt | gemini | local | api]
model_used: [model identifier]
timestamp: [ISO 8601]
conversation_title: [if available]
turn_range: [e.g., "3-4" for merged turns, "7" for single turn]
topics: [topic tag 1, topic tag 2]
chunk_id: [source_file stem]-[turn_range]-[timestamp date]
agent_id: [string — the identifier of the agent involved in this conversation. Default: "user" for personal system conversations. For named agents, use the agent's identifier from the agent registry (e.g., "malcolm", "researcher"). For raw commercial AI imports without system involvement, use "external".]
---

## Context

[Contextual header: 2-4 sentences]

## Exchange

**User:**

[User's prompt, full text]

**Assistant:**

[Assistant's response, full text]
```

Before proceeding: confirm that every turn pair from the input (cleaned-pair set or normalized sequence) is represented in exactly one chunk. No turn pair should be missing or duplicated.

---

## LAYER 4: DEDUPLICATION AND WRITE

**Stage Focus**: Check processed chunks against existing files in `~/Documents/conversations/`, write new chunks, and update the ChromaDB conversations collection and processing manifest.

### Processing Instructions

1. For each chunk produced in Layer 3:
   a. Check whether a chunk with the same chunk_id already exists in `~/Documents/conversations/`. IF it does, THEN skip — this chunk was already processed in a prior run.
   b. IF no duplicate exists, THEN write the chunk to `~/Documents/conversations/[chunk_id].md` via file_write.
   c. Add the chunk to the ChromaDB conversations collection with:
      - Document content: the full chunk text (header + exchange)
      - Metadata: all YAML frontmatter fields, especially timestamp (for recency queries), topics (for semantic queries), and agent_id (for scoped retrieval — filter by agent_id to retrieve one agent's conversation history; omit the filter for cross-agent retrieval)
      - Embedding: generated from the contextual header + user prompt (not the full assistant response, which would dilute the embedding toward the response's topic rather than the query's topic)

2. After all chunks for a file are written:
   a. Update the cleanup manifest with the file's name, processing date, number of cleaned-pair files produced (full tier), number of chunks produced, chunk_ids generated, and per-pair cost.
   b. Proceed to the next file in the queue.

3. After all files are processed:
   a. Persist the final manifest at `~/ora/data/cleanup-manifest.json`.
   b. Generate the processing summary.

**Named failure mode — The Embedding Dilution:** Embedding the full assistant response dilutes the vector toward whatever the AI talked about most. For retrieval purposes, the embedding should capture what the exchange is about — which is better represented by the contextual header and the user's prompt. The assistant's response is included in the stored document (so it appears in the context window when retrieved) but excluded from the embedding calculation.

### Output Formatting for This Layer

Processing summary:
- Files processed: [count]
- Cleaned-pair files written: [count] (full tier only)
- Chunks generated: [count]
- Chunks skipped (duplicates): [count]
- Files skipped (unrecognized format): [count] [list filenames]
- Errors: [count] [list with file and error description]
- ChromaDB conversations collection: [total entries after update]
- Total cost (USD): [amount] (full tier only)

---

## LAYER 5: SELF-EVALUATION

**Stage Focus**: Evaluate all output against the Evaluation Criteria.

**Calibration warning**: Self-evaluation scores are systematically inflated. Score conservatively.

For each criterion:
1. State the criterion name and number.
2. Wait — verify the current output against this specific criterion's rubric descriptions before scoring.
3. Identify specific evidence in the output that supports or undermines each score level.
4. Assign a score (1-5) with cited evidence from the output.
5. IF the score is below 3, THEN identify the deficiency, state the required modification, apply it, and re-score.
6. IF the score meets or exceeds 3, THEN confirm and proceed.

After all criteria are evaluated:
- IF all scores meet threshold, THEN proceed to final output.
- IF any score remains below threshold after one modification attempt, THEN flag with UNRESOLVED DEFICIENCY.

---

## LAYER 6: ERROR CORRECTION AND OUTPUT FORMATTING

**Stage Focus**: Final verification of all written files and manifest integrity.

### Error Correction Protocol

1. Verify every cleaned-pair file in `~/Documents/Commercial AI archives/` has valid YAML frontmatter that parses correctly (full tier only).
2. Verify every chunk file in `~/Documents/conversations/` has valid YAML frontmatter that parses correctly.
3. Verify the cleanup manifest accurately reflects all files processed in this run, with correct pair counts and per-file cost attributions.
4. Verify ChromaDB entry count matches the number of new chunks written.
5. Verify no chunk_id collision — every chunk has a unique identifier.
6. Verify cleaned-pair prior_pair / next_pair links form coherent threads with no orphans or cycles (full tier only).

### Recovery Declaration

IF any files failed to process, THEN restate each failure with:
- The raw file that failed
- The error encountered
- Whether the failure is recoverable on a retry or requires manual intervention
- Whether any partial output from the failed file needs cleanup

---

## NAMED FAILURE MODES

This section consolidates failure modes named throughout the layers above, plus the cross-layer failures that don't fit any single layer.

**The Delivery Block (inline mode).** Inline processing that takes too long blocks the user from entering their next prompt. The two-second budget is a hard constraint. If header generation is slow, write the chunk with a placeholder header and backfill asynchronously — never block the user's workflow to generate a perfect contextual header.

**The Encoding Trap (batch mode).** Raw exports from different platforms use different Unicode encodings and escaping schemes. Normalize to UTF-8 during format normalization.

**The Granularity Trap.** Over-merging turn pairs into large chunks that dilute retrieval precision. Err toward smaller chunks. (Primarily a batch mode concern — inline mode processes one pair at a time by default.)

**The Generic Header.** Contextual headers that are too vague to orient a model during retrieval. Headers must be specific to the exchange's topic and intent. (Both modes.)

**The Embedding Dilution.** Embedding the full assistant response instead of the contextual header + user prompt. The embedding should capture what the exchange is about, not what the AI said. (Both modes.)

**The Silent Reprocess.** Processing a file that was already processed in a prior run, producing duplicate chunks. The manifest prevents this — always check before processing. (Batch mode only — inline mode generates unique chunk IDs from session ID + pair number, which cannot collide.)

**The Cross-File Bleed.** Letting context from one file's processing leak into another file's contextual headers or topic tags. Context window resets between files prevent this. (Batch mode only.)

**The Stream-of-Consciousness Stall (batch mode, full tier).** Sending a 100K+-word personal segment to a single model call exhausts output-token budget and produces a 30-minute stall. *Recovery:* per-segment chunker splits any personal segment exceeding ~30K tokens on paragraph boundaries into ~10K-token chunks, cleans each independently, concatenates.

**The Refusal Leak (batch mode, full tier).** The cleanup model comments on the input ("I'm a text-cleanup tool...") instead of returning it, and the commentary is persisted as cleaned content — original text destroyed. *Recovery:* prompt v2 never-refuse rule + the deterministic Refusal Guard (signature match → original text preserved, event logged to `~/ora/data/cleanup-guard.log`). Structurally impossible since 2026-07-10; worst case is uncleaned-but-intact text.

**The Rate-Limit Cascade (batch mode, full tier, `api` backend).** Metered-API 429 responses include a `retry-after` header; exponential backoff alone fires retries before the window refills, cascading 429s. *Recovery:* parse `retry-after` from the exception, sleep that exact duration before retry. Fix landed in `api_client.py::call`.

**The Cleanup Summarization Drift (batch mode, full tier).** Cleanup model summarizes instead of cleaning — drops thoughts that look tangential or repetitive. *Recovery:* cleanup prompt explicitly instructs preservation of 100% of thought content; spot-check on 50 random cleaned-pair files vs raw sources.

**The Misclassified Paste (batch mode, full tier).** Pasted segment classified into the wrong bucket. *Recovery:* vault-index lookup catches earlier-drafts deterministically; for the other three buckets, run the LLM reclassifier (`orchestrator.historical.llm_reclassify`) post-hoc.

**The Engagement-Strip False Positive (batch mode).** Engagement strip removes substantive content because the final paragraph contained a `?` that was a rhetorical question or a question the user posed back. *Recovery:* policy accepted — the audit log allows post-hoc detection; user explicitly preferred aggressive stripping over conservatism.

**The Context-Window Drain (batch mode).** Operating the framework from within a single conversation thread that uses the Monitor tool to follow a long batch fills the context window with per-file notifications. *Recovery:* launch the batch with `run_in_background: true`, do not use Monitor, do not poll; check the manifest once at completion. For long-running batches use ScheduleWakeup with ~30-minute cadence and a single status-check command per wake-up.

---

## DOWNSTREAM CONSUMERS

CPP produces cleaned-pair files (batch mode, full tier) and chunk files (both modes). Downstream frameworks and pipelines consume these for further extraction. CPP's responsibility ends at the cleaned-pair archive + chunk files + ChromaDB index; downstream extraction is out of scope.

- **News + opinion outlines** — pasted segments classified as `news-article` or `opinion-piece` are extracted by the news/opinion extraction pipeline. News articles get fact-filtered outlines; opinion pieces preserve the user's reaction (the cleaned user input) as context. Algorithm spec deferred until the cleanup pipeline is stable for ongoing imports.
- **Resource notes** — pasted segments classified as `resource` route through the Document Processing framework's HCP mode (`~/ora/orchestrator/tools/hcp.py`).
- **Atomic notes** — cleaned-pair files are walked in reverse chronological order by `orchestrator.historical.phase5_atomic_extraction`, which uses the dedup index at `~/ora/data/atomic-dedup-index.json` to avoid minting duplicates of atomic claims already extracted.
- **Engram cleaning detection / resolution** — `orchestrator.historical.run_engram_cleaning_detection` + `run_engram_cleaning_resolver` operate on the produced atomic notes per the Engram Cleaning framework.
- **News supersession detection / resolution** — `orchestrator.historical.run_news_supersession_detection` + `run_news_supersession_resolver` operate on news-derived atomic notes for the MSI publication.

---

## IMPLEMENTATION POINTER

The batch-mode pipeline is implemented in the `~/ora/orchestrator/historical/` subpackage. The framework spec above describes the architecture; the modules below are the runnable expression of it.

| Module | Layer / Step |
|---|---|
| `cli.py` | Entry point: `python3 -m orchestrator.historical.cli` |
| `parser.py` | Layer 2 — format detection + Web-Clipper / live-Ora / ChatGPT / Gemini parsing |
| `paste_detection.py` | Layer 2.5 Steps 1 + 2 — segment + classify (with vault-index lookup) |
| `llm_reclassify.py` | Post-hoc bucket reclassification (Layer 2.5 Step 2 retroactive fix) |
| `pair_cleanup.py` | Layer 2.5 Steps 3 + 4 — per-pair cleanup orchestration + Refusal Guard integration |
| `prompts.py` | Layer 2.5 Step 3 — cleanup prompt templates (v2: never-refuse, word-locks, pronoun resolution) with XML prompt-injection defense + refusal-signature detection |
| `model_router.py` | Layer 2.5 Step 3 — token-threshold tier routing (light ≤30K, heavy >30K) |
| `cleanup_backends.py` | Layer 2.5 Step 3 — pluggable model-call backends (`api` / `claude-cli` / `ora-slots`); tier-to-model resolution lives here and in routing config, never in this framework |
| `api_client.py` | Layer 2.5 Step 3 — metered-API wrapper (`api` backend) with `retry-after` handling, keyring auth |
| `engagement.py` | Layer 2.5 Step 5 — strict 5-step engagement strip + JSONL audit log |
| `context_header.py` | Layer 2.5 Steps 6 + 7 — thread continuity + multi-level context header |
| `writer.py` | Layer 2.5 Step 8 — cleaned-pair file write with collision handling |
| `file_orchestrator.py` | Per-file parallel cleanup with error-budget abort |
| `cleaned_pair_reader.py` | Layer 3 input adapter (full tier) — reads cleaned-pair files for chunking |
| `path2_orchestrator.py` / `path2_cli.py` | Layer 3 + 4 — chunk emission and ChromaDB indexing |

Supporting infrastructure outside `historical/`:
- `~/ora/orchestrator/tools/vault_indexer.py` — Phase 0 vault index builder; produces `~/ora/data/vault-index.json` consumed by Layer 2.5 Step 2.
- `~/ora/orchestrator/conversation_chunk.py` — shared chunk-building helpers (live inline + batch historical).
- `~/ora/orchestrator/tools/path2_emitter.py` — chunk emitter; Layer 3/4 in batch mode.

**Historical context:** this implementation was built across April–May 2026 during the one-time historical archive run that processed 39,081 cleaned-pair files from 3,733 source files at a cost of $510.31 with 99.9% pair-level success. Going forward, the same code processes ad-hoc imports of fresh chats captured from phone, web, or any commercial AI service. Drop the export into `~/Documents/conversations/raw/` and re-run the CLI; the manifest's resume logic skips everything already processed.

---

## AGENT EXECUTION METADATA

### Inline Mode Execution Path

The inline path is not a staged pipeline — it is a three-step procedure executed by the orchestrator after each model response:

1. Append exchange to session raw log (file I/O, ~10ms)
2. Generate contextual header and topic tags (model call to sidebar model, ~500ms–1500ms)
3. Write chunk file and index into ChromaDB (file I/O + embedding, ~200ms)

Total inline processing budget: under 2 seconds. If Step 2 exceeds budget, write chunk with placeholder header and backfill asynchronously.

### Batch Mode Stage Boundaries

Stage 1: Layer 1 (inventory and manifest check)
  Handoff to Stage 2: processing queue with file list, source formats, and file sizes.

Stage 2: Layer 2 (format normalization) — executes once per file, context window resets between files.
  Handoff to Stage 3: normalized turn-pair sequence for current file.

Stage 3: **Layer 2.5 (per-pair cleanup and classification)** — executes once per turn pair, context resets between pairs. Skipped at `light` tier except for Step 5.
  Handoff to Stage 4: cleaned-pair files written to disk; manifest updated.

Stage 4: Layer 3 (semantic chunking and header generation) — executes once per file (full tier: consumes cleaned-pair files; light tier: consumes normalized turn pairs). Context window resets between files.
  Handoff to Stage 5: complete chunk file contents ready for writing.

Stage 5: Layer 4 (deduplication, write, and indexing) — executes once per file.
  Handoff: updated manifest and ChromaDB state.

Stage 6: Layers 5–6 (self-evaluation and error correction) — runs once after all files processed.

### Persistent Reference Document (Batch Mode)

Injected into every batch mode stage's context window:

```
OBJECTIVE: Process raw conversation exports into a persistent
cleaned-pair archive plus self-contained, semantically chunked
turn-pair files with contextual headers and topic metadata,
ready for dual-strategy RAG retrieval (timestamp-sorted for
recency, semantic similarity for relevance) and for downstream
extraction by news, resource, and atomic-note pipelines.

SOURCE: ~/Documents/conversations/raw/ (or --input path)
CLEANED ARCHIVE: ~/Documents/Commercial AI archives/
CHUNK DESTINATION: ~/Documents/conversations/
INDEX: ~/ora/chromadb/ (conversations collection)
MANIFEST: ~/ora/data/cleanup-manifest.json
VAULT INDEX: ~/ora/data/vault-index.json
ENGAGEMENT AUDIT LOG: ~/ora/data/engagement-strips.log

CONSTRAINTS:
- Cleanup preserves 100% of thought content; words/grammar free
- Cleanup model never refuses; unsure → return input verbatim
- Refusal Guard: output matching role-commentary signatures falls
  back to original text + logs to ~/ora/data/cleanup-guard.log
- Tier-to-model resolution belongs to the backend/routing config;
  no model names in this framework
- Pasted segments preserved verbatim, never sent to cleanup model
- Engagement-wrapper strip is aggressive (any final paragraph
  with a ? after URL/code stripping)
- One cleaned-pair file per turn pair (full tier)
- One turn pair per chunk (default); merge only for direct
  continuations
- Maximum chunk size: 2,000 words
- Contextual headers: 2-4 sentences, written for retrieval
  orientation
- Embedding source: contextual header + user prompt only
- Context window resets between files and between turn pairs
- Check manifest before processing to prevent duplicates
- Parse retry-after header on 429 responses before backoff
```

### Tool Definitions (Batch Mode)

Tool: file_read
  Description: Read contents of files in input directory, cleaned-pair archive, or chunk directory.
  Trigger: When processing requires a raw, cleaned, or chunk file, or checking for existing outputs.

Tool: file_write
  Description: Write cleaned-pair files, chunk files, manifest updates, and audit log entries.
  Trigger: After cleanup completes for a pair (cleaned-pair file), after chunk generation completes (chunk file), and after engagement strip removes a paragraph (audit log).

Tool: file_list
  Description: List files in a directory.
  Trigger: During inventory (Layer 1), during cleaned-pair reading (Layer 3 full tier), and during deduplication check (Layer 4).

Tool: chromadb_index
  Description: Add entries to the conversations collection in ChromaDB.
  Trigger: After writing each chunk file to disk.

Tool: model_client
  Description: Per-segment cleanup calls through the selected backend (light or heavy tier based on routing; the backend resolves tiers to models).
  Trigger: Layer 2.5 Step 3 for each personal segment of each turn pair (full tier).

Tool: local_endpoint_dispatch
  Description: Fallback dispatch to local slot endpoints via `orchestrator.boot.call_local_endpoint`.
  Trigger: Layer 2.5 Step 3 if user has configured local fallback and a segment exceeds the selected backend's capacity.

---

**END OF CONVERSATION PROCESSING PIPELINE FRAMEWORK v2.0**
