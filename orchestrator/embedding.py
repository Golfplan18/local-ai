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
import math
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

try:  # pragma: no cover - import shim
    from orchestrator import network_policy
except ImportError:  # pragma: no cover
    import network_policy


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


_DEFAULT_EMBEDDING_PROVIDER = "ollama"
_DEFAULT_EMBEDDING_MODEL = "bge-m3"
_DEFAULT_EMBEDDING_DIM = 1024
_DEFAULT_OLLAMA_URL = "http://localhost:11434"
_DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1"

# Dimensions Ora can establish from its supported profiles and tracked model
# catalogue.  Unknown/custom models remain valid when they declare a positive
# dimension; these entries are the identities whose dimensions are fixed.
KNOWN_EMBEDDING_DIMS = {
    "baai/bge-m3": 1024,
    "bge-m3": 1024,
    "nomic-embed-text": 768,
    "qwen/qwen3-embedding-8b": 4096,
    "openai/text-embedding-3-large": 3072,
    "openai/text-embedding-3-small": 1536,
    "openai/text-embedding-ada-002": 1536,
    "mistralai/mistral-embed": 1024,
}

# Logical name -> physical ChromaDB collection name. Call sites pass logical
# names; the get_collection / get_or_create_collection / delete_collection
# helpers translate via resolve_collection(). Unknown logical names pass
# through unchanged so ad-hoc / test collections do not have to be registered.
_DEFAULT_COLLECTIONS = {
    "knowledge": "knowledge",
    "conversations": "conversations",
    "atomics": "atomic_dedup",
    "conversations_incognito": "conversations-incognito",
    "help": "help",
}


_CHROMADB_CONFIG_PATH = Path(__file__).parent.parent / "config" / "chromadb.json"


class ChromaConfigurationError(RuntimeError):
    """The present machine-specific Chroma identity cannot be trusted."""


def validate_chromadb_config(data: object, config_path: Path) -> dict:
    """Return one complete, internally consistent Chroma storage identity."""
    if not isinstance(data, dict):
        raise ChromaConfigurationError(
            f"Chroma configuration must be a JSON object: {config_path}"
        )

    embedder = data.get("embedder")
    if not isinstance(embedder, dict):
        raise ChromaConfigurationError(
            f"Chroma configuration embedder must be an object: {config_path}"
        )
    provider = embedder.get("provider")
    model = embedder.get("model")
    dim = embedder.get("dim")
    if not isinstance(provider, str) or not provider.strip():
        raise ChromaConfigurationError(
            f"Chroma configuration embedder.provider is required: {config_path}"
        )
    provider = provider.strip()
    if provider not in {"ollama", "openrouter"}:
        raise ChromaConfigurationError(
            f"Chroma configuration embedder.provider is unsupported: {config_path}"
        )
    if not isinstance(model, str) or not model.strip():
        raise ChromaConfigurationError(
            f"Chroma configuration embedder.model is required: {config_path}"
        )
    model = model.strip()
    if isinstance(dim, bool) or not isinstance(dim, int) or dim < 1:
        raise ChromaConfigurationError(
            f"Chroma configuration embedder.dim must be a positive integer: {config_path}"
        )
    known_dim = KNOWN_EMBEDDING_DIMS.get(model.lower())
    if known_dim is not None and dim != known_dim:
        raise ChromaConfigurationError(
            "Chroma configuration embedder.dim is inconsistent with known model "
            f"{model!r} (expected {known_dim}, found {dim}): {config_path}"
        )
    profile_id = embedder.get("profile_id")
    if profile_id is not None and profile_id != f"{provider}:{model}":
        raise ChromaConfigurationError(
            f"Chroma configuration embedder.profile_id is inconsistent: {config_path}"
        )
    for field in ("base_url", "url", "function_name"):
        value = embedder.get(field)
        if value is not None and (
            not isinstance(value, str) or not value.strip()
        ):
            raise ChromaConfigurationError(
                f"Chroma configuration embedder.{field} is invalid: {config_path}"
            )

    collections = data.get("collections")
    if not isinstance(collections, dict):
        raise ChromaConfigurationError(
            f"Chroma configuration collections must be an object: {config_path}"
        )
    for logical, physical in collections.items():
        if (
            not isinstance(logical, str)
            or not logical.strip()
            or not isinstance(physical, str)
            or not physical.strip()
        ):
            raise ChromaConfigurationError(
                f"Chroma configuration collection identities must be non-empty strings: "
                f"{config_path}"
            )
    missing_collections = sorted(set(_DEFAULT_COLLECTIONS) - set(collections))
    if missing_collections:
        raise ChromaConfigurationError(
            "Chroma configuration is missing collection identities "
            f"({', '.join(missing_collections)}): {config_path}"
        )

    history = data.get("collection_history", {})
    if not isinstance(history, dict):
        raise ChromaConfigurationError(
            f"Chroma configuration collection_history must be an object: {config_path}"
        )
    for logical, physical_names in history.items():
        names = [physical_names] if isinstance(physical_names, str) else physical_names
        if (
            not isinstance(logical, str)
            or not logical.strip()
            or not isinstance(names, list)
            or any(not isinstance(name, str) or not name.strip() for name in names)
        ):
            raise ChromaConfigurationError(
                f"Chroma configuration collection history is invalid: {config_path}"
            )

    normalized = dict(data)
    normalized["embedder"] = {
        **embedder,
        "provider": provider,
        "model": model,
        "dim": dim,
    }
    return normalized


def _load_chromadb_config(path: Path | None = None) -> dict:
    """Load and validate chromadb.json once at module import.

    Defaults are valid only for a genuinely absent file.  A present file is an
    explicit storage-identity decision, so unreadable, partial, or inconsistent
    identity fields must stop startup rather than redirecting reads and writes
    to the default collections.
    """
    config_path = path or _CHROMADB_CONFIG_PATH
    try:
        config_path.lstat()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ChromaConfigurationError(
            f"Chroma configuration path is unreadable: {config_path}: {exc}"
        ) from exc
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise ChromaConfigurationError(
            f"Chroma configuration is present but unreadable: {config_path}: {exc}"
        ) from exc
    return validate_chromadb_config(data, config_path)


_CONFIG = _load_chromadb_config()
_embedder_cfg = _CONFIG.get("embedder", {}) or {}

EMBEDDING_PROVIDER = (
    _embedder_cfg["provider"] if _CONFIG else _DEFAULT_EMBEDDING_PROVIDER
)
EMBEDDING_MODEL = _embedder_cfg["model"] if _CONFIG else _DEFAULT_EMBEDDING_MODEL
EMBEDDING_DIM = _embedder_cfg["dim"] if _CONFIG else _DEFAULT_EMBEDDING_DIM
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
EMBEDDING_FUNCTION_NAME = (_embedder_cfg.get("function_name") or "").strip() or None

COLLECTIONS = (
    dict(_CONFIG["collections"]) if _CONFIG else dict(_DEFAULT_COLLECTIONS)
)
COLLECTION_HISTORY = _CONFIG.get("collection_history") or {}


def resolve_collection(logical: str) -> str:
    """Translate a logical collection name to its physical ChromaDB name.

    Unknown logical names pass through unchanged.
    """
    return COLLECTIONS.get(logical, logical)


def resolve_collection_copies(logical: str) -> tuple[str, ...]:
    """Return active then retired physical names for one logical corpus.

    Migration history is machine-specific and therefore lives beside the
    active mapping in ``chromadb.json``.  Lifecycle callers can mutate every
    rollback-visible copy without hardcoding version suffixes or model names.
    """
    active = resolve_collection(logical)
    configured = COLLECTION_HISTORY.get(logical) or []
    if isinstance(configured, str):
        configured = [configured]
    if not isinstance(configured, list):
        configured = []
    ordered: list[str] = []
    for name in [active, *configured]:
        if isinstance(name, str) and name and name not in ordered:
            ordered.append(name)
    return tuple(ordered)


def _listed_collection_name_and_metadata(value: Any) -> tuple[str, dict]:
    if isinstance(value, str):
        return value, {}
    name = getattr(value, "name", "")
    metadata = getattr(value, "metadata", None)
    return (
        name if isinstance(name, str) else "",
        metadata if isinstance(metadata, dict) else {},
    )


def discover_collection_copies(client, logical: str) -> tuple[str, ...]:
    """Discover configured and legacy physical copies of a logical corpus.

    New collections carry explicit logical provenance.  For installations
    predating that metadata, candidates are assigned to the longest matching
    configured/default physical-name family (``<base>`` or ``<base>_...``).
    Hyphenated descendants require explicit provenance/config because they may
    be distinct logical corpora (for example, ``knowledge-graph``).
    Longest-family assignment prevents the conversations
    corpus from claiming the more specific conversations-incognito corpus.
    """
    ordered = list(resolve_collection_copies(logical))
    listed = list(client.list_collections())

    family_roots = {
        key: {
            value
            for value in (
                _DEFAULT_COLLECTIONS.get(key),
                COLLECTIONS.get(key),
            )
            if isinstance(value, str) and value
        }
        for key in set(_DEFAULT_COLLECTIONS) | set(COLLECTIONS)
    }

    for item in listed:
        name, metadata = _listed_collection_name_and_metadata(item)
        if not name:
            continue
        declared = (
            metadata.get("ora:logical_collection")
            or metadata.get("ora_logical_collection")
            or metadata.get("logical_collection")
        )
        belongs = declared == logical
        if not belongs and not declared:
            matches: list[tuple[int, str]] = []
            for candidate_logical, roots in family_roots.items():
                for root in roots:
                    if name == root or name.startswith(root + "_"):
                        matches.append((len(root), candidate_logical))
            if matches:
                matches.sort(reverse=True)
                belongs = matches[0][1] == logical
        if belongs and name not in ordered:
            ordered.append(name)
    return tuple(ordered)


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
    dim: int | None = None,
) -> list[list[float]]:
    """Call OpenRouter's embeddings endpoint for one batch."""
    if dim is None:
        model_key = model.strip().lower() if isinstance(model, str) else ""
        dim = (
            EMBEDDING_DIM
            if model_key == EMBEDDING_MODEL.strip().lower()
            else KNOWN_EMBEDDING_DIMS.get(model_key)
        )
    if isinstance(dim, bool) or not isinstance(dim, int) or dim < 1:
        raise RuntimeError(f"OpenRouter dimension is not configured for {model!r}")

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
            raw, _destination = network_policy.openrouter_request_bytes(
                url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://ora.local",
                    "X-Title": "Ora",
                },
                timeout=timeout,
                max_bytes=32 * 1024 * 1024,
            )
            data = json.loads(raw)
            rows = data.get("data")
            if not isinstance(rows, list):
                raise RuntimeError("OpenRouter returned no embedding data")
            ordered: list[list[float] | None] = [None] * len(texts)
            for position, row in enumerate(rows):
                if not isinstance(row, dict):
                    raise RuntimeError(f"OpenRouter row {position} is not an object")
                if "index" not in row:
                    raise RuntimeError(f"OpenRouter row {position} has no index")
                index = row["index"]
                if type(index) is not int:
                    raise RuntimeError(f"OpenRouter row {position} index is not an int")
                if index < 0 or index >= len(texts):
                    raise RuntimeError(f"OpenRouter index {index} is out of range")
                if ordered[index] is not None:
                    raise RuntimeError(f"OpenRouter index {index} is duplicated")
                vector = row.get("embedding")
                if not isinstance(vector, list):
                    raise RuntimeError(f"OpenRouter vector {index} is not a list")
                if len(vector) != dim:
                    raise RuntimeError(
                        f"OpenRouter returned vector dim {len(vector)}, "
                        f"expected {dim} for {model}"
                    )
                if any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    for value in vector
                ):
                    raise RuntimeError(
                        f"OpenRouter embedding at index {index} contains "
                        "a non-numeric or non-finite component"
                    )
                ordered[index] = vector
            missing = [index for index, vector in enumerate(ordered) if vector is None]
            if missing:
                raise RuntimeError(f"OpenRouter response is missing indices {missing}")
            return [vector for vector in ordered if vector is not None]
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                body = ""
            safe_body = network_policy.redact_sensitive_text(
                body, secrets=(key,),
            )
            last_err = RuntimeError(
                f"OpenRouter embeddings HTTP {exc.code}: {safe_body}",
            )
        except Exception as exc:
            last_err = RuntimeError(
                network_policy.redact_sensitive_text(exc, secrets=(key,)),
            )
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
    dim: int | None = None,
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
            dim=dim,
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
                dim=self.dim,
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


def _make_ollama_embedding_function(
    *,
    model_name: str,
    url: str,
    timeout: int,
    dim: int,
    function_name: str | None = None,
):
    """Build a Chroma-compatible Ollama embedding function.

    ``function_name`` lets a proven-compatible local model attach to a
    collection that was originally created by another provider. Chroma stores
    the embedding function name in collection metadata and rejects a normal
    Ollama function named ``ollama`` when the existing collection was created
    by Ora's OpenRouter adapter.
    """
    from chromadb.api.types import Documents, EmbeddingFunction

    class _OllamaEmbeddingFunction(EmbeddingFunction[Documents]):
        def __init__(self):
            self.model_name = model_name
            self.url = url
            self.timeout = timeout
            self.dim = int(dim)
            self.function_name = function_name or "ollama"

        def name(self) -> str:
            return self.function_name

        def __call__(self, input):  # noqa: A002 - chromadb interface
            items = input if isinstance(input, (list, tuple)) else [input]
            vectors = embed_texts(
                [str(item or "") for item in items],
                provider="ollama",
                model_name=self.model_name,
                url=self.url,
                timeout=self.timeout,
            )
            if self.dim:
                for vec in vectors:
                    if len(vec) != self.dim:
                        raise RuntimeError(
                            f"Ollama returned vector dim {len(vec)}, "
                            f"expected {self.dim} for {self.model_name}"
                        )
            return vectors

        @classmethod
        def build_from_config(cls, config):
            return cls()

        def get_config(self):
            return {
                "model_name": self.model_name,
                "url": self.url,
                "timeout": self.timeout,
                "dim": self.dim,
                "function_name": self.function_name,
            }

        def default_space(self):
            return "cosine"

        @staticmethod
        def is_legacy() -> bool:
            return False

    return _OllamaEmbeddingFunction()


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
    function_name: str | None = EMBEDDING_FUNCTION_NAME,
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

    if function_name:
        return _make_ollama_embedding_function(
            model_name=model_name,
            url=url,
            timeout=timeout,
            dim=dim,
            function_name=function_name,
        )

    return _make_ollama_embedding_function(
        model_name=model_name,
        url=url,
        timeout=timeout,
        dim=dim,
    )


def embed_text(text: str) -> list[float]:
    """Embed one text with the active configured model and dimension.

    Historical pipelines sometimes need an explicit vector because they
    query and update Chroma with ``query_embeddings`` / ``embeddings``.
    Routing those calls through the same configured embedding function used
    to open the collection prevents provider, model, and dimension drift.
    """
    vectors = get_embedding_function()([str(text or "")])
    if not isinstance(vectors, (list, tuple)) or len(vectors) != 1:
        count = len(vectors) if isinstance(vectors, (list, tuple)) else "no"
        raise RuntimeError(
            f"Configured embedder returned {count} vectors for one input"
        )
    # Coerce to real Python floats. The configured embedding function returns
    # numpy arrays, and ``list(ndarray)`` yields np.float32 scalars, not floats
    # — which satisfies the dim check below but is rejected by Chroma's
    # ``query_embeddings`` validator ("expected a list of floats or ints, a
    # numpy array, or a list of numpy arrays"). The annotation says list[float];
    # honour it here so every caller gets the declared type.
    vector = [float(x) for x in vectors[0]]
    if len(vector) != EMBEDDING_DIM:
        raise RuntimeError(
            f"Configured embedder returned vector dim {len(vector)}, "
            f"expected {EMBEDDING_DIM} for {EMBEDDING_MODEL}"
        )
    return vector


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
    collection_metadata = dict(metadata or {"hnsw:space": "cosine"})
    collection_metadata.setdefault("ora:logical_collection", name)
    return client.get_or_create_collection(
        name=resolve_collection(name),
        metadata=collection_metadata,
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
    "ChromaConfigurationError",
    "KNOWN_EMBEDDING_DIMS",
    "validate_chromadb_config",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "EMBEDDING_BASE_URL",
    "OLLAMA_URL",
    "COLLECTIONS",
    "COLLECTION_HISTORY",
    "resolve_collection",
    "resolve_collection_copies",
    "discover_collection_copies",
    "embed_texts",
    "embed_text",
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
