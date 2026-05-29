"""Web search — Brave (paid) preferred, DuckDuckGo (free) fallback.

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

Provider selection (2026-05-28): when ``BRAVE_API_KEY`` is set in the
environment (sourced from ``~/.config/ora/brave-api-key`` by ora.env),
queries route to Brave Search API. Brave survives the MSI production
burst (~400-700 queries/overnight pass) that DDG silently rate-limits.
When ``BRAVE_API_KEY`` is unset, falls back to free DDG. Result shape
is identical across providers so downstream consumers don't branch.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request


BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


def _brave_text(query: str, max_results: int) -> list[dict]:
    """Brave Web Search API. Returns raw library-style dicts so the
    downstream normaliser in ``web_search_structured`` (and the markdown
    formatter in ``web_search``) sees a familiar shape.

    Brave's JSON shape: response["web"]["results"][] with title/url/description.
    We re-emit DDG's keys (``title``/``href``/``body``) so callers that read
    either key family keep working without branching.

    Raises on HTTP / parse error so the caller's try/except logs it the
    same way DDG errors are logged.
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


def _search_text(query: str, max_results: int) -> tuple[list[dict], str]:
    """Dispatch to Brave when BRAVE_API_KEY is set, else DDG.

    Returns (results, provider_tag). provider_tag is "brave" or "ddg" —
    used by callers that want to log which provider answered.
    """
    if os.environ.get("BRAVE_API_KEY", "").strip():
        try:
            return _brave_text(query, max_results), "brave"
        except Exception as e:
            print(
                f"[web_search] Brave error for query {query!r}: {e} "
                f"— falling back to DDG",
                file=sys.stderr, flush=True,
            )
            # Fall through to DDG so a Brave outage doesn't kill the
            # pipeline. DDG may rate-limit, but partial is better than
            # nothing for non-burst single-query callers.
    return _ddgs_text(query, max_results), "ddg"


def web_search(query: str, max_results: int = 5) -> str:
    """Markdown-formatted search results for tool-calling models.

    Provider is auto-selected (Brave when BRAVE_API_KEY is set, else DDG).
    """
    try:
        results, _provider = _search_text(query, max_results)
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


def web_search_structured(query: str, max_results: int = 5) -> list[dict]:
    """Search returning a list of ``{title, url, snippet}`` dicts.

    Provider is auto-selected (Brave when BRAVE_API_KEY is set, else DDG).
    Result keys are normalised across providers and library versions:
    the legacy ``ddgs`` and ``duckduckgo_search`` packages have used both
    ``href``/``body`` and ``url``/``snippet`` in different releases, and
    Brave uses ``url``/``description``. This wrapper normalises all of
    them to ``title``/``url``/``snippet``.

    Returns an empty list on no results or on provider error. Errors are
    logged to stderr so the failure becomes inspectable.
    """
    try:
        raw, _provider = _search_text(query, max_results)
    except Exception as e:
        print(
            f"[web_search_structured] provider error for query {query!r}: {e}",
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
