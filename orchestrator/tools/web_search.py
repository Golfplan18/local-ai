"""Web search via DuckDuckGo (no API key required).

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
"""

from __future__ import annotations

import sys


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


def web_search(query: str, max_results: int = 5) -> str:
    """Markdown-formatted DDG search results for tool-calling models."""
    try:
        results = _ddgs_text(query, max_results)
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
    """DDG search returning a list of ``{title, url, snippet}`` dicts.

    Result keys are normalised across DDG library versions: the
    ``ddgs`` package and the older ``duckduckgo_search`` package have
    used both ``href``/``body`` and ``url``/``snippet`` in different
    releases. This wrapper accepts either.

    Returns an empty list on no results or on DDG error. Errors are
    logged to stderr so the failure becomes inspectable — silent
    empty-on-error here would mean the Step 2.5 supplement loop runs
    against zero results with no signal that a network / rate-limit /
    library error occurred.
    """
    try:
        raw = _ddgs_text(query, max_results)
    except Exception as e:
        print(
            f"[web_search_structured] DDG error for query {query!r}: {e}",
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
