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
import tempfile
import unittest
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
