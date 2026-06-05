"""Web search — configurable cascade across Tavily, Brave, Exa, DuckDuckGo.

Two entry points:

  - ``web_search(query, max_results=5)`` returns a *formatted markdown
    string* — the original tool surface registered with the dispatcher
    so tool-calling models can invoke it as a tool. Preserved for
    backward compat.

  - ``web_search_structured(query, max_results=5)`` returns a *list of
    dicts* with ``title`` / ``url`` / ``snippet`` keys. Used by the
    Step 2.5 web-supplement loop and by any code path that needs to
    process search results programmatically — notably feeding the
    results through ``rag_engine.score_external_chunks`` for ranking
    and ``rag_engine.format_context_with_provenance`` for injection
    into the context package.

Registered providers:

  - Tavily — keyword + LLM-friendly snippets (``TAVILY_API_KEY``).
  - Brave  — keyword, larger free tier, survives MSI production burst
    that DDG silently rate-limits (``BRAVE_API_KEY``).
  - Exa    — neural / semantic retrieval (``EXA_API_KEY``); different
    shape from the keyword tiers, useful for concept-style queries.
    Runs as a co-equal semantic tier: when ``semantic_augment`` is enabled
    (the default for the Step-2 consultation and the model web_search tool),
    Exa results are interleaved round-robin with the keyword cascade
    (``_merge_interleave``) rather than appended after it, so its best hit is
    not buried below — or truncated past — the keyword results. Can still be
    pinned into ``search_cascade_order`` for a keyword-style fallback.
  - DDG    — keyless fallback. Always available.

Default cascade order: ``tavily → brave → ddg``. Configurable via the
``search_cascade_order`` field in ``config/routing-config.json``.

Providers without an API key configured are skipped silently. On a
provider error (HTTP, parse, timeout) — or an empty result from a
successful provider — the cascade falls through to the next tier and
logs to stderr. If every tier fails, is skipped, or returns empty,
``_search_text`` returns ``([], "none")`` and ``web_search_structured``
returns ``[]`` — callers (notably the Step-2 web consultation step)
treat that as a COVERAGE GAP rather than a fatal pipeline error.

Result shape is normalised to DDG-style keys (``title`` / ``href`` /
``body``) at the provider boundary so downstream consumers don't
branch on provider identity.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request


BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
TAVILY_ENDPOINT = "https://api.tavily.com/search"
EXA_ENDPOINT = "https://api.exa.ai/search"

_DEFAULT_CASCADE_ORDER = ("tavily", "brave", "ddg")
_ROUTING_CONFIG_PATH = os.path.expanduser(
    "~/ora/config/routing-config.json"
)


# ── Providers ────────────────────────────────────────────────────────


def _tavily_text(query: str, max_results: int) -> list[dict]:
    """Tavily Search API. POST JSON body, parse ``results[]``.

    Tavily's response shape: ``{"results": [{"title", "url", "content",
    "score"}, ...]}``. We re-emit DDG keys (``title``/``href``/``body``)
    so downstream stays uniform.

    Raises on HTTP / parse error so the cascade catches and falls through.
    """
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY not set")

    # Tavily caps at 20 per query; clamp.
    count = max(1, min(int(max_results), 20))
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": count,
        "search_depth": "basic",
    }
    req = urllib.request.Request(
        TAVILY_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Ora/1.0 (web_search via Tavily)",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    items = data.get("results") or []
    out: list[dict] = []
    for r in items[:count]:
        out.append({
            "title": r.get("title", ""),
            "href":  r.get("url", ""),
            "body":  r.get("content", ""),
        })
    return out


def _brave_text(query: str, max_results: int) -> list[dict]:
    """Brave Web Search API. Returns raw library-style dicts so the
    downstream normaliser in ``web_search_structured`` (and the markdown
    formatter in ``web_search``) sees a familiar shape.

    Brave's JSON shape: response["web"]["results"][] with title/url/description.
    We re-emit DDG's keys (``title``/``href``/``body``) so callers that read
    either key family keep working without branching.

    Raises on HTTP / parse error so the cascade catches and falls through.
    """
    api_key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("BRAVE_API_KEY not set")

    # Brave caps at 20 per query; clamp.
    count = max(1, min(int(max_results), 20))
    url = f"{BRAVE_ENDPOINT}?{urllib.parse.urlencode({'q': query, 'count': count})}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
            "User-Agent": "Ora/1.0 (web_search via Brave)",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        # Brave returns gzip when the client advertises it; urllib doesn't
        # auto-decompress unless we ask. Read raw + handle gzip if present.
        raw_bytes = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw_bytes = gzip.decompress(raw_bytes)
        data = json.loads(raw_bytes.decode("utf-8"))

    items = ((data.get("web") or {}).get("results") or [])
    out: list[dict] = []
    for r in items[:count]:
        out.append({
            "title": r.get("title", ""),
            "href":  r.get("url", ""),
            "body":  r.get("description", "") or r.get("extra_snippets", [""])[0],
        })
    return out


def _exa_text(query: str, max_results: int) -> list[dict]:
    """Exa Search API (neural / semantic). POST JSON body, parse ``results[]``.

    Exa returns documents with metadata only by default; we request
    ``contents.text`` with a 500-char cap so the cascade sees a body
    field comparable to Tavily/Brave snippets. Re-emits DDG keys
    (``title``/``href``/``body``) so downstream stays uniform.

    Raises on HTTP / parse error so the cascade catches and falls through.
    """
    api_key = os.environ.get("EXA_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("EXA_API_KEY not set")

    count = max(1, min(int(max_results), 20))
    payload = {
        "query": query,
        "numResults": count,
        "type": "auto",
        "contents": {"text": {"maxCharacters": 500}},
    }
    req = urllib.request.Request(
        EXA_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-api-key": api_key,
            "User-Agent": "Ora/1.0 (web_search via Exa)",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    items = data.get("results") or []
    out: list[dict] = []
    for r in items[:count]:
        out.append({
            "title": r.get("title", ""),
            "href":  r.get("url", ""),
            "body":  r.get("text", "") or "",
        })
    return out


def _ddgs_text(query: str, max_results: int) -> list[dict]:
    """Run a DDG text search and return the library's raw result dicts.

    Imports the DDG library lazily so an import failure becomes a
    runtime failure (with a clear log) rather than a module-load
    failure that breaks every downstream import.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    return list(DDGS().text(query, max_results=max_results))


# Provider registry: name → (env_var_name | None, fetcher_callable).
# env_var_name == None means the provider is keyless (DDG).
_PROVIDERS: dict[str, tuple[str | None, "callable"]] = {
    "tavily": ("TAVILY_API_KEY", _tavily_text),
    "brave":  ("BRAVE_API_KEY",  _brave_text),
    "exa":    ("EXA_API_KEY",    _exa_text),
    "ddg":    (None,             _ddgs_text),
}


# ── Cascade ordering ────────────────────────────────────────────────


_cached_cascade_order: tuple[str, ...] | None = None


def _load_cascade_order() -> tuple[str, ...]:
    """Read ``search_cascade_order`` from routing-config.json.

    Cached at module level; first call reads the file. Restart picks up
    config changes. Returns a tuple of valid provider names; unknown
    names are dropped with a stderr warning. Falls back to the default
    on any failure (file missing, parse error, field absent / wrong shape).
    """
    global _cached_cascade_order
    if _cached_cascade_order is not None:
        return _cached_cascade_order

    order = _DEFAULT_CASCADE_ORDER
    try:
        with open(_ROUTING_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        raw = cfg.get("search_cascade_order")
        if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
            valid = tuple(x for x in raw if x in _PROVIDERS)
            dropped = [x for x in raw if x not in _PROVIDERS]
            if dropped:
                print(
                    f"[web_search] Unknown provider(s) in search_cascade_order: "
                    f"{dropped} — ignored",
                    file=sys.stderr, flush=True,
                )
            if valid:
                order = valid
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        # Silent fall-through to default — routing-config may be absent
        # in test environments or temporarily broken during edits.
        pass

    _cached_cascade_order = order
    return order


def _reset_cascade_order_cache() -> None:
    """Test helper — clear the module-level cache so the next call re-reads."""
    global _cached_cascade_order
    _cached_cascade_order = None


# ── Semantic augmentation ───────────────────────────────────────────


_DEFAULT_SEMANTIC_PROVIDER = "exa"
_cached_semantic_augment: tuple[bool, str] | None = None


def _load_semantic_augment() -> tuple[bool, str]:
    """Read the ``semantic_augment`` block from routing-config.json.

    Returns ``(enabled, provider_name)``. When enabled, a caller that
    opts in (``semantic_augment=True``) runs the keyword cascade AND a
    provider-only semantic search, merging the two. Disabled-safe:
    returns ``(False, "exa")`` if the block is absent, malformed, or the
    config file is missing — so a clean install never augments until the
    operator turns it on.
    """
    global _cached_semantic_augment
    if _cached_semantic_augment is not None:
        return _cached_semantic_augment

    enabled, provider = False, _DEFAULT_SEMANTIC_PROVIDER
    try:
        with open(_ROUTING_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        block = cfg.get("semantic_augment")
        if isinstance(block, dict):
            enabled = bool(block.get("enabled", False))
            prov = block.get("provider")
            if isinstance(prov, str) and prov in _PROVIDERS:
                provider = prov
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    _cached_semantic_augment = (enabled, provider)
    return _cached_semantic_augment


def _reset_semantic_augment_cache() -> None:
    """Test helper — clear the semantic-augment config cache."""
    global _cached_semantic_augment
    _cached_semantic_augment = None


def _merge_interleave(primary: list[dict], secondary: list[dict]) -> list[dict]:
    """Round-robin merge of two result lists, deduped by URL.

    Unlike a plain concatenation (primary then secondary), this interleaves the
    two sources — ``primary[0]``, ``secondary[0]``, ``primary[1]``,
    ``secondary[1]``, … — so the semantic provider (Exa) is a *co-equal*
    discovery tier whose best hit lands at position 2 rather than after every
    keyword result (and thus past the point a ``max_results`` / char budget
    would cut it). Primary still leads each pair, preserving keyword priority
    within a tie. Dedup keeps the first occurrence of each URL.
    """
    from itertools import zip_longest
    seen: set[str] = set()
    out: list[dict] = []
    for a, b in zip_longest(primary, secondary):
        for r in (a, b):
            if r is None:
                continue
            url = (r.get("href") or r.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(r)
    return out


def _gather_raw(
    query: str, max_results: int, *, semantic_augment: bool = False,
) -> list[dict]:
    """Run the keyword cascade and, when ``semantic_augment`` is requested
    AND enabled in config AND the semantic provider is keyed, also run a
    provider-only semantic search and merge the two (dedup by URL).

    Returns raw provider dicts (``title`` / ``href`` / ``body``); callers
    normalise. Safe no-op whenever the semantic provider has no key — the
    semantic search is simply not run, so the result is exactly the
    keyword cascade. This is the gate that keeps no-key installs (and
    forks) on keyword-only behaviour with zero cost.
    """
    raw, _provider = _search_text(query, max_results)
    if not semantic_augment:
        return raw
    enabled, provider = _load_semantic_augment()
    if not enabled:
        return raw
    env_var = _PROVIDERS.get(provider, (None, None))[0]
    if not env_var or not os.environ.get(env_var, "").strip():
        return raw  # semantic provider not keyed → keyword-only no-op
    sem, _sp = _search_text(query, max_results, order=(provider,))
    if not sem:
        return raw
    merged = _merge_interleave(raw, sem)
    # Observability: how many semantic hits were genuinely new (not already
    # surfaced by the keyword cascade). Lets "is Exa actually contributing?"
    # be answered from the logs instead of guessed.
    raw_urls = {(r.get("href") or r.get("url") or "").strip() for r in raw}
    new_sem = sum(
        1 for r in sem
        if (r.get("href") or r.get("url") or "").strip() not in raw_urls
    )
    if new_sem:
        print(
            f"[web_search] semantic({provider}) contributed {new_sem} new "
            f"result(s) alongside {len(raw)} keyword result(s) for {query!r}",
            file=sys.stderr, flush=True,
        )
    return merged


# ── Cascade execution ───────────────────────────────────────────────


def _search_text(
    query: str, max_results: int, order: tuple[str, ...] | None = None,
) -> tuple[list[dict], str]:
    """Iterate the cascade, return first successful provider's results.

    Returns ``(results, provider_tag)``. ``provider_tag`` is the name of
    the provider that returned non-empty results; ``"none"`` when every
    tier failed, was skipped, or returned empty. An empty result from a
    successful provider is treated as a soft miss and the cascade
    continues to the next tier — a thin index or a free tier that returns
    empty-on-exhaustion should not dead-end the search.

    ``order`` overrides the configured cascade for this call — e.g.
    ``("exa",)`` to force a semantic-only search. Unknown names are
    dropped; an empty / all-invalid override falls back to the configured
    cascade. ``None`` (default) uses ``_load_cascade_order()``.

    Errors are logged to stderr so the cascade behavior is inspectable.
    """
    if order is None:
        order = _load_cascade_order()
    else:
        order = tuple(p for p in order if p in _PROVIDERS) or _load_cascade_order()
    for provider in order:
        env_var, fetcher = _PROVIDERS[provider]
        if env_var is not None and not os.environ.get(env_var, "").strip():
            # Silently skip providers without a configured key.
            continue
        try:
            results = fetcher(query, max_results)
        except Exception as e:
            print(
                f"[web_search] {provider} error for query {query!r}: {e} "
                f"— cascading to next tier",
                file=sys.stderr, flush=True,
            )
            continue
        if not results:
            # Empty (but successful) result is a soft miss, not a terminal
            # "no results" answer: a thin index or a free tier that returns
            # empty-on-exhaustion must not dead-end the cascade before the
            # paid / keyless tiers are tried. Fall through; only report
            # "none" when every tier is empty or errored.
            print(
                f"[web_search] {provider} returned no results for query {query!r} "
                f"— cascading to next tier",
                file=sys.stderr, flush=True,
            )
            continue
        return results, provider

    print(
        f"[web_search] All cascade tiers failed or skipped for query {query!r}",
        file=sys.stderr, flush=True,
    )
    return [], "none"


# ── Public entry points ─────────────────────────────────────────────


def web_search(query: str, max_results: int = 5, *, semantic_augment: bool = False) -> str:
    """Markdown-formatted search results for tool-calling models.

    Provider is auto-selected per the cascade order in routing-config.json
    (default: Tavily → Brave → DDG). When ``semantic_augment`` is set —
    and the feature is enabled in config with the semantic provider keyed
    — results from the semantic provider (e.g. Exa) are merged in. The
    model-facing tool wrapper opts in so the agentic loop benefits.
    """
    try:
        results = _gather_raw(query, max_results, semantic_augment=semantic_augment)
        if not results:
            return f"No results found for: {query}"
        output = []
        for i, r in enumerate(results, 1):
            output.append(f"{i}. {r.get('title', 'No title')}")
            output.append(f"   URL: {r.get('href', 'No URL')}")
            output.append(f"   {r.get('body', 'No snippet')}")
            output.append("")
        return "\n".join(output)
    except Exception as e:
        return f"Search error: {str(e)}"


def web_search_structured(
    query: str, max_results: int = 5, *, semantic_augment: bool = False,
) -> list[dict]:
    """Search returning a list of ``{title, url, snippet}`` dicts.

    Provider is auto-selected per the cascade order in routing-config.json
    (default: Tavily → Brave → DDG). Result keys are normalised across
    providers and library versions: Tavily uses ``url``/``content``, Brave
    uses ``url``/``description``, the legacy ``ddgs`` and
    ``duckduckgo_search`` packages have used both ``href``/``body`` and
    ``url``/``snippet`` in different releases. This wrapper normalises
    all of them to ``title``/``url``/``snippet``.

    When ``semantic_augment`` is set — and the feature is enabled in
    config with the semantic provider keyed — results from the semantic
    provider (e.g. Exa) are merged in. Step-2 web consultation opts in;
    claim verification does not (fact-checking wants keyword precision).

    Returns an empty list on no results or on provider error. Errors are
    logged to stderr so the failure becomes inspectable.
    """
    try:
        raw = _gather_raw(query, max_results, semantic_augment=semantic_augment)
    except Exception as e:
        print(
            f"[web_search_structured] cascade error for query {query!r}: {e}",
            file=sys.stderr, flush=True,
        )
        return []

    out: list[dict] = []
    for r in raw:
        url = r.get("href") or r.get("url") or ""
        if not url:
            continue
        out.append({
            "title":   r.get("title", ""),
            "url":     url,
            "snippet": r.get("body") or r.get("snippet") or "",
        })
    return out
