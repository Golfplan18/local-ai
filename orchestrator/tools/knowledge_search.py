"""ChromaDB knowledge search — Phase 5.3.

Per Reference — Ora YAML Schema §6.5 (rev 3, 2026-04-30) the retrieval
engine applies tag filters before any provenance or decay weighting:

    archived   → excluded entirely from default retrieval.
    incubating → included with explicit `[incubating]` flag in output.
    private    → visible to Private and Stealth callers only.
    stealth    → visible to Stealth callers only.

`type_filter` (Phase 4 mode-file rule) restricts retrieval to chunks
whose `type` is in the supplied list. The active mode's filter lives
in its `## RAG PROFILE → ### type_filter` subsection.

Transitional dispatch:

    - knowledge collection: uses Phase 5.2 boolean extracts
      (`tag_archived`, `tag_incubating`, `tag_private`, `tag_stealth`).
    - conversations collection: uses the conversation `tag` string field.

`include_private=True` (or the legacy `include:private` query modifier) maps
to Private visibility; it never grants access to Stealth chunks. New callers
should pass the explicit `privacy_tag` lattice value.
"""

from __future__ import annotations

import os
import re
import sqlite3
from difflib import SequenceMatcher
from typing import Any, Optional

try:
    from orchestrator.conversation_memory import (
        knowledge_admitted_paths,
        knowledge_metadata_allows,
    )
except ImportError:  # pragma: no cover - direct orchestrator import context
    from conversation_memory import (
        knowledge_admitted_paths,
        knowledge_metadata_allows,
    )

def _chromadb_default() -> str:
    """Resolve the vector store through runtime_paths, never a hardcoded path.

    A literal os.path.expanduser("~/ora/chromadb") ignores ORA_CHROMADB_PATH,
    so it bypassed the test quarantine in orchestrator/tests/live_guard.py and
    read the user's real 7 GB store during unit tests — which is how
    test_rag_isolation_bypass came to run a lexical scan over the live corpus
    and hang the suite. runtime_paths is also what makes these modules portable
    off macOS.
    """
    from orchestrator import runtime_paths as _rp
    return str(_rp.chromadb_dir())


CHROMADB_PATH = _chromadb_default()
_INCLUDE_PRIVATE_MODIFIER = "include:private"
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")
_METADATA_CACHE: dict[str, dict[str, Any]] = {}
_SQLITE_METADATA_SEGMENT = "urn:chroma:segment/metadata/sqlite"
_LEXICAL_SQL_CANDIDATES = int(os.environ.get("ORA_RAG_LEXICAL_SQL_CANDIDATES", "400"))
_LEXICAL_SQL_BODY_CANDIDATES = int(os.environ.get("ORA_RAG_LEXICAL_SQL_BODY_CANDIDATES", "400"))
_LEXICAL_METADATA_KEYS = (
    "title",
    "source",
    "path",
    "obsidian_path",
    "conversation_title",
    "conversation_id",
    "session_id",
    "source_file",
    "source_document",
    "source_path",
    "raw_path",
    "chunk_path",
    "vault_path",
    "source_chat",
)

_STOPWORDS = {
    "about", "after", "again", "against", "also", "among", "because",
    "before", "being", "between", "could", "does", "from", "have",
    "into", "like", "more", "over", "should", "that", "their", "there",
    "these", "thing", "this", "those", "through", "what", "when", "where",
    "which", "while", "with", "would", "your",
}


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


def _extract_mode_exclude_tags(mode_text: str) -> Optional[list[str]]:
    """Pull the `exclude_tags` list out of a mode file's RAG PROFILE.

    Mirrors `_extract_mode_type_filter`. Looks for an `### exclude_tags`
    subsection and returns the bracketed list of tag names to filter OUT
    of retrieval. Returns None when the section is missing, malformed, or
    empty — in which case nothing is excluded (the default: a tag like
    `msi-news` rides along with the rest of the `knowledge` collection).

    Mode files express exclude_tags like:

        ### exclude_tags

        Exclude chunks tagged: `[msi-news]`
    """
    if not mode_text:
        return None

    section_match = re.search(
        r"^###\s+exclude_tags\s*\n(.*?)(?=^##|\Z)",
        mode_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not section_match:
        return None

    list_match = _TYPE_FILTER_LIST_RE.search(section_match.group(1))
    if not list_match:
        return None

    tags = [t.strip() for t in list_match.group(1).split(",")]
    tags = [t for t in tags if t]
    return tags or None


# ---------------------------------------------------------------------------
# Where-clause composition
# ---------------------------------------------------------------------------


def _build_where_clause(
    collection: str,
    type_filter: Optional[list[str]],
    include_private: bool,
    include_archived: bool,
    exclude_tags: Optional[list[str]] = None,
    privacy_tag: Optional[str] = None,
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

    if privacy_tag is not None and privacy_tag not in ("", "private", "stealth"):
        raise ValueError("privacy_tag is invalid")
    privacy = privacy_tag if privacy_tag is not None else (
        "private" if include_private else ""
    )

    if collection == "knowledge":
        if not include_archived:
            clauses.append({"tag_archived": {"$ne": True}})
        if privacy == "":
            clauses.append({"tag_private": {"$ne": True}})
            clauses.append({"tag_stealth": {"$ne": True}})
        elif privacy == "private":
            clauses.append({"tag_stealth": {"$ne": True}})
        # Mode-conditioned tag exclusions (e.g. `msi-news`). Uses
        # `$ne True` rather than `== False` so that documents indexed
        # before the tag was added to knowledge_index._FILTERABLE_TAGS
        # (field absent) are treated as not carrying the tag and stay
        # retrievable. Verified against ChromaDB 1.5.5 missing-key
        # semantics: `{$ne: True}` matches both `False` and absent.
        for _tag in (exclude_tags or []):
            clauses.append({f"tag_{_tag}": {"$ne": True}})
    elif collection == "conversations":
        # Each complete exchange carries an exact authority. Equality/inclusion
        # filters intentionally exclude legacy missing/invalid rows before
        # Chroma computes semantic candidates.
        if privacy == "":
            clauses.append({"turn_privacy": {"$eq": "standard"}})
        elif privacy == "private":
            clauses.append({
                "turn_privacy": {"$in": ["standard", "private"]},
            })
        else:
            clauses.append({
                "turn_privacy": {
                    "$in": ["standard", "private", "stealth"],
                },
            })

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


# ---------------------------------------------------------------------------
# Hybrid lexical helpers
# ---------------------------------------------------------------------------


def _normalise_for_match(text: str) -> str:
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for raw in _WORD_RE.findall(query or ""):
        for term in _normalise_for_match(raw).split():
            if len(term) < 3 or term in _STOPWORDS or term in seen:
                continue
            seen.add(term)
            terms.append(term)
    return terms


def _document_needles(query: str, terms: list[str]) -> list[str]:
    """Bounded body-search needles for Chroma's where_document filter.

    Title/source rescue is handled by metadata scanning below. Body search
    stays narrow so a normal RAG turn does not become a full document scan.
    """
    needles: list[str] = []
    stripped = " ".join(str(query or "").split())
    if 4 <= len(stripped) <= 120:
        needles.append(stripped)
    # Prefer distinctive terms; Chroma's contains filter is literal, so these
    # catch exact-body mentions without assuming phrase order.
    distinctive = sorted(
        (t for t in terms if len(t) >= 5),
        key=lambda t: (-len(t), t),
    )
    needles.extend(distinctive[:8])

    out: list[str] = []
    seen: set[str] = set()
    for needle in needles:
        n = needle.strip()
        if not n or n.lower() in seen:
            continue
        seen.add(n.lower())
        out.append(n)
    return out


def _field_tokens(text: str) -> list[str]:
    return _query_terms(text)


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _metadata_text(meta: dict[str, Any]) -> str:
    fields = [
        meta.get("title"),
        meta.get("source"),
        meta.get("path"),
        meta.get("obsidian_path"),
        meta.get("conversation_title"),
        meta.get("conversation_id"),
        meta.get("session_id"),
        meta.get("source_file"),
        meta.get("source_document"),
    ]
    return " ".join(str(v or "") for v in fields)


def _conversation_safe_payload(
    document: str,
    metadata: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    """Strip Dialogue-wide text before Standard row scoring or return."""
    text = str(document or "")
    user_match = re.search(
        r"\*\*User:\*\*\s*(.*?)(?=\n\*\*Assistant:\*\*|\Z)",
        text,
        flags=re.DOTALL,
    )
    assistant_match = re.search(
        r"\*\*Assistant:\*\*\s*(.*)", text, flags=re.DOTALL,
    )
    if user_match is None:
        return None
    user = user_match.group(1).strip()
    if not user:
        return None
    assistant = assistant_match.group(1).strip() if assistant_match else ""
    safe_document = (
        f"**User:**\n\n{user}\n\n**Assistant:**\n\n{assistant}"
    )
    title = " ".join(user.split())
    title = title if len(title) <= 80 else title[:79].rstrip() + "…"
    safe_metadata = dict(metadata or {})
    for key in (
        "title", "description", "raw_path", "source_file",
        "source_document", "source_path",
    ):
        safe_metadata.pop(key, None)
    safe_metadata["conversation_title"] = title
    return safe_document, safe_metadata


def _conversation_allowed_turn_privacies(
    *,
    include_private: bool,
    privacy_tag: Optional[str],
) -> tuple[str, ...]:
    if privacy_tag is not None and privacy_tag not in ("", "private", "stealth"):
        return ()
    privacy = privacy_tag if privacy_tag is not None else (
        "private" if include_private else ""
    )
    if privacy == "":
        return ("standard",)
    if privacy == "private":
        return ("standard", "private")
    return ("standard", "private", "stealth")


def _knowledge_target_tag(
    *,
    include_private: bool,
    privacy_tag: Optional[str],
) -> str | None:
    if privacy_tag is not None:
        return privacy_tag if privacy_tag in ("", "private", "stealth") else None
    return "private" if include_private else ""


def _knowledge_admitted_path_inventory(
    collection_obj: Any,
    *,
    include_private: bool,
    privacy_tag: Optional[str],
) -> list[str]:
    """Inventory every knowledge row and authenticate owner paths.

    The inventory deliberately has no metadata ``where`` filter: malformed
    owner claims cannot be described safely by a filter over expected values.
    Only the returned paths may be named by a later vector or lexical query.
    """
    target_tag = _knowledge_target_tag(
        include_private=include_private,
        privacy_tag=privacy_tag,
    )
    if target_tag is None:
        return []
    result = collection_obj.get(include=["metadatas"])
    metadatas = result.get("metadatas") if isinstance(result, dict) else None
    if not isinstance(metadatas, list):
        raise RuntimeError("knowledge authority inventory is unavailable")
    return knowledge_admitted_paths(metadatas, target_tag)


def _where_with_admitted_paths(
    where: Optional[dict[str, Any]],
    admitted_paths: list[str],
) -> dict[str, Any]:
    path_scope: dict[str, Any] = {"path": {"$in": admitted_paths}}
    if where is None:
        return path_scope
    clauses = where.get("$and") if set(where) == {"$and"} else None
    if isinstance(clauses, list):
        return {"$and": [*clauses, path_scope]}
    return {"$and": [where, path_scope]}


def _lexical_score(query: str, text: str, *, metadata_match: bool = False) -> float:
    """Score exact and near-miss lexical matches on a 0-1 similarity scale.

    This is not a final rank. It gives exact title/source/body hits enough
    synthetic similarity to enter the normal floor → fit-gate → provenance →
    rerank funnel, where bad matches can still be removed.
    """
    qnorm = _normalise_for_match(query)
    hay = _normalise_for_match(text)
    if not qnorm or not hay:
        return 0.0
    if qnorm in hay:
        return 0.95 if metadata_match else 0.85

    terms = _query_terms(query)
    if not terms:
        return 0.0
    hay_tokens = set(_field_tokens(hay))
    exact = sum(1 for t in terms if t in hay_tokens or t in hay)

    fuzzy = 0
    field_tokens = list(hay_tokens)
    for term in terms:
        if term in hay_tokens or term in hay:
            continue
        if any(_ratio(term, token) >= 0.86 for token in field_tokens):
            fuzzy += 1

    coverage = (exact + fuzzy) / max(1, len(terms))
    if exact == 0 and fuzzy == 0:
        return 0.0
    base = 0.50 if metadata_match else 0.42
    score = base + (0.35 * coverage)
    if fuzzy and metadata_match:
        score += 0.08
    return min(score, 0.90 if metadata_match else 0.78)


def _metadata_passes_filters(
    meta: dict[str, Any],
    *,
    collection: str,
    type_filter: Optional[list[str]],
    include_private: bool,
    include_archived: bool,
    exclude_tags: Optional[list[str]] = None,
    privacy_tag: Optional[str] = None,
) -> bool:
    raw_tags = meta.get("tags")
    if isinstance(raw_tags, (list, tuple, set)):
        tags = {
            str(value).strip().casefold() for value in raw_tags
            if str(value).strip()
        }
    elif isinstance(raw_tags, str):
        # Legacy Chroma rows may carry the canonical list as JSON or as a
        # comma-delimited scalar.  Controlled tag values are word-like, so
        # tokenising preserves hyphenated tags without trusting one encoding.
        tags = set(re.findall(r"[a-z0-9][a-z0-9_-]*", raw_tags.casefold()))
    else:
        tags = set()
    stored_tag = str(meta.get("tag") or "").strip().casefold()
    if stored_tag:
        tags.add(stored_tag)
    if privacy_tag is not None and privacy_tag not in ("", "private", "stealth"):
        return False
    privacy = privacy_tag if privacy_tag is not None else (
        "private" if include_private else ""
    )
    if type_filter and meta.get("type") not in set(type_filter):
        return False
    if collection == "knowledge":
        target_tag = _knowledge_target_tag(
            include_private=include_private,
            privacy_tag=privacy_tag,
        )
        if target_tag is None or not knowledge_metadata_allows(meta, target_tag):
            return False
        if not include_archived and (
            bool(meta.get("tag_archived", False)) or "archived" in tags
        ):
            return False
        if privacy == "" and (
            bool(meta.get("tag_private", False)) or "private" in tags
        ):
            return False
        if privacy != "stealth" and (
            bool(meta.get("tag_stealth", False)) or "stealth" in tags
        ):
            return False
        for tag in exclude_tags or []:
            if bool(meta.get(f"tag_{tag}", False)) or tag.casefold() in tags:
                return False
    elif collection == "conversations":
        archived = bool(meta.get("tag_archived", False)) or "archived" in tags
        if not include_archived and archived:
            return False
        exact = meta.get("turn_privacy")
        allowed = (
            {"standard"} if privacy == ""
            else {"standard", "private"} if privacy == "private"
            else {"standard", "private", "stealth"}
        )
        if exact not in allowed:
            return False
    return True


def _fetch_chunks_by_id(
    collection_obj: Any,
    ids: list[str],
    scores: dict[str, float],
    *,
    sanitize_conversations: bool = False,
    metadata_filter=None,
) -> list[dict[str, Any]]:
    if not ids:
        return []
    try:
        result = collection_obj.get(
            ids=ids,
            include=["documents", "metadatas"],
        )
    except Exception:
        return []
    returned_ids = [str(i) for i in (result.get("ids") or [])]
    docs = result.get("documents") or []
    metas = result.get("metadatas") or []
    by_id = {
        cid: (doc or "", meta or {})
        for cid, doc, meta in zip(returned_ids, docs, metas)
    }
    chunks: list[dict[str, Any]] = []
    for cid in ids:
        if cid not in by_id:
            continue
        doc, meta = by_id[cid]
        if metadata_filter is not None and not metadata_filter(meta):
            continue
        if sanitize_conversations:
            safe_payload = _conversation_safe_payload(doc, meta)
            if safe_payload is None:
                continue
            doc, meta = safe_payload
        score = float(scores.get(cid, 0.0))
        chunks.append({
            "id": cid,
            "document": doc,
            "metadata": meta,
            "distance": max(0.0, 1.0 - score),
            "similarity": score,
            "lexical_score": score,
            "retrieval_source": "lexical",
        })
    return chunks


def _sqlite_path() -> str:
    return os.path.join(os.path.expanduser(CHROMADB_PATH), "chroma.sqlite3")


def _collection_metadata_segment(cur: sqlite3.Cursor, collection_name: str) -> str | None:
    row = cur.execute(
        """
        SELECT s.id
        FROM collections c
        JOIN segments s ON s.collection = c.id
        WHERE c.name = ?
          AND s.type = ?
        LIMIT 1
        """,
        (collection_name, _SQLITE_METADATA_SEGMENT),
    ).fetchone()
    return str(row[0]) if row else None


def _dedupe_ids(ids: list[str], limit: Optional[int] = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in ids:
        cid = str(raw or "")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
        if limit is not None and len(out) >= limit:
            break
    return out


def _fts_match_query(terms: list[str]) -> str:
    clean: list[str] = []
    for term in terms:
        for part in re.findall(r"[a-z0-9]+", term.lower()):
            if len(part) >= 3 and part not in _STOPWORDS:
                clean.append(f'"{part}"')
    return " OR ".join(_dedupe_ids(clean))


def _metadata_like_patterns(query: str, terms: list[str]) -> list[str]:
    parts = [p for p in _normalise_for_match(query).split() if len(p) >= 3]
    parts.extend(terms)
    ordered: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part in _STOPWORDS or part in seen:
            continue
        seen.add(part)
        ordered.append(part)
    ordered.sort(key=lambda t: (-len(t), t))
    return [f"%{part}%" for part in ordered]


def _sqlite_candidate_ids(
    collection_name: str,
    query: str,
    terms: list[str],
    *,
    limit: Optional[int],
    allowed_turn_privacies: tuple[str, ...] | None = None,
    allowed_knowledge_paths: tuple[str, ...] | None = None,
) -> list[str]:
    """Use Chroma's SQLite metadata and FTS tables for lexical recall.

    This intentionally avoids Chroma's collection-wide `where_document`
    contains scan. The output is only a candidate set; the normal filters,
    floor, fit gate, provenance ranking, and reranker still decide whether
    any candidate is allowed into context. ``limit=None`` is genuinely
    uncapped: no per-term SQL ceiling may starve an assistant-only match.
    """
    db_path = _sqlite_path()
    if not os.path.exists(db_path) or (limit is not None and limit <= 0):
        return []
    if allowed_turn_privacies == ():
        return []
    if allowed_knowledge_paths == ():
        return []

    privacy_join = ""
    privacy_clause = ""
    privacy_params: list[str] = []
    if allowed_turn_privacies is not None:
        placeholders = ",".join("?" for _ in allowed_turn_privacies)
        privacy_join = (
            "JOIN embedding_metadata turn_authority "
            "ON turn_authority.id = e.id "
            "AND turn_authority.key = 'turn_privacy'"
        )
        privacy_clause = (
            f"AND turn_authority.string_value IN ({placeholders})"
        )
        privacy_params = list(allowed_turn_privacies)

    knowledge_join = ""
    if allowed_knowledge_paths is not None:
        knowledge_join = (
            "JOIN embedding_metadata knowledge_path "
            "ON knowledge_path.id = e.id "
            "AND knowledge_path.key = 'path' "
            "JOIN ora_admitted_knowledge_paths admitted_path "
            "ON admitted_path.path = knowledge_path.string_value"
        )

    ids: list[str] = []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return []
    try:
        cur = conn.cursor()
        segment_id = _collection_metadata_segment(cur, collection_name)
        if not segment_id:
            return []
        if allowed_knowledge_paths is not None:
            cur.execute(
                "CREATE TEMP TABLE ora_admitted_knowledge_paths "
                "(path TEXT PRIMARY KEY)",
            )
            cur.executemany(
                "INSERT OR IGNORE INTO ora_admitted_knowledge_paths(path) "
                "VALUES (?)",
                ((path,) for path in allowed_knowledge_paths),
            )

        patterns = _metadata_like_patterns(query, terms)
        if patterns:
            metadata_keys = (
                tuple(
                    key for key in _LEXICAL_METADATA_KEYS
                    if key not in {
                        "title", "conversation_title", "raw_path",
                        "source_file", "source_document", "source_path",
                    }
                )
                if allowed_turn_privacies is not None
                else _LEXICAL_METADATA_KEYS
            )
            key_placeholders = ",".join("?" for _ in metadata_keys)
            per_term_limit = (
                None if limit is None else max(
                    12,
                    min(80, max(
                        1, _LEXICAL_SQL_CANDIDATES // max(1, len(patterns)),
                    )),
                )
            )
            for pattern in patterns:
                sql = f"""
                    SELECT DISTINCT e.embedding_id
                    FROM embeddings e
                    JOIN embedding_metadata m ON m.id = e.id
                    {privacy_join}
                    {knowledge_join}
                    WHERE e.segment_id = ?
                      AND m.key IN ({key_placeholders})
                      AND m.string_value IS NOT NULL
                      AND lower(m.string_value) LIKE ?
                      {privacy_clause}
                """
                params: list[Any] = [
                    segment_id, *metadata_keys, pattern,
                    *privacy_params,
                ]
                if per_term_limit is not None:
                    sql += " LIMIT ?"
                    params.append(per_term_limit)
                rows = cur.execute(sql, params).fetchall()
                ids.extend(str(row[0]) for row in rows)

        fts_terms = [term.strip('"') for term in _fts_match_query(terms).split(" OR ") if term]
        if fts_terms:
            per_term_limit = (
                None if limit is None else max(
                    12,
                    min(80, max(
                        1, _LEXICAL_SQL_BODY_CANDIDATES // max(1, len(fts_terms)),
                    )),
                )
            )
            for term in fts_terms:
                if limit is not None and len(ids) >= limit * 3:
                    break
                sql = f"""
                    SELECT e.embedding_id
                    FROM embedding_fulltext_search
                    JOIN embeddings e ON e.id = embedding_fulltext_search.rowid
                    {privacy_join}
                    {knowledge_join}
                    WHERE e.segment_id = ?
                      AND embedding_fulltext_search MATCH ?
                      {privacy_clause}
                """
                params = [
                    segment_id, f'"{term}"', *privacy_params,
                ]
                if per_term_limit is not None:
                    sql += " LIMIT ?"
                    params.append(per_term_limit)
                rows = cur.execute(sql, params).fetchall()
                ids.extend(str(row[0]) for row in rows)
    except sqlite3.Error:
        if allowed_knowledge_paths is not None:
            return []
        return _dedupe_ids(ids, limit)
    finally:
        conn.close()
    return _dedupe_ids(ids, limit)


def _payloads_by_id(collection_obj: Any, ids: list[str]) -> dict[str, tuple[str, dict[str, Any]]]:
    if not ids:
        return {}
    try:
        result = collection_obj.get(ids=ids, include=["documents", "metadatas"])
    except Exception:
        return {}
    returned_ids = [str(i) for i in (result.get("ids") or [])]
    docs = result.get("documents") or []
    metas = result.get("metadatas") or []
    return {
        cid: (doc or "", meta or {})
        for cid, doc, meta in zip(returned_ids, docs, metas)
    }


def lexical_search_raw(
    query: str,
    collection: str = "knowledge",
    n_results: Optional[int] = 10,
    *,
    type_filter: Optional[list[str]] = None,
    include_private: bool = False,
    include_archived: bool = False,
    exclude_tags: Optional[list[str]] = None,
    privacy_tag: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return exact/title/source/body lexical rescue candidates.

    This complements vector retrieval. It is deliberately bounded and
    fail-soft: metadata/title/source matching and body matching use Chroma's
    SQLite metadata/full-text indexes, then hand the small candidate set back
    to the normal ranking pipeline.
    """
    if not query or (n_results is not None and n_results <= 0):
        return []

    try:
        import chromadb
        from orchestrator.embedding import get_or_create_collection
        client = chromadb.PersistentClient(path=CHROMADB_PATH)
        col = get_or_create_collection(client, collection)
        count = col.count()
        if count == 0:
            return []
        effective_n = count if n_results is None else min(n_results, count)

        scores: dict[str, float] = {}
        terms = _query_terms(query)
        admitted_paths: list[str] | None = None
        admitted_path_set: set[str] | None = None
        if collection == "knowledge":
            admitted_paths = _knowledge_admitted_path_inventory(
                col,
                include_private=include_private,
                privacy_tag=privacy_tag,
            )
            if not admitted_paths:
                return []
            admitted_path_set = set(admitted_paths)
        allowed_turn_privacies = (
            _conversation_allowed_turn_privacies(
                include_private=include_private,
                privacy_tag=privacy_tag,
            )
            if collection == "conversations" else None
        )
        candidate_ids = _sqlite_candidate_ids(
            getattr(col, "name", None) or collection,
            query,
            terms,
            limit=(None if n_results is None else max(
                effective_n * 12, min(_LEXICAL_SQL_CANDIDATES, 120)
            )),
            allowed_turn_privacies=allowed_turn_privacies,
            allowed_knowledge_paths=(
                tuple(admitted_paths) if admitted_paths is not None else None
            ),
        )
        payloads = _payloads_by_id(col, candidate_ids)

        for cid in candidate_ids:
            doc, meta = payloads.get(cid, ("", {}))
            if (
                admitted_path_set is not None
                and str(meta.get("path") or "").strip()
                not in admitted_path_set
            ):
                continue
            if not _metadata_passes_filters(
                meta,
                collection=collection,
                type_filter=type_filter,
                include_private=include_private,
                include_archived=include_archived,
                exclude_tags=exclude_tags,
                privacy_tag=privacy_tag,
            ):
                continue
            if collection == "conversations":
                safe_payload = _conversation_safe_payload(doc, meta)
                if safe_payload is None:
                    continue
                doc, meta = safe_payload
            metadata_score = _lexical_score(
                query, _metadata_text(meta), metadata_match=True,
            )
            body_score = _lexical_score(query, doc or "", metadata_match=False)
            score = max(metadata_score, body_score)
            if score:
                scores[cid] = score

        if not scores:
            return []
        ordered = sorted(scores, key=lambda cid: scores[cid], reverse=True)
        if n_results is not None:
            ordered = ordered[:effective_n]

        def metadata_filter(meta: dict[str, Any]) -> bool:
            if (
                admitted_path_set is not None
                and str(meta.get("path") or "").strip()
                not in admitted_path_set
            ):
                return False
            return _metadata_passes_filters(
                meta,
                collection=collection,
                type_filter=type_filter,
                include_private=include_private,
                include_archived=include_archived,
                exclude_tags=exclude_tags,
                privacy_tag=privacy_tag,
            )

        return _fetch_chunks_by_id(
            col,
            ordered,
            scores,
            sanitize_conversations=collection == "conversations",
            metadata_filter=metadata_filter,
        )
    except Exception as exc:
        import sys
        print(
            f"[lexical_search_raw] retrieval failed for collection "
            f"{collection!r} (query {query[:80]!r}): "
            f"{type(exc).__name__}: {exc}. Returning empty result.",
            file=sys.stderr, flush=True,
        )
        return []


def _merge_raw_chunks(
    semantic_chunks: list[dict[str, Any]],
    lexical_chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def _add(chunk: dict[str, Any], source: str) -> None:
        cid = str(chunk.get("id") or "")
        if not cid:
            cid = f"doc:{_normalise_for_match(chunk.get('document') or '')[:160]}"
        incoming = dict(chunk)
        incoming["retrieval_source"] = source
        if source == "semantic":
            incoming["semantic_similarity"] = float(incoming.get("similarity", 0.0))
        if cid not in merged:
            merged[cid] = incoming
            order.append(cid)
            return
        existing = merged[cid]
        existing_source = str(existing.get("retrieval_source") or "")
        sources = set(existing_source.split("+")) if existing_source else set()
        sources.add(source)
        existing["retrieval_source"] = "+".join(sorted(s for s in sources if s))
        if "lexical_score" in incoming:
            existing["lexical_score"] = max(
                float(existing.get("lexical_score", 0.0) or 0.0),
                float(incoming.get("lexical_score", 0.0) or 0.0),
            )
        if "semantic_similarity" in incoming:
            existing["semantic_similarity"] = max(
                float(existing.get("semantic_similarity", 0.0) or 0.0),
                float(incoming.get("semantic_similarity", 0.0) or 0.0),
            )
        if float(incoming.get("similarity", 0.0)) > float(existing.get("similarity", 0.0)):
            for key in ("similarity", "distance", "document", "metadata"):
                existing[key] = incoming.get(key)

    for chunk in semantic_chunks:
        _add(chunk, "semantic")
    for chunk in lexical_chunks:
        _add(chunk, "lexical")
    return [merged[cid] for cid in order]


def knowledge_search_hybrid_raw(
    query: str,
    collection: str = "knowledge",
    n_results: Optional[int] = 5,
    *,
    type_filter: Optional[list[str]] = None,
    include_private: bool = False,
    include_archived: bool = False,
    exclude_tags: Optional[list[str]] = None,
    lexical_n_results: Optional[int] = None,
    privacy_tag: Optional[str] = None,
    excluded_conversation_ids: Optional[list[str] | set[str]] = None,
    excluded_paths: Optional[list[str] | set[str]] = None,
) -> list[dict[str, Any]]:
    semantic = knowledge_search_raw(
        query=query,
        collection=collection,
        n_results=n_results,
        type_filter=type_filter,
        include_private=include_private,
        include_archived=include_archived,
        exclude_tags=exclude_tags,
        privacy_tag=privacy_tag,
        excluded_conversation_ids=excluded_conversation_ids,
        excluded_paths=excluded_paths,
    )
    if os.environ.get("ORA_RAG_HYBRID_RETRIEVAL", "1").strip().lower() in {"0", "false", "no", "off"}:
        for chunk in semantic:
            chunk.setdefault("retrieval_source", "semantic")
            chunk.setdefault("semantic_similarity", float(chunk.get("similarity", 0.0)))
        return semantic
    if lexical_n_results is None and n_results is not None:
        try:
            lexical_n_results = int(os.environ.get("ORA_RAG_LEXICAL_N", str(n_results)))
        except ValueError:
            lexical_n_results = n_results
    lexical = lexical_search_raw(
        query=query,
        collection=collection,
        n_results=(
            None if n_results is None and lexical_n_results is None
            else max(0, int(lexical_n_results or 0))
        ),
        type_filter=type_filter,
        include_private=include_private,
        include_archived=include_archived,
        exclude_tags=exclude_tags,
        privacy_tag=privacy_tag,
    )
    return _filter_excluded_chunks(
        _merge_raw_chunks(semantic, lexical),
        excluded_conversation_ids=excluded_conversation_ids,
        excluded_paths=excluded_paths,
    )


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _filter_excluded_chunks(
    chunks: list[dict[str, Any]],
    *,
    excluded_conversation_ids: Optional[list[str] | set[str]] = None,
    excluded_paths: Optional[list[str] | set[str]] = None,
) -> list[dict[str, Any]]:
    """Remove complete records owned by explicitly inventoried sources."""
    excluded_conversations = {
        str(value).strip().casefold()
        for value in (excluded_conversation_ids or [])
        if str(value).strip()
    }
    canonical_paths: set[str] = set()
    for value in excluded_paths or []:
        try:
            canonical_paths.add(
                os.path.realpath(os.path.abspath(str(value))).casefold()
            )
        except (OSError, ValueError):
            continue
    if not excluded_conversations and not canonical_paths:
        return chunks

    filtered: list[dict[str, Any]] = []
    for chunk in chunks:
        metadata = (
            chunk.get("metadata")
            if isinstance(chunk.get("metadata"), dict) else {}
        )
        conversation_id = str(
            metadata.get("conversation_id") or ""
        ).strip().casefold()
        source_path = metadata.get("path")
        try:
            canonical_path = (
                os.path.realpath(os.path.abspath(str(source_path))).casefold()
                if source_path else ""
            )
        except (OSError, ValueError):
            canonical_path = ""
        if (conversation_id in excluded_conversations
                or (canonical_path and canonical_path in canonical_paths)):
            continue
        filtered.append(chunk)
    return filtered


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
    n_results: Optional[int] = 5,
    *,
    type_filter: Optional[list[str]] = None,
    include_private: bool = False,
    include_archived: bool = False,
    exclude_tags: Optional[list[str]] = None,
    privacy_tag: Optional[str] = None,
    excluded_conversation_ids: Optional[list[str] | set[str]] = None,
    excluded_paths: Optional[list[str] | set[str]] = None,
) -> str:
    """Query a ChromaDB collection with schema-aware tag filters.

    Args:
        query: natural-language query text. May begin with the legacy
            V3 modifier `include:private` to set include_private=True.
        collection: ChromaDB collection name (knowledge or conversations).
        n_results: maximum number of results to return.
        type_filter: list of Schema §4 type values to restrict to (e.g.
            ["engram", "resource", "incubator"]). When None, no type filter.
        include_private: legacy signal for Private visibility. Stealth remains
            excluded; explicit callers should pass ``privacy_tag``.
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

        admitted_paths: list[str] | None = None
        admitted_path_set: set[str] | None = None
        if collection == "knowledge":
            admitted_paths = _knowledge_admitted_path_inventory(
                col,
                include_private=include_private,
                privacy_tag=privacy_tag,
            )
            if not admitted_paths:
                return "No results found."
            admitted_path_set = set(admitted_paths)

        where = _build_where_clause(
            collection=collection,
            type_filter=type_filter,
            include_private=include_private,
            include_archived=include_archived,
            exclude_tags=exclude_tags,
            privacy_tag=privacy_tag,
        )
        if admitted_paths is not None:
            where = _where_with_admitted_paths(where, admitted_paths)

        query_kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": count if n_results is None else min(n_results, count),
        }
        if where is not None:
            query_kwargs["where"] = where

        results = col.query(**query_kwargs)
        output: list[str] = []
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        safe_chunks: list[dict[str, Any]] = []
        for doc, meta in zip(docs, metas):
            meta = meta or {}
            if (
                admitted_path_set is not None
                and str(meta.get("path") or "").strip()
                not in admitted_path_set
            ):
                continue
            if not _metadata_passes_filters(
                meta, collection=collection,
                type_filter=type_filter,
                include_private=include_private,
                include_archived=include_archived,
                exclude_tags=exclude_tags,
                privacy_tag=privacy_tag,
            ):
                continue
            if collection == "conversations":
                safe_payload = _conversation_safe_payload(doc, meta)
                if safe_payload is None:
                    continue
                doc, meta = safe_payload
            safe_chunks.append({"document": doc, "metadata": meta})
        filtered = _filter_excluded_chunks(
            safe_chunks,
            excluded_conversation_ids=excluded_conversation_ids,
            excluded_paths=excluded_paths,
        )
        for i, chunk in enumerate(filtered, 1):
            output.extend(_format_result_line(
                i, chunk["document"], chunk["metadata"],
            ))
        return "\n".join(output) if output else "No results found."
    except Exception as e:
        return f"Knowledge search error: {str(e)}"


def knowledge_search_raw(
    query: str,
    collection: str = "knowledge",
    n_results: Optional[int] = 5,
    *,
    type_filter: Optional[list[str]] = None,
    include_private: bool = False,
    include_archived: bool = False,
    exclude_tags: Optional[list[str]] = None,
    privacy_tag: Optional[str] = None,
    excluded_conversation_ids: Optional[list[str] | set[str]] = None,
    excluded_paths: Optional[list[str] | set[str]] = None,
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

        admitted_paths: list[str] | None = None
        admitted_path_set: set[str] | None = None
        if collection == "knowledge":
            admitted_paths = _knowledge_admitted_path_inventory(
                col,
                include_private=include_private,
                privacy_tag=privacy_tag,
            )
            if not admitted_paths:
                return []
            admitted_path_set = set(admitted_paths)

        where = _build_where_clause(
            collection=collection,
            type_filter=type_filter,
            include_private=include_private,
            include_archived=include_archived,
            exclude_tags=exclude_tags,
            privacy_tag=privacy_tag,
        )
        if admitted_paths is not None:
            where = _where_with_admitted_paths(where, admitted_paths)

        query_kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": count if n_results is None else min(n_results, count),
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
            if (
                admitted_path_set is not None
                and str((meta or {}).get("path") or "").strip()
                not in admitted_path_set
            ):
                continue
            if not _metadata_passes_filters(
                meta or {}, collection=collection,
                type_filter=type_filter,
                include_private=include_private,
                include_archived=include_archived,
                exclude_tags=exclude_tags,
                privacy_tag=privacy_tag,
            ):
                continue
            if collection == "conversations":
                safe_payload = _conversation_safe_payload(doc, meta or {})
                if safe_payload is None:
                    continue
                doc, meta = safe_payload
            chunks.append({
                "id":         cid,
                "document":   doc,
                "metadata":   meta or {},
                "distance":   float(dist) if dist is not None else 1.0,
                "similarity": 1.0 - float(dist) if dist is not None else 0.0,
            })
        return _filter_excluded_chunks(
            chunks,
            excluded_conversation_ids=excluded_conversation_ids,
            excluded_paths=excluded_paths,
        )
    except Exception as exc:
        # Previously this swallowed every error into an empty result with no
        # signal — a transient ChromaDB write-lock during indexing, or an
        # import/path error, would silently blank the RAG package and the
        # model would proceed context-free. Surface it so RAG outages are
        # visible; still degrade gracefully (empty list) rather than crashing
        # the pipeline. (Added 2026-06-04, RAG selection upgrade.)
        import sys
        print(
            f"[knowledge_search_raw] retrieval failed for collection "
            f"{collection!r} (query {query[:80]!r}): "
            f"{type(exc).__name__}: {exc}. Returning empty result.",
            file=sys.stderr, flush=True,
        )
        return []


__all__ = [
    "knowledge_search",
    "knowledge_search_raw",
    "knowledge_search_hybrid_raw",
    "lexical_search_raw",
    "_extract_mode_type_filter",
    "_build_where_clause",
    "_format_result_line",
]
