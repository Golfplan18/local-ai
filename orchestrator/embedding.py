"""Shared embedding configuration and provider adapter.

Cross-platform local default. Ora ships with a native Ollama embedding
profile (BGE-M3) and can optionally switch a specific installation to an
API-backed profile such as OpenRouter's Qwen3 Embedding 8B. The active
profile lives in ``config/chromadb.json`` beside the physical collection
map because embedding model, vector dimension, and Chroma collection names
must move together.

Centralizes:
  - which embedding provider/model/dimension the system uses
  - how ChromaDB collections are opened with the matching embedding function
  - health checks for local and API-backed embedding profiles

Chroma collections are always opened with an explicit embedding function.
That keeps failures loud: ChromaDB must not silently fall through to its
default sentence-transformers embedder and create dimension-mismatched
collections.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


_DEFAULT_EMBEDDING_PROVIDER = "ollama"
_DEFAULT_EMBEDDING_MODEL = "bge-m3"
_DEFAULT_EMBEDDING_DIM = 1024
_DEFAULT_OLLAMA_URL = "http://localhost:11434"
_DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1"

# Logical name -> physical ChromaDB collection name. Call sites pass logical
# names; the get_collection / get_or_create_collection / delete_collection
# helpers translate via resolve_collection(). Unknown logical names pass
# through unchanged so ad-hoc / test collections do not have to be registered.
_DEFAULT_COLLECTIONS = {
    "knowledge": "knowledge",
    "conversations": "conversations",
    "atomics": "atomic_dedup",
    "conversations_incognito": "conversations-incognito",
}


_CHROMADB_CONFIG_PATH = Path(__file__).parent.parent / "config" / "chromadb.json"


def _load_chromadb_config() -> dict:
    """Load chromadb.json once at module import.

    Missing file or parse error returns an empty dict so defaults apply.
    """
    if not _CHROMADB_CONFIG_PATH.exists():
        return {}
    try:
        with open(_CHROMADB_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


_CONFIG = _load_chromadb_config()
_embedder_cfg = _CONFIG.get("embedder", {}) or {}

EMBEDDING_PROVIDER = (
    _embedder_cfg.get("provider") or _DEFAULT_EMBEDDING_PROVIDER
).strip() or _DEFAULT_EMBEDDING_PROVIDER
EMBEDDING_MODEL = _embedder_cfg.get("model") or _DEFAULT_EMBEDDING_MODEL
EMBEDDING_DIM = int(_embedder_cfg.get("dim") or _DEFAULT_EMBEDDING_DIM)
EMBEDDING_BASE_URL = (
    _embedder_cfg.get("base_url")
    or _embedder_cfg.get("url")
    or (
        _DEFAULT_OPENROUTER_URL
        if EMBEDDING_PROVIDER == "openrouter"
        else _DEFAULT_OLLAMA_URL
    )
)
# Backward-compatible alias used by older local-only call sites.
OLLAMA_URL = EMBEDDING_BASE_URL if EMBEDDING_PROVIDER == "ollama" else _DEFAULT_OLLAMA_URL

COLLECTIONS = {**_DEFAULT_COLLECTIONS, **(_CONFIG.get("collections") or {})}


def resolve_collection(logical: str) -> str:
    """Translate a logical collection name to its physical ChromaDB name.

    Unknown logical names pass through unchanged.
    """
    return COLLECTIONS.get(logical, logical)


# ---------------------------------------------------------------------------
# Provider helpers
# ---------------------------------------------------------------------------


def _openrouter_api_key() -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    try:
        import keyring

        return keyring.get_password("ora", "openrouter-api-key")
    except Exception:
        return None


def _openrouter_embed_batch(
    texts: list[str],
    *,
    model: str,
    base_url: str = _DEFAULT_OPENROUTER_URL,
    timeout: float = 120.0,
    attempts: int = 3,
) -> list[list[float]]:
    """Call OpenRouter's embeddings endpoint for one batch."""
    key = _openrouter_api_key()
    if not key:
        raise RuntimeError(
            "OpenRouter API key is not set. Add it in Settings -> External APIs."
        )

    url = base_url.rstrip("/") + "/embeddings"
    payload = json.dumps({
        "model": model,
        "input": texts,
        "encoding_format": "float",
    }).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://ora.local",
                    "X-Title": "Ora",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            rows = data.get("data")
            if not isinstance(rows, list):
                raise RuntimeError("OpenRouter returned no embedding data")
            rows = sorted(rows, key=lambda r: int(r.get("index", 0)))
            embeddings = [r.get("embedding") for r in rows]
            if len(embeddings) != len(texts):
                raise RuntimeError(
                    f"OpenRouter returned {len(embeddings)} embeddings "
                    f"for {len(texts)} inputs"
                )
            if not all(isinstance(v, list) for v in embeddings):
                raise RuntimeError("OpenRouter returned malformed embeddings")
            return embeddings
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                body = ""
            last_err = RuntimeError(f"OpenRouter embeddings HTTP {exc.code}: {body}")
        except Exception as exc:
            last_err = exc
        if attempt < attempts:
            time.sleep(attempt * 2)
    assert last_err is not None
    raise last_err


def _ollama_embed_batch(
    texts: list[str],
    *,
    model: str,
    url: str = _DEFAULT_OLLAMA_URL,
    timeout: float = 120.0,
    attempts: int = 3,
) -> list[list[float]]:
    """Call Ollama's /api/embed endpoint for one batch."""
    payload = json.dumps({"model": model, "input": texts}).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                f"{url.rstrip('/')}/api/embed",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            embeddings = data.get("embeddings")
            if not isinstance(embeddings, list) or len(embeddings) != len(texts):
                raise RuntimeError(
                    f"Ollama returned "
                    f"{len(embeddings) if isinstance(embeddings, list) else 'no'} "
                    f"embeddings for {len(texts)} inputs"
                )
            return embeddings
        except Exception as exc:
            last_err = exc
        if attempt < attempts:
            time.sleep(attempt * 2)
    assert last_err is not None
    raise last_err


def embed_texts(
    texts: list[str],
    *,
    provider: str = EMBEDDING_PROVIDER,
    model_name: str = EMBEDDING_MODEL,
    url: str = OLLAMA_URL,
    base_url: str = EMBEDDING_BASE_URL,
    timeout: float = 120.0,
    attempts: int = 3,
) -> list[list[float]]:
    """Embed a batch of texts with the selected provider."""
    clean_texts = [str(t or "") for t in texts]
    if provider == "openrouter":
        return _openrouter_embed_batch(
            clean_texts,
            model=model_name,
            base_url=base_url,
            timeout=timeout,
            attempts=attempts,
        )
    return _ollama_embed_batch(
        clean_texts,
        model=model_name,
        url=url,
        timeout=timeout,
        attempts=attempts,
    )


def _make_openrouter_embedding_function(
    *,
    model_name: str,
    base_url: str,
    timeout: int,
    dim: int,
):
    """Build a Chroma-compatible OpenRouter embedding function."""
    from chromadb.api.types import Documents, EmbeddingFunction

    class _OpenRouterEmbeddingFunction(EmbeddingFunction[Documents]):
        def __init__(self):
            self.model_name = model_name
            self.base_url = base_url
            self.timeout = timeout
            self.dim = int(dim)

        @staticmethod
        def name() -> str:
            return "ora-openrouter-embedding"

        def __call__(self, input):  # noqa: A002 - chromadb interface
            items = input if isinstance(input, (list, tuple)) else [input]
            vectors = embed_texts(
                [str(item or "") for item in items],
                provider="openrouter",
                model_name=self.model_name,
                base_url=self.base_url,
                timeout=self.timeout,
            )
            if self.dim:
                for vec in vectors:
                    if len(vec) != self.dim:
                        raise RuntimeError(
                            f"OpenRouter returned vector dim {len(vec)}, "
                            f"expected {self.dim} for {self.model_name}"
                        )
            return vectors

        @classmethod
        def build_from_config(cls, config):
            return cls()

        def get_config(self):
            return {
                "model_name": self.model_name,
                "base_url": self.base_url,
                "timeout": self.timeout,
                "dim": self.dim,
            }

        def default_space(self):
            return "cosine"

        @staticmethod
        def is_legacy() -> bool:
            return False

    return _OpenRouterEmbeddingFunction()


# ---------------------------------------------------------------------------
# Embedding function factory
# ---------------------------------------------------------------------------


def get_embedding_function(
    *,
    provider: str = EMBEDDING_PROVIDER,
    model_name: str = EMBEDDING_MODEL,
    url: str = OLLAMA_URL,
    base_url: str = EMBEDDING_BASE_URL,
    timeout: int = 60,
    dim: int = EMBEDDING_DIM,
):
    """Return a Chroma-compatible EmbeddingFunction.

    Used by both ``client.create_collection(embedding_function=...)`` and
    ``client.get_collection(embedding_function=...)``. Once a collection is
    bound to this function, every ``add()`` and ``query()`` routes through
    the chosen provider.
    """
    if provider == "openrouter":
        return _make_openrouter_embedding_function(
            model_name=model_name,
            base_url=base_url,
            timeout=timeout,
            dim=dim,
        )

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
        req = urllib.request.Request(f"{url.rstrip('/')}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True, f"Ollama reachable at {url}"
    except urllib.error.URLError as exc:
        return False, (
            f"Ollama not reachable at {url}: {exc}. "
            f"Install Ollama, then run `ollama serve` to start the daemon."
        )
    except Exception as exc:
        return False, f"Ollama not reachable at {url}: {exc}"


def check_embedding_model_available(
    model: str = EMBEDDING_MODEL,
    url: str = OLLAMA_URL,
    timeout: float = 2.0,
) -> tuple[bool, str]:
    """Verify the local embedding model has been pulled."""
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}/api/tags")
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
    except Exception as exc:
        return False, f"Cannot reach Ollama: {exc}"


def check_openrouter_embedding_available(
    model: str = EMBEDDING_MODEL,
) -> tuple[bool, str]:
    """Verify API credentials are present for an OpenRouter embedder."""
    if _openrouter_api_key():
        return True, f"OpenRouter key available for embedding model '{model}'"
    return False, "OpenRouter key missing. Add it in Settings -> External APIs."


def assert_embedding_ready(*, raise_on_error: bool = False) -> tuple[bool, list[str]]:
    """Combined startup check. Returns (ready, [messages])."""
    messages: list[str] = []
    if EMBEDDING_PROVIDER == "openrouter":
        ok, msg = check_openrouter_embedding_available()
        messages.append(msg)
        if not ok and raise_on_error:
            raise RuntimeError("Embedding setup not ready: " + msg)
        return ok, messages

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
    """Idempotent collection accessor with Ora's active embedding function."""
    return client.get_or_create_collection(
        name=resolve_collection(name),
        metadata=metadata or {"hnsw:space": "cosine"},
        embedding_function=get_embedding_function(),
    )


def get_collection(client, name: str):
    """Open an existing collection with Ora's active embedding function."""
    return client.get_collection(
        name=resolve_collection(name),
        embedding_function=get_embedding_function(),
    )


def delete_collection(client, name: str):
    """Delete a collection by logical name."""
    return client.delete_collection(name=resolve_collection(name))


# ---------------------------------------------------------------------------
# Test stub
# ---------------------------------------------------------------------------


def _make_stub_class():
    """Build the stub class lazily so ChromaDB is only required at use time."""
    from chromadb.api.types import Documents, EmbeddingFunction

    class _DeterministicStubEmbeddingFunction(EmbeddingFunction[Documents]):
        """Test-only deterministic embedder."""

        def __init__(self, dim: int = EMBEDDING_DIM):
            self.dim = dim

        @staticmethod
        def name() -> str:
            return "ora-test-stub"

        def __call__(self, input):  # noqa: A002 - chromadb interface
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
    """Replace ``get_embedding_function`` with a deterministic stub."""
    global _TEST_STUB_INSTALLED, get_embedding_function
    if _TEST_STUB_INSTALLED:
        return
    StubCls = _make_stub_class()

    def _stub(
        *,
        provider=EMBEDDING_PROVIDER,
        model_name=EMBEDDING_MODEL,
        url=OLLAMA_URL,
        base_url=EMBEDDING_BASE_URL,
        timeout=60,
    ):
        return StubCls()

    get_embedding_function = _stub
    _TEST_STUB_INSTALLED = True


def uninstall_test_stub() -> None:
    """Restore the real provider-backed embedding function."""
    global _TEST_STUB_INSTALLED, get_embedding_function
    get_embedding_function = _REAL_GET_EMBEDDING_FUNCTION
    _TEST_STUB_INSTALLED = False


__all__ = [
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "EMBEDDING_BASE_URL",
    "OLLAMA_URL",
    "COLLECTIONS",
    "resolve_collection",
    "embed_texts",
    "get_embedding_function",
    "check_ollama_available",
    "check_embedding_model_available",
    "check_openrouter_embedding_available",
    "assert_embedding_ready",
    "get_or_create_collection",
    "get_collection",
    "delete_collection",
    "install_test_stub",
    "uninstall_test_stub",
]
