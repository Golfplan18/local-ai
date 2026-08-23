"""Hermetic tests through native network caller boundaries."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TOOLS = _ORCH / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
_TESTS = str(Path(__file__).resolve().parent)
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)
import live_guard  # noqa: E402,F401

import network_policy  # noqa: E402
import programming  # noqa: E402
import web_fetch as wf  # noqa: E402


def _dns(mapping):
    def resolve(host, port, **_kwargs):
        address = mapping.get(host, "93.184.216.34")
        family = (network_policy.socket.AF_INET6 if ":" in address
                  else network_policy.socket.AF_INET)
        return [(family, network_policy.socket.SOCK_STREAM, 6, "",
                 (address, port))]
    return resolve


class _Response:
    def __init__(self, status=200, *, headers=None, text="<p>public body</p>"):
        self.status_code = status
        self.status = status
        self.code = status
        self.headers = headers or {}
        self.text = text


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, url):
        self.calls.append(url)
        return self.responses.pop(0)


class TestHTTPBoundaries(unittest.TestCase):
    def test_private_initial_is_refused_before_any_tier(self):
        with mock.patch.object(
            network_policy.socket, "getaddrinfo",
            side_effect=_dns({"private.example": "10.0.0.8"}),
        ), mock.patch.object(wf, "_fetch_httpx") as http, \
             mock.patch.object(wf, "_fetch_playwright") as browser, \
             mock.patch.object(wf, "_fetch_jina") as jina:
            result = wf.web_fetch("https://private.example/data")
        self.assertIn("non-public", result["error"])
        http.assert_not_called()
        browser.assert_not_called()
        jina.assert_not_called()

    def test_public_to_private_redirect_is_refused_before_second_get(self):
        client = _Client([
            _Response(302, headers={"location": "http://private.example/secret"}),
        ])
        with mock.patch.object(
            network_policy.socket, "getaddrinfo",
            side_effect=_dns({
                "public.example": "93.184.216.34",
                "private.example": "192.168.1.9",
            }),
        ):
            with self.assertRaises(network_policy.NetworkPolicyError):
                wf._manual_httpx_get(client, "https://public.example/start")
        self.assertEqual(client.calls, ["https://public.example/start"])

    def test_public_redirect_chain_is_manually_revalidated(self):
        client = _Client([
            _Response(302, headers={"location": "https://next.example/final"}),
            _Response(200, text="ok"),
        ])
        with mock.patch.object(
            network_policy.socket, "getaddrinfo",
            side_effect=_dns({}),
        ):
            response, final = wf._manual_httpx_get(
                client, "https://public.example/start",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(final.origin, "https://next.example")
        self.assertEqual(client.calls, [
            "https://public.example/start", "https://next.example/final",
        ])

    def test_signed_url_is_never_forwarded_to_jina(self):
        bad = wf._error_result("https://example.com", "httpx", "short")
        with mock.patch.object(
            network_policy.socket, "getaddrinfo", side_effect=_dns({}),
        ), mock.patch.object(wf, "_fetch_httpx", return_value=bad), \
             mock.patch.object(wf, "_fetch_playwright", return_value=bad), \
             mock.patch.object(wf, "_fetch_jina") as jina:
            automatic = wf.web_fetch(
                "https://example.com/file?X-Amz-Signature=secret",
            )
            explicit = wf.web_fetch(
                "https://example.com/file?token=secret", channel="api",
            )
        jina.assert_not_called()
        for result in (automatic, explicit):
            self.assertFalse(result["third_party_forwarding"]["forwarded"])
            self.assertNotIn("secret", str(result))

    def test_sensitive_query_value_is_never_forwarded_to_jina(self):
        with mock.patch.object(
            network_policy.socket, "getaddrinfo", side_effect=_dns({}),
        ), mock.patch.object(wf, "_fetch_jina") as jina:
            results = [
                wf.web_fetch(url, channel="api")
                for url in (
                    "https://example.com/file?q=Bearer%20secret",
                    "https://example.com/file?q=AKIA1234567890EXAMPLE",
                    "https://example.com/file?q=user%40example.com",
                )
            ]
        jina.assert_not_called()
        for result in results:
            self.assertFalse(result["third_party_forwarding"]["forwarded"])
        self.assertNotIn("secret", str(results))
        self.assertNotIn("AKIA", str(results))

    def test_opaque_unknown_query_is_not_forwarded_on_automatic_fallback(self):
        bad = wf._error_result("https://example.com", "httpx", "short")
        with mock.patch.object(
            network_policy.socket, "getaddrinfo", side_effect=_dns({}),
        ), mock.patch.object(wf, "_fetch_httpx", return_value=bad), \
             mock.patch.object(wf, "_fetch_playwright", return_value=bad), \
             mock.patch.object(wf, "_fetch_jina") as jina:
            result = wf.web_fetch(
                "https://example.com/file?context=quarterly-draft",
            )
        jina.assert_not_called()
        self.assertIn("error", result)
        self.assertFalse(result["third_party_forwarding"]["forwarded"])
        self.assertNotIn("quarterly-draft", str(result))

    def test_public_search_pagination_query_remains_forwardable(self):
        url = (
            "https://example.com/search?"
            "q=public+records&keyword=climate&page=2&sort=date"
        )
        bad = wf._error_result(url, "httpx", "short")
        good = {
            "url": url, "markdown": "x" * 600, "title": "ok",
            "channel": "api", "fetched_at": "now",
            "destination_classification": "public-forwarded-to-jina",
            "third_party_forwarding": {
                "forwarded": True, "provider": "jina-reader",
                "reason": "automatic-fallback",
            },
        }
        with mock.patch.object(
            network_policy.socket, "getaddrinfo", side_effect=_dns({}),
        ), mock.patch.object(wf, "_fetch_httpx", return_value=bad), \
             mock.patch.object(wf, "_fetch_playwright", return_value=bad), \
             mock.patch.object(wf, "_fetch_jina", return_value=good) as jina:
            result = wf.web_fetch(url)
        jina.assert_called_once_with(url, reason="automatic-fallback")
        self.assertTrue(result["third_party_forwarding"]["forwarded"])

    def test_safe_public_fallback_is_explicitly_forwarded(self):
        bad = wf._error_result("https://example.com", "httpx", "short")
        good = {
            "url": "https://example.com/", "markdown": "x" * 600,
            "title": "ok", "channel": "api", "fetched_at": "now",
            "destination_classification": "public-forwarded-to-jina",
            "third_party_forwarding": {
                "forwarded": True, "provider": "jina-reader",
            },
        }
        with mock.patch.object(
            network_policy.socket, "getaddrinfo", side_effect=_dns({}),
        ), mock.patch.object(wf, "_fetch_httpx", return_value=bad), \
             mock.patch.object(wf, "_fetch_playwright", return_value=bad), \
             mock.patch.object(wf, "_fetch_jina", return_value=good) as jina:
            result = wf.web_fetch("https://example.com/article")
        jina.assert_called_once()
        self.assertTrue(result["third_party_forwarding"]["forwarded"])

    def test_harmless_public_query_fallback_remains_available(self):
        bad = wf._error_result("https://example.com", "httpx", "short")
        good = {
            "url": "https://example.com/article?page=2", "markdown": "x" * 600,
            "title": "ok", "channel": "httpx", "fetched_at": "now",
            "destination_classification": "public-forwarded-to-jina",
            "third_party_forwarding": {
                "forwarded": True, "provider": "jina-reader",
            },
        }
        with mock.patch.object(
            network_policy.socket, "getaddrinfo", side_effect=_dns({}),
        ), mock.patch.object(wf, "_fetch_httpx", return_value=bad), \
             mock.patch.object(wf, "_fetch_playwright", return_value=bad), \
             mock.patch.object(wf, "_fetch_jina", return_value=good) as jina:
            result = wf.web_fetch("https://example.com/article?page=2")
        jina.assert_called_once()
        self.assertTrue(result["third_party_forwarding"]["forwarded"])

    def test_sensitive_card_number_query_is_not_forwarded(self):
        bad = wf._error_result("https://example.com", "httpx", "short")
        with mock.patch.object(
            network_policy.socket, "getaddrinfo", side_effect=_dns({}),
        ), mock.patch.object(wf, "_fetch_httpx", return_value=bad), \
             mock.patch.object(wf, "_fetch_playwright", return_value=bad), \
             mock.patch.object(wf, "_fetch_jina") as jina:
            result = wf.web_fetch(
                "https://example.com/search?q=4111-1111-1111-1111",
            )
        jina.assert_not_called()
        self.assertFalse(result["third_party_forwarding"]["forwarded"])


class _Route:
    def __init__(self, url):
        self.request = types.SimpleNamespace(url=url)
        self.aborted = False
        self.continued = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        self.continued = True


class _WebSocketRoute:
    def __init__(self, url):
        self.url = url
        self.closed = False
        self.connected = False

    def close(self, **_kwargs):
        self.closed = True

    def connect_to_server(self):
        self.connected = True


class _Page:
    def __init__(self, context, requests, websockets):
        self.context = context
        self.requests = requests
        self.websockets = websockets

    def goto(self, _url, **_kwargs):
        for route in self.requests:
            self.context.http_handler(route)
        for route in self.websockets:
            self.context.ws_handler(route)

    def content(self):
        return "<html><body>" + ("x" * 600) + "</body></html>"

    def screenshot(self, **_kwargs):
        return b"png"


class _Context:
    def __init__(self, requests, websockets):
        self.requests = requests
        self.websockets = websockets
        self.http_handler = None
        self.ws_handler = None

    def route(self, _pattern, handler):
        self.http_handler = handler

    def route_web_socket(self, _pattern, handler):
        self.ws_handler = handler

    def new_page(self):
        return _Page(self, self.requests, self.websockets)


class _Browser:
    def __init__(self, requests, websockets):
        self.requests = requests
        self.websockets = websockets
        self.context_kwargs = None

    def new_context(self, **kwargs):
        self.context_kwargs = kwargs
        return _Context(self.requests, self.websockets)

    def close(self):
        return None


def _playwright_modules(browser):
    manager = mock.MagicMock()
    manager.__enter__.return_value.chromium.launch.return_value = browser
    manager.__exit__.return_value = False
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = mock.Mock(return_value=manager)
    package = types.ModuleType("playwright")
    package.sync_api = sync_api
    return {"playwright": package, "playwright.sync_api": sync_api}


class TestBrowserBoundaries(unittest.TestCase):
    def test_web_fetch_launches_managed_chromium_without_a_channel(self):
        browser = _Browser([], [])
        modules = _playwright_modules(browser)
        with mock.patch.object(
            network_policy.socket, "getaddrinfo", side_effect=_dns({}),
        ), mock.patch.dict(sys.modules, modules), \
             mock.patch.object(wf, "_trafilatura_to_result", return_value={
                 "url": "https://public.example/", "markdown": "x" * 600,
                 "title": None, "channel": "local", "fetched_at": "now",
             }):
            wf._fetch_playwright("https://public.example/")

        launch = (
            modules["playwright.sync_api"].sync_playwright.return_value
            .__enter__.return_value.chromium.launch
        )
        launch.assert_called_once_with(headless=True)
        self.assertNotIn("channel", launch.call_args.kwargs)

    def test_web_fetch_blocks_private_subrequest_and_websocket(self):
        private_http = _Route("http://private.example/data")
        private_ws = _WebSocketRoute("ws://private.example/socket")
        browser = _Browser([private_http], [private_ws])
        with mock.patch.object(
            network_policy.socket, "getaddrinfo",
            side_effect=_dns({
                "public.example": "93.184.216.34",
                "private.example": "10.0.0.4",
            }),
        ), mock.patch.dict(sys.modules, _playwright_modules(browser)), \
             mock.patch.object(wf, "_trafilatura_to_result", return_value={
                 "url": "https://public.example/", "markdown": "x" * 600,
                 "title": None, "channel": "local", "fetched_at": "now",
             }):
            wf._fetch_playwright("https://public.example/")
        self.assertTrue(private_http.aborted)
        self.assertFalse(private_http.continued)
        self.assertTrue(private_ws.closed)
        self.assertFalse(private_ws.connected)
        self.assertEqual(browser.context_kwargs["service_workers"], "block")

    def test_programming_loopback_contract_allows_only_exact_origin(self):
        allowed = _Route("http://localhost:3000/app.js")
        forbidden = _Route("http://127.0.0.1:3000/secret")
        websocket = _WebSocketRoute("ws://localhost:3000/socket")
        browser = _Browser([allowed, forbidden], [websocket])
        with tempfile.TemporaryDirectory() as root, mock.patch.object(
            network_policy.socket, "getaddrinfo",
            side_effect=_dns({"localhost": "127.0.0.1"}),
        ), mock.patch.dict(sys.modules, _playwright_modules(browser)):
            with self.assertRaises(programming.ProgrammingError):
                programming._interface_payloads(
                    Path(root), {"url": "http://localhost:3000/"},
                )
        self.assertTrue(allowed.continued)
        self.assertTrue(forbidden.aborted)
        self.assertTrue(websocket.connected)
        self.assertEqual(browser.context_kwargs["service_workers"], "block")

    def test_programming_loopback_contract_rejects_non_loopback_resolution(self):
        route = _Route("http://localhost:3000/app.js")
        browser = _Browser([route], [])
        with tempfile.TemporaryDirectory() as root, mock.patch.object(
            network_policy.socket, "getaddrinfo",
            side_effect=_dns({"localhost": "93.184.216.34"}),
        ), mock.patch.dict(sys.modules, _playwright_modules(browser)):
            with self.assertRaises(programming.ProgrammingError):
                programming._interface_payloads(
                    Path(root), {"url": "http://localhost:3000/"},
                )
        self.assertTrue(route.aborted)

    def test_programming_file_contract_stays_inside_repository(self):
        browser = _Browser([], [])
        with tempfile.TemporaryDirectory() as root:
            # macOS exposes /var as a symlink to /private/var; production callers
            # supply an already canonical repository root.
            root_path = Path(root).resolve()
            page = root_path / "page.html"
            page.write_text("<html>ok</html>", encoding="utf-8")
            with mock.patch.dict(sys.modules, _playwright_modules(browser)):
                payload = programming._interface_payloads(
                    root_path, {"path": "page.html"},
                )
            self.assertEqual(payload[0]["mime"], "image/png")
            outside = root_path.parent / "outside-interface.html"
            outside.write_text("x", encoding="utf-8")
            try:
                with self.assertRaises(programming.ProgrammingError):
                    programming._interface_payloads(
                        root_path, {"url": outside.as_uri()},
                    )
            finally:
                outside.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
