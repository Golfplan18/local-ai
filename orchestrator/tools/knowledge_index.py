"""Knowledge indexer — indexes vault notes into ChromaDB's knowledge collection.

Usage:
    # Index all .md files in a directory:
    python3 knowledge_index.py ~/Documents/vault/Engrams/

    # Index a single file:
    python3 knowledge_index.py ~/Documents/vault/Engrams/inversion.md

    # Index the mental models directory:
    python3 knowledge_index.py ~/ora/knowledge/mental-models/

    # Re-index (clear and rebuild):
    python3 knowledge_index.py --reindex ~/Documents/vault/Engrams/

The indexer reads each .md file, strips YAML frontmatter for metadata,
and indexes the content into ChromaDB using nomic-embed-text for embeddings.
Files already indexed (by path) are skipped unless --reindex is used.

Mental model notes should follow this format:

    ---
    title: Inversion
    nexus: mental-model
    type: engram
    domain: [problem-solving, decision-making]
    triggers: when a problem has been approached from only one direction
    ---

    # Inversion

    ## Core Principle
    [What the model says — one paragraph]

    ## When to Apply
    [Trigger conditions — when this lens is useful]

    ## How to Apply
    [Operational steps]

    ## Example
    [A worked example showing the model in action]

The 'triggers' field is especially important — it becomes part of the
embedded content, making the note retrievable when a prompt matches
the trigger conditions semantically.
"""

import os
import sys
import re
import json

CHROMADB_PATH = os.path.expanduser("~/ora/chromadb/")


def _nomic_embed(text):
    """Embed text via nomic-embed-text through ollama."""
    try:
        import urllib.request
        payload = json.dumps({"model": "nomic-embed-text", "prompt": text}).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("embedding")
    except Exception:
        return None


def _parse_frontmatter(content):
    """Extract YAML frontmatter and body from a markdown file."""
    if not content.startswith("---"):
        return {}, content

    end = content.find("\n---", 3)
    if end == -1:
        return {}, content

    yaml_block = content[3:end].strip()
    body = content[end + 4:].strip()

    # Simple YAML parser for flat key-value pairs
    meta = {}
    for line in yaml_block.splitlines():
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            # Handle YAML arrays: [item1, item2]
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",")]
            meta[key] = val
    return meta, body


def _build_embed_text(meta, body):
    """Build the text to embed. Includes title, triggers, and first ~1000 chars of body."""
    parts = []
    if meta.get("title"):
        parts.append(meta["title"])
    if meta.get("triggers"):
        triggers = meta["triggers"]
        if isinstance(triggers, list):
            triggers = ", ".join(triggers)
        parts.append(f"Triggers: {triggers}")
    if meta.get("domain"):
        domain = meta["domain"]
        if isinstance(domain, list):
            domain = ", ".join(domain)
        parts.append(f"Domain: {domain}")
    # First ~1000 chars of body for semantic content
    parts.append(body[:1000])
    return "\n".join(parts)


def index_file(collection, filepath, stats):
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

    # Check if already indexed
    try:
        existing = collection.get(ids=[doc_id])
        if existing and existing["ids"]:
            stats["skipped"] += 1
            return
    except Exception:
        pass

    # Build metadata for ChromaDB
    chroma_meta = {
        "source": os.path.basename(filepath),
        "path": doc_id,
        "title": str(meta.get("title", os.path.basename(filepath).replace(".md", ""))),
        "nexus": str(meta.get("nexus", "")),
        "type": str(meta.get("type", "")),
    }
    if meta.get("domain"):
        domain = meta["domain"]
        chroma_meta["domain"] = ", ".join(domain) if isinstance(domain, list) else str(domain)
    if meta.get("triggers"):
        triggers = meta["triggers"]
        chroma_meta["triggers"] = ", ".join(triggers) if isinstance(triggers, list) else str(triggers)

    # Build embedding text and document text
    embed_text = _build_embed_text(meta, body)
    # Store the full body (up to 8000 chars) as the document
    doc_text = body[:8000]

    # Generate embedding
    embedding = _nomic_embed(embed_text)

    add_kwargs = dict(
        ids=[doc_id],
        documents=[doc_text],
        metadatas=[chroma_meta],
    )
    if embedding is not None:
        add_kwargs["embeddings"] = [embedding]

    collection.add(**add_kwargs)
    stats["indexed"] += 1
    print(f"  + {chroma_meta['title']}")


def index_path(path, reindex=False):
    """Index a file or directory into the knowledge collection."""
    import chromadb

    client = chromadb.PersistentClient(path=CHROMADB_PATH)

    if reindex:
        try:
            client.delete_collection("knowledge")
            print("Cleared existing knowledge collection.")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        "knowledge",
        metadata={"hnsw:space": "cosine"},
    )

    stats = {"indexed": 0, "skipped": 0, "errors": 0}

    path = os.path.expanduser(path)

    if os.path.isfile(path):
        print(f"Indexing file: {path}")
        index_file(collection, path, stats)
    elif os.path.isdir(path):
        md_files = []
        for root, dirs, files in os.walk(path):
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
