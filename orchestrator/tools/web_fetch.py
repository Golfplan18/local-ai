"""Fetch a URL as clean markdown.

Cascade (``channel="auto"``):

    1. httpx + Trafilatura  — cheap, fast baseline.
    2. Playwright (managed Chromium) — handles JS-rendered pages.
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
from urllib.parse import urlsplit

try:
    import network_policy
except ImportError:  # pragma: no cover
    from orchestrator import network_policy

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
_MAX_REDIRECTS = 5

# Execution Review Phase 8 Chunk C (§4): the response headers a deploy_probe may
# inspect (staleness / cache state). Whitelisted so an event never carries an
# arbitrary header set.
_RESP_HEADER_WHITELIST = ("last-modified", "age", "cache-control",
                          "cf-cache-status", "etag", "content-type",
                          "content-length")


def web_fetch(
    url: str,
    channel: str = "auto",
    persist: bool = False,
    *,
    raw: bool = False,
    timeout_s: float | None = None,
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
    raw : bool
        Execution Review Phase 8 Chunk C: httpx tier ONLY. Skip Trafilatura
        extraction (so an XML sitemap/feed body survives instead of extracting
        to nothing and cascading), and return the origin ``status_code`` even on
        a ≥400 response (so a probe can distinguish FAIL from INDETERMINATE).
        Not a bypass of any safety — extraction is a readability transform.
    timeout_s : float | None
        Per-call timeout override for the httpx tier (default 15s).
    """
    if persist:
        raise NotImplementedError(
            "persist=True requires the Long-Form Document Processing "
            "framework — see G3.25 in vault/Working — Ora Setup and "
            "Refinement.md. The ephemeral path (persist=False) ships in "
            "G1.10 Phase 2."
        )

    try:
        destination = network_policy.validate_public_url(url)
    except network_policy.NetworkPolicyError as exc:
        result = _error_result(
            network_policy.safe_url_label(str(url or "")), "auto", str(exc),
        )
        result["destination_classification"] = "refused-non-public"
        result["third_party_forwarding"] = {
            "forwarded": False,
            "provider": "jina-reader",
            "reason": "invalid-destination",
        }
        return _record_fetch_read(result)
    url = destination.url

    if channel == "httpx":
        return _record_fetch_read(_fetch_httpx(url, raw=raw, timeout_s=timeout_s))
    if channel == "local":
        return _record_fetch_read(_fetch_playwright(url))
    if channel == "api":
        if not destination.third_party_safe:
            return _record_fetch_read(_third_party_refusal(url, explicit=True))
        return _record_fetch_read(_fetch_jina(url, reason="explicit-request"))
    if channel != "auto":
        return _error_result(url, channel, f"Unknown channel: {channel}")

    # auto cascade: extraction wanted (raw is a pinned-httpx affordance).
    result = _fetch_httpx(url, timeout_s=timeout_s)
    if _is_acceptable(result):
        return _record_fetch_read(result)
    result = _fetch_playwright(url)
    if _is_acceptable(result):
        return _record_fetch_read(result)
    if not destination.third_party_safe:
        return _record_fetch_read(_third_party_refusal(url, explicit=False))
    return _record_fetch_read(_fetch_jina(url, reason="automatic-fallback"))


def _filter_headers(resp_headers) -> dict:
    """Whitelisted response headers only (never an arbitrary set on an event)."""
    out: dict = {}
    try:
        for h in _RESP_HEADER_WHITELIST:
            v = resp_headers.get(h)
            if v is not None:
                out[h] = str(v)
    except Exception:
        pass
    return out


def _record_fetch_read(result: dict[str, Any]) -> dict[str, Any]:
    """Execution Review Phase 8 (Chunk A §2.3) LIBRARY GUARD: record EVERY
    fetch as a ``web_fetch`` tool-event — successful ones with the sanitized
    URL, content length, and a CONTENT-ONLY hash (sha256 of the markdown
    body — stable across identical fetches, unlike hashing a serialized dict
    with a timestamp in it); FAILED ones with ``exit.ok: false`` (egress
    happened even when every tier errored — the observation layer never
    pretends the contact didn't happen; risk_gate ignores non-ok reads for
    the source signal). Suppressed inside a dispatcher-recording context.
    Import-guarded + never-raises; always returns ``result`` unchanged."""
    try:
        if not isinstance(result, dict):
            return result
        try:
            import tool_events as _te
        except ImportError:  # pragma: no cover
            from orchestrator import tool_events as _te
        if _te.library_recording_suppressed():
            return result
        safe_url = _te.sanitize_url(result.get("url", ""))
        forwarding = result.get("third_party_forwarding")
        forwarding = dict(forwarding) if isinstance(forwarding, dict) else None
        classification = str(
            result.get("destination_classification") or "unknown",
        )[:80]
        if result.get("error"):
            _te.record_web_reads(
                "web_fetch",
                [{"what": safe_url, "where": "network"}],
                args_redacted={"url": safe_url,
                               "channel": result.get("channel", "")},
                exit_ok=False, exit_reason=str(result.get("error", ""))[:120],
                destination_classification=classification,
                third_party_forwarding=forwarding)
            return result
        import hashlib
        markdown = result.get("markdown") or ""
        _te.record_web_reads("web_fetch", [{
            "what": safe_url, "where": "network", "chars": len(markdown),
            "content_hash": hashlib.sha256(
                markdown.encode("utf-8", "replace")).hexdigest()[:16],
        }], args_redacted={"url": safe_url,
                           "channel": result.get("channel", "")},
            destination_classification=classification,
            third_party_forwarding=forwarding)
    except Exception:
        pass
    return result


# ── Tier implementations ─────────────────────────────────────────────


def _fetch_httpx(url: str, *, raw: bool = False,
                 timeout_s: float | None = None) -> dict[str, Any]:
    try:
        import httpx
    except ImportError:
        return _error_result(url, "httpx", "httpx not installed")
    if not raw:
        try:
            import trafilatura  # noqa: F401
        except ImportError:
            return _error_result(url, "httpx", "trafilatura not installed")

    timeout = timeout_s if timeout_s is not None else _HTTPX_TIMEOUT_SECONDS
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp, final = _manual_httpx_get(client, url)
        status = resp.status_code
        headers = _filter_headers(resp.headers)
        if raw:
            # RAW mode (Phase 8 Chunk C): never collapse ≥400 into an error that
            # loses the status — a probe needs to SEE 403/404 to decide
            # FAIL-vs-INDETERMINATE. Return the body + status + headers as-is.
            return {
                "url": url, "markdown": resp.text or "", "title": None,
                "channel": "httpx", "fetched_at": _now(),
                "status_code": status, "headers": headers,
                "destination_classification": "public",
                "final_origin": final.origin,
            }
        if status >= 400:
            r = _error_result(url, "httpx", f"HTTP {status}")
            r["status_code"] = status
            r["headers"] = headers
            return r
        result = _trafilatura_to_result(
            resp.text, url, "httpx", status_code=status, headers=headers,
        )
        result["destination_classification"] = "public"
        result["final_origin"] = final.origin
        return result
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
        contract = network_policy.BrowserNetworkContract(
            "public",
            network_policy.validate_public_url(url).url,
            origin=network_policy.validate_public_url(url).origin,
        )
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=_USER_AGENT,
                    service_workers="block",
                )
                if not hasattr(context, "route_web_socket"):
                    return _error_result(
                        url, "local",
                        "browser tier refused: WebSocket routing is unavailable",
                    )

                def route_request(route):
                    try:
                        network_policy.validate_browser_request(
                            route.request.url, contract,
                        )
                    except network_policy.NetworkPolicyError:
                        route.abort()
                        return
                    route.continue_()

                def route_websocket(websocket_route):
                    request_url = getattr(websocket_route, "url", "")
                    try:
                        network_policy.validate_browser_request(
                            request_url, contract,
                        )
                    except network_policy.NetworkPolicyError:
                        close = getattr(websocket_route, "close", None)
                        if callable(close):
                            close(code=1008, reason="destination refused")
                        return
                    connect = getattr(websocket_route, "connect_to_server", None)
                    if callable(connect):
                        connect()

                context.route("**/*", route_request)
                context.route_web_socket("**/*", route_websocket)
                page = context.new_page()
                page.goto(
                    contract.initial_url,
                    wait_until="networkidle",
                    timeout=_PLAYWRIGHT_TIMEOUT_MS,
                )
                html = page.content()
            finally:
                browser.close()
        result = _trafilatura_to_result(html, url, "local")
        result["destination_classification"] = "public-browser-routed"
        return result
    except Exception as e:
        return _error_result(url, "local", str(e))


def _fetch_jina(url: str, *, reason: str = "explicit-request") -> dict[str, Any]:
    try:
        import httpx
    except ImportError:
        result = _error_result(url, "api", "httpx not installed")
        result["destination_classification"] = "public-not-forwarded"
        result["third_party_forwarding"] = {
            "forwarded": False, "provider": "jina-reader",
            "reason": "provider-unavailable",
        }
        return result

    try:
        destination = network_policy.validate_public_url(url)
    except network_policy.NetworkPolicyError as exc:
        result = _error_result(network_policy.safe_url_label(url), "api", str(exc))
        result["destination_classification"] = "refused-non-public"
        result["third_party_forwarding"] = {
            "forwarded": False, "provider": "jina-reader",
            "reason": "invalid-destination",
        }
        return result
    if not destination.third_party_safe:
        return _third_party_refusal(url, explicit=True)
    jina_url = "https://r.jina.ai/" + destination.url
    try:
        with httpx.Client(
            timeout=_JINA_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/markdown",
            },
        ) as client:
            resp, _final = _manual_httpx_get(client, jina_url)
        if resp.status_code >= 400:
            result = _error_result(url, "api", f"HTTP {resp.status_code}")
            result["destination_classification"] = "public-forwarded-to-jina"
            result["third_party_forwarding"] = {
                "forwarded": True, "provider": "jina-reader", "reason": reason,
            }
            return result
        text = resp.text or ""
        title = _jina_title(text)
        return {
            "url": url,
            "markdown": text,
            "title": title,
            "channel": "api",
            "fetched_at": _now(),
            "status_code": None,
            "headers": None,
            "destination_classification": "public-forwarded-to-jina",
            "third_party_forwarding": {
                "forwarded": True,
                "provider": "jina-reader",
                "reason": reason,
                "source_origin": destination.origin,
            },
        }
    except Exception as e:
        result = _error_result(
            url, "api", network_policy.redact_sensitive_text(e),
        )
        result["destination_classification"] = "public-forwarded-to-jina"
        result["third_party_forwarding"] = {
            "forwarded": True, "provider": "jina-reader", "reason": reason,
        }
        return result


# ── Helpers ──────────────────────────────────────────────────────────


def _manual_httpx_get(client, url: str):
    """GET with bounded, per-hop public validation and no implicit redirects."""

    current = network_policy.validate_public_url(url)
    for hop in range(_MAX_REDIRECTS + 1):
        # Re-resolve immediately before each effect, including the initial hop.
        current = network_policy.validate_public_url(current.url)
        response = client.get(current.url)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response, current
        if hop >= _MAX_REDIRECTS:
            raise network_policy.NetworkPolicyError("redirect limit exceeded")
        location = response.headers.get("location")
        current = network_policy.validate_redirect(current, location)
    raise network_policy.NetworkPolicyError("redirect limit exceeded")


def _third_party_refusal(url: str, *, explicit: bool) -> dict[str, Any]:
    result = _error_result(
        network_policy.safe_url_label(url),
        "api",
        (
            "explicit Jina forwarding refused for a credential-bearing, "
            "signed, or sensitive-query URL"
            if explicit else
            "automatic Jina fallback skipped for a credential-bearing, "
            "signed, or sensitive-query URL"
        ),
    )
    result["destination_classification"] = "public-not-forwardable"
    result["third_party_forwarding"] = {
        "forwarded": False,
        "provider": "jina-reader",
        "reason": "sensitive-url",
    }
    return result


def _trafilatura_to_result(
    html: str, url: str, channel: str,
    *, status_code: int | None = None, headers: dict | None = None,
) -> dict[str, Any]:
    """Run Trafilatura on raw HTML and build a result dict.

    Reuses Trafilatura's markdown extraction + metadata pass. A
    metadata-extraction failure is non-fatal: the result still carries
    the markdown body with ``title=None``. ``status_code``/``headers`` are
    populated on the httpx tier (Phase 8 Chunk C), ``None`` elsewhere.
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
        "status_code": status_code,
        "headers": headers,
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
        "status_code": None,
        "headers": None,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
