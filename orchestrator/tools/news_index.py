"""News-article indexer — indexes published MSI news articles into ChromaDB's
`msi_news_articles` collection for news-to-news cross-linking.

Mirrors knowledge_index.py's conventions: PersistentClient at ~/ora/chromadb/,
nomic-embed-text via Ollama, doc id = absolute file path, idempotent on path,
--reindex rebuilds the collection.

Usage:
    # Index all .md files in the articles directory:
    python3 news_index.py ~/sites/mainstreetindependent/src/content/articles/

    # Index a single article (post-publish hook):
    python3 news_index.py ~/sites/mainstreetindependent/src/content/articles/2026-05-13-april-cpi-headline-cools-shelter-sticky.md

    # Re-index (clear and rebuild):
    python3 news_index.py --reindex ~/sites/mainstreetindependent/src/content/articles/

ChromaDB metadata schema (msi_news_articles collection):

    Always present:
        path                 — absolute file path (also serves as ChromaDB id)
        slug                 — filename without .md extension
        headline             — article headline (display + match signal)
        publish_date         — ISO date string YYYY-MM-DD (queryable for recency)
        source_cluster_id    — the GDELT-derived cluster identifier (queryable
                                for the continues-chain match signal)
        lede_excerpt         — first 300 chars of the lede (for retrieval display)

    Present when frontmatter carries them:
        primary_themes_json    — JSON-serialized list of theme strings
        primary_entities_json  — JSON-serialized list of entity strings

The embedding text combines headline + lede + nut_graf + body[:6000] so cosine
similarity captures both the article's framing and its content. The full body
(truncated to 8000 chars per the knowledge-index precedent) is stored as the
document text for downstream chunked retrieval if needed.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import yaml

CHROMADB_PATH = os.path.expanduser("~/ora/chromadb/")
COLLECTION_NAME = "msi_news_articles"


# ---------------------------------------------------------------------------
# Frontmatter parsing (mirrors knowledge_index.py)
# ---------------------------------------------------------------------------


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and body from a markdown file."""
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


def _coerce_str(value: Any) -> str:
    """Coerce dates / None / scalars to a clean string."""
    if value is None:
        return ""
    return str(value)


def _coerce_list_of_str(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None and str(v) != ""]
    return [str(value)]


# ---------------------------------------------------------------------------
# Metadata composition
# ---------------------------------------------------------------------------


def _filename_slug(filepath: str) -> str:
    """Slug = filename without .md extension."""
    base = os.path.basename(filepath)
    if base.endswith(".md"):
        base = base[:-3]
    return base


def _compose_chroma_metadata(filepath: str, meta: dict[str, Any]) -> dict[str, Any]:
    """Compose the ChromaDB metadata dict for a parsed news article.

    Reads the article's top-level fields (headline, lede, publish_date) and
    metadata-object fields (source_cluster_id, primary_themes, primary_entities)
    per the Astro articles schema.
    """
    chroma_meta: dict[str, Any] = {
        "path": os.path.abspath(filepath),
        "slug": _filename_slug(filepath),
    }

    chroma_meta["headline"] = _coerce_str(meta.get("headline"))
    chroma_meta["publish_date"] = _coerce_str(meta.get("publish_date"))

    # Truncate lede to 300 chars for display in retrieval results.
    lede = _coerce_str(meta.get("lede"))
    chroma_meta["lede_excerpt"] = lede[:300]

    # The metadata object holds source_cluster_id, primary_themes, primary_entities.
    article_metadata = meta.get("metadata") or {}
    if not isinstance(article_metadata, dict):
        article_metadata = {}

    chroma_meta["source_cluster_id"] = _coerce_str(article_metadata.get("source_cluster_id"))

    themes = _coerce_list_of_str(article_metadata.get("primary_themes"))
    if themes:
        chroma_meta["primary_themes_json"] = json.dumps(themes, ensure_ascii=False)

    entities = _coerce_list_of_str(article_metadata.get("primary_entities"))
    if entities:
        chroma_meta["primary_entities_json"] = json.dumps(entities, ensure_ascii=False)

    return chroma_meta


# ---------------------------------------------------------------------------
# Embedding text
# ---------------------------------------------------------------------------


def _build_embed_text(meta: dict[str, Any], body: str) -> str:
    """Build the text passed to the embedding model.

    Combines headline + lede + nut_graf + leading body so cosine similarity
    captures both the article's framing and its substantive content.
    """
    headline = _coerce_str(meta.get("headline"))
    lede = _coerce_str(meta.get("lede"))
    nut_graf = _coerce_str(meta.get("nut_graf"))
    parts = [headline, lede, nut_graf, body[:6000]]
    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


def index_file(collection, filepath: str, stats: dict[str, int]) -> None:
    """Index a single article into the msi_news_articles collection."""
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

    # Already-indexed check (path-based; --reindex bypasses this via collection delete)
    try:
        existing = collection.get(ids=[doc_id])
        if existing and existing["ids"]:
            stats["skipped"] += 1
            return
    except Exception:
        pass

    chroma_meta = _compose_chroma_metadata(filepath, meta)
    embed_text = _build_embed_text(meta, body)
    doc_text = body[:8000]

    # Add to collection — the collection's bound embedding_function handles
    # embedding via Ollama nomic-embed-text per the embedding module.
    collection.add(
        ids=[doc_id],
        documents=[embed_text],
        metadatas=[chroma_meta],
    )
    stats["indexed"] += 1
    print(f"  + {chroma_meta['slug']}")


def index_path(path: str, reindex: bool = False) -> None:
    """Index a file or directory into the msi_news_articles collection."""
    import chromadb
    from orchestrator.embedding import get_or_create_collection

    client = chromadb.PersistentClient(path=CHROMADB_PATH)

    if reindex:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"Cleared existing {COLLECTION_NAME} collection.")
        except Exception:
            pass

    collection = get_or_create_collection(client, COLLECTION_NAME)

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
    print(f"{COLLECTION_NAME} collection total: {collection.count()} documents")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 news_index.py [--reindex] <path>")
        print("  path: a .md article file or directory of articles to index")
        sys.exit(1)

    reindex = "--reindex" in sys.argv
    paths = [a for a in sys.argv[1:] if a != "--reindex"]
    for p in paths:
        index_path(p, reindex=reindex)
