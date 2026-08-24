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

from dataclasses import dataclass
from datetime import datetime, timezone
import threading
from typing import Any
from urllib.parse import urlsplit
import zlib

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
# One shared cap for response bodies held by the HTTP and Jina tiers.  It is
# deliberately generous for ordinary articles, while ensuring a broken or
# hostile endpoint cannot grow an in-memory response without bound.
_MAX_CONTENT_BYTES = 8 * 1024 * 1024
_STREAM_CHUNK_BYTES = 64 * 1024
_JINA_READER_BASE = "https://r.jina.ai/"
_SUPPORTED_ACCEPT_ENCODINGS = "gzip, deflate"
_SUPPORTED_CONTENT_ENCODINGS = frozenset({"identity", "gzip", "deflate"})

_BROWSER_FETCH_LOCK = threading.Lock()

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
    if _is_terminal_result(result):
        return _record_fetch_read(result)
    result = _fetch_playwright(url)
    if _is_acceptable(result):
        return _record_fetch_read(result)
    if _is_terminal_result(result):
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
            headers={
                "User-Agent": _USER_AGENT,
                "Accept-Encoding": _SUPPORTED_ACCEPT_ENCODINGS,
            },
        ) as client:
            resp, final = _manual_httpx_get(client, url)
        status = resp.status_code
        headers = _filter_headers(resp.headers)
        unsupported_encoding = _response_unsupported_content_encoding(resp)
        if unsupported_encoding:
            return _unsupported_content_encoding_result(
                url, "httpx", unsupported_encoding,
                status_code=status, headers=headers,
                destination_classification="public",
                final_origin=final.origin,
            )
        if _response_content_limit_exceeded(resp):
            return _content_limit_result(
                url, "httpx", status_code=status, headers=headers,
                destination_classification="public",
                final_origin=final.origin,
            )
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
    except network_policy.NetworkPolicyError as e:
        return _policy_refusal_result(url, "httpx", str(e))
    except Exception as e:
        return _error_result(url, "httpx", str(e))


def _fetch_playwright(url: str) -> dict[str, Any]:
    """Run at most one heavy browser render in this process."""

    if not _BROWSER_FETCH_LOCK.acquire(blocking=False):
        result = _error_result(
            url, "local",
            "browser fetch busy: another browser-rendered fetch is in progress",
        )
        result["browser_busy"] = True
        result["destination_classification"] = "public-browser-busy"
        return result
    try:
        return _fetch_playwright_locked(url)
    finally:
        _BROWSER_FETCH_LOCK.release()


def _fetch_playwright_locked(url: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _error_result(url, "local", "playwright not installed")
    try:
        import trafilatura
    except ImportError:
        return _error_result(url, "local", "trafilatura not installed")

    policy_refusal: str | None = None
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
                    nonlocal policy_refusal
                    try:
                        network_policy.validate_browser_request(
                            route.request.url, contract,
                        )
                    except network_policy.NetworkPolicyError as exc:
                        policy_refusal = str(exc)
                        route.abort()
                        return
                    route.continue_()

                def route_websocket(websocket_route):
                    nonlocal policy_refusal
                    request_url = getattr(websocket_route, "url", "")
                    try:
                        network_policy.validate_browser_request(
                            request_url, contract,
                        )
                    except network_policy.NetworkPolicyError as exc:
                        policy_refusal = str(exc)
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
        if policy_refusal:
            return _policy_refusal_result(url, "local", policy_refusal)
        result = _trafilatura_to_result(html, url, "local")
        result["destination_classification"] = "public-browser-routed"
        return result
    except network_policy.NetworkPolicyError as e:
        return _policy_refusal_result(url, "local", str(e))
    except Exception as e:
        # route.abort() can make page.goto() raise after the route callback has
        # already recorded the policy refusal.  Preserve that stronger truth;
        # otherwise the auto cascade would mistake a refusal for a retryable
        # browser failure and forward the URL to Jina.
        if policy_refusal:
            return _policy_refusal_result(url, "local", policy_refusal)
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
    jina_url = _JINA_READER_BASE + destination.url
    try:
        with httpx.Client(
            timeout=_JINA_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/markdown",
                "Accept-Encoding": _SUPPORTED_ACCEPT_ENCODINGS,
            },
        ) as client:
            resp, _final = _manual_httpx_get(client, jina_url)
        unsupported_encoding = _response_unsupported_content_encoding(resp)
        if unsupported_encoding:
            result = _unsupported_content_encoding_result(
                url, "api", unsupported_encoding,
                status_code=resp.status_code,
                headers=_filter_headers(resp.headers),
                destination_classification="public-forwarded-to-jina",
                third_party_forwarding={
                    "forwarded": True,
                    "provider": "jina-reader",
                    "reason": reason,
                    "source_origin": destination.origin,
                },
            )
            return result
        if _response_content_limit_exceeded(resp):
            result = _content_limit_result(
                url, "api", status_code=resp.status_code,
                headers=_filter_headers(resp.headers),
                destination_classification="public-forwarded-to-jina",
                third_party_forwarding={
                    "forwarded": True,
                    "provider": "jina-reader",
                    "reason": reason,
                    "source_origin": destination.origin,
                },
            )
            return result
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
    except network_policy.NetworkPolicyError as e:
        result = _policy_refusal_result(
            url, "api", str(e),
            destination_classification="public-forwarded-to-jina",
            third_party_forwarding={
                "forwarded": True,
                "provider": "jina-reader",
                "reason": reason,
            },
        )
        return result
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
        if callable(getattr(client, "stream", None)):
            redirect_location = None
            with client.stream("GET", current.url) as response:
                status = response.status_code
                if status in {301, 302, 303, 307, 308}:
                    redirect_location = response.headers.get("location")
                else:
                    try:
                        body, exceeded = _read_stream_body(response)
                    except _UnsupportedContentEncoding as exc:
                        return _BoundedHTTPResponse(
                            status_code=status,
                            headers=_response_headers(response.headers),
                            content=b"",
                            encoding=getattr(response, "encoding", None),
                            unsupported_content_encoding=exc.encoding,
                        ), current
                    return _BoundedHTTPResponse(
                        status_code=status,
                        headers=_response_headers(response.headers),
                        content=body,
                        encoding=getattr(response, "encoding", None),
                        content_limit_exceeded=exceeded,
                    ), current
            if hop >= _MAX_REDIRECTS:
                raise network_policy.NetworkPolicyError("redirect limit exceeded")
            current = network_policy.validate_redirect(current, redirect_location)
            continue

        # Small test doubles and older callers may expose only .get().  The
        # production httpx.Client path above always streams; this compatibility
        # branch preserves the existing helper contract for those callers.
        response = client.get(current.url)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response, current
        if hop >= _MAX_REDIRECTS:
            raise network_policy.NetworkPolicyError("redirect limit exceeded")
        location = response.headers.get("location")
        current = network_policy.validate_redirect(current, location)
    raise network_policy.NetworkPolicyError("redirect limit exceeded")


@dataclass(frozen=True)
class _BoundedHTTPResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes
    encoding: str | None = None
    content_limit_exceeded: bool = False
    unsupported_content_encoding: str | None = None

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding or "utf-8", "replace")


def _response_headers(headers) -> dict[str, str]:
    try:
        return {str(key).lower(): str(value) for key, value in headers.items()}
    except Exception:
        return {}


def _response_content_limit_exceeded(response) -> bool:
    return getattr(response, "content_limit_exceeded", False) is True


def _response_unsupported_content_encoding(response) -> str | None:
    value = getattr(response, "unsupported_content_encoding", None)
    return value if isinstance(value, str) and value else None


def _header_int(headers, name: str) -> int | None:
    try:
        value = _header_value(headers, name)
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _header_value(headers, name: str) -> str | None:
    """Read one header from HTTPX headers or a small test-double mapping."""

    try:
        value = headers.get(name)
        if value is not None:
            return str(value)
    except Exception:
        pass
    try:
        for key, value in headers.items():
            if str(key).casefold() == name.casefold():
                return str(value)
    except Exception:
        pass
    return None


class _ContentLimitExceeded(Exception):
    """Internal signal that decoded or wire bytes crossed the shared cap."""


class _UnsupportedContentEncoding(Exception):
    """Internal signal that a response cannot be read by the bounded path."""

    def __init__(self, encoding: str):
        self.encoding = encoding
        super().__init__(
            f"unsupported or unsafe response content encoding: {encoding}",
        )


class _ZlibContentDecoder:
    """Incremental gzip/deflate decoder with a maximum output per call."""

    def __init__(self, encoding: str):
        self._encoding = encoding
        self._deflate_first_attempt = encoding == "deflate"
        self._decompressor = self._new_decompressor()

    def _new_decompressor(self, *, raw: bool = False):
        if self._encoding == "gzip":
            return zlib.decompressobj(zlib.MAX_WBITS | 16)
        return zlib.decompressobj(-zlib.MAX_WBITS if raw else zlib.MAX_WBITS)

    def _decode_with_current(self, data: bytes, max_output: int) -> bytes:
        output = bytearray()
        pending = data
        while pending:
            remaining = max_output - len(output)
            if remaining < 0:
                raise _ContentLimitExceeded
            prior_pending = pending
            piece = self._decompressor.decompress(pending, remaining + 1)
            output.extend(piece)
            if len(output) > max_output:
                raise _ContentLimitExceeded
            pending = self._decompressor.unconsumed_tail
            if pending == prior_pending and not piece:
                raise zlib.error("compressed stream made no progress")
        return bytes(output)

    def decode(self, data: bytes, max_output: int) -> bytes:
        if not data:
            return b""
        if self._deflate_first_attempt:
            self._deflate_first_attempt = False
            try:
                return self._decode_with_current(data, max_output)
            except zlib.error:
                # HTTPX accepts both zlib-wrapped and raw deflate streams.
                self._decompressor = self._new_decompressor(raw=True)
                return self._decode_with_current(data, max_output)
        return self._decode_with_current(data, max_output)

    def flush(self, max_output: int) -> bytes:
        piece = self._decompressor.flush(max_output + 1)
        if len(piece) > max_output:
            raise _ContentLimitExceeded
        return piece


def _content_decoders(headers) -> list:
    """Build only bounded decoders, refusing every other content coding."""

    value = _header_value(headers, "content-encoding")
    if not value:
        return []
    decoders = []
    for encoding in (part.strip().casefold() for part in value.split(",")):
        if not encoding or encoding == "identity":
            continue
        if encoding in _SUPPORTED_CONTENT_ENCODINGS - {"identity"}:
            decoders.append(_ZlibContentDecoder(encoding))
            continue
        raise _UnsupportedContentEncoding(encoding)
    # HTTP content codings are applied left-to-right and removed right-to-left.
    return list(reversed(decoders))


def _append_bounded(existing: bytes, piece: bytes, max_output: int) -> bytes:
    if len(existing) + len(piece) > max_output:
        raise _ContentLimitExceeded
    return existing + piece


def _read_stream_body(response) -> tuple[bytes, bool]:
    """Read at most the shared cap without unbounded decompressed materialization."""

    headers = getattr(response, "headers", {}) or {}
    raw_iterator = getattr(response, "iter_raw", None)
    if callable(raw_iterator):
        decoders = _content_decoders(headers)
    else:
        # Compatibility response doubles may expose only iter_bytes(), which
        # is already decoded.  Still reject optional/unknown encodings rather
        # than silently treating them as identity.
        _content_decoders(headers)
        decoders = []
    declared = _header_int(headers, "content-length")
    if declared is not None and declared > _MAX_CONTENT_BYTES:
        return b"", True

    if callable(raw_iterator):
        iterator = raw_iterator
    else:
        # Compatibility for small response doubles.  Production HTTPX
        # responses always expose iter_raw(); iter_bytes() is already decoded.
        iterator = response.iter_bytes
        decoders = []
    try:
        chunks = iterator(chunk_size=_STREAM_CHUNK_BYTES)
    except TypeError:
        chunks = iterator()
    retained = bytearray()
    wire_bytes = 0
    try:
        for chunk in chunks:
            if not chunk:
                continue
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8", "replace")
            wire_bytes += len(chunk)
            if wire_bytes > _MAX_CONTENT_BYTES:
                return b"", True
            decoded = chunk
            remaining = _MAX_CONTENT_BYTES - len(retained)
            for decoder in decoders:
                decoded = decoder.decode(decoded, remaining)
                if len(decoded) > remaining:
                    raise _ContentLimitExceeded
            if len(decoded) > remaining:
                raise _ContentLimitExceeded
            retained.extend(decoded)

        # Match HTTPX's MultiDecoder flush order: the output flushed by the
        # inner decoder is fed through each outer decoder in sequence.
        pending = b""
        for decoder in decoders:
            remaining = _MAX_CONTENT_BYTES - len(retained)
            pending = decoder.decode(pending, remaining)
            pending = _append_bounded(
                pending, decoder.flush(remaining - len(pending)), remaining,
            )
        if len(pending) > _MAX_CONTENT_BYTES - len(retained):
            raise _ContentLimitExceeded
        retained.extend(pending)
    except _ContentLimitExceeded:
        return b"", True
    return bytes(retained), False


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


def _content_limit_result(
    url: str,
    channel: str,
    *,
    status_code: int | None = None,
    headers: dict | None = None,
    destination_classification: str | None = None,
    final_origin: str | None = None,
    third_party_forwarding: dict | None = None,
) -> dict[str, Any]:
    result = _error_result(
        url,
        channel,
        f"Response exceeded the shared content cap of {_MAX_CONTENT_BYTES} bytes",
    )
    result["content_limit_exceeded"] = True
    result["content_limit_bytes"] = _MAX_CONTENT_BYTES
    result["status_code"] = status_code
    result["headers"] = headers
    if destination_classification is not None:
        result["destination_classification"] = destination_classification
    if final_origin is not None:
        result["final_origin"] = final_origin
    if third_party_forwarding is not None:
        result["third_party_forwarding"] = third_party_forwarding
    return result


def _unsupported_content_encoding_result(
    url: str,
    channel: str,
    encoding: str,
    *,
    status_code: int | None = None,
    headers: dict | None = None,
    destination_classification: str | None = None,
    final_origin: str | None = None,
    third_party_forwarding: dict | None = None,
) -> dict[str, Any]:
    result = _error_result(
        url,
        channel,
        (
            f"Unsupported or unsafe response content encoding {encoding!r}; "
            "refused before body expansion (bounded support: identity, "
            "gzip, deflate)"
        ),
    )
    result["unsupported_content_encoding"] = encoding
    result["status_code"] = status_code
    result["headers"] = headers
    if destination_classification is not None:
        result["destination_classification"] = destination_classification
    if final_origin is not None:
        result["final_origin"] = final_origin
    if third_party_forwarding is not None:
        result["third_party_forwarding"] = third_party_forwarding
    return result


def _policy_refusal_result(
    url: str,
    channel: str,
    message: str,
    *,
    destination_classification: str = "refused-destination-policy",
    third_party_forwarding: dict | None = None,
) -> dict[str, Any]:
    result = _error_result(
        url, channel, network_policy.redact_sensitive_text(message),
    )
    result["policy_refusal"] = True
    result["destination_classification"] = destination_classification
    if third_party_forwarding is not None:
        result["third_party_forwarding"] = third_party_forwarding
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


def _is_terminal_result(result: dict[str, Any]) -> bool:
    """Results that must not be hidden by an automatic fallback tier."""

    return bool(result and (
        result.get("content_limit_exceeded")
        or result.get("policy_refusal")
    ))


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
