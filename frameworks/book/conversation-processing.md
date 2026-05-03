# Conversation Processing Pipeline

## Display Name
Conversation Processing

## Display Description
Process raw conversation exports and live session exchanges into structured turn-pair chunks with contextual headers, topic metadata, and ChromaDB indexing for RAG retrieval. Use to ingest external chat archives into the vault's retrieval surface.


_Updated March 31, 2026 — dual-mode architecture: inline processing for ongoing conversations (primary), batch processing for imports only. Inline processing executes as part of the output delivery step, eliminating overnight batch dependency for ongoing work._

## PURPOSE

This framework processes conversations into structured turn-pair chunks ready for RAG retrieval. It generates contextual headers, creates semantically chunked prompt-response pairs with timestamp and topic metadata, writes processed files to ~/Documents/conversations/, and indexes them into ChromaDB's conversations collection. The processed files serve two retrieval strategies: timestamp-sorted retrieval for recent context during prompt cleanup, and semantic similarity retrieval for historical memory during RAG package assembly. This pipeline is distinct from the Data Formulation Pipeline, which processes documents and research for the vault.

**This pipeline operates in two modes:**

- **Inline mode (primary):** Processes each prompt-response pair immediately after the model delivers its response, as part of the output delivery step. The exchange is appended to the session's raw log, written as a processed chunk file, and indexed into ChromaDB before the system accepts the next user input. This means conversation RAG has access to every exchange in the current session — including the one that just completed.

- **Batch mode (imports only):** Processes files dropped into ~/Documents/conversations/raw/ — commercial AI exports (Claude, ChatGPT, Gemini) and the one-time historical archive migration. Batch mode uses the same processing logic as inline mode but operates on complete conversation files rather than individual exchanges. Batch processing is triggered manually or scheduled as needed. There is no automatic overnight batch for ongoing conversations — inline mode handles those in real time.

## INPUT CONTRACT

**Inline mode inputs:**
- The prompt-response pair that just completed: user prompt (full text), assistant response (full text), timestamp (current), model identifier, session ID, turn index within the current session.
- The current session's raw log file path (for appending).
- Source: provided by the orchestrator (boot.py) as part of the output delivery step.

**Batch mode inputs:**
- Unprocessed conversation files in ~/Documents/conversations/raw/. Source: user export from commercial AI services (Claude.ai JSON, ChatGPT export, Gemini export), historical local system session logs, or API call logs.
- Processing manifest: a record of which files in raw/ have already been processed. Source: ~/Documents/conversations/.processing-manifest.json (created and maintained by this pipeline).

Optional (both modes):
- Existing ChromaDB conversations collection. Source: ~/ora/chromadb/. Default behavior if absent: pipeline creates the collection and indexes all processed files.

## OUTPUT CONTRACT

Primary outputs (both modes):
- Processed turn-pair chunk files written to ~/Documents/conversations/. Each file contains one prompt-response pair with contextual header, topic metadata, timestamps, and provenance tag. Format: Markdown with YAML frontmatter. Quality threshold: every chunk is self-contained — a reader or retrieval system encountering the chunk in isolation can understand the exchange without needing the full conversation.

Secondary outputs (both modes):
- Updated ChromaDB conversations collection with embeddings for all new chunks. Each entry carries timestamp metadata for recency queries and semantic content for similarity queries.

Additional outputs (inline mode):
- Updated session raw log at ~/Documents/conversations/raw/[session-id].md with the new exchange appended.

Additional outputs (batch mode):
- Updated processing manifest recording which raw files have been processed and when.
- Processing summary: count of files processed, chunks generated, and any errors or skipped files.

## EXECUTION TIER

**Inline mode:** Orchestrator. This pipeline executes as part of the orchestrator's output delivery step — after the model produces a response and before the system accepts the next user input. Processing a single exchange inline must complete in under two seconds to avoid perceptible delay. The inline path runs Layers 3 and 4 only (semantic chunking, header generation, write, and indexing) because the prompt-response pair is already normalized — it comes directly from the orchestrator, not from a file that needs format detection and parsing.

**Batch mode:** Agent. This pipeline runs on demand for processing imported conversation files. It executes through boot.py with tool access to the filesystem and ChromaDB. Stage boundaries represent actual context window resets to prevent context debt accumulation across many files. Batch mode runs all layers (1 through 6).

Available tools (batch mode):
- file_read: Read raw conversation files and existing processed files.
- file_write: Write processed chunks to ~/Documents/conversations/ and update the manifest.
- file_list: Enumerate files in ~/Documents/conversations/raw/ and ~/Documents/conversations/.
- chromadb_index: Add entries to the conversations collection.

The single batch-mode milestone covers Layers 1-6 (six processing layers). Per the Process Formalization Framework Section II §2.3, this single-milestone-for->5-layer-modes design is justified by the integration of the chunk pipeline: format detection, semantic chunking, header generation, write, and indexing must all complete before the chunk-set is queryable, and intermediate states would represent un-indexed or un-headered chunks unsafe to commit to ChromaDB.

---

## MILESTONES DELIVERED

This framework's declaration of the project-level milestones it can deliver. Used by the Problem Evolution Framework (PEF) to invoke this framework for milestone delivery under project supervision. Inline mode is invoked automatically by the orchestrator on every session turn and is not PEF-selectable; it behaves as a pipeline stage per the exemption in PFF Section II subsection 2.3. Only batch mode produces a project-level milestone and is declared below.

### Milestone 1: Processed Conversation Chunks with ChromaDB Indexing

- **Mode:** batch
- **Endpoint produced:** A set of processed turn-pair chunk files written to ~/Documents/conversations/ — each with YAML frontmatter (source_file, source_platform, model_used, timestamp, conversation_title, turn_range, topics, chunk_id, agent_id), a 2-4 sentence contextual header, and the full user/assistant exchange — plus corresponding entries in the ChromaDB conversations collection (document content, metadata, embedding derived from contextual header + user prompt), plus an updated processing manifest at ~/Documents/conversations/.processing-manifest.json recording every file processed in the run.
- **Verification criterion:** (a) every raw file in the batch's input set is either represented in the updated manifest with its chunk_ids and processing date, or listed in the processing summary as skipped with a reason (unrecognized format, parser failure, or error); (b) every chunk written to ~/Documents/conversations/ has a unique chunk_id with no collisions and valid YAML frontmatter that parses programmatically; (c) ChromaDB conversations collection entry count increases by exactly the number of new (non-duplicate) chunks written, with embeddings generated from contextual header + user prompt per the Embedding Dilution failure mode; (d) no chunk duplicates an existing chunk_id from a prior run — deduplication check against ~/Documents/conversations/ ran before every write; (e) all seven Evaluation Criteria score 3 or above against the produced chunks.
- **Layers covered:** 1, 2, 3, 4, 5, 6
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** Set of chunk markdown files with structured YAML frontmatter, ChromaDB collection updates, and updated processing manifest JSON.
- **Drift check question:** Does every input file in the batch produce either a chunk-set or a documented skip reason, and do the produced chunks faithfully reflect the original conversation content without lossy summarization?

---

## EVALUATION CRITERIA

This framework's output is evaluated against these 7 criteria. Each criterion is rated 1-5. Minimum passing score: 3 per criterion.

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
   - 5: No chunk duplicates content already in ~/Documents/conversations/ from a prior processing run. The manifest is checked before processing and updated after.
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

The following layers (1 through 6) describe the batch processing path for imported conversation files — commercial AI exports and historical archive migration. Batch mode is triggered manually when the user drops files into `~/Documents/conversations/raw/`. It is not an automatic overnight process.

---

## LAYER 1: INVENTORY AND MANIFEST CHECK

**Stage Focus**: Identify which raw files need processing by comparing ~/Documents/conversations/raw/ against the processing manifest. This layer runs in batch mode only — inline mode skips directly to chunk generation.

### Processing Instructions

1. Read the processing manifest from ~/Documents/conversations/.processing-manifest.json. IF the manifest does not exist, THEN create an empty manifest and treat all files in raw/ as unprocessed.
2. List all files in ~/Documents/conversations/raw/.
3. Compare the file list against the manifest. A file needs processing IF:
   - It does not appear in the manifest, OR
   - Its modification date is newer than the manifest's recorded processing date for that file (the file was updated since last processing).
4. For each file needing processing, identify the source format:
   - Claude.ai JSON export (conversations.json or similar)
   - ChatGPT export (conversations.json with ChatGPT schema)
   - Gemini export
   - Local system session log (Markdown with timestamp headers)
   - API call log (JSON with messages array)
   - Unknown format — flag for manual review, do not attempt processing.
5. Sort unprocessed files by date (oldest first). Processing in chronological order ensures that contextual headers can reference earlier conversations if needed.

### Output Formatting for This Layer

Processing queue: ordered list of files with source format identified and byte size noted. Summary count: N files to process, N already processed, N unrecognized.

Before proceeding: confirm that the primary objective (processing raw conversations into chunks) has not shifted and that the manifest has been correctly loaded or created.

---

## LAYER 2: FORMAT NORMALIZATION

**Stage Focus**: Convert each source format into a common intermediate representation — a sequence of timestamped turn pairs (user prompt, AI response) with source metadata.

**This layer executes once per file in the processing queue. Context window resets between files to prevent cross-file contamination.**

### Processing Instructions

For each file in the processing queue:

1. Read the file via file_read.
2. Parse according to identified source format:

**Claude.ai JSON export:**
- Extract each conversation as a sequence of human/assistant message pairs.
- Preserve conversation-level metadata: title (if present), creation timestamp, model used.
- Each human message + subsequent assistant message = one turn pair.
- IF multiple assistant responses exist for one human message (regenerations), THEN use the final response only.

**ChatGPT export:**
- Extract conversations from the messages array.
- Each user/assistant pair = one turn pair.
- Preserve conversation title, creation time, model.

**Local system session log (Markdown):**
- Parse timestamp headers and user/assistant blocks.
- Each timestamped exchange = one turn pair.
- Preserve session start time and model endpoint used.

**API call log (JSON):**
- Parse the messages array.
- Each user/assistant pair = one turn pair.
- Preserve timestamp, model identifier, and any system prompt summary.

3. Output: sequence of normalized turn pairs, each carrying:
   - user_message: the user's prompt (full text)
   - assistant_message: the AI's response (full text)
   - timestamp: ISO 8601 (from source metadata; if unavailable, use file creation date)
   - source_file: filename in raw/
   - source_platform: claude | chatgpt | gemini | local | api
   - model_used: model identifier if available, "unknown" if not
   - conversation_title: if available from source metadata
   - turn_index: position within the original conversation (1-indexed)
   - total_turns: total number of turns in the original conversation

**Named failure mode — The Encoding Trap:** Raw exports from different platforms use different Unicode encodings, line ending conventions, and JSON escaping schemes. Normalize all text to UTF-8 with Unix line endings during this layer. Smart quotes, em dashes, and non-ASCII punctuation are preserved in content but must be valid UTF-8.

### Output Formatting for This Layer

Normalized turn-pair sequence as a structured list. Each entry contains all fields enumerated above. This intermediate representation is consumed by Layer 3 and discarded after processing completes.

Before proceeding: confirm that the number of extracted turn pairs is plausible given the source file size. IF zero turns were extracted from a non-empty file, THEN the parser failed — flag the file and skip to the next file in the queue.

---

## LAYER 3: SEMANTIC CHUNKING AND CONTEXTUAL HEADER GENERATION

**Stage Focus**: Group consecutive turn pairs into semantically coherent chunks and generate a contextual header for each chunk.

**This layer executes once per file's normalized output. Context window resets between files.**

### Processing Instructions

**Chunking strategy:**

1. Process the normalized turn-pair sequence from Layer 2 in order.
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

Before proceeding: confirm that every turn pair from the normalized sequence is represented in exactly one chunk. No turn pair should be missing or duplicated.

---

## LAYER 4: DEDUPLICATION AND WRITE

**Stage Focus**: Check processed chunks against existing files in ~/Documents/conversations/, write new chunks, and update the ChromaDB conversations collection and processing manifest.

### Processing Instructions

1. For each chunk produced in Layer 3:
   a. Check whether a chunk with the same chunk_id already exists in ~/Documents/conversations/. IF it does, THEN skip — this chunk was already processed in a prior run.
   b. IF no duplicate exists, THEN write the chunk to ~/Documents/conversations/[chunk_id].md via file_write.
   c. Add the chunk to the ChromaDB conversations collection with:
      - Document content: the full chunk text (header + exchange)
      - Metadata: all YAML frontmatter fields, especially timestamp (for recency queries), topics (for semantic queries), and agent_id (for scoped retrieval — filter by agent_id to retrieve one agent's conversation history; omit the filter for cross-agent retrieval)
      - Embedding: generated from the contextual header + user prompt (not the full assistant response, which would dilute the embedding toward the response's topic rather than the query's topic)

2. After all chunks for a file are written:
   a. Update the processing manifest with the file's name, processing date, number of chunks produced, and the chunk_ids generated.
   b. Proceed to the next file in the queue.

3. After all files are processed:
   a. Write the updated manifest to ~/Documents/conversations/.processing-manifest.json.
   b. Generate the processing summary.

**Named failure mode — The Embedding Dilution:** Embedding the full assistant response dilutes the vector toward whatever the AI talked about most. For retrieval purposes, the embedding should capture what the exchange is about — which is better represented by the contextual header and the user's prompt. The assistant's response is included in the stored document (so it appears in the context window when retrieved) but excluded from the embedding calculation.

### Output Formatting for This Layer

Processing summary:
- Files processed: [count]
- Chunks generated: [count]
- Chunks skipped (duplicates): [count]
- Files skipped (unrecognized format): [count] [list filenames]
- Errors: [count] [list with file and error description]
- ChromaDB conversations collection: [total entries after update]

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

1. Verify every chunk file in ~/Documents/conversations/ has valid YAML frontmatter that parses correctly.
2. Verify the processing manifest accurately reflects all files processed in this run.
3. Verify ChromaDB entry count matches the number of new chunks written.
4. Verify no chunk_id collision — every chunk has a unique identifier.

### Recovery Declaration

IF any files failed to process, THEN restate each failure with:
- The raw file that failed
- The error encountered
- Whether the failure is recoverable on a retry or requires manual intervention
- Whether any partial output from the failed file needs cleanup

---

## NAMED FAILURE MODES

**The Delivery Block.** Inline processing that takes too long blocks the user from entering their next prompt. The two-second budget is a hard constraint. If header generation is slow, write the chunk with a placeholder header and backfill asynchronously — never block the user's workflow to generate a perfect contextual header.

**The Encoding Trap.** Raw exports from different platforms use different Unicode encodings and escaping schemes. Normalize to UTF-8 during format normalization. (Batch mode only — inline mode receives clean UTF-8 from the orchestrator.)

**The Granularity Trap.** Over-merging turn pairs into large chunks that dilute retrieval precision. Err toward smaller chunks. (Primarily a batch mode concern — inline mode processes one pair at a time by default.)

**The Generic Header.** Contextual headers that are too vague to orient a model during retrieval. Headers must be specific to the exchange's topic and intent. (Both modes.)

**The Embedding Dilution.** Embedding the full assistant response instead of the contextual header + user prompt. The embedding should capture what the exchange is about, not what the AI said. (Both modes.)

**The Silent Reprocess.** Processing a file that was already processed in a prior run, producing duplicate chunks. The manifest prevents this — always check before processing. (Batch mode only — inline mode generates unique chunk IDs from session ID + pair number, which cannot collide.)

**The Cross-File Bleed.** Letting context from one file's processing leak into another file's contextual headers or topic tags. Context window resets between files prevent this. (Batch mode only.)

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

Stage 3: Layer 3 (semantic chunking and header generation) — executes once per file, context window resets between files.
  Handoff to Stage 4: complete chunk file contents ready for writing.

Stage 4: Layer 4 (deduplication, write, and indexing) — executes once per file.
  Handoff: updated manifest and ChromaDB state.

Stage 5: Layers 5-6 (self-evaluation and error correction) — runs once after all files processed.

### Persistent Reference Document (Batch Mode)

Injected into every batch mode stage's context window:

```
OBJECTIVE: Process raw conversation exports into self-contained, 
semantically chunked turn-pair files with contextual headers 
and topic metadata, ready for dual-strategy RAG retrieval 
(timestamp-sorted for recency, semantic similarity for relevance).

SOURCE: ~/Documents/conversations/raw/
DESTINATION: ~/Documents/conversations/
INDEX: ~/ora/chromadb/ (conversations collection)
MANIFEST: ~/Documents/conversations/.processing-manifest.json

CONSTRAINTS:
- One turn pair per chunk (default); merge only for direct continuations
- Maximum chunk size: 2,000 words
- Contextual headers: 2-4 sentences, written for retrieval orientation
- Embedding source: contextual header + user prompt only
- Context window resets between files
- Check manifest before processing to prevent duplicates
```

### Tool Definitions (Batch Mode)

Tool: file_read
  Description: Read contents of a file from ~/Documents/conversations/raw/ or ~/Documents/conversations/.
  Trigger: When processing requires a raw file or checking for existing chunks.

Tool: file_write
  Description: Write processed chunk files to ~/Documents/conversations/ and manifest updates.
  Trigger: After chunk generation and deduplication check.

Tool: file_list
  Description: List files in a directory.
  Trigger: During inventory (Layer 1) and deduplication check (Layer 4).

Tool: chromadb_index
  Description: Add entries to the conversations collection in ChromaDB.
  Trigger: After writing each chunk file to disk.
