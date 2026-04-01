"""Web search tool using DuckDuckGo (no API key required)."""

def web_search(query: str, max_results: int = 5) -> str:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

    try:
        results = list(DDGS().text(query, max_results=max_results))
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
