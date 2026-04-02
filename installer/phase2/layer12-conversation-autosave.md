### PHASE 2, LAYER 12: CONVERSATION AUTO-SAVE + RAG INDEXING

**When to execute**: After Phase 2, Layer 11 (or Layer 10 on non-macOS). Runs on all tiers.

**Purpose**: Persist every user↔AI exchange immediately after delivery — raw audit log, processed chunk file, and ChromaDB index entry. All three steps are inline. There is no batch scheduler for routine session saving.

### Processing Instructions

1. **Add `_save_conversation(user_input, ai_response, panel_id, is_new_session)` to `server/server.py`**. This function executes three steps every time, immediately after every response:

   **Step 1 — Raw log.** Append the pair to `~/Documents/conversations/raw/`. One file per session, appended throughout. Filename: `YYYY-MM-DD_HH-MM_topic-slug_session-[6-char-id].md`. File header on first write includes session metadata (start time, panel_id, model, source_platform: local). Each pair entry: `<!-- pair NNN | timestamp -->` followed by `**User:**` and `**Assistant:**` blocks separated by `---`.

   **Step 2 — Processed chunk file.** Write one file per pair to `~/Documents/conversations/`. Filename: `YYYY-MM-DD_HH-MM_session-[id]_pair-[NNN]_[topic-slug].md`. Format:
   ```
   ---
   source_file: [raw log filename]
   source_platform: local
   model_used: [model id]
   timestamp: [ISO 8601]
   session_id: [6-char id]
   turn_range: "[pair number]"
   topics: [word1, word2, word3]
   chunk_id: session-[id]-pair-[NNN]
   ---

   ## Context

   [2–4 sentence contextual header written for retrieval orientation:
    date, panel, model, turn number, preview of user's question]

   ## Exchange

   **User:**

   [full user prompt]

   **Assistant:**

   [full assistant response]
   ```

   **Step 3 — ChromaDB index.** Add the chunk to the `"conversations"` collection (separate from `"knowledge"`). Embedding input: contextual header + user prompt only — not the assistant response (embedding the response dilutes the vector toward the AI's topic rather than the query). Use nomic-embed-text-v1.5 via ollama (`POST http://localhost:11434/api/embeddings`). Fall back to chromadb's default embedding if ollama is unavailable.

2. **Track session state** in a per-panel `_session_data` dict: `{raw_path, session_id, pair_count, model, start}`. Detect new session when `len(history) == 0`.

3. **Call in a `daemon=True` background thread** so it never blocks the SSE stream. Raw log write happens first; chunk and index follow.

4. **Verify**: Send one message. Confirm `~/Documents/conversations/raw/` contains the raw log and `~/Documents/conversations/` contains the processed chunk with YAML frontmatter.

### What the overnight batch is NOT for

The Conversation Processing Pipeline spec's multi-layer batch process applies only to: (1) one-time migration of historical archives, and (2) bulk processing of commercial AI exports dropped into `raw/`. It does not apply to routine local sessions — those are processed inline.

### Output Format for This Layer

```
CONVERSATION AUTO-SAVE INSTALLED
Raw logs:       ~/Documents/conversations/raw/  (one file per session)
Processed chunks: ~/Documents/conversations/    (one file per pair)
ChromaDB:       "conversations" collection — nomic-embed-text-v1.5 (or default fallback)
Embedding input: contextual header + user prompt only
Trigger:        every completed exchange, all panels, inline background thread
Session behavior: browser reloads start fresh (by design); full history on disk
```

---

### LOCAL ENDPOINT REGISTRATION

After Phase 2 completes successfully, confirm the endpoint registry contains the local model entry:

```json
{
  "name": "local-[engine]",
  "type": "local",
  "engine": "[mlx|ollama]",
  "model": "[model_name]",
  "url": "[localhost endpoint URL]",
  "status": "active"
}
```

Confirm `default_endpoint` is set to `"local-[engine]"`. If a browser endpoint was previously set as default and the reader wishes to keep cloud as default, preserve that choice and document it.

---

## CHAPTER 3: HOW FILE ACCESS ACTUALLY WORKS

*This section provides conceptual grounding for what the boot framework installs and why the reader's workflow is what it is.*

