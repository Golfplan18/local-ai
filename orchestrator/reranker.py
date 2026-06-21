"""Reranking adapter for Ora retrieval.

Reranking is intentionally independent of the embedding profile. Embeddings
find a candidate set; the reranker reads the query plus candidate text and
reorders those candidates for this one request. That makes it safe to use
Cohere via OpenRouter when online and fall back to a local Qwen reranker
when the API path is unavailable.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

try:  # pragma: no cover - import shim
    import retrieval_config
except ImportError:  # pragma: no cover
    from orchestrator import retrieval_config


DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1"
DEFAULT_LOCAL_RERANK_URL = "http://localhost:8081/v1"
DEFAULT_MAX_DOC_CHARS = int(os.environ.get("ORA_RERANK_MAX_DOC_CHARS", "8000"))
DEFAULT_LOCAL_TIMEOUT = float(os.environ.get("ORA_LOCAL_RERANK_TIMEOUT", "2.0"))


def _openrouter_api_key() -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    try:
        import keyring

        return keyring.get_password("ora", "openrouter-api-key")
    except Exception:
        return None


def _candidate_document(chunk: dict[str, Any]) -> str:
    doc = chunk.get("document") or chunk.get("text") or ""
    doc = str(doc)
    if len(doc) > DEFAULT_MAX_DOC_CHARS:
        return doc[:DEFAULT_MAX_DOC_CHARS]
    return doc


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    attempts: int = 2,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    all_headers = {"Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers=all_headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                detail = ""
            last_err = RuntimeError(f"HTTP {exc.code}: {detail}")
        except Exception as exc:
            last_err = exc
        if attempt < attempts:
            time.sleep(attempt)
    assert last_err is not None
    raise last_err


def _normalise_results(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("results")
    if rows is None:
        rows = data.get("data")
    if not isinstance(rows, list):
        raise RuntimeError("reranker returned no result list")
    normalised: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        if idx is None:
            idx = row.get("document_index")
        score = row.get("relevance_score")
        if score is None:
            score = row.get("score")
        if idx is None or score is None:
            continue
        normalised.append({"index": int(idx), "score": float(score)})
    if not normalised:
        raise RuntimeError("reranker returned no usable scores")
    normalised.sort(key=lambda r: r["score"], reverse=True)
    return normalised


def _call_openrouter(
    *,
    query: str,
    documents: list[str],
    model: str,
    base_url: str,
    top_n: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    key = _openrouter_api_key()
    if not key:
        raise RuntimeError("OpenRouter key missing")
    payload = {
        "model": model,
        "query": query,
        "documents": documents,
        "top_n": top_n,
    }
    data = _post_json(
        base_url.rstrip("/") + "/rerank",
        payload,
        headers={
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://ora.local",
            "X-Title": "Ora",
        },
        timeout=45,
        attempts=2,
    )
    return _normalise_results(data), {
        "provider": "openrouter",
        "model": model,
        "usage": data.get("usage") or {},
    }


def _call_local_llama_cpp(
    *,
    query: str,
    documents: list[str],
    model: str,
    base_url: str,
    top_n: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = {
        "model": model,
        "query": query,
        "documents": documents,
        "top_n": top_n,
    }
    base = base_url.rstrip("/")
    errors: list[str] = []
    if base.endswith("/v1"):
        urls = [base + "/rerank", base[:-3] + "/rerank"]
    else:
        urls = [base + "/rerank", base + "/v1/rerank"]
    for url in urls:
        try:
            data = _post_json(url, payload, timeout=DEFAULT_LOCAL_TIMEOUT, attempts=1)
            return _normalise_results(data), {
                "provider": "llama_cpp",
                "model": model,
                "usage": data.get("usage") or {},
            }
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("; ".join(errors))


def _provider_chain(active: dict[str, Any]) -> list[dict[str, Any]]:
    provider = active.get("provider") or "auto"
    if provider == "none":
        return []
    if provider == "auto":
        chain: list[dict[str, Any]] = []
        if retrieval_config.openrouter_key_present():
            chain.append({
                "provider": "openrouter",
                "model": active.get("model") or "cohere/rerank-4-pro",
                "base_url": DEFAULT_OPENROUTER_URL,
            })
        for rid in active.get("fallbacks") or ["llama_cpp:Qwen3-Reranker-0.6B-GGUF"]:
            opt = retrieval_config.option_by_id(
                retrieval_config.list_reranker_options(), rid
            )
            if opt:
                chain.append(opt)
        return chain
    return [active]


def rerank_chunks(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    top_n: int | None = None,
    active: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return reranked chunks plus a trace dict.

    On every failure path the original chunk order is returned. Reranking
    should improve retrieval quality, never blank the RAG package.
    """
    if os.environ.get("ORA_RERANK_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        return chunks, {"status": "disabled"}
    if not query or not chunks:
        return chunks, {"status": "skipped", "reason": "empty_query_or_chunks"}

    active = active or retrieval_config.active_reranker()
    chain = _provider_chain(active)
    if not chain:
        return chunks, {"status": "disabled", "reason": "no_reranker"}

    documents = [_candidate_document(chunk) for chunk in chunks]
    limit = min(int(top_n or len(chunks)), len(chunks))
    failures: list[dict[str, str]] = []
    for option in chain:
        provider = option.get("provider")
        model = option.get("model") or ""
        base_url = option.get("base_url") or (
            DEFAULT_OPENROUTER_URL if provider == "openrouter" else DEFAULT_LOCAL_RERANK_URL
        )
        try:
            if provider == "openrouter":
                scores, trace = _call_openrouter(
                    query=query,
                    documents=documents,
                    model=model,
                    base_url=base_url,
                    top_n=limit,
                )
            elif provider == "llama_cpp":
                scores, trace = _call_local_llama_cpp(
                    query=query,
                    documents=documents,
                    model=model,
                    base_url=base_url,
                    top_n=limit,
                )
            else:
                continue
        except Exception as exc:
            failures.append({
                "provider": str(provider),
                "model": str(model),
                "error": str(exc)[:500],
            })
            continue

        seen: set[int] = set()
        reranked: list[dict[str, Any]] = []
        for row in scores:
            idx = row["index"]
            if idx < 0 or idx >= len(chunks) or idx in seen:
                continue
            seen.add(idx)
            item = dict(chunks[idx])
            item["rerank_score"] = row["score"]
            item["rerank_provider"] = trace["provider"]
            item["rerank_model"] = trace["model"]
            reranked.append(item)
        for idx, chunk in enumerate(chunks):
            if idx not in seen:
                reranked.append(chunk)
        trace.update({
            "status": "reranked",
            "candidates": len(chunks),
            "returned": len(reranked),
            "failures": failures,
        })
        return reranked, trace

    return chunks, {
        "status": "fallback_original_order",
        "reason": "all_rerankers_failed",
        "failures": failures,
    }


__all__ = ["rerank_chunks"]
