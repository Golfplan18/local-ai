"""
incognito.py — Incognito Mode with Temporary ChromaDB Collection (Phase 13.2)

Creates a third ChromaDB collection (conversations-incognito) for temporary
conversation storage during incognito sessions.

Features:
  - Toggle on/off via API endpoint
  - Incognito conversations write to temporary collection instead of permanent
  - Temporary collection serves as conversation RAG during session
  - On toggle-off, all incognito records are deleted with confirmation
  - Persistent visible indicator when active

Privacy caveat (displayed when incognito is active):
  "Incognito removes the local record. Anything sent to commercial API
  endpoints during this session was received by the provider and is not
  affected by local deletion. True incognito requires local models for
  the conversation."

Usage:
    from orchestrator.tools.incognito import IncognitoManager
    manager = IncognitoManager()
    manager.enable()
    # ... conversation happens, routed to incognito collection ...
    manager.disable()  # deletes all incognito records
"""

from __future__ import annotations

import os
from dataclasses import dataclass


CHROMADB_PATH = os.path.expanduser("~/ora/chromadb/")
INCOGNITO_COLLECTION = "conversations-incognito"

PRIVACY_CAVEAT = (
    "Incognito removes the local record. Anything sent to commercial API "
    "endpoints during this session was received by the provider and is not "
    "affected by local deletion. True incognito requires local models for "
    "the conversation."
)


@dataclass
class IncognitoState:
    """Current state of incognito mode."""
    enabled: bool = False
    session_count: int = 0  # number of exchanges in current incognito session
    collection_size: int = 0  # records in incognito collection


class IncognitoManager:
    """
    Manages incognito mode for the chat server.

    When enabled, conversation processing writes to the incognito
    ChromaDB collection instead of the permanent one.
    """

    def __init__(self, chromadb_path: str = None):
        self.chromadb_path = chromadb_path or CHROMADB_PATH
        self.state = IncognitoState()
        self._client = None
        self._collection = None

    def _get_client(self):
        """Lazy-load ChromaDB client."""
        if self._client is None:
            try:
                import chromadb
                self._client = chromadb.PersistentClient(path=self.chromadb_path)
            except ImportError:
                return None
        return self._client

    def _get_collection(self):
        """Get or create the incognito collection."""
        if self._collection is None:
            client = self._get_client()
            if client:
                self._collection = client.get_or_create_collection(
                    name=INCOGNITO_COLLECTION
                )
        return self._collection

    def enable(self) -> IncognitoState:
        """Enable incognito mode."""
        self.state.enabled = True
        self.state.session_count = 0
        # Ensure collection exists
        self._get_collection()
        return self.state

    def disable(self, confirm: bool = True) -> IncognitoState:
        """
        Disable incognito mode and delete all incognito records.

        Args:
            confirm: Must be True to proceed with deletion.
                     Safety check to prevent accidental data loss.
        """
        if not confirm:
            return self.state

        self.state.enabled = False

        # Delete all records from incognito collection
        collection = self._get_collection()
        if collection:
            try:
                # Get all IDs in the collection
                results = collection.get()
                if results and results.get("ids"):
                    collection.delete(ids=results["ids"])
                self.state.collection_size = 0
            except Exception:
                pass

        self.state.session_count = 0
        self._collection = None
        return self.state

    def get_state(self) -> IncognitoState:
        """Get current incognito state."""
        if self.state.enabled:
            collection = self._get_collection()
            if collection:
                try:
                    self.state.collection_size = collection.count()
                except Exception:
                    pass
        return self.state

    def get_collection_name(self) -> str:
        """
        Return the appropriate collection name based on incognito state.
        Use this when writing conversation data.
        """
        if self.state.enabled:
            return INCOGNITO_COLLECTION
        return "conversations"

    def add_to_incognito(self, document: str, metadata: dict,
                         embedding: list[float] = None,
                         doc_id: str = None):
        """
        Add a conversation record to the incognito collection.

        Args:
            document: The conversation text.
            metadata: Metadata dict (timestamp, topics, etc.).
            embedding: Optional pre-computed embedding.
            doc_id: Optional document ID.
        """
        if not self.state.enabled:
            return

        collection = self._get_collection()
        if not collection:
            return

        if doc_id is None:
            import uuid
            doc_id = str(uuid.uuid4())

        kwargs = {
            "documents": [document],
            "metadatas": [metadata],
            "ids": [doc_id],
        }
        if embedding:
            kwargs["embeddings"] = [embedding]

        collection.add(**kwargs)
        self.state.session_count += 1
        self.state.collection_size = collection.count()

    def query_incognito(self, query_text: str, n_results: int = 5) -> list[dict]:
        """
        Query the incognito collection for conversation RAG.
        Returns results in the same format as the regular conversation query.
        """
        if not self.state.enabled:
            return []

        collection = self._get_collection()
        if not collection or collection.count() == 0:
            return []

        try:
            results = collection.query(
                query_texts=[query_text],
                n_results=min(n_results, collection.count()),
            )

            matches = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                    distance = results["distances"][0][i] if results.get("distances") else 0
                    matches.append({
                        "document": doc,
                        "metadata": meta,
                        "distance": distance,
                    })
            return matches
        except Exception:
            return []


# Global incognito manager instance
_incognito_manager = IncognitoManager()


def get_incognito_manager() -> IncognitoManager:
    """Get the global incognito manager."""
    return _incognito_manager
