"""Tests for ``orchestrator/tools/web_fetch.py``.

Default suite is offline:
  - tool contract shape
  - channel parameter validation
  - persist=True raises NotImplementedError
  - cascade escalation logic (mocked tiers)

Live network smoke tests are gated on ``ORA_WEB_FETCH_LIVE=1`` so CI
doesn't fail on rate limits. Run locally with::

    ORA_WEB_FETCH_LIVE=1 python3 -m unittest \\
        orchestrator.tests.test_web_fetch
"""

from __future__ import annotations

import os
import sys
import json
from contextlib import contextmanager
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
import threading
import types
import unittest
from urllib.parse import urlsplit
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.join(_HERE, "..", "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import web_fetch as wf  # noqa: E402
import network_policy  # noqa: E402
import tool_events  # noqa: E402


_LIVE = os.environ.get("ORA_WEB_FETCH_LIVE") == "1"
_dns_patch = None


def setUpModule():
    global _dns_patch
    if not _LIVE:
        _dns_patch = mock.patch.object(
            network_policy.socket,
            "getaddrinfo",
            return_value=[
                (network_policy.socket.AF_INET,
                 network_policy.socket.SOCK_STREAM, 6, "",
                 ("93.184.216.34", 443)),
            ],
        )
        _dns_patch.start()


def tearDownModule():
    if _dns_patch is not None:
        _dns_patch.stop()


class ContractShapeTests(unittest.TestCase):
    """Every code path returns the documented dict shape."""

    _expected_keys = {"url", "markdown", "title", "channel", "fetched_at"}

    def _assert_shape(self, result):
        self.assertIsInstance(result, dict)
        self.assertTrue(
            self._expected_keys.issubset(result.keys()),
            f"missing keys: {self._expected_keys - result.keys()}",
        )

    def test_invalid_url_returns_error_dict(self):
        result = wf.web_fetch("")
        self._assert_shape(result)
        self.assertEqual(result["markdown"], "")
        self.assertIn("error", result)

    def test_unsupported_scheme_returns_error_dict(self):
        result = wf.web_fetch("ftp://example.com")
        self._assert_shape(result)
        self.assertIn("error", result)
        self.assertIn("scheme", result["error"].lower())

    def test_unknown_channel_returns_error_dict(self):
        result = wf.web_fetch("https://example.com", channel="banana")
        self._assert_shape(result)
        self.assertIn("error", result)
        self.assertIn("banana", result["error"])


class PersistGateTests(unittest.TestCase):
    def test_persist_true_raises_not_implemented(self):
        with self.assertRaises(NotImplementedError) as ctx:
            wf.web_fetch("https://example.com", persist=True)
        self.assertIn("G3.25", str(ctx.exception))


class CascadeLogicTests(unittest.TestCase):
    """The auto-cascade escalates only when the previous tier fell short."""

    def _good(self, channel):
        return {
            "url": "https://example.com",
            "markdown": "A" * 1000,
            "title": "ok",
            "channel": channel,
            "fetched_at": "2026-05-28T00:00:00+00:00",
        }

    def _bad(self, channel, reason="empty"):
        return {
            "url": "https://example.com",
            "markdown": "",
            "title": None,
            "channel": channel,
            "fetched_at": "2026-05-28T00:00:00+00:00",
            "error": reason,
        }

    def test_cascade_stops_at_httpx_when_acceptable(self):
        with mock.patch.object(wf, "_fetch_httpx",
                               return_value=self._good("httpx")) as h, \
             mock.patch.object(wf, "_fetch_playwright") as p, \
             mock.patch.object(wf, "_fetch_jina") as j:
            wf.web_fetch("https://example.com")
        h.assert_called_once()
        p.assert_not_called()
        j.assert_not_called()

    def test_cascade_escalates_to_playwright_on_short_markdown(self):
        short = {
            "url": "https://example.com",
            "markdown": "x",
            "title": None,
            "channel": "httpx",
            "fetched_at": "2026-05-28T00:00:00+00:00",
        }
        with mock.patch.object(wf, "_fetch_httpx", return_value=short), \
             mock.patch.object(wf, "_fetch_playwright",
                               return_value=self._good("local")) as p, \
             mock.patch.object(wf, "_fetch_jina") as j:
            result = wf.web_fetch("https://example.com")
        p.assert_called_once()
        j.assert_not_called()
        self.assertEqual(result["channel"], "local")

    def test_cascade_falls_through_to_jina_on_double_failure(self):
        with mock.patch.object(wf, "_fetch_httpx",
                               return_value=self._bad("httpx")), \
             mock.patch.object(wf, "_fetch_playwright",
                               return_value=self._bad("local")), \
             mock.patch.object(wf, "_fetch_jina",
                               return_value=self._good("api")) as j:
            result = wf.web_fetch("https://example.com")
        j.assert_called_once()
        self.assertEqual(result["channel"], "api")

    def test_policy_refusal_stops_the_cascade(self):
        refusal = self._bad("httpx", "redirect destination refused")
        refusal["policy_refusal"] = True
        with mock.patch.object(wf, "_fetch_httpx", return_value=refusal), \
             mock.patch.object(wf, "_fetch_playwright") as p, \
             mock.patch.object(wf, "_fetch_jina") as j:
            result = wf.web_fetch("https://example.com")
        self.assertIs(result, refusal)
        p.assert_not_called()
        j.assert_not_called()


class ChannelPinTests(unittest.TestCase):
    def test_channel_httpx_pins_to_httpx(self):
        with mock.patch.object(wf, "_fetch_httpx",
                               return_value={"channel": "httpx"}) as h, \
             mock.patch.object(wf, "_fetch_playwright") as p, \
             mock.patch.object(wf, "_fetch_jina") as j:
            wf.web_fetch("https://example.com", channel="httpx")
        h.assert_called_once()
        p.assert_not_called()
        j.assert_not_called()

    def test_channel_local_pins_to_playwright(self):
        with mock.patch.object(wf, "_fetch_httpx") as h, \
             mock.patch.object(wf, "_fetch_playwright",
                               return_value={"channel": "local"}) as p, \
             mock.patch.object(wf, "_fetch_jina") as j:
            wf.web_fetch("https://example.com", channel="local")
        p.assert_called_once()
        h.assert_not_called()
        j.assert_not_called()

    def test_channel_api_pins_to_jina(self):
        with mock.patch.object(wf, "_fetch_httpx") as h, \
             mock.patch.object(wf, "_fetch_playwright") as p, \
             mock.patch.object(wf, "_fetch_jina",
                               return_value={"channel": "api"}) as j:
            wf.web_fetch("https://example.com", channel="api")
        j.assert_called_once()
        h.assert_not_called()
        p.assert_not_called()


class JinaTitleParsingTests(unittest.TestCase):
    def test_extracts_title_prefix(self):
        self.assertEqual(
            wf._jina_title("Title: My Article\n\nBody"),
            "My Article",
        )

    def test_returns_none_when_no_prefix(self):
        self.assertIsNone(wf._jina_title("# Heading\n\nBody"))

    def test_returns_none_on_empty(self):
        self.assertIsNone(wf._jina_title(""))


class JinaForwardingRecordTests(unittest.TestCase):
    def test_opaque_query_refusal_record_is_failed_and_redacted(self):
        with tempfile.TemporaryDirectory() as temp:
            sink = os.path.join(temp, "events.jsonl")
            prior = tool_events.GLOBAL_SINK_DEFAULT
            prior_disabled = os.environ.pop("ORA_TOOL_EVENTS", None)
            tool_events.GLOBAL_SINK_DEFAULT = sink
            try:
                result = wf.web_fetch(
                    "https://example.com/file?context=private-draft-never-store",
                    channel="api",
                )
                with open(sink, encoding="utf-8") as stream:
                    event = json.loads(stream.readlines()[-1])
            finally:
                tool_events.GLOBAL_SINK_DEFAULT = prior
                if prior_disabled is not None:
                    os.environ["ORA_TOOL_EVENTS"] = prior_disabled
            self.assertIn("error", result)
            self.assertFalse(event["exit"]["ok"])
            self.assertEqual(event["destination_classification"],
                             "public-not-forwardable")
            self.assertEqual(event["third_party_forwarding"], {
                "provider": "jina-reader",
                "forwarded": False,
                "reason": "sensitive-url",
            })
            self.assertNotIn("never-store", json.dumps(event))

    def test_safe_fallback_records_forwarding_reason(self):
        bad = {
            "url": "https://example.com", "markdown": "", "title": None,
            "channel": "httpx", "fetched_at": "now", "error": "short",
        }
        response = mock.Mock(status_code=200, text="Title: Safe\n\n" + "x" * 600)
        manager = mock.MagicMock()
        manager.__enter__.return_value = mock.Mock()
        manager.__exit__.return_value = False
        fake_httpx = mock.Mock()
        fake_httpx.Client.return_value = manager
        with tempfile.TemporaryDirectory() as temp:
            sink = os.path.join(temp, "events.jsonl")
            prior = tool_events.GLOBAL_SINK_DEFAULT
            prior_disabled = os.environ.pop("ORA_TOOL_EVENTS", None)
            tool_events.GLOBAL_SINK_DEFAULT = sink
            try:
                with mock.patch.dict(sys.modules, {"httpx": fake_httpx}), \
                     mock.patch.object(wf, "_fetch_httpx", return_value=bad), \
                     mock.patch.object(wf, "_fetch_playwright", return_value=bad), \
                     mock.patch.object(wf, "_manual_httpx_get",
                                       return_value=(response, mock.sentinel.final)):
                    result = wf.web_fetch("https://example.com/article?page=2")
                with open(sink, encoding="utf-8") as stream:
                    event = json.loads(stream.readlines()[-1])
            finally:
                tool_events.GLOBAL_SINK_DEFAULT = prior
                if prior_disabled is not None:
                    os.environ["ORA_TOOL_EVENTS"] = prior_disabled
        self.assertEqual(result["destination_classification"],
                         "public-forwarded-to-jina")
        self.assertEqual(result["third_party_forwarding"]["provider"],
                         "jina-reader")
        self.assertTrue(result["third_party_forwarding"]["forwarded"])
        self.assertEqual(result["third_party_forwarding"]["reason"],
                         "automatic-fallback")
        self.assertTrue(event["exit"]["ok"])
        self.assertEqual(event["third_party_forwarding"], {
            "provider": "jina-reader",
            "forwarded": True,
            "reason": "automatic-fallback",
        })


class AcceptabilityTests(unittest.TestCase):
    def test_error_result_is_unacceptable(self):
        self.assertFalse(wf._is_acceptable({"markdown": "x" * 1000,
                                            "error": "boom"}))

    def test_short_markdown_is_unacceptable(self):
        self.assertFalse(wf._is_acceptable({"markdown": "short"}))

    def test_long_markdown_is_acceptable(self):
        self.assertTrue(wf._is_acceptable(
            {"markdown": "x" * (wf._MIN_USEFUL_CHARS + 1)}
        ))


class _FetchFixtureHandler(BaseHTTPRequestHandler):
    """Small local body fixture; oversized responses omit Content-Length."""

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        if "redirect" in self.path:
            self.send_response(302)
            self.send_header("Location", "/private")
            self.end_headers()
            return
        content_encoding = None
        if "compressed-oversized" in self.path:
            body = gzip.compress(b"expanded-fixture-" * 4096)
            content_type = "text/html; charset=utf-8"
            content_encoding = "gzip"
        elif "compressed-normal" in self.path:
            body = gzip.compress(
                b"<html><head><title>Fixture article</title></head>"
                b"<body>" + (b"Deterministic local article sentence. " * 40)
                + b"</body></html>"
            )
            content_type = "text/html; charset=utf-8"
            content_encoding = "gzip"
        elif "oversized" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            try:
                for _ in range(32):
                    self.wfile.write(b"oversized-fixture-" * 64)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        elif "/reader/" in self.path:
            body = (
                b"Title: Fixture article\n\n"
                + (b"Deterministic local article sentence. " * 40)
            )
            content_type = "text/markdown; charset=utf-8"
        else:
            body = (
                b"<html><head><title>Fixture article</title></head><body>"
                + (b"Deterministic local article sentence. " * 40)
                + b"</body></html>"
            )
            content_type = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        if content_encoding:
            self.send_header("Content-Encoding", content_encoding)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return None


class LocalStreamFixtureTests(unittest.TestCase):
    """Exercise real httpx streaming without contacting an external service."""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FetchFixtureHandler)
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, name="web-fetch-fixture", daemon=True,
        )
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def _url(self, path):
        return self.base_url + "/" + path

    def _fixture_validation(self, value, **_kwargs):
        parsed = urlsplit(value)
        if "private" in (parsed.path or ""):
            raise network_policy.NetworkPolicyError(
                "destination resolves to a non-public address",
            )
        return network_policy.ValidatedURL(
            url=value,
            scheme=parsed.scheme,
            host=parsed.hostname,
            port=parsed.port,
            origin=f"{parsed.scheme}://{parsed.netloc}",
            resolved_addresses=("127.0.0.1",),
            third_party_safe=True,
        )

    @contextmanager
    def _allow_fixture_urls(self):
        # setUpModule's offline DNS guard points every hostname at a public
        # documentation address.  This fixture needs the real loopback socket,
        # while the validator is still replaced only for these local URLs.
        with mock.patch.object(
            wf.network_policy,
            "validate_public_url",
            side_effect=self._fixture_validation,
        ), mock.patch.object(
            wf.network_policy.socket,
            "getaddrinfo",
            return_value=[(
                wf.network_policy.socket.AF_INET,
                wf.network_policy.socket.SOCK_STREAM,
                6,
                "",
                ("127.0.0.1", self.server.server_port),
            )],
        ):
            yield

    def test_normal_http_response_is_extracted_unchanged(self):
        with self._allow_fixture_urls():
            result = wf.web_fetch(self._url("normal"), channel="httpx")
        self.assertEqual(result["channel"], "httpx")
        self.assertNotIn("error", result)
        self.assertIn("Deterministic local article sentence", result["markdown"])

    def test_oversized_http_response_is_bounded_and_terminal(self):
        with mock.patch.object(wf, "_MAX_CONTENT_BYTES", 1024), \
             self._allow_fixture_urls(), \
             mock.patch.object(wf, "_fetch_playwright") as browser, \
             mock.patch.object(wf, "_fetch_jina") as jina:
            result = wf.web_fetch(self._url("oversized"))
        self.assertTrue(result["content_limit_exceeded"])
        self.assertEqual(result["content_limit_bytes"], 1024)
        self.assertEqual(result["markdown"], "")
        self.assertIn("shared content cap", result["error"])
        browser.assert_not_called()
        jina.assert_not_called()

    def test_compressed_http_response_is_bounded_before_decompression(self):
        with mock.patch.object(wf, "_MAX_CONTENT_BYTES", 1024), \
             self._allow_fixture_urls(), \
             mock.patch.object(wf, "_fetch_playwright") as browser, \
             mock.patch.object(wf, "_fetch_jina") as jina:
            result = wf.web_fetch(
                self._url("compressed-oversized"), channel="httpx",
            )
        self.assertTrue(result["content_limit_exceeded"])
        self.assertEqual(result["markdown"], "")
        browser.assert_not_called()
        jina.assert_not_called()

    def test_bounded_reader_uses_raw_stream_for_compressed_body(self):
        compressed = gzip.compress(b"expanded-fixture-" * 4096)

        class _CompressedResponse:
            headers = {
                "Content-Encoding": "gzip",
                "Content-Length": str(len(compressed)),
            }

            def iter_raw(self, chunk_size=None):
                self.chunk_size = chunk_size
                yield compressed

            def iter_bytes(self, **_kwargs):
                raise AssertionError("bounded reader used decoded iterator")

        response = _CompressedResponse()
        with mock.patch.object(wf, "_MAX_CONTENT_BYTES", 1024):
            body, exceeded = wf._read_stream_body(response)
        self.assertLess(len(compressed), 1024)
        self.assertEqual(response.chunk_size, wf._STREAM_CHUNK_BYTES)
        self.assertEqual(body, b"")
        self.assertTrue(exceeded)

    def test_optional_codec_is_refused_before_raw_body_iteration_and_auto_falls_back(self):
        class _OptionalCodecResponse:
            status_code = 200
            headers = {"Content-Encoding": "br", "Content-Length": "4"}
            encoding = "utf-8"

            def __init__(self):
                self.raw_iterated = False

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def iter_raw(self, **_kwargs):
                self.raw_iterated = True
                raise AssertionError("optional codec body was materialized")

        class _Client:
            def __init__(self, response):
                self.response = response
                self.headers = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @contextmanager
            def stream(self, method, url):
                self.request = (method, url)
                yield self.response

        response = _OptionalCodecResponse()
        client = _Client(response)
        with self._allow_fixture_urls(), mock.patch(
            "httpx.Client", return_value=client,
        ) as client_factory:
            result = wf.web_fetch(self._url("optional-codec"), channel="httpx")

        self.assertEqual(result["unsupported_content_encoding"], "br")
        self.assertIn("unsupported or unsafe", result["error"].lower())
        self.assertFalse(response.raw_iterated)
        self.assertEqual(
            client_factory.call_args.kwargs["headers"]["Accept-Encoding"],
            "gzip, deflate",
        )

        browser_result = {
            "url": self._url("optional-codec"),
            "markdown": "browser content " * 50,
            "title": "browser",
            "channel": "local",
            "fetched_at": "now",
        }
        with self._allow_fixture_urls(), mock.patch(
            "httpx.Client", return_value=_Client(_OptionalCodecResponse()),
        ), mock.patch.object(
            wf, "_fetch_playwright", return_value=browser_result,
        ) as browser, mock.patch.object(wf, "_fetch_jina") as jina:
            automatic = wf.web_fetch(self._url("optional-codec"))
        self.assertIs(automatic, browser_result)
        browser.assert_called_once()
        jina.assert_not_called()

    def test_oversized_jina_response_is_bounded(self):
        with mock.patch.object(wf, "_MAX_CONTENT_BYTES", 1024), \
             mock.patch.object(wf, "_JINA_READER_BASE", self.base_url + "/reader/"), \
             self._allow_fixture_urls():
            result = wf.web_fetch(self._url("oversized"), channel="api")
        self.assertTrue(result["content_limit_exceeded"])
        self.assertEqual(result["content_limit_bytes"], 1024)
        self.assertEqual(result["markdown"], "")
        self.assertTrue(result["third_party_forwarding"]["forwarded"])

    def test_compressed_jina_response_is_bounded_before_decompression(self):
        with mock.patch.object(wf, "_MAX_CONTENT_BYTES", 1024), \
             mock.patch.object(wf, "_JINA_READER_BASE", self.base_url + "/reader/"), \
             self._allow_fixture_urls():
            result = wf.web_fetch(
                self._url("compressed-oversized"), channel="api",
            )
        self.assertTrue(result["content_limit_exceeded"])
        self.assertEqual(result["markdown"], "")
        self.assertTrue(result["third_party_forwarding"]["forwarded"])

    def test_normal_gzip_response_remains_supported(self):
        with mock.patch.object(wf, "_MAX_CONTENT_BYTES", 4096), \
             self._allow_fixture_urls():
            result = wf.web_fetch(
                self._url("compressed-normal"), channel="httpx",
            )
        self.assertNotIn("error", result)
        self.assertIn("Deterministic local article sentence", result["markdown"])

    def test_redirect_policy_refusal_is_terminal(self):
        with self._allow_fixture_urls(), \
             mock.patch.object(wf, "_fetch_playwright") as browser, \
             mock.patch.object(wf, "_fetch_jina") as jina:
            result = wf.web_fetch(self._url("redirect"))
        self.assertTrue(result["policy_refusal"])
        self.assertIn("non-public", result["error"])
        browser.assert_not_called()
        jina.assert_not_called()

    def test_normal_jina_response_uses_the_same_streaming_path(self):
        with mock.patch.object(wf, "_JINA_READER_BASE", self.base_url + "/reader/"), \
             self._allow_fixture_urls():
            result = wf.web_fetch(self._url("normal"), channel="api")
        self.assertEqual(result["channel"], "api")
        self.assertNotIn("error", result)
        self.assertEqual(result["title"], "Fixture article")


class BrowserBusyTests(unittest.TestCase):
    def test_browser_route_abort_preserves_policy_refusal_and_stops_cascade(self):
        class _AbortRoute:
            request = types.SimpleNamespace(url="https://private.example/secret")

            def abort(self):
                raise RuntimeError("route aborted")

        class _Page:
            def __init__(self, context):
                self.context = context

            def goto(self, _url, **_kwargs):
                self.context.http_handler(_AbortRoute())

            def content(self):
                return "<html><body>unreachable</body></html>"

        class _Context:
            def route(self, _pattern, handler):
                self.http_handler = handler

            def route_web_socket(self, _pattern, _handler):
                return None

            def new_page(self):
                return _Page(self)

        class _Browser:
            def new_context(self, **_kwargs):
                self.context = _Context()
                return self.context

            def close(self):
                return None

        browser = _Browser()
        manager = mock.MagicMock()
        manager.__enter__.return_value = types.SimpleNamespace(
            chromium=types.SimpleNamespace(
                launch=mock.Mock(return_value=browser),
            ),
        )
        manager.__exit__.return_value = False
        playwright_package = types.ModuleType("playwright")
        playwright_package.__path__ = []
        sync_api = types.ModuleType("playwright.sync_api")
        sync_api.sync_playwright = mock.Mock(return_value=manager)
        trafilatura = types.ModuleType("trafilatura")
        short = wf._error_result("https://example.com/", "httpx", "short")
        with mock.patch.dict(sys.modules, {
            "playwright": playwright_package,
            "playwright.sync_api": sync_api,
            "trafilatura": trafilatura,
        }), mock.patch.object(
            wf.network_policy,
            "validate_browser_request",
            side_effect=network_policy.NetworkPolicyError(
                "destination resolves to a non-public address",
            ),
        ), mock.patch.object(wf, "_fetch_httpx", return_value=short), \
             mock.patch.object(wf, "_fetch_jina") as jina:
            result = wf.web_fetch("https://example.com")

        self.assertTrue(result["policy_refusal"])
        self.assertIn("non-public", result["error"])
        jina.assert_not_called()

    def test_second_browser_fetch_returns_busy_without_starting_render(self):
        entered = threading.Event()
        release = threading.Event()
        good = {
            "url": "https://example.com", "markdown": "x" * 600,
            "title": "ok", "channel": "local", "fetched_at": "now",
        }

        def hold_render(_url):
            entered.set()
            release.wait(timeout=2)
            return good

        with mock.patch.object(wf, "_fetch_playwright_locked",
                               side_effect=hold_render) as render:
            first = threading.Thread(
                target=wf._fetch_playwright, args=("https://example.com",),
                name="first-browser-fetch", daemon=True,
            )
            first.start()
            self.assertTrue(entered.wait(timeout=1))
            second = wf._fetch_playwright("https://example.com")
            release.set()
            first.join(timeout=2)

        self.assertTrue(second["browser_busy"])
        self.assertIn("busy", second["error"])
        self.assertEqual(first.is_alive(), False)
        render.assert_called_once()

    def test_busy_browser_result_falls_through_to_jina_in_auto_mode(self):
        self.assertTrue(wf._BROWSER_FETCH_LOCK.acquire(blocking=False))
        try:
            bad = {
                "url": "https://example.com", "markdown": "",
                "title": None, "channel": "httpx", "fetched_at": "now",
                "error": "short",
            }
            jina_result = {
                "url": "https://example.com", "markdown": "j" * 600,
                "title": "jina", "channel": "api", "fetched_at": "now",
            }
            with mock.patch.object(wf, "_fetch_httpx", return_value=bad), \
                 mock.patch.object(wf, "_fetch_jina",
                                   return_value=jina_result) as jina:
                result = wf.web_fetch("https://example.com")
        finally:
            wf._BROWSER_FETCH_LOCK.release()
        self.assertIs(result, jina_result)
        jina.assert_called_once_with(
            "https://example.com/", reason="automatic-fallback",
        )


@unittest.skipUnless(_LIVE, "set ORA_WEB_FETCH_LIVE=1 to run network smoke")
class LiveSmokeTests(unittest.TestCase):
    """Hit the open network. Skipped by default."""

    def test_httpx_fetches_example_com(self):
        result = wf.web_fetch("https://example.com", channel="httpx")
        self.assertEqual(result["channel"], "httpx")
        # example.com is small; cascade would escalate but pinning works.
        self.assertNotIn("error", result)

    def test_cascade_auto_completes(self):
        result = wf.web_fetch("https://example.com")
        self.assertIn(result["channel"], {"httpx", "local", "api"})


if __name__ == "__main__":
    unittest.main()
