"""ChromaDB knowledge search — Phase 5.3.

Per Reference — Ora YAML Schema §6.5 (rev 3, 2026-04-30) the retrieval
engine applies tag filters before any provenance or decay weighting:

    archived   → excluded entirely from default retrieval.
    incubating → included with explicit `[incubating]` flag in output.
    private    → mode-conditioned at retrieval time. When the active
                 conversation is NOT in private mode, chunks tagged
                 `private` are excluded. When it IS in private mode,
                 all chunks are visible.

`type_filter` (Phase 4 mode-file rule) restricts retrieval to chunks
whose `type` is in the supplied list. The active mode's filter lives
in its `## RAG PROFILE → ### type_filter` subsection.

Transitional dispatch:

    - knowledge collection: uses Phase 5.2 boolean extracts
      (`tag_archived`, `tag_incubating`, `tag_private`).
    - conversations collection: still uses the V3 legacy `tag` string
      field (`tag == "private"`) until Phase 5.8 migrates the writer.

`include_private=True` (or the `include:private` query modifier) is
how the caller signals "the active conversation IS in private mode" —
the private filter is suppressed and all chunks become visible.
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

CHROMADB_PATH = os.path.expanduser("~/ora/chromadb/")

_INCLUDE_PRIVATE_MODIFIER = "include:private"


# ---------------------------------------------------------------------------
# Mode file parsing
# ---------------------------------------------------------------------------


_TYPE_FILTER_LIST_RE = re.compile(r"`\[\s*([^`\]]+)\]`")


def _extract_mode_type_filter(mode_text: str) -> Optional[list[str]]:
    """Pull the `type_filter` list out of a Phase 4 mode file.

    Looks for the `### type_filter` subsection and returns the
    bracketed list of types as a Python list. Returns None when the
    section is missing, malformed, or empty.

    Phase 4 mode files express type_filter like:

        ### type_filter

        Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`
    """
    if not mode_text:
        return None

    # Match the type_filter subsection (### type_filter ... up to next heading)
    section_match = re.search(
        r"^###\s+type_filter\s*\n(.*?)(?=^##|\Z)",
        mode_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not section_match:
        return None

    body = section_match.group(1)
    list_match = _TYPE_FILTER_LIST_RE.search(body)
    if not list_match:
        return None

    raw = list_match.group(1)
    types = [t.strip() for t in raw.split(",")]
    types = [t for t in types if t]
    return types or None


# ---------------------------------------------------------------------------
# Where-clause composition
# ---------------------------------------------------------------------------


def _build_where_clause(
    collection: str,
    type_filter: Optional[list[str]],
    include_private: bool,
    include_archived: bool,
) -> Optional[dict[str, Any]]:
    """Compose a ChromaDB where-clause for the supplied filters.

    ChromaDB requires explicit `$and` for multiple field conditions —
    a flat dict with two keys is rejected. So this builder returns:
        - None when there are no filters
        - {field: ...} when there is exactly one filter
        - {"$and": [...]} when there are multiple

    Dispatches on collection name during the 5.3-to-5.8 transition:
        - knowledge:     tag_archived / tag_private booleans (Phase 5.2)
        - conversations: legacy `tag` string equality (Phase 5.8 will migrate)
    """
    clauses: list[dict[str, Any]] = []

    if type_filter:
        clauses.append({"type": {"$in": list(type_filter)}})

    if collection == "knowledge":
        if not include_archived:
            clauses.append({"tag_archived": False})
        if not include_private:
            clauses.append({"tag_private": False})
    elif collection == "conversations":
        # Legacy V3: stealth/private encoded in a single `tag` string
        # field. Archived isn't represented in the conversations
        # collection (V3 doesn't emit it). Phase 5.8 will normalize.
        if not include_private:
            clauses.append({"tag": {"$ne": "private"}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _format_result_line(rank: int, doc: str, meta: dict[str, Any]) -> list[str]:
    """Format one result entry in the assembled output string.

    Adds an `[incubating]` flag inline with the source name when the
    chunk's metadata carries `tag_incubating: True`. The flag is the
    Schema §6.5 presentation marker — it tells the consuming model
    that this content is mid-review and not yet vetted.
    """
    source = (meta or {}).get("source", "unknown") if meta else "unknown"
    incubating = bool((meta or {}).get("tag_incubating", False))
    header = f"{rank}. [{source}]"
    if incubating:
        header += " [incubating]"
    excerpt = doc[:500] + ("..." if len(doc) > 500 else "")
    return [header, f"   {excerpt}", ""]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def knowledge_search(
    query: str,
    collection: str = "knowledge",
    n_results: int = 5,
    *,
    type_filter: Optional[list[str]] = None,
    include_private: bool = False,
    include_archived: bool = False,
) -> str:
    """Query a ChromaDB collection with schema-aware tag filters.

    Args:
        query: natural-language query text. May begin with the legacy
            V3 modifier `include:private` to set include_private=True.
        collection: ChromaDB collection name (knowledge or conversations).
        n_results: maximum number of results to return.
        type_filter: list of Schema §4 type values to restrict to (e.g.
            ["engram", "resource", "incubator"]). When None, no type filter.
        include_private: when True, suppress the private-tag filter so
            the caller's active conversation can see private content.
            Schema §6.5 retrieval-time mode-conditioned semantics.
        include_archived: when True, include archived chunks. Default
            False — archived is the canonical "intentionally retired"
            signal and stays out of default retrieval.

    Returns a human-readable formatted string of search results.
    """
    # Strip and honor the V3 query modifier `include:private`.
    stripped = query.lstrip()
    if stripped.lower().startswith(_INCLUDE_PRIVATE_MODIFIER):
        include_private = True
        query = stripped[len(_INCLUDE_PRIVATE_MODIFIER):].lstrip()

    try:
        import chromadb
        from orchestrator.embedding import get_or_create_collection
        client = chromadb.PersistentClient(path=CHROMADB_PATH)
        # Bind the canonical embedding_function so query_texts embeds
        # through the same model the collection was indexed with.
        col = get_or_create_collection(client, collection)
        count = col.count()
        if count == 0:
            return f"Collection '{collection}' is empty. Add documents to enable semantic search."

        where = _build_where_clause(
            collection=collection,
            type_filter=type_filter,
            include_private=include_private,
            include_archived=include_archived,
        )

        query_kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(n_results, count),
        }
        if where is not None:
            query_kwargs["where"] = where

        results = col.query(**query_kwargs)
        output: list[str] = []
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        for i, (doc, meta) in enumerate(zip(docs, metas), 1):
            output.extend(_format_result_line(i, doc, meta))
        return "\n".join(output) if output else "No results found."
    except Exception as e:
        return f"Knowledge search error: {str(e)}"


def knowledge_search_raw(
    query: str,
    collection: str = "knowledge",
    n_results: int = 5,
    *,
    type_filter: Optional[list[str]] = None,
    include_private: bool = False,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """Like `knowledge_search` but returns raw chunk dicts instead of a
    formatted string. Used by the Phase 5.6 ranker.

    Returns a list of dicts with keys:
        id        — ChromaDB document id
        document  — the chunk's text content
        metadata  — full metadata dict (type, tags, etc.)
        distance  — ChromaDB cosine distance (lower = more similar)
        similarity — 1.0 - distance (higher = more similar)

    Empty list when the collection is empty, the query fails, or no
    chunks pass the filters.
    """
    stripped = query.lstrip()
    if stripped.lower().startswith(_INCLUDE_PRIVATE_MODIFIER):
        include_private = True
        query = stripped[len(_INCLUDE_PRIVATE_MODIFIER):].lstrip()

    try:
        import chromadb
        from orchestrator.embedding import get_or_create_collection
        client = chromadb.PersistentClient(path=CHROMADB_PATH)
        col = get_or_create_collection(client, collection)
        count = col.count()
        if count == 0:
            return []

        where = _build_where_clause(
            collection=collection,
            type_filter=type_filter,
            include_private=include_private,
            include_archived=include_archived,
        )

        query_kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(n_results, count),
        }
        if where is not None:
            query_kwargs["where"] = where

        results = col.query(**query_kwargs)
        ids = (results.get("ids") or [[]])[0]
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        dists = (results.get("distances") or [[]])[0]

        chunks = []
        for i, (cid, doc, meta, dist) in enumerate(zip(ids, docs, metas, dists)):
            chunks.append({
                "id":         cid,
                "document":   doc,
                "metadata":   meta or {},
                "distance":   float(dist) if dist is not None else 1.0,
                "similarity": 1.0 - float(dist) if dist is not None else 0.0,
            })
        return chunks
    except Exception:
        return []


__all__ = [
    "knowledge_search",
    "knowledge_search_raw",
    "_extract_mode_type_filter",
    "_build_where_clause",
    "_format_result_line",
]
