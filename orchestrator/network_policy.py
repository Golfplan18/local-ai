"""Stateless outbound destination validation for model/provider-controlled I/O.

This module owns destination policy only.  It does not proxy traffic, retain
state, or choose transport.  Callers validate immediately before each HTTP,
HTTPS, WebSocket, or redirect effect and may continue using the process's
ordinary HTTP(S)/ALL_PROXY and NO_PROXY transport settings.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import ipaddress
import re
import socket
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit, urlunsplit
import urllib.error
import urllib.request


class NetworkPolicyError(ValueError):
    """A destination cannot cross the public-network boundary."""


_HTTP_SCHEMES = frozenset({"http", "https"})
_WS_SCHEMES = frozenset({"ws", "wss"})
_PUBLIC_SEARCH_QUERY_KEYS = frozenset({
    "q", "query", "s", "search", "search_query", "keyword", "keywords",
    "term", "terms", "text", "category", "categories", "tag", "tags",
    "topic", "section",
})
_PUBLIC_PAGINATION_QUERY_KEYS = frozenset({
    "p", "page", "page_num", "page_number", "pagenum", "pagenumber",
    "offset", "limit", "start", "count", "per_page", "perpage",
    "page_size", "pagesize",
})
_PUBLIC_PRESENTATION_QUERY_KEYS = frozenset({
    "sort", "order", "dir", "direction", "view", "format", "lang",
    "language", "locale",
})
_PUBLIC_FORWARDABLE_QUERY_KEYS = (
    _PUBLIC_SEARCH_QUERY_KEYS
    | _PUBLIC_PAGINATION_QUERY_KEYS
    | _PUBLIC_PRESENTATION_QUERY_KEYS
)
_SENSITIVE_QUERY_VALUE = re.compile(
    r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)|"
    r"(?i:\b(?:ssn|social[-_ ]?security|dob|date[-_ ]?of[-_ ]?birth)\b"
    r"[=:][^&\s]+)",
)
_CREDENTIAL_VALUE = re.compile(
    r"(?i)(?:\bbearer\s+[a-z0-9._~+/=-]+\b|"
    r"\b(?:api[_ -]?key|auth(?:orization)?|credential|jwt|password|"
    r"secret|session|sig(?:nature)?|signed|token)\s*[:=]\s*[^\s&]+)"
)
_JWT_VALUE = re.compile(r"^ey[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}$", re.IGNORECASE)
_CREDENTIAL_PREFIX_VALUE = re.compile(
    r"(?i)^(?:akia|asia|aiza|ghp_|github_pat_|rk_live_|sk[-_]|xox[a-z]-|ya29\.)"
)
_EMAIL_VALUE = re.compile(r"(?i)^[^\s@]+@[^\s@]+\.[^\s@]+$")
_SSN_VALUE = re.compile(r"^\d{3}-\d{2}-\d{4}$")
_OPAQUE_HEX_VALUE = re.compile(r"^[a-f0-9]{24,}$", re.IGNORECASE)
_OPAQUE_TOKEN_ALPHABET = re.compile(r"^[A-Za-z0-9._~+/=-]+$")
_CONTROL_OR_SPACE = re.compile(r"[\x00-\x20\x7f]")
_URL_IN_TEXT = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
_BEARER_IN_TEXT = re.compile(r"(?i)\b(?:bearer|token)\s+[A-Za-z0-9._~+/=-]+")

OPENROUTER_ORIGIN = "https://openrouter.ai"
OPENROUTER_API_BASE = OPENROUTER_ORIGIN + "/api/v1"


@dataclass(frozen=True)
class ValidatedURL:
    """Normalized destination identity returned by a successful check."""

    url: str
    scheme: str
    host: str
    port: int
    origin: str
    resolved_addresses: tuple[str, ...]
    third_party_safe: bool


@dataclass(frozen=True)
class BrowserNetworkContract:
    """The request policy installed before one Programming navigation."""

    kind: str  # public | loopback | file
    initial_url: str
    origin: str | None = None
    repository_root: str | None = None


def _forbidden_address(address: str, *, allow_loopback: bool = False) -> bool:
    try:
        value = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError as exc:
        raise NetworkPolicyError("destination resolved to a malformed address") from exc
    if isinstance(value, ipaddress.IPv6Address) and value.ipv4_mapped:
        value = value.ipv4_mapped
    if allow_loopback and value.is_loopback:
        return False
    # is_global excludes loopback, private, link-local, multicast, reserved,
    # unspecified, benchmarking/documentation ranges, and mapped variants.
    return not value.is_global


def _resolve_addresses(
    host: str,
    port: int,
    *,
    resolver: Callable[..., Iterable[tuple]] | None = None,
) -> tuple[str, ...]:
    lookup = resolver or socket.getaddrinfo
    try:
        records = lookup(host, port, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror) as exc:
        raise NetworkPolicyError("destination hostname did not resolve") from exc
    addresses: list[str] = []
    for record in records:
        try:
            address = str(record[4][0])
        except (IndexError, TypeError):
            continue
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise NetworkPolicyError("destination hostname resolved to no addresses")
    return tuple(addresses)


def _host_display(host: str) -> str:
    return f"[{host}]" if ":" in host else host


def _normalized_query_key(value: str) -> str:
    decoded = unquote(str(value or ""))
    decoded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", decoded)
    return re.sub(r"[^a-z0-9]+", "_", decoded.casefold()).strip("_")


def _looks_like_opaque_token(value: str) -> bool:
    text = value.strip()
    if _JWT_VALUE.fullmatch(text) or _OPAQUE_HEX_VALUE.fullmatch(text):
        return True
    if len(text) < 24 or not _OPAQUE_TOKEN_ALPHABET.fullmatch(text):
        return False
    classes = sum((
        any(char.islower() for char in text),
        any(char.isupper() for char in text),
        any(char.isdigit() for char in text),
        any(not char.isalnum() for char in text),
    ))
    # Long mixed-alphabet strings and very long compact identifiers are
    # plausibly bearer material even when the caller chose an innocuous key.
    return classes >= 3 or (len(text) >= 40 and len(set(text.casefold())) >= 10)


def _public_query_value_safe(key: str, value: str) -> bool:
    text = unquote(str(value or ""))
    if not text or len(text) > 256 or re.search(r"[\x00-\x1f\x7f]", text):
        return False
    if key in _PUBLIC_PAGINATION_QUERY_KEYS:
        return bool(re.fullmatch(r"\d{1,9}", text))
    if (
        _CREDENTIAL_VALUE.search(text)
        or _CREDENTIAL_PREFIX_VALUE.search(text)
        or _EMAIL_VALUE.fullmatch(text)
        or _SSN_VALUE.fullmatch(text)
        or _SENSITIVE_QUERY_VALUE.search(text)
        or _looks_like_opaque_token(text)
    ):
        return False
    try:
        nested = urlsplit(text)
    except ValueError:
        return False
    if nested.scheme.casefold() in _HTTP_SCHEMES and nested.hostname:
        return False
    return True


def _third_party_safe_query(query: str) -> bool:
    """Allow only demonstrably public search/pagination query semantics.

    Jina receives the complete source URL.  An arbitrary query key can carry
    private data even when it is not named ``token`` or ``signature``, so the
    safe default for non-empty queries is refusal.  The narrow allowlist keeps
    ordinary public search, pagination, sorting, and locale URLs useful while
    still rejecting opaque or sensitive values under those names.
    """

    if not query:
        return True
    try:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    if not pairs:
        return False
    for raw_key, value in pairs:
        key = _normalized_query_key(raw_key)
        if key not in _PUBLIC_FORWARDABLE_QUERY_KEYS:
            return False
        if not _public_query_value_safe(key, value):
            return False
    return True


def validate_public_url(
    value: str,
    *,
    allow_websocket: bool = False,
    resolver: Callable[..., Iterable[tuple]] | None = None,
) -> ValidatedURL:
    """Normalize and validate one public HTTP(S), or explicit WS(S), URL."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise NetworkPolicyError("destination URL is missing or malformed")
    if _CONTROL_OR_SPACE.search(value) or "\\" in value:
        raise NetworkPolicyError("destination URL contains invalid characters")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise NetworkPolicyError("destination URL is malformed") from exc
    scheme = parsed.scheme.casefold()
    allowed = set(_HTTP_SCHEMES)
    if allow_websocket:
        allowed.update(_WS_SCHEMES)
    if scheme not in allowed:
        raise NetworkPolicyError("destination scheme is not allowed")
    if parsed.username is not None or parsed.password is not None:
        raise NetworkPolicyError("destination URL may not contain user information")
    host = (parsed.hostname or "").rstrip(".").casefold()
    if not host:
        raise NetworkPolicyError("destination URL has no hostname")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise NetworkPolicyError("destination hostname is malformed") from exc
    effective_port = port or (443 if scheme in {"https", "wss"} else 80)
    if port == 0:
        raise NetworkPolicyError("destination port is malformed")
    try:
        literal = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        addresses = _resolve_addresses(host, effective_port, resolver=resolver)
    else:
        addresses = (str(literal),)
    if any(_forbidden_address(address) for address in addresses):
        raise NetworkPolicyError("destination resolves to a non-public address")
    default_port = 443 if scheme in {"https", "wss"} else 80
    netloc = _host_display(host) + (f":{effective_port}" if effective_port != default_port else "")
    path = parsed.path or "/"
    normalized = urlunsplit((scheme, netloc, path, parsed.query, ""))
    origin = f"{scheme}://{netloc}"
    return ValidatedURL(
        url=normalized,
        scheme=scheme,
        host=host,
        port=effective_port,
        origin=origin,
        resolved_addresses=addresses,
        third_party_safe=_third_party_safe_query(parsed.query),
    )


def validate_redirect(
    current: ValidatedURL,
    location: str,
    *,
    allow_websocket: bool = False,
    required_origin: str | None = None,
    resolver: Callable[..., Iterable[tuple]] | None = None,
) -> ValidatedURL:
    if not isinstance(location, str) or not location.strip():
        raise NetworkPolicyError("redirect is missing a destination")
    target = validate_public_url(
        urljoin(current.url, location),
        allow_websocket=allow_websocket,
        resolver=resolver,
    )
    if required_origin and target.origin != required_origin:
        raise NetworkPolicyError("authenticated request refused an origin-changing redirect")
    return target


def safe_url_label(value: str) -> str:
    """Return a log-safe origin label without path, query, or user data."""

    try:
        parsed = urlsplit(str(value or ""))
        host = parsed.hostname or "unknown-host"
        port = parsed.port
        scheme = parsed.scheme.casefold() or "url"
        netloc = _host_display(host) + (f":{port}" if port else "")
        return f"{scheme}://{netloc}/…"
    except Exception:
        return "unparseable-url"


def redact_sensitive_text(value: Any, *, secrets: Iterable[str] = ()) -> str:
    """Return provider/error text without credentials or URL path/query data."""

    text = str(value or "")
    for secret in secrets:
        if secret:
            text = text.replace(str(secret), "[credential redacted]")
    text = _BEARER_IN_TEXT.sub("[credential redacted]", text)
    return _URL_IN_TEXT.sub(
        lambda match: safe_url_label(match.group(0)),
        text,
    )


def validate_exact_origin_request(request: Any, required_origin: str) -> None:
    """HTTPX request hook for a credential bound to one exact origin."""

    destination = validate_public_url(str(getattr(request, "url", "")))
    if destination.origin != required_origin:
        raise NetworkPolicyError(
            "credential request is outside its trusted origin",
        )


def validate_openrouter_request(request: Any) -> None:
    """Refuse an OpenRouter bearer request immediately before transport."""

    validate_exact_origin_request(request, OPENROUTER_ORIGIN)


@contextmanager
def openrouter_sdk_client(
    api_key: str,
    *,
    timeout: float | None = None,
    max_retries: int | None = None,
    request_validator: Callable[[Any], None] = validate_openrouter_request,
) -> Iterator[Any]:
    """Yield the OpenAI SDK over a no-redirect, exact-OpenRouter transport."""

    import httpx
    from openai import OpenAI

    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "base_url": OPENROUTER_API_BASE,
    }
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    if max_retries is not None:
        client_kwargs["max_retries"] = max_retries
    with httpx.Client(
        follow_redirects=False,
        event_hooks={"request": [request_validator]},
    ) as transport:
        client_kwargs["http_client"] = transport
        yield OpenAI(**client_kwargs)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def urllib_request_bytes(
    value: str,
    *,
    headers: Mapping[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 60,
    required_origin: str | None = None,
    max_redirects: int = 5,
    max_bytes: int | None = None,
    opener=None,
) -> tuple[bytes, ValidatedURL]:
    """urllib transport with public validation before every bounded hop.

    Authenticated callers pass ``required_origin``.  Their headers are then
    never sent outside that origin.  POST redirects are refused because
    changing method/body semantics is not part of this small transport.
    """

    current = validate_public_url(value)
    if required_origin and current.origin != required_origin:
        raise NetworkPolicyError("authenticated request is outside its trusted origin")
    transport = opener or urllib.request.build_opener(_NoRedirect())
    for hop in range(max_redirects + 1):
        current = validate_public_url(current.url)
        if required_origin and current.origin != required_origin:
            raise NetworkPolicyError("authenticated request is outside its trusted origin")
        request = urllib.request.Request(
            current.url,
            data=data,
            headers=dict(headers or {}),
        )
        try:
            response = transport.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                raise
            response = exc
        status = int(getattr(response, "status", None) or getattr(response, "code", 200))
        if status not in {301, 302, 303, 307, 308}:
            try:
                if max_bytes is None:
                    body = response.read()
                else:
                    if max_bytes < 0:
                        raise NetworkPolicyError("response byte limit is malformed")
                    body = response.read(max_bytes + 1)
                    if len(body) > max_bytes:
                        raise NetworkPolicyError("response exceeded the byte limit")
                return body, current
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        close = getattr(response, "close", None)
        if callable(close):
            close()
        if data is not None:
            raise NetworkPolicyError("authenticated/body request refused a redirect")
        if hop >= max_redirects:
            raise NetworkPolicyError("redirect limit exceeded")
        location = response.headers.get("location")
        current = validate_redirect(
            current,
            location,
            required_origin=required_origin,
        )
    raise NetworkPolicyError("redirect limit exceeded")


def openrouter_request_bytes(
    value: str,
    *,
    headers: Mapping[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 60,
    max_bytes: int | None = None,
    opener=None,
) -> tuple[bytes, ValidatedURL]:
    """Send one credentialed OpenRouter request with no redirect forwarding."""

    return urllib_request_bytes(
        value,
        headers=headers,
        data=data,
        timeout=timeout,
        required_origin=OPENROUTER_ORIGIN,
        max_redirects=0,
        max_bytes=max_bytes,
        opener=opener,
    )


def browser_contract(initial: str, repository_root: str | Path) -> BrowserNetworkContract:
    """Create Programming's only local-network exception contract."""

    root = Path(repository_root).resolve(strict=True)
    parsed = urlsplit(initial)
    if parsed.scheme.casefold() == "file":
        if parsed.netloc not in {"", "localhost"} or parsed.query or parsed.fragment:
            raise NetworkPolicyError("file inspection URL is malformed")
        try:
            target = Path(unquote(parsed.path)).resolve(strict=True)
            target.relative_to(root)
        except (OSError, ValueError) as exc:
            raise NetworkPolicyError("file inspection must stay inside the repository") from exc
        return BrowserNetworkContract("file", target.as_uri(), repository_root=str(root))
    if parsed.scheme.casefold() in _HTTP_SCHEMES and (parsed.hostname or "").casefold() == "localhost":
        try:
            port = parsed.port
        except ValueError as exc:
            raise NetworkPolicyError("localhost inspection URL is malformed") from exc
        if port in {None, 0} or parsed.username is not None or parsed.password is not None:
            raise NetworkPolicyError("localhost inspection requires an explicit port and no user information")
        scheme = parsed.scheme.casefold()
        origin = f"{scheme}://localhost:{port}"
        normalized = urlunsplit((scheme, f"localhost:{port}", parsed.path or "/", parsed.query, ""))
        return BrowserNetworkContract("loopback", normalized, origin=origin)
    public = validate_public_url(initial)
    return BrowserNetworkContract("public", public.url, origin=public.origin)


def validate_browser_request(
    value: str,
    contract: BrowserNetworkContract,
    *,
    resolver: Callable[..., Iterable[tuple]] | None = None,
) -> str:
    """Validate each navigation, redirect, subrequest, and WebSocket URL."""

    parsed = urlsplit(value)
    scheme = parsed.scheme.casefold()
    if scheme in {"data", "blob", "about"}:
        return value
    if contract.kind == "file":
        if scheme != "file":
            raise NetworkPolicyError("repository file inspection may not make network requests")
        nested = browser_contract(value, contract.repository_root or "")
        return nested.initial_url
    if contract.kind == "loopback":
        if scheme not in _HTTP_SCHEMES | _WS_SCHEMES:
            raise NetworkPolicyError("localhost inspection requested an unsupported scheme")
        if parsed.username is not None or parsed.password is not None:
            raise NetworkPolicyError("localhost inspection may not contain user information")
        host = (parsed.hostname or "").casefold()
        port = parsed.port or (443 if scheme in {"https", "wss"} else 80)
        initial = urlsplit(contract.initial_url)
        if host != "localhost" or port != initial.port:
            raise NetworkPolicyError("localhost inspection may reach only its exact loopback origin")
        addresses = _resolve_addresses(host, port, resolver=resolver)
        try:
            resolved = tuple(
                ipaddress.ip_address(address.split("%", 1)[0])
                for address in addresses
            )
        except ValueError as exc:
            raise NetworkPolicyError(
                "localhost inspection resolved to a malformed address",
            ) from exc
        for address in resolved:
            normalized = (
                address.ipv4_mapped
                if isinstance(address, ipaddress.IPv6Address)
                and address.ipv4_mapped is not None
                else address
            )
            if not normalized.is_loopback:
                raise NetworkPolicyError(
                    "localhost inspection resolved outside loopback",
                )
        return value
    return validate_public_url(value, allow_websocket=True, resolver=resolver).url


__all__ = [
    "BrowserNetworkContract",
    "NetworkPolicyError",
    "OPENROUTER_API_BASE",
    "OPENROUTER_ORIGIN",
    "ValidatedURL",
    "browser_contract",
    "openrouter_request_bytes",
    "openrouter_sdk_client",
    "redact_sensitive_text",
    "safe_url_label",
    "urllib_request_bytes",
    "validate_browser_request",
    "validate_exact_origin_request",
    "validate_openrouter_request",
    "validate_public_url",
    "validate_redirect",
]
