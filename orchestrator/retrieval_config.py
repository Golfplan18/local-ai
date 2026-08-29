"""Retrieval configuration helpers.

The live retrieval profile is machine-specific. It lives in
``~/ora/config/chromadb.json`` beside the Chroma collection map because
embedding provider/model/dimensions and physical collection names have to
move together. The tracked template carries the universal local default;
the live file can point a power user at an API embedder without changing
the install default for everyone else.
"""
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

try:
    from orchestrator.embedding import KNOWN_EMBEDDING_DIMS as _KNOWN_DIMS
except ImportError:  # pragma: no cover - direct-module import shim
    from embedding import KNOWN_EMBEDDING_DIMS as _KNOWN_DIMS

ORA_HOME = Path(os.environ.get("ORA_HOME") or os.path.expanduser("~/ora"))
CONFIG_DIR = ORA_HOME / "config"
CHROMADB_CONFIG_PATH = CONFIG_DIR / "chromadb.json"
OPENROUTER_CATALOG_PATH = CONFIG_DIR / "openrouter-catalog.json"

DEFAULT_COLLECTIONS = {
    "knowledge": "knowledge",
    "conversations": "conversations",
    "atomics": "atomic_dedup",
    "conversations_incognito": "conversations-incognito",
    "help": "help",
}

DEFAULT_EMBEDDING_PROFILES: list[dict[str, Any]] = [
    {
        "id": "ollama:bge-m3",
        "label": "BGE-M3 local (Ollama)",
        "provider": "ollama",
        "model": "bge-m3",
        "dimensions": 1024,
        "base_url": "http://localhost:11434",
        "native": True,
        "requires_api_key": False,
        "recommended": "standard",
    },
    {
        "id": "ollama:nomic-embed-text",
        "label": "nomic-embed-text local (Ollama)",
        "provider": "ollama",
        "model": "nomic-embed-text",
        "dimensions": 768,
        "base_url": "http://localhost:11434",
        "native": True,
        "requires_api_key": False,
        "recommended": "legacy",
    },
    {
        "id": "openrouter:qwen/qwen3-embedding-8b",
        "label": "Qwen3 Embedding 8B (OpenRouter)",
        "provider": "openrouter",
        "model": "qwen/qwen3-embedding-8b",
        "dimensions": 4096,
        "base_url": "https://openrouter.ai/api/v1",
        "native": False,
        "requires_api_key": True,
        "recommended": "power",
    },
]

DEFAULT_RERANKERS: list[dict[str, Any]] = [
    {
        "id": "auto",
        "label": "Auto: Cohere Pro, then local Qwen",
        "provider": "auto",
        "model": "cohere/rerank-4-pro",
        "requires_api_key": False,
        "fallbacks": ["llama_cpp:Qwen3-Reranker-0.6B-GGUF"],
    },
    {
        "id": "openrouter:cohere/rerank-4-pro",
        "label": "Cohere Rerank 4 Pro (OpenRouter)",
        "provider": "openrouter",
        "model": "cohere/rerank-4-pro",
        "requires_api_key": True,
    },
    {
        "id": "openrouter:cohere/rerank-4-fast",
        "label": "Cohere Rerank 4 Fast (OpenRouter)",
        "provider": "openrouter",
        "model": "cohere/rerank-4-fast",
        "requires_api_key": True,
    },
    {
        "id": "llama_cpp:Qwen3-Reranker-0.6B-GGUF",
        "label": "Qwen3 Reranker 0.6B local",
        "provider": "llama_cpp",
        "model": "Qwen3-Reranker-0.6B-GGUF",
        "base_url": "http://localhost:8081/v1",
        "requires_api_key": False,
        "native": True,
    },
    {
        "id": "none",
        "label": "No reranker",
        "provider": "none",
        "model": "",
        "requires_api_key": False,
    },
]

class RetrievalConfigurationError(RuntimeError):
    """The present retrieval configuration cannot be read without data loss."""


def validate_chromadb_config(
    data: object, config_path: Path | None = None,
) -> dict[str, Any]:
    """Validate one complete Chroma identity through the runtime reader."""
    path = config_path or CHROMADB_CONFIG_PATH
    try:
        from orchestrator.embedding import validate_chromadb_config as validate
    except ImportError:  # pragma: no cover - direct-module import shim
        from embedding import validate_chromadb_config as validate
    return validate(data, path)


def _default_chromadb_config() -> dict[str, Any]:
    profile = DEFAULT_EMBEDDING_PROFILES[0]
    collections = dict(DEFAULT_COLLECTIONS)
    return {
        "_schema_version": 1,
        "embedder": {
            "profile_id": profile["id"],
            "provider": profile["provider"],
            "model": profile["model"],
            "dim": int(profile["dimensions"]),
            "base_url": profile["base_url"],
            "url": profile["base_url"],
        },
        "collections": collections,
        "collection_history": {
            logical: [physical] for logical, physical in collections.items()
        },
    }


def read_chromadb_config() -> dict[str, Any]:
    try:
        CHROMADB_CONFIG_PATH.lstat()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise RetrievalConfigurationError(
            f"Chroma configuration path is unreadable: {CHROMADB_CONFIG_PATH}: {exc}"
        ) from exc
    try:
        data = json.loads(CHROMADB_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RetrievalConfigurationError(
            f"Chroma configuration is present but unreadable: "
            f"{CHROMADB_CONFIG_PATH}: {exc}"
        ) from exc
    return validate_chromadb_config(data, CHROMADB_CONFIG_PATH)


def write_chromadb_config(data: dict[str, Any]) -> None:
    validate_chromadb_config(data, CHROMADB_CONFIG_PATH)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CHROMADB_CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(CHROMADB_CONFIG_PATH)


def _profile_id(provider: str, model: str) -> str:
    return f"{provider}:{model}"


def _profile_from_embedder(embedder: dict[str, Any]) -> dict[str, Any]:
    provider = (embedder.get("provider") or "ollama").strip() or "ollama"
    model = (embedder.get("model") or "bge-m3").strip() or "bge-m3"
    dim = int(embedder.get("dim") or embedder.get("dimensions") or infer_embedding_dim(model) or 1024)
    base_url = (
        embedder.get("base_url")
        or embedder.get("url")
        or ("https://openrouter.ai/api/v1" if provider == "openrouter" else "http://localhost:11434")
    )
    return {
        "id": embedder.get("profile_id") or _profile_id(provider, model),
        "label": embedder.get("label") or _label_for(provider, model),
        "provider": provider,
        "model": model,
        "dimensions": dim,
        "base_url": base_url,
        "requires_api_key": provider == "openrouter",
        "native": provider != "openrouter",
    }


def _default_reranker_base_url(provider: str) -> str:
    if provider in {"auto", "openrouter"}:
        return "https://openrouter.ai/api/v1"
    return "http://localhost:8081/v1"


def active_embedding_profile(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config if config is not None else read_chromadb_config()
    embedder = cfg.get("embedder") if isinstance(cfg.get("embedder"), dict) else {}
    if not embedder:
        return copy.deepcopy(DEFAULT_EMBEDDING_PROFILES[0])
    return _profile_from_embedder(embedder)


def active_reranker(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config if config is not None else read_chromadb_config()
    reranker = cfg.get("reranker") if isinstance(cfg.get("reranker"), dict) else {}
    if not reranker:
        return copy.deepcopy(DEFAULT_RERANKERS[0])
    provider = (reranker.get("provider") or "auto").strip() or "auto"
    model = (reranker.get("model") or "cohere/rerank-4-pro").strip()
    rid = reranker.get("id") or ("auto" if provider == "auto" else _profile_id(provider, model))
    known = option_by_id(list_reranker_options(), rid) or {}
    base_url = reranker.get("base_url") or known.get("base_url") or _default_reranker_base_url(provider)
    if provider == "auto" and base_url.startswith("http://localhost:"):
        base_url = _default_reranker_base_url(provider)
    return {
        "id": rid,
        "label": reranker.get("label") or known.get("label") or _label_for(provider, model),
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "requires_api_key": provider == "openrouter",
        "fallbacks": reranker.get("fallbacks") or ["llama_cpp:Qwen3-Reranker-0.6B-GGUF"],
    }


def infer_embedding_dim(model_id: str, description: str = "") -> int | None:
    model = (model_id or "").lower()
    if model in _KNOWN_DIMS:
        return _KNOWN_DIMS[model]
    if description:
        match = re.search(r"(\d{3,5})[-\s]?dimensional", description, re.I)
        if match:
            return int(match.group(1))
    return None


def _label_for(provider: str, model: str) -> str:
    if provider == "ollama":
        return f"{model} local (Ollama)"
    if provider == "openrouter":
        return f"{model} (OpenRouter)"
    if provider == "llama_cpp":
        return f"{model} local"
    return model or provider


def _openrouter_catalog_models(modality: str) -> list[dict[str, Any]]:
    if not OPENROUTER_CATALOG_PATH.exists():
        return []
    try:
        data = json.loads(OPENROUTER_CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    models = data.get("models") if isinstance(data, dict) else []
    if not isinstance(models, list):
        return []
    rows: list[dict[str, Any]] = []
    for row in models:
        if not isinstance(row, dict) or row.get("modality") != modality:
            continue
        rows.append(row)
    return rows


def list_embedding_options() -> list[dict[str, Any]]:
    options = [copy.deepcopy(p) for p in DEFAULT_EMBEDDING_PROFILES]
    seen = {p["id"] for p in options}
    for row in _openrouter_catalog_models("embedding"):
        model = row.get("id")
        if not model:
            continue
        pid = _profile_id("openrouter", model)
        if pid in seen:
            continue
        dim = infer_embedding_dim(model, row.get("description") or "")
        options.append({
            "id": pid,
            "label": row.get("display_name") or _label_for("openrouter", model),
            "provider": "openrouter",
            "model": model,
            "dimensions": dim,
            "base_url": "https://openrouter.ai/api/v1",
            "requires_api_key": True,
            "native": False,
            "pricing_per_million": row.get("pricing_per_million") or {},
            "context_length": row.get("context_length"),
            "disabled_reason": None if dim else "Embedding dimension is not known; run a probe before activation.",
        })
        seen.add(pid)
    return options


def list_reranker_options() -> list[dict[str, Any]]:
    options = [copy.deepcopy(p) for p in DEFAULT_RERANKERS]
    seen = {p["id"] for p in options}
    for row in _openrouter_catalog_models("rerank"):
        model = row.get("id")
        if not model:
            continue
        rid = _profile_id("openrouter", model)
        if rid in seen:
            continue
        options.append({
            "id": rid,
            "label": row.get("display_name") or _label_for("openrouter", model),
            "provider": "openrouter",
            "model": model,
            "base_url": "https://openrouter.ai/api/v1",
            "requires_api_key": True,
            "pricing_per_million": row.get("pricing_per_million") or {},
            "context_length": row.get("context_length"),
        })
        seen.add(rid)
    return options


def collections(config: dict[str, Any] | None = None) -> dict[str, str]:
    cfg = config if config is not None else read_chromadb_config()
    return {**DEFAULT_COLLECTIONS, **(cfg.get("collections") or {})}


def profile_collection_suffix(profile_id: str) -> str:
    raw = profile_id.replace("openrouter:", "").replace("ollama:", "")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_").lower()
    return slug[:64] or "embedding"


def target_collections_for_profile(profile_id: str) -> dict[str, str]:
    suffix = profile_collection_suffix(profile_id)
    return {
        "knowledge": f"knowledge_{suffix}",
        "conversations": f"conversations_{suffix}",
        "atomics": f"atomic_dedup_{suffix}",
        "conversations_incognito": f"conversations_incognito_{suffix}",
        "help": f"help_{suffix}",
        "msi_news_articles": f"msi_news_articles_{suffix}",
    }


def update_active_embedding_profile(profile: dict[str, Any], *,
                                    collection_names: dict[str, str] | None = None) -> dict[str, Any]:
    cfg = read_chromadb_config()
    if not cfg:
        cfg = _default_chromadb_config()
    cfg["embedder"] = {
        "profile_id": profile["id"],
        "provider": profile["provider"],
        "model": profile["model"],
        "dim": int(profile["dimensions"]),
        "base_url": profile.get("base_url") or (
            "https://openrouter.ai/api/v1"
            if profile["provider"] == "openrouter"
            else "http://localhost:11434"
        ),
        "url": profile.get("base_url") or "http://localhost:11434",
    }
    if collection_names:
        existing = cfg.get("collections") if isinstance(cfg.get("collections"), dict) else {}
        cfg["collections"] = {**existing, **collection_names}
    write_chromadb_config(cfg)
    return cfg


def update_active_reranker(reranker: dict[str, Any]) -> dict[str, Any]:
    cfg = read_chromadb_config()
    if not cfg:
        cfg = _default_chromadb_config()
    rid = reranker.get("id") or _profile_id(reranker.get("provider", "auto"), reranker.get("model", ""))
    known = option_by_id(list_reranker_options(), rid) or {}
    provider = reranker.get("provider") or known.get("provider") or "auto"
    model = reranker.get("model") or known.get("model") or ""
    cfg["reranker"] = {
        "id": rid,
        "label": reranker.get("label") or known.get("label") or _label_for(provider, model),
        "provider": provider,
        "model": model,
        "base_url": reranker.get("base_url") or known.get("base_url") or _default_reranker_base_url(provider),
        "fallbacks": reranker.get("fallbacks") or known.get("fallbacks") or ["llama_cpp:Qwen3-Reranker-0.6B-GGUF"],
    }
    write_chromadb_config(cfg)
    return cfg


def option_by_id(options: list[dict[str, Any]], option_id: str) -> dict[str, Any] | None:
    for option in options:
        if option.get("id") == option_id:
            return option
    return None


def openrouter_key_present() -> bool:
    if os.environ.get("OPENROUTER_API_KEY"):
        return True
    try:
        import keyring
        return bool(keyring.get_password("ora", "openrouter-api-key"))
    except Exception:
        return False


def snapshot() -> dict[str, Any]:
    cfg = read_chromadb_config()
    active_embedding = active_embedding_profile(cfg)
    active_rerank = active_reranker(cfg)
    target_collections = target_collections_for_profile(active_embedding["id"])
    return {
        "active_embedding": active_embedding,
        "active_reranker": active_rerank,
        "embedding_options": list_embedding_options(),
        "reranker_options": list_reranker_options(),
        "collections": collections(cfg),
        "suggested_target_collections": target_collections,
        "openrouter_key_present": openrouter_key_present(),
    }
