"""Fetch a URL as clean markdown.

Cascade (``channel="auto"``):

    1. httpx + Trafilatura  — cheap, fast baseline.
    2. Playwright (chrome)  — handles JS-rendered pages.
    3. Jina Reader          — final fallback (``r.jina.ai/<url>``).

Each tier returns an acceptable result (markdown >= ``_MIN_USEFUL_CHARS``
and no error) or falls through. The caller can pin a tier with
``channel="httpx" | "local" | "api"`` (``local`` = Playwright, ``api`` =
Jina, matching the G1.6 brief's vocabulary).

Returns
-------
A dict shaped ``{url, markdown, title, channel, fetched_at}`` (ISO 8601
UTC). ``markdown`` is an empty string on hard failure; an ``error`` key
is set when a tier failed for an inspectable reason. Caller is the
dispatcher in ``orchestrator/dispatcher.py``; the dict gets
``json.dumps``-serialised before reaching the model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Minimum useful markdown length to consider a tier successful. Pages
# below this trigger escalation in the cascade. JS-rendered SPAs
# typically return a near-empty HTML shell that httpx accepts at the
# protocol layer but contains no real content.
_MIN_USEFUL_CHARS = 500

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 (Ora web_fetch)"
)

_HTTPX_TIMEOUT_SECONDS = 15
_PLAYWRIGHT_TIMEOUT_MS = 30_000
_JINA_TIMEOUT_SECONDS = 20


def web_fetch(
    url: str,
    channel: str = "auto",
    persist: bool = False,
) -> dict[str, Any]:
    """Retrieve ``url`` as clean markdown.

    Parameters
    ----------
    url : str
        Absolute http(s) URL.
    channel : str
        ``"auto"`` (default) runs the cascade. ``"httpx"`` / ``"local"`` /
        ``"api"`` pins a single tier.
    persist : bool
        ``False`` returns the markdown ephemerally. ``True`` is reserved
        for the Long-Form Document Processing path (G3.25) and currently
        raises ``NotImplementedError``.
    """
    if persist:
        raise NotImplementedError(
            "persist=True requires the Long-Form Document Processing "
            "framework — see G3.25 in vault/Working — Ora Setup and "
            "Refinement.md. The ephemeral path (persist=False) ships in "
            "G1.10 Phase 2."
        )

    if not url or not isinstance(url, str):
        return _error_result(url or "", "auto", "URL required")
    if not (url.startswith("http://") or url.startswith("https://")):
        return _error_result(url, "auto", f"Invalid URL scheme: {url}")

    if channel == "httpx":
        return _fetch_httpx(url)
    if channel == "local":
        return _fetch_playwright(url)
    if channel == "api":
        return _fetch_jina(url)
    if channel != "auto":
        return _error_result(url, channel, f"Unknown channel: {channel}")

    result = _fetch_httpx(url)
    if _is_acceptable(result):
        return result
    result = _fetch_playwright(url)
    if _is_acceptable(result):
        return result
    return _fetch_jina(url)


# ── Tier implementations ─────────────────────────────────────────────


def _fetch_httpx(url: str) -> dict[str, Any]:
    try:
        import httpx
    except ImportError:
        return _error_result(url, "httpx", "httpx not installed")
    try:
        import trafilatura
    except ImportError:
        return _error_result(url, "httpx", "trafilatura not installed")

    try:
        with httpx.Client(
            timeout=_HTTPX_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = client.get(url)
        if resp.status_code >= 400:
            return _error_result(url, "httpx", f"HTTP {resp.status_code}")
        return _trafilatura_to_result(resp.text, url, "httpx")
    except Exception as e:
        return _error_result(url, "httpx", str(e))


def _fetch_playwright(url: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _error_result(url, "local", "playwright not installed")
    try:
        import trafilatura
    except ImportError:
        return _error_result(url, "local", "trafilatura not installed")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page(user_agent=_USER_AGENT)
                page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=_PLAYWRIGHT_TIMEOUT_MS,
                )
                html = page.content()
            finally:
                browser.close()
        return _trafilatura_to_result(html, url, "local")
    except Exception as e:
        return _error_result(url, "local", str(e))


def _fetch_jina(url: str) -> dict[str, Any]:
    try:
        import httpx
    except ImportError:
        return _error_result(url, "api", "httpx not installed")

    jina_url = "https://r.jina.ai/" + url
    try:
        with httpx.Client(
            timeout=_JINA_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/markdown",
            },
        ) as client:
            resp = client.get(jina_url)
        if resp.status_code >= 400:
            return _error_result(url, "api", f"HTTP {resp.status_code}")
        text = resp.text or ""
        title = _jina_title(text)
        return {
            "url": url,
            "markdown": text,
            "title": title,
            "channel": "api",
            "fetched_at": _now(),
        }
    except Exception as e:
        return _error_result(url, "api", str(e))


# ── Helpers ──────────────────────────────────────────────────────────


def _trafilatura_to_result(
    html: str, url: str, channel: str,
) -> dict[str, Any]:
    """Run Trafilatura on raw HTML and build a result dict.

    Reuses Trafilatura's markdown extraction + metadata pass. A
    metadata-extraction failure is non-fatal: the result still carries
    the markdown body with ``title=None``.
    """
    import trafilatura

    markdown = trafilatura.extract(html, output_format="markdown") or ""
    title: str | None = None
    try:
        meta = trafilatura.extract_metadata(html)
        if meta is not None:
            title = getattr(meta, "title", None) or None
    except Exception:
        title = None

    return {
        "url": url,
        "markdown": markdown,
        "title": title,
        "channel": channel,
        "fetched_at": _now(),
    }


def _jina_title(text: str) -> str | None:
    """Jina Reader prefixes the markdown with ``Title: <title>``. Pull it."""
    if not text:
        return None
    first_line = text.split("\n", 1)[0].strip()
    prefix = "Title: "
    if first_line.startswith(prefix):
        return first_line[len(prefix):].strip() or None
    return None


def _is_acceptable(result: dict[str, Any]) -> bool:
    if not result or result.get("error"):
        return False
    markdown = result.get("markdown") or ""
    return len(markdown.strip()) >= _MIN_USEFUL_CHARS


def _error_result(
    url: str, channel: str, message: str,
) -> dict[str, Any]:
    return {
        "url": url,
        "markdown": "",
        "title": None,
        "channel": channel,
        "fetched_at": _now(),
        "error": message,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
