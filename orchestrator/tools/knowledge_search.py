"""ChromaDB knowledge search tool."""

import os

CHROMADB_PATH = os.path.expanduser("~/local-ai/chromadb/")


def knowledge_search(query: str, collection: str = "knowledge", n_results: int = 5) -> str:
    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMADB_PATH)
        col = client.get_or_create_collection(collection)
        count = col.count()
        if count == 0:
            return f"Collection '{collection}' is empty. Add documents to enable semantic search."
        results = col.query(query_texts=[query], n_results=min(n_results, count))
        output = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        for i, (doc, meta) in enumerate(zip(docs, metas), 1):
            source = meta.get("source", "unknown") if meta else "unknown"
            output.append(f"{i}. [{source}]")
            output.append(f"   {doc[:500]}{'...' if len(doc) > 500 else ''}")
            output.append("")
        return "\n".join(output) if output else "No results found."
    except Exception as e:
        return f"Knowledge search error: {str(e)}"
