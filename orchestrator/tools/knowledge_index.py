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
        path           — absolute file path (also serves as ChromaDB id)
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
        chunk_index            — int
        total_chunks           — int
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
from typing import Any

import yaml

CHROMADB_PATH = os.path.expanduser("~/ora/chromadb/")


# Tag values that need fast where-filterable boolean extracts.
# Schema §6.5 — these three tags drive the RAG retrieval filters.
_FILTERABLE_TAGS = ("archived", "incubating", "private")

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
        return list(result[0]) if result else None
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
    leading body. Schema §9 retired `domain` — no longer included.
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
    parts.append(body[:1000])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


def index_file(collection, filepath: str, stats: dict[str, int]) -> None:
    """Index a single .md file into the knowledge collection."""
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
    doc_id = os.path.abspath(filepath)

    # Already-indexed check
    try:
        existing = collection.get(ids=[doc_id])
        if existing and existing["ids"]:
            stats["skipped"] += 1
            return
    except Exception:
        pass

    chroma_meta = _compose_chroma_metadata(filepath, meta)
    embed_text = _build_embed_text(meta, body, filepath)
    doc_text = body[:8000]
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
    print(f"  + {chroma_meta['title']}")


def index_path(path: str, reindex: bool = False) -> None:
    """Index a file or directory into the knowledge collection."""
    import chromadb
    # Lazy import to avoid circular dependencies at module load.
    from orchestrator.embedding import get_or_create_collection

    client = chromadb.PersistentClient(path=CHROMADB_PATH)

    if reindex:
        try:
            client.delete_collection("knowledge")
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
