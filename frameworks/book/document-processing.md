# Document Processing Framework

## Display Name

Document Processing

## Display Description

Convert any document — PDF, Word, slides, HTML, plain text — into vault-ready atomic notes with full YAML frontmatter, subtype classification, grammar-rule enforcement, and relationship mapping. Used by the file-attach pipeline; also runnable directly to ingest a single document or batch.

_Created April 14, 2026 — canonical pipeline specification for converting any document input into vault-ready notes with complete YAML frontmatter, subtype classification, grammar rules, and relationship mapping._

## Setup Questions

### Document or files

Required. The document(s) you want processed. Provide a file path, paste the document text directly, or attach files to the input pane. Supported formats: PDF, Word (.docx), PowerPoint (.pptx), HTML, RTF, plain text, Markdown.

### Source provenance

Optional. Where the document came from — for example, a chat export, a published paper, a personal note, or a research report. Helps the framework choose the right note type and tags for the extracted material.

## PURPOSE

This framework processes any document — a conversation transcript, book chapter, scientific paper, vault note, research report, or external chat export — and produces vault-ready notes with correct note type classification, atomic subtype assignment, grammar rule enforcement, and relationship mapping. It is the automated implementation of the Knowledge Artifact Coach (Framework — Knowledge Artifact Coach v6.0) operating in pipeline mode without human interaction.

The framework serves three use cases:
1. **Batch extraction** — processing the historical archive of ~3,500 conversations and external documents
2. **Ongoing external processing** — digesting conversations conducted outside Ora (commercial AI exports)
3. **Source document processing** — extracting knowledge from books, papers, reports, and other long-form sources

**Canonical specification:** Framework — Knowledge Artifact Coach v6.0 is the single source of truth for note types, subtypes, body schemas, quality checks, grammar rules, and output formats. This framework implements that specification as automated pipeline code. The Knowledge Artifact Coach framework defines *what* the engine produces; this document defines *how* the engine produces it.

---

## TWO OUTPUT PATHS

When the framework identifies the input as a chat (input/output pair format), it runs both paths:

- **Path 1 — Knowledge extraction:** semantic extraction → note subtype classification → grammar rules → quality gate → vault-ready atomic notes
- **Path 2 — Conversation processing:** conversation processing protocol → five-level summaries → ChromaDB conversations collection

Non-chat documents (books, papers, notes) run Path 1 only.

Path 2 delegates to the existing conversation processing pipeline (frameworks/book/conversation-processing.md). This framework calls it as infrastructure, not reimplementing it.

---

## INPUT CONTRACT

**Accepted input formats:**
- PDF (.pdf) — text extraction with heading/table detection
- Word (.docx) — text, headings, tables, lists
- PowerPoint (.pptx) — slide text and speaker notes
- HTML (.html, .htm) — strip markup, preserve structure
- RTF (.rtf) — strip formatting
- Plain text (.txt) — passthrough with minimal cleanup
- Markdown (.md) — passthrough

**Input sources:**
- Files placed in a processing queue directory
- Direct API call from the orchestrator with a file path
- Batch processing manifest pointing to a directory of files
- Run-time configuration block declaring source provenance and per-document parameters. When an invocation binds a project nexus + framework-configuration profile (Plugin Convention §14), the framework reads the values declared in the `## CONFIGURATION INTERFACE` section below — `${config.chromadb_collection}`, `${config.output_type_override}`, voice-tagging properties, working-dir locations, etc. — and adjusts its behavior accordingly. With no project binding, the framework runs with the documented defaults (general-purpose knowledge extraction; no project-specific tagging).

**Pre-processing:** All inputs pass through the format conversion utility (`orchestrator/tools/format_convert.py`) before any analysis. The converter normalizes all formats to clean markdown with heading structure preserved. All subsequent pipeline stages operate on markdown, never on raw binary formats.

### Search-Path Resolution (Optional)

When configured with the `${config.search_paths}` list (see CONFIGURATION INTERFACE below), the framework's INPUT CONTRACT resolves bare filename references by walking the configured search paths in declaration order. The first matching file is loaded. The default behavior (empty search-paths list) preserves direct-path resolution.

**Configuration source:** the `search_paths` key in the bound project's `framework_configurations` profile (Plugin Convention §14). Example shape:

```yaml
search_paths:
  - /Users/oracle/Documents/vault
  - /Users/oracle/Documents/vault/Sources/<Project Research Dir>
```

Search-path resolution is opt-in per run. It supports the pattern where source dossiers physically live in a project-scoped subdirectory while the consuming references (Mind files, Trackers, methodology docs, Editorial Routers, Registries) continue to reference them by bare canonical filename. The search-path list lets the framework locate them without forcing every consuming reference to update its path. The first-matching-wins resolution preserves backward compatibility for any reference still pointing at vault root.

## CONFIGURATION INTERFACE

When this framework is invoked with a project nexus + a
`framework_configurations` profile bound (Plugin Convention §14), it
reads the following configuration keys from the project's profile.
With no project binding, each key falls back to its documented default,
and the framework runs project-neutral (general-purpose knowledge
extraction into the standard `knowledge` collection with no
project-specific tagging).

- **`chromadb_collection`** (string, default: `knowledge`) — Target ChromaDB collection for extracted atomic notes. Project-specific runs typically route to a project-scoped collection (e.g., a publication's research collection) rather than the general knowledge collection.
- **`output_type_override`** (object `{from, to}` or null, default: null) — When set, atomic notes that would otherwise carry `type: <from>` are emitted with `type: <to>`. Used by project-specific runs to redirect note types into project-scoped buckets.
- **`voice_property_name`** (string or null, default: null) — When set, every generated note carries a frontmatter property of this name whose value comes from the per-document configuration's voice slug. Used by publishing projects that organize notes by editorial voice.
- **`voice_property_namespace`** (string or null, default: null) — Prefix the voice slug carries (e.g., `<publication>-pen-name`). Documentation hint for project authors; the framework doesn't enforce it.
- **`dossier_property_name`** (string or null, default: null) — When set, every generated note carries a frontmatter property of this name whose value is the source dossier filename.
- **`nexus_value`** (string or null, default: null) — When set, every generated note carries `nexus: [<value>]` in its frontmatter, linking the note to the project's conceptual layer.
- **`calibration_profile`** (string, default: `historical-archive`) — Which calibration profile to use (see CALIBRATION PROTOCOL below).
- **`auto_reject_log_path`** (string, default: `${ORA_HOME}/data/processing-manifest.jsonl`) — Where auto-rejected notes get logged. Project-specific runs often route this to a project-scoped log file.
- **`working_dir_pattern`** (string, default: `vault/temp/processing-run-${date}/${dossier_stem}/`) — Template for the per-run working directory (intermediate markdown, signal maps, candidate-note staging).
- **`hcp_manifest_dir_pattern`** (string or null, default: null) — When set, structural-context manifests land at the configured pattern (e.g., `Sources/MSI Research/_manifests/`); otherwise they land alongside the source document.
- **`search_paths`** (list of strings, default: `[]`) — Additional vault search paths for bare-filename reference resolution. The framework walks these in declaration order before the vault root.

The following extension points may be filled by a project overlay
(via `framework_configurations[].overlays` per §14):

- **`provenance-overlay-rules`** — Spliced after the OUTPUT CONTRACT section. Used by projects whose provenance-tagging rules go beyond what the parametric keys above express (e.g., per-voice duplicate-check scope semantics, project-specific frontmatter schemas).

---

## OUTPUT CONTRACT

**Path 1 outputs (knowledge extraction):**
- Vault-ready note files in machine-readable pipeline format (<<<NOTE_START>>> delimited blocks)
- Each note includes: complete YAML frontmatter, typed title, body in correct schema, relationship declarations, source provenance
- Notes routed to three queues: auto-approve, auto-reject, human-review
- Relationship candidates for graph builder ingestion
- Processing run metadata block (<<<RUN_METADATA>>>)

**Path 2 outputs (conversation processing):**
- Processed turn-pair chunk files per the conversation processing pipeline specification
- ChromaDB conversations collection entries
- Processing manifest updates

**Type assignments per output category** (per Reference — Ora YAML Schema rev 5):
- Source-document chunks (Path 1): `type: resource` (P2, weight 0.8)
- Extracted atomic notes (Path 1, external sources): `type: engram` + `source-derived` provenance-modifier tag (P1 with tag, weight 0.9 per Schema §6.5)
- Extracted atomic notes (Path 1, MSI source provenance): `type: engram` + `source-derived` tag + MSI provenance properties (`source_voice`, `source_dossier`, `source_dossier_section`) + `nexus: [main-street-independent]`. MSI editorial-research engrams live in the standard `Engrams/` corpus per the user's 2026-05-09 rework; column-generation frameworks retrieve voice-scoped subsets via `source_voice` filtering against the `knowledge` collection (no dedicated collection).
- Conversation turn-pair chunks (Path 2): `type: chat` (P3, weight 0.6)

**Quality guarantees:**
- Every auto-approved note passes all [AUTO] quality checks from Framework — Knowledge Artifact Coach Phase 4
- Every note has a valid subtype assignment (for atomics) verified against body schema
- All proposition-format notes (atomic, molecular) enforce the three grammar rules
- No note enters the auto-approve queue without passing the self-containedness check

<!-- ora-project-extension: provenance-overlay-rules -->

---

## EXECUTION TIER

**Pipeline mode:** Orchestrator with tool access. The framework executes as a multi-pass pipeline through boot.py. Each pass is a distinct model invocation with a focused context window — raw input never persists across passes.

**Available tools:**
- file_read: Read source documents and existing vault notes
- file_write: Write extracted notes to staging directory
- file_list: Enumerate files in processing queues and vault
- chromadb_query: Check for duplicate notes via semantic similarity
- chromadb_index: Add approved notes to the knowledge collection
- vault_search: Search existing vault notes by title for deduplication

---

## INPUT TYPE DETECTION

Before extraction, classify the input to determine processing strategy. Detection runs on the markdown output from format conversion.

### Detection Rules

```
IF input contains alternating speaker blocks (User:/Assistant:, Human:/AI:,
   Q:/A:, or similar turn-pair structure)
  AND turn count >= 2
  THEN → input_type: chat
  THEN → run Path 1 + Path 2

IF input has document structure (headings, sections, formal tone,
   specification language, bibliography, abstract)
  AND estimated token count > 4000
  THEN → input_type: long_form_source
  THEN → run Path 1 with HCP context prepend

IF input has document structure
  AND estimated token count <= 4000
  THEN → input_type: short_document
  THEN → run Path 1 (standard)

IF input has YAML frontmatter with vault properties (nexus, type, tags)
  THEN → input_type: vault_note
  THEN → run Path 1 (simplified — skip classification, use existing metadata)

IF input is plain text without structure
  AND token count < 500
  THEN → input_type: fragment
  THEN → flag for human review — too small for reliable extraction

ELSE → input_type: unknown
  THEN → flag for human review
```

### Processing Strategy Per Type

| Input Type | Path(s) | HCP | Pass A Focus | Special Handling |
|---|---|---|---|---|
| chat | 1 + 2 | No | Crystallization moments, decisions, novel frameworks, validated positions | Conversation processing pipeline for Path 2 |
| long_form_source | 1 | Yes | Chapter-level claims, section arguments, thesis statements | Structural index before chunking; six context levels |
| short_document | 1 | No | Primary claims, definitions, procedures, relationships | Standard three-pass extraction |
| vault_note | 1 (simplified) | No | Reprocessing with current subtype taxonomy and grammar rules | Preserve existing frontmatter where valid |
| fragment | Review | No | N/A | Route to human review queue |

---

## THE THREE-PASS EXTRACTION ENGINE

The extraction pipeline runs three sequential passes. Each pass is a separate model invocation with a focused context window. The raw input document does not persist across passes — only the structured output of each pass feeds the next.

### Pass A — Signal Identification

**Model:** Lightweight model (sidebar slot or rag_planner slot)
**Input:** Converted markdown document + input type classification
**Output:** Structured signal map

Pass A reads the full document and produces a structured inventory of extractable signals without generating any notes. This is a triage pass — fast, cheap, focused on what's there rather than what to do with it.

**Signal types to identify:**

For all input types:
- **Crystallization moments** — points where an idea becomes precise enough for a standalone note
- **Definitional claims** — terms defined in load-bearing ways → glossary candidates
- **Causal assertions** — X causes/prevents/enables Y → causal_claim candidates
- **Process descriptions** — sequential or conditional procedures → process note candidates
- **Evaluative judgments** — ranked comparisons or quality assessments → evaluative candidates
- **Structural analogies** — domain mappings → analogy candidates
- **Governing principles** — generalizable rules about how systems work → process_principle candidates
- **Factual claims** — verifiable empirical statements → fact candidates
- **Position statements** — deliberate stances on debatable questions → position note candidates
- **Relationship signals** — explicit references between concepts (wikilinks, citations, "as discussed in", "building on")

For chat inputs additionally:
- **Decisions made** — conclusions reached during the conversation
- **Novel frameworks** — new conceptual structures proposed
- **Validated positions** — claims tested and confirmed during exchange
- **Open questions** — unresolved tensions flagged for incubation
- **Re-education content** — explanations of well-known concepts (flag for exclusion, not extraction)

For long-form sources additionally:
- **Thesis statements** — document-level and section-level arguments
- **Supporting evidence chains** — sequences of claims building to a conclusion
- **Cross-references** — internal document references between sections

**Signal map output format:**

```
<<<SIGNAL_MAP_START>>>
source_file: "[filename]"
input_type: [chat | long_form_source | short_document | vault_note]
total_signals: [count]
estimated_notes: [count]

signals:
  - id: S001
    type: [crystallization | definition | causal | process | evaluative |
           analogy | principle | fact | position | relationship |
           decision | framework | validated | open_question | re_education |
           thesis | evidence_chain | cross_reference]
    location: "[section heading or line range]"
    summary: "[one-sentence description of the signal]"
    proposed_note_type: [atomic | glossary | molecular | compound | process | position | moc]
    proposed_subtype: [fact | process_principle | definition | causal_claim | analogy | evaluative | null]
    confidence: [high | medium | low]
    skip_reason: "[if recommending skip — e.g., re-education, too fragmentary]"

  - id: S002
    ...
<<<SIGNAL_MAP_END>>>
```

### Pass B — Note Generation

**Model:** Primary analysis model (depth slot or breadth slot)
**Input:** Signal map from Pass A (NOT the raw document) + relevant document sections referenced by signal locations + subtype body schemas + grammar rules
**Output:** Candidate notes in machine-readable pipeline format

Pass B receives the signal map and generates complete notes for each viable signal. The model sees the signal map, the relevant document sections (pulled by signal location references), and the canonical subtype schemas and grammar rules from Framework — Knowledge Artifact Coach.

**Pass B instructions to model:**

For each signal in the signal map:

1. **Skip** if `skip_reason` is populated — do not generate a note
2. **Retrieve** the relevant section from the source document using the signal's location reference
3. **Generate** a note in the correct type and subtype schema:
   - Atomic notes: declarative title stating the claim; proposition-bullet body with actor-verb-target structure; subtype-specific body schema
   - Glossary notes: noun-based title; definition + scope + excludes + related terms
   - Molecular notes: declarative title; proposition-bullet body; constituent atom links
   - Process notes: imperative/declarative title; IF/THEN conditional body
   - Position notes: declarative title; current position + reasoning + rejected alternatives
   - Compound notes: preserve as-is with extracted principles section
4. **Enforce grammar rules** on all proposition-format notes (atomic, molecular):
   - Rule 1 — Named Actors: every bullet names its actor explicitly
   - Rule 2 — Resolved Pronouns: no unresolved pronouns; restate actor over using "it", "they", "this"
   - Rule 3 — Concrete Verbs: active voice, specific verbs, no hidden actors
5. **Assign relationships** using the 13-type taxonomy: supports, contradicts, qualifies, extends, supersedes, analogous-to, derived-from, enables, requires, produces, precedes, parent, child
6. **Emit** each note in the machine-readable pipeline format (<<<NOTE_START>>> blocks)

**MSI provenance tagging** (when run-time configuration declares MSI source provenance per the INPUT CONTRACT). For each generated note, additionally:

7. Keep the default `type: engram` and append the `source-derived` provenance-modifier tag (per Schema §6.5; lowers effective weight to 0.9 — AI/external-author claims sit below user-authored).
8. Set `source_voice` from the per-document configuration's voice slug (e.g., `msi-pen-name-mary-magdalena`)
9. Set `source_dossier` to the source filename (e.g., `Reference — MSI Mary Magdalena Voice Library.md`)
10. Set `source_dossier_section` from the HCP structural index — the section heading or topic-path the signal originated in (e.g., `Part 1 — Bible-fluency substrate / Economic justice and the prophets`)
11. Set `nexus: [main-street-independent]`
12. Emit the note per the MSI Research extracted atomic note template in Reference — Ora YAML Schema §12

**Body schema enforcement:**

| Subtype | Required Elements |
|---|---|
| fact | Verifiable claim bullets; evidence basis named |
| process_principle | Transferable governing rule; cross-context applicability |
| definition | Opening definitional proposition; scope; boundary conditions |
| causal_claim | Cause → effect with explicit directionality; mechanism; boundary conditions |
| analogy | Two domains named; structural correspondence mapped; limits stated |
| evaluative | Evaluative claim with explicit criteria; evidence; comparison points |

### Pass C — Quality Pre-Screening

**Model:** Lightweight model (sidebar slot or rag_planner slot)
**Input:** Candidate notes from Pass B
**Output:** Quality-screened notes routed to three queues

Pass C applies rapid quality checks to each candidate note before the full quality gate. This is a fast-fail filter — it catches obvious problems cheaply so the full quality gate doesn't waste cycles on clearly bad notes.

**Pass C quick checks:**

1. **Self-containment check** — Read each bullet in isolation. Does it make sense without the title or other bullets? If not → flag
2. **Single-claim check** — Does the note make exactly one claim (for atomics)? If the title contains "and" connecting two independent ideas → flag
3. **Complete-sentence title check** — Is the title a declarative claim (for atomics/molecular)? If it's a topic label → flag
4. **Schema conformance check** — Does the body follow the subtype's required schema? Missing elements → flag

**Routing logic:**

```
IF all four checks pass
  THEN → quality_gate queue (proceed to automated quality gate)

IF any check fails with clear violation
  AND the violation is structural (topic-label title, multiple claims, empty body)
  THEN → auto_reject queue

IF any check fails with ambiguity
  OR the note type is compound (always requires human review)
  THEN → human_review queue
```

---

## AUTOMATED QUALITY GATE

The quality gate is Python rule-based logic that runs on the quality_gate queue output from Pass C. No model invocation required — this is pure programmatic evaluation.

### Auto-Approve Criteria (all must pass)

A note is auto-approved if ALL of the following are true:

1. **Grammar scan passes** — no passive voice with hidden actor, no unresolved pronouns, no bullets without named actors (for proposition-format notes)
2. **Schema conformance** — body matches the subtype's required schema (all required elements present)
3. **Title is declarative claim** — not a topic label, not a question (for atomic/molecular)
4. **Exactly one claim** — title expresses a single proposition (for atomic)
5. **YAML frontmatter complete** — nexus, type, tags present; subtype present for atomics; type is `engram` for extracted atomic notes (with `source-derived` tag for external-source extracts) / `resource` for source-document chunks (per Reference — Ora YAML Schema §4 rev 5)
6. **Limits/boundary section present** — for causal_claim, analogy, and process_principle subtypes
7. **Self-containedness verified** — each bullet parseable in isolation (heuristic: no bullet starts with "This", "It", "They" without prior referent in the same bullet)
8. **Minimum length** — body contains at least 2 proposition bullets (for atomic/molecular)
9. **No duplicate title** — title does not match any existing note title within similarity threshold (>0.90 cosine). Scope of the duplicate check depends on the run's source provenance: general runs check against the full `knowledge` collection; MSI runs check against the `knowledge` collection scoped by `source_voice` (a duplicate is only a duplicate within the same voice; cross-voice duplication is acceptable and expected, since the same concept may legitimately appear in multiple voices' editorial substrates with different perspectives).

### Auto-Reject Criteria (any one triggers rejection)

A note is auto-rejected if ANY of the following are true:

1. **Empty body** — note has title and frontmatter but no content
2. **Topic-label title** — title is a noun phrase with no predicate (e.g., "Consciousness", "The Observer Effect")
3. **Re-education content** — note restates well-known concepts without novel synthesis (flagged in Pass A)
4. **Fragment** — note body contains fewer than 2 complete sentences or bullets
5. **Duplicate** — note title matches an existing vault note at >0.95 cosine similarity

### Human-Review Queue Criteria (any one triggers review)

A note is routed to human review if ANY of the following are true:

1. **Potential contradiction** — note's claim appears to contradict an existing vault note (detected via relationship graph or semantic search)
2. **Uncertain subtype** — Pass A confidence was "low" on the proposed subtype
3. **Cross-domain analogy** — analogy subtype with domains the pipeline hasn't seen before
4. **Compound note** — all compound notes require human confirmation of emergent complexity
5. **Borderline self-containedness** — some bullets pass, some are ambiguous
6. **Potential duplicate** — title similarity 0.85-0.95 with existing note (needs human judgment)
7. **Missing glossary dependency** — note uses a term that appears load-bearing but has no glossary entry
8. **Position note** — all position notes require human confirmation (they represent the user's intellectual stance)

---

## HCP INTEGRATION (Long-Form Sources)

When `input_type: long_form_source`, the framework prepends Hierarchical Context Protocol metadata before chunking for extraction.

### Structural Index Creation

Before processing, build a structural index of the document:

```
STRUCTURAL INDEX
Document: "[title]"
Total sections: [count]
Estimated tokens: [count]

Level 1 — Document thesis: "[one-sentence thesis]"
Level 2 — Parts/major sections:
  Part I: "[section title]" — "[section argument]"
  Part II: "[section title]" — "[section argument]"
Level 3 — Chapters/subsections:
  1.1: "[title]" — "[chapter-level claim]"
  1.2: "[title]" — "[chapter-level claim]"
```

### Context Levels (prepended to each chunk)

When processing a chunk from a long-form source, prepend these context levels:

1. **Positional breadcrumb** — where this chunk sits in the document structure (e.g., "Part II > Chapter 4 > Section 4.2")
2. **Source-level thesis** — the document's overall argument
3. **Part/section argument** — the argument of the part containing this chunk
4. **Chapter-level claim** — the specific claim of the chapter containing this chunk
5. **Local narrative continuity** — what the immediately preceding section established
6. **Role declaration** — "You are extracting knowledge from a [document type]. The following chunk is from [location]."

### Similarity-Scaling Rules

Context levels are included based on semantic similarity between the chunk and the broader context:

| Similarity Score | Context Levels Included |
|---|---|
| >= 0.90 | All six levels |
| 0.75 - 0.89 | Levels 1-4 |
| 0.60 - 0.74 | Levels 1-2 |
| < 0.60 | Exclude chunk (too dissimilar from document's themes) |

### Structural-Context Manifest

For each long-form source processed, the framework writes a per-document structural-context manifest alongside the extraction outputs. The manifest captures the structural index, the chunk-by-chunk context-level inclusions, and the section-to-extracted-note mapping. This artifact preserves the HCP context state for downstream review (human-review queue inspection; calibration tuning; future re-extraction) and lets column-generation frameworks re-establish dossier-section context when retrieving an atomic whose interpretation depends on the surrounding section's argument.

**Manifest format:**

```yaml
<<<STRUCTURAL_MANIFEST>>>
source_file: "Reference — MSI Mary Magdalena Voice Library.md"
source_format: md
total_sections: 12
extraction_date: 2026-05-08
source_voice: msi-pen-name-mary-magdalena

structural_index:
  level_1_thesis: "Mary Magdalena's voice substrate is the Gnostic-apocryphal Mary corpus, drawn on for the Seal movement of four-movement columns..."
  level_2_parts:
    - title: "Part 1 — Gnostic-apocryphal Mary corpus"
      argument: "..."
      sections:
        - title: "§1.1 Gospel of Mary"
          claim: "..."
        - title: "§1.2 Pistis Sophia"
          claim: "..."

extraction_map:
  - section: "Part 1 / §1.1 Gospel of Mary"
    notes_extracted: 4
    note_ids:
      - "Mary Magdalena teaches the disciples after the Resurrection per the Gospel of Mary"
      - "Peter's challenge to Mary's authority surfaces the canonical-vs-Gnostic gender tension"
      - "..."
<<<MANIFEST_END>>>
```

**Manifest location.** For MSI runs, manifests write to `Sources/MSI Research/_manifests/[dossier-stem]-manifest.yaml` (vault-discoverable, version-controlled, alongside the dossiers themselves). For general (non-MSI) long-form runs, manifests write to `~/ora/data/extraction-manifests/[dossier-stem]-manifest.yaml`.

---

## QUESTION GENERATION (Post-Extraction Enrichment)

After Pass C, generate questions about each extracted note. This serves two purposes:

1. **Quality signal** — if the system cannot generate a meaningful question about a note, the note may not be self-contained enough → flag for human review
2. **Relationship seeding** — questions about one note may semantically match content in other notes, providing discovery signals for relationship Pass 2

### Question Types

For each extracted note, generate:
- **Implication question** — "What does this imply for [related domain]?"
- **Challenge question** — "What evidence would weaken or falsify this claim?"
- **Adjacent question** — "What is the next question this raises?"

### Quality Check Integration

```
IF the system generates 0 meaningful questions about a note
  THEN flag for human review (possible self-containedness failure)

IF a generated question semantically matches (>0.80 cosine) an existing vault note
  THEN create a relationship candidate: source_note → [matched note]
       with type: extends or supports (determined by question type)
       and confidence: medium
```

---

## ENTITY CO-OCCURRENCE FOR RELATIONSHIP DISCOVERY

Lightweight NLP entity extraction runs as part of Pass A to provide a third relationship discovery signal alongside explicit references (Pass 1 in Phase 7) and semantic similarity (Pass 2 in Phase 7).

### Process

1. Extract named entities from each note using spaCy or equivalent: proper nouns, technical terms, domain concepts
2. Build an entity co-occurrence matrix across all notes in the current extraction batch
3. When two notes share 2+ non-trivial entities but are not already linked by explicit reference or high semantic similarity → flag as relationship candidate

### Confidence Assignment

Entity co-occurrence relationships receive `confidence: low` by default. They are discovery signals, not confirmed relationships. They feed the human review queue, not the auto-approve path.

---

## DEDUPLICATION MODULE

Runs after batch extraction or as an ongoing check when new notes are produced.

### Three Categories

1. **Clean merge** — identical or near-identical notes. Keep the stronger expression (more complete body, more precise title, more recent source). Add `arrival_history` to the surviving note recording the merge.
2. **Variant merge** — same core concept expressed differently, each capturing a distinct facet. Keep both notes. Add a `qualifies` or `extends` relationship between them. Add `arrival_history` noting the variant detection.
3. **False positive** — surface-similar notes that are actually about different things. Add a `surface-similar` note in the deduplication log. No merge, no relationship. Flag for human review if similarity > 0.90 to confirm.

### Trigger

```
IF new note title cosine similarity > 0.85 with any existing vault note
  THEN → deduplication review (auto-categorize or human review based on body comparison)

IF body-level cosine similarity > 0.90 between two notes in the same extraction batch
  THEN → deduplication review
```

---

## BATCH PROCESSING MODE

Queue management for large jobs (historical archive of ~3,500 conversations).

### Queue Architecture

```
INPUT QUEUE          → ordered by type and date (oldest first)
  ↓
FORMAT CONVERSION    → format_convert.py normalizes to markdown
  ↓
TYPE DETECTION       → classifies input type, routes to correct track
  ↓
EXTRACTION PIPELINE  → Pass A → Pass B → Pass C (per-document, context resets between documents)
  ↓
QUALITY GATE         → auto-approve / auto-reject / human-review routing
  ↓
DEDUPLICATION        → within-batch and cross-vault duplicate detection
  ↓
REVIEW QUEUES
  ├── auto-approve   → vault write queue
  ├── human-review   → held for human review interface
  └── auto-reject    → logged with rejection reason
  ↓
VAULT WRITE QUEUE    → writes notes to vault staging directory
  ↓
RELATIONSHIP INDEX   → updates relationship graph with new connections
```

### Context Window Management

Each document gets its own context window — no cross-document contamination. For documents that exceed the context window:

```
IF document tokens > context_window_budget
  AND input_type == long_form_source
  THEN → chunk with HCP context prepend, process each chunk as independent extraction

IF document tokens > context_window_budget
  AND input_type == chat
  THEN → split at natural conversation boundaries (topic shifts), process each segment independently
```

### Progress Tracking

The batch processor maintains a processing manifest at `~/ora/data/processing-manifest.json`:

```json
{
  "started": "ISO 8601 timestamp",
  "total_files": 0,
  "processed": 0,
  "failed": 0,
  "notes_extracted": 0,
  "notes_approved": 0,
  "notes_rejected": 0,
  "notes_review": 0,
  "current_file": "",
  "files": {
    "filename.md": {
      "status": "completed | failed | pending",
      "processed_at": "ISO 8601",
      "notes_extracted": 0,
      "error": null
    }
  }
}
```

### Sleep-Wake Cycle

For overnight batch processing:
- Processing continues until the queue is empty or a configurable time limit is reached
- State is saved to the manifest on each file completion — processing is resumable
- If interrupted, the next run picks up from the last incomplete file

---

## NAMED FAILURE MODES

**The Schema Drift.** The extraction engine generates notes that don't match the subtype's body schema — a "causal_claim" without explicit directionality, an "analogy" without two named domains. The quality gate catches this, but the root cause is Pass B instructions that don't enforce schema strongly enough. Keep Pass B's schema templates precise and up to date with Framework — Knowledge Artifact Coach.

**The Over-Extraction.** Generating too many notes from a single document, especially low-quality fragments that don't pass the minimum sufficiency test. Pass A should be conservative in signal identification — better to miss a marginal signal than to generate a fragment that wastes quality gate cycles. Target: 60-70% auto-approve rate.

**The Grammar Decay.** Notes that pass schema checks but violate the three grammar rules — hidden actors in passive voice, unresolved "it" and "this", nominalized verbs. The grammar scan in the quality gate must be strict. Common pattern: a note that starts strong with named actors but drifts to passive voice by the third bullet.

**The Cross-Document Bleed.** In batch processing, context from one document leaking into another document's extraction. Context window resets between documents prevent this — enforce strictly.

**The Duplicate Flood.** In large batch runs, the same concept appearing in multiple source documents generates multiple notes. The deduplication module catches this post-extraction, but the cost is wasted extraction cycles. For known-overlapping source sets, consider running cross-document analysis (Mode C logic) before extraction.

**The HCP Overhead.** For long-form sources, the six context levels consume significant context window budget. If the chunk is highly relevant (similarity >= 0.90), all six levels are worth the cost. At lower similarity, aggressive pruning keeps the context window focused.

**The Re-Education Trap.** Chat conversations often contain the AI explaining well-known concepts to the user. These explanations are not novel knowledge — they are re-education. Pass A must flag these for exclusion. Signal: the AI's response restates textbook-level information without novel synthesis, user commentary, or contextual application.

**The Position Presumption.** The pipeline auto-generates a position note from a claim in a conversation. But position notes represent the user's deliberate intellectual stance — a claim made in passing during a chat is not a position. All position note candidates route to human review for this reason.

---

## CALIBRATION PROTOCOL

Two calibration profiles are defined: the **General Historical-Archive profile** (the original baseline, designed for the chat-archive batch population) and the **AI-Research Deliverable profile** (added 2026-05-08 to support batches of commissioned deep-research dossiers, beginning with the MSI 33-dossier corpus). Run-time configuration selects the active profile.

### Profile selection

- Default → General Historical-Archive profile.
- When `source_provenance: msi-editorial-research` is declared in the run-time configuration → AI-Research Deliverable profile is selected automatically.
- Other AI-research-style batches (commissioned dossiers, vetted external research deliverables) → AI-Research Deliverable profile is appropriate when the input population matches the profile's characteristics; opt-in via `calibration_profile: ai-research-deliverable` in the run-time configuration.

### General Historical-Archive Profile

Before full processing, run calibration on a 50-document sample covering the full input type range.

**Calibration Metrics:**

| Metric | Target | Adjustment If Off-Target |
|---|---|---|
| Auto-approve rate | 60-70% | If low: relax quality gate thresholds. If high: tighten Pass C screening |
| Auto-reject rate | 10-15% | If low: Pass A may be too conservative. If high: Pass B quality is poor |
| Human review queue rate | 20-25% | If high: quality gate criteria too strict. If low: may be missing edge cases |
| Duplicate rate | <40% of batch | If high: add cross-document deduplication before extraction |
| Subtype distribution | process_principles >= 10% of atomics | If low: Pass A signal detection under-identifies governing principles |
| Grammar scan failure | <5% | If high: Pass B grammar rule enforcement is weak |

**Calibration Procedure:**

1. Select 50 documents: 20 chat transcripts, 15 short documents, 10 long-form sources, 5 vault notes
2. Run full pipeline on sample
3. Human-review ALL output (including auto-approved notes) to establish ground truth
4. Compute metrics against ground truth
5. Adjust pipeline parameters per the adjustment column
6. Re-run on the same 50 documents
7. Verify metrics are within target range

### AI-Research Deliverable Profile

For batches of commissioned deep-research dossiers (e.g., the MSI editorial-research corpus). These input populations differ from the historical-archive baseline:

- Source material is professionally written and structurally curated (often three-part deep-research deliverables with topical subsections)
- Auto-approve rates trend higher because structural conformance is high in the source
- Auto-reject rates trend lower because the source is intentionally curated rather than incidentally captured
- Human-review rate trends higher because dense load-bearing-but-ambiguous claims are common in research-deliverable prose
- Grammar enforcement should be tighter because the source is professionally edited; failures here suggest Pass B grammar enforcement is weak rather than source quality

**Calibration Metrics:**

| Metric | Target | Adjustment If Off-Target |
|---|---|---|
| Auto-approve rate | 60-70% | If significantly off, the threshold for Pass C structural conformance checks needs adjustment for the higher-baseline input |
| Auto-reject rate | 5-10% (lower than historical-archive baseline) | If matching the historical-archive baseline (10-15%), Pass A signal identification may be missing structurally complex but valid signals in dense research prose |
| Human review queue rate | 25-35% (higher than historical-archive baseline) | Dense AI-research deliverables surface more load-bearing-but-ambiguous claims — accept this as the input characteristic rather than tightening Pass C |
| Duplicate rate | <40% of batch | Same handling as the historical-archive profile; for cross-dossier overlap (same author cited across multiple dossiers), add cross-document deduplication before extraction |
| Subtype distribution | Heavy on `fact`, `process_principle`, and `definition`; medium on `causal_claim` and `analogy`; light on `evaluative` and `position` | Pass A signal-type frequency reflects the AI-research deliverable's topical-substrate nature |
| Grammar scan failure | <2% (tighter than historical-archive baseline) | Source is professionally edited; if higher, Pass B grammar rule enforcement is weak rather than the source being noisy |

**Calibration sample size:** A representative sample of the input-shape range is sufficient — typically 5-7 documents covering the structural variation present in the batch (e.g., long-form three-part / long-form with author corpus / character-background / lane-overlay / memorandum / quote-corpus shape). The 50-document calibration sample of the historical-archive profile is unnecessary for batches with narrower input-shape variation.

**Calibration Procedure** (same shape as the historical-archive procedure but parameterized to this profile):

1. Select 5-7 documents covering the input-shape variation present in the batch
2. Run full pipeline on sample
3. Human-review ALL output (including auto-approved notes) to establish ground truth
4. Compute metrics against the AI-Research Deliverable Profile targets above
5. Adjust pipeline parameters per the adjustment column
6. Re-run on the same sample
7. Verify metrics are within target range

The MSI 33-dossier corpus calibration sample (2026-05-08): Stewart Letterkenski Character Dossier (character-background); Joanna Rivera Blackwell Theological Substrate (long-form three-part with author-corpus subsection); Ashley Wagner Cultural-Text and Formation Substrate (long-form three-part); Mark Paulson Climate-Policy Overlay (lane-overlay); Thomas Reynolds Gerrymandering-Solution Memorandum (short-document, HCP-off); Hector Rentier Quote Corpus (quote-and-citation indexed format — distinct from prose dossier shapes).

### Auto-Reject Log Location

Auto-rejected notes are logged with rejection reason for calibration-tuning history. Log location depends on the run's source provenance:

- Default → `~/ora/data/auto-reject-log.jsonl` (general-purpose log; rotation policy per `~/ora/data/` retention rules)
- MSI runs → `~/ora/data/msi-research-rejects.jsonl` (separate log for the MSI editorial-research corpus; permanent calibration record for tuning Pass C thresholds against future MSI runs)

---

## PIPELINE INTEGRATION POINTS

### With boot.py (Orchestrator)

The document processing framework is invoked by the orchestrator for:
- On-demand document processing (user submits a document via chat interface)
- Batch processing jobs triggered by queue directory watcher or manual invocation

### With Relationship Graph (Phase 7)

- Pass A identifies explicit references → feeds Phase 7 Pass 1 (relationship_discovery.py)
- Entity co-occurrence → feeds Phase 7 as a third discovery signal
- Question generation → feeds Phase 7 Pass 2 (semantic similarity clustering)
- All new relationships → indexed into relationship-graph.db via relationship_graph.py

### With RAG Engine (Phase 8)

- Extracted notes → indexed into the standard ChromaDB `knowledge` collection. MSI editorial-research engrams (when `source_provenance: msi-editorial-research` is declared at run-time) live in the same collection but are scoped at retrieval time by `source_voice` filtering per the MSI column-generation frameworks' INPUT CONTRACT.
- Note metadata (subtype, tags, relationships) → available for RAG priority stack assembly
- Glossary notes → available for dependency resolution during context assembly
- MSI Research notes → consumed by MSI column-generation frameworks via voice-scoped retrieval (column-generation framework's INPUT CONTRACT queries the MSI collection filtered by `source_voice` matching the writing voice currently producing the column)

### With Conversation Processing Pipeline

- Chat-type inputs → Path 2 delegates to conversation-processing.md pipeline
- Inline mode (ongoing Ora conversations) → handled by conversation pipeline directly, not this framework
- Batch mode (historical/external chats) → this framework detects chat type and routes to conversation pipeline

### With Human Review Interface (Phase 10 Step 14)

- Human review queue → served by the review web interface
- Approve/reject/edit decisions → fed back to quality gate calibration
- Edit-in-place → updated notes re-enter the vault write queue
