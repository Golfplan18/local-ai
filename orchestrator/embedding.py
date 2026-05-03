"""Shared embedding configuration — single source of truth.

Cross-platform. Works wherever Ollama runs (Windows / Linux / macOS).

Centralizes:
  - which embedding model the system uses (nomic-embed-text, 768-dim)
  - how chromadb collections are created with the matching
    embedding_function (so the collection itself owns the embedder
    and can't silently fall through to a different model)
  - health checks for Ollama reachability and model availability

The previous codebase relied on each indexer call computing
embeddings explicitly via `_nomic_embed(text)` and falling through to
chromadb's default sentence-transformers when Ollama was unreachable.
That silent fallback locked the collection to MiniLM-L6 (384-dim)
without anyone noticing. Wiring the embedding_function onto the
collection makes failures loud — chromadb raises rather than
substituting a different model.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIM = 768
OLLAMA_URL = "http://localhost:11434"


# ---------------------------------------------------------------------------
# Embedding function factory
# ---------------------------------------------------------------------------


def get_embedding_function(
    *,
    model_name: str = EMBEDDING_MODEL,
    url: str = OLLAMA_URL,
    timeout: int = 60,
):
    """Return a chromadb-compatible EmbeddingFunction backed by Ollama.

    Used by both `client.create_collection(embedding_function=...)`
    and `client.get_collection(embedding_function=...)`. Once a
    collection is bound to this function, every add() and query()
    routes through it — there's no path for chromadb to silently
    substitute a different embedder.
    """
    from chromadb.utils import embedding_functions
    return embedding_functions.OllamaEmbeddingFunction(
        url=url,
        model_name=model_name,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Health checks (used at startup)
# ---------------------------------------------------------------------------


def check_ollama_available(url: str = OLLAMA_URL, timeout: float = 2.0) -> tuple[bool, str]:
    """Quick liveness check on the Ollama daemon. Returns (ok, message)."""
    try:
        req = urllib.request.Request(f"{url}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True, f"Ollama reachable at {url}"
    except urllib.error.URLError as e:
        return False, (
            f"Ollama not reachable at {url}: {e}. "
            f"Install Ollama (https://ollama.ai), then run "
            f"`ollama serve` to start the daemon."
        )
    except Exception as e:
        return False, f"Ollama not reachable at {url}: {e}"


def check_embedding_model_available(
    model: str = EMBEDDING_MODEL,
    url: str = OLLAMA_URL,
    timeout: float = 2.0,
) -> tuple[bool, str]:
    """Verify the embedding model has been pulled. Returns (ok, message)."""
    try:
        req = urllib.request.Request(f"{url}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        models = data.get("models", []) or []
        names = [m.get("name", "") for m in models]
        if any(model in (n or "") for n in names):
            return True, f"Embedding model '{model}' available"
        return False, (
            f"Embedding model '{model}' not pulled. "
            f"Run: `ollama pull {model}`"
        )
    except Exception as e:
        return False, f"Cannot reach Ollama: {e}"


def assert_embedding_ready(*, raise_on_error: bool = False) -> tuple[bool, list[str]]:
    """Combined startup check. Returns (ready, [messages]).

    When `raise_on_error=True`, raises RuntimeError instead of returning
    False. Used by the server startup path so the operator sees a clear
    error rather than silent degradation.
    """
    messages: list[str] = []
    ok1, msg1 = check_ollama_available()
    messages.append(msg1)
    if not ok1:
        if raise_on_error:
            raise RuntimeError("Embedding setup not ready: " + msg1)
        return False, messages

    ok2, msg2 = check_embedding_model_available()
    messages.append(msg2)
    if not ok2 and raise_on_error:
        raise RuntimeError("Embedding setup not ready: " + msg2)

    return ok1 and ok2, messages


# ---------------------------------------------------------------------------
# Collection helpers
# ---------------------------------------------------------------------------


def get_or_create_collection(client, name: str, *, metadata: Optional[dict] = None):
    """Idempotent collection accessor that always binds the canonical
    embedding_function. Use everywhere instead of
    `client.get_or_create_collection(name)` so collections never end
    up bound to chromadb's default embedder by accident.
    """
    return client.get_or_create_collection(
        name=name,
        metadata=metadata or {"hnsw:space": "cosine"},
        embedding_function=get_embedding_function(),
    )


def get_collection(client, name: str):
    """Open an existing collection with the canonical embedding_function.

    chromadb requires the embedding_function on every access for
    collections originally created with one — otherwise queries embed
    via the default and produce dimension mismatches. Use this rather
    than `client.get_collection(name)`.
    """
    return client.get_collection(
        name=name,
        embedding_function=get_embedding_function(),
    )


# ---------------------------------------------------------------------------
# Test stub — used to swap a deterministic embedder into the canonical
# accessor for unit tests that shouldn't depend on Ollama running.
# ---------------------------------------------------------------------------


def _make_stub_class():
    """Build the stub class lazily so chromadb is only required at use
    time (not at module import time)."""
    from chromadb.api.types import EmbeddingFunction, Documents

    class _DeterministicStubEmbeddingFunction(EmbeddingFunction[Documents]):
        """Test-only embedding function. Generates deterministic 768-dim
        vectors by hashing the input text. Tests never depend on Ollama
        when this is installed via `install_test_stub()`.

        Cross-platform: pure Python, stdlib hashlib only.
        """

        def __init__(self, dim: int = EMBEDDING_DIM):
            self.dim = dim

        @staticmethod
        def name() -> str:
            return "ora-test-stub"

        def __call__(self, input):  # noqa: A002 — chromadb interface
            import hashlib
            results = []
            items = input if isinstance(input, (list, tuple)) else [input]
            for text in items:
                h = hashlib.sha256((text or "").encode("utf-8")).digest()
                vec: list[float] = []
                i = 0
                while len(vec) < self.dim:
                    vec.append(float(h[i % len(h)]) / 255.0)
                    i += 1
                results.append(vec[: self.dim])
            return results

        @classmethod
        def build_from_config(cls, config):
            return cls(dim=int(config.get("dim", EMBEDDING_DIM)))

        def get_config(self):
            return {"dim": self.dim}

        def default_space(self):
            return "cosine"

        @staticmethod
        def is_legacy() -> bool:
            return False

    return _DeterministicStubEmbeddingFunction


_TEST_STUB_INSTALLED = False
_REAL_GET_EMBEDDING_FUNCTION = get_embedding_function


def install_test_stub() -> None:
    """Replace `get_embedding_function` with a stub that returns a
    deterministic embedder. Idempotent. Use in test setUp; reverse with
    `uninstall_test_stub()`."""
    global _TEST_STUB_INSTALLED, get_embedding_function
    if _TEST_STUB_INSTALLED:
        return
    StubCls = _make_stub_class()
    def _stub(*, model_name=EMBEDDING_MODEL, url=OLLAMA_URL, timeout=60):
        return StubCls()
    get_embedding_function = _stub
    _TEST_STUB_INSTALLED = True


def uninstall_test_stub() -> None:
    """Restore the real Ollama-backed embedding function."""
    global _TEST_STUB_INSTALLED, get_embedding_function
    get_embedding_function = _REAL_GET_EMBEDDING_FUNCTION
    _TEST_STUB_INSTALLED = False


__all__ = [
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "OLLAMA_URL",
    "get_embedding_function",
    "check_ollama_available",
    "check_embedding_model_available",
    "assert_embedding_ready",
    "get_or_create_collection",
    "get_collection",
    "install_test_stub",
    "uninstall_test_stub",
]
