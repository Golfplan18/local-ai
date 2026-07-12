"""Knowledge indexer — indexes vault notes into ChromaDB's `knowledge`
collection per Reference — Ora YAML Schema (rev 3, 2026-04-30).

Usage:
    # Index all .md files in a directory:
    python3 knowledge_index.py ~/Documents/vault/Engrams/

    # Index a single file:
    python3 knowledge_index.py ~/Documents/vault/Engrams/inversion.md

    # Re-index (clear and rebuild):
    python3 knowledge_index.py --reindex ~/Documents/vault/Engrams/

The indexer reads each .md file, parses YAML frontmatter (block-list
form per Schema §10 rule 3), and indexes the content into ChromaDB.
Already-indexed paths are skipped unless --reindex is used.

ChromaDB metadata schema (Phase 5.2):

    Always present:
        path           — absolute file path. Also the ChromaDB id for
                         single-record files; a file whose body exceeds one
                         HCP chunk is stored as multiple records with ids
                         "<abspath>#chunk-N" (see the HCP chunked-indexing
                         constants below). Delete/reindex flows must use
                         delete_file_records(), which resolves by path.
        source         — basename
        title          — derived from filename (Schema §10 rule 8)
        nexus          — comma-joined string ("ora" / "ora,project_b" / "")
        type           — Schema §4 type vocabulary (one of 12)
        tags           — list of strings (preserved as-is from YAML)
        tag_archived   — bool (extracted from tags for fast where-filter)
        tag_incubating — bool
        tag_private    — bool

    Standard-property fields (present when YAML carries them):
        subtype                — atomic-only per Schema §7
        relationships          — JSON-serialized list of {type, target, confidence}
        source_file            — DP source provenance
        source_format
        source_path
        processed_date
        chunk_index            — int (from frontmatter, or stamped by the
                                 HCP chunked-indexing path: 1-based)
        total_chunks           — int (ditto)
        source_document        — JSON-serialized list of source wikilinks

    Conditional fields (present per §8):
        writing
        project_type           — JSON-serialized list
        hub                    — int
        source_duration_seconds
        transcription_model
        transcription_date
        transcription_language

    Legacy mental-model retention (non-canonical):
        triggers               — kept because it materially affects
                                 mental-model retrieval; pre-schema field

ChromaDB cannot filter on list-membership in metadata where-clauses, so
list-typed schema fields (`tags`, `relationships`, `source_document`,
`project_type`) get parallel scalar extracts where filterability is
needed. The full lists are still preserved for display and round-trip.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable, Iterable

import yaml

CHROMADB_PATH = os.path.expanduser("~/ora/chromadb/")

# Upper bound (chars) on BOTH the stored ChromaDB document and the text sent
# to the embedder. Derived from the qwen3-embedding-8b input ceiling —
# 32k tokens × ~4 chars/token ≈ 128k chars — with margin. This is a safety
# guard against pathological files (multi-megabyte exports, log dumps), NOT
# a tuning knob: normal notes and articles are far below it and index in
# full. Smaller embedders (e.g. bge-m3, 8k tokens) truncate the input at
# the model layer, which matches prior behavior.
MAX_INDEX_CHARS = 120_000

# --- HCP chunked indexing (Hierarchical Context Protocol) -------------------
# A file whose body exceeds one HCP chunk is indexed as MULTIPLE records —
# one per chunk, ids "<abspath>#chunk-N" (1-based), each stamping the
# chunk_index / total_chunks metadata fields and carrying its HCP context
# prepend in the stored document. Files at or below one chunk keep the
# original single-record layout (id = abspath). Before this, a long file
# was ONE record hard-truncated at MAX_INDEX_CHARS — everything past
# ~40 pages of a 100-page document was silently unretrievable.
# Canonical spec: vault "Specification — Hierarchical Context Protocol.md".
#
# Both values are PROVISIONAL tuning constants (judgment-set, not
# calibrated; retune freely). CHUNK_THRESHOLD_CHARS ≈ one chunk of text at
# ~4 chars/token — "chunk only when the file exceeds one chunk".
HCP_MAX_CHUNK_TOKENS = 2000                       # provisional — mirrors hcp.DEFAULT_MAX_CHUNK_TOKENS
CHUNK_THRESHOLD_CHARS = HCP_MAX_CHUNK_TOKENS * 4  # provisional — chunking trigger


# Tag values that need fast where-filterable boolean extracts.
# Schema §6.5 — these three tags drive the RAG retrieval filters.
_FILTERABLE_TAGS = ("archived", "incubating", "private", "msi-news")

# Properties retired per Schema §9 — drop from metadata if a legacy
# file still carries them.
_RETIRED_PROPERTIES = frozenset({
    "title",  # Schema §10 rule 8 — filename is the title
    "content",
    "use",
    "state",
    "verification_status",
    "confidence",
    "provenance",
    "provenance_score",
    "framework_version",
    "execution_tier",
    "domain",
    "purpose",
    "last-updated",
    "pipeline_step",
})

# Standard properties from Schema §7 that the indexer surfaces flat in
# ChromaDB metadata. List-typed values become JSON strings.
_STANDARD_SCALAR_FIELDS = (
    "subtype",
    "source_file",
    "source_format",
    "source_path",
    "processed_date",
    "chunk_index",
    "total_chunks",
)

_STANDARD_LIST_FIELDS = (
    "source_document",
)

# Conditional properties from Schema §8.
_CONDITIONAL_SCALAR_FIELDS = (
    "writing",
    "hub",
    "source_duration_seconds",
    "transcription_model",
    "transcription_date",
    "transcription_language",
)

_CONDITIONAL_LIST_FIELDS = (
    "project_type",
)


# ---------------------------------------------------------------------------
# Embedding (Ollama, kept patchable for tests)
# ---------------------------------------------------------------------------


def _nomic_embed(text: str):
    """Embed text via the canonical embedding module (Ollama-backed).

    Routes through `orchestrator.embedding.get_embedding_function()` so
    the embedder is consistent with what the collection itself uses.
    Returns a list of floats on success, or None if Ollama is
    unreachable. Cross-platform: works wherever Ollama runs.

    On None: the caller doesn't pass `embeddings=` to chromadb, and the
    collection's bound embedding_function (also Ollama) re-attempts —
    raising loudly if Ollama is genuinely down rather than silently
    substituting a different model.
    """
    try:
        from orchestrator.embedding import get_embedding_function
        ef = get_embedding_function()
        result = ef([text])
        if not result:
            return None
        emb = result[0]
        return emb.tolist() if hasattr(emb, "tolist") else list(emb)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and body from a markdown file.

    Uses PyYAML's safe_load to handle the schema-canonical block-list
    form (Schema §10 rule 3). Returns ({}, content) for files without
    frontmatter.
    """
    if not content.startswith("---"):
        return {}, content

    end = content.find("\n---", 3)
    if end == -1:
        return {}, content

    yaml_block = content[3:end].strip()
    body = content[end + 4:].strip()

    if not yaml_block:
        return {}, body

    try:
        parsed = yaml.safe_load(yaml_block)
    except yaml.YAMLError:
        return {}, body

    if not isinstance(parsed, dict):
        return {}, body

    return parsed, body


# ---------------------------------------------------------------------------
# Body filtering helpers
# ---------------------------------------------------------------------------


def strip_markdown_sections(body: str, section_titles: Iterable[str]) -> str:
    """Remove whole level-2 markdown sections by heading title.

    A section runs from its ``## `` heading line through the line before
    the next ``## `` heading (or EOF). Nested ``###`` subsections inside a
    stripped section are removed with it. Heading matching is
    case-insensitive and whitespace-trimmed, so ``##  sources `` matches
    the title ``"Sources"``.

    Universal helper — callers compose corpus-specific body filters from
    it (see orchestrator/tools/index_msi_news.py) and pass them to
    ``index_file(body_filter=...)``.
    """
    wanted = {str(t).strip().lower() for t in section_titles}
    out: list[str] = []
    skipping = False
    for line in body.split("\n"):
        # "## " matches only level-2 headings: "### x" fails the
        # startswith because its third char is "#", not a space.
        if line.startswith("## "):
            skipping = line[3:].strip().lower() in wanted
            if skipping:
                continue
        if not skipping:
            out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Metadata composition (Phase 5.2)
# ---------------------------------------------------------------------------


def _normalize_nexus(value: Any) -> str:
    """nexus is a list per Schema §3. Flatten to a comma-joined string for
    ChromaDB scalar matching. Empty / None → empty string."""
    if value is None or value == "" or value == []:
        return ""
    if isinstance(value, list):
        return ",".join(str(v) for v in value if v)
    return str(value)


def _normalize_tags(value: Any) -> list[str]:
    """tags is a list per Schema §3. Coerce single-string legacy form to
    a one-element list. Empty / None → []."""
    if value is None or value == "" or value == []:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None and str(v) != ""]
    return [str(value)]


def _filename_title(filepath: str) -> str:
    """Filename is the title per Schema §10 rule 8."""
    return os.path.basename(filepath).rsplit(".", 1)[0]


def _compose_chroma_metadata(filepath: str, meta: dict[str, Any]) -> dict[str, Any]:
    """Compose the ChromaDB metadata dict for a parsed vault note.

    Drops retired Schema §9 properties. Adds the Phase 5.2 boolean
    extracts for fast tag-based where-filtering. Serializes list-typed
    standard / conditional fields as JSON strings since ChromaDB cannot
    filter on metadata list membership.
    """
    chroma_meta: dict[str, Any] = {
        "path":   os.path.abspath(filepath),
        "source": os.path.basename(filepath),
        "title":  _filename_title(filepath),
    }

    # Core fields (always present; absence written as empty)
    chroma_meta["nexus"] = _normalize_nexus(meta.get("nexus"))
    chroma_meta["type"]  = str(meta.get("type", ""))

    tags = _normalize_tags(meta.get("tags"))
    # ChromaDB rejects empty list metadata, so only emit `tags` when non-empty.
    # The tag_<name> booleans below stay set unconditionally so where-filters work
    # uniformly across files with and without tags.
    if tags:
        chroma_meta["tags"] = tags
    for tag_name in _FILTERABLE_TAGS:
        chroma_meta[f"tag_{tag_name}"] = tag_name in tags

    # Subtype is atomic-scoped per Schema §7. Skip if not atomic-tagged.
    subtype_value = meta.get("subtype")
    if subtype_value and "atomic" in tags:
        chroma_meta["subtype"] = str(subtype_value)

    # Relationships — JSON-serialized list of {type, target, confidence}
    relationships = meta.get("relationships")
    if relationships:
        try:
            chroma_meta["relationships"] = json.dumps(relationships, ensure_ascii=False)
        except (TypeError, ValueError):
            pass

    # Standard scalar fields (Schema §7)
    for field in _STANDARD_SCALAR_FIELDS:
        if field == "subtype":
            continue  # handled above with atomic-tag scoping
        value = meta.get(field)
        if value is None or value == "":
            continue
        if isinstance(value, (int, float, bool)):
            chroma_meta[field] = value
        else:
            chroma_meta[field] = str(value)

    # Standard list fields → JSON-serialized
    for field in _STANDARD_LIST_FIELDS:
        value = meta.get(field)
        if value:
            try:
                chroma_meta[field] = json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                pass

    # Conditional fields (Schema §8)
    for field in _CONDITIONAL_SCALAR_FIELDS:
        value = meta.get(field)
        if value is None or value == "":
            continue
        if isinstance(value, (int, float, bool)):
            chroma_meta[field] = value
        else:
            chroma_meta[field] = str(value)

    for field in _CONDITIONAL_LIST_FIELDS:
        value = meta.get(field)
        if value:
            try:
                chroma_meta[field] = json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                pass

    # Legacy mental-model retention — `triggers` is non-canonical but
    # materially affects retrieval quality for the mental-model corpus.
    if meta.get("triggers"):
        triggers = meta["triggers"]
        if isinstance(triggers, list):
            chroma_meta["triggers"] = ", ".join(str(t) for t in triggers)
        else:
            chroma_meta["triggers"] = str(triggers)

    return chroma_meta


# ---------------------------------------------------------------------------
# Embedding text
# ---------------------------------------------------------------------------


def _build_embed_text(meta: dict[str, Any], body: str, filepath: str | None = None) -> str:
    """Build the text passed to the embedding model.

    Includes filename-derived title, mental-model triggers (when
    present, since they're a strong retrieval signal), tags, and the
    full body (guarded by MAX_INDEX_CHARS — see the constant's comment).
    Schema §9 retired `domain` — no longer included.
    """
    parts: list[str] = []
    if filepath:
        parts.append(_filename_title(filepath))
    if meta.get("triggers"):
        triggers = meta["triggers"]
        if isinstance(triggers, list):
            triggers = ", ".join(str(t) for t in triggers)
        parts.append(f"Triggers: {triggers}")
    tags = _normalize_tags(meta.get("tags"))
    if tags:
        parts.append(f"Tags: {', '.join(tags)}")
    parts.append(body[:MAX_INDEX_CHARS])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


def _chunk_record_id(doc_id: str, n: int) -> str:
    """Record id for chunk N (1-based) of a chunked file."""
    return f"{doc_id}#chunk-{n}"


def delete_file_records(collection, filepath: str) -> int:
    """Delete EVERY record a file may have in the collection — the
    single-record id (= abspath) AND any chunked records (abspath#chunk-N).

    Uses the always-present `path` metadata to find records instead of
    assuming the id layout, so callers stay correct across the
    single-record ↔ chunked transition (a file that shrank below the
    chunking threshold must not leave orphan chunk records, and vice
    versa). Returns the number of ids requested for deletion.
    """
    abspath = os.path.abspath(filepath)
    ids: set[str] = {abspath}
    try:
        existing = collection.get(where={"path": abspath})
        ids.update(existing.get("ids") or [])
    except Exception:
        pass  # where-lookup unsupported/failed — the abspath id still goes
    try:
        collection.delete(ids=sorted(ids))
    except Exception:
        return 0
    return len(ids)


def _split_for_storage(text: str, max_chars: int) -> list[str]:
    """Split text exceeding max_chars into <=max_chars pieces for storage.

    hcp.py deliberately never splits a single blank-line-delimited
    paragraph/block even when it exceeds the token budget ("oversized
    beats dropped") — the right call at the semantic-chunking layer, but
    it means one HCP chunk can still exceed MAX_INDEX_CHARS (a huge
    unbroken list/table/code fence with no blank lines). Truncating that
    at the storage layer would silently reintroduce the exact loss HCP
    exists to eliminate, just scoped to one record instead of the whole
    document. This is the storage-layer backstop: prefer a paragraph
    break, then a sentence break, falling back to a hard cut — no text is
    ever dropped, only split across more records."""
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        window = remaining[:max_chars]
        cut = window.rfind("\n\n")
        if cut < max_chars // 2:
            sentence_cut = window.rfind(". ")
            cut = sentence_cut + 2 if sentence_cut >= max_chars // 2 else -1
        if cut < max_chars // 2:
            cut = max_chars  # no good boundary — hard cut; nothing is lost
        parts.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        parts.append(remaining)
    return parts


def _index_chunked(collection, filepath: str, doc_id: str,
                   meta: dict[str, Any], body: str, stats: dict[str, int],
                   verbose: bool) -> bool:
    """Index a long file as one record per HCP chunk (further split into
    multiple storage records via _split_for_storage when a single chunk's
    formatted text exceeds MAX_INDEX_CHARS).

    Returns True when chunked records were written; False to signal the
    caller to fall back to the single-record path — for fewer than two
    HCP chunks, an HCP failure, or a collection.add() failure. Fail OPEN
    toward the old behavior so content is never lost to an ingest error,
    and so a force-reindex (which already deleted the file's prior
    records before this runs) never leaves the file with zero records
    just because one batched write failed.
    """
    try:
        # Lazy import — hcp pulls in the embedding layer for its
        # similarity scorer; keep module import light.
        from orchestrator.tools.hcp import (
            format_chunk_for_extraction, process_long_form)
        chunks = process_long_form(body, max_chunk_tokens=HCP_MAX_CHUNK_TOKENS)
    except Exception as e:
        print(f"  HCP chunking failed for {filepath} ({type(e).__name__}: {e}) "
              f"— falling back to single-record indexing.", file=sys.stderr)
        return False
    if len(chunks) < 2:
        return False

    total = len(chunks)
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    embeddings: list[Any] = []
    for n, chunk in enumerate(chunks, 1):
        # The stored document is prepend + chunk, so what gets retrieved
        # carries the HCP context block.
        doc_text_full = format_chunk_for_extraction(chunk)
        parts = _split_for_storage(doc_text_full, MAX_INDEX_CHARS)
        base_id = _chunk_record_id(doc_id, n)
        for p, part_text in enumerate(parts, 1):
            record_id = base_id if len(parts) == 1 else f"{base_id}-part-{p}"
            chunk_meta = _compose_chroma_metadata(filepath, meta)
            chunk_meta["chunk_index"] = n
            chunk_meta["total_chunks"] = total
            ids.append(record_id)
            documents.append(part_text)
            metadatas.append(chunk_meta)
            embeddings.append(
                _nomic_embed(_build_embed_text(meta, part_text, filepath)))

    add_kwargs: dict[str, Any] = dict(
        ids=ids, documents=documents, metadatas=metadatas)
    if all(e is not None for e in embeddings):
        add_kwargs["embeddings"] = embeddings
    # else: omit — the collection's bound embedding_function re-attempts,
    # raising loudly if the embedder is genuinely down (same contract as
    # the single-record path).

    try:
        collection.add(**add_kwargs)
    except Exception as e:
        print(f"  HCP chunked collection.add() failed for {filepath} "
              f"({type(e).__name__}: {e}) — falling back to single-record "
              f"indexing so the file isn't left with zero records.",
              file=sys.stderr)
        return False

    stats["indexed"] += 1
    if verbose:
        print(f"  + {metadatas[0]['title']} ({total} chunks, {len(ids)} records)")
    return True


def index_file(
    collection,
    filepath: str,
    stats: dict[str, int],
    meta_overrides: dict[str, Any] | None = None,
    force: bool = False,
    body_filter: Callable[[str], str] | None = None,
    verbose: bool = True,
) -> None:
    """Index a single .md file into the knowledge collection.

    meta_overrides, when given, are merged over the file's parsed
    frontmatter before metadata composition and embed-text building. This
    forces schema fields (e.g. type/tags/nexus) onto a corpus whose
    on-disk files don't carry them — notably the MSI News mirror, an rsync
    --delete copy of the cloud pipeline whose files can't be persistently
    stamped (see orchestrator/tools/index_msi_news.py).

    force=True re-indexes even when the file already has records
    (delete-by-path-then-add via delete_file_records, so chunked records
    are cleaned up too), for refreshing a changed source file. Default
    False keeps the original skip-if-already-indexed behaviour.

    A file whose body exceeds CHUNK_THRESHOLD_CHARS is indexed as one
    record per HCP chunk (ids "<abspath>#chunk-N", chunk_index /
    total_chunks stamped, HCP context prepend included in the stored
    document). Shorter files keep the original single-record layout.

    body_filter, when given, is applied to the body immediately after
    frontmatter stripping, before BOTH the stored document and the embed
    text are built — so what gets retrieved is exactly what got embedded.
    Use it to drop non-content apparatus (source lists, boilerplate).
    If the filter consumes the ENTIRE body (apparatus-only files), the
    unfiltered body is kept instead: an empty document is unretrievable
    and injects nothing useful into a RAG package, while the raw
    apparatus (quoted claims, source citations) still carries the
    article's semantic content.

    verbose=False suppresses the per-file "+ <title>" print, for bulk
    callers that manage their own progress output.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"  SKIP (read error): {filepath} — {e}")
        stats["errors"] += 1
        return

    if len(content.strip()) < 50:
        stats["skipped"] += 1
        return

    meta, body = _parse_frontmatter(content)
    if body_filter is not None:
        filtered = body_filter(body)
        if filtered.strip():
            body = filtered
        # else: the filter emptied the body (apparatus-only file) — keep
        # the unfiltered body rather than indexing an empty document.
    if meta_overrides:
        meta = {**meta, **meta_overrides}
    doc_id = os.path.abspath(filepath)

    if force:
        # Drop any prior copy so the re-index reflects current content/meta.
        # Delete-by-path, not delete-by-id: a chunked file's records live at
        # <abspath>#chunk-N, and the file may have crossed the chunking
        # threshold since it was last indexed.
        delete_file_records(collection, filepath)
    else:
        # Already-indexed check — a chunked file has no record at the bare
        # abspath id, so probe the first chunk id too.
        try:
            existing = collection.get(ids=[doc_id, _chunk_record_id(doc_id, 1)])
            if existing and existing["ids"]:
                stats["skipped"] += 1
                return
        except Exception:
            pass

    # Long file → multi-record HCP chunked indexing (falls back to the
    # single-record path if HCP produced fewer than two chunks or errored).
    if len(body) > CHUNK_THRESHOLD_CHARS:
        if _index_chunked(collection, filepath, doc_id, meta, body, stats,
                          verbose):
            return

    chroma_meta = _compose_chroma_metadata(filepath, meta)
    embed_text = _build_embed_text(meta, body, filepath)
    doc_text = body[:MAX_INDEX_CHARS]
    embedding = _nomic_embed(embed_text)

    add_kwargs: dict[str, Any] = dict(
        ids=[doc_id],
        documents=[doc_text],
        metadatas=[chroma_meta],
    )
    if embedding is not None:
        add_kwargs["embeddings"] = [embedding]

    collection.add(**add_kwargs)
    stats["indexed"] += 1
    if verbose:
        print(f"  + {chroma_meta['title']}")


def get_knowledge_collection():
    """Create the ChromaDB client and return the embedder-bound knowledge
    collection — the same binding index_path uses. Entry point for runtime
    callers (session post-processing, engram promotion) that index or
    delete individual files without going through the CLI.
    """
    import chromadb
    # Lazy import to avoid circular dependencies at module load.
    from orchestrator.embedding import get_or_create_collection

    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    return get_or_create_collection(client, "knowledge")


def index_single_file(filepath: str, *, force: bool = False,
                      verbose: bool = True) -> dict[str, int]:
    """Index one .md file into the knowledge collection, building the
    client/collection binding in-call. Returns the stats dict so the
    caller can see the real outcome ({"indexed": 1} vs a skip or read
    error) instead of treating "no exception" as success.
    """
    stats = {"indexed": 0, "skipped": 0, "errors": 0}
    index_file(get_knowledge_collection(), filepath, stats,
               force=force, verbose=verbose)
    return stats


def index_path(path: str, reindex: bool = False) -> None:
    """Index a file or directory into the knowledge collection."""
    import chromadb
    # Lazy import to avoid circular dependencies at module load.
    from orchestrator.embedding import delete_collection, get_or_create_collection

    client = chromadb.PersistentClient(path=CHROMADB_PATH)

    if reindex:
        try:
            delete_collection(client, "knowledge")
            print("Cleared existing knowledge collection.")
        except Exception:
            pass

    # Bind the embedding_function to the collection so all add/query
    # operations route through Ollama nomic-embed-text. No silent
    # fallback to chromadb's default embedder.
    collection = get_or_create_collection(client, "knowledge")

    stats = {"indexed": 0, "skipped": 0, "errors": 0}
    path = os.path.expanduser(path)

    if os.path.isfile(path):
        print(f"Indexing file: {path}")
        index_file(collection, path, stats)
    elif os.path.isdir(path):
        md_files: list[str] = []
        for root, _dirs, files in os.walk(path):
            for f in files:
                if f.endswith(".md") and not f.startswith("."):
                    md_files.append(os.path.join(root, f))
        print(f"Indexing {len(md_files)} files from {path}")
        for fp in sorted(md_files):
            index_file(collection, fp, stats)
    else:
        print(f"Path not found: {path}")
        return

    print(f"\nDone. Indexed: {stats['indexed']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}")
    print(f"Knowledge collection total: {collection.count()} documents")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 knowledge_index.py [--reindex] <path>")
        print("  path: a .md file or directory of .md files to index")
        sys.exit(1)

    reindex = "--reindex" in sys.argv
    paths = [a for a in sys.argv[1:] if a != "--reindex"]
    for p in paths:
        index_path(p, reindex=reindex)
